"""BI adapters (patent claim 13): hand the query result and the visualization configuration to an
external BI tool. Power BI is implemented; a Tableau adapter would implement the same protocol.

An adapter turns (result table, chart config, question) into a file the BI tool opens, and never
contacts the tool or any network.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd

from . import export_pbi
from .charts import ChartSpec


@dataclass
class Export:
    filename: str
    mime: str
    content: bytes


class BIAdapter(Protocol):
    key: str
    label: str

    def supports(self, chart_type: str) -> bool: ...

    def export(self, df: pd.DataFrame, chart: ChartSpec, question: str, sort: str = "desc") -> Export: ...


class PowerBIAdapter:
    key = "powerbi"
    label = "Power BI"

    def supports(self, chart_type: str) -> bool:
        return chart_type in export_pbi.VISUAL

    def export(self, df: pd.DataFrame, chart: ChartSpec, question: str, sort: str = "desc") -> Export:
        with tempfile.TemporaryDirectory() as tmp:
            pbip = export_pbi.export_powerbi(df, chart, question, Path(tmp), sort)
            return Export(f"{pbip.stem}.zip", "application/zip", export_pbi.zip_project(pbip))


ADAPTERS: dict[str, BIAdapter] = {a.key: a for a in (PowerBIAdapter(),)}
