"""Upload preparation: cleaning, type guessing, fact-table and join detection."""
import pandas as pd
import pytest

from locallens.data import autoprep, ingest


def test_column_names_become_safe_identifiers():
    df = autoprep.clean_frame(pd.DataFrame({"Sales Amount ($)": [1], "Order-Date": ["2024-01-01"], "a": [1], "A": [2], "9lives": [1]}))
    assert list(df.columns) == ["sales_amount", "order_date", "a", "a_2", "c_9lives"]


def test_dates_numbers_and_blanks_are_detected_in_text_columns():
    df = autoprep.clean_frame(pd.DataFrame({"d": ["2024-01-05", "2024-02-10", "2024-03-01", ""], "n": ["1", "2.5", "3", "4"],
                                            "t": [" a ", "b", "", "c"], "mixed": ["x", "2024-01-01", "y", "z"]}))
    assert pd.api.types.is_datetime64_any_dtype(df["d"]) and pd.api.types.is_numeric_dtype(df["n"])
    assert df["t"].tolist()[0] == "a" and pd.isna(df["t"].tolist()[2])
    assert not pd.api.types.is_datetime64_any_dtype(df["mixed"])


def test_tag_guesses():
    n = 1000
    rng = pd.Series(range(n))
    cases = {
        "order_id": (rng, "ignore"), "sales_amt": (rng * 1.5, "metric"), "quantity": (rng % 7 + 1, "metric"),
        "rating": (rng % 5 + 1, "dimension"), "region": (pd.Series(["N", "S", "E", "W"] * 250), "dimension"),
        "comment": (pd.Series([f"free text {i}" for i in range(n)]), "ignore"),
        "when": (pd.to_datetime("2024-01-01") + pd.to_timedelta(rng, "D"), "date"),
        "flag": (pd.Series([True, False] * 500), "dimension"),
    }
    for name, (s, want) in cases.items():
        assert autoprep.guess_tag(name, s, n) == want, name


def test_fact_table_is_found_by_its_keys_not_its_size():
    frames = {"customers": pd.DataFrame({"customer_id": range(800), "seg": ["a"] * 800}),
              "orders": pd.DataFrame({"order_id": range(100), "customer_id": [i % 50 for i in range(100)], "amt": range(100)})}
    assert autoprep.pick_main(frames) == "orders"
    assert [(j.left, j.left_key, j.right) for j in autoprep.suggest_joins(frames, "orders")] == [("orders", "customer_id", "customers")]


def test_id_to_plural_table_join():
    frames = {"sales": pd.DataFrame({"region_id": [1, 2, 1, 1], "amount": [1.0, 2.0, 3.0, 4.0]}),
              "regions": pd.DataFrame({"id": [1, 2], "name": ["N", "S"]})}
    main = autoprep.pick_main(frames)
    j = autoprep.suggest_joins(frames, main)
    assert main == "sales" and (j[0].left_key, j[0].right, j[0].right_key) == ("region_id", "regions", "id")


def test_columns_of_an_unjoined_table_are_unavailable_not_fatal(tmp_path):
    a, b = tmp_path / "a.parquet", tmp_path / "b.parquet"
    pd.DataFrame({"x": [1, 2, 3], "g": ["u", "v", "u"]}).to_parquet(a)
    pd.DataFrame({"y": [5, 6], "h": ["p", "q"]}).to_parquet(b)
    reg = autoprep.build_registry("t", {"a": pd.read_parquet(a), "b": pd.read_parquet(b)}, {"a": str(a), "b": str(b)})
    assert all(c.tag == "ignore" for c in reg.columns if c.table != reg.main_table)
    for c in reg.columns:                       # even if the user tags them anyway
        c.tag = "dimension" if c.name in ("g", "h") else c.tag
    con = ingest.prepare(reg)
    dims = {c.name for c in reg.tagged("dimension")}
    assert "g" in dims and "h" not in dims and "h" not in [r[0] for r in con.execute("DESCRIBE flat").fetchall()]


@pytest.mark.parametrize("name", ["data.csv", "data.CSV", "weird name (1).csv"])
def test_supported_names(tmp_path, name):
    p = tmp_path / "f.csv"
    p.write_text("a,b\n1,2\n")
    assert list(autoprep.read_upload(p, name).values())[0].shape == (1, 2)
