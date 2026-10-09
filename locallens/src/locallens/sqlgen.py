"""Deterministic frame -> SQL. ~6 templates, no model involved."""
from __future__ import annotations

from .frame import QueryFrame
from .ingest import FLAT
from .registry import Registry

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


def metric_alias(frame: QueryFrame) -> str:
    return f"{frame.metric.agg.lower()}_{frame.metric.column}"


def _metric_expr(frame: QueryFrame) -> str:
    m = frame.metric
    return f"{m.agg}({_q(m.column)}) AS {_q(metric_alias(frame))}"


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
    return ("WHERE " + " AND ".join(conds)) if conds else ""


def _period(frame: QueryFrame) -> str:
    t = frame.time
    grain = (t.grain if t else None) or DEFAULT_GRAIN
    return f"date_trunc('{grain}', CAST({_q(t.column)} AS DATE))"


def build_sql(frame: QueryFrame, reg: Registry) -> str:
    where = _where(frame, reg)
    value = _q(metric_alias(frame))
    m = _metric_expr(frame)
    dim = _q(frame.dimension) if frame.dimension else None

    if frame.intent == "trend":
        if not frame.time:
            raise FrameError("A trend needs a date column.")
        period = _period(frame)
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
                f"GROUP BY 1 ORDER BY {value} DESC{limit}")

    if frame.intent == "distribution":
        return f"SELECT {_q(frame.metric.column)} FROM {FLAT} {where} LIMIT 100000"

    # summary
    return f"SELECT {m} FROM {FLAT} {where}"
