"""Gold questions for the synthetic retail demo data.

Each entry: (question, gold frame, expected chart). Relative dates assume the data's latest
date is in Q4 2025, so 'last year' = 2024 and 'last quarter' = Q3 2025 (checked by the harness).
"""
S = lambda col="sales_amt", agg="SUM": {"column": col, "agg": agg}  # noqa: E731
P = lambda: S("profit")  # noqa: E731
Y24 = ("2024-01-01", "2024-12-31")
Y25 = ("2025-01-01", "2025-12-31")
Q325 = ("2025-07-01", "2025-09-30")


def T(rng, grain="month"):
    return {"column": "order_date", "grain": grain, "start": rng[0], "end": rng[1]}


def F(col, val):
    return {"column": col, "op": "=", "value": val}


QUESTIONS = [
    # --- trend
    ("Show monthly sales for 2024", {"intent": "trend", "metric": S(), "time": T(Y24)}, "line"),
    ("Show monthly sales for 2024 by region", {"intent": "trend", "metric": S(), "dimension": "store_region", "time": T(Y24)}, "multi_line"),
    ("Monthly profit in 2025", {"intent": "trend", "metric": P(), "time": T(Y25)}, "line"),
    ("How did revenue change over time in 2023", {"intent": "trend", "metric": S(), "time": T(("2023-01-01", "2023-12-31"))}, "line"),
    ("Quarterly sales for 2025", {"intent": "trend", "metric": S(), "time": T(Y25, "quarter")}, "line"),
    ("Show monthly revenue for Q3 2025", {"intent": "trend", "metric": S(), "time": T(Q325)}, "line"),
    ("Monthly sales trend by category in 2024", {"intent": "trend", "metric": S(), "dimension": "category", "time": T(Y24)}, "multi_line"),
    ("Yearly profit", {"intent": "trend", "metric": P(), "time": T(("2023-01-01", "2025-12-31"), "year")}, "line"),
    # --- comparison
    ("Compare sales by category", {"intent": "comparison", "metric": S(), "dimension": "category"}, "bar"),
    ("Compare profit across regions", {"intent": "comparison", "metric": P(), "dimension": "store_region"}, "bar"),
    ("Sales by customer segment", {"intent": "comparison", "metric": S(), "dimension": "cust_seg"}, "bar"),
    ("Compare revenue by city in 2025", {"intent": "comparison", "metric": S(), "dimension": "cust_city", "time": T(Y25, None)}, "bar"),
    ("Average sales per category", {"intent": "comparison", "metric": S(agg="AVG"), "dimension": "category"}, "bar"),
    ("Compare quantity by sub category", {"intent": "comparison", "metric": S("quantity"), "dimension": "sub_category"}, "bar"),
    ("Compare profit by store", {"intent": "comparison", "metric": P(), "dimension": "store_name"}, "bar"),
    ("Sales by category for consumer customers", {"intent": "comparison", "metric": S(), "dimension": "category", "filters": [F("cust_seg", "Consumer")]}, "bar"),
    ("Compare profit across categories last year", {"intent": "comparison", "metric": P(), "dimension": "category", "time": T(Y24, None)}, "bar"),
    # --- ranking
    ("Top 10 products by revenue", {"intent": "ranking", "metric": S(), "dimension": "product_name", "top_n": 10}, "hbar"),
    ("Top 5 products by profit", {"intent": "ranking", "metric": P(), "dimension": "product_name", "top_n": 5}, "hbar"),
    ("Top 3 sub categories by profit for consumer segment in 2025", {"intent": "ranking", "metric": P(), "dimension": "sub_category", "top_n": 3, "time": T(Y25, None), "filters": [F("cust_seg", "Consumer")]}, "hbar"),
    ("Which city has the highest sales", {"intent": "ranking", "metric": S(), "dimension": "cust_city", "top_n": 1}, "hbar"),
    ("Rank stores by revenue", {"intent": "ranking", "metric": S(), "dimension": "store_name"}, "hbar"),
    ("Top 5 categories by quantity in 2024", {"intent": "ranking", "metric": S("quantity"), "dimension": "category", "top_n": 5, "time": T(Y24, None)}, "hbar"),
    # --- proportion
    ("What share of sales comes from each category", {"intent": "proportion", "metric": S(), "dimension": "category"}, "donut"),
    ("Proportion of profit by customer segment", {"intent": "proportion", "metric": P(), "dimension": "cust_seg"}, "donut"),
    ("What percent of revenue is from each region in 2025", {"intent": "proportion", "metric": S(), "dimension": "store_region", "time": T(Y25, None)}, "donut"),
    ("Share of quantity by sub category", {"intent": "proportion", "metric": S("quantity"), "dimension": "sub_category"}, "bar"),
    # --- distribution
    ("What is the distribution of order sales", {"intent": "distribution", "metric": S()}, "histogram"),
    ("Distribution of profit", {"intent": "distribution", "metric": P()}, "histogram"),
    ("Show the spread of quantity", {"intent": "distribution", "metric": S("quantity")}, "histogram"),
    # --- summary
    ("Total revenue last year", {"intent": "summary", "metric": S(), "time": T(Y24, None)}, "kpi"),
    ("Total sales", {"intent": "summary", "metric": S()}, "kpi"),
    ("What was the total profit in 2025", {"intent": "summary", "metric": P(), "time": T(Y25, None)}, "kpi"),
    ("Average order sales", {"intent": "summary", "metric": S(agg="AVG")}, "kpi"),
    ("Total sales for corporate customers", {"intent": "summary", "metric": S(), "filters": [F("cust_seg", "Corporate")]}, "kpi"),
    ("How many units did we sell in 2024", {"intent": "summary", "metric": S("quantity"), "time": T(Y24, None)}, "kpi"),
    # --- typos / synonyms
    ("compare revnue by categry", {"intent": "comparison", "metric": S(), "dimension": "category"}, "bar"),
    ("show montly turnover for 2024", {"intent": "trend", "metric": S(), "time": T(Y24)}, "line"),
    ("top 5 items by earnings", {"intent": "ranking", "metric": P(), "dimension": "product_name", "top_n": 5}, "hbar"),
    ("total margin for furniture", {"intent": "summary", "metric": P(), "filters": [F("category", "Furniture")]}, "kpi"),
]
