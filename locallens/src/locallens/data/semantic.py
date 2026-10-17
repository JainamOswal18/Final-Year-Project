"""The semantic layer: user-defined measures, calculated columns and business rules.

Users write small SQL fragments. Nothing they write is trusted: every fragment is parsed and
must pass an allowlist (known columns, safe functions, no subqueries) before it is ever run.
The model never sees or writes these expressions; it only picks a measure or column by name.
"""
from __future__ import annotations

import duckdb
import sqlglot
from sqlglot import exp

from locallens.data.registry import CALC_TABLE, IDENT, Column, Registry

FLAT = "flat"
BASE = "_base"
SAMPLE_ROWS = 2000  # dry runs look at this many rows, never the whole table


class ExpressionError(ValueError):
    pass


AGGREGATES = (exp.Sum, exp.Avg, exp.Count, exp.Min, exp.Max)
_ALLOWED = (
    exp.Column, exp.Identifier, exp.Literal, exp.Null, exp.Boolean, exp.Paren, exp.Neg, exp.Not,
    exp.Add, exp.Sub, exp.Mul, exp.Div, exp.Mod, exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.And, exp.Or, exp.In, exp.Between, exp.Is, exp.Like, exp.ILike, exp.Case, exp.If,
    exp.Cast, exp.Coalesce, exp.Nullif, exp.Round, exp.Abs, exp.Lower, exp.Upper, exp.Length,
    exp.DateDiff, exp.Extract, exp.Distinct, exp.DataType, exp.Var, exp.Interval, exp.CurrentDate,
    exp.Floor, exp.Ceil, exp.Trim, exp.Concat, exp.Substring, exp.DateTrunc, exp.Greatest, exp.Least,
    *AGGREGATES,
)


def parse_expression(text: str) -> exp.Expression:
    text = (text or "").strip()
    if not text:
        raise ExpressionError("The expression is empty.")
    if ";" in text:
        raise ExpressionError("Only a single expression is allowed.")
    try:
        return sqlglot.parse_one(text, read="duckdb")
    except sqlglot.errors.SqlglotError as e:
        raise ExpressionError(f"Could not parse the expression: {str(e).splitlines()[0]}") from e


def check_expression(text: str, columns: set[str], *, aggregate: bool | None = None) -> exp.Expression:
    """Parse and vet one expression. aggregate=True requires an aggregate function, False forbids one."""
    tree = parse_expression(text)
    for node in tree.walk():
        if isinstance(node, (exp.Subquery, exp.Select, exp.Star, exp.Window)):
            raise ExpressionError("Subqueries, * and window functions are not allowed.")
        if isinstance(node, exp.Column):
            if node.table:
                raise ExpressionError(f"Use plain column names, not {node.sql()!r}.")
            if node.name not in columns:
                raise ExpressionError(f"Unknown column {node.name!r}.")
        elif not isinstance(node, _ALLOWED):
            raise ExpressionError(f"{type(node).__name__.upper()} is not allowed here ({node.sql()[:40]!r}).")
    has_agg = any(isinstance(n, AGGREGATES) for n in tree.walk())
    if aggregate is True and not has_agg:
        raise ExpressionError("A measure needs an aggregate such as SUM(...) or COUNT(...).")
    if aggregate is False and has_agg:
        raise ExpressionError("This expression cannot contain SUM, AVG, COUNT, MIN or MAX.")
    return tree


def _sample(con: duckdb.DuckDBPyConnection) -> str:
    return f"(SELECT * FROM {FLAT} LIMIT {SAMPLE_ROWS})"


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def apply_calculated_columns(con: duckdb.DuckDBPyConnection, reg: Registry) -> None:
    """(Re)create `flat` as the base view plus each calculated column. A bad column is switched
    off with an error message instead of breaking the whole dataset."""
    base_cols = {c.flat_name for c in reg.columns if c.table != CALC_TABLE and c.flat_name}
    good: list[Column] = []
    names = set(base_cols)
    for c in (c for c in reg.columns if c.table == CALC_TABLE):
        c.flat_name, c.error = c.name, ""
        try:
            if not IDENT.match(c.name):
                raise ExpressionError(f"{c.name!r} is not a valid name (letters, digits, underscore).")
            if c.name in names:
                raise ExpressionError(f"{c.name!r} is already a column name.")
            check_expression(c.expression, names, aggregate=False)
            select = ", ".join(f"({g.expression}) AS {_q(g.name)}" for g in [*good, c])
            con.execute(f"CREATE OR REPLACE VIEW {FLAT} AS SELECT *, {select} FROM {BASE}")
            con.execute(f"SELECT * FROM {_sample(con)} LIMIT 1").fetchall()
        except (ExpressionError, duckdb.Error) as e:
            c.error = str(e).splitlines()[0]
            select = ", ".join(f"({g.expression}) AS {_q(g.name)}" for g in good)
            con.execute(f"CREATE OR REPLACE VIEW {FLAT} AS SELECT *{', ' + select if select else ''} FROM {BASE}")
            continue
        good.append(c)
        names.add(c.name)


def validate_semantic(con: duckdb.DuckDBPyConnection, reg: Registry) -> list[str]:
    """Check measures and rules against the finished `flat` view. Failures switch the item off
    (item.error is set) and are returned as readable messages."""
    cols = {c.flat_name for c in reg.columns if c.flat_name and not c.error}
    problems = [f"Column {c.name}: {c.error}" for c in reg.columns if c.error]
    taken = set(cols)
    for m in reg.measures:
        m.error = ""
        try:
            if not IDENT.match(m.name):
                raise ExpressionError(f"{m.name!r} is not a valid name (letters, digits, underscore).")
            if m.name in taken:
                raise ExpressionError(f"{m.name!r} is already used by a column or another measure.")
            check_expression(m.expression, cols, aggregate=True)
            con.execute(f"SELECT {m.expression} FROM {_sample(con)}").fetchall()
        except (ExpressionError, duckdb.Error) as e:
            m.error = str(e).splitlines()[0]
            problems.append(f"Measure {m.name}: {m.error}")
            continue
        taken.add(m.name)
    for r in reg.rules:
        r.error = ""
        try:
            check_expression(r.condition, cols, aggregate=False)
            con.execute(f"SELECT count(*) FROM {_sample(con)} WHERE {r.condition}").fetchall()
        except (ExpressionError, duckdb.Error) as e:
            r.error = str(e).splitlines()[0]
            problems.append(f"Rule {r.name}: {r.error}")
    return problems


def preview_expression(con: duckdb.DuckDBPyConnection, reg: Registry, kind: str, expression: str) -> dict:
    """Live check for the editor: is this expression valid, and what does it produce on a sample?"""
    cols = {c.flat_name for c in reg.columns if c.flat_name and not c.error}
    try:
        if kind == "measure":
            check_expression(expression, cols, aggregate=True)
            value = con.execute(f"SELECT {expression} FROM {_sample(con)}").fetchone()[0]
            return {"ok": True, "preview": {"value": None if value is None else float(value)}}
        if kind == "column":
            check_expression(expression, cols, aggregate=False)
            rows = con.execute(f"SELECT DISTINCT ({expression}) AS v FROM {_sample(con)} LIMIT 8").fetchall()
            return {"ok": True, "preview": {"values": [None if r[0] is None else str(r[0]) for r in rows]}}
        if kind == "rule":
            check_expression(expression, cols, aggregate=False)
            hit, total = con.execute(
                f"SELECT count(*) FILTER (WHERE {expression}), count(*) FROM {_sample(con)}").fetchone()
            return {"ok": True, "preview": {"matching": int(hit), "of": int(total)}}
        return {"ok": False, "error": f"Unknown kind {kind!r}."}
    except (ExpressionError, duckdb.Error) as e:
        return {"ok": False, "error": str(e).splitlines()[0]}
