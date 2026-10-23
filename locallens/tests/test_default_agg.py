"""The saved default aggregation applies only when the question does not say how to combine numbers."""
import pandas as pd
import pytest

from locallens.core import pipeline
from locallens.core.session import Session
from locallens.nlu.rules import infer
from locallens.viz.charts import _compatible, build_spec
from locallens.data.profiler import profile
from locallens.server.routes_chat import CHART_CHOICES
from tests.test_pipeline import FakeSLM

M = {"column": "sales_amt", "agg": "SUM"}
COMPARE = {"intent": "comparison", "metric": M, "dimension": "category"}


def test_infer_uses_the_default_only_without_an_aggregation_word():
    assert infer("sales by region", True, True, default_agg="AVG").agg == "AVG"
    assert infer("sales by region", True, True, default_agg="AVG").agg_is_default
    for text, agg in [("total sales by region", "SUM"), ("average sales by region", "AVG"),
                      ("highest sales by region", None), ("maximum sales by region", "MAX"), ("number of orders by region", "COUNT")]:
        h = infer(text, True, True, default_agg="MIN")
        assert not h.agg_is_default or agg is None, text
        if agg:
            assert h.agg == agg, text


def agg_of(reg, con, text, default_agg):
    res = pipeline.ask(text, reg, con, FakeSLM(COMPARE), Session(), prefs={"default_agg": default_agg})
    assert res.error == "", res.error
    return res.frame.metric.agg


def test_default_agg_reaches_the_frame(reg, con):
    assert agg_of(reg, con, "compare sales by category", "AVG") == "AVG"
    assert agg_of(reg, con, "compare sales by category", "SUM") == "SUM"
    assert agg_of(reg, con, "compare sales by category", None) == "SUM"       # no preference stored


def test_words_in_the_question_beat_the_preference(reg, con):
    assert agg_of(reg, con, "compare total sales by category", "AVG") == "SUM"
    assert agg_of(reg, con, "compare maximum sales by category", "AVG") == "MAX"


def test_a_share_is_never_an_average(reg, con):
    res = pipeline.ask("what share of sales comes from each category", reg, con,
                       FakeSLM({"intent": "proportion", "metric": M, "dimension": "category"}), Session(),
                       prefs={"default_agg": "AVG"})
    assert res.error == "" and res.frame.intent == "proportion" and res.frame.metric.agg == "SUM"


def test_every_saved_chart_choice_can_actually_take_effect():
    """A choice offered on the Preferences page must be compatible with what the rules pick for that intent."""
    typical = {
        "trend": (pd.DataFrame({"period": pd.to_datetime(["2024-01-01", "2024-02-01"]), "v": [1, 2]}), "line"),
        "comparison": (pd.DataFrame({"c": ["a", "b"], "v": [1, 2]}), "bar"),
        "ranking": (pd.DataFrame({"c": ["a", "b"], "v": [2, 1]}), "hbar"),
        "proportion": (pd.DataFrame({"c": ["a", "b"], "v": [1, 2]}), "donut"),
    }
    assert set(CHART_CHOICES) == set(typical)            # distribution and summary have no real alternative
    for intent, choices in CHART_CHOICES.items():
        df, auto = typical[intent]
        for choice in choices:
            assert _compatible(choice, auto), (intent, choice)
            got = build_spec(df, intent, profile(df), {"chart_overrides": {intent: choice}}).type
            assert got == choice, (intent, choice, got)
