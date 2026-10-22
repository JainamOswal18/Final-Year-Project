"""question -> Result. No UI code here so any front end can call it."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import duckdb
import pandas as pd

from ..data import engine
from ..viz.charts import ChartSpec, build_spec
from ..query.frame import Filter, QueryFrame, TimeSpec
from ..data.ingest import FLAT
from ..nlu.preprocess import Preprocessed, _hints, phrase_re, preprocess, unknown_group_term
from ..data.profiler import profile
from ..data.registry import Registry
from ..nlu.rules import infer
from .session import Clarification, Session
from ..query.sqlgen import FrameError, build_sql
from ..query.validator import validate_frame, validate_sql


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
    semantic: list[tuple[str, str]] = field(default_factory=list)   # (word, column) understood by meaning
    timings_ms: dict[str, float] = field(default_factory=dict)
    error: str = ""


def data_today(con: duckdb.DuckDBPyConnection, reg: Registry) -> date:
    dates = reg.tagged("date")
    if not dates:
        return date.today()
    d = dates[0].flat_name
    return con.execute(f'SELECT max(CAST("{d}" AS DATE)) FROM {FLAT}').fetchone()[0]


DATA_WORDS = re.compile(
    r"\b(?:total|sum|average|avg|mean|count|how many|number of|max|maximum|min|minimum|top|bottom|best|worst|"
    r"highest|lowest|most|least|rank|ranking|compare|comparison|versus|vs|trend|growth|over time|distribution|"
    r"spread|histogram|share|proportion|percent|percentage|daily|weekly|monthly|quarterly|yearly|annual|"
    r"per|each|by)\b", re.I)


def looks_like_data_question(pre: Preprocessed, reg: Registry | None = None) -> bool:
    """False for 'hi there' and other chatter: no column, value, date or analysis word in it."""
    t = pre.text.lower()
    rule_phrase = bool(reg) and any(p.lower() in t for r in reg.active_rules() for p in r.phrases)
    return bool(pre.column_hints or pre.value_mentions or pre.date_hint or pre.ambiguous_terms
                or rule_phrase or DATA_WORDS.search(pre.text))


def _not_a_data_question(reg: Registry) -> str:
    metric = (reg.tagged("metric") or [None])[0]
    dim = (reg.tagged("dimension") or [None])[0]
    m = metric.flat_name.replace("_", " ") if metric else "sales"
    d = dim.flat_name.replace("_", " ") if dim else "category"
    return ("That doesn't look like a question about your data, so I won't guess. "
            f"Try something like: \"total {m}\", \"{m} by {d}\", \"monthly {m} for 2024\" "
            f"or \"top 5 {d} by {m}\".")


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


def _value_beside_column(text: str, value: str, phrases: list[str]) -> bool:
    v = re.escape(value.lower())
    return any(re.search(rf"\b{v}\s+{phrase_re(p)[2:-2]}\b|{phrase_re(p)}\s+(?:of\s+|=\s*|is\s+)?{v}\b", text.lower())
               for p in phrases)


def _grouped_by(text: str, phrases: list[str]) -> bool:
    t = text.lower()
    return any(re.search(rf"\b(?:by|per|each|across|every|for each)\s+(?:the\s+)?{phrase_re(p)[2:-2]}", t) for p in phrases)


def _singular(text: str, phrase: str) -> bool:
    """The phrase appears in the question in singular form only ("store", not "stores")."""
    t = text.lower()
    plural = phrase[:-1] + "ies" if phrase.endswith("y") else phrase + "s"
    return bool(re.search(rf"\b{re.escape(phrase)}\b", t)) and not re.search(rf"\b{re.escape(plural)}\b", t)


def _ground_dimension(frame: QueryFrame, pre: Preprocessed, reg: Registry, prev: QueryFrame | None = None) -> None:
    """The group-by column must be mentioned in the question, otherwise the model made it up."""
    # "the Technology category by month": the value sits next to the column name, so it is a filter, not a grouping
    for col, val in pre.value_mentions:
        if frame.dimension == col and _value_beside_column(pre.text, val, reg.phrases(col)) \
                and not _grouped_by(pre.text, reg.phrases(col)):
            frame.dimension = None
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


def _value_columns(pre: Preprocessed, reg: Registry, chosen: str | None = None) -> tuple[dict[str, str], dict[str, list[str]]]:
    """For a value that exists in several columns ("West" in store_region and cust_region): which column
    does the question mean? Returns (resolved value -> column, unresolved value -> candidate columns)."""
    by_val: dict[str, list[str]] = {}
    for col, val in pre.value_mentions:
        by_val.setdefault(val.lower(), []).append(col)
    named = set(pre.column_hints.values())
    resolved, unresolved = {}, {}
    for val, cols in by_val.items():
        if len(cols) == 1:
            continue
        beside = [c for c in cols if _value_beside_column(pre.text, val, reg.phrases(c))]
        said = [c for c in cols if c in named]
        pick = [chosen] if chosen in cols else beside if len(beside) == 1 else said if len(said) == 1 else []
        if len(pick) == 1:
            resolved[val] = pick[0]
        else:
            unresolved[val] = cols
    return resolved, unresolved


def _add_value_filters(frame: QueryFrame, pre: Preprocessed, resolved: dict[str, str] | None = None) -> None:
    """A dimension value named in the question (e.g. 'corporate') is a filter, even if the model missed it."""
    resolved = resolved or {}
    frame.filters = [f for f in frame.filters if not (f.value.lower() in resolved and resolved[f.value.lower()] != f.column)]
    have = {f.column for f in frame.filters}
    for col, val in pre.value_mentions:
        if val.lower() in resolved and resolved[val.lower()] != col:
            continue
        if col not in have and col != frame.dimension:
            frame.filters.append(Filter(column=col, op="=", value=val))


def _apply_rules(frame: QueryFrame, pre: Preprocessed, reg: Registry) -> None:
    """Rule-assisted overrides: where a keyword rule fires, it beats the model."""
    dates = reg.tagged("date")
    dim_cols = {c.flat_name for c in reg.tagged("dimension")}
    # a dimension phrase that is not just a filter value ("by city", not "corporate customers")
    has_dim = any(c in dim_cols and c not in {v for v, _ in pre.value_mentions} for c in pre.column_hints.values())
    singular = any(_singular(pre.text, p) for p, c in pre.column_hints.items()
                   if c in dim_cols and c not in {v for v, _ in pre.value_mentions})
    h = infer(pre.text, has_dim, bool(dates), singular)
    if h.order:
        frame.order = h.order
    if h.intent:
        frame.intent = h.intent
    frame.metric.agg = h.agg or frame.metric.agg
    # a limit must come from the question (a number or a singular superlative); the model's own guess is dropped
    frame.top_n = h.top_n or None
    if frame.intent == "trend" and dates and frame.time is None:
        frame.time = TimeSpec(column=dates[0].flat_name, grain=h.grain)
    if frame.time and h.grain:
        frame.time.grain = h.grain
    if frame.intent in ("distribution", "summary"):
        frame.dimension = None
    if frame.intent in ("comparison", "ranking", "proportion") and not frame.dimension:
        hinted = [c for c in pre.column_hints.values() if c in dim_cols and c not in {v for v, _ in pre.value_mentions}]
        frame.dimension = hinted[0] if hinted else None


def _ground_metric(frame: QueryFrame, pre: Preprocessed, reg: Registry) -> None:
    """If the question names exactly one metric or measure, that is the metric (the model may pick a neighbour)."""
    metric_like = set(reg.metric_names())
    named = {c for c in pre.column_hints.values() if c in metric_like}
    if len(named) == 1:
        frame.metric.column = next(iter(named))
    if reg.measure(frame.metric.column):
        frame.metric.agg = "SUM"   # a measure carries its own aggregate; keep the frame tidy


def _select_rules(text: str, reg: Registry, prev: QueryFrame | None = None) -> list[str]:
    """Names of the phrase-triggered business rules that apply (always-on rules need no entry)."""
    t = text.lower()
    names = {r.name for r in reg.active_rules() if any(p.lower() in t for p in r.phrases)}
    if prev:
        names |= {n for n in prev.rules if any(r.name == n for r in reg.active_rules())}
    return sorted(names)


def _apply_date_hint(frame: QueryFrame, pre: Preprocessed, reg: Registry) -> None:
    """Deterministic date resolution wins over whatever the model produced."""
    h = pre.date_hint
    dates = reg.tagged("date")
    if not (h and dates):
        return
    col = frame.time.column if frame.time else dates[0].flat_name
    grain = (frame.time.grain if frame.time else None) or h.grain
    frame.time = TimeSpec(column=col, grain=grain, start=h.start.isoformat(), end=h.end.isoformat())


def _carry_over(frame: QueryFrame, prev: QueryFrame, pre: Preprocessed, reg: Registry,
                resolved: dict[str, str]) -> QueryFrame:
    """A follow-up changes only what it names. The small model often returns a bare frame and forgets the
    previous one, so start from the previous frame and apply just the changes the words themselves carry."""
    base = prev.model_copy(deep=True)
    changed = False
    value_cols = {c for c, _ in pre.value_mentions}
    for col, val in pre.value_mentions:
        if val.lower() in resolved and resolved[val.lower()] != col:
            continue
        base.filters = [f for f in base.filters if f.column != col] + [Filter(column=col, op="=", value=val)]
        changed = True
    named = [c for c in pre.column_hints.values() if c not in value_cols]
    dims = [c for c in named if (col := reg.by_flat_name(c)) and col.tag == "dimension"]
    if dims and dims[0] != base.dimension:
        base.dimension = dims[0]
        if base.intent in ("summary", "distribution"):
            base.intent = "comparison"
        changed = True
    mets = [c for c in named if (col := reg.by_flat_name(c)) and col.tag == "metric"]
    if mets:
        base.metric = frame.metric
        changed = True
    if pre.date_hint:
        changed = True
    return base if changed else frame


FOLLOWUP_STARTS = ("now", "also", "and", "only", "same", "instead", "split", "break", "what about", "how about", "but")


def is_followup(question: str, session: Session, reg: Registry | None = None) -> bool:
    if session.last_frame is None:
        return False
    q = question.lower().strip()
    if q.startswith(FOLLOWUP_STARTS):
        return True
    if len(q.split()) > 3:
        return False
    # a short message that names a metric ("profit by region") is a new question, not a tweak
    metrics = {c.flat_name for c in reg.tagged("metric")} if reg else set()
    return not (metrics & set(_hints(q, reg).values()))


def _apply_overrides(frame: QueryFrame, overrides: dict[str, str]) -> None:
    """Apply a column the user picked from a clarification."""
    if "metric" in overrides:
        frame.metric.column = overrides["metric"]
    if "dimension" in overrides:
        frame.dimension = overrides["dimension"]
        if frame.intent == "summary":
            frame.intent = "comparison"          # asked to group by something: it is no longer a single total
    if "time" in overrides and frame.time:
        frame.time.column = overrides["time"]
    frame.ambiguous = []


def ask(
    question: str, reg: Registry, con: duckdb.DuckDBPyConnection, slm: FrameFiller,
    session: Session | None = None, prefs: dict | None = None, followup: bool = False,
    overrides: dict[str, str] | None = None, term_index=None,
) -> Result:
    session = session or Session()
    res = Result(question=question)
    t0 = time.perf_counter()
    try:
        pre = preprocess(question, reg, data_today(con, reg), term_index)
    except ValueError as e:
        res.error = str(e)
        return res
    res.corrections = pre.corrections
    res.semantic = pre.semantic
    res.timings_ms["preprocess"] = (time.perf_counter() - t0) * 1000

    if not overrides and not looks_like_data_question(pre, reg):
        res.error = _not_a_data_question(reg)
        return res

    # a term that could mean several columns -> ask, don't guess
    if pre.ambiguous_terms and not overrides:
        phrase, cols = next(iter(pre.ambiguous_terms.items()))
        res.clarification = Clarification(
            f'"{phrase}" could mean more than one column. Which one?', "metric", cols, question)
        session.pending = res.clarification
        return res

    unknown = None if overrides else unknown_group_term(pre, reg)
    if unknown:
        dims = [c.flat_name for c in reg.tagged("dimension")]
        res.clarification = Clarification(f'I don\'t know what "{unknown}" refers to in this data. What should I group by?',
                                          "dimension", dims, question)
        session.pending = res.clarification
        return res

    resolved_values, unresolved_values = _value_columns(pre, reg, (overrides or {}).get("filter"))
    if unresolved_values:
        val, cols = next(iter(unresolved_values.items()))
        names = ", ".join(c.replace("_", " ") for c in cols)
        res.clarification = Clarification(f'"{val}" appears in more than one column ({names}). Which one do you mean?',
                                          "filter", cols, question)
        session.pending = res.clarification
        return res

    t1 = time.perf_counter()
    try:
        frame, raw = slm.fill_frame(pre, reg, session.last_frame if followup else None)
    except TimeoutError as e:
        res.error = str(e)
        return res
    except Exception as e:  # model output failed validation / generation error
        res.error = f"Could not interpret the question: {e}"
        return res
    res.timings_ms["slm"] = (time.perf_counter() - t1) * 1000
    res.raw_frame = raw

    prev = session.last_frame if followup else None
    if prev:
        frame = _carry_over(frame, prev, pre, reg, resolved_values)
    _ground_filters(frame, pre.text, reg, prev)
    _ground_dimension(frame, pre, reg, prev)
    if not followup:
        _apply_rules(frame, pre, reg)
    _add_value_filters(frame, pre, resolved_values)
    _ground_metric(frame, pre, reg)
    frame.rules = _select_rules(pre.text, reg, prev)
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
