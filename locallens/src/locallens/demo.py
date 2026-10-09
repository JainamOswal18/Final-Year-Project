"""Preset tags/joins for the synthetic retail dataset (so the demo needs no manual tagging)."""
from __future__ import annotations

from pathlib import Path

from . import ingest
from .registry import Join, Registry

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synthetic"

TAGS = {
    "sales_amt": ("metric", ["sales", "revenue", "turnover"]),
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


def demo_registry(data_dir: Path = DATA_DIR) -> Registry:
    tables = {p.stem: str(p) for p in sorted(data_dir.glob("*.csv"))}
    if "orders" not in tables:
        raise FileNotFoundError(f"No synthetic data in {data_dir}. Run: python scripts/make_synthetic_data.py")
    reg = ingest.new_registry_from_files("retail_demo", tables, "orders")
    reg.joins = list(JOINS)
    return apply_demo_tags(reg)
