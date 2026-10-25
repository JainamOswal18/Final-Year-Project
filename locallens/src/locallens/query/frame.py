"""The query frame: the only thing the SLM is allowed to produce.

It is the patent's 'structured intermediate representation' (claim 3). The JSON
schema is built per dataset from the tagged columns, so the model can only pick
column names that exist.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..data.registry import Registry

Intent = Literal["trend", "comparison", "distribution", "proportion", "ranking", "summary"]
INTENTS: tuple[str, ...] = ("trend", "comparison", "distribution", "proportion", "ranking", "summary")
AGGS = ("SUM", "AVG", "COUNT", "MIN", "MAX")
GRAINS = ("day", "week", "month", "quarter", "year")
OPS = ("=", "!=", ">", "<", ">=", "<=", "in")


class Metric(BaseModel):
    column: str
    agg: Literal["SUM", "AVG", "COUNT", "MIN", "MAX"] = "SUM"


class TimeSpec(BaseModel):
    column: str
    grain: Literal["day", "week", "month", "quarter", "year"] | None = None
    start: str | None = None   # ISO date, inclusive
    end: str | None = None     # ISO date, inclusive


class Filter(BaseModel):
    column: str
    op: Literal["=", "!=", ">", "<", ">=", "<=", "in"] = "="
    value: str                 # numbers as strings; 'in' takes comma-separated values


class QueryFrame(BaseModel):
    intent: Intent
    metric: Metric
    dimension: str | None = None
    time: TimeSpec | None = None
    filters: list[Filter] = Field(default_factory=list)
    top_n: int | None = None
    order: Literal["desc", "asc"] = "desc"            # ranking direction; set by rules, never by the model
    ambiguous: list[str] = Field(default_factory=list)  # fields the model was unsure about
    rules: list[str] = Field(default_factory=list)      # business rules applied; set by code, never by the model


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def build_schema(reg: Registry) -> dict:
    """JSON schema (for grammar-constrained decoding) limited to this dataset's columns."""
    metrics = reg.metric_names()
    dims = [c.flat_name for c in reg.tagged("dimension")]
    dates = [c.flat_name for c in reg.tagged("date")]
    filterable = dims + [c.flat_name for c in reg.tagged("metric")]
    props: dict = {
        "intent": {"enum": list(INTENTS)},
        "metric": {
            "type": "object",
            "properties": {"column": {"enum": metrics}, "agg": {"enum": list(AGGS)}},
            "required": ["column", "agg"],
        },
        "dimension": {"enum": dims + [None]} if dims else {"type": "null"},
    }
    if dates:   # same field order as QueryFrame and the prompt's examples: the grammar follows this order
        props["time"] = _nullable(
            {
                "type": "object",
                "properties": {
                    "column": {"enum": dates},
                    "grain": {"enum": list(GRAINS) + [None]},
                    "start": _nullable({"type": "string"}),
                    "end": _nullable({"type": "string"}),
                },
                "required": ["column", "grain", "start", "end"],
            }
        )
    props |= {
        "filters": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "column": {"enum": filterable},
                    "op": {"enum": list(OPS)},
                    "value": {"type": "string"},
                },
                "required": ["column", "op", "value"],
            },
        },
        "top_n": _nullable({"type": "integer"}),
        "ambiguous": {"type": "array", "maxItems": 3, "items": {"enum": ["metric", "dimension", "time", "filters"]}},
    }
    return {"type": "object", "properties": props, "required": list(props)}
