"""HELD-OUT questions for the synthetic retail demo.

Written in one sitting AFTER the rules were tuned, in the way a colleague would actually ask,
and never used to tune anything. The first score on this set is the honest accuracy number.
(After that, failures here may be fixed; keep the first score in docs/EVAL.md.)

Entry: (question, gold frame, expected chart[, gold SQL]). A gold SQL is used where the frame
cannot express the answer (e.g. 'lowest' needs ascending order).
Relative dates assume the data ends 2025-12-31.
"""
S = lambda col="sales_amt", agg="SUM": {"column": col, "agg": agg}  # noqa: E731
P = lambda: S("profit")  # noqa: E731
Y23, Y24, Y25 = ("2023-01-01", "2023-12-31"), ("2024-01-01", "2024-12-31"), ("2025-01-01", "2025-12-31")


def T(rng, grain="month"):
    return {"column": "order_date", "grain": grain, "start": rng[0], "end": rng[1]}


def F(col, val):
    return {"column": col, "op": "=", "value": val}


def lowest(dim, metric_expr, n):
    return (f'SELECT "{dim}", {metric_expr} AS v FROM flat WHERE (quantity > 0) GROUP BY 1 ORDER BY v ASC, 1 LIMIT {n}')


QUESTIONS = [
    # --- trend
    ("How have sales moved month by month in 2025?", {"intent": "trend", "metric": S(), "time": T(Y25)}, "line"),
    ("profit per quarter 2024", {"intent": "trend", "metric": P(), "time": T(Y24, "quarter")}, "line"),
    ("Revenue trend over the last 12 months", {"intent": "trend", "metric": S(), "time": T(("2025-01-05", "2025-12-31"))}, "line"),
    ("weekly units sold in Q4 2024", {"intent": "trend", "metric": S("quantity"), "time": T(("2024-10-01", "2024-12-31"), "week")}, "line"),
    ("Show me the sales trend for each category during 2024", {"intent": "trend", "metric": S(), "dimension": "category", "time": T(Y24)}, "multi_line"),
    ("daily sales last month", {"intent": "trend", "metric": S(), "time": T(("2025-11-01", "2025-11-30"), "day")}, "line"),
    ("how is profit growing year over year", {"intent": "trend", "metric": P(), "time": {"column": "order_date", "grain": "year", "start": None, "end": None}}, "line"),
    ("monthly average order value for 2025", {"intent": "trend", "metric": S("avg_order_value"), "time": T(Y25)}, "line"),
    ("Plot sales by month across all years", {"intent": "trend", "metric": S(), "time": {"column": "order_date", "grain": "month", "start": None, "end": None}}, "line"),
    ("quarterly profit margin by store region in 2025", {"intent": "trend", "metric": S("profit_margin"), "dimension": "store_region", "time": T(Y25, "quarter")}, "multi_line"),
    ("What were the sales in 2024 for the Technology category by month", {"intent": "trend", "metric": S(), "time": T(Y24), "filters": [F("category", "Technology")]}, "line"),
    ("montly proft for 2025", {"intent": "trend", "metric": P(), "time": T(Y25)}, "line"),
    # --- comparison
    ("Compare profit across customer segments", {"intent": "comparison", "metric": P(), "dimension": "cust_seg"}, "bar"),
    ("sales by store", {"intent": "comparison", "metric": S(), "dimension": "store_name"}, "bar"),
    ("How do the regions stack up on revenue?", {"intent": "comparison", "metric": S(), "dimension": "store_region"}, "bar"),
    ("units sold per sub category", {"intent": "comparison", "metric": S("quantity"), "dimension": "sub_category"}, "bar"),
    ("average sales by customer segment", {"intent": "comparison", "metric": S("sales_amt", "AVG"), "dimension": "cust_seg"}, "bar"),
    ("sales per city", {"intent": "comparison", "metric": S(), "dimension": "cust_city"}, "bar"),
    ("profit by category in 2024", {"intent": "comparison", "metric": P(), "dimension": "category", "time": {"column": "order_date", "grain": None, "start": Y24[0], "end": Y24[1]}}, "bar"),
    ("compare revenue across order sizes", {"intent": "comparison", "metric": S(), "dimension": "order_size"}, "bar"),
    ("average order value by customer segment", {"intent": "comparison", "metric": S("avg_order_value"), "dimension": "cust_seg"}, "bar"),
    ("profits of Consumer segment by region", {"intent": "comparison", "metric": P(), "dimension": "store_region", "filters": [F("cust_seg", "Consumer")]}, "bar"),
    ("sales by sub-category", {"intent": "comparison", "metric": S(), "dimension": "sub_category"}, "bar"),
    # --- ranking
    ("top 3 stores by profit", {"intent": "ranking", "metric": P(), "dimension": "store_name", "top_n": 3}, "hbar"),
    ("best selling products by units", {"intent": "ranking", "metric": S("quantity"), "dimension": "product_name"}, "hbar"),
    ("which category has the lowest sales", {"intent": "ranking", "metric": S(), "dimension": "category", "top_n": 1}, "hbar", lowest("category", "SUM(sales_amt)", 1)),
    ("top 10 cities by revenue", {"intent": "ranking", "metric": S(), "dimension": "cust_city", "top_n": 10}, "hbar"),
    ("5 most profitable products", {"intent": "ranking", "metric": P(), "dimension": "product_name", "top_n": 5}, "hbar"),
    ("highest revenue store", {"intent": "ranking", "metric": S(), "dimension": "store_name", "top_n": 1}, "hbar"),
    ("rank customer segments by profit", {"intent": "ranking", "metric": P(), "dimension": "cust_seg"}, "hbar"),
    ("bottom 5 sub categories by profit", {"intent": "ranking", "metric": P(), "dimension": "sub_category", "top_n": 5}, "hbar", lowest("sub_category", "SUM(profit)", 5)),
    ("top 5 products in the Furniture category by sales", {"intent": "ranking", "metric": S(), "dimension": "product_name", "top_n": 5, "filters": [F("category", "Furniture")]}, "hbar"),
    # --- proportion
    ("what percentage of profit comes from each segment", {"intent": "proportion", "metric": P(), "dimension": "cust_seg"}, "donut"),
    ("split of sales across store regions", {"intent": "proportion", "metric": S(), "dimension": "store_region"}, "donut"),
    ("category share of units sold", {"intent": "proportion", "metric": S("quantity"), "dimension": "category"}, "donut"),
    ("share of orders by order size", {"intent": "proportion", "metric": S("order_count"), "dimension": "order_size"}, "donut"),
    ("how much of total revenue is each city responsible for", {"intent": "proportion", "metric": S(), "dimension": "cust_city"}, "bar"),
    # --- distribution
    ("distribution of order values", {"intent": "distribution", "metric": S()}, "histogram"),
    ("spread of quantity per order", {"intent": "distribution", "metric": S("quantity")}, "histogram"),
    ("histogram of profit", {"intent": "distribution", "metric": P()}, "histogram"),
    ("how are profits distributed in 2024", {"intent": "distribution", "metric": P(), "time": {"column": "order_date", "grain": None, "start": Y24[0], "end": Y24[1]}}, "histogram"),
    # --- summary
    ("what is our total revenue", {"intent": "summary", "metric": S()}, "kpi"),
    ("total profit last year", {"intent": "summary", "metric": P(), "time": {"column": "order_date", "grain": None, "start": Y24[0], "end": Y24[1]}}, "kpi"),
    ("how many units did consumers buy in 2025", {"intent": "summary", "metric": S("quantity"), "time": {"column": "order_date", "grain": None, "start": Y25[0], "end": Y25[1]}, "filters": [F("cust_seg", "Consumer")]}, "kpi"),
    ("overall profit margin", {"intent": "summary", "metric": S("profit_margin")}, "kpi"),
    ("average order value this year", {"intent": "summary", "metric": S("avg_order_value"), "time": {"column": "order_date", "grain": None, "start": Y25[0], "end": Y25[1]}}, "kpi"),
    ("number of orders in Q2 2024", {"intent": "summary", "metric": S("order_count"), "time": {"column": "order_date", "grain": None, "start": "2024-04-01", "end": "2024-06-30"}}, "kpi"),
    ("total sales in Mumbai", {"intent": "summary", "metric": S(), "filters": [F("cust_city", "Mumbai")]}, "kpi"),
    ("total furniture sales", {"intent": "summary", "metric": S(), "filters": [F("category", "Furniture")]}, "kpi"),
    ("sales for home office customers in 2023", {"intent": "summary", "metric": S(), "time": {"column": "order_date", "grain": None, "start": Y23[0], "end": Y23[1]}, "filters": [F("cust_seg", "Home Office")]}, "kpi"),
]
