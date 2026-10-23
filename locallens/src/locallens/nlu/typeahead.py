"""Typeahead for the question box: finish the last word or two a person is typing from the dataset's own vocabulary
(column names, synonyms, metric names, and the values found in category columns). No model involved."""
from __future__ import annotations

import re

from ..data.registry import Registry

MAX_ITEMS = 8
MAX_TAIL_WORDS = 3
MIN_CHARS = 2


def complete(text: str, reg: Registry) -> list[dict]:
    """Each item: {"replace": the words at the end of `text` it replaces, "with": the full phrase, "kind": ...}.
    The caller swaps the tail for `with`. Matches are prefixes of a phrase; the phrase must be longer than what is typed."""
    if not text or text[-1].isspace():
        return []
    words = re.findall(r"[\w'-]+", text)
    if not words or len(words[-1]) < MIN_CHARS:
        return []
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for e in reg.entities():
        kind = "metric" if e.tag in ("metric", "measure") else "date" if e.tag == "date" else "category"
        for p in [e.flat_name.replace("_", " "), *e.synonyms]:
            p = p.strip()
            if p and p.lower() not in seen:
                seen.add(p.lower())
                candidates.append((p, kind))
    for c in reg.tagged("dimension"):
        for v in c.values:
            v = str(v).strip()
            if len(v) >= 3 and v.lower() not in seen:
                seen.add(v.lower())
                candidates.append((v, "value"))

    out: list[dict] = []
    done: set[str] = set()
    for n in range(min(MAX_TAIL_WORDS, len(words)), 0, -1):          # the longest tail first
        tail = " ".join(words[-n:])
        if not text.rstrip().lower().endswith(tail.lower()):
            continue
        for phrase, kind in candidates:
            if phrase.lower() in done:
                continue
            if phrase.lower().startswith(tail.lower()) and len(phrase) > len(tail):
                done.add(phrase.lower())
                out.append({"replace": tail, "with": phrase, "kind": kind})
        if out:
            break
    order = {"metric": 0, "category": 1, "date": 2, "value": 3}
    out.sort(key=lambda i: (order.get(i["kind"], 4), len(i["with"])))
    return out[:MAX_ITEMS]
