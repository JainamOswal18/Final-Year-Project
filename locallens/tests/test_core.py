"""Frame -> SQL -> result -> chart, with hand-written frames (no model)."""
import pytest

from locallens import engine
from locallens.charts import build_spec
from locallens.frame import QueryFrame, build_schema
from locallens.profiler import profile
from locallens.sqlgen import FrameError, build_sql
from locallens.validator import validate_frame, validate_sql


def run(reg, con, frame_dict):
    frame = QueryFrame.model_validate(frame_dict)
    validate_frame(frame, reg)
    sql = build_sql(frame, reg)
    validate_sql(sql, reg)
    df = engine.run(con, sql)
    return frame, sql, df, build_spec(df, frame.intent, profile(df))


M = {"column": "sales_amt", "agg": "SUM"}
T = {"column": "order_date", "grain": "month", "start": "2024-01-01", "end": "2024-12-31"}


def test_trend_by_dimension_is_multi_line(reg, con):
    _, sql, df, chart = run(reg, con, {"intent": "trend", "metric": M, "dimension": "store_region", "time": T})
    assert chart.type == "multi_line" and len(df) == 12 * 4
    assert "date_trunc('month'" in sql


def test_trend_single_series_is_line(reg, con):
    *_, df, chart = run(reg, con, {"intent": "trend", "metric": M, "time": T})
    assert chart.type == "line" and len(df) == 12


def test_comparison_is_bar(reg, con):
    *_, df, chart = run(reg, con, {"intent": "comparison", "metric": M, "dimension": "category"})
    assert chart.type == "bar" and len(df) == 3


def test_ranking_is_sorted_hbar_with_limit(reg, con):
    *_, df, chart = run(reg, con, {"intent": "ranking", "metric": {"column": "profit", "agg": "SUM"},
                                   "dimension": "product_name", "top_n": 5})
    assert chart.type == "hbar" and len(df) == 5
    assert df.iloc[:, 1].is_monotonic_decreasing


def test_proportion_few_categories_is_donut(reg, con):
    *_, chart = run(reg, con, {"intent": "proportion", "metric": M, "dimension": "category"})
    assert chart.type == "donut"


def test_distribution_is_histogram(reg, con):
    *_, df, chart = run(reg, con, {"intent": "distribution", "metric": M})
    assert chart.type == "histogram" and len(df) == 2000


def test_summary_is_kpi(reg, con):
    *_, df, chart = run(reg, con, {"intent": "summary", "metric": M})
    assert chart.type == "kpi" and df.shape == (1, 1)


def test_filter_applied(reg, con):
    f = {"column": "cust_seg", "op": "=", "value": "Consumer"}
    _, sql, df, _ = run(reg, con, {"intent": "summary", "metric": M, "filters": [f]})
    assert "'Consumer'" in sql
    total = con.execute("SELECT SUM(sales_amt) FROM flat").fetchone()[0]
    assert df.iloc[0, 0] < total


def test_filter_value_is_escaped(reg, con):
    f = {"column": "cust_seg", "op": "=", "value": "x'; DROP TABLE orders; --"}
    _, sql, df, _ = run(reg, con, {"intent": "summary", "metric": M, "filters": [f]})
    assert "''" in sql and con.execute("SELECT count(*) FROM orders").fetchone()[0] == 2000


def test_unknown_column_rejected(reg):
    bad = QueryFrame.model_validate({"intent": "summary", "metric": {"column": "revenue_usd", "agg": "SUM"}})
    with pytest.raises(FrameError):
        validate_frame(bad, reg)


def test_trend_without_date_needs_clarification(reg):
    frame = QueryFrame.model_validate({"intent": "trend", "metric": M})
    with pytest.raises(FrameError):
        build_sql(frame, reg)


def test_sql_validator_blocks_foreign_table_and_columns(reg):
    with pytest.raises(FrameError):
        validate_sql("SELECT * FROM orders", reg)
    with pytest.raises(FrameError):
        validate_sql("SELECT secret FROM flat", reg)
    with pytest.raises(FrameError):
        validate_sql("DROP TABLE flat", reg)


def test_schema_only_offers_tagged_columns(reg):
    s = build_schema(reg)
    assert set(s["properties"]["metric"]["properties"]["column"]["enum"]) == {"sales_amt", "profit", "quantity"}
    assert "order_id" not in str(s)
    assert s["properties"]["time"]["anyOf"][0]["properties"]["column"]["enum"] == ["order_date"]
