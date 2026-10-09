"""Dataset registry: tables, column tags, synonyms and join keys.

The registry is the single source of truth for what the model may refer to.
Persisted as JSON so tagging is done once per dataset.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

TAGS = ("metric", "dimension", "date", "ignore")


class Column(BaseModel):
    table: str
    name: str                      # name in the source table
    flat_name: str = ""            # name in the flat view (set by ingest)
    tag: str = "ignore"            # metric | dimension | date | ignore
    synonyms: list[str] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)  # sample values shown to the model
    values: list[str] = Field(default_factory=list)   # all distinct values (low-cardinality dimensions)


class Join(BaseModel):
    left: str
    left_key: str
    right: str
    right_key: str


class Registry(BaseModel):
    name: str = "dataset"
    main_table: str = ""
    tables: dict[str, str] = Field(default_factory=dict)  # table -> file path
    columns: list[Column] = Field(default_factory=list)
    joins: list[Join] = Field(default_factory=list)

    # ---- queries -------------------------------------------------------
    def tagged(self, tag: str) -> list[Column]:
        return [c for c in self.columns if c.tag == tag]

    def by_flat_name(self, flat_name: str) -> Column | None:
        return next((c for c in self.columns if c.flat_name == flat_name), None)

    def phrases(self, flat_name: str) -> list[str]:
        c = self.by_flat_name(flat_name)
        return [] if c is None else [c.flat_name.replace("_", " ").lower(), *[x.lower().strip() for x in c.synonyms]]

    def vocabulary(self) -> dict[str, str]:
        """Every phrase a user might type -> the flat column it means."""
        vocab: dict[str, str] = {}
        for c in self.columns:
            if c.tag == "ignore" or not c.flat_name:
                continue
            vocab[c.flat_name.replace("_", " ").lower()] = c.flat_name
            for s in c.synonyms:
                vocab[s.strip().lower()] = c.flat_name
        return vocab

    # ---- persistence ---------------------------------------------------
    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "Registry":
        return cls.model_validate(json.loads(Path(path).read_text()))
