import pytest

import make_synthetic_data
from locallens import ingest
from locallens.demo import JOINS, apply_demo_tags

tag_registry = apply_demo_tags


@pytest.fixture(scope="session")
def reg(tmp_path_factory):
    out = tmp_path_factory.mktemp("syn")
    tables = {}
    for name, df in make_synthetic_data.build(2000).items():
        path = out / f"{name}.csv"
        df.to_csv(path, index=False)
        tables[name] = str(path)
    r = ingest.new_registry_from_files("retail", tables, "orders")
    r.joins = list(JOINS)
    return tag_registry(r)


@pytest.fixture(scope="session")
def con(reg):
    return ingest.prepare(reg)
