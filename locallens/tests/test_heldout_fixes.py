"""Regression tests for the failures found by the first held-out evaluation (docs/EVAL.md)."""
from datetime import date

import pytest

from locallens.core import pipeline
from locallens.data.registry import Registry
from locallens.nlu.preprocess import preprocess
from locallens.nlu.rules import infer
from locallens.query.frame import QueryFrame
from locallens.query.sqlgen import build_sql
from tests.test_pipeline import FakeSLM, M


@pytest.mark.parametrize("text,intent,grain", [
    ("profit per quarter 2024", "trend", "quarter"),
    ("how is profit growing year over year", "trend", "year"),
    ("sales a week", "trend", "week"),
    ("revenue month over month", "trend", "month"),
    ("yoy profit", "trend", "year"),
])
def test_grain_and_trend_words(text, intent, grain):
    h = infer(text, False, True)
    assert (h.intent, h.grain) == (intent, grain)


def test_distributed_means_distribution():
    assert infer("how are profits distributed in 2024", False, True).intent == "distribution"


@pytest.mark.parametrize("text", ["which category has the lowest sales", "bottom 5 sub categories by profit",
                                  "worst performing store", "fewest orders by region"])
def test_lowest_and_bottom_sort_ascending(text):
    assert infer(text, True, True).order == "asc"


def test_highest_x_means_one_but_plural_means_a_list():
    assert infer("highest revenue store", True, True, dimension_is_singular=True).top_n == 1
    assert infer("best selling products by units", True, True, dimension_is_singular=False).top_n is None
    assert infer("top 5 stores by sales", True, True, dimension_is_singular=True).top_n == 5


def test_ranking_sql_respects_order(sreg, scon):
    f = lambda order: QueryFrame.model_validate({"intent": "ranking", "metric": M, "dimension": "category",  # noqa: E731
                                                 "top_n": 1, "order": order})
    hi = scon.execute(build_sql(f("desc"), sreg)).df()
    lo = scon.execute(build_sql(f("asc"), sreg)).df()
    full = scon.execute("SELECT category, SUM(sales_amt) v FROM flat GROUP BY 1 ORDER BY v").df()
    assert lo.iloc[0, 0] == full.iloc[0, 0] and hi.iloc[0, 0] == full.iloc[-1, 0]


def test_end_to_end_lowest(sreg, scon):
    slm = FakeSLM({"intent": "ranking", "metric": M, "dimension": "category", "top_n": 1})
    res = pipeline.ask("which category has the lowest sales", sreg, scon, slm)
    full = scon.execute("SELECT category, SUM(sales_amt) v FROM flat GROUP BY 1 ORDER BY v").df()
    assert res.frame.order == "asc" and res.df.iloc[0, 0] == full.iloc[0, 0]


def test_hyphen_between_words_but_not_in_dates(sreg):
    assert "sub category" in preprocess("sales by sub-category", sreg, date(2025, 12, 31)).text
    assert "2024-01-01" in preprocess("sales since 2024-01-01", sreg, date(2025, 12, 31)).text


def test_value_beside_column_is_a_filter_not_a_grouping(sreg, scon):
    slm = FakeSLM({"intent": "trend", "metric": M, "dimension": "category",
                   "time": {"column": "order_date", "grain": "month"}})
    res = pipeline.ask("What were the sales in 2024 for the Technology category by month", sreg, scon, slm)
    assert res.frame.dimension is None
    assert [(f.column, f.value) for f in res.frame.filters] == [("category", "Technology")]


def test_grouping_by_a_column_that_also_has_a_value_mentioned_is_kept(sreg, scon):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category"})
    res = pipeline.ask("sales by category", sreg, scon, slm)
    assert res.frame.dimension == "category" and res.frame.filters == []


def test_order_value_means_sales_not_average_order_value(sreg):
    pre = preprocess("distribution of order values", sreg, date(2025, 12, 31))
    assert pre.column_hints.get("order value") == "sales_amt"


@pytest.mark.parametrize("text,n", [("5 most profitable products", 5), ("top 3 stores", 3), ("three best regions", 3),
                                    ("bottom 5 sub categories by profit", 5), ("10 highest cities", 10),
                                    ("best selling products by units", None)])
def test_top_n_comes_from_the_question(text, n):
    assert infer(text, True, True).top_n == n


def test_models_invented_limit_is_dropped(sreg, scon):
    slm = FakeSLM({"intent": "ranking", "metric": M, "dimension": "product_name", "top_n": 1})
    res = pipeline.ask("best selling products by sales", sreg, scon, slm)
    assert res.frame.top_n is None and len(res.df) == 10        # default list length, not 1


def test_plurals_are_not_treated_as_typos(sreg):
    pre = preprocess("best selling products by sales across stores and categories", sreg, date(2025, 12, 31))
    assert pre.corrections == [] and "products" in pre.text and "categories" in pre.text
    assert preprocess("compare revnue by categry", sreg, date(2025, 12, 31)).corrections   # real typos still fixed


def test_last_n_months_is_not_a_limit():
    assert infer("Revenue trend over the last 12 months", False, True).top_n is None


def test_named_dimension_with_no_other_signal_is_a_comparison():
    assert infer("how do the regions stack up on revenue", True, True).intent == "comparison"
    assert infer("what is our total revenue", False, True).intent == "summary"


def test_plural_value_mentions_still_filter(sreg):
    pre = preprocess("how many units did consumers buy in 2025", sreg, date(2025, 12, 31))
    assert ("cust_seg", "Consumer") in pre.value_mentions


# ---- round 2 (second held-out set) -----------------------------------------------------
TODAY = date(2025, 12, 31)
from locallens.nlu.preprocess import resolve_dates  # noqa: E402


@pytest.mark.parametrize("text,start,end", [
    ("weekly profit in December 2025", date(2025, 12, 1), date(2025, 12, 31)),
    ("daily orders in November 2025", date(2025, 11, 1), date(2025, 11, 30)),
    ("sales in Feb 2024", date(2024, 2, 1), date(2024, 2, 29)),
    ("sales in March", date(2025, 3, 1), date(2025, 3, 31)),
    ("sales for may 2023", date(2023, 5, 1), date(2023, 5, 31)),
    ("sales in September", date(2025, 9, 1), date(2025, 9, 30)),
])
def test_month_names(text, start, end):
    h = resolve_dates(text, TODAY)
    assert (h.start, h.end) == (start, end)


@pytest.mark.parametrize("text", ["you may want to see sales", "mar the data", "what is the dec", "sales in 2024"])
def test_month_names_are_not_over_matched(text):
    h = resolve_dates(text, TODAY)
    assert h is None or h.phrase == "2024"          # only a real year may match, never a stray "may"/"mar"/"dec"


def test_a_month_in_a_past_year_still_beats_a_bare_year():
    assert resolve_dates("sales in June 2024", TODAY).start == date(2024, 6, 1)


@pytest.mark.parametrize("text", ["Can you show me how sales developed over 2024?",
                                  "I'd like to see the revenue curve for 2023", "sales trajectory in 2025"])
def test_more_trend_words(text):
    assert infer(text, False, True).intent == "trend"


def test_profitable_means_profit(sreg):
    pre = preprocess("show me the 3 least profitable categories", sreg, TODAY)
    assert pre.column_hints.get("profit") == "profit"


def test_value_in_two_columns_asks_which(sreg, scon):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category"})
    res = pipeline.ask("sales by category for West", sreg, scon, slm)
    assert res.clarification and res.clarification.field == "filter"
    assert set(res.clarification.options) == {"cust_region", "store_region"} and slm.calls == []
    again = pipeline.ask("sales by category for West", sreg, scon, slm, overrides={"filter": "store_region"})
    assert [(f.column, f.value) for f in again.frame.filters] == [("store_region", "West")]


def test_value_beside_its_column_name_needs_no_question(sreg, scon):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "category",
                   "filters": [{"column": "cust_region", "op": "=", "value": "West"},
                               {"column": "store_region", "op": "=", "value": "West"}]})
    res = pipeline.ask("sales in the West store region by category", sreg, scon, slm)
    assert res.clarification is None and res.error == ""
    assert [(f.column, f.value) for f in res.frame.filters] == [("store_region", "West")]


# ---- round 3: unknown words after "by / per / each" -------------------------------------------------
from locallens.nlu.preprocess import unknown_group_term  # noqa: E402


@pytest.mark.parametrize("q,word", [("units sold by town", "town"), ("sales for each outlet", "outlet"), ("profit per widget", "widget")])
def test_unknown_grouping_word_is_found(sreg, q, word):
    assert unknown_group_term(preprocess(q, sreg, TODAY), sreg) == word


@pytest.mark.parametrize("q", ["sales by category", "profit per month", "sales by customer segment", "revenue by store in 2024",
                               "orders per quarter", "sales by region", "units each year", "sales for each product", "sales by Furniture"])
def test_known_grouping_words_are_not_questioned(sreg, q):
    assert unknown_group_term(preprocess(q, sreg, TODAY), sreg) is None


def test_unknown_grouping_word_asks_and_the_answer_is_used(sreg, scon):
    slm = FakeSLM({"intent": "summary", "metric": {"column": "quantity", "agg": "SUM"}})
    r = pipeline.ask("units sold by town", sreg, scon, slm)
    assert r.clarification and r.clarification.field == "dimension" and "cust_city" in r.clarification.options and slm.calls == []
    again = pipeline.ask("units sold by town", sreg, scon, slm, overrides={"dimension": "cust_city"})
    assert again.error == "" and again.frame.intent == "comparison" and again.frame.dimension == "cust_city" and len(again.df) == 8
