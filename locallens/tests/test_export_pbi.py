"""Power BI export: every chart type produces a consistent, self-contained project."""
import json
import re
import zipfile

import pandas as pd
import pytest

from locallens.viz import export_pbi

from locallens.core import pipeline
from locallens.viz.charts import ChartSpec
from tests.test_pipeline import FakeSLM, M

FRAMES = {
    "line": {"intent": "trend", "metric": M, "time": {"column": "order_date", "grain": "month"}},
    "multi_line": {"intent": "trend", "metric": M, "dimension": "category",
                   "time": {"column": "order_date", "grain": "month"}},
    "bar": {"intent": "comparison", "metric": M, "dimension": "category"},
    "hbar": {"intent": "ranking", "metric": M, "dimension": "product_name", "top_n": 5},
    "donut": {"intent": "proportion", "metric": M, "dimension": "category"},
    "histogram": {"intent": "distribution", "metric": M},
    "kpi": {"intent": "summary", "metric": M},
}


QUESTIONS = {
    "line": "monthly sales", "multi_line": "monthly sales by category", "bar": "compare sales by category",
    "hbar": "top 5 products by sales", "donut": "share of sales by category",
    "histogram": "distribution of sales", "kpi": "total sales",
}


def _run(reg, con, chart, tmp_path):
    res = pipeline.ask(QUESTIONS[chart], reg, con, FakeSLM(FRAMES[chart]))
    assert res.error == "" and res.chart.type == chart, (res.error, res.chart and res.chart.type)
    return res, export_pbi.export_powerbi(res.df, res.chart, res.question, tmp_path)


@pytest.mark.parametrize("chart", list(FRAMES))
def test_project_structure_and_references(reg, con, tmp_path, chart):
    res, pbip = _run(reg, con, chart, tmp_path)
    root = pbip.parent
    name = pbip.stem
    assert json.loads(pbip.read_text())["artifacts"][0]["report"]["path"] == f"{name}.Report"
    pbir = json.loads((root / f"{name}.Report" / "definition.pbir").read_text())
    assert (root / f"{name}.Report" / pbir["datasetReference"]["byPath"]["path"]).is_dir()

    tmdl = (root / f"{name}.SemanticModel" / "definition" / "tables" / "Result.tmdl").read_text()
    data = export_pbi.prepare_frame(res.df, chart)
    for c in data.columns:                      # every column is declared in the model
        assert f"sourceColumn: {c}" in tmdl

    visuals = list((root / f"{name}.Report" / "definition" / "pages").glob("*/visuals/*/visual.json"))
    assert visuals
    v = json.loads(visuals[0].read_text())["visual"]
    assert v["visualType"] == export_pbi.VISUAL[chart]
    fields = [p["field"] for r in v["query"]["queryState"].values() for p in r["projections"]]
    assert not any("Aggregation" in x for x in fields)       # the model discourages implicit measures
    columns = {x["Column"]["Property"] for x in fields if "Column" in x}
    measures = {x["Measure"]["Property"] for x in fields if "Measure" in x}
    assert columns <= set(data.columns)         # visuals only reference real columns
    declared = set(re.findall(r"^\tmeasure '?(.+?)'? = SUM", tmdl, re.M))
    assert measures and measures <= declared    # and measures that the model really defines
    for m in declared:
        assert f"Result[{m.removeprefix('Sum of ')}]" in tmdl


def test_data_is_embedded_not_a_path(reg, con, tmp_path):
    _, pbip = _run(reg, con, "line", tmp_path)
    tmdl = next(pbip.parent.rglob("Result.tmdl")).read_text()
    assert "Binary.FromText" in tmdl and "File.Contents" not in tmdl and ":\\" not in tmdl


def test_histogram_is_binned(reg, con, tmp_path):
    res, _ = _run(reg, con, "histogram", tmp_path)
    data = export_pbi.prepare_frame(res.df, "histogram")
    assert list(data.columns)[1] == "count" and len(data) <= 10 and data["count"].sum() == len(res.df)


def test_fallback_adds_table_visual(tmp_path):
    df = pd.DataFrame({"a": ["x", "y"], "b": [1.0, 2.0], "c": [3.0, 4.0]})
    pbip = export_pbi.export_powerbi(df, ChartSpec("table_bar", {}, True, ""), "odd question", tmp_path)
    assert len(list(pbip.parent.rglob("visual.json"))) == 2


def test_scatter_gets_point_id(tmp_path):
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0], "y": [2.0, 4.0, 5.0]})
    pbip = export_pbi.export_powerbi(df, ChartSpec("scatter", {}, False, ""), "x vs y", tmp_path)
    v = json.loads(next(pbip.parent.rglob("visual.json")).read_text())["visual"]
    assert set(v["query"]["queryState"]) == {"Category", "X", "Y"}


def test_empty_result_and_odd_names(tmp_path):
    with pytest.raises(export_pbi.ExportError):
        export_pbi.export_powerbi(pd.DataFrame(), ChartSpec("bar"), "q", tmp_path)
    df = pd.DataFrame({"a": ["x"], "b": [1]})
    pbip = export_pbi.export_powerbi(df, ChartSpec("bar"), 'Sales: "Q1" / 2024?? ../../etc', tmp_path)
    assert tmp_path in pbip.parents and ".." not in pbip.name


def test_zip_contains_whole_project(reg, con, tmp_path):
    _, pbip = _run(reg, con, "bar", tmp_path)
    names = zipfile.ZipFile(__import__("io").BytesIO(export_pbi.zip_project(pbip))).namelist()
    assert any(n.endswith(".pbip") for n in names) and any(n.endswith("Result.tmdl") for n in names)


def test_explicit_measures_replace_implicit_aggregation(tmp_path):
    df = pd.DataFrame({"region": ["a", "b"], "sales amount": [10.5, 20.0], "orders": [3, 4]})
    pbip = export_pbi.export_powerbi(df, ChartSpec("bar"), "sales by region", tmp_path)
    tmdl = next(pbip.parent.rglob("Result.tmdl")).read_text()
    assert "measure 'Sum of sales amount' = SUM(Result[sales amount])" in tmdl
    assert "measure 'Sum of orders' = SUM(Result[orders])" in tmdl and "Sum of region" not in tmdl
    assert "discourageImplicitMeasures" in next(pbip.parent.rglob("model.tmdl")).read_text()
    v = json.loads(next(pbip.parent.rglob("visual.json")).read_text())["visual"]
    y = v["query"]["queryState"]["Y"]["projections"][0]
    assert y["field"]["Measure"]["Property"] == "Sum of sales amount" and y["queryRef"] == "Result.Sum of sales amount"
    assert "Measure" in json.dumps(v["query"]["sortDefinition"])


def test_readme_tells_the_user_where_the_chart_is(tmp_path):
    pbip = export_pbi.export_powerbi(pd.DataFrame({"a": ["x"], "b": [1]}), ChartSpec("bar"), "q", tmp_path)
    assert "Report icon" in (pbip.parent / "README.txt").read_text()
