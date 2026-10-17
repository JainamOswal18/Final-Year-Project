"""Result -> JSON for the web app (rows, chart spec, explanation)."""
from __future__ import annotations

import datetime as dt
import decimal
import math

import numpy as np
import pandas as pd

from ..core.pipeline import Result
from ..data.profiler import profile
from ..data.registry import Registry
from ..viz import export_pbi
from ..viz.adapters import ADAPTERS


def json_value(v):
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return v.strftime("%Y-%m-%d") if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat(sep=" ")
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float, decimal.Decimal)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v if isinstance(v, (int, str, bool)) else str(v)


def table_payload(df: pd.DataFrame, limit: int) -> dict:
    p = profile(df)
    shown = df.head(limit)
    return {
        "columns": [{"name": c, "kind": p.kinds.get(c, "categorical")} for c in df.columns],
        "rows": [[json_value(v) for v in row] for row in shown.itertuples(index=False, name=None)],
        "row_count": int(len(df)),
        "truncated": len(df) > limit,
    }


def _web_chart(res: Result) -> tuple[dict, pd.DataFrame]:
    """The spec to draw and the table it draws from. Histograms are binned here, not in the browser."""
    chart, df = res.chart, res.df
    if chart.type == "histogram":
        binned = export_pbi.prepare_frame(df, "histogram")
        x = binned.columns[0]
        spec = {"mark": "bar", "encoding": {
            "x": {"field": x, "type": "ordinal", "sort": None, "title": df.columns[0].replace("_", " ")},
            "y": {"field": "count", "type": "quantitative", "title": "orders"}}}
        return {"type": "histogram", "reason": chart.reason, "fallback": False, "spec": spec}, binned
    return {"type": chart.type, "reason": chart.reason, "fallback": chart.fallback, "spec": chart.spec}, df


def result_payload(res: Result, reg: Registry, max_rows: int) -> dict:
    out: dict = {"question": res.question, "error": res.error, "corrections": [list(c) for c in res.corrections], "semantic": [list(c) for c in res.semantic],
                 "timings_ms": {k: round(v, 1) for k, v in res.timings_ms.items()}, "clarification": None,
                 "frame": None, "sql": "", "rules": [], "chart": None, "kpi": None, "metric": None,
                 "exports": [], "columns": [], "rows": [], "row_count": 0, "truncated": False}
    if res.clarification:
        c = res.clarification
        out["clarification"] = {"message": c.message, "field": c.field, "options": c.options, "question": c.question}
    if res.frame:
        f = res.frame
        out["frame"] = f.model_dump()
        out["sql"] = res.sql
        by_name = {r.name: r for r in reg.rules}
        out["rules"] = [{"name": r.name, "description": r.description, "always": not r.phrases}
                        for r in reg.active_rules() if not r.phrases or r.name in f.rules]
        m = reg.measure(f.metric.column)
        col = reg.by_flat_name(f.metric.column)
        out["metric"] = {"name": f.metric.column,
                         "label": (m.label or m.name.replace("_", " ")) if m else f.metric.column.replace("_", " "),
                         "format": m.format if m else "number",
                         "agg": None if m else f.metric.agg,
                         "description": (m.description if m else (col.description if col else ""))}
        _ = by_name
    if res.df is not None and res.chart is not None:
        chart, shown = _web_chart(res)
        out["chart"] = chart
        out.update(table_payload(shown, max_rows))
        if chart["type"] == "kpi":
            out["kpi"] = {"value": json_value(res.df.iloc[0, 0]), "label": res.df.columns[0].replace("_", " ")}
        out["exports"] = [k for k, a in ADAPTERS.items() if a.supports(res.chart.type)] + ["csv"]
    return out
