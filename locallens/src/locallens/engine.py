"""Run validated SQL on the local DuckDB connection."""
from __future__ import annotations

import duckdb
import pandas as pd


def run(con: duckdb.DuckDBPyConnection, sql: str) -> pd.DataFrame:
    return con.execute(sql).df()
