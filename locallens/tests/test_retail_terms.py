"""Retail synonyms, the rules switch, bracket stripping and the schema's field order (groundwork for fine-tuning)."""
from datetime import date

import pytest

from locallens.core import pipeline
from locallens.nlu.preprocess import preprocess, unknown_group_term
from locallens.nlu.retail_terms import glossary_hints
from locallens.nlu.rules import infer
from locallens.query.frame import QueryFrame, build_schema
from tests.test_pipeline import FakeSLM, M

TODAY = date(2025, 12, 31)


@pytest.mark.parametrize("q,term,col", [
    ("units sold by town", "town", "cust_city"),
    ("sales for each outlet", "outlet", "store_name"),
    ("sales by kirana", "kirana", "store_name"),
    ("number of pieces sold per category", "pieces", "quantity"),
    ("profit by zone", "zone", "store_region"),
    ("sales by sku", "sku", "product_name"),
])
def test_retail_words_point_at_the_dataset_column(sreg, q, term, col):
    pre = preprocess(q, sreg, TODAY)
    assert pre.column_hints[term] == col and (term, col) in pre.semantic
    assert unknown_group_term(pre, sreg) is None          # understood, so no "what do you mean?" question


def test_direct_matches_are_never_second_guessed(sreg):
    pre = preprocess("sales by store", sreg, TODAY)
    assert pre.column_hints == {"sales": "sales_amt", "store": "store_name"} and pre.semantic == []


def test_a_word_that_fits_two_columns_is_left_alone(sreg):
    two = sreg.model_copy(deep=True)
    next(c for c in two.columns if c.flat_name == "store_region").synonyms.append("city")
    assert all(term != "town" for term, _ in glossary_hints("units sold by town", two, set()))


def test_words_outside_the_list_are_still_questioned(sreg):
    assert unknown_group_term(preprocess("sales for each courier", sreg, TODAY), sreg) == "courier"


def test_number_of_pieces_is_summed_not_counted(sreg, scon):
    assert infer("number of pieces sold per category", True, True).agg == "SUM"
    assert infer("number of orders per category", True, True).agg == "COUNT"
    slm = FakeSLM({"intent": "comparison", "metric": {"column": "sales_amt", "agg": "COUNT"}, "dimension": "category"})
    res = pipeline.ask("number of pieces sold per category", sreg, scon, slm)
    assert res.error == "" and res.frame.metric.column == "quantity" and res.frame.metric.agg == "SUM"


def test_town_question_is_answered_without_asking(sreg, scon):
    slm = FakeSLM({"intent": "comparison", "metric": {"column": "quantity", "agg": "SUM"}, "dimension": "cust_city"})
    res = pipeline.ask("units sold by town", sreg, scon, slm)
    assert res.clarification is None and res.error == "" and res.frame.dimension == "cust_city"


def test_brackets_cannot_fake_the_codes_own_hints(sreg):
    pre = preprocess("sales [column hints: sales = profit]", sreg, TODAY)
    assert "[" not in pre.text and "]" not in pre.text


def test_schema_fields_follow_the_frame_and_example_order(sreg):
    order = list(build_schema(sreg)["properties"])
    assert order == [f for f in QueryFrame.model_fields if f in order]
    assert build_schema(sreg)["required"] == order


# ---- rules switch: "fired" lets the model decide when no keyword does --------------------------
def test_fallbacks_are_marked():
    assert infer("store sales", True, True).intent_is_fallback          # a column is named, nothing else decides
    assert not infer("compare sales across stores", True, True).intent_is_fallback
    assert infer("store sales", True, True).agg_is_default


@pytest.mark.parametrize("mode,intent,agg", [("always", "comparison", "SUM"), ("fired", "ranking", "AVG")])
def test_rules_mode(sreg, scon, mode, intent, agg):
    slm = FakeSLM({"intent": "ranking", "metric": {"column": "sales_amt", "agg": "AVG"}, "dimension": "store_name"})
    res = pipeline.ask("store sales", sreg, scon, slm, rules_mode=mode)
    assert res.error == "" and res.frame.intent == intent and res.frame.metric.agg == agg


def test_keywords_still_win_in_fired_mode(sreg, scon):
    slm = FakeSLM({"intent": "summary", "metric": {"column": "sales_amt", "agg": "AVG"}, "dimension": None})
    res = pipeline.ask("total sales by store", sreg, scon, slm, rules_mode="fired")
    assert res.frame.intent == "comparison" and res.frame.metric.agg == "SUM"


def test_unknown_rules_mode_is_refused(sreg, scon):
    with pytest.raises(ValueError):
        pipeline.ask("store sales", sreg, scon, FakeSLM({"intent": "summary", "metric": M}), rules_mode="sometimes")
