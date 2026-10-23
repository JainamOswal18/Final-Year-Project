"""Deterministic frame -> SQL. ~6 templates, no model involved."""
from __future__ import annotations

from locallens.query.frame import QueryFrame
from ..data.ingest import FLAT
from ..data.registry import Registry

DEFAULT_GRAIN = "month"
DEFAULT_TOP_N = 10


class FrameError(ValueError):
    """The frame is internally inconsistent; the UI turns this into a clarification."""


def _q(ident: str) -> str:
    return '"' + ident.replace('"', '""') + '"'


def _lit(value: str, numeric: bool) -> str:
    if numeric:
        try:
            float(value)
        except ValueError as e:
            raise FrameError(f"Expected a number, got {value!r}") from e
        return value
    return "'" + value.replace("'", "''") + "'"


def metric_alias(frame: QueryFrame, reg: Registry | None = None) -> str:
    if reg is not None and reg.measure(frame.metric.column):
        return frame.metric.column                      # a measure is already an aggregate
    return f"{frame.metric.agg.lower()}_{frame.metric.column}"


def _metric_expr(frame: QueryFrame, reg: Registry) -> str:
    m = frame.metric
    measure = reg.measure(m.column)
    if measure:
        return f"{measure.expression} AS {_q(metric_alias(frame, reg))}"
    return f"{m.agg}({_q(m.column)}) AS {_q(metric_alias(frame, reg))}"


def _rule_conditions(frame: QueryFrame, reg: Registry) -> list[str]:
    """Always-on rules, plus the phrase-triggered rules the pipeline recorded on the frame."""
    return [f"({r.condition})" for r in reg.active_rules() if not r.phrases or r.name in frame.rules]


def _where(frame: QueryFrame, reg: Registry) -> str:
    conds: list[str] = []
    t = frame.time
    if t and t.start:
        conds.append(f"CAST({_q(t.column)} AS DATE) >= DATE {_lit(t.start, False)}")
    if t and t.end:
        conds.append(f"CAST({_q(t.column)} AS DATE) <= DATE {_lit(t.end, False)}")
    for f in frame.filters:
        col = reg.by_flat_name(f.column)
        numeric = bool(col and col.tag == "metric")
        if f.op == "in":
            vals = ", ".join(_lit(v.strip(), numeric) for v in f.value.split(",") if v.strip())
            conds.append(f"{_q(f.column)} IN ({vals})")
        else:
            conds.append(f"{_q(f.column)} {f.op} {_lit(f.value, numeric)}")
    conds += _rule_conditions(frame, reg)
    return ("WHERE " + " AND ".join(conds)) if conds else ""


def _period(frame: QueryFrame, reg: Registry) -> str:
    """Start date of the period each row falls in. Years and quarters follow the financial calendar: shift the
    date back so the fiscal year starts on January 1st, truncate, then shift forward again."""
    t = frame.time
    grain = (t.grain if t else None) or DEFAULT_GRAIN
    day = f"CAST({_q(t.column)} AS DATE)"
    shift = {"year": reg.fiscal_start_month - 1, "quarter": (reg.fiscal_start_month - 1) % 3}.get(grain, 0)
    if not shift:
        return f"date_trunc('{grain}', {day})"
    return f"CAST(date_trunc('{grain}', {day} - INTERVAL {shift} MONTH) + INTERVAL {shift} MONTH AS DATE)"


def build_sql(frame: QueryFrame, reg: Registry) -> str:
    where = _where(frame, reg)
    value = _q(metric_alias(frame, reg))
    m = _metric_expr(frame, reg)
    dim = _q(frame.dimension) if frame.dimension else None
    measure = reg.measure(frame.metric.column)
    if measure and frame.intent == "distribution":
        raise FrameError(f"{measure.label or measure.name} is a calculated total, so it has no spread of values. "
                         "Try a trend or a comparison.")
    if measure and frame.intent == "proportion" and not measure.additive:
        raise FrameError(f"{measure.label or measure.name} can't be split into shares. Try a comparison instead.")

    if frame.intent == "trend":
        if not frame.time:
            raise FrameError("A trend needs a date column.")
        period = _period(frame, reg)
        if dim:
            return (f"SELECT {period} AS period, {dim}, {m} FROM {FLAT} {where} "
                    f"GROUP BY 1, 2 ORDER BY 1, 2")
        return f"SELECT {period} AS period, {m} FROM {FLAT} {where} GROUP BY 1 ORDER BY 1"

    if frame.intent in ("comparison", "ranking", "proportion"):
        if not dim:
            raise FrameError(f"A {frame.intent} needs something to group by.")
        limit = ""
        if frame.intent == "ranking":
            limit = f" LIMIT {int(frame.top_n or DEFAULT_TOP_N)}"
        return (f"SELECT {dim}, {m} FROM {FLAT} {where} "
                f"GROUP BY 1 ORDER BY {value} {'ASC' if frame.order == 'asc' and frame.intent == 'ranking' else 'DESC'}, 1{limit}")   # 2nd key: ties stay in a stable order

    if frame.intent == "distribution":
        return f"SELECT {_q(frame.metric.column)} FROM {FLAT} {where} LIMIT 100000"

    # summary
    return f"SELECT {m} FROM {FLAT} {where}"
