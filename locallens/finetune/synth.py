"""Synthetic retail schemas and questions for fine-tuning data (our own data: no third-party licence applies).

What it makes
  * schemas: random retail datasets, each a Registry with renamed columns, shuffled order, synonyms, value lists,
    sometimes two date columns, sometimes business measures. Nothing needs real data, because the model only ever sees
    the column list, the question and the code's hints.
  * questions: templates x vocabulary for the six intents, aggregation words, filters, relative and Indian financial-year
    dates, top-N, follow-ups, a few "which metric?" cases and Hinglish.
  * the gold frame comes from the template. The prompt is built by the SAME code the app uses (preprocess + build_messages),
    so the hints the model sees in training are the hints it will see in use.

An example is kept only when the app's own preprocessing resolves what the question names (the metric and the group-by
column appear in the code's column hints, no term is ambiguous, a date phrase gives a date range). That is what the
model faces in use; questions the code would have turned into a clarification never reach it.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from datetime import date

from locallens.data.registry import Column, Measure, Registry
from locallens.nlu.preprocess import preprocess
from locallens.nlu.retail_terms import GROUPS
from locallens.nlu.slm import build_messages
from locallens.query.frame import QueryFrame

TABLE = "sales"
FRAME_KEYS = ("intent", "metric", "dimension", "time", "filters", "top_n", "ambiguous")   # the schema's field order

# ----------------------------------------------------------------------------------------------------- vocabulary
METRICS = {
    "sales": dict(names=["sales_amt", "revenue", "net_sales", "amt", "sales_value", "sale_amount", "order_total", "bill_amount",
                         "total_sales", "turnover", "gmv", "Sales Value", "SalesAmt", "net_revenue", "line_total", "invoice_value"],
                  syn=["sales", "revenue", "turnover", "takings", "income", "sales value", "gmv", "order value", "bill value", "net sales"]),
    "profit": dict(names=["profit", "net_profit", "gross_profit", "margin_amt", "earnings", "pnl", "Profit", "profit_amt"],
                   syn=["profit", "earnings", "net profit", "gross profit", "profits"]),
    "quantity": dict(names=["quantity", "qty", "units_sold", "pieces", "unit_count", "items_sold", "Quantity", "qty_sold", "volume"],
                     syn=["quantity", "units", "qty", "pieces", "units sold", "items sold", "volume"]),
    "discount": dict(names=["discount", "disc_amt", "markdown", "discount_amt", "Discount"], syn=["discount", "markdown", "rebate"]),
    "price": dict(names=["mrp", "list_price", "unit_price", "price", "selling_price", "MRP"], syn=["mrp", "price", "list price", "unit price"]),
}
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Hyderabad", "Pune", "Ahmedabad", "Jaipur", "Lucknow", "Surat", "Kochi",
          "Indore", "Nagpur", "Bhopal", "Chandigarh", "Bhubaneswar", "Patna", "Coimbatore", "Vadodara"]
STATES = ["Maharashtra", "Karnataka", "Tamil Nadu", "Gujarat", "Rajasthan", "Kerala", "West Bengal", "Telangana", "Uttar Pradesh", "Punjab", "Odisha"]
CATEGORIES = ["Furniture", "Office Supplies", "Technology", "Groceries", "Apparel", "Footwear", "Electronics", "Home Decor", "Beauty",
              "Toys", "Stationery", "Appliances", "Snacks", "Beverages", "Dairy", "Personal Care", "Sports"]
SUBCATS = ["Phones", "Laptops", "Chairs", "Tables", "Binders", "Paper", "Storage", "T-Shirts", "Jeans", "Sarees", "Rice", "Pulses", "Biscuits",
           "Soaps", "Shampoo", "Mixers", "Lamps", "Headphones", "Notebooks", "Sofas", "Juices", "Cereals", "Sneakers", "Watches"]
BRANDS = ["Samsung", "Apple", "Sony", "Boat", "Nike", "Adidas", "Puma", "Tata", "Amul", "Britannia", "Nestle", "Dabur", "Himalaya", "Godrej",
          "Philips", "Bajaj", "Havells", "Parle", "Fabindia", "Titan"]
SEGMENTS = ["Consumer", "Corporate", "Home Office", "Retail", "Wholesale", "Small Business", "Premium", "Regular"]
CHANNELS = ["Online", "Offline", "Marketplace", "Franchise", "Direct", "Mobile App"]
PAYMENTS = ["UPI", "Card", "Cash", "Wallet", "Net Banking", "COD"]
REGIONS = ["North", "South", "East", "West", "Central", "North East"]

DIMS = {
    "category": dict(names=["category", "product_category", "dept", "department", "Category", "prod_cat", "item_category"],
                     syn=["category", "product category", "department", "categories"], values=CATEGORIES),
    "sub_category": dict(names=["sub_category", "subcategory", "sub_cat", "Sub Category", "product_type", "item_type"],
                         syn=["sub category", "subcategory", "product type", "type"], values=SUBCATS),
    "product": dict(names=["product_name", "item", "item_name", "product", "sku_name", "Product Name", "article"],
                    syn=["product", "item", "sku", "article", "products"], values=None),
    "brand": dict(names=["brand", "brand_name", "Brand", "manufacturer", "make"], syn=["brand", "manufacturer", "brands"], values=BRANDS),
    "store": dict(names=["store_name", "outlet", "shop_name", "branch", "outlet_name", "Store", "store"],
                  syn=["store", "outlet", "shop", "branch", "stores"], values=None),
    "city": dict(names=["cust_city", "city", "town", "customer_city", "City", "ship_city"], syn=["city", "town", "cities"], values=CITIES),
    "state": dict(names=["state", "cust_state", "State", "customer_state", "ship_state"], syn=["state", "states"], values=STATES),
    "region": dict(names=["region", "store_region", "zone", "territory", "Region", "sales_zone"], syn=["region", "zone", "territory", "regions"], values=REGIONS),
    "segment": dict(names=["cust_seg", "segment", "customer_segment", "customer_type", "Segment", "cust_type"],
                    syn=["segment", "customer segment", "customer type", "segments"], values=SEGMENTS),
    "channel": dict(names=["channel", "sales_channel", "Channel", "order_channel", "mode"], syn=["channel", "sales channel", "channels"], values=CHANNELS),
    "payment": dict(names=["payment_mode", "pay_type", "payment_method", "Payment Mode", "pay_mode"],
                    syn=["payment mode", "payment method", "payment type"], values=PAYMENTS),
}
DATES = [("order_date", ["order date", "date"]), ("txn_date", ["transaction date", "date"]), ("invoice_date", ["invoice date", "date"]),
         ("bill_date", ["bill date", "date"]), ("sale_date", ["sale date", "date"]), ("date", ["date"]), ("Order Date", ["order date", "date"]),
         ("order_dt", ["order date", "date"]), ("purchase_date", ["purchase date", "date"])]
SECOND_DATES = [("ship_date", ["ship date", "shipping date"]), ("delivery_date", ["delivery date"]), ("return_date", ["return date"])]
DESCRIPTIONS = [
    "Retail sales for a multi-store chain, one row per order line.", "Point-of-sale transactions from our stores and online shop.",
    "Order lines of an Indian retail business. Amounts are in rupees.", "Sales transactions, one row per bill line. Amounts in INR.",
    "Retail orders with product, customer and store details.", "Sales data of a retail chain. The financial year runs April to March.", ""]
STYLES = ["snake", "snake", "snake", "title", "prefix"]


@dataclass
class Schema:
    reg: Registry
    today: date
    concept: dict = field(default_factory=dict)      # concept -> flat name
    metrics: list[str] = field(default_factory=list)  # flat names usable as metrics (columns and measures)
    dims: list[str] = field(default_factory=list)
    date_col: str = ""
    date2: str = ""
    measures: dict = field(default_factory=dict)     # concept -> measure name
    examples: list = field(default_factory=list)


def _styled(name: str, style: str, rng: random.Random) -> str:
    if style == "title" and "_" in name:
        return " ".join(w.capitalize() for w in name.split("_"))
    if style == "prefix" and name.islower() and " " not in name:
        return f"{rng.choice(['orders', 'sales', 'txn'])}_{name}"
    return name


def make_schema(rng: random.Random, idx: int) -> Schema:
    style = rng.choice(STYLES)
    reg = Registry(name=f"synthetic_{idx}", description=rng.choice(DESCRIPTIONS), main_table=TABLE,
                   fiscal_start_month=4 if rng.random() < 0.85 else 1)
    sc = Schema(reg, today=rng.choice([date(2025, 12, 31), date(2025, 9, 30), date(2026, 3, 31), date(2025, 6, 30), date(2024, 12, 31), date(2025, 11, 15)]))
    used: set[str] = set()

    def add(concept, spec, tag, values=None) -> str:
        for _ in range(10):
            name = _styled(rng.choice(spec["names"]), style, rng)
            if name.lower() not in used:
                break
        else:
            return ""
        used.add(name.lower())
        syn = rng.sample(spec["syn"], k=min(len(spec["syn"]), rng.randint(1, 3)))
        base = {w for w in re.findall(r"[a-z]+", name.lower().replace("_", " "))}
        col = Column(table=TABLE, name=name, flat_name=name, tag=tag, synonyms=syn)
        if rng.random() < 0.4:
            col.description = rng.choice(["", "in rupees", "after discount", "as recorded at billing", "used in reports"]) if tag == "metric" else ""
        if values:
            col.values = list(values)
            col.samples = rng.sample(values, k=min(6, len(values)))
        reg.columns.append(col)
        sc.concept[concept] = name
        return name

    metric_concepts = ["sales"] + [c for c, p in [("profit", .85), ("quantity", .85), ("discount", .3), ("price", .3)] if rng.random() < p]
    for c in metric_concepts:
        n = add(c, METRICS[c], "metric")
        if n:
            sc.metrics.append(n)
    dim_concepts = rng.sample(list(DIMS), k=rng.randint(4, 8))
    for c in dim_concepts:
        spec = DIMS[c]
        values = spec["values"]
        if c == "store":
            cities = rng.sample(CITIES, k=rng.randint(3, 7))
            values = [f"{x} {rng.choice(['Store', 'Outlet'])}" for x in cities]
        elif c == "product":
            subs = rng.sample(SUBCATS, k=3)
            values = [f"{s} {i}" for s in subs for i in range(1, rng.randint(3, 5))]
        else:
            values = rng.sample(values, k=min(len(values), rng.randint(3, 8)))
        n = add(c, spec, "dimension", values)
        if n:
            sc.dims.append(n)
    dname, dsyn = rng.choice(DATES)
    dname = _styled(dname, style, rng)
    used.add(dname.lower())
    reg.columns.append(Column(table=TABLE, name=dname, flat_name=dname, tag="date", synonyms=list(dsyn)))
    sc.date_col = dname
    if rng.random() < 0.15:
        n2, s2 = rng.choice(SECOND_DATES)
        reg.columns.append(Column(table=TABLE, name=n2, flat_name=n2, tag="date", synonyms=list(s2)))
        sc.date2 = n2
    # business measures
    if "profit" in sc.concept and rng.random() < 0.6:
        reg.measures.append(Measure(name="profit_margin", label="profit margin", format="percent", synonyms=["margin percent"],
                                    expression=f'SUM("{sc.concept["profit"]}") / NULLIF(SUM("{sc.concept["sales"]}"), 0)', description="Profit as a share of sales"))
        sc.measures["margin"] = "profit_margin"
    if rng.random() < 0.6:
        reg.measures.append(Measure(name="order_count", label="order count", additive=True, synonyms=["orders", "number of orders"],
                                    expression="COUNT(DISTINCT order_id)", description="Number of distinct orders"))
        sc.measures["orders"] = "order_count"
    if rng.random() < 0.4:
        reg.measures.append(Measure(name="avg_order_value", label="average order value", format="currency", synonyms=["aov", "basket value"],
                                    expression=f'SUM("{sc.concept["sales"]}") / NULLIF(COUNT(DISTINCT order_id), 0)', description="Sales per order"))
        sc.measures["aov"] = "avg_order_value"
    sc.metrics += [m.name for m in reg.measures]
    rng.shuffle(reg.columns)
    return sc


# ---------------------------------------------------------------------------------------------------- phrases
GLOSSARY_EXTRA = {"city": ["town"], "store": ["outlet", "shop", "branch"], "quantity": ["pieces", "units"], "region": ["zone"],
                  "sales": ["revenue", "turnover", "gmv"], "product": ["item", "sku"], "category": ["department"]}


def phrase(sc: Schema, flat: str, rng: random.Random) -> str:
    """A way a user might name this column: its own name, one of its synonyms (what preprocess resolves)."""
    opts = sc.reg.phrases(flat)                     # [the column's own name, then its synonyms]
    if rng.random() < 0.15:                         # a retail word the dataset does not use ("outlet" for a store column)
        alts = [t for g in GROUPS if any(o in g for o in opts) for t in g if t not in opts and " " not in t]
        if alts:
            return rng.choice(sorted(alts))
    return opts[0] if len(opts) == 1 or rng.random() < 0.25 else rng.choice(opts[1:])


def plural(p: str) -> str:
    return p[:-1] + "ies" if p.endswith("y") else p + "s"


DATE_PHRASES = ["in 2024", "for 2025", "in 2023", "last month", "last quarter", "this year", "last year", "this month", "in March 2025", "in January 2024",
                "in Q3 2024", "in Q1 2025", "in the last 6 months", "in the last 30 days", "in FY25", "for FY 2024-25", "in Q2 FY25", "in Q4 FY24",
                "during the last financial year", "in financial year 2023-24", "in October 2025", "in December 2024", "in 2022"]
GRAIN_ADJ = {"month": ["monthly"], "week": ["weekly"], "day": ["daily"], "quarter": ["quarterly"], "year": ["yearly", "annual"]}
GRAIN_PER = {"month": ["by month", "per month", "month by month", "each month"], "week": ["by week", "per week", "each week", "week by week"],
             "day": ["by day", "per day", "each day"], "quarter": ["by quarter", "per quarter", "each quarter"], "year": ["by year", "per year", "each year", "year over year"]}
POLITE = ["", "", "", "show me ", "give me ", "can you show ", "i want to see ", "please show ", "what is ", "tell me "]


def dress(q: str, rng: random.Random) -> str:
    q = q.strip()
    r = rng.random()
    if r < 0.25:
        q = q[0].upper() + q[1:]
    if r > 0.9 and not q.endswith("?"):
        q += "?"
    return q


def time_of(pre, sc: Schema, grain: str | None, use_range: bool = True) -> dict | None:
    h = pre.date_hint
    if not h:
        return None
    col = sc.date_col
    for c in pre.column_hints.values():
        if c == sc.date2:
            col = c
    return {"column": col, "grain": grain, "start": h.start.isoformat() if use_range else None, "end": h.end.isoformat() if use_range else None}


def metric_of(sc: Schema, flat: str, agg: str = "SUM") -> dict:
    return {"column": flat, "agg": "SUM" if flat in {m.name for m in sc.reg.measures} else agg}


def frame(intent, metric, dim=None, time=None, filters=None, top_n=None, ambiguous=None, sc: Schema | None = None) -> dict:
    f = {"intent": intent, "metric": metric, "dimension": dim}
    if sc is None or sc.date_col:
        f["time"] = time
    f |= {"filters": filters or [], "top_n": top_n, "ambiguous": ambiguous or []}
    return f


AGG_WORDS = [("average", "AVG"), ("mean", "AVG"), ("maximum", "MAX"), ("highest single", "MAX"), ("largest single", "MAX"), ("minimum", "MIN"),
             ("lowest single", "MIN"), ("total", "SUM"), ("overall", "SUM"), ("", "SUM"), ("", "SUM"), ("", "SUM"), ("", "SUM")]


@dataclass
class Gen:
    sc: Schema
    rng: random.Random

    # ---- slots
    def metric(self, allow_measures=True):
        pool = [m for m in self.sc.metrics if allow_measures or m in self.sc.concept.values()]
        return self.rng.choice(pool)

    def dim(self, exclude=()):
        pool = [d for d in self.sc.dims if d not in exclude]
        return self.rng.choice(pool) if pool else None

    def filt(self, exclude_dims=()):
        """(phrase fragment, filter dict) for a value of some dimension, or None."""
        dims = [d for d in self.sc.dims if d not in exclude_dims and self.sc.reg.by_flat_name(d).values]
        if not dims:
            return None
        d = self.rng.choice(dims)
        col = self.sc.reg.by_flat_name(d)
        v = self.rng.choice(col.values)
        r = self.rng.random()
        if r < 0.15 and len(col.values) >= 3:
            v2 = self.rng.choice([x for x in col.values if x != v])
            return (f"{v} and {v2}", {"column": d, "op": "in", "value": f"{v},{v2}"}, d)
        if r < 0.25:
            return (f"excluding {v}", {"column": d, "op": "!=", "value": v}, d)
        return (v, {"column": d, "op": "=", "value": v}, d)

    def num_filter(self):
        m = [x for x in self.sc.metrics if x in self.sc.concept.values() and x != self.sc.concept["sales"]]
        if not m:
            m = [self.sc.concept["sales"]]
        col = self.rng.choice(m)
        n = self.rng.choice([5, 10, 50, 100, 500, 1000, 2000])
        word, op = self.rng.choice([("above", ">"), ("over", ">"), ("below", "<"), ("under", "<"), ("at least", ">="), ("more than", ">")])
        return col, word, op, n

    def date(self):
        return self.rng.choice(DATE_PHRASES)

    def agg(self):
        return self.rng.choice(AGG_WORDS)

    # ---- one question
    def make(self, kind: str):
        rng, sc = self.rng, self.sc
        if kind == "trend":
            return self.trend()
        if kind == "comparison":
            return self.comparison()
        if kind == "ranking":
            return self.ranking()
        if kind == "proportion":
            return self.proportion()
        if kind == "distribution":
            return self.distribution()
        if kind == "summary":
            return self.summary()
        if kind == "ambiguous":
            return self.ambiguous()
        if kind == "hinglish":
            return self.hinglish()
        raise ValueError(kind)

    def _mp(self, m: str, agg_word: str) -> str:
        p = phrase(self.sc, m, self.rng)
        return f"{agg_word} {p}".strip()

    def trend(self):
        rng, sc = self.rng, self.sc
        m = self.metric()
        aw, agg = ("", "SUM") if m in {x.name for x in sc.reg.measures} else self.agg()
        grain = rng.choice(["month"] * 5 + ["week", "day", "quarter", "year"])
        has_date = rng.random() < 0.75
        d = self.date() if has_date else ""
        dim = self.dim() if rng.random() < 0.2 else None
        filt = self.filt(exclude_dims=[dim] if dim else ()) if rng.random() < 0.2 else None
        mp = self._mp(m, aw)
        forms = [
            lambda: f"{rng.choice(GRAIN_ADJ[grain])} {mp} {d}",
            lambda: f"{mp} {rng.choice(GRAIN_PER[grain])} {d}",
            lambda: f"how has {mp} changed {rng.choice(GRAIN_PER[grain])} {d}",
            lambda: f"{mp} trend {d}" if grain == "month" else f"{rng.choice(GRAIN_ADJ[grain])} {mp} trend {d}",
            lambda: f"plot {mp} over time {d}" if grain == "month" else f"plot {rng.choice(GRAIN_ADJ[grain])} {mp} {d}",
            lambda: f"{POLITE[rng.randrange(len(POLITE))]}{rng.choice(GRAIN_ADJ[grain])} {mp} {d}",
        ]
        q = rng.choice(forms)()
        if dim:
            q += f" for each {phrase(sc, dim, rng)}" if rng.random() < .5 else f" by {phrase(sc, dim, rng)}"
        if filt:
            q += f" for {filt[0]}" if filt[1]["op"] != "!=" else f" {filt[0]}"
        pre_q = " ".join(q.split())
        return pre_q, dict(kind="trend", m=m, agg=agg, grain=grain, has_date=has_date, dim=dim, filters=[filt[1]] if filt else [], tag="trend")

    def comparison(self):
        rng, sc = self.rng, self.sc
        m = self.metric()
        aw, agg = ("", "SUM") if m in {x.name for x in sc.reg.measures} else self.agg()
        dim = self.dim()
        mp, dp = self._mp(m, aw), phrase(sc, dim, rng)
        filt = self.filt(exclude_dims=[dim]) if rng.random() < 0.3 else None
        d = self.date() if rng.random() < 0.3 else ""
        forms = [f"{mp} by {dp}", f"compare {mp} across {plural(dp)}", f"{mp} for each {dp}", f"{mp} split by {dp}", f"how does {mp} differ by {dp}",
                 f"{mp} per {dp}", f"{dp} level {mp}", f"{POLITE[rng.randrange(len(POLITE))]}{mp} by {dp}", f"break down {mp} by {dp}",
                 f"{mp} of every {dp}", f"{mp} across {plural(dp)}"]
        q = rng.choice(forms)
        if filt:
            q += f" for {filt[0]}" if filt[1]["op"] != "!=" else f" {filt[0]}"
        if d:
            q += f" {d}"
        return " ".join(q.split()), dict(kind="comparison", m=m, agg=agg, dim=dim, has_date=bool(d), filters=[filt[1]] if filt else [], tag="comparison")

    def ranking(self):
        rng, sc = self.rng, self.sc
        m = self.metric()
        dim = self.dim()
        mp, dp = self._mp(m, ""), phrase(sc, dim, rng)
        n = rng.choice([3, 5, 5, 10, 10, 2, 4])
        d = self.date() if rng.random() < 0.3 else ""
        filt = self.filt(exclude_dims=[dim]) if rng.random() < 0.2 else None
        form = rng.choice(["top", "top", "bottom", "best", "which_max", "which_min", "rank", "worst", "most", "n_highest"])
        top_n: int | None = n
        if form == "top":
            q = f"top {n} {plural(dp)} by {mp}"
        elif form == "bottom":
            q = f"bottom {n} {plural(dp)} by {mp}"
        elif form == "best":
            q = f"best {n} {plural(dp)} for {mp}"
        elif form == "worst":
            q = f"worst {n} {plural(dp)} by {mp}"
        elif form == "which_max":
            q, top_n = f"which {dp} has the highest {mp}", 1
        elif form == "which_min":
            q, top_n = f"which {dp} has the lowest {mp}", 1
        elif form == "rank":
            q, top_n = f"rank {plural(dp)} by {mp}", None
        elif form == "most":
            q, top_n = f"{dp} with the most {mp}", 1
        else:
            q = f"{n} {plural(dp)} with the highest {mp}"
        if filt:
            q += f" for {filt[0]}" if filt[1]["op"] != "!=" else f" {filt[0]}"
        if d:
            q += f" {d}"
        return " ".join(q.split()), dict(kind="ranking", m=m, agg="SUM", dim=dim, top_n=top_n, has_date=bool(d), filters=[filt[1]] if filt else [], tag="ranking")

    def proportion(self):
        rng, sc = self.rng, self.sc
        pool = [x for x in sc.metrics if x in sc.concept.values() or x in sc.measures.values() and x == sc.measures.get("orders")]
        m = rng.choice(pool or [sc.concept["sales"]])
        dim = self.dim()
        mp, dp = self._mp(m, ""), phrase(sc, dim, rng)
        d = self.date() if rng.random() < 0.25 else ""
        filt = self.filt(exclude_dims=[dim]) if rng.random() < 0.15 else None
        q = rng.choice([f"share of {mp} by {dp}", f"what percentage of {mp} comes from each {dp}", f"{mp} split across {plural(dp)} as a share",
                        f"proportion of {mp} by {dp}", f"contribution of each {dp} to {mp}", f"how is {mp} divided among {plural(dp)}",
                        f"{dp} share of {mp}", f"percentage of {mp} per {dp}"])
        if filt:
            q += f" for {filt[0]}" if filt[1]["op"] != "!=" else f" {filt[0]}"
        if d:
            q += f" {d}"
        return " ".join(q.split()), dict(kind="proportion", m=m, agg="SUM", dim=dim, has_date=bool(d), filters=[filt[1]] if filt else [], tag="proportion")

    def distribution(self):
        rng, sc = self.rng, self.sc
        m = rng.choice([x for x in sc.metrics if x in sc.concept.values()])
        mp = self._mp(m, "")
        d = self.date() if rng.random() < 0.25 else ""
        filt = self.filt() if rng.random() < 0.2 else None
        q = rng.choice([f"distribution of {mp}", f"histogram of {mp}", f"spread of {mp} per order", f"how is {mp} distributed", f"show the distribution of {mp}",
                        f"{mp} distribution", f"what does the spread of {mp} look like"])
        if filt:
            q += f" for {filt[0]}" if filt[1]["op"] != "!=" else f" {filt[0]}"
        if d:
            q += f" {d}"
        return " ".join(q.split()), dict(kind="distribution", m=m, agg="SUM", has_date=bool(d), filters=[filt[1]] if filt else [], tag="distribution")

    def summary(self):
        rng, sc = self.rng, self.sc
        m = self.metric()
        aw, agg = ("", "SUM") if m in {x.name for x in sc.reg.measures} else self.agg()
        mp = self._mp(m, aw)
        d = self.date() if rng.random() < 0.5 else ""
        filt = self.filt() if rng.random() < 0.45 else None
        numf = None
        if rng.random() < 0.08:
            numf = self.num_filter()
        base = rng.choice([f"{mp}", f"total {mp}" if not aw else f"{mp}", f"how much {mp}" if not aw else f"what is the {mp}", f"what was our {mp}",
                           f"{mp} overall" if not d else f"{mp}", f"what is the {mp}"])
        q = base
        filters = []
        if filt:
            q += f" for {filt[0]}" if filt[1]["op"] != "!=" else f" {filt[0]}"
            filters.append(filt[1])
        if numf:
            col, word, op, n = numf
            q += f" for orders with {phrase(sc, col, rng)} {word} {n}"
            filters.append({"column": col, "op": op, "value": str(n)})
        if d:
            q += f" {d}"
        return " ".join(q.split()), dict(kind="summary", m=m, agg=agg, has_date=bool(d), filters=filters, tag="summary")

    def ambiguous(self):
        """No metric named, or a comparison with nothing to compare by: the right output says what is unclear."""
        rng, sc = self.rng, self.sc
        dim = self.dim()
        dp = phrase(sc, dim, rng)
        if rng.random() < 0.6:
            q = rng.choice([f"show the breakdown by {dp}", f"give me a split by {dp}", f"compare {plural(dp)}", f"how do the {plural(dp)} compare"])
            return q, dict(kind="ambiguous", m=sc.concept["sales"], agg="SUM", dim=dim, amb=["metric"], has_date=False, filters=[], tag="ambiguous", intent="comparison")
        m = self.metric()
        q = rng.choice([f"compare {self._mp(m, '')}", f"{self._mp(m, '')} comparison"])
        return q, dict(kind="ambiguous", m=m, agg="SUM", dim=None, amb=["dimension"], has_date=False, filters=[], tag="ambiguous", intent="comparison")

    def hinglish(self):
        rng, sc = self.rng, self.sc
        m = self.metric(allow_measures=False)
        mp = phrase(sc, m, rng)
        dim = self.dim()
        dp = phrase(sc, dim, rng)
        hd = rng.choice(["pichle mahine", "is saal", "pichle saal", "pichli quarter", "2024 mein", "2025 mein"])
        form = rng.choice(["wise", "hisab", "total", "kitna", "sabse", "trend", "share"])
        n = rng.choice([3, 5, 10])
        if form == "wise":
            q, info = rng.choice([f"{dp} wise {mp}", f"{dp} wise {mp} dikhao", f"{mp} {dp} wise batao"]), dict(kind="comparison", dim=dim)
        elif form == "hisab":
            q, info = f"{dp} ke hisab se {mp}", dict(kind="comparison", dim=dim)
        elif form == "total":
            q, info = rng.choice([f"{hd} ka {mp}", f"{hd} ka total {mp}"]), dict(kind="summary")
        elif form == "kitna":
            q, info = f"{mp} kitna hua {hd}", dict(kind="summary")
        elif form == "sabse":
            hi, top = rng.choice([("zyada", 1), ("kam", 1)])
            q, info = f"sabse {hi} {mp} wala {dp}", dict(kind="ranking", dim=dim, top_n=1)
        elif form == "trend":
            q, info = rng.choice([f"{mp} month wise {hd}", f"mahine ke hisab se {mp} {hd}", f"har mahine ka {mp}"]), dict(kind="trend", grain="month")
        else:
            q, info = f"{dp} ka {mp} share", dict(kind="proportion", dim=dim)
        has_date = any(w in q for w in ("pichle", "is saal", "pichli", "mein"))
        if info["kind"] == "ranking":
            info["top_n"] = 1
        return q, dict(m=m, agg="SUM", has_date=has_date, filters=[], tag="hinglish", **info)


# --------------------------------------------------------------------------------------------- frames from info
def build_frame(sc: Schema, info: dict, pre) -> dict | None:
    kind = info["kind"]
    metric = metric_of(sc, info["m"], info.get("agg", "SUM"))
    dim = info.get("dim")
    flt = info.get("filters", [])
    grain = info.get("grain")
    t = None
    if kind == "trend":
        if info.get("has_date"):
            if not pre.date_hint:
                return None
            hint_grain = pre.date_hint.grain
            t = time_of(pre, sc, grain if grain != "month" or True else hint_grain)
        else:
            t = {"column": sc.date_col, "grain": grain, "start": None, "end": None}
        return frame("trend", metric, dim, t, flt, None, None, sc)
    if info.get("has_date"):
        if not pre.date_hint:
            return None
        t = time_of(pre, sc, None)
    intent = info.get("intent", kind)
    return frame(intent, metric, dim if intent in ("comparison", "ranking", "proportion") else None, t, flt, info.get("top_n"),
                 info.get("amb"), sc)


def resolves(sc: Schema, pre, info: dict) -> bool:
    """Would the app hand this question to the model with the metric and group-by already pointed out by its hints?"""
    if pre.ambiguous_terms:
        return False
    hinted = set(pre.column_hints.values())
    if info["m"] not in hinted and info["kind"] != "ambiguous":
        return False
    if info.get("dim") and info["dim"] not in hinted and info["kind"] != "ambiguous":
        return False
    for f in info.get("filters", []):
        if f["op"] in ("=", "!=", "in") and not any(c == f["column"] for c, _ in pre.value_mentions):
            return False
    return True


def verified_examples(gen: Gen, n: int) -> list[dict]:
    """A few saved questions of this dataset, as a user's 'verified examples' (shown to the model when similar)."""
    out = []
    for _ in range(n * 4):
        if len(out) >= n:
            break
        kind = gen.rng.choice(["comparison", "summary", "ranking", "trend"])
        q, info = gen.make(kind)
        pre = preprocess(q, gen.sc.reg, gen.sc.today)
        if not resolves(gen.sc, pre, info):
            continue
        fr = build_frame(gen.sc, info, pre)
        if fr:
            out.append({"question": q, "frame": fr})
    return out


# ---------------------------------------------------------------------------------------------------- follow-ups
def followup(gen: Gen, prev_frame: dict):
    """(follow-up text, new gold frame) that changes the previous frame the way a user would."""
    rng, sc = gen.rng, gen.sc
    prev = json.loads(json.dumps(prev_frame))
    kinds = ["filter", "time", "dim", "metric", "agg", "topn", "grain"]
    rng.shuffle(kinds)
    for k in kinds:
        new = json.loads(json.dumps(prev))
        if k == "filter":
            f = gen.filt(exclude_dims=[prev.get("dimension")] if prev.get("dimension") else ())
            if not f or f[1]["op"] != "=":
                continue
            new["filters"] = [x for x in new["filters"] if x["column"] != f[1]["column"]] + [f[1]]
            return rng.choice([f"now only {f[0]}", f"just {f[0]}", f"for {f[0]} only", f"only {f[0]}", f"and for {f[0]}"]), new, {"v": f[1]["value"]}
        if k == "time" and sc.date_col:
            d = rng.choice(["2024", "2025", "2023", "last month", "last quarter", "last year", "this year", "Q3 2024", "FY25", "Q1 FY25"])
            pre = preprocess(d, sc.reg, sc.today)
            if not pre.date_hint:
                continue
            col = prev["time"]["column"] if prev.get("time") else sc.date_col
            grain = prev["time"]["grain"] if prev.get("time") else None
            new["time"] = {"column": col, "grain": grain, "start": pre.date_hint.start.isoformat(), "end": pre.date_hint.end.isoformat()}
            return rng.choice([f"only {d}", f"and for {d}", f"what about {d}", f"same for {d}", f"now for {d}", f"limit it to {d}"]), new, {"date": d}
        if k == "dim":
            dim = gen.dim(exclude=[prev.get("dimension")] if prev.get("dimension") else ())
            if not dim or prev["intent"] in ("distribution",):
                continue
            dp = phrase(sc, dim, rng)
            new["dimension"] = dim
            if prev["intent"] == "summary":
                new["intent"] = "comparison"
            return rng.choice([f"split it by {dp}", f"now by {dp}", f"break it down by {dp}", f"by {dp} instead", f"show it per {dp}"]), new, {"dp": dp}
        if k == "metric":
            m2 = gen.metric()
            if m2 == prev["metric"]["column"]:
                continue
            new["metric"] = metric_of(sc, m2, prev["metric"]["agg"])
            return rng.choice([f"what about {phrase(sc, m2, rng)}", f"now the {phrase(sc, m2, rng)}", f"show {phrase(sc, m2, rng)} instead", f"and {phrase(sc, m2, rng)}"]), new, {"m": m2}
        if k == "agg":
            if prev["metric"]["column"] in {m.name for m in sc.reg.measures}:
                continue
            word, agg = rng.choice([("the average", "AVG"), ("average instead", "AVG"), ("the maximum", "MAX"), ("the minimum", "MIN"), ("the total instead", "SUM")])
            if prev["metric"]["agg"] == agg:
                continue
            new["metric"] = {"column": prev["metric"]["column"], "agg": agg}
            return rng.choice([f"now {word}", f"use {word}", f"what about {word}"]), new, {}
        if k == "topn":
            if not prev.get("dimension") or prev["intent"] == "trend":
                continue
            n = rng.choice([3, 5, 10])
            new["intent"], new["top_n"] = "ranking", n
            return rng.choice([f"show only the top {n}", f"top {n} only", f"just the top {n}"]), new, {}
        if k == "grain":
            if prev["intent"] != "trend" or not prev.get("time"):
                continue
            g = rng.choice(["quarter", "week", "month", "year"])
            if g == prev["time"]["grain"]:
                continue
            new["time"]["grain"] = g
            return rng.choice([f"make it {GRAIN_ADJ[g][0]}", f"{GRAIN_PER[g][0]} instead", f"switch to {GRAIN_ADJ[g][0]}"]), new, {}
    return None


# --------------------------------------------------------------------------------------------------- examples
def target_json(fr: dict, sc: Schema) -> str:
    """The answer exactly as the app's own few-shot examples are written (json.dumps, schema field order)."""
    keys = [k for k in FRAME_KEYS if k != "time" or sc.date_col]
    return json.dumps({k: fr[k] for k in keys})


def norm(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", q.lower()).strip()


def fits_schema(fr: dict, sc: Schema) -> bool:
    """The answer must be something the app's constrained decoder could produce for this dataset."""
    reg = sc.reg
    metrics = set(reg.metric_names())
    dims = {c.flat_name for c in reg.tagged("dimension")}
    dates = {c.flat_name for c in reg.tagged("date")}
    filterable = dims | {c.flat_name for c in reg.tagged("metric")}
    if fr["metric"]["column"] not in metrics or (fr["dimension"] is not None and fr["dimension"] not in dims):
        return False
    if fr.get("time") and fr["time"]["column"] not in dates:
        return False
    if len(fr["filters"]) > 3 or any(f["column"] not in filterable for f in fr["filters"]):
        return False
    return all(x in ("metric", "dimension", "time", "filters") for x in fr["ambiguous"])


def make_example(sc: Schema, question: str, fr: dict, prev: dict | None, style: str, meta: dict) -> dict | None:
    if not fits_schema(fr, sc):
        return None
    pre = preprocess(question, sc.reg, sc.today)
    prev_frame = QueryFrame.model_validate(prev) if prev is not None else None
    try:
        QueryFrame.model_validate(fr)
    except Exception:
        return None
    messages = build_messages(pre, sc.reg, prev_frame, style)
    messages.append({"role": "assistant", "content": target_json(fr, sc)})
    return {"messages": messages, "meta": {**meta, "style": style, "question": question}}
