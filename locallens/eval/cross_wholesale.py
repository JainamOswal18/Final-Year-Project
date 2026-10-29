"""Cross-schema test 2: UCI Wholesale customers (CC BY 4.0): annual spend of 440 customers of a Portuguese wholesaler.

Another unseen schema: six spend columns, two dimensions (Channel, Region), and NO date column, so the model's
schema has no `time` field at all. Used for evaluation only; fetch it with finetune/fetch_external.py.
Written by the project developer. Entry format as eval/heldout4.py.
"""
from __future__ import annotations

from pathlib import Path

from locallens.data import ingest
from locallens.data.registry import Measure, Registry

CSV = Path(__file__).resolve().parent.parent / "finetune" / "external" / "wholesale" / "wholesale.csv"
TAGS: dict[str, set[str]] = {}
QUESTIONS: list[tuple] = []
SPEND = {"Fresh": ["fresh", "fresh food", "fresh products"], "Milk": ["milk", "dairy"], "Grocery": ["grocery", "groceries"],
         "Frozen": ["frozen", "frozen food"], "Detergents_Paper": ["detergents and paper", "detergents", "paper goods", "cleaning"],
         "Delicassen": ["delicatessen", "deli", "delicassen"]}


def registry() -> Registry:
    if not CSV.exists():
        raise FileNotFoundError("Run: python -I finetune/fetch_external.py")
    reg = ingest.new_registry_from_files("wholesale", {"customers": str(CSV)}, "customers")
    for c in reg.columns:
        if c.name in SPEND:
            c.tag, c.synonyms = "metric", list(SPEND[c.name])
        elif c.name == "Channel":
            c.tag, c.synonyms = "dimension", ["channel", "customer type", "sales channel"]
        elif c.name == "Region":
            c.tag, c.synonyms = "dimension", ["region", "area"]
    reg.description = "Annual spend in euros of 440 customers of a wholesaler, by product group. Channel is Horeca (hotels, restaurants, cafes) or Retail."
    reg.measures = [Measure(name="total_spend", label="total spend", expression='SUM("Fresh" + "Milk" + "Grocery" + "Frozen" + "Detergents_Paper" + "Delicassen")',
                            synonyms=["spend", "overall spend", "total purchases"], additive=True, description="All six product groups added up")]
    return reg


def M(col, agg="SUM"):
    return {"column": col, "agg": agg}


def Q(question, intent, metric, dim=None, filters=(), top_n=None, chart=None, tags=()):
    f = {"intent": intent, "metric": metric}
    if dim:
        f["dimension"] = dim
    if filters:
        f["filters"] = [{"column": c, "op": op, "value": v} for c, op, v in filters]
    if top_n:
        f["top_n"] = top_n
    TAGS[question] = set(tags)
    QUESTIONS.append((question, f, chart))


for col, word in [("Fresh", "fresh spend"), ("Milk", "milk spend"), ("Grocery", "grocery spend"), ("Frozen", "frozen spend"),
                  ("Detergents_Paper", "detergents and paper spend"), ("Delicassen", "delicatessen spend")]:
    Q(f"total {word}", "summary", M(col))
Q(f"{'fresh spend'} by channel", "comparison", M("Fresh"), dim="Channel")
Q("milk spend by region", "comparison", M("Milk"), dim="Region")
Q("grocery spend by channel", "comparison", M("Grocery"), dim="Channel")
Q("frozen spend by region", "comparison", M("Frozen"), dim="Region")
Q("detergents and paper spend by channel", "comparison", M("Detergents_Paper"), dim="Channel")
Q("delicatessen spend by region", "comparison", M("Delicassen"), dim="Region")
Q("average fresh spend by channel", "comparison", M("Fresh", "AVG"), dim="Channel")
Q("average grocery spend per region", "comparison", M("Grocery", "AVG"), dim="Region")
Q("total spend by channel", "comparison", M("total_spend"), dim="Channel")
Q("total spend by region", "comparison", M("total_spend"), dim="Region")
Q("average milk spend for Retail customers by region", "comparison", M("Milk", "AVG"), dim="Region", filters=[("Channel", "=", "Retail")])
Q("fresh spend by region for Horeca customers", "comparison", M("Fresh"), dim="Region", filters=[("Channel", "=", "Horeca")])
Q("maximum frozen spend by channel", "comparison", M("Frozen", "MAX"), dim="Channel")
Q("minimum grocery spend by region", "comparison", M("Grocery", "MIN"), dim="Region")
Q("which region spends the most on milk", "ranking", M("Milk"), dim="Region", top_n=1)
Q("which channel spends the most on grocery", "ranking", M("Grocery"), dim="Channel", top_n=1)
Q("rank regions by total spend", "ranking", M("total_spend"), dim="Region")
Q("rank channels by fresh spend", "ranking", M("Fresh"), dim="Channel")
Q("which region spends the least on frozen food", "ranking", M("Frozen"), dim="Region", top_n=1)
Q("share of fresh spend by region", "proportion", M("Fresh"), dim="Region")
Q("share of grocery spend by channel", "proportion", M("Grocery"), dim="Channel")
Q("what percentage of milk spend comes from each region", "proportion", M("Milk"), dim="Region")
Q("share of total spend by region", "proportion", M("total_spend"), dim="Region")
Q("share of frozen spend by channel", "proportion", M("Frozen"), dim="Channel")
Q("distribution of fresh spend", "distribution", M("Fresh"))
Q("histogram of milk spend", "distribution", M("Milk"))
Q("distribution of grocery spend for Retail customers", "distribution", M("Grocery"), filters=[("Channel", "=", "Retail")])
Q("spread of frozen spend", "distribution", M("Frozen"))
Q("total spend for Lisbon", "summary", M("total_spend"), filters=[("Region", "=", "Lisbon")])
Q("fresh spend in Oporto", "summary", M("Fresh"), filters=[("Region", "=", "Oporto")])
Q("grocery spend for Horeca customers", "summary", M("Grocery"), filters=[("Channel", "=", "Horeca")])
Q("average fresh spend", "summary", M("Fresh", "AVG"))
Q("average total spend", "summary", M("total_spend", "AVG"))
Q("highest milk spend", "summary", M("Milk", "MAX"))
Q("lowest delicatessen spend", "summary", M("Delicassen", "MIN"))
Q("frozen spend for Retail customers in Lisbon", "summary", M("Frozen"), filters=[("Channel", "=", "Retail"), ("Region", "=", "Lisbon")])
Q("total detergents and paper spend in the Other region", "summary", M("Detergents_Paper"), filters=[("Region", "=", "Other")])
Q("dairy spend by area", "comparison", M("Milk"), dim="Region", tags=["vocab"])
Q("cleaning spend by customer type", "comparison", M("Detergents_Paper"), dim="Channel", tags=["vocab"])
Q("deli spend by region", "comparison", M("Delicassen"), dim="Region", tags=["vocab"])
Q("top region for groceries", "ranking", M("Grocery"), dim="Region", top_n=1, tags=["vocab"])
Q("fresh spend for Lisbon by channel", "comparison", M("Fresh"), dim="Channel", filters=[("Region", "=", "Lisbon")])
Q("average frozen spend in Oporto", "summary", M("Frozen", "AVG"), filters=[("Region", "=", "Oporto")])
Q("rank regions by delicatessen spend", "ranking", M("Delicassen"), dim="Region")
Q("overall spend of Horeca customers", "summary", M("total_spend"), filters=[("Channel", "=", "Horeca")])
