"""Result -> Power BI Desktop project (.pbip), patent claim 13.

The folder is self-contained: the query result is embedded in the model as an
inline table (like "Enter data"), so nothing points at this machine's paths and
nothing is uploaded anywhere. Open the .pbip in Power BI Desktop (Windows).
"""
from __future__ import annotations

import base64
import io
import json
import re
import uuid
import zipfile
from pathlib import Path

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_integer_dtype, is_numeric_dtype

from locallens.viz.charts import ChartSpec
from ..data.profiler import profile

TABLE = "Result"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
PAGE_W, PAGE_H = 1280, 720
SUM, COUNT = 0, 3   # Power BI aggregation function ids

# our chart type -> Power BI visualType
VISUAL = {"line": "lineChart", "multi_line": "lineChart", "bar": "clusteredColumnChart",
          "table_bar": "clusteredColumnChart", "hbar": "clusteredBarChart", "donut": "donutChart",
          "histogram": "clusteredColumnChart", "scatter": "scatterChart", "kpi": "card"}


class ExportError(Exception):
    pass


def safe_name(text: str, fallback: str = "LocalLens chart", limit: int = 40) -> str:
    s = re.sub(r"[^\w\- ]+", "", text).strip()
    s = re.sub(r"\s+", " ", s)[:limit].strip()
    return s or fallback


# ---- data prep ---------------------------------------------------------------
def _bin_histogram(df: pd.DataFrame, col: str, bins: int = 10) -> pd.DataFrame:
    s = df[col].dropna()
    cut = pd.cut(s, bins=min(bins, max(1, s.nunique())))
    counts = cut.value_counts(sort=False)
    return pd.DataFrame({f"{col}_bin_start": [round(float(i.left), 2) for i in counts.index],
                         "count": counts.to_numpy().astype(int)})


def prepare_frame(df: pd.DataFrame, chart_type: str) -> pd.DataFrame:
    """Shape the result for Power BI (histogram -> bins, scatter -> point id)."""
    p = profile(df)
    if chart_type == "histogram":
        return _bin_histogram(df, p.numeric_cols[0])
    if chart_type == "scatter":
        out = df.copy()
        out.insert(0, "point", range(1, len(out) + 1))
        return out
    return df.reset_index(drop=True)


# ---- TMDL (semantic model) ----------------------------------------------------
def _col_kind(s: pd.Series) -> tuple[str, str, str]:
    """(tmdl dataType, M type, summarizeBy)"""
    if is_datetime64_any_dtype(s):
        return "dateTime", "type date", "none"
    if is_integer_dtype(s):
        return "int64", "Int64.Type", "sum"
    if is_numeric_dtype(s):
        return "double", "type number", "sum"
    return "string", "type text", "none"


def _cell(v, s: pd.Series):
    if pd.isna(v):
        return None
    if is_datetime64_any_dtype(s):
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    if is_integer_dtype(s):
        return int(v)
    if is_numeric_dtype(s):
        return float(v)
    return str(v)


def _m_expression(df: pd.DataFrame) -> str:
    rows = [[_cell(v, df[c]) for c, v in zip(df.columns, r)] for r in df.itertuples(index=False, name=None)]
    b64 = base64.b64encode(json.dumps(rows, ensure_ascii=True, separators=(",", ":")).encode()).decode()
    names = ", ".join(f'{_q(c)} = _t' for c in df.columns)
    types = ", ".join(f'{{{_mq(c)}, {_col_kind(df[c])[1]}}}' for c in df.columns)
    return (
        "let\n"
        f'    Source = Table.FromRows(Json.Document(Binary.FromText("{b64}", BinaryEncoding.Base64)), '
        f"let _t = ((type nullable text) meta [Serialized.Text = true]) in type table [{names}]),\n"
        f'    #"Changed Type" = Table.TransformColumnTypes(Source, {{{types}}}, "en-US")\n'
        "in\n"
        '    #"Changed Type"'
    )


def _q(name: str) -> str:   # M record field name
    return name if re.fullmatch(r"[A-Za-z_]\w*", name) else '#"' + name.replace('"', '""') + '"'


def _mq(name: str) -> str:  # M string literal
    return '"' + name.replace('"', '""') + '"'


def _tmdl_name(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_]\w*", name) else "'" + name.replace("'", "''") + "'"


def measure_name(col: str) -> str:
    """The model measure that adds up a column. Charts use these, never a bare column: the model switches
    implicit measures off (discourageImplicitMeasures), so an aggregated column would not draw."""
    return f"Sum of {col}"


def _measure_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if is_numeric_dtype(df[c]) and c != "point"]


def tmdl_table(df: pd.DataFrame) -> str:
    lines = [f"table {TABLE}", f"\tlineageTag: {uuid.uuid4()}", ""]
    for c in df.columns:
        dtype, _, summ = _col_kind(df[c])
        lines += [f"\tcolumn {_tmdl_name(c)}", f"\t\tdataType: {dtype}"]
        if dtype == "dateTime":
            lines.append("\t\tformatString: Long Date")
        lines += [f"\t\tlineageTag: {uuid.uuid4()}", f"\t\tsummarizeBy: {summ}",
                  f"\t\tsourceColumn: {c}", ""]
    for c in _measure_columns(df):
        fmt = "#,0" if is_integer_dtype(df[c]) else "#,0.00"
        ref = c.replace("]", "]]")
        lines += [f"\tmeasure {_tmdl_name(measure_name(c))} = SUM({TABLE}[{ref}])",
                  f"\t\tformatString: {fmt}", f"\t\tlineageTag: {uuid.uuid4()}", ""]
    m = "\n".join("\t\t\t\t" + ln for ln in _m_expression(df).split("\n"))
    lines += [f"\tpartition {TABLE} = m", "\t\tmode: import", "\t\tsource =", m, ""]
    return "\n".join(lines)


# ---- PBIR (report) ------------------------------------------------------------
def _col(c: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": TABLE}}, "Property": c}}


def _measure(name: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": TABLE}}, "Property": name}}


def _proj(c: str, agg: int | None = None) -> dict:
    if agg is None:
        return {"field": _col(c), "queryRef": f"{TABLE}.{c}", "nativeQueryRef": c, "active": True}
    m = measure_name(c)           # `agg` says "add this column up"; the model's measure does that
    return {"field": _measure(m), "queryRef": f"{TABLE}.{m}", "nativeQueryRef": m}


def _sort(field: dict, direction: str) -> dict:
    return {"sort": [{"field": field, "direction": direction}]}


def build_visual(chart_type: str, df: pd.DataFrame, sort: str = "desc") -> tuple[str, dict]:
    """(visualType, query) for the (already prepared) frame."""
    p = profile(df)
    vtype = VISUAL[chart_type]
    nums, cats, t = p.numeric_cols, p.category_cols, p.time_col
    direction = "Descending" if sort == "desc" else "Ascending"
    if chart_type == "kpi":
        return vtype, {"queryState": {"Values": {"projections": [_proj(nums[0], SUM)]}}}
    if chart_type in ("line", "multi_line"):
        qs = {"Category": {"projections": [_proj(t)]}, "Y": {"projections": [_proj(nums[0], SUM)]}}
        if chart_type == "multi_line":
            qs["Series"] = {"projections": [_proj(cats[0])]}
        return vtype, {"queryState": qs, "sortDefinition": _sort(_col(t), "Ascending")}
    if chart_type == "histogram":
        x = df.columns[0]
        return vtype, {"queryState": {"Category": {"projections": [_proj(x)]},
                                      "Y": {"projections": [_proj("count", SUM)]}},
                       "sortDefinition": _sort(_col(x), "Ascending")}
    if chart_type == "scatter":
        xy = [n for n in nums if n != "point"]
        return vtype, {"queryState": {"Category": {"projections": [_proj("point")]},
                                      "X": {"projections": [_proj(xy[0], SUM)]},
                                      "Y": {"projections": [_proj(xy[1], SUM)]}}}
    if chart_type == "bar" and t:
        qs = {"Category": {"projections": [_proj(t)]}, "Y": {"projections": [_proj(nums[0], SUM)]}}
        if cats:
            qs["Series"] = {"projections": [_proj(cats[0])]}
        return vtype, {"queryState": qs, "sortDefinition": _sort(_col(t), "Ascending")}
    cat = cats[0] if cats else df.columns[0]
    y = nums[0] if nums else df.columns[-1]
    qs = {"Category": {"projections": [_proj(cat)]}, "Y": {"projections": [_proj(y, SUM)]}}
    return vtype, {"queryState": qs,
                   "sortDefinition": _sort(_measure(measure_name(y)), direction)}


def _visual_json(name: str, vtype: str, query: dict, x: int, y: int, w: int, h: int, z: int) -> dict:
    return {
        "$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {"visualType": vtype, "query": query, "drillFilterOtherVisuals": True},
    }


def _table_visual(df: pd.DataFrame) -> tuple[str, dict]:
    return "tableEx", {"queryState": {"Values": {"projections": [_proj(c) for c in df.columns]}}}


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data, indent=2), encoding="utf-8")


def _vid() -> str:
    return uuid.uuid4().hex[:20]


def export_powerbi(df: pd.DataFrame, chart: ChartSpec, question: str, out_dir: Path,
                   sort: str = "desc") -> Path:
    """Write <out_dir>/<name>/<name>.pbip (+ .Report, .SemanticModel). Returns the .pbip path."""
    if df is None or df.empty:
        raise ExportError("Nothing to export: the result is empty.")
    if chart.type not in VISUAL:
        raise ExportError(f"No Power BI chart for '{chart.type}'.")
    data = prepare_frame(df, chart.type)
    name = safe_name(question)
    root = Path(out_dir) / name
    model, report = root / f"{name}.SemanticModel", root / f"{name}.Report"

    # semantic model
    _write(model / "definition.pbism", {"$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
                                        "version": "4.0", "settings": {}})
    _write(model / "definition" / "database.tmdl", "database\n\tcompatibilityLevel: 1567\n")
    _write(model / "definition" / "model.tmdl",
           f"model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n\nref table {TABLE}\n")
    _write(model / "definition" / "tables" / f"{TABLE}.tmdl", tmdl_table(data))

    # report
    _write(report / "definition.pbir", {"$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
                                        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{name}.SemanticModel"}}})
    d = report / "definition"
    _write(d / "version.json", {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
                                "version": "2.0.0"})
    _write(d / "report.json", {"$schema": f"{SCHEMA}/item/report/definition/report/2.0.0/schema.json",
                               "themeCollection": {"baseTheme": {"name": "CY24SU10", "type": "SharedResources",
                                                                 "reportVersionAtImport": "5.55"}},
                               "settings": {"useStylableVisualContainerHeader": True}})
    page = _vid()
    _write(d / "pages" / "pages.json", {"$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
                                        "pageOrder": [page], "activePageName": page})
    _write(d / "pages" / page / "page.json", {"$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
                                              "name": page, "displayName": safe_name(question, "Chart", 60),
                                              "displayOption": "FitToPage", "height": PAGE_H, "width": PAGE_W})
    vtype, query = build_visual(chart.type, data, sort)
    show_table = chart.fallback and chart.type != "kpi"
    ch = PAGE_H // 2 - 20 if show_table else PAGE_H - 40
    vid = _vid()
    _write(d / "pages" / page / "visuals" / vid / "visual.json",
           _visual_json(vid, vtype, query, 20, 20, PAGE_W - 40, ch, 0))
    if show_table:
        tv = _vid()
        ttype, tquery = _table_visual(data)
        _write(d / "pages" / page / "visuals" / tv / "visual.json",
               _visual_json(tv, ttype, tquery, 20, PAGE_H // 2 + 10, PAGE_W - 40, PAGE_H // 2 - 30, 1))

    pbip = root / f"{name}.pbip"
    _write(pbip, {"$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                  "artifacts": [{"report": {"path": f"{name}.Report"}}], "settings": {"enableAutoRecovery": True}})
    (root / f"{name}.csv").write_text(data.to_csv(index=False), encoding="utf-8")
    _write(root / "README.txt", f"Open {name}.pbip in Power BI Desktop (Windows).\n"
                                "The data is embedded in the model; nothing was uploaded.\n"
                                f"{name}.csv is the same data, for reference.\n\n"
                                "If you see only data and no chart: you may be in the Data or Model view; click the\n"
                                "Report icon (top of the left bar). If Desktop reports an unsupported format, turn on\n"
                                "File > Options > Preview features: the Power BI Project (.pbip) save option, TMDL\n"
                                "format for the semantic model, and enhanced report format (PBIR). Then reopen the file.\n")
    return pbip


def zip_project(pbip: Path) -> bytes:
    """Zip the whole project folder (for a browser download)."""
    root = pbip.parent
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(root.rglob("*")):
            if f.is_file():
                z.write(f, Path(root.name) / f.relative_to(root))
    return buf.getvalue()
