"""Rule-assisted intent/grain/aggregation (patent: 'rule-assisted classification logic').

Keyword rules are right when they fire; the 0.5B model is the fallback for everything
else. Where a rule fires it overrides the model, which makes the common phrasings
deterministic and leaves the model to handle the long tail.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class RuleHints:
    intent: str | None = None
    grain: str | None = None
    top_n: int | None = None
    agg: str | None = None
    agg_is_default: bool = False   # no aggregation word in the question: the user's saved default was used
    order: str | None = None   # "asc" for lowest/bottom/worst questions


NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
ASC = re.compile(r"\b(?:lowest|bottom|worst|least|fewest|smallest|cheapest)\b", re.I)
SUPERLATIVE = re.compile(r"\b(?:highest|lowest|best|worst|biggest|smallest|largest|most|least)\b", re.I)
GRAIN_WORD = {"day": "day", "week": "week", "month": "month", "quarter": "quarter", "year": "year"}
GRAIN_PHRASE = re.compile(r"\b(?:per|each|every|by|a)\s+(day|week|month|quarter|year)\b", re.I)
GRAIN_OVER = re.compile(r"\b(year|month|week|quarter)\s*(?:over|on|by)\s*\1\b|\b(yoy|mom|wow|qoq)\b", re.I)
TREND = re.compile(r"\b(?:over time|trend|growth|growing|grow|grew|change over|changed over|moved|evolv\w*|"
                   r"progress\w*|develop\w*|curve|trajectory|history|over the (?:last )?(?:years|months|weeks|quarters)|by month|by year)\b", re.I)


GRAINS = [("daily", "day"), ("weekly", "week"), ("monthly", "month"), ("quarterly", "quarter"),
          ("yearly", "year"), ("annual", "year"), ("per month", "month"), ("per year", "year"),
          ("each month", "month"), ("by month", "month"), ("by quarter", "quarter"), ("by year", "year")]


def infer(text: str, has_dimension_phrase: bool, has_date_column: bool, dimension_is_singular: bool = False,
          default_agg: str = "SUM") -> RuleHints:
    t = text.lower()
    h = RuleHints()

    for kw, g in GRAINS:
        if re.search(rf"\b{kw}\b", t) or re.search(rf"\b{kw[:-2]}ly\b", t):
            h.grain = g
            break
    if h.grain is None:
        m = GRAIN_PHRASE.search(t)
        if m:
            h.grain = GRAIN_WORD[m[1].lower()]
        else:
            m = GRAIN_OVER.search(t)
            if m:
                h.grain = {"yoy": "year", "mom": "month", "wow": "week", "qoq": "quarter"}.get((m[2] or "").lower()) or m[1].lower()

    t = re.sub(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", lambda m: str(NUMBER_WORDS[m[1]]), t)
    m = re.search(r"\b(?:top|bottom|best|worst|first)\s+(\d+)\b", t) or re.search(
        r"\b(\d+)\s+(?:most|best|worst|least|highest|lowest|biggest|largest|smallest|top|bottom)\b", t)
    if m:
        h.top_n = int(m[1])
    elif re.search(r"\b(?:which|what)\b.*\b(?:highest|lowest|most|least|best|worst)\b", t):
        h.top_n = 1
    elif dimension_is_singular and SUPERLATIVE.search(t):
        h.top_n = 1          # "highest revenue store" asks for one store
    if ASC.search(t):
        h.order = "asc"

    if re.search(r"\b(?:average|avg|mean)\b", t):
        h.agg = "AVG"
    elif re.search(r"\b(?:maximum|max)\b", t):
        h.agg = "MAX"
    elif re.search(r"\b(?:minimum|min)\b", t):
        h.agg = "MIN"
    elif re.search(r"\b(?:number of|count of)\b", t):
        h.agg = "COUNT"
    elif re.search(r"\b(?:total|sum|overall|altogether)\b", t):
        h.agg = "SUM"
    else:
        h.agg, h.agg_is_default = default_agg, True

    # priority order matters: first matching rule wins
    if re.search(r"\b(?:distribution|distributed|distribute|spread|histogram)\b", t):
        h.intent = "distribution"
    elif re.search(r"\b(?:share|proportion|percent|percentage)\b", t):
        h.intent = "proportion"
    elif h.top_n or re.search(r"\b(?:top|bottom|rank|ranking|ranked|highest|lowest|best|worst)\b", t):
        h.intent = "ranking"
    elif has_date_column and (h.grain or TREND.search(t) or GRAIN_OVER.search(t)):
        h.intent = "trend"
    elif re.search(r"\b(?:compare|comparison|versus|vs|across)\b", t) or (
        has_dimension_phrase and re.search(r"\b(?:by|per|for each|each)\b", t)
    ):
        h.intent = "comparison"
    elif re.search(r"\b(?:total|overall|how many|how much|sum|average|what was|what is)\b", t) or not has_dimension_phrase:
        h.intent = "summary"
    else:
        h.intent = "comparison"      # a dimension is named and nothing else decides: break the metric down by it
    return h
