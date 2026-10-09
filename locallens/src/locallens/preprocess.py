"""Deterministic pre-processing before the model sees the question (patent: syntactic
validation + spelling normalization + semantic disambiguation).

Dates are resolved here, not by the model: small models are unreliable at date maths.
"today" is the latest date in the data, so relative phrases always hit real rows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from rapidfuzz import fuzz, process

from .registry import Registry

STOP = {
    "show", "what", "which", "total", "average", "compare", "versus", "month", "monthly", "year",
    "yearly", "week", "weekly", "quarter", "daily", "last", "this", "over", "time", "each", "split",
    "group", "sorted", "least", "most", "best", "worst", "share", "number", "count", "trend",
    "distribution", "proportion", "ranking", "summary", "top", "bottom", "highest", "lowest",
}


@dataclass
class DateHint:
    start: date
    end: date
    phrase: str
    grain: str | None = None


@dataclass
class Preprocessed:
    text: str
    date_hint: DateHint | None = None
    corrections: list[tuple[str, str]] = field(default_factory=list)
    ambiguous_terms: dict[str, list[str]] = field(default_factory=dict)  # phrase -> candidate columns
    column_hints: dict[str, str] = field(default_factory=dict)           # unambiguous phrase -> column
    value_mentions: list[tuple[str, str]] = field(default_factory=list)  # (column, value) found in the text


def phrase_re(p: str) -> str:
    """Regex for a column phrase that also matches simple plurals (category -> categories)."""
    p = re.escape(p)
    p = rf"{p[:-1]}(?:y|ies)" if p.endswith("y") else rf"{p}(?:s|es)?"
    return rf"\b{p}\b"


def _quarter_bounds(year: int, q: int) -> tuple[date, date]:
    start = date(year, 3 * (q - 1) + 1, 1)
    end = date(year + (q == 4), (3 * q) % 12 + 1, 1) - timedelta(days=1)
    return start, end


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return start, end


def resolve_dates(text: str, today: date) -> DateHint | None:
    t = text.lower()
    m = re.search(r"\bq([1-4])\s*(?:of\s*)?((?:19|20)\d{2})\b", t)
    if m:
        s, e = _quarter_bounds(int(m[2]), int(m[1]))
        return DateHint(s, e, m[0], "month")
    q = (today.month - 1) // 3 + 1
    if "last quarter" in t or "previous quarter" in t:
        y, qq = (today.year - 1, 4) if q == 1 else (today.year, q - 1)
        s, e = _quarter_bounds(y, qq)
        return DateHint(s, e, "last quarter", "month")
    if "this quarter" in t:
        s, e = _quarter_bounds(today.year, q)
        return DateHint(s, min(e, today), "this quarter", "month")
    if "last month" in t or "previous month" in t:
        y, mo = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        s, e = _month_bounds(y, mo)
        return DateHint(s, e, "last month", "day")
    if "this month" in t:
        s, e = _month_bounds(today.year, today.month)
        return DateHint(s, min(e, today), "this month", "day")
    if "last year" in t or "previous year" in t:
        return DateHint(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "last year", "month")
    if "this year" in t:
        return DateHint(date(today.year, 1, 1), today, "this year", "month")
    m = re.search(r"\blast\s+(\d+)\s+(day|week|month|year)s?\b", t)
    if m:
        n, unit = int(m[1]), m[2]
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        return DateHint(today - timedelta(days=days), today, m[0], "day" if unit in ("day", "week") else "month")
    m = re.search(r"\b((?:19|20)\d{2})\b", t)
    if m:
        y = int(m[1])
        return DateHint(date(y, 1, 1), date(y, 12, 31), m[0], "month")
    return None


def _ambiguous(text: str, reg: Registry) -> dict[str, list[str]]:
    phrase_cols: dict[str, set[str]] = {}
    for c in reg.columns:
        if c.tag == "ignore" or not c.flat_name:
            continue
        for p in [c.flat_name.replace("_", " "), *c.synonyms]:
            phrase_cols.setdefault(p.lower().strip(), set()).add(c.flat_name)
    t = text.lower()
    return {
        p: sorted(cols)
        for p, cols in phrase_cols.items()
        if len(cols) > 1 and re.search(phrase_re(p), t)
    }


def _hints(text: str, reg: Registry) -> dict[str, str]:
    """Phrases in the question that map to exactly one column. Longest phrase wins, so
    'customer region' is not also read as 'region'."""
    phrase_cols: dict[str, set[str]] = {}
    for c in reg.columns:
        if c.tag == "ignore" or not c.flat_name:
            continue
        for p in [c.flat_name.replace("_", " "), *c.synonyms]:
            phrase_cols.setdefault(p.lower().strip(), set()).add(c.flat_name)
    t = text.lower()
    found: dict[str, str] = {}
    for p in sorted(phrase_cols, key=len, reverse=True):
        cols = phrase_cols[p]
        if len(cols) == 1 and re.search(phrase_re(p), t) and not any(p in f for f in found):
            found[p] = next(iter(cols))
    return found


def _value_mentions(text: str, reg: Registry) -> list[tuple[str, str]]:
    t = text.lower()
    out = []
    for c in reg.tagged("dimension"):
        # longest value first so 'Home Office' wins over a hypothetical 'Home'
        for v in sorted(c.values, key=len, reverse=True):
            if len(v) >= 3 and re.search(rf"\b{re.escape(v.lower())}\b", t):
                out.append((c.flat_name, v))
                break
    return out


KEYWORDS = {"monthly", "weekly", "daily", "quarterly", "yearly", "annual", "distribution", "compare",
            "comparison", "average", "maximum", "minimum", "percentage", "proportion", "histogram",
            "highest", "lowest", "versus", "total", "overall", "ranking", "trend", "growth"}


def _known_words(reg: Registry) -> set[str]:
    words: set[str] = set()
    for c in reg.columns:
        if c.tag == "ignore":
            continue
        for p in [c.flat_name.replace("_", " "), *c.synonyms, *c.samples]:
            words.update(re.findall(r"[a-z]+", p.lower()))
    return words


def normalise_spelling(text: str, reg: Registry) -> tuple[str, list[tuple[str, str]]]:
    known = _known_words(reg)
    out, fixes = [], []
    for tok in re.findall(r"\s+|[^\s]+", text):
        m = re.fullmatch(r"([A-Za-z]{5,})([^A-Za-z]*)", tok)
        if m and m[1].lower() not in known and m[1].lower() not in STOP and m[1].lower() not in KEYWORDS:
            hit = process.extractOne(m[1].lower(), known | KEYWORDS, scorer=fuzz.ratio, score_cutoff=84)
            if hit:
                out.append(hit[0] + m[2])
                fixes.append((m[1], hit[0]))
                continue
        out.append(tok)
    return "".join(out), fixes


def preprocess(question: str, reg: Registry, today: date) -> Preprocessed:
    text = " ".join(question.strip().split())
    if not text:
        raise ValueError("Empty question.")
    text, fixes = normalise_spelling(text, reg)
    return Preprocessed(text, resolve_dates(text, today), fixes, _ambiguous(text, reg), _hints(text, reg),
                        _value_mentions(text, reg))
