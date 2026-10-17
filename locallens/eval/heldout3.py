"""THIRD held-out set, written after round 2. Part A uses everyday words the demo's synonym lists do not
contain (to see what matching by meaning adds); part B is plain fresh phrasing. Data ends 2025-12-31."""
from heldout import F, P, S, T, Y23, Y24, Y25, lowest  # noqa: F401
from heldout2 import R

QUESTIONS = [
    # --- A: words outside the synonym lists
    ("takings by shop", {"intent": "comparison", "metric": S(), "dimension": "store_name"}, "bar"),
    ("shop with the highest revenue", {"intent": "ranking", "metric": S(), "dimension": "store_name", "top_n": 1}, "hbar"),
    ("profit per item", {"intent": "comparison", "metric": P(), "dimension": "product_name"}, "table_bar"),
    ("units sold by town", {"intent": "comparison", "metric": S("quantity"), "dimension": "cust_city"}, "bar"),
    ("sales for each outlet", {"intent": "comparison", "metric": S(), "dimension": "store_name"}, "bar"),
    ("top 3 shops by profit", {"intent": "ranking", "metric": P(), "dimension": "store_name", "top_n": 3}, "hbar"),
    ("revenue by shop in 2024", {"intent": "comparison", "metric": S(), "dimension": "store_name", "time": R(Y24)}, "bar"),
    ("number of pieces sold per category", {"intent": "comparison", "metric": S("quantity"), "dimension": "category"}, "bar"),
    ("earnings by month in 2024", {"intent": "trend", "metric": P(), "time": T(Y24)}, "line"),
    ("how much did each town spend", {"intent": "comparison", "metric": S(), "dimension": "cust_city"}, "bar"),
    # --- B: fresh phrasing
    ("What was the total profit in Q3 2024?", {"intent": "summary", "metric": P(), "time": R(("2024-07-01", "2024-09-30"))}, "kpi"),
    ("show me quantity by month for last year", {"intent": "trend", "metric": S("quantity"), "time": T(Y24)}, "line"),
    ("sales for Consumer customers split by category", {"intent": "comparison", "metric": S(), "dimension": "category", "filters": [F("cust_seg", "Consumer")]}, "bar"),
    ("average profit margin per store", {"intent": "comparison", "metric": S("profit_margin"), "dimension": "store_name"}, "bar"),
    ("list the top 4 sub categories by revenue in 2025", {"intent": "ranking", "metric": S(), "dimension": "sub_category", "top_n": 4, "time": R(Y25)}, "hbar"),
    ("how much profit did Delhi generate", {"intent": "summary", "metric": P(), "filters": [F("cust_city", "Delhi")]}, "kpi"),
    ("orders per customer segment in 2024", {"intent": "comparison", "metric": S("order_count"), "dimension": "cust_seg", "time": R(Y24)}, "bar"),
    ("monthly average order value in 2023", {"intent": "trend", "metric": S("avg_order_value"), "time": T(Y23)}, "line"),
    ("share of sales by city", {"intent": "proportion", "metric": S(), "dimension": "cust_city"}, "bar"),
    ("revenue for Corporate customers", {"intent": "summary", "metric": S(), "filters": [F("cust_seg", "Corporate")]}, "kpi"),
    ("distribution of profit for technology", {"intent": "distribution", "metric": P(), "filters": [F("category", "Technology")]}, "histogram"),
    ("yearly revenue by region", {"intent": "trend", "metric": S(), "dimension": "store_region", "time": {"column": "order_date", "grain": "year", "start": None, "end": None}}, "multi_line"),
    ("how many units in the Furniture category last quarter", {"intent": "summary", "metric": S("quantity"), "filters": [F("category", "Furniture")], "time": R(("2025-07-01", "2025-09-30"))}, "kpi"),
    ("bottom 3 stores by sales", {"intent": "ranking", "metric": S(), "dimension": "store_name", "top_n": 3}, "hbar", lowest("store_name", "SUM(sales_amt)", 3)),
    ("weekly sales in October 2025", {"intent": "trend", "metric": S(), "time": T(("2025-10-01", "2025-10-31"), "week")}, "line"),
    ("which city has the highest average order value", {"intent": "ranking", "metric": S("avg_order_value"), "dimension": "cust_city", "top_n": 1}, "hbar"),
    ("total orders", {"intent": "summary", "metric": S("order_count")}, "kpi"),
    ("profit by sub category for Technology", {"intent": "comparison", "metric": P(), "dimension": "sub_category", "filters": [F("category", "Technology")]}, "bar"),
    ("daily quantity in December 2024", {"intent": "trend", "metric": S("quantity"), "time": T(("2024-12-01", "2024-12-31"), "day")}, "line"),
    ("sales by sub category", {"intent": "comparison", "metric": S(), "dimension": "sub_category"}, "bar"),
]
