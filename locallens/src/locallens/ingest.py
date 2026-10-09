"""Load files into DuckDB and build the flat view the whole pipeline queries."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .registry import Column, Registry

FLAT = "flat"
MAX_VALUES = 200  # keep every distinct value of a dimension up to this many


def _read(path: str) -> pd.DataFrame:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(p)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(p)
    if suffix == ".parquet":
        return pd.read_parquet(p)
    raise ValueError(f"Unsupported file type: {suffix}")


def load_tables(con: duckdb.DuckDBPyConnection, tables: dict[str, str]) -> None:
    for name, path in tables.items():
        df = _read(path)  # noqa: F841  (referenced by DuckDB replacement scan)
        con.register("_tmp_df", df)
        con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT * FROM _tmp_df')
        con.unregister("_tmp_df")


def new_registry_from_files(name: str, tables: dict[str, str], main_table: str) -> Registry:
    """Untagged registry: every column present, tag = 'ignore' until the user tags it."""
    reg = Registry(name=name, main_table=main_table, tables=tables)
    for t, path in tables.items():
        df = _read(path)
        for col in df.columns:
            reg.columns.append(Column(table=t, name=str(col), flat_name=str(col)))
    return reg


def build_flat_view(con: duckdb.DuckDBPyConnection, reg: Registry) -> list[str]:
    """Create view `flat` = main table LEFT JOIN the declared tables.

    Columns of joined tables that collide with an existing name get a
    '<table>_' prefix. Join keys of joined tables are dropped (duplicates).
    Updates each Column.flat_name and returns the list of flat column names.
    """
    main = reg.main_table
    select: list[str] = []
    used: set[str] = set()

    def add(table: str, col: str, flat: str) -> None:
        select.append(f'"{table}"."{col}" AS "{flat}"')
        used.add(flat)

    main_cols = [c for c in reg.columns if c.table == main]
    for c in main_cols:
        add(main, c.name, c.name)
        c.flat_name = c.name

    joins_sql: list[str] = []
    for j in reg.joins:
        joins_sql.append(
            f'LEFT JOIN "{j.right}" ON "{j.left}"."{j.left_key}" = "{j.right}"."{j.right_key}"'
        )
        for c in (c for c in reg.columns if c.table == j.right):
            if c.name == j.right_key:
                c.flat_name = j.left_key if j.left == main else c.name
                continue
            flat = c.name if c.name not in used else f"{j.right}_{c.name}"
            add(j.right, c.name, flat)
            c.flat_name = flat

    sql = f'CREATE OR REPLACE VIEW {FLAT} AS SELECT {", ".join(select)} FROM "{main}" ' + " ".join(joins_sql)
    con.execute(sql)
    return [c for c in used]


def collect_samples(con: duckdb.DuckDBPyConnection, reg: Registry, limit: int = 12) -> None:
    """Fill sample values for dimensions so the prompt can show the model real values."""
    for c in reg.tagged("dimension"):
        rows = con.execute(
            f'SELECT DISTINCT CAST("{c.flat_name}" AS VARCHAR) FROM {FLAT} '
            f'WHERE "{c.flat_name}" IS NOT NULL LIMIT {limit}'
        ).fetchall()
        c.samples = [r[0] for r in rows]
        n = con.execute(f'SELECT count(DISTINCT "{c.flat_name}") FROM {FLAT}').fetchone()[0]
        if n <= MAX_VALUES:
            c.values = [r[0] for r in con.execute(
                f'SELECT DISTINCT CAST("{c.flat_name}" AS VARCHAR) FROM {FLAT} '
                f'WHERE "{c.flat_name}" IS NOT NULL').fetchall()]


def prepare(reg: Registry, con: duckdb.DuckDBPyConnection | None = None) -> duckdb.DuckDBPyConnection:
    con = con or duckdb.connect(":memory:")
    load_tables(con, reg.tables)
    build_flat_view(con, reg)
    collect_samples(con, reg)
    return con
