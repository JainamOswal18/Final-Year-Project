"""Retail words people use for the same thing ("outlet" = store, "town" = city, "pieces" = quantity).

A word in the question that the dataset does not know, but that sits in a group here with a word the
dataset does know, points at that column. Deterministic, and it works for any uploaded retail dataset,
because the match is made against the dataset's own column names and synonyms.
"""
from __future__ import annotations

import re

from ..data.registry import Registry

GROUPS: list[set[str]] = [
    {"city", "town", "district"},
    {"store", "outlet", "shop", "branch", "showroom", "kirana", "kirana store"},
    {"quantity", "units", "unit", "qty", "pieces", "piece", "pcs", "items sold", "volume sold", "unit sales"},
    {"region", "zone", "territory", "circle"},
    {"state", "province"},
    {"customer", "client", "buyer", "shopper", "consumer"},
    {"product", "item", "sku", "article"},
    {"category", "department", "vertical", "product line"},
    {"sub category", "subcategory"},
    {"brand", "manufacturer"},
    {"sales", "revenue", "turnover", "gmv", "takings", "sales value", "gross sales"},
    {"profit", "earnings", "net profit"},
    {"discount", "markdown", "rebate"},
    {"price", "mrp", "selling price", "unit price"},
    {"footfall", "visitors", "walk ins", "walkins"},
    {"orders", "order count", "number of orders", "bills", "invoices", "transactions", "receipts"},
    {"average order value", "aov", "basket value", "basket size", "average bill", "average ticket"},
    {"supplier", "vendor", "distributor"},
    {"channel", "sales channel"},
    {"payment method", "payment mode", "payment type"},
]


def _term_re(term: str) -> str:
    t = re.escape(term)
    return rf"\b{t}(?:s|es)?\b"


def glossary_hints(text: str, reg: Registry, covered: set[str]) -> list[tuple[str, str]]:
    """(term, column) for retail words in `text` that point at exactly one column of this dataset.
    Words in `covered` were already explained by a direct match and are left alone."""
    t = text.lower()
    phrases = {e.flat_name: set(reg.phrases(e.flat_name)) for e in reg.entities()}
    out: list[tuple[str, str]] = []
    used: set[str] = set(covered)
    for group in GROUPS:
        for term in sorted(group, key=len, reverse=True):
            words = set(term.split())
            if words & used or not re.search(_term_re(term), t):
                continue
            cols = [c for c, ps in phrases.items() if ps & group]
            if len(cols) == 1:
                out.append((term, cols[0]))
                used |= words
            break                       # one hint per group; a second term from the same group adds nothing
    return out
