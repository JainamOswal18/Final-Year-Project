"""Validate generated .pbip JSON against Microsoft's published schemas (needs internet).

Usage: python scripts/validate_pbip.py [path/to/project-folder-or-.pbip]
With no argument it generates a sample project per chart type and checks them all.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import json
import sys
import tempfile
from pathlib import Path

import pandas as pd
import requests
from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

from locallens.viz import export_pbi
from locallens.viz.charts import ChartSpec

_cache: dict[str, dict] = {}


def _fetch(uri: str):
    if uri not in _cache:
        r = requests.get(uri, timeout=30)
        r.raise_for_status()
        _cache[uri] = r.json()
    return Resource.from_contents(_cache[uri], default_specification=DRAFT7)


def validate_file(path: Path) -> list[str]:
    doc = json.loads(path.read_text())
    uri = doc.get("$schema")
    if not uri:
        return []
    registry = Registry(retrieve=_fetch)
    schema = _fetch(uri).contents
    v = Draft7Validator(schema, registry=registry)
    return [f"{path.name}: {'/'.join(map(str, e.absolute_path))}: {e.message[:200]}" for e in v.iter_errors(doc)]


def samples(out: Path) -> list[Path]:
    months = pd.date_range("2024-01-01", periods=6, freq="MS")
    cases = {
        "line": pd.DataFrame({"order_month": months, "sum_sales": range(1, 7)}),
        "multi_line": pd.DataFrame({"order_month": list(months) * 2, "category": ["A"] * 6 + ["B"] * 6, "sum_sales": range(12)}),
        "bar": pd.DataFrame({"category": list("ABC"), "sum_sales": [3.0, 2.0, 1.0]}),
        "hbar": pd.DataFrame({"product": list("ABC"), "sum_sales": [3.0, 2.0, 1.0]}),
        "donut": pd.DataFrame({"category": list("ABC"), "sum_sales": [3.0, 2.0, 1.0]}),
        "histogram": pd.DataFrame({"sales": [float(i) for i in range(50)]}),
        "scatter": pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [2.0, 3.0, 5.0]}),
        "kpi": pd.DataFrame({"sum_sales": [12345.6]}),
        "table_bar": pd.DataFrame({"a": ["x", "y"], "b": [1.0, 2.0], "c": [3.0, 4.0]}),
    }
    return [export_pbi.export_powerbi(df, ChartSpec(k, {}, k == "table_bar", ""), f"sample {k}", out) for k, df in cases.items()]


def main() -> int:
    if len(sys.argv) > 1:
        a = Path(sys.argv[1])
        roots = [a.parent if a.suffix == ".pbip" else a]
    else:
        tmp = Path(tempfile.mkdtemp())
        roots = [p.parent for p in samples(tmp)]
    bad = 0
    for root in roots:
        files = [f for f in root.rglob("*") if f.suffix in {".json", ".pbip", ".pbir", ".pbism"} and ".pbi" not in f.parts]
        errs = [e for f in files for e in validate_file(f)]
        print(("FAIL " if errs else "ok   ") + root.name)
        for e in errs:
            print("   ", e)
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
