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


GRAINS = [("daily", "day"), ("weekly", "week"), ("monthly", "month"), ("quarterly", "quarter"),
          ("yearly", "year"), ("annual", "year"), ("per month", "month"), ("per year", "year"),
          ("each month", "month"), ("by month", "month"), ("by quarter", "quarter"), ("by year", "year")]


def infer(text: str, has_dimension_phrase: bool, has_date_column: bool) -> RuleHints:
    t = text.lower()
    h = RuleHints()

    for kw, g in GRAINS:
        if re.search(rf"\b{kw}\b", t) or re.search(rf"\b{kw[:-2]}ly\b", t):
            h.grain = g
            break

    m = re.search(r"\b(?:top|bottom|best|worst|first)\s+(\d+)\b", t)
    if m:
        h.top_n = int(m[1])
    elif re.search(r"\b(?:which|what)\b.*\b(?:highest|lowest|most|least|best|worst)\b", t):
        h.top_n = 1

    if re.search(r"\b(?:average|avg|mean)\b", t):
        h.agg = "AVG"
    elif re.search(r"\b(?:maximum|max)\b", t):
        h.agg = "MAX"
    elif re.search(r"\b(?:minimum|min)\b", t):
        h.agg = "MIN"
    elif re.search(r"\b(?:number of|count of)\b", t):
        h.agg = "COUNT"
    else:
        h.agg = "SUM"

    # priority order matters: first matching rule wins
    if re.search(r"\b(?:distribution|spread|histogram)\b", t):
        h.intent = "distribution"
    elif re.search(r"\b(?:share|proportion|percent|percentage)\b", t):
        h.intent = "proportion"
    elif h.top_n or re.search(r"\b(?:top|bottom|rank|ranking|ranked|highest|lowest|best|worst)\b", t):
        h.intent = "ranking"
    elif has_date_column and (h.grain or re.search(r"\b(?:over time|trend|growth|change over|by month|by year)\b", t)):
        h.intent = "trend"
    elif re.search(r"\b(?:compare|comparison|versus|vs|across)\b", t) or (
        has_dimension_phrase and re.search(r"\b(?:by|per|for each|each)\b", t)
    ):
        h.intent = "comparison"
    elif re.search(r"\b(?:total|overall|how many|how much|sum|average|what was|what is)\b", t) or not has_dimension_phrase:
        h.intent = "summary"
    return h
