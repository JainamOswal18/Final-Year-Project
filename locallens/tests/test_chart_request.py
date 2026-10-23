"""'Make it a pie chart': chart words in a question, redrawing the last answer without the language model."""
import pytest

from locallens.core import pipeline
from locallens.core.session import Session
from locallens.nlu.chart_request import detect_chart, strip_chart_words
from tests.test_pipeline import FakeSLM

M = {"column": "sales_amt", "agg": "SUM"}
T = {"column": "order_date", "grain": "month", "start": "2024-01-01", "end": "2024-12-31"}
COMPARE = {"intent": "comparison", "metric": M, "dimension": "category"}
TREND = {"intent": "trend", "metric": M, "time": T}
TREND_BY = {"intent": "trend", "metric": M, "dimension": "category", "time": T}
SUMMARY = {"intent": "summary", "metric": M}
DISTRIBUTION = {"intent": "distribution", "metric": {"column": "sales_amt", "agg": "SUM"}}


@pytest.mark.parametrize("text, chart", [
    ("make it a pie chart", "donut"), ("show it as a pie", "donut"), ("a donut please", "donut"),
    ("as a doughnut", "donut"), ("make it a bar chart", "bar"), ("as bars", "bar"),
    ("show horizontal bars", "hbar"), ("horizontal bar chart", "hbar"),
    ("now a histogram", "histogram"), ("make it a line chart", "line"), ("as a line", "line"),
    ("sales by product line", None), ("sales by category", None), ("total sales", None),
])
def test_chart_words(text, chart):
    assert detect_chart(text) == chart


def test_chart_words_are_removed_before_the_model_sees_them():
    assert strip_chart_words("sales by region as a pie chart") == "sales by region"
    assert strip_chart_words("top 5 products as bars") == "top 5 products"
    assert strip_chart_words("sales by product line as a bar chart") == "sales by product line"   # the column survives


QUESTION = {"comparison": "compare sales by category", "trend": "monthly sales for 2024",
            "distribution": "distribution of sales", "summary": "total sales"}


def start(reg, con, frame, question=None):
    """Ask a first question so there is an answer to redraw. The question must say what the frame says, because
    the rule layer corrects a model answer that disagrees with the words."""
    s = Session()
    slm = FakeSLM(frame)
    first = pipeline.ask(question or QUESTION[frame["intent"]], reg, con, slm, s)
    assert first.error == "", first.error
    return s, slm


def test_chart_request_with_nothing_to_chart(reg, con):
    res = pipeline.ask("make it a pie chart", reg, con, FakeSLM(COMPARE), Session())
    assert "nothing to show as a pie chart" in res.error and res.df is None


def test_comparison_to_pie_works_and_skips_the_model(reg, con):
    s, slm = start(reg, con, COMPARE)
    calls = len(slm.calls)
    res = pipeline.ask("make it a pie chart", reg, con, slm, s)
    assert res.error == "" and res.chart.type == "donut" and res.chart.reason == "you asked for a pie chart"
    assert res.chart_forced == "donut" and len(slm.calls) == calls          # the model was not asked again
    assert res.frame.intent == "comparison" and res.frame.dimension == "category"


def test_histogram_to_pie_explains_why_it_cannot(reg, con):
    s, slm = start(reg, con, DISTRIBUTION)
    res = pipeline.ask("now make it a pie", reg, con, slm, s)
    assert "needs something to split by" in res.error and "by " in res.error
    assert res.chart is None
    assert s.last_frame.intent == "distribution"                           # the earlier answer is still the current one


def test_trend_with_a_category_becomes_a_proportion_for_a_pie(reg, con):
    s, slm = start(reg, con, TREND_BY, "monthly sales for 2024 by category")
    res = pipeline.ask("show as a pie chart", reg, con, slm, s)
    assert res.error == "" and res.frame.intent == "proportion" and res.chart.type == "donut"


def test_trend_without_a_category_cannot_be_a_pie(reg, con):
    s, slm = start(reg, con, TREND)
    res = pipeline.ask("as a pie", reg, con, slm, s)
    assert "needs something to split by" in res.error


def test_trend_as_bars_keeps_the_dates_on_the_x_axis(reg, con):
    s, slm = start(reg, con, TREND)
    res = pipeline.ask("make it a bar chart", reg, con, slm, s)
    assert res.error == "" and res.chart.type == "bar" and res.frame.intent == "trend"
    enc = res.chart.spec["encoding"]
    assert enc["x"]["type"] == "temporal" and "color" not in enc


def test_trend_by_category_as_bars_colours_by_category(reg, con):
    s, slm = start(reg, con, TREND_BY, "monthly sales for 2024 by category")
    res = pipeline.ask("make it a bar chart", reg, con, slm, s)
    assert res.chart.type == "bar" and res.chart.spec["encoding"]["color"]["field"] == "category"


def test_comparison_as_horizontal_bars(reg, con):
    s, slm = start(reg, con, COMPARE)
    res = pipeline.ask("make it horizontal bars", reg, con, slm, s)
    assert res.error == "" and res.chart.type == "hbar"


def test_comparison_as_a_line_becomes_a_trend_by_category(reg, con):
    s, slm = start(reg, con, COMPARE)
    res = pipeline.ask("make it a line chart", reg, con, slm, s)
    assert res.error == "" and res.frame.intent == "trend" and res.frame.time.column == "order_date"
    assert res.chart.type == "multi_line"


def test_summary_as_a_histogram(reg, con):
    s, slm = start(reg, con, SUMMARY)
    res = pipeline.ask("now a histogram", reg, con, slm, s)
    assert res.error == "" and res.frame.intent == "distribution" and res.chart.type == "histogram"


def test_line_chart_needs_a_date_column(reg, con):
    s, slm = start(reg, con, COMPARE)
    r2 = reg.model_copy(deep=True)
    for c in r2.columns:
        if c.tag == "date":
            c.tag = "ignore"
    res = pipeline.ask("make it a line chart", r2, con, slm, s)
    assert "needs dates" in res.error


def test_chart_word_in_a_new_question(reg, con):
    slm = FakeSLM(COMPARE)
    res = pipeline.ask("sales by category as a pie", reg, con, slm, Session())
    assert res.error == "" and res.chart.type == "donut" and res.chart_forced == "donut"
    asked_text = slm.calls[0][0].text
    assert "pie" not in asked_text and "category" in asked_text


def test_too_many_slices_for_a_pie(reg, con):
    s, slm = start(reg, con, {"intent": "comparison", "metric": M, "dimension": "product_name"}, "compare sales by product name")
    res = pipeline.ask("make it a pie chart", reg, con, slm, s)
    assert "slices" in res.error
