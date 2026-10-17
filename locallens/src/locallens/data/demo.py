"""Preset tags/joins for the synthetic retail dataset (so the demo needs no manual tagging)."""
from __future__ import annotations

from pathlib import Path

from . import ingest
from .registry import CALC_TABLE, Column, Example, Join, Measure, Registry, Rule

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "synthetic"

TAGS = {
    "sales_amt": ("metric", ["sales", "revenue", "turnover", "order value"]),
    "profit": ("metric", ["profit", "margin", "earnings"]),
    "quantity": ("metric", ["quantity", "units", "qty"]),
    "order_date": ("date", ["date", "order date"]),
    "category": ("dimension", ["category", "product category"]),
    "sub_category": ("dimension", ["sub category", "subcategory"]),
    "product_name": ("dimension", ["product", "item"]),
    "cust_seg": ("dimension", ["segment", "customer segment"]),
    "cust_region": ("dimension", ["customer region"]),
    "cust_city": ("dimension", ["city"]),
    "store_name": ("dimension", ["store"]),
    "store_region": ("dimension", ["region", "store region"]),
}

JOINS = [
    Join(left="orders", left_key="product_id", right="products", right_key="product_id"),
    Join(left="orders", left_key="customer_id", right="customers", right_key="customer_id"),
    Join(left="orders", left_key="store_id", right="stores", right_key="store_id"),
]


def apply_demo_tags(reg: Registry) -> Registry:
    for c in reg.columns:
        if c.name in TAGS:
            c.tag, c.synonyms = TAGS[c.name][0], list(TAGS[c.name][1])
    return reg


def add_semantic(reg: Registry) -> Registry:
    """Business definitions for the demo: what a user would add on the Semantic page."""
    reg.description = ("Retail sales for a multi-store chain: one row per order, 2023 to 2025. "
                       "Amounts are in rupees. Customers belong to a region, stores to a store region.")
    for c in reg.columns:
        c.description = {
            "sales_amt": "Order value after discount",
            "profit": "Profit on the order after costs",
            "cust_region": "Region where the customer lives",
            "store_region": "Region where the store is",
        }.get(c.name, c.description)
    reg.columns.append(Column(
        table=CALC_TABLE, name="order_size", tag="dimension", synonyms=["order size", "basket size"],
        description="Large (1000+), Medium (300-999) or Small order",
        expression="CASE WHEN sales_amt >= 1000 THEN 'Large' WHEN sales_amt >= 300 THEN 'Medium' ELSE 'Small' END"))
    reg.measures = [
        Measure(name="profit_margin", label="profit margin", format="percent",
                expression="SUM(profit) / NULLIF(SUM(sales_amt), 0)",
                synonyms=["margin percent", "margin percentage"],
                description="Profit as a share of sales"),
        Measure(name="avg_order_value", label="average order value", format="currency",
                expression="SUM(sales_amt) / NULLIF(COUNT(DISTINCT order_id), 0)",
                synonyms=["aov", "basket value"], description="Sales per order"),
        Measure(name="order_count", label="order count", additive=True,
                expression="COUNT(DISTINCT order_id)", synonyms=["number of orders", "orders"],
                description="Number of distinct orders"),
    ]
    reg.rules = [
        Rule(name="valid_orders", condition="quantity > 0", description="Ignore rows with no quantity (returns)"),
        Rule(name="high_value", condition="sales_amt >= 1000", phrases=["high value", "high-value", "big orders"],
             description="High-value orders are those of 1000 or more"),
    ]
    reg.examples = [Example(
        question="average order value by store",
        frame={"intent": "comparison", "metric": {"column": "avg_order_value", "agg": "SUM"},
               "dimension": "store_name", "filters": [], "top_n": None, "ambiguous": [], "time": None})]
    return reg


def demo_registry(data_dir: Path = DATA_DIR) -> Registry:
    tables = {p.stem: str(p) for p in sorted(data_dir.glob("*.csv"))}
    if "orders" not in tables:
        raise FileNotFoundError(f"No synthetic data in {data_dir}. Run: python scripts/make_synthetic_data.py")
    reg = ingest.new_registry_from_files("retail_demo", tables, "orders")
    reg.joins = list(JOINS)
    return add_semantic(apply_demo_tags(reg))
