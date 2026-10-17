"""Semantic layer: measures, calculated columns, business rules, fiscal dates, prompt context."""
from datetime import date

import pytest

from locallens.data import ingest

from locallens.core import pipeline

from locallens.data import semantic
from locallens.query.frame import QueryFrame, build_schema
from locallens.nlu.preprocess import preprocess, resolve_dates
from locallens.data.registry import CALC_TABLE, Column, Measure, Registry, Rule
from locallens.nlu.slm import describe_columns, similar_examples
from locallens.query.sqlgen import FrameError, build_sql
from locallens.query.validator import validate_frame, validate_sql
from tests.test_pipeline import FakeSLM

M = {"column": "sales_amt", "agg": "SUM"}
COLS = {"profit", "sales_amt", "quantity", "order_id"}


def frame(**kw):
    base = {"intent": "comparison", "metric": M, "dimension": "category"}
    return QueryFrame.model_validate({**base, **kw})


# ---- expression safety ---------------------------------------------------------
@pytest.mark.parametrize("bad", [
    "(SELECT 1)", "profit + nope", "read_csv('/etc/passwd')", "SUM(profit); DROP TABLE x",
    "orders.profit", "*", "SUM(profit) OVER ()", "epoch_ms(1)", "current_setting('x')", "", "SUM(profit",
])
def test_unsafe_or_broken_expressions_are_rejected(bad):
    with pytest.raises(semantic.ExpressionError):
        semantic.check_expression(bad, COLS)


def test_aggregate_rules():
    semantic.check_expression("SUM(profit) / NULLIF(SUM(sales_amt), 0)", COLS, aggregate=True)
    semantic.check_expression("CASE WHEN sales_amt > 5 THEN 'a' ELSE 'b' END", COLS, aggregate=False)
    with pytest.raises(semantic.ExpressionError):
        semantic.check_expression("profit * 2", COLS, aggregate=True)      # measure without an aggregate
    with pytest.raises(semantic.ExpressionError):
        semantic.check_expression("SUM(profit)", COLS, aggregate=False)    # row-level with an aggregate


# ---- loading ---------------------------------------------------------------------
def test_demo_semantic_layer_loads_cleanly(sreg, scon):
    assert sreg.problems == []
    assert {m.name for m in sreg.active_measures()} == {"profit_margin", "avg_order_value", "order_count"}
    assert "order_size" in {c.flat_name for c in sreg.tagged("dimension")}
    assert set(scon.execute("SELECT DISTINCT order_size FROM flat").df()["order_size"]) == {"Large", "Medium", "Small"}


def test_bad_definitions_are_switched_off_not_fatal(sreg, tmp_path):
    r = sreg.model_copy(deep=True)
    r.columns.append(Column(table=CALC_TABLE, name="oops", tag="dimension", expression="nope + 1"))
    r.columns.append(Column(table=CALC_TABLE, name="fine", tag="metric", expression="profit * 2"))
    r.measures.append(Measure(name="no_agg", expression="profit * 2"))
    r.measures.append(Measure(name="sales_amt", expression="SUM(profit)"))          # clashes with a column
    r.measures.append(Measure(name="bad name", expression="SUM(profit)"))
    r.rules.append(Rule(name="broken", condition="ghost > 1"))
    con = ingest.prepare(r)
    errors = {c.name: c.error for c in r.columns if c.table == CALC_TABLE}
    assert errors["oops"] and not errors["fine"]
    assert {m.name for m in r.measures if m.error} == {"no_agg", "sales_amt", "bad name"}
    assert [x.name for x in r.rules if x.error] == ["broken"]
    assert len(r.problems) == 5
    assert "profit_margin" in {m.name for m in r.active_measures()}                    # the rest still works
    con.execute("SELECT fine FROM flat LIMIT 1")


def test_registry_roundtrip_and_old_files_still_load(sreg, tmp_path):
    sreg.save(tmp_path / "r.json")
    again = Registry.load(tmp_path / "r.json")
    assert [m.name for m in again.measures] == [m.name for m in sreg.measures] and again.rules[1].phrases
    legacy = Registry.model_validate({"name": "old", "main_table": "t", "columns": [{"table": "t", "name": "a"}]})
    assert legacy.measures == [] and legacy.fiscal_start_month == 1


# ---- measures --------------------------------------------------------------------
def test_measure_is_a_choice_in_the_schema(sreg):
    enum = build_schema(sreg)["properties"]["metric"]["properties"]["column"]["enum"]
    assert {"sales_amt", "profit_margin", "avg_order_value"} <= set(enum)


def test_measure_sql_matches_hand_computed_numbers(sreg, scon):
    f = frame(metric={"column": "profit_margin", "agg": "SUM"})
    validate_frame(f, sreg)
    sql = build_sql(f, sreg)
    validate_sql(sql, sreg)
    got = scon.execute(sql).df().set_index("category")["profit_margin"]
    want = scon.execute("SELECT category, SUM(profit)/SUM(sales_amt) m FROM flat GROUP BY 1").df().set_index("category")["m"]
    assert (got - want).abs().max() < 1e-12


def test_measure_guards(sreg):
    with pytest.raises(FrameError, match="no spread"):
        build_sql(frame(intent="distribution", dimension=None, metric={"column": "profit_margin", "agg": "SUM"}), sreg)
    with pytest.raises(FrameError, match="shares"):
        build_sql(frame(intent="proportion", metric={"column": "profit_margin", "agg": "SUM"}), sreg)
    build_sql(frame(intent="proportion", metric={"column": "order_count", "agg": "SUM"}), sreg)   # additive: fine


def test_measures_work_in_trends_and_rankings(sreg, scon):
    t = build_sql(frame(intent="trend", dimension=None, metric={"column": "avg_order_value", "agg": "SUM"},
                        time={"column": "order_date", "grain": "month"}), sreg)
    assert len(scon.execute(t).df()) > 12
    r = build_sql(frame(intent="ranking", top_n=3, metric={"column": "profit_margin", "agg": "SUM"}), sreg)
    assert len(scon.execute(r).df()) == 3


# ---- the pipeline picks measures up from plain language ---------------------------------
def test_named_measure_beats_the_models_guess(sreg, scon):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category"})   # model picked sales_amt
    res = pipeline.ask("profit margin by category", sreg, scon, slm)
    assert res.error == "" and res.frame.metric.column == "profit_margin"
    assert "profit_margin" in res.df.columns


def test_measure_synonyms_and_spelling(sreg):
    pre = preprocess("show aov by store", sreg, date(2025, 12, 31))
    assert pre.column_hints["aov"] == "avg_order_value"
    pre = preprocess("baskt value by store", sreg, date(2025, 12, 31))   # typo in a measure synonym
    assert pre.text.startswith("basket value") and pre.column_hints["basket value"] == "avg_order_value"


# ---- business rules -----------------------------------------------------------------
def test_always_rule_is_in_every_query(sreg):
    assert "(quantity > 0)" in build_sql(frame(), sreg)


def test_phrase_rule_only_when_asked(sreg, scon):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category"})
    plain = pipeline.ask("sales by category", sreg, scon, slm)
    high = pipeline.ask("sales by category for high value orders", sreg, scon, slm)
    assert plain.frame.rules == [] and "sales_amt >= 1000" not in plain.sql
    assert high.frame.rules == ["high_value"] and "sales_amt >= 1000" in high.sql
    assert high.df.iloc[:, 1].sum() < plain.df.iloc[:, 1].sum()


def test_rule_phrase_alone_passes_the_data_question_gate(sreg):
    assert pipeline.looks_like_data_question(preprocess("high value", sreg, date(2025, 12, 31)), sreg)


def test_followup_keeps_the_rule(sreg, scon):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category"})
    s = pipeline.Session()
    first = pipeline.ask("sales by category for high value orders", sreg, scon, slm, s)
    second = pipeline.ask("now only 2024", sreg, scon, slm, s, followup=True)
    assert first.frame.rules == second.frame.rules == ["high_value"]


def test_disabled_rule_is_not_applied(sreg, scon):
    r = sreg.model_copy(deep=True)
    for x in r.rules:
        x.enabled = False
    assert "quantity > 0" not in build_sql(frame(), r)


# ---- fiscal calendar ------------------------------------------------------------------
TODAY = date(2025, 12, 31)


def test_calendar_year_default_is_unchanged():
    assert resolve_dates("sales last quarter", TODAY).start == date(2025, 7, 1)
    assert resolve_dates("sales this year", TODAY).start == date(2025, 1, 1)
    assert resolve_dates("sales in 2024", TODAY).end == date(2024, 12, 31)
    h = resolve_dates("sales fy2025", TODAY)
    assert (h.start, h.end) == (date(2025, 1, 1), date(2025, 12, 31))


def test_fiscal_year_starting_in_april():
    fy = lambda q: resolve_dates(q, TODAY, 4)           # noqa: E731
    assert (fy("last quarter").start, fy("last quarter").end) == (date(2025, 7, 1), date(2025, 9, 30))
    assert fy("this quarter").start == date(2025, 10, 1)
    assert fy("this year").start == date(2025, 4, 1)
    assert (fy("last year").start, fy("last year").end) == (date(2024, 4, 1), date(2025, 3, 31))
    assert (fy("FY2025").start, fy("FY25").end) == (date(2024, 4, 1), date(2025, 3, 31))
    assert (fy("Q1 2026").start, fy("Q1 2026").end) == (date(2025, 4, 1), date(2025, 6, 30))
    assert fy("sales in 2024").start == date(2024, 1, 1)  # a bare year stays a calendar year


def test_fiscal_quarter_rolls_over_the_year_boundary():
    assert resolve_dates("last quarter", date(2026, 1, 15), 4).end == date(2025, 12, 31)
    assert resolve_dates("last quarter", date(2026, 4, 10), 4).start == date(2026, 1, 1)
    assert resolve_dates("last quarter", date(2025, 5, 1), 4).start == date(2025, 1, 1)   # Q4 of FY2025


def test_registry_setting_reaches_preprocess(sreg):
    r = sreg.model_copy(deep=True)
    r.fiscal_start_month = 4
    assert preprocess("sales this year", r, TODAY).date_hint.start == date(2025, 4, 1)


# ---- what the model is told ------------------------------------------------------------
def test_prompt_carries_descriptions_and_measures(sreg):
    text = describe_columns(sreg)
    assert "Order value after discount" in text and "order_size (dimension)" in text
    assert "profit_margin (metric) - Profit as a share of sales" in text and "aov" in text


def test_closest_verified_examples_come_last(sreg):
    from locallens.data.registry import Example
    r = sreg.model_copy(deep=True)
    r.examples += [Example(question=q, frame={}) for q in
                   ("sales by region", "top products by profit", "profit margin by category", "zzz qqq")]
    got = [q for q, _ in similar_examples(r, "profit margin by store")]
    assert got[-1] == "profit margin by category" and "zzz qqq" not in got


def test_ranking_ties_have_a_stable_order(sreg, scon):
    sql = build_sql(frame(intent="ranking", top_n=5, dimension="product_name",
                          metric={"column": "order_count", "agg": "SUM"}), sreg)
    runs = [scon.execute(sql).df()["product_name"].tolist() for _ in range(5)]
    assert all(r == runs[0] for r in runs)


def test_measure_agg_is_normalised(sreg, scon):
    slm = FakeSLM({"intent": "comparison", "metric": {"column": "avg_order_value", "agg": "AVG"}, "dimension": "category"})
    res = pipeline.ask("average order value by category", sreg, scon, slm)
    assert res.error == "" and res.frame.metric.agg == "SUM"
