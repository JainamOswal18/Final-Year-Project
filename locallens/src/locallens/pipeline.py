"""question -> Result. No UI code here so any front end can call it."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import duckdb
import pandas as pd

from . import engine
from .charts import ChartSpec, build_spec
from .frame import Filter, QueryFrame, TimeSpec
from .ingest import FLAT
from .preprocess import Preprocessed, phrase_re, preprocess
from .profiler import profile
from .registry import Registry
from .rules import infer
from .session import Clarification, Session
from .sqlgen import FrameError, build_sql
from .validator import validate_frame, validate_sql


class FrameFiller(Protocol):
    def fill_frame(self, pre: Preprocessed, reg: Registry, prev: QueryFrame | None = None) -> tuple[QueryFrame, str]: ...


@dataclass
class Result:
    question: str
    frame: QueryFrame | None = None
    raw_frame: str = ""
    sql: str = ""
    df: pd.DataFrame | None = None
    chart: ChartSpec | None = None
    clarification: Clarification | None = None
    corrections: list[tuple[str, str]] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
    error: str = ""


def data_today(con: duckdb.DuckDBPyConnection, reg: Registry) -> date:
    dates = reg.tagged("date")
    if not dates:
        return date.today()
    d = dates[0].flat_name
    return con.execute(f'SELECT max(CAST("{d}" AS DATE)) FROM {FLAT}').fetchone()[0]


def _ground_filters(frame: QueryFrame, text: str, reg: Registry, prev: QueryFrame | None = None) -> None:
    """Small models invent filters. Keep a filter only if its value is literally in the question
    and, where we know the column's full value list, is a real value (normalised to real casing)."""
    t = text.lower()
    carried = {(f.column, f.value) for f in prev.filters} if prev else set()
    kept = []
    for f in frame.filters:
        if (f.column, f.value) in carried:
            kept.append(f)
            continue
        vals = [v.strip() for v in f.value.split(",") if v.strip()]
        if not vals or not all(v.lower() in t for v in vals):
            continue
        col = reg.by_flat_name(f.column)
        if col and col.values:
            real = {v.lower(): v for v in col.values}
            if not all(v.lower() in real for v in vals):
                continue
            f.value = ",".join(real[v.lower()] for v in vals)
        kept.append(f)
    frame.filters = kept


def _ground_dimension(frame: QueryFrame, pre: Preprocessed, reg: Registry, prev: QueryFrame | None = None) -> None:
    """The group-by column must be mentioned in the question, otherwise the model made it up."""
    # the question names a value of this column ("consumer segment"), so it is a filter, not the grouping
    value_cols = {c for c, _ in pre.value_mentions}
    if frame.dimension in value_cols:
        hinted = [c for c in pre.column_hints.values()
                  if c not in value_cols and (col := reg.by_flat_name(c)) and col.tag == "dimension"]
        if hinted:
            frame.dimension = hinted[0]
    if not frame.dimension or (prev and frame.dimension == prev.dimension):
        return  # nothing to check, or carried over from the previous question in a follow-up
    t = pre.text.lower()
    if not any(re.search(phrase_re(p), t) for p in reg.phrases(frame.dimension)):
        frame.dimension = None


def _add_value_filters(frame: QueryFrame, pre: Preprocessed) -> None:
    """A dimension value named in the question (e.g. 'corporate') is a filter, even if the model missed it."""
    have = {f.column for f in frame.filters}
    for col, val in pre.value_mentions:
        if col not in have and col != frame.dimension:
            frame.filters.append(Filter(column=col, op="=", value=val))


def _apply_rules(frame: QueryFrame, pre: Preprocessed, reg: Registry) -> None:
    """Rule-assisted overrides: where a keyword rule fires, it beats the model."""
    dates = reg.tagged("date")
    dim_cols = {c.flat_name for c in reg.tagged("dimension")}
    # a dimension phrase that is not just a filter value ("by city", not "corporate customers")
    has_dim = any(c in dim_cols and c not in {v for v, _ in pre.value_mentions} for c in pre.column_hints.values())
    h = infer(pre.text, has_dim, bool(dates))
    if h.intent:
        frame.intent = h.intent
    frame.metric.agg = h.agg or frame.metric.agg
    if h.top_n:
        frame.top_n = h.top_n
    if frame.intent == "trend" and dates and frame.time is None:
        frame.time = TimeSpec(column=dates[0].flat_name, grain=h.grain)
    if frame.time and h.grain:
        frame.time.grain = h.grain
    if frame.intent in ("distribution", "summary"):
        frame.dimension = None
    if frame.intent in ("comparison", "ranking", "proportion") and not frame.dimension:
        hinted = [c for c in pre.column_hints.values() if c in dim_cols and c not in {v for v, _ in pre.value_mentions}]
        frame.dimension = hinted[0] if hinted else None


def _apply_date_hint(frame: QueryFrame, pre: Preprocessed, reg: Registry) -> None:
    """Deterministic date resolution wins over whatever the model produced."""
    h = pre.date_hint
    dates = reg.tagged("date")
    if not (h and dates):
        return
    col = frame.time.column if frame.time else dates[0].flat_name
    grain = (frame.time.grain if frame.time else None) or h.grain
    frame.time = TimeSpec(column=col, grain=grain, start=h.start.isoformat(), end=h.end.isoformat())


FOLLOWUP_STARTS = ("now", "also", "and", "only", "same", "instead", "split", "break", "what about", "how about", "but")


def is_followup(question: str, session: Session) -> bool:
    if session.last_frame is None:
        return False
    q = question.lower().strip()
    return q.startswith(FOLLOWUP_STARTS) or len(q.split()) <= 3


def _apply_overrides(frame: QueryFrame, overrides: dict[str, str]) -> None:
    """Apply a column the user picked from a clarification."""
    if "metric" in overrides:
        frame.metric.column = overrides["metric"]
    if "dimension" in overrides:
        frame.dimension = overrides["dimension"]
    if "time" in overrides and frame.time:
        frame.time.column = overrides["time"]
    frame.ambiguous = []


def ask(
    question: str, reg: Registry, con: duckdb.DuckDBPyConnection, slm: FrameFiller,
    session: Session | None = None, prefs: dict | None = None, followup: bool = False,
    overrides: dict[str, str] | None = None,
) -> Result:
    session = session or Session()
    res = Result(question=question)
    t0 = time.perf_counter()
    try:
        pre = preprocess(question, reg, data_today(con, reg))
    except ValueError as e:
        res.error = str(e)
        return res
    res.corrections = pre.corrections
    res.timings_ms["preprocess"] = (time.perf_counter() - t0) * 1000

    # a term that could mean several columns -> ask, don't guess
    if pre.ambiguous_terms and not overrides:
        phrase, cols = next(iter(pre.ambiguous_terms.items()))
        res.clarification = Clarification(
            f'"{phrase}" could mean more than one column. Which one?', "metric", cols, question)
        session.pending = res.clarification
        return res

    t1 = time.perf_counter()
    try:
        frame, raw = slm.fill_frame(pre, reg, session.last_frame if followup else None)
    except Exception as e:  # model output failed validation / generation error
        res.error = f"Could not interpret the question: {e}"
        return res
    res.timings_ms["slm"] = (time.perf_counter() - t1) * 1000
    res.raw_frame = raw

    prev = session.last_frame if followup else None
    _ground_filters(frame, pre.text, reg, prev)
    _ground_dimension(frame, pre, reg, prev)
    if not followup:
        _apply_rules(frame, pre, reg)
    _add_value_filters(frame, pre)
    if overrides:
        _apply_overrides(frame, overrides)
    _apply_date_hint(frame, pre, reg)
    res.frame = frame
    try:
        validate_frame(frame, reg)
        if frame.ambiguous:
            field_ = frame.ambiguous[0]
            tag = {"metric": "metric", "dimension": "dimension", "time": "date"}.get(field_)
            if tag:
                res.clarification = Clarification(
                    f"I wasn't sure which {field_} you meant.", field_,
                    [c.flat_name for c in reg.tagged(tag)], question)
                session.pending = res.clarification
                return res
        t2 = time.perf_counter()
        sql = build_sql(frame, reg)
        validate_sql(sql, reg)
        res.sql = sql
        res.timings_ms["sql"] = (time.perf_counter() - t2) * 1000
        t3 = time.perf_counter()
        res.df = engine.run(con, sql)
        res.timings_ms["query"] = (time.perf_counter() - t3) * 1000
        if res.df.empty:
            res.error = "The query returned no rows. Try a different date range or filter."
            return res
        res.chart = build_spec(res.df, frame.intent, profile(res.df), prefs)
    except FrameError as e:
        res.error = str(e)
        return res
    res.timings_ms["total"] = (time.perf_counter() - t0) * 1000
    session.last_frame = frame
    session.pending = None
    session.history.append(question)
    return res
