from locallens.data.profiler import profile  # noqa: E402


def test_flat_view_keeps_order_rowcount(reg, con):
    n_orders = con.execute("SELECT count(*) FROM orders").fetchone()[0]
    n_flat = con.execute("SELECT count(*) FROM flat").fetchone()[0]
    assert n_orders == n_flat == 2000


def test_flat_view_has_joined_columns(con):
    cols = {r[0] for r in con.execute("DESCRIBE flat").fetchall()}
    assert {"sales_amt", "category", "cust_seg", "store_region"} <= cols


def test_samples_collected_for_dimensions(reg, con):
    seg = reg.by_flat_name("cust_seg")
    assert set(seg.samples) <= {"Consumer", "Corporate", "Home Office"} and seg.samples


def test_profile_time_series(con):
    df = con.execute(
        "SELECT date_trunc('month', CAST(order_date AS DATE)) AS month, SUM(sales_amt) AS s "
        "FROM flat GROUP BY 1 ORDER BY 1"
    ).df()
    p = profile(df)
    assert p.time_col == "month" and p.time_ordered and p.numeric_cols == ["s"]
