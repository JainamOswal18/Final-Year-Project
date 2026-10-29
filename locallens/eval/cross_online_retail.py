"""Cross-schema test 1: UCI Online Retail II (CC BY 4.0), a real UK gift-ware wholesaler's invoices, 2009-12 to 2011-12.

A schema the model never saw: spaced column names ("Customer ID"), no profit, revenue is a calculated column
(Quantity x Price), product names in capitals, 43 countries. Data ends 2011-12-09, which is "today" for relative dates.
Used for evaluation only; fetch it with finetune/fetch_external.py. Written by the project developer.

Entry format as eval/heldout4.py: (question, gold frame, expected chart or None[, gold SQL]).
"""
from __future__ import annotations

from pathlib import Path

from locallens.data import ingest
from locallens.data.registry import CALC_TABLE, Column, Measure, Registry, Rule

PARQUET = Path(__file__).resolve().parent.parent / "finetune" / "external" / "uci" / "online_retail_ii.parquet"
DATE = "InvoiceDate"
REV = "revenue"
TAGS: dict[str, set[str]] = {}
QUESTIONS: list[tuple] = []


def registry() -> Registry:
    if not PARQUET.exists():
        raise FileNotFoundError("Run: python -I finetune/fetch_external.py")
    reg = ingest.new_registry_from_files("online_retail", {"sales": str(PARQUET)}, "sales")
    tags = {
        "StockCode": ("dimension", ["stock code", "sku"]), "Description": ("dimension", ["product", "item", "product name"]),
        "Quantity": ("metric", ["quantity", "units", "qty", "pieces"]), "InvoiceDate": ("date", ["date", "invoice date", "order date"]),
        "Price": ("metric", ["price", "unit price"]), "Customer ID": ("dimension", ["customer", "customer id"]),
        "Country": ("dimension", ["country", "market"]),
    }
    for c in reg.columns:
        if c.name in tags:
            c.tag, c.synonyms = tags[c.name][0], list(tags[c.name][1])
    reg.columns.append(Column(table=CALC_TABLE, name=REV, tag="metric", synonyms=["revenue", "sales", "turnover", "sales amount"],
                              description="Quantity times unit price, in pounds", expression='"Quantity" * "Price"'))
    reg.description = "Invoice lines of a UK online gift-ware wholesaler, December 2009 to December 2011. Amounts are in pounds."
    reg.measures = [
        Measure(name="order_count", label="order count", additive=True, expression='COUNT(DISTINCT "Invoice")',
                synonyms=["orders", "number of orders", "invoices"], description="Number of distinct invoices"),
        Measure(name="avg_order_value", label="average order value", format="currency",
                expression='SUM("Quantity" * "Price") / NULLIF(COUNT(DISTINCT "Invoice"), 0)', synonyms=["aov", "basket value"],
                description="Revenue per invoice"),
    ]
    reg.rules = [Rule(name="no_returns", condition="\"Quantity\" > 0 AND \"Invoice\" NOT LIKE 'C%'",
                      description="Leave out cancelled invoices and returns")]
    reg.fiscal_start_month = 1
    return reg


def D(*a, **k):
    return {"column": DATE, "grain": k.get("grain"), "start": a[0] if a else None, "end": a[1] if len(a) > 1 else None}


def M(col, agg="SUM"):
    return {"column": col, "agg": agg}


def Q(question, intent, metric, dim=None, time=None, filters=(), top_n=None, chart=None, tags=(), sql=None):
    f = {"intent": intent, "metric": metric}
    if dim:
        f["dimension"] = dim
    if time:
        f["time"] = time
    if filters:
        f["filters"] = [{"column": c, "op": op, "value": v} for c, op, v in filters]
    if top_n:
        f["top_n"] = top_n
    TAGS[question] = set(tags)
    QUESTIONS.append((question, f, chart, sql) if sql else (question, f, chart))


Y10, Y11 = ("2010-01-01", "2010-12-31"), ("2011-01-01", "2011-12-31")
UK = ("Country", "=", "United Kingdom")

# trend
Q("monthly revenue in 2010", "trend", M(REV), time=D(*Y10, grain="month"))
Q("revenue by month for 2011", "trend", M(REV), time=D(*Y11, grain="month"))
Q("quarterly revenue for 2010", "trend", M(REV), time=D(*Y10, grain="quarter"))
Q("how many units were sold each month in 2011", "trend", M("Quantity"), time=D(*Y11, grain="month"))
Q("weekly revenue in November 2011", "trend", M(REV), time=D("2011-11-01", "2011-11-30", grain="week"))
Q("daily orders in the first week of March 2011", "trend", M("order_count"), time=D("2011-03-01", "2011-03-07", grain="day"))
Q("yearly revenue", "trend", M(REV), time=D(grain="year"))
Q("monthly revenue from Germany in 2011", "trend", M(REV), time=D(*Y11, grain="month"), filters=[("Country", "=", "Germany")])
Q("monthly average order value for 2011", "trend", M("avg_order_value"), time=D(*Y11, grain="month"))
Q("monthly revenue by country in 2010 for France and Germany", "trend", M(REV), dim="Country", time=D(*Y10, grain="month"),
  filters=[("Country", "in", "France,Germany")])
Q("monthly orders for the United Kingdom in 2010", "trend", M("order_count"), time=D(*Y10, grain="month"), filters=[UK])
Q("revenue trend over all months", "trend", M(REV), time=D(grain="month"))
# comparison
Q("revenue by country", "comparison", M(REV), dim="Country")
Q("units sold by country in 2011", "comparison", M("Quantity"), dim="Country", time=D(*Y11))
Q("number of orders by country", "comparison", M("order_count"), dim="Country")
Q("average order value by country", "comparison", M("avg_order_value"), dim="Country")
Q("average unit price by country", "comparison", M("Price", "AVG"), dim="Country")
Q("compare revenue between Germany and France", "comparison", M(REV), dim="Country", filters=[("Country", "in", "Germany,France")])
Q("revenue by product in 2011", "comparison", M(REV), dim="Description", time=D(*Y11))
Q("revenue by market for 2010", "comparison", M(REV), dim="Country", time=D(*Y10))
Q("quantity per customer", "comparison", M("Quantity"), dim="Customer ID")
Q("orders by customer in 2010", "comparison", M("order_count"), dim="Customer ID", time=D(*Y10))
Q("maximum unit price by country", "comparison", M("Price", "MAX"), dim="Country")
Q("units by product for the United Kingdom", "comparison", M("Quantity"), dim="Description", filters=[UK])
# ranking
Q("top 5 countries by revenue", "ranking", M(REV), dim="Country", top_n=5)
Q("top 10 products by revenue", "ranking", M(REV), dim="Description", top_n=10)
Q("top 10 products by units sold in 2011", "ranking", M("Quantity"), dim="Description", time=D(*Y11), top_n=10)
Q("which country has the most orders", "ranking", M("order_count"), dim="Country", top_n=1)
Q("top 5 customers by revenue", "ranking", M(REV), dim="Customer ID", top_n=5)
Q("top 3 countries by average order value", "ranking", M("avg_order_value"), dim="Country", top_n=3)
Q("best selling items in 2010", "ranking", M("Quantity"), dim="Description", time=D(*Y10))
Q("top 5 products by revenue in Germany", "ranking", M(REV), dim="Description", filters=[("Country", "=", "Germany")], top_n=5)
Q("which product sold the most units", "ranking", M("Quantity"), dim="Description", top_n=1)
Q("top 5 stock codes by revenue", "ranking", M(REV), dim="StockCode", top_n=5)
Q("country with the highest revenue last month", "ranking", M(REV), dim="Country", time=D("2011-11-01", "2011-11-30"), top_n=1)
# proportion
Q("share of revenue by country", "proportion", M(REV), dim="Country")
Q("what percentage of orders comes from each country", "proportion", M("order_count"), dim="Country")
Q("share of units by country in 2011", "proportion", M("Quantity"), dim="Country", time=D(*Y11))
# distribution
Q("distribution of unit price", "distribution", M("Price"))
Q("histogram of quantity per line", "distribution", M("Quantity"))
Q("distribution of revenue per line in 2011", "distribution", M(REV), time=D(*Y11))
# summary
Q("total revenue", "summary", M(REV))
Q("total revenue in 2011", "summary", M(REV), time=D(*Y11))
Q("how many units did we sell in 2010", "summary", M("Quantity"), time=D(*Y10))
Q("number of orders in 2011", "summary", M("order_count"), time=D(*Y11))
Q("average order value in 2010", "summary", M("avg_order_value"), time=D(*Y10))
Q("average unit price", "summary", M("Price", "AVG"))
Q("revenue from Germany", "summary", M(REV), filters=[("Country", "=", "Germany")])
Q("units sold in the United Kingdom in 2011", "summary", M("Quantity"), time=D(*Y11), filters=[UK])
Q("revenue last month", "summary", M(REV), time=D("2011-11-01", "2011-11-30"))
Q("highest unit price", "summary", M("Price", "MAX"))
Q("total revenue in the last quarter", "summary", M(REV), time=D("2011-07-01", "2011-09-30"))
Q("orders from France in 2011", "summary", M("order_count"), time=D(*Y11), filters=[("Country", "=", "France")])
Q("revenue in Q4 2010", "summary", M(REV), time=D("2010-10-01", "2010-12-31"))
Q("total turnover in the Netherlands", "summary", M(REV), filters=[("Country", "=", "Netherlands")])
