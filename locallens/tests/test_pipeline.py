"""Pipeline behaviour with a fake SLM: date handling, clarification, follow-ups, offline."""
import socket
from datetime import date

import pytest

from locallens.core import pipeline
from locallens.query.frame import QueryFrame
from locallens.nlu.preprocess import preprocess, resolve_dates
from locallens.core.session import Session

M = {"column": "sales_amt", "agg": "SUM"}


class FakeSLM:
    """Returns a canned frame; records what it was asked."""

    def __init__(self, frame: dict):
        self.frame = QueryFrame.model_validate(frame)
        self.calls = []

    def fill_frame(self, pre, reg, prev=None):
        self.calls.append((pre, prev))
        return self.frame.model_copy(deep=True), self.frame.model_dump_json()


def test_relative_dates_use_data_max_as_today():
    today = date(2025, 12, 31)
    assert resolve_dates("revenue last quarter", today).start == date(2025, 7, 1)
    assert resolve_dates("revenue last quarter", today).end == date(2025, 9, 30)
    assert resolve_dates("sales in 2024", today).end == date(2024, 12, 31)
    assert resolve_dates("sales Q1 2024", today).end == date(2024, 3, 31)
    assert resolve_dates("show sales", today) is None


def test_spelling_fixed_against_schema_vocabulary(reg):
    pre = preprocess("compare revnue by categry", reg, date(2025, 12, 31))
    assert "category" in pre.text
    assert ("categry", "category") in pre.corrections


def test_date_hint_overrides_model_dates(reg, con):
    slm = FakeSLM({"intent": "trend", "metric": M,
                   "time": {"column": "order_date", "grain": "month", "start": "1999-01-01", "end": "1999-12-31"}})
    res = pipeline.ask("monthly sales for 2024", reg, con, slm)
    assert res.error == "" and "2024-01-01" in res.sql and "1999" not in res.sql
    assert res.chart.type == "line"


def test_ambiguous_term_asks_instead_of_guessing(reg, con):
    # "region" is a synonym of store_region; "customer region" maps to cust_region -> add a clash
    reg.by_flat_name("cust_region").synonyms.append("region")
    try:
        res = pipeline.ask("compare sales by region", reg, con, FakeSLM({"intent": "summary", "metric": M}))
    finally:
        reg.by_flat_name("cust_region").synonyms.remove("region")
    assert res.clarification and set(res.clarification.options) == {"cust_region", "store_region"}
    assert res.sql == ""


def test_model_flagged_ambiguity_becomes_clarification(reg, con):
    slm = FakeSLM({"intent": "summary", "metric": M, "ambiguous": ["metric"]})
    res = pipeline.ask("show sales", reg, con, slm)
    assert res.clarification and res.clarification.field == "metric"
    assert "sales_amt" in res.clarification.options


def test_followup_passes_previous_frame(reg, con):
    s = Session()
    pipeline.ask("total sales", reg, con, FakeSLM({"intent": "summary", "metric": M}), s)
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category"})
    res = pipeline.ask("now by category", reg, con, slm, s, followup=True)
    assert slm.calls[0][1] is not None and slm.calls[0][1].intent == "summary"
    assert res.chart.type == "bar"


def test_empty_result_gives_helpful_error(reg, con):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category"})
    res = pipeline.ask("sales by category in 1999", reg, con, slm)   # data only covers 2023-2025
    assert "no rows" in res.error


def test_full_pipeline_makes_no_network_calls(reg, con, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category"})
    res = pipeline.ask("compare sales by category", reg, con, slm)
    assert res.error == "" and res.df is not None


def test_clarification_choice_is_applied(reg, con):
    slm = FakeSLM({"intent": "summary", "metric": {"column": "sales_amt", "agg": "SUM"}, "ambiguous": ["metric"]})
    res = pipeline.ask("show profit", reg, con, slm, overrides={"metric": "profit"})
    assert res.error == "" and "profit" in res.sql and res.clarification is None


def test_followup_detection():
    s = Session(last_frame=QueryFrame.model_validate({"intent": "summary", "metric": M}))
    assert pipeline.is_followup("now split by region", s)
    assert pipeline.is_followup("only 2024", s)
    assert not pipeline.is_followup("show monthly sales for 2024 by region", s)
    assert not pipeline.is_followup("only 2024", Session())


def test_column_hints_pick_longest_unique_phrase(reg):
    pre = preprocess("sales by region", reg, date(2025, 12, 31))
    assert pre.column_hints["region"] == "store_region"
    pre = preprocess("sales by customer region", reg, date(2025, 12, 31))
    assert "region" not in pre.column_hints and pre.column_hints["customer region"] == "cust_region"


def test_invented_filters_are_dropped(reg, con):
    bogus = [{"column": "cust_region", "op": ">=", "value": "2024-01-01"},
             {"column": "cust_seg", "op": "=", "value": "Corporate"}]
    slm = FakeSLM({"intent": "summary", "metric": M, "filters": bogus})
    res = pipeline.ask("total revenue for corporate in 2024", reg, con, slm)
    assert "cust_region" not in res.sql and "'Corporate'" in res.sql


def test_invented_dimension_is_dropped(reg, con):
    slm = FakeSLM({"intent": "trend", "metric": M, "dimension": "cust_seg",
                   "time": {"column": "order_date", "grain": "month", "start": None, "end": None}})
    res = pipeline.ask("monthly revenue for 2024", reg, con, slm)
    assert res.frame.dimension is None and res.chart.type == "line"


def test_value_mentioned_in_question_becomes_filter(reg, con):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "cust_city"})
    res = pipeline.ask("sales for corporate customers by city", reg, con, slm)
    assert "'Corporate'" in res.sql and "cust_seg" in res.sql


def test_plural_phrases_match(reg):
    pre = preprocess("top 3 sub categories by profit", reg, date(2025, 12, 31))
    assert pre.column_hints.get("sub category") == "sub_category"
    pre = preprocess("sales by categories", reg, date(2025, 12, 31))
    assert pre.column_hints.get("category") == "category"


def test_value_column_is_filter_not_grouping(reg, con):
    slm = FakeSLM({"intent": "ranking", "metric": {"column": "profit", "agg": "SUM"},
                   "dimension": "cust_seg", "top_n": 3})
    res = pipeline.ask("top 3 sub categories by profit for consumer segment in 2025", reg, con, slm)
    assert res.frame.dimension == "sub_category"
    assert "'Consumer'" in res.sql and len(res.df) == 3


def test_followup_keeps_dimension_and_filters_from_previous_question(reg, con):
    s = Session()
    f = {"column": "cust_seg", "op": "=", "value": "Consumer"}
    pipeline.ask("compare sales by category for consumer", reg, con,
                 FakeSLM({"intent": "comparison", "metric": M, "dimension": "category", "filters": [f]}), s)
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category", "filters": [f],
                   "time": {"column": "order_date", "grain": None, "start": None, "end": None}})
    res = pipeline.ask("now only for 2025", reg, con, slm, s, followup=True)
    assert res.error == "" and res.frame.dimension == "category"
    assert "'Consumer'" in res.sql and "2025-01-01" in res.sql


def test_keyword_typos_are_fixed(reg):
    pre = preprocess("show montly turnover for 2024", reg, date(2025, 12, 31))
    assert "monthly" in pre.text


def test_filter_with_unknown_value_is_dropped_and_casing_normalised(reg, con):
    bad = {"column": "category", "op": "=", "value": "category"}      # in the text, but not a real category
    good = {"column": "cust_seg", "op": "=", "value": "consumer"}     # real value, wrong casing
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category", "filters": [bad, good]})
    res = pipeline.ask("sales by category for consumer customers", reg, con, slm)
    assert [(f.column, f.value) for f in res.frame.filters] == [("cust_seg", "Consumer")]
    assert len(res.df) == 3


@pytest.mark.parametrize("chatter", ["hi there", "hello", "thanks", "what is your name", "asdfgh"])
def test_chatter_is_refused_without_calling_the_model(reg, con, chatter):
    slm = FakeSLM({"intent": "summary", "metric": M})
    res = pipeline.ask(chatter, reg, con, slm)
    assert res.error and "Try something like" in res.error
    assert res.df is None and slm.calls == []


@pytest.mark.parametrize("q", ["total sales", "profit by region", "top 5 products by sales", "sales in 2024",
                               "revenue", "how many orders", "what about corporate customers"])
def test_real_questions_pass_the_gate(reg, con, q):
    pre = preprocess(q, reg, date(2025, 12, 31))
    assert pipeline.looks_like_data_question(pre), q


def test_short_message_naming_a_metric_is_a_new_question(reg):
    s = Session()
    s.last_frame = QueryFrame.model_validate({"intent": "summary", "metric": M})
    assert pipeline.is_followup("by region", s, reg)             # short tweak
    assert pipeline.is_followup("now only 2025", s, reg)
    assert not pipeline.is_followup("profit by region", s, reg)  # names a metric -> fresh
    assert not pipeline.is_followup("sales by category", s, reg)


def test_followup_applies_only_the_named_change_when_model_forgets_previous_frame(reg, con):
    s = Session()
    t = {"column": "order_date", "grain": "month", "start": "2024-01-01", "end": "2024-12-31"}
    pipeline.ask("monthly sales for 2024 by category", reg, con,
                 FakeSLM({"intent": "trend", "metric": M, "dimension": "category", "time": t}), s)
    # the small model returns a bare frame that has lost the trend, the dimension and the year
    bare = FakeSLM({"intent": "summary", "metric": M})
    res = pipeline.ask("now only for Technology", reg, con, bare, s, followup=True)
    assert res.frame.intent == "trend" and res.frame.dimension == "category"
    assert res.frame.time.start == "2024-01-01"
    assert [(f.column, f.value) for f in res.frame.filters] == [("category", "Technology")]
    res = pipeline.ask("and for 2025", reg, con, bare, s, followup=True)
    assert res.frame.time.start == "2025-01-01" and res.frame.filters[0].value == "Technology"


def test_numeric_group_by_column_is_charted_as_a_category():
    import pandas as pd
    from locallens.core.pipeline import label_dimension
    from locallens.query.frame import QueryFrame
    f = QueryFrame.model_validate({"intent": "ranking", "metric": {"column": "revenue", "agg": "SUM"}, "dimension": "Customer ID", "top_n": 3})
    df = pd.DataFrame({"Customer ID": [12347.0, 12348.0], "revenue": [10.5, 7.0]})
    out = label_dimension(df, f)
    assert list(out["Customer ID"]) == ["12347", "12348"] and list(out["revenue"]) == [10.5, 7.0]
