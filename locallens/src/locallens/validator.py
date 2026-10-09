"""Two checks before anything runs: the frame makes sense, and the SQL only touches known columns."""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from .frame import QueryFrame
from .ingest import FLAT
from .registry import Registry
from .sqlgen import FrameError


def validate_frame(frame: QueryFrame, reg: Registry) -> None:
    metrics = {c.flat_name for c in reg.tagged("metric")}
    dims = {c.flat_name for c in reg.tagged("dimension")}
    dates = {c.flat_name for c in reg.tagged("date")}
    if frame.metric.column not in metrics:
        raise FrameError(f"{frame.metric.column!r} is not a metric column.")
    if frame.dimension and frame.dimension not in dims:
        raise FrameError(f"{frame.dimension!r} is not a dimension column.")
    if frame.time and frame.time.column not in dates:
        raise FrameError(f"{frame.time.column!r} is not a date column.")
    for f in frame.filters:
        if f.column not in dims | metrics:
            raise FrameError(f"Cannot filter on {f.column!r}.")


def validate_sql(sql: str, reg: Registry) -> None:
    try:
        parsed = sqlglot.parse_one(sql, read="duckdb")
    except sqlglot.errors.ParseError as e:
        raise FrameError(f"Generated SQL does not parse: {e}") from e
    if not isinstance(parsed, exp.Select):
        raise FrameError("Only SELECT statements are allowed.")
    tables = {t.name for t in parsed.find_all(exp.Table)}
    if tables != {FLAT}:
        raise FrameError(f"Query may only read {FLAT!r}, found {sorted(tables)}.")
    allowed = {c.flat_name for c in reg.columns if c.flat_name} | {
        a.alias for a in parsed.find_all(exp.Alias)
    }
    unknown = {c.name for c in parsed.find_all(exp.Column)} - allowed
    if unknown:
        raise FrameError(f"Unknown columns: {sorted(unknown)}")
