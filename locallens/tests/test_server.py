"""The web API: accounts, access control, datasets, asking, exports. The language model is a stub."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

import make_synthetic_data
from locallens.query.frame import Metric, QueryFrame
from locallens.server.app import create_app
from locallens.server.config import Settings

H = {"X-Requested-With": "LocalLens"}
PW = "correct horse 1"


class StubSLM:
    """Stands in for the model: picks columns named in the question, then the rules layer does the rest."""

    def fill_frame(self, pre, reg, prev=None):
        metrics = [c for c in pre.column_hints.values() if c in reg.metric_names()]
        dims = [c for c in pre.column_hints.values() if c in {x.flat_name for x in reg.tagged("dimension")}]
        if prev is not None and not dims and not metrics:
            f = prev.model_copy(deep=True)                       # a follow-up that only changes the dates
        else:
            f = QueryFrame(intent="comparison" if dims else "summary",
                           metric=Metric(column=metrics[0] if metrics else reg.metric_names()[0]),
                           dimension=dims[0] if dims else None)
        return f, f.model_dump_json()


def make_client(tmp_path, **kw):
    s = Settings(data_dir=tmp_path / "data", web_dir=tmp_path / "web", preload_model=False, **kw)
    return TestClient(create_app(s, slm_factory=StubSLM), base_url="http://testserver")


@pytest.fixture()
def client(tmp_path):
    return make_client(tmp_path)


@pytest.fixture()
def admin(client):
    r = client.post("/api/auth/setup", json={"username": "boss", "password": PW}, headers=H)
    assert r.status_code == 200, r.text
    return client


def new_user(admin_client, name, role="user", password="temp-pass-123"):
    r = admin_client.post("/api/users", json={"username": name, "role": role, "password": password}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def login_as(app_client, name, password, change_to=None):
    c = TestClient(app_client.app, base_url="http://testserver")
    r = c.post("/api/auth/login", json={"username": name, "password": password}, headers=H)
    assert r.status_code == 200, r.text
    if change_to:
        r = c.post("/api/auth/password", json={"current_password": password, "new_password": change_to}, headers=H)
        assert r.status_code == 200, r.text
    return c


def csv_files(n=400):
    return [("files", (f"{k}.csv", df.to_csv(index=False).encode(), "text/csv"))
            for k, df in make_synthetic_data.build(n).items()]


def upload(c, name="Sales", files=None):
    return c.post("/api/datasets", data={"name": name}, files=files or csv_files(), headers=H)


# ---- accounts --------------------------------------------------------------------------------
def test_first_run_setup_then_closed(client):
    assert client.get("/api/auth/status").json() == {"setup_required": True}
    assert client.post("/api/auth/setup", json={"username": "a b", "password": PW}, headers=H).status_code == 422
    assert client.post("/api/auth/setup", json={"username": "boss", "password": "short"}, headers=H).status_code == 422
    r = client.post("/api/auth/setup", json={"username": "boss", "password": PW}, headers=H)
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.get("/api/auth/status").json() == {"setup_required": False}
    assert client.post("/api/auth/setup", json={"username": "x" * 5, "password": PW}, headers=H).status_code == 409


def test_login_logout_and_cookie_flags(admin):
    c = TestClient(admin.app, base_url="http://testserver")
    assert c.get("/api/auth/me").status_code == 401
    r = c.post("/api/auth/login", json={"username": "BOSS", "password": PW}, headers=H)   # names are case-insensitive
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert c.get("/api/auth/me").json()["username"] == "boss"
    c.post("/api/auth/logout", headers=H)
    assert c.get("/api/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_look_the_same(admin):
    c = TestClient(admin.app, base_url="http://testserver")
    a = c.post("/api/auth/login", json={"username": "boss", "password": "nope-nope-1"}, headers=H)
    b = c.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope-1"}, headers=H)
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_login_lockout_after_repeated_failures(tmp_path):
    c = make_client(tmp_path, login_max_failures=3)
    c.post("/api/auth/setup", json={"username": "boss", "password": PW}, headers=H)
    fresh = TestClient(c.app, base_url="http://testserver")
    codes = [fresh.post("/api/auth/login", json={"username": "boss", "password": "bad-bad-bad"}, headers=H).status_code
             for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    assert fresh.post("/api/auth/login", json={"username": "boss", "password": PW}, headers=H).status_code == 429


def test_state_changing_calls_need_the_csrf_header(admin):
    assert admin.post("/api/datasets/demo").status_code == 403
    assert admin.post("/api/datasets/demo", headers=H).status_code == 201


def test_api_requires_sign_in(client):
    for path in ("/api/datasets", "/api/users", "/api/prefs", "/api/auth/me"):
        assert client.get(path).status_code == 401, path


def test_temporary_password_must_be_changed(admin):
    u = new_user(admin, "alice", password="temp-pass-123")
    assert u["must_change_password"] is True
    c = TestClient(admin.app, base_url="http://testserver")
    c.post("/api/auth/login", json={"username": "alice", "password": "temp-pass-123"}, headers=H)
    r = c.get("/api/datasets")
    assert r.status_code == 403 and r.json()["detail"] == "password_change_required"
    assert c.get("/api/auth/me").json()["must_change_password"] is True
    assert c.post("/api/auth/password", json={"current_password": "wrong", "new_password": "brand new 99"}, headers=H).status_code == 403
    assert c.post("/api/auth/password", json={"current_password": "temp-pass-123", "new_password": "password"}, headers=H).status_code == 422
    assert c.post("/api/auth/password", json={"current_password": "temp-pass-123", "new_password": "brand new 99"}, headers=H).status_code == 200
    assert c.get("/api/datasets").status_code == 200


def test_only_admins_manage_users_and_one_admin_always_remains(admin):
    new_user(admin, "alice", password="temp-pass-123")
    alice = login_as(admin, "alice", "temp-pass-123", change_to="alice new pass 1")
    assert alice.get("/api/users").status_code == 403
    assert alice.post("/api/users", json={"username": "mallory"}, headers=H).status_code == 403
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/users/{me['id']}", json={"active": False}, headers=H).status_code == 409
    assert admin.patch(f"/api/users/{me['id']}", json={"role": "user"}, headers=H).status_code == 409
    assert admin.delete(f"/api/users/{me['id']}", headers=H).status_code == 409


def test_deactivating_a_user_ends_their_sessions(admin):
    u = new_user(admin, "bob", password="temp-pass-123")
    bob = login_as(admin, "bob", "temp-pass-123", change_to="bob new pass 1")
    assert bob.get("/api/datasets").status_code == 200
    admin.patch(f"/api/users/{u['id']}", json={"active": False}, headers=H)
    assert bob.get("/api/datasets").status_code == 401
    c = TestClient(admin.app, base_url="http://testserver")
    assert c.post("/api/auth/login", json={"username": "bob", "password": "bob new pass 1"}, headers=H).status_code == 401


def test_password_is_hashed_in_the_database(admin):
    row = admin.app.state.rt.db.one("SELECT pw_hash FROM users WHERE username = 'boss'")
    assert PW not in row["pw_hash"] and row["pw_hash"].startswith("scrypt$")


# ---- datasets ----------------------------------------------------------------------------------------
def test_demo_dataset_has_the_semantic_layer(admin):
    d = admin.post("/api/datasets/demo", headers=H).json()
    full = admin.get(f"/api/datasets/{d['id']}").json()
    assert full["problems"] == [] and {m["name"] for m in full["registry"]["measures"]} >= {"profit_margin"}
    assert full["stats"]["tables"]["orders"] == 20000
    assert all(not p.startswith("/") for p in full["registry"]["tables"].values())     # no server paths leak


def test_upload_guesses_tags_and_joins(admin):
    d = upload(admin).json()
    reg = admin.get(f"/api/datasets/{d['id']}").json()["registry"]
    tags = {c["name"]: c["tag"] for c in reg["columns"]}
    assert reg["main_table"] == "orders" and len(reg["joins"]) == 3
    assert tags["sales_amt"] == "metric" and tags["order_date"] == "date" and tags["category"] == "dimension"
    assert tags["order_id"] == "ignore" and tags["customer_id"] == "ignore"


def test_uploaded_dataset_answers_questions(admin):
    d = upload(admin).json()
    r = admin.post(f"/api/datasets/{d['id']}/ask", json={"question": "sales by category"}, headers=H)
    assert r.status_code == 200, r.text
    resp = r.json()["response"]
    assert resp["error"] == "" and resp["chart"]["type"] in ("bar", "donut") and resp["row_count"] == 3


@pytest.mark.parametrize("files,msg", [
    ([("files", ("x.exe", b"MZ", "application/octet-stream"))], "unsupported"),
    ([("files", ("x.csv", b"", "text/csv"))], "could not read"),
    ([("files", ("x.csv", b"a,b\n", "text/csv"))], "no rows"),
    ([("files", ("x.xlsx", b"not an excel file", "application/octet-stream"))], "could not read"),
    ([("files", ("x.sqlite", b"not a database", "application/octet-stream"))], "could not read"),
])
def test_bad_uploads_are_refused_cleanly(admin, files, msg):
    r = upload(admin, files=files)
    assert r.status_code == 422 and msg in r.json()["detail"].lower()
    assert admin.get("/api/datasets").json() == []
    assert list((admin.app.state.rt.settings.datasets_dir).iterdir()) == []            # nothing left behind


def test_oversized_upload_is_refused(tmp_path):
    c = make_client(tmp_path, max_upload_mb=1)
    c.post("/api/auth/setup", json={"username": "boss", "password": PW}, headers=H)
    big = ("files", ("big.csv", b"a,b\n" + b"1,2\n" * 600_000, "text/csv"))
    assert upload(c, files=[big]).status_code == 413


def test_hostile_names_are_neutralised(admin):
    csv = b'Sales Amount,"x; DROP TABLE orders",../../etc\n1,2,3\n4,5,6\n7,8,9\n'
    r = upload(admin, name="<script>alert(1)</script>", files=[("files", ("../../evil.csv", csv, "text/csv"))])
    assert r.status_code == 201
    d = r.json()
    reg = admin.get(f"/api/datasets/{d['id']}").json()["registry"]
    names = {c["name"] for c in reg["columns"]}
    assert names == {"sales_amount", "x_drop_table_orders", "etc"} and list(reg["tables"]) == ["evil"]
    assert [p.name for p in admin.app.state.rt.dataset_dir(d["id"]).iterdir()] == ["evil.parquet"]


def test_sqlite_and_excel_uploads(admin, tmp_path):
    import sqlite3
    import pandas as pd

    db = tmp_path / "shop.db"
    con = sqlite3.connect(db)
    pd.DataFrame({"id": [1, 2], "region": ["N", "S"]}).to_sql("regions", con, index=False)
    pd.DataFrame({"region_id": [1, 2, 1, 1], "amount": [10.0, 20.0, 5.0, 7.5]}).to_sql("sales", con, index=False)
    con.close()
    r = upload(admin, files=[("files", ("shop.db", db.read_bytes(), "application/octet-stream"))])
    assert r.status_code == 201
    xl = tmp_path / "book.xlsx"
    with pd.ExcelWriter(xl) as w:
        pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_excel(w, sheet_name="One", index=False)
        pd.DataFrame({"c": [1, 2, 3]}).to_excel(w, sheet_name="Two", index=False)
    r = upload(admin, name="Book", files=[("files", ("book.xlsx", xl.read_bytes(), "application/octet-stream"))])
    assert r.status_code == 201
    reg = admin.get(f"/api/datasets/{r.json()['id']}").json()["registry"]
    assert set(reg["tables"]) == {"book_one", "book_two"}


# ---- access control ----------------------------------------------------------------------------------
@pytest.fixture()
def two_users(admin):
    new_user(admin, "alice", password="temp-pass-123")
    new_user(admin, "bob", password="temp-pass-456")
    alice = login_as(admin, "alice", "temp-pass-123", change_to="alice pass 123")
    bob = login_as(admin, "bob", "temp-pass-456", change_to="bob pass 4567")
    return alice, bob


def test_private_datasets_are_invisible_to_others(two_users):
    alice, bob = two_users
    d = alice.post("/api/datasets/demo", headers=H).json()["id"]
    assert bob.get("/api/datasets").json() == []
    for method, path, kw in [("get", f"/api/datasets/{d}", {}), ("get", f"/api/datasets/{d}/preview", {}),
                             ("get", f"/api/datasets/{d}/suggestions", {}),
                             ("post", f"/api/datasets/{d}/ask", {"json": {"question": "total sales"}}),
                             ("post", f"/api/datasets/{d}/check-expression", {"json": {"kind": "rule", "expression": "1=1"}}),
                             ("patch", f"/api/datasets/{d}", {"json": {"name": "mine now"}}),
                             ("delete", f"/api/datasets/{d}", {})]:
        r = getattr(bob, method)(path, headers=H, **kw)
        assert r.status_code == 404, (method, path, r.status_code)
    assert alice.get(f"/api/datasets/{d}").status_code == 200


def test_shared_dataset_can_be_used_but_not_changed(two_users):
    alice, bob = two_users
    d = alice.post("/api/datasets/demo", headers=H).json()["id"]
    assert alice.patch(f"/api/datasets/{d}", json={"visibility": "shared"}, headers=H).status_code == 200
    assert [x["id"] for x in bob.get("/api/datasets").json()] == [d]
    full = bob.get(f"/api/datasets/{d}").json()
    assert full["can_edit"] is False
    assert bob.post(f"/api/datasets/{d}/ask", json={"question": "total sales"}, headers=H).status_code == 200
    reg = full["registry"]
    assert bob.put(f"/api/datasets/{d}/registry", json=reg, headers=H).status_code == 404
    assert bob.delete(f"/api/datasets/{d}", headers=H).status_code == 404
    assert bob.patch(f"/api/datasets/{d}", json={"visibility": "private"}, headers=H).status_code == 404


def test_conversations_and_messages_are_private_even_on_shared_data(two_users):
    alice, bob = two_users
    d = alice.post("/api/datasets/demo", headers=H).json()["id"]
    alice.patch(f"/api/datasets/{d}", json={"visibility": "shared"}, headers=H)
    r = alice.post(f"/api/datasets/{d}/ask", json={"question": "total sales"}, headers=H).json()
    cid, mid = r["conversation_id"], r["message_id"]
    assert bob.get(f"/api/conversations/{cid}").status_code == 404
    assert bob.delete(f"/api/conversations/{cid}", headers=H).status_code == 404
    assert bob.get(f"/api/messages/{mid}/export/csv").status_code == 404
    assert bob.post(f"/api/messages/{mid}/feedback", json={"rating": -1}, headers=H).status_code == 404
    assert bob.post(f"/api/messages/{mid}/example", headers=H).status_code == 404
    assert bob.post(f"/api/datasets/{d}/ask", json={"question": "total sales", "conversation_id": cid}, headers=H).status_code == 404
    assert bob.get(f"/api/datasets/{d}/conversations").json() == []
    assert len(alice.get(f"/api/datasets/{d}/conversations").json()) == 1


def test_admin_cannot_read_other_peoples_conversations(admin, two_users):
    alice, _ = two_users
    d = alice.post("/api/datasets/demo", headers=H).json()["id"]
    cid = alice.post(f"/api/datasets/{d}/ask", json={"question": "total sales"}, headers=H).json()["conversation_id"]
    assert admin.get(f"/api/conversations/{cid}").status_code == 404
    assert [x["id"] for x in admin.get("/api/datasets").json()] == []                  # private datasets stay private in lists
    assert admin.get(f"/api/datasets/{d}").status_code == 200                           # but an admin can manage them


def test_deleting_a_user_removes_their_data(admin, two_users):
    alice, _ = two_users
    d = alice.post("/api/datasets/demo", headers=H).json()["id"]
    uid = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "alice")
    assert admin.delete(f"/api/users/{uid}", headers=H).status_code == 200
    assert not admin.app.state.rt.dataset_dir(d).exists()
    assert admin.app.state.rt.db.one("SELECT 1 FROM datasets WHERE id = ?", (d,)) is None


# ---- asking -----------------------------------------------------------------------------------------------
@pytest.fixture()
def demo_id(admin):
    return admin.post("/api/datasets/demo", headers=H).json()["id"]


def ask(c, d, q, **kw):
    r = c.post(f"/api/datasets/{d}/ask", json={"question": q, **kw}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_answer_has_everything_the_screen_needs(admin, demo_id):
    r = ask(admin, demo_id, "profit margin by category")["response"]
    assert r["chart"]["type"] == "bar" and r["chart"]["spec"]["mark"] == "bar"
    assert [c["name"] for c in r["columns"]] == ["category", "profit_margin"] and len(r["rows"]) == 3
    assert r["metric"]["format"] == "percent" and "valid_orders" in [x["name"] for x in r["rules"]]
    assert r["sql"].startswith("SELECT") and r["frame"]["metric"]["column"] == "profit_margin"
    assert all(isinstance(v, (int, float, str, type(None))) for row in r["rows"] for v in row)
    assert {"powerbi", "csv"} <= set(r["exports"])


def test_kpi_and_histogram_shapes(admin, demo_id):
    k = ask(admin, demo_id, "total sales")["response"]
    assert k["chart"]["type"] == "kpi" and k["kpi"]["value"] > 0
    h = ask(admin, demo_id, "distribution of sales")["response"]
    assert h["chart"]["type"] == "histogram" and h["row_count"] <= 10                    # binned on the server
    assert h["columns"][1]["name"] == "count" and sum(r[1] for r in h["rows"]) == 20000


def test_followups_use_the_conversation(admin, demo_id):
    first = ask(admin, demo_id, "sales by category")
    second = ask(admin, demo_id, "now only 2025", conversation_id=first["conversation_id"])["response"]
    assert second["followup"] is True and second["frame"]["dimension"] == "category"
    assert "2025-01-01" in second["sql"]
    conv = admin.get(f"/api/conversations/{first['conversation_id']}").json()
    assert [m["response"]["question"] for m in conv["messages"]] == ["sales by category", "now only 2025"]


def test_errors_and_clarifications_are_answers_not_crashes(admin, demo_id):
    r = ask(admin, demo_id, "hi there")["response"]
    assert r["error"] and r["chart"] is None
    c = ask(admin, demo_id, "sales by category for West")["response"]
    assert c["clarification"]["field"] == "filter"
    again = ask(admin, demo_id, c["clarification"]["question"], overrides={"filter": "store_region"})["response"]
    assert again["error"] == "" and again["frame"]["filters"][0]["column"] == "store_region"
    assert admin.post(f"/api/datasets/{demo_id}/ask", json={"question": "x", "overrides": {"evil": "1"}}, headers=H).status_code == 422
    assert admin.post(f"/api/datasets/{demo_id}/ask", json={"question": ""}, headers=H).status_code == 422
    assert admin.post(f"/api/datasets/{demo_id}/ask", json={"question": "a" * 501}, headers=H).status_code == 422


def test_model_failure_is_a_clear_503(tmp_path):
    def broken():
        raise FileNotFoundError("model file is missing")
    s = Settings(data_dir=tmp_path / "d", web_dir=tmp_path / "w", preload_model=False)
    c = TestClient(create_app(s, slm_factory=broken), base_url="http://testserver")
    c.post("/api/auth/setup", json={"username": "boss", "password": PW}, headers=H)
    d = c.post("/api/datasets/demo", headers=H).json()["id"]
    r = c.post(f"/api/datasets/{d}/ask", json={"question": "total sales"}, headers=H)
    assert r.status_code == 503 and "model" in r.json()["detail"]
    assert c.get("/api/health").json()["model_error"]


# ---- the semantic editor ---------------------------------------------------------------------------------
def test_user_defined_measure_changes_answers(admin, demo_id):
    full = admin.get(f"/api/datasets/{demo_id}").json()
    reg = full["registry"]
    reg["measures"].append({"name": "avg_qty", "label": "average quantity", "expression": "SUM(quantity) / COUNT(DISTINCT order_id)",
                            "description": "", "synonyms": [], "format": "number", "additive": False, "error": ""})
    r = admin.put(f"/api/datasets/{demo_id}/registry", json=reg, headers=H)
    assert r.status_code == 200 and r.json()["problems"] == []
    out = ask(admin, demo_id, "average quantity by category")["response"]
    assert out["frame"]["metric"]["column"] == "avg_qty" and out["error"] == ""


def test_bad_definitions_report_problems_but_do_not_break_the_dataset(admin, demo_id):
    reg = admin.get(f"/api/datasets/{demo_id}").json()["registry"]
    reg["measures"].append({"name": "evil", "expression": "(SELECT 1)", "label": "", "description": "", "synonyms": [],
                            "format": "number", "additive": False, "error": ""})
    reg["rules"].append({"name": "badrule", "condition": "nope > 1", "phrases": [], "description": "", "enabled": True, "error": ""})
    r = admin.put(f"/api/datasets/{demo_id}/registry", json=reg, headers=H)
    assert r.status_code == 200 and len(r.json()["problems"]) == 2
    assert ask(admin, demo_id, "profit margin by category")["response"]["error"] == ""


def test_registry_edits_cannot_change_the_source_data(admin, demo_id):
    reg = admin.get(f"/api/datasets/{demo_id}").json()["registry"]
    gone = {**reg, "columns": reg["columns"][1:]}
    assert admin.put(f"/api/datasets/{demo_id}/registry", json=gone, headers=H).status_code == 422
    bad_join = {**reg, "joins": [{"left": "orders", "left_key": "nope", "right": "stores", "right_key": "store_id"}]}
    assert admin.put(f"/api/datasets/{demo_id}/registry", json=bad_join, headers=H).status_code == 422
    sneaky = {**reg, "tables": {"orders": "/etc/passwd"}}
    r = admin.put(f"/api/datasets/{demo_id}/registry", json=sneaky, headers=H)
    assert r.status_code == 200 and "passwd" not in json.dumps(r.json())
    assert ask(admin, demo_id, "total sales")["response"]["error"] == ""


@pytest.mark.parametrize("edit", [
    lambda r: r.update(description="x" * 601),
    lambda r: r["columns"][0].update(description="y" * 201),
    lambda r: r["examples"].append({"question": "q", "frame": {"nonsense": 1}}),
    lambda r: r["columns"][0].update(tag="admin"),
    lambda r: r["columns"].append({"table": "_calc", "name": "bad name", "tag": "metric", "expression": "1"}),
])
def test_oversized_or_malformed_definitions_are_refused(admin, demo_id, edit):
    reg = admin.get(f"/api/datasets/{demo_id}").json()["registry"]
    edit(reg)
    assert admin.put(f"/api/datasets/{demo_id}/registry", json=reg, headers=H).status_code == 422


def test_live_expression_check(admin, demo_id):
    ok = admin.post(f"/api/datasets/{demo_id}/check-expression",
                    json={"kind": "measure", "expression": "SUM(profit) / SUM(sales_amt)"}, headers=H).json()
    assert ok["ok"] and 0 < ok["preview"]["value"] < 1
    col = admin.post(f"/api/datasets/{demo_id}/check-expression",
                     json={"kind": "column", "expression": "CASE WHEN quantity > 3 THEN 'bulk' ELSE 'single' END"}, headers=H).json()
    assert col["ok"] and set(col["preview"]["values"]) == {"bulk", "single"}
    rule = admin.post(f"/api/datasets/{demo_id}/check-expression",
                      json={"kind": "rule", "expression": "sales_amt >= 1000"}, headers=H).json()
    assert rule["ok"] and 0 < rule["preview"]["matching"] < rule["preview"]["of"]
    for bad in ("(SELECT 1)", "read_csv('/etc/passwd')", "nope + 1"):
        r = admin.post(f"/api/datasets/{demo_id}/check-expression", json={"kind": "measure", "expression": bad}, headers=H).json()
        assert r["ok"] is False and r["error"]


def test_suggestions_come_from_the_dataset(admin, demo_id):
    s = admin.get(f"/api/datasets/{demo_id}/suggestions").json()
    assert "average order value by store" in s and any(x.startswith("total ") for x in s) and len(s) <= 8


def test_preview(admin, demo_id):
    p = admin.get(f"/api/datasets/{demo_id}/preview?table=flat&limit=5").json()
    assert len(p["rows"]) == 5 and "order_size" in [c["name"] for c in p["columns"]]
    assert admin.get(f"/api/datasets/{demo_id}/preview?table=nope").status_code == 404
    assert admin.get(f'/api/datasets/{demo_id}/preview?table=orders"%3B%20DROP').status_code == 404


# ---- feedback, examples, exports, prefs -------------------------------------------------------------------
def test_feedback_and_saving_a_verified_example(admin, demo_id):
    r = ask(admin, demo_id, "profit by category")
    mid = r["message_id"]
    assert admin.post(f"/api/messages/{mid}/feedback", json={"rating": 5}, headers=H).status_code == 422
    assert admin.post(f"/api/messages/{mid}/feedback", json={"rating": -1, "note": "wrong chart"}, headers=H).status_code == 200
    fb = admin.get("/api/admin/feedback").json()
    assert fb[0]["question"] == "profit by category" and fb[0]["note"] == "wrong chart" and fb[0]["sql"]
    assert admin.post(f"/api/messages/{mid}/example", headers=H).json() == {"ok": True, "already": False}
    assert admin.post(f"/api/messages/{mid}/example", headers=H).json()["already"] is True
    reg = admin.get(f"/api/datasets/{demo_id}").json()["registry"]
    assert "profit by category" in [e["question"] for e in reg["examples"]]
    bad = ask(admin, demo_id, "hi there")["message_id"]
    assert admin.post(f"/api/messages/{bad}/example", headers=H).status_code == 422


def test_non_admins_cannot_read_feedback(two_users):
    assert two_users[0].get("/api/admin/feedback").status_code == 403


def test_powerbi_export_is_a_working_project(admin, demo_id):
    mid = ask(admin, demo_id, "monthly sales for 2024")["message_id"]
    r = admin.get(f"/api/messages/{mid}/export/powerbi")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert any(n.endswith(".pbip") for n in names) and any(n.endswith("Result.tmdl") for n in names)
    assert admin.get(f"/api/messages/{mid}/export/tableau").status_code == 404


def test_csv_export_blocks_formula_injection(admin):
    d = upload(admin, files=[("files", ("evil.csv", b"label,amount\n=HYPERLINK(\"http://x\"),5\n+cmd|x,6\nok,7\n"
                                       b"@sum,1\nfine,2\nmore,3\n", "text/csv"))]).json()["id"]
    reg = admin.get(f"/api/datasets/{d}").json()["registry"]
    for c in reg["columns"]:
        c["tag"] = {"label": "dimension", "amount": "metric"}[c["name"]]
    admin.put(f"/api/datasets/{d}/registry", json=reg, headers=H)
    mid = ask(admin, d, "amount by label")["message_id"]
    body = admin.get(f"/api/messages/{mid}/export/csv").text
    lines = body.splitlines()
    assert all(not ln.startswith(("=", "+", "-", "@")) for ln in lines[1:]) and "'=HYPERLINK" in body


def test_preferences(admin, demo_id):
    assert admin.get("/api/prefs").json()["sort"] == "desc"
    assert admin.put("/api/prefs", json={"sort": "up"}, headers=H).status_code == 422
    assert admin.put("/api/prefs", json={"sort": "asc", "chart_overrides": {"trend": "donut"}}, headers=H).status_code == 422
    ok = admin.put("/api/prefs", json={"sort": "asc", "chart_overrides": {"comparison": "hbar"}}, headers=H).json()
    assert ok["chart_overrides"] == {"comparison": "hbar"}
    r = ask(admin, demo_id, "compare sales by category")["response"]
    assert r["chart"]["type"] == "hbar"                                                   # the saved preference is used


# ---- serving the web app and basic hardening -----------------------------------------------------------
def test_security_headers_and_health(admin):
    r = admin.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    for h in ("x-content-type-options", "x-frame-options", "content-security-policy"):
        assert h in r.headers
    assert "script-src 'self'" in r.headers["content-security-policy"] and "unsafe-eval" not in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    assert admin.get("/openapi.json").status_code in (404, 200) and admin.get("/docs").status_code == 404


def test_single_page_app_is_served_and_cannot_leak_files(tmp_path):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>app</html>")
    (web / "assets" / "a.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("TOP SECRET")
    c = make_client(tmp_path)
    assert "app" in c.get("/").text and "app" in c.get("/datasets/abc").text          # client-side routes fall back to index
    assert c.get("/assets/a.js").status_code == 200
    for attack in ("/../secret.txt", "/%2e%2e/secret.txt", "/..%2fsecret.txt", "/assets/../../secret.txt"):
        r = c.get(attack)
        assert "TOP SECRET" not in r.text, attack
    assert c.get("/api/nothing").status_code in (404, 401)


def test_default_aggregation_preference(admin, demo_id):
    assert admin.get("/api/prefs").json()["default_agg"] == "SUM"
    assert admin.put("/api/prefs", json={"sort": "desc", "default_agg": "MEDIAN"}, headers=H).status_code == 422
    ok = admin.put("/api/prefs", json={"sort": "desc", "default_agg": "AVG"}, headers=H).json()
    assert ok["default_agg"] == "AVG" and "AVG" in ok["default_aggs"]
    r = ask(admin, demo_id, "compare sales by category")["response"]
    assert r["frame"]["metric"]["agg"] == "AVG"
    r = ask(admin, demo_id, "compare total sales by category")["response"]
    assert r["frame"]["metric"]["agg"] == "SUM"                                           # the words win


def test_typeahead_endpoint(admin, demo_id):
    items = admin.get(f"/api/datasets/{demo_id}/complete", params={"q": "sales by cat"}).json()
    assert any(i["with"].lower().startswith("categor") and i["replace"] == "cat" for i in items)
    assert admin.get(f"/api/datasets/{demo_id}/complete", params={"q": "sales by "}).json() == []
    assert admin.get(f"/api/datasets/{demo_id}/complete", params={"q": "x" * 600}).status_code == 422
    assert admin.get("/api/datasets/nope/complete", params={"q": "sa"}).status_code == 404


def test_chart_request_over_http_and_its_export(admin, demo_id):
    first = ask(admin, demo_id, "compare sales by category")
    cid = first["conversation_id"]
    r = admin.post(f"/api/datasets/{demo_id}/ask", json={"question": "make it a pie chart", "conversation_id": cid}, headers=H).json()
    assert r["response"]["chart"]["type"] == "donut" and r["response"]["chart_forced"] == "donut"
    assert r["response"]["chart"]["reason"] == "you asked for a pie chart"
    export = admin.get(f"/api/messages/{r['message_id']}/export/powerbi")
    assert export.status_code == 200                                                      # exported as the chart the user chose
