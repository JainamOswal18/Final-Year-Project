"""Generate a seeded synthetic multi-table retail dataset (star schema).

Column names are deliberately a bit messy (sales_amt, cust_seg) so column tagging
and synonyms actually matter in the app.

Usage: python scripts/make_synthetic_data.py [--out data/synthetic] [--orders 20000]
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42

REGIONS = ["North", "South", "East", "West"]
CATEGORIES = {
    "Furniture": ["Chairs", "Tables", "Bookcases"],
    "Technology": ["Phones", "Laptops", "Accessories"],
    "Office Supplies": ["Paper", "Binders", "Storage"],
}
SEGMENTS = ["Consumer", "Corporate", "Home Office"]
CITIES = {
    "North": ["Delhi", "Chandigarh"],
    "South": ["Chennai", "Bengaluru"],
    "East": ["Kolkata", "Bhubaneswar"],
    "West": ["Mumbai", "Pune"],
}


def build(n_orders: int, seed: int = SEED) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)

    # products
    rows = []
    pid = 1
    for cat, subs in CATEGORIES.items():
        for sub in subs:
            for k in range(1, 6):
                base = {"Furniture": 220, "Technology": 380, "Office Supplies": 35}[cat]
                rows.append(
                    {
                        "product_id": pid,
                        "product_name": f"{sub} {k}",
                        "category": cat,
                        "sub_category": sub,
                        "unit_price": round(base * rng.uniform(0.5, 1.8), 2),
                    }
                )
                pid += 1
    products = pd.DataFrame(rows)

    # stores
    stores = pd.DataFrame(
        [
            {"store_id": i + 1, "store_name": f"{city} Store", "store_region": region}
            for i, (region, city) in enumerate(
                (r, c) for r, cs in CITIES.items() for c in cs
            )
        ]
    )

    # customers
    n_cust = 800
    cust_region = rng.choice(REGIONS, n_cust)
    customers = pd.DataFrame(
        {
            "customer_id": np.arange(1, n_cust + 1),
            "cust_seg": rng.choice(SEGMENTS, n_cust, p=[0.5, 0.3, 0.2]),
            "cust_region": cust_region,
            "cust_city": [rng.choice(CITIES[r]) for r in cust_region],
        }
    )

    # orders: 3 years of dates with mild seasonality (Q4 peak) and growth
    start, end = pd.Timestamp("2023-01-01"), pd.Timestamp("2025-12-31")
    days = pd.date_range(start, end, freq="D")
    month_w = np.array([0.8, 0.8, 0.9, 0.9, 1.0, 1.0, 1.0, 1.0, 1.1, 1.2, 1.4, 1.5])
    year_w = np.array([{2023: 0.8, 2024: 1.0, 2025: 1.25}[d.year] for d in days])
    w = month_w[days.month - 1] * year_w
    order_dates = rng.choice(days, n_orders, p=w / w.sum())
    order_dates.sort()

    prod_idx = rng.integers(0, len(products), n_orders)
    qty = rng.integers(1, 8, n_orders)
    unit = products["unit_price"].to_numpy()[prod_idx]
    discount = rng.choice([0, 0, 0, 0.1, 0.2], n_orders)
    sales = np.round(unit * qty * (1 - discount), 2)
    margin = np.where(
        products["category"].to_numpy()[prod_idx] == "Technology", 0.12, 0.22
    ) - discount * 0.6 + rng.normal(0, 0.04, n_orders)
    profit = np.round(sales * margin, 2)

    orders = pd.DataFrame(
        {
            "order_id": np.arange(1, n_orders + 1),
            "order_date": pd.to_datetime(order_dates).strftime("%Y-%m-%d"),
            "customer_id": rng.integers(1, n_cust + 1, n_orders),
            "product_id": products["product_id"].to_numpy()[prod_idx],
            "store_id": rng.integers(1, len(stores) + 1, n_orders),
            "quantity": qty,
            "sales_amt": sales,
            "profit": profit,
        }
    )
    return {
        "orders": orders,
        "products": products.drop(columns=["unit_price"]),
        "customers": customers,
        "stores": stores,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/synthetic")
    ap.add_argument("--orders", type=int, default=20000)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, df in build(args.orders).items():
        df.to_csv(out / f"{name}.csv", index=False)
        print(f"{name}: {len(df)} rows -> {out / (name + '.csv')}")


if __name__ == "__main__":
    main()
