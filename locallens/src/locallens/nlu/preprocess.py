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

from ..data.registry import Registry

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
    semantic: list[tuple[str, str]] = field(default_factory=list)        # (word, column) matched by meaning, not spelling


def phrase_re(p: str) -> str:
    """Regex for a column phrase that also matches simple plurals (category -> categories)."""
    p = re.escape(p)
    p = rf"{p[:-1]}(?:y|ies)" if p.endswith("y") else rf"{p}(?:s|es|able|ability)?"
    return rf"\b{p}\b"


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return start, end


def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    k = year * 12 + (month - 1) + n
    return k // 12, k % 12 + 1


def _fy_start_year(d: date, start_month: int) -> int:
    """Calendar year in which the fiscal year containing d begins."""
    return d.year if d.month >= start_month else d.year - 1


def _fy_bounds(start_year: int, start_month: int) -> tuple[date, date]:
    s = date(start_year, start_month, 1)
    ey, em = _add_months(start_year, start_month, 11)
    return s, _month_bounds(ey, em)[1]


def _fq_bounds(start_year: int, q: int, start_month: int) -> tuple[date, date]:
    y, m = _add_months(start_year, start_month, 3 * (q - 1))
    ey, em = _add_months(y, m, 2)
    return date(y, m, 1), _month_bounds(ey, em)[1]


def _label_to_start_year(label: int, start_month: int) -> int:
    """FY labels use the year the fiscal year ENDS in (FY2025 = Apr 2024 - Mar 2025 when it starts in April)."""
    return label if start_month == 1 else label - 1


MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
          "sep": 9, "oct": 10, "nov": 11, "dec": 12}
MONTH_RE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)\b(?:\s+(?:of\s+)?((?:19|20)\d{2}))?", re.I)


def _month_mention(t: str, today: date) -> DateHint | None:
    """'December 2025', 'dec 2025', 'in November' (the latest such month on or before today)."""
    for m in MONTH_RE.finditer(t):
        word, year = m[1].lower(), m[2]
        if word == "may" and not year and not re.search(r"\b(?:in|for|during|of|since)\s+may\b", t):
            continue                      # the verb, not the month
        if len(word) <= 4 and word not in ("june", "july", "may") and not year and word[:3] != "sep":
            continue                      # bare abbreviation without a year is too ambiguous ("mar", "dec")
        mo = MONTHS[word[:3]]
        y = int(year) if year else (today.year if mo <= today.month else today.year - 1)
        s, e = _month_bounds(y, mo)
        return DateHint(s, e, m[0], "day")
    return None


def resolve_dates(text: str, today: date, fiscal_start: int = 1) -> DateHint | None:
    t = text.lower()
    fy_now = _fy_start_year(today, fiscal_start)
    q_now = ((today.month - fiscal_start) % 12) // 3 + 1
    m = re.search(r"\bq([1-4])\s*(?:of\s*)?(?:fy\s*)?((?:19|20)\d{2})\b", t)
    if m:
        s, e = _fq_bounds(_label_to_start_year(int(m[2]), fiscal_start), int(m[1]), fiscal_start)
        return DateHint(s, e, m[0], "month")
    m = re.search(r"\bfy\s*((?:19|20)?\d{2})\b", t)
    if m:
        label = int(m[1]) + (2000 if len(m[1]) == 2 else 0)
        s, e = _fy_bounds(_label_to_start_year(label, fiscal_start), fiscal_start)
        return DateHint(s, e, m[0], "month")
    if "last quarter" in t or "previous quarter" in t:
        y, qq = (fy_now - 1, 4) if q_now == 1 else (fy_now, q_now - 1)
        s, e = _fq_bounds(y, qq, fiscal_start)
        return DateHint(s, e, "last quarter", "month")
    if "this quarter" in t:
        s, e = _fq_bounds(fy_now, q_now, fiscal_start)
        return DateHint(s, min(e, today), "this quarter", "month")
    if "last month" in t or "previous month" in t:
        y, mo = (today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1)
        s, e = _month_bounds(y, mo)
        return DateHint(s, e, "last month", "day")
    if "this month" in t:
        s, e = _month_bounds(today.year, today.month)
        return DateHint(s, min(e, today), "this month", "day")
    if "last year" in t or "previous year" in t:
        s, e = _fy_bounds(fy_now - 1, fiscal_start)
        return DateHint(s, e, "last year", "month")
    if "this year" in t:
        s, _ = _fy_bounds(fy_now, fiscal_start)
        return DateHint(s, today, "this year", "month")
    m = re.search(r"\blast\s+(\d+)\s+(day|week|month|year)s?\b", t)
    if m:
        n, unit = int(m[1]), m[2]
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        return DateHint(today - timedelta(days=days), today, m[0], "day" if unit in ("day", "week") else "month")
    hit = _month_mention(t, today)
    if hit:
        return hit
    m = re.search(r"\b((?:19|20)\d{2})\b", t)
    if m:
        y = int(m[1])
        return DateHint(date(y, 1, 1), date(y, 12, 31), m[0], "month")
    return None


def _phrase_cols(reg: Registry) -> dict[str, set[str]]:
    phrase_cols: dict[str, set[str]] = {}
    for e in reg.entities():
        for p in [e.flat_name.replace("_", " "), *e.synonyms]:
            if p.strip():
                phrase_cols.setdefault(p.lower().strip(), set()).add(e.flat_name)
    return phrase_cols


def _ambiguous(text: str, reg: Registry) -> dict[str, list[str]]:
    t = text.lower()
    return {
        p: sorted(cols)
        for p, cols in _phrase_cols(reg).items()
        if len(cols) > 1 and re.search(phrase_re(p), t)
    }


def _hints(text: str, reg: Registry) -> dict[str, str]:
    """Phrases in the question that map to exactly one column. Longest phrase wins, so
    'customer region' is not also read as 'region'."""
    phrase_cols = _phrase_cols(reg)
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
            if len(v) >= 3 and re.search(rf"\b{re.escape(v.lower())}(?:s|es)?\b", t):
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
    for m in reg.active_measures():
        for p in [m.name.replace("_", " "), m.label, *m.synonyms]:
            words.update(re.findall(r"[a-z]+", p.lower()))
    return words


def _is_plural_of(word: str, known: set[str]) -> bool:
    return (word.endswith("ies") and word[:-3] + "y" in known) or \
           (word.endswith("es") and word[:-2] in known) or (word.endswith("s") and word[:-1] in known)


def normalise_spelling(text: str, reg: Registry) -> tuple[str, list[tuple[str, str]]]:
    known = _known_words(reg)
    out, fixes = [], []
    for tok in re.findall(r"\s+|[^\s]+", text):
        m = re.fullmatch(r"([A-Za-z]{5,})([^A-Za-z]*)", tok)
        if m and m[1].lower() not in known and m[1].lower() not in STOP and m[1].lower() not in KEYWORDS \
                and not _is_plural_of(m[1].lower(), known):
            hit = process.extractOne(m[1].lower(), known | KEYWORDS, scorer=fuzz.ratio, score_cutoff=84)
            if hit:
                out.append(hit[0] + m[2])
                fixes.append((m[1], hit[0]))
                continue
        out.append(tok)
    return "".join(out), fixes


def preprocess(question: str, reg: Registry, today: date, term_index=None) -> Preprocessed:
    text = " ".join(question.strip().split())
    text = re.sub(r"(?<=[A-Za-z])-(?=[A-Za-z])", " ", text)   # "sub-category" -> "sub category" (dates keep their dashes)
    if not text:
        raise ValueError("Empty question.")
    text, fixes = normalise_spelling(text, reg)
    pre = Preprocessed(text, resolve_dates(text, today, reg.fiscal_start_month), fixes, _ambiguous(text, reg), _hints(text, reg),
                       _value_mentions(text, reg))
    if term_index is not None:
        _add_semantic_hints(pre, reg, term_index)
    return pre


def _add_semantic_hints(pre: Preprocessed, reg: Registry, index) -> None:
    """Words that matched nothing by spelling are compared by meaning (nlu/embeddings.py)."""
    from .embeddings import semantic_matches

    covered = {w for p in pre.column_hints for w in re.findall(r"[a-z]+", p)}
    covered |= {w for _, v in pre.value_mentions for w in re.findall(r"[a-z]+", v.lower())}
    covered |= {w for p in pre.ambiguous_terms for w in re.findall(r"[a-z]+", p)}
    if pre.date_hint:
        covered |= set(re.findall(r"[a-z]+", pre.date_hint.phrase.lower()))
    skip = STOP | KEYWORDS | {w for r in reg.active_rules() for p in r.phrases for w in re.findall(r"[a-z]+", p.lower())}
    for m in semantic_matches(pre.text, covered, index, skip):
        if m.entity not in pre.column_hints.values():     # never second-guess a direct match
            pre.column_hints[m.word] = m.entity
            pre.semantic.append((m.word, m.entity))


GROUP_WORD = re.compile(r"\b(?:by|per|for each|each|across|every)\s+(?:the\s+|a\s+|an\s+)?([a-z]{3,})\b")
TIME_WORDS = {"day", "days", "week", "weeks", "month", "months", "quarter", "quarters", "year", "years", "date", "dates", "time",
              "hour", "hours", "period", "periods", "cent", "percent", "one", "all", "any", "the", "and", "for", "that", "this", "its"}


def unknown_group_term(pre: Preprocessed, reg: Registry) -> str | None:
    """"units sold by town": a word after by/per/each that nothing in the dataset explains. Better to ask than to guess."""
    known = _known_words(reg)
    covered = {w for p in pre.column_hints for w in re.findall(r"[a-z]+", p)}
    covered |= {w for _, v in pre.value_mentions for w in re.findall(r"[a-z]+", v.lower())}
    covered |= {w for p in pre.ambiguous_terms for w in re.findall(r"[a-z]+", p)}
    for m in GROUP_WORD.finditer(pre.text.lower()):
        w = m[1]
        stems = {w, w.rstrip("s"), w[:-3] + "y" if w.endswith("ies") else w, w[:-2] if w.endswith("es") else w}
        if stems & (known | covered | TIME_WORDS | STOP | KEYWORDS):
            continue
        return w
    return None
