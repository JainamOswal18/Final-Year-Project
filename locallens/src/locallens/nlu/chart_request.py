"""Chart words in a question ("make it a pie chart", "sales by region as a bar"): which chart did the user ask for?

Plain pattern matching, no model. The word "line" alone is not enough ("product line" is a column), so a line chart
needs "line chart", "line graph", "line plot", "as a line" or "in a line"."""
from __future__ import annotations

import re

# first match wins: "horizontal bar" must be tried before "bar"
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("hbar", re.compile(r"\bhorizontal\s+bars?\b|\bbars?\s+(?:chart|graph|plot)\s+horizontal(?:ly)?\b|\bhorizontal(?:ly)?\b.*\bbars?\b", re.I)),
    ("donut", re.compile(r"\b(?:pie|donut|doughnut)s?\b", re.I)),
    ("histogram", re.compile(r"\bhistograms?\b", re.I)),
    ("line", re.compile(r"\bline\s+(?:chart|graph|plot)s?\b|\b(?:as|in|into|a)\s+(?:an?\s+)?line\b", re.I)),
    ("bar", re.compile(r"\bbars?\b|\bbar\s+(?:chart|graph|plot)s?\b|\bcolumn\s+(?:chart|graph)s?\b", re.I)),
]

CHART_NAMES = {"donut": "pie chart", "bar": "bar chart", "hbar": "horizontal bar chart",
               "histogram": "histogram", "line": "line chart"}

# the part of the sentence that names the chart, removed before the language model sees the question
_KIND = r"(?:horizontal\s+)?(?:pie|donut|doughnut|bar|line|column)s?"
_PHRASE = re.compile(
    rf"\b(?:as|in|into|using|with)\s+(?:an?\s+)?{_KIND}(?:\s+(?:chart|graph|plot))?\b"    # "as a pie", "in a bar chart"
    rf"|\b(?:an?\s+)?{_KIND}\s+(?:chart|graph|plot)\b", re.I)                          # "pie chart of"


def detect_chart(text: str) -> str | None:
    for chart, pattern in _PATTERNS:
        if pattern.search(text):
            return chart
    return None


def strip_chart_words(text: str) -> str:
    """'sales by region as a pie chart' -> 'sales by region'. Histogram stays: it also says what to compute."""
    out = _PHRASE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", out).strip(" ,.")
