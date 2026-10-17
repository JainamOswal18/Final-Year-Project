"""SECOND held-out set. Written after the round-1 fixes; the first score on it is the honest
generalisation number (see docs/EVAL.md). Same entry format as heldout.py. Data ends 2025-12-31."""
from heldout import F, P, S, T, Y23, Y24, Y25, lowest  # noqa: F401

NONE = {"column": "order_date", "grain": None}


def R(rng, grain=None):
    return {**NONE, "grain": grain, "start": rng[0], "end": rng[1]}


QUESTIONS = [
    # --- trend
    ("Can you show me how sales developed over 2024?", {"intent": "trend", "metric": S(), "time": T(Y24)}, "line"),
    ("Give me profit by quarter for last year", {"intent": "trend", "metric": P(), "time": T(Y24, "quarter")}, "line"),
    ("I'd like to see the revenue curve for 2023", {"intent": "trend", "metric": S(), "time": T(Y23)}, "line"),
    ("units sold each month in Q1 2025", {"intent": "trend", "metric": S("quantity"), "time": T(("2025-01-01", "2025-03-31"))}, "line"),
    ("yearly sales for corporate customers", {"intent": "trend", "metric": S(), "time": {"column": "order_date", "grain": "year", "start": None, "end": None}, "filters": [F("cust_seg", "Corporate")]}, "line"),
    ("weekly profit in December 2025", {"intent": "trend", "metric": P(), "time": T(("2025-12-01", "2025-12-31"), "week")}, "line"),
    ("quarterly sales by category for 2025", {"intent": "trend", "metric": S(), "dimension": "category", "time": T(Y25, "quarter")}, "multi_line"),
    ("daily orders in November 2025", {"intent": "trend", "metric": S("order_count"), "time": T(("2025-11-01", "2025-11-30"), "day")}, "line"),
    ("profit margin by month in 2024", {"intent": "trend", "metric": S("profit_margin"), "time": T(Y24)}, "line"),
    ("monthly revnue 2024 by regon", {"intent": "trend", "metric": S(), "dimension": "store_region", "time": T(Y24)}, "multi_line"),
    # --- comparison
    ("revenue by product category", {"intent": "comparison", "metric": S(), "dimension": "category"}, "bar"),
    ("profit for each store", {"intent": "comparison", "metric": P(), "dimension": "store_name"}, "bar"),
    ("units per customer segment", {"intent": "comparison", "metric": S("quantity"), "dimension": "cust_seg"}, "bar"),
    ("average profit by category", {"intent": "comparison", "metric": S("profit", "AVG"), "dimension": "category"}, "bar"),
    ("average order value across stores", {"intent": "comparison", "metric": S("avg_order_value"), "dimension": "store_name"}, "bar"),
    ("profit margin per sub category", {"intent": "comparison", "metric": S("profit_margin"), "dimension": "sub_category"}, "bar"),
    ("sales in the West store region by category", {"intent": "comparison", "metric": S(), "dimension": "category", "filters": [F("store_region", "West")]}, "bar"),
    ("Total quantity for each city in 2025", {"intent": "comparison", "metric": S("quantity"), "dimension": "cust_city", "time": R(Y25)}, "bar"),
    ("sale by categry", {"intent": "comparison", "metric": S(), "dimension": "category"}, "bar"),
    # --- ranking
    ("top 7 customer cities by profit", {"intent": "ranking", "metric": P(), "dimension": "cust_city", "top_n": 7}, "hbar"),
    ("show me the 3 least profitable categories", {"intent": "ranking", "metric": P(), "dimension": "category", "top_n": 3}, "hbar", lowest("category", "SUM(profit)", 3)),
    ("biggest product by revenue", {"intent": "ranking", "metric": S(), "dimension": "product_name", "top_n": 1}, "hbar"),
    ("which store sold the most units", {"intent": "ranking", "metric": S("quantity"), "dimension": "store_name", "top_n": 1}, "hbar"),
    ("top 5 stores by sales in 2024", {"intent": "ranking", "metric": S(), "dimension": "store_name", "top_n": 5, "time": R(Y24)}, "hbar"),
    ("five best products by profit margin", {"intent": "ranking", "metric": S("profit_margin"), "dimension": "product_name", "top_n": 5}, "hbar"),
    ("TOP 5 PRODUCTS BY PROFIT", {"intent": "ranking", "metric": P(), "dimension": "product_name", "top_n": 5}, "hbar"),
    # --- proportion
    ("what portion of revenue does each category make up", {"intent": "proportion", "metric": S(), "dimension": "category"}, "donut"),
    ("percentage of orders by customer segment", {"intent": "proportion", "metric": S("order_count"), "dimension": "cust_seg"}, "donut"),
    ("share of profit by store region in 2024", {"intent": "proportion", "metric": P(), "dimension": "store_region", "time": R(Y24)}, "donut"),
    ("contribution of each sub category to total sales", {"intent": "proportion", "metric": S(), "dimension": "sub_category"}, "bar"),
    # --- distribution
    ("how are order quantities spread", {"intent": "distribution", "metric": S("quantity")}, "histogram"),
    ("distribution of sales amounts for corporate customers", {"intent": "distribution", "metric": S(), "filters": [F("cust_seg", "Corporate")]}, "histogram"),
    ("profit histogram for 2025", {"intent": "distribution", "metric": P(), "time": R(Y25)}, "histogram"),
    # --- summary
    ("what were total sales in 2025?", {"intent": "summary", "metric": S(), "time": R(Y25)}, "kpi"),
    ("total units sold in Pune", {"intent": "summary", "metric": S("quantity"), "filters": [F("cust_city", "Pune")]}, "kpi"),
    ("what was the profit last quarter", {"intent": "summary", "metric": P(), "time": R(("2025-07-01", "2025-09-30"))}, "kpi"),
    ("number of orders last year", {"intent": "summary", "metric": S("order_count"), "time": R(Y24)}, "kpi"),
    ("average profit margin for technology", {"intent": "summary", "metric": S("profit_margin"), "filters": [F("category", "Technology")]}, "kpi"),
    ("overall sales for large orders in 2025", {"intent": "summary", "metric": S(), "time": R(Y25), "filters": [F("order_size", "Large")]}, "kpi"),
    ("how many orders did Home Office customers place in 2023", {"intent": "summary", "metric": S("order_count"), "time": R(Y23), "filters": [F("cust_seg", "Home Office")]}, "kpi"),
]
