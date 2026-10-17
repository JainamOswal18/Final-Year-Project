"""Intent x result shape -> Vega-Lite spec, by rule (patent claims 9-11)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from ..data.profiler import Profile

RULES = yaml.safe_load((Path(__file__).parent / "charts_rules.yaml").read_text())


@dataclass
class ChartSpec:
    type: str                         # line|multi_line|bar|hbar|donut|histogram|scatter|kpi|table_bar
    spec: dict = field(default_factory=dict)  # Vega-Lite (no data); empty for kpi
    fallback: bool = False            # True when the default policy was used
    reason: str = ""                  # shown in the "How I read this" panel


def _matches(when: dict, intent: str, p: Profile) -> bool:
    first_cat = p.category_cols[0] if p.category_cols else None
    checks = {
        "intent": lambda v: intent in v,
        "has_time": lambda v: bool(p.time_col) == v,
        "n_category": lambda v: len(p.category_cols) == v,
        "n_numeric": lambda v: len(p.numeric_cols) == v,
        "rows": lambda v: p.rows == v,
        "max_categories": lambda v: first_cat is None or p.cardinality[first_cat] <= v,
        "min_categories": lambda v: first_cat is not None and p.cardinality[first_cat] >= v,
    }
    return all(checks[k](v) for k, v in when.items())


def pick_chart(intent: str, p: Profile, prefs: dict | None = None) -> tuple[str, str, bool]:
    """Returns (chart type, reason, used_default)."""
    override = (prefs or {}).get("chart_overrides", {}).get(intent)
    for rule in RULES["rules"]:
        if _matches(rule["when"], intent, p):
            chart = rule["chart"]
            reason = f"rule: {rule['when']} -> {chart}"
            if override and _compatible(override, chart):
                return override, f"your saved preference for {intent} -> {override}", False
            return chart, reason, False
    return RULES["default"], "no rule matched -> default (table + bar)", True


def _compatible(override: str, chosen: str) -> bool:
    groups = [{"bar", "hbar", "donut"}, {"line", "multi_line"}]
    return any(override in g and chosen in g for g in groups)


def build_spec(df: pd.DataFrame, intent: str, p: Profile, prefs: dict | None = None) -> ChartSpec:
    chart, reason, fallback = pick_chart(intent, p, prefs)
    t = p.time_col
    nums = p.numeric_cols
    cats = p.category_cols
    y = nums[0] if nums else None
    desc = (prefs or {}).get("sort", "desc")

    if chart == "kpi":
        return ChartSpec("kpi", {}, False, reason)
    if chart == "line":
        spec = {"mark": {"type": "line", "point": True},
                "encoding": {"x": {"field": t, "type": "temporal"}, "y": {"field": y, "type": "quantitative"}}}
    elif chart == "multi_line":
        spec = {"mark": {"type": "line", "point": True},
                "encoding": {"x": {"field": t, "type": "temporal"}, "y": {"field": y, "type": "quantitative"},
                             "color": {"field": cats[0], "type": "nominal"}}}
    elif chart in ("bar", "table_bar"):
        x = cats[0] if cats else (df.columns[0])
        sort = "-y" if desc == "desc" else "y"
        spec = {"mark": "bar",
                "encoding": {"x": {"field": x, "type": "nominal", "sort": sort},
                             "y": {"field": y or df.columns[-1], "type": "quantitative"}}}
    elif chart == "hbar":
        sort = "-x" if desc == "desc" else "x"
        spec = {"mark": "bar",
                "encoding": {"y": {"field": cats[0], "type": "nominal", "sort": sort},
                             "x": {"field": y, "type": "quantitative"}}}
    elif chart == "donut":
        spec = {"mark": {"type": "arc", "innerRadius": 60},
                "encoding": {"theta": {"field": y, "type": "quantitative"},
                             "color": {"field": cats[0], "type": "nominal"}}}
    elif chart == "histogram":
        spec = {"mark": "bar",
                "encoding": {"x": {"field": y, "type": "quantitative", "bin": True},
                             "y": {"aggregate": "count", "type": "quantitative"}}}
    elif chart == "scatter":
        spec = {"mark": "point",
                "encoding": {"x": {"field": nums[0], "type": "quantitative"},
                             "y": {"field": nums[1], "type": "quantitative"}}}
    else:  # pragma: no cover
        raise ValueError(chart)
    return ChartSpec(chart, spec, fallback, reason)
