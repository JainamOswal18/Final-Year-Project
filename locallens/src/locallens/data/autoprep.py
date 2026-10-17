"""Turn uploaded files into clean tables and a first-guess registry (tags and joins).

The guesses are only a starting point: the user reviews and corrects them on the Columns page.
"""
from __future__ import annotations

import re
import sqlite3
import warnings
from pathlib import Path

import pandas as pd
from pandas.api.types import (is_bool_dtype, is_datetime64_any_dtype, is_integer_dtype, is_numeric_dtype,
                              is_object_dtype, is_string_dtype)

from .registry import Column, Join, Registry

SUPPORTED = {".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".sqlite", ".sqlite3", ".db"}
MAX_TABLES = 40
MAX_COLUMNS = 400
METRIC_WORDS = re.compile(r"(qty|quantity|units|count|amount|amt|price|sales|revenue|profit|cost|total|value|sum|spend|margin|discount|tax)", re.I)
ID_NAME = re.compile(r"(^id$|_id$|^id_|\bkey$|_key$|_code$|^code$|^uuid$|guid)", re.I)
DATE_LIKE = re.compile(r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})([ T]\d{1,2}:\d{2}(:\d{2})?)?\s*$")


class UploadError(ValueError):
    pass


def snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower()
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    if not s:
        s = "column"
    return ("c_" + s) if s[0].isdigit() else s


def unique_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        k = snake(n)
        seen[k] = seen.get(k, 0) + 1
        out.append(k if seen[k] == 1 else f"{k}_{seen[k]}")
    return out


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(axis=1, how="all").copy()
    df.columns = unique_names([str(c) for c in df.columns])
    for c in df.columns:
        s = df[c]
        if is_object_dtype(s) or is_string_dtype(s):
            s = s.astype(object).map(lambda v: v.strip() if isinstance(v, str) else v)
            s = s.where(s != "", None)
            sample = s.dropna().astype(str).head(200)
            if len(sample) >= 3 and sample.map(lambda v: bool(DATE_LIKE.match(v))).mean() >= 0.95:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    parsed = pd.to_datetime(s, errors="coerce", dayfirst=False)
                if parsed.notna().sum() >= 0.95 * s.notna().sum():
                    s = parsed
            elif len(sample) >= 3:
                num = pd.to_numeric(s, errors="coerce")
                if num.notna().sum() >= 0.98 * s.notna().sum():
                    s = num
        df[c] = s
    return df


def read_upload(path: Path, filename: str) -> dict[str, pd.DataFrame]:
    """One file -> {table name: DataFrame}. Excel gives one table per sheet, SQLite one per table."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED:
        raise UploadError(f"{filename}: unsupported file type {ext or '(none)'}. Use CSV, Excel, Parquet or SQLite.")
    stem = snake(Path(filename).stem)
    try:
        if ext == ".csv":
            return {stem: pd.read_csv(path)}
        if ext == ".tsv":
            return {stem: pd.read_csv(path, sep="\t")}
        if ext in (".xlsx", ".xls"):
            sheets = pd.read_excel(path, sheet_name=None)
            return {(stem if len(sheets) == 1 else f"{stem}_{snake(k)}"): v for k, v in sheets.items()}
        if ext == ".parquet":
            return {stem: pd.read_parquet(path)}
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]
            if not names:
                raise UploadError(f"{filename}: the SQLite file has no tables.")
            return {snake(n): pd.read_sql_query(f'SELECT * FROM "{n}"', con) for n in names[:MAX_TABLES]}
        finally:
            con.close()
    except UploadError:
        raise
    except Exception as e:  # unreadable or corrupt file
        raise UploadError(f"{filename}: could not read it ({str(e).splitlines()[0][:120]}).") from e


def unique_table_names(frames: list[tuple[str, pd.DataFrame]]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for name, df in frames:
        n, k = name, 2
        while n in out:
            n, k = f"{name}_{k}", k + 1
        out[n] = df
    return out


# ---- guesses ------------------------------------------------------------------------
def guess_tag(name: str, s: pd.Series, n_rows: int) -> str:
    n_unique = int(s.nunique(dropna=True))
    if is_datetime64_any_dtype(s):
        return "date"
    if is_bool_dtype(s):
        return "dimension"
    if is_numeric_dtype(s):
        if ID_NAME.search(name) or (is_integer_dtype(s) and n_rows > 20 and n_unique == s.notna().sum()):
            return "ignore"
        if METRIC_WORDS.search(name):
            return "metric"
        if is_integer_dtype(s) and 1 < n_unique <= 12:
            return "dimension"
        return "metric"
    if ID_NAME.search(name) and n_unique > 0.5 * max(n_rows, 1):
        return "ignore"
    if n_unique <= 500 and n_unique <= max(0.5 * n_rows, 12):
        return "dimension"
    return "ignore"


def suggest_joins(frames: dict[str, pd.DataFrame], main: str) -> list[Join]:
    """Join the main table to every other table on a shared column that is unique in the other table."""
    joins = []
    for name, df in frames.items():
        if name == main:
            continue
        for c in df.columns:
            if c in frames[main].columns and df[c].notna().all() and df[c].is_unique and ID_NAME.search(c):
                joins.append(Join(left=main, left_key=c, right=name, right_key=c))
                break
        else:                                   # sales.region_id -> regions.id
            if "id" in df.columns and df["id"].notna().all() and df["id"].is_unique:
                for c in frames[main].columns:
                    stem = c[:-3] if c.endswith("_id") else None
                    if stem and snake(name) in (stem, stem + "s", stem + "es", stem[:-1] + "ies" if stem.endswith("y") else stem):
                        joins.append(Join(left=main, left_key=c, right=name, right_key="id"))
                        break
    return joins


def pick_main(frames: dict[str, pd.DataFrame]) -> str:
    """The fact table is the one whose id columns repeat while being unique in other tables
    (orders.customer_id repeats; customers.customer_id does not). Ties go to the larger table."""
    def score(t: str) -> int:
        n = 0
        for u, other in frames.items():
            if u == t:
                continue
            n += any(c in other.columns and ID_NAME.search(c) and other[c].notna().all() and other[c].is_unique
                     and not frames[t][c].is_unique for c in frames[t].columns)
        return n
    return max(frames, key=lambda t: (score(t), len(frames[t])))


def build_registry(name: str, frames: dict[str, pd.DataFrame], paths: dict[str, str]) -> Registry:
    if not frames:
        raise UploadError("No tables found in the upload.")
    if sum(len(f.columns) for f in frames.values()) > MAX_COLUMNS:
        raise UploadError(f"Too many columns (limit {MAX_COLUMNS}).")
    main = pick_main(frames)
    reg = Registry(name=name, main_table=main, tables=paths)
    reg.joins = suggest_joins(frames, main)
    join_keys = {j.right_key for j in reg.joins} | {j.left_key for j in reg.joins}
    reachable = {main} | {j.right for j in reg.joins}
    for t, df in frames.items():
        for c in df.columns:
            tag = "ignore" if (c in join_keys or t not in reachable) else guess_tag(c, df[c], len(df))
            reg.columns.append(Column(table=t, name=c, flat_name=c, tag=tag))
    return reg
