"""Dataset registry: tables, column tags, synonyms and join keys.

The registry is the single source of truth for what the model may refer to.
Persisted as JSON so tagging is done once per dataset.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

TAGS = ("metric", "dimension", "date", "ignore")


CALC_TABLE = "_calc"           # Column.table of a user-defined calculated column
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class Column(BaseModel):
    table: str
    name: str                      # name in the source table
    flat_name: str = ""            # name in the flat view (set by ingest)
    tag: str = "ignore"            # metric | dimension | date | ignore
    description: str = ""          # shown to the model and the user
    expression: str = ""           # row-level SQL, only for calculated columns (table == _calc)
    error: str = ""                # why a calculated column is switched off (set on load)
    synonyms: list[str] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)  # sample values shown to the model
    values: list[str] = Field(default_factory=list)   # all distinct values (low-cardinality dimensions)


class Join(BaseModel):
    left: str
    left_key: str
    right: str
    right_key: str


class Measure(BaseModel):
    """A business metric defined as an aggregate expression, e.g. profit margin =
    SUM(profit) / NULLIF(SUM(sales_amt), 0). The model picks it by name like any metric."""
    name: str                                  # identifier, used as the result column name
    expression: str                            # aggregate SQL over flat columns
    label: str = ""
    description: str = ""
    synonyms: list[str] = Field(default_factory=list)
    format: Literal["number", "currency", "percent"] = "number"
    additive: bool = False                     # True: parts sum to the whole (needed for shares)
    error: str = ""                            # why it is switched off (set on load)


class Rule(BaseModel):
    """A business rule that adds a filter. No phrases = always applied ("exclude cancelled
    orders"); with phrases = applied when the question uses one ("active customers")."""
    name: str
    condition: str                             # boolean SQL over flat columns
    phrases: list[str] = Field(default_factory=list)
    description: str = ""
    enabled: bool = True
    error: str = ""


class Example(BaseModel):
    """A verified question and its frame. The closest ones are shown to the model as few-shot examples."""
    question: str
    frame: dict


@dataclass
class Entity:
    """Anything a user can name in a question: a column or a measure."""
    flat_name: str
    tag: str                                   # metric | dimension | date | measure
    synonyms: list[str]


class Registry(BaseModel):
    name: str = "dataset"
    description: str = ""                      # what this data is, in the user's words
    main_table: str = ""
    tables: dict[str, str] = Field(default_factory=dict)  # table -> file path
    columns: list[Column] = Field(default_factory=list)
    joins: list[Join] = Field(default_factory=list)
    fiscal_start_month: int = Field(default=4, ge=1, le=12)   # Indian financial year; saved datasets keep their own value
    measures: list[Measure] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list, exclude=True)  # set on load, not saved

    # ---- queries -------------------------------------------------------
    def by_flat_name(self, flat_name: str) -> Column | None:
        return next((c for c in self.columns if c.flat_name == flat_name), None)

    def active_measures(self) -> list[Measure]:
        return [m for m in self.measures if not m.error]

    def measure(self, name: str) -> Measure | None:
        return next((m for m in self.active_measures() if m.name == name), None)

    def active_rules(self) -> list[Rule]:
        return [r for r in self.rules if r.enabled and not r.error]

    def metric_names(self) -> list[str]:
        """Everything the model may use as the metric: tagged columns plus measures."""
        return [c.flat_name for c in self.tagged("metric")] + [m.name for m in self.active_measures()]

    def tagged(self, tag: str) -> list[Column]:
        return [c for c in self.columns if c.tag == tag and not c.error and c.flat_name]

    def entities(self) -> list[Entity]:
        out = [Entity(c.flat_name, c.tag, c.synonyms) for c in self.columns
               if c.tag != "ignore" and c.flat_name and not c.error]
        out += [Entity(m.name, "measure", [m.label, *m.synonyms] if m.label else m.synonyms)
                for m in self.active_measures()]
        return out

    def phrases(self, flat_name: str) -> list[str]:
        e = next((e for e in self.entities() if e.flat_name == flat_name), None)
        return [] if e is None else [e.flat_name.replace("_", " ").lower(), *[x.lower().strip() for x in e.synonyms if x.strip()]]

    def vocabulary(self) -> dict[str, str]:
        """Every phrase a user might type -> the flat column or measure it means."""
        vocab: dict[str, str] = {}
        for e in self.entities():
            for p in self.phrases(e.flat_name):
                vocab[p] = e.flat_name
        return vocab

    # ---- persistence ---------------------------------------------------
    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "Registry":
        return cls.model_validate(json.loads(Path(path).read_text()))
