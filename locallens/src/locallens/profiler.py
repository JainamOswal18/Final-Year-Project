"""Describe the shape of a query result so chart rules can reason about it."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype


@dataclass
class Profile:
    rows: int
    cols: int
    kinds: dict[str, str] = field(default_factory=dict)       # column -> temporal|numeric|categorical
    cardinality: dict[str, int] = field(default_factory=dict)  # categorical column -> distinct count
    time_col: str | None = None
    numeric_cols: list[str] = field(default_factory=list)
    category_cols: list[str] = field(default_factory=list)
    time_ordered: bool = False


def profile(df: pd.DataFrame) -> Profile:
    p = Profile(rows=len(df), cols=df.shape[1])
    for c in df.columns:
        s = df[c]
        if is_datetime64_any_dtype(s):
            p.kinds[c] = "temporal"
            p.time_col = p.time_col or c
        elif is_numeric_dtype(s):
            p.kinds[c] = "numeric"
            p.numeric_cols.append(c)
        else:
            p.kinds[c] = "categorical"
            p.category_cols.append(c)
            p.cardinality[c] = int(s.nunique())
    if p.time_col is not None:
        p.time_ordered = bool(df[p.time_col].is_monotonic_increasing)
    return p
