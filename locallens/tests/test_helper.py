"""One-click open in Power BI Desktop: single-use links and the Windows helper package."""
import io
import json
import zipfile

from fastapi.testclient import TestClient

from locallens.server import helper
from locallens.server.links import LinkStore
from tests.test_server import H, admin, ask, client, demo_id, login_as, new_user  # noqa: F401  (fixtures)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_a_link_works_once():
    store = LinkStore()
    token = store.issue(7, "m1", "powerbi")
    grant = store.redeem(token)
    assert (grant.user_id, grant.message_id, grant.kind) == (7, "m1", "powerbi")
    assert store.redeem(token) is None                    # used
    assert store.redeem("nope") is None                   # unknown


def test_a_link_expires():
    clock = Clock()
    store = LinkStore(ttl=120, clock=clock)
    token = store.issue(1, "m", "powerbi")
    clock.now = 121
    assert store.redeem(token) is None


def test_pending_links_are_capped():
    store = LinkStore()
    tokens = [store.issue(1, f"m{i}", "powerbi") for i in range(600)]
    assert store.redeem(tokens[0]) is None and store.redeem(tokens[-1]) is not None


def test_origin_is_normalised():
    assert helper.origin_of("http://Server.Corp:8000/") == "http://server.corp:8000"
    assert helper.origin_of("https://host/api/x") == "https://host"


def test_helper_package(admin):
    r = admin.get("/api/helper/windows")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = {n.split("/")[-1] for n in z.namelist()}
    assert {"config.json", "locallens-open.ps1", "install.ps1", "uninstall.ps1", "install.bat", "README.txt"} <= names
    cfg = json.loads(z.read("LocalLens-helper/config.json"))
    assert cfg == {"server": "http://testserver"}
    open_ps = z.read("LocalLens-helper/locallens-open.ps1").decode("ascii")      # PowerShell 5 reads BOM-less files as ANSI
    for must in ("$cfg.server", "/api/export/dl/", "GetFullPath", "StartsWith($destFull", "Start-Process"):
        assert must in open_ps
    assert "Invoke-Expression" not in open_ps and "iex " not in open_ps
    for n in z.namelist():
        z.read(n).decode("ascii")


def test_helper_needs_sign_in(client):
    assert client.get("/api/helper/windows").status_code == 401


def test_link_download_flow(admin, demo_id):
    msg = ask(admin, demo_id, "compare sales by category")
    link = admin.post(f"/api/messages/{msg['message_id']}/export/powerbi/link", headers=H).json()
    assert link["url"].startswith("http://testserver/api/export/dl/")
    assert link["protocol"].startswith("locallens://open?u=http%3A%2F%2Ftestserver%2Fapi%2Fexport%2Fdl%2F")
    path = link["url"].removeprefix("http://testserver")

    anon = TestClient(admin.app, base_url="http://testserver")                      # no cookie, like the helper
    r = anon.get(path)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip" and r.headers["cache-control"] == "no-store"
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert any(n.endswith(".pbip") for n in names) and any("Result.tmdl" in n for n in names)
    assert anon.get(path).status_code == 404                                         # single use


def test_link_needs_sign_in_csrf_and_ownership(admin, demo_id):
    msg = ask(admin, demo_id, "compare sales by category")
    url = f"/api/messages/{msg['message_id']}/export/powerbi/link"
    anon = TestClient(admin.app, base_url="http://testserver")
    assert anon.post(url, headers=H).status_code == 401
    assert admin.post(url).status_code in (400, 403)                                  # CSRF header missing
    new_user(admin, "sam", password="temp-pass-123")
    sam = login_as(admin, "sam", "temp-pass-123", change_to="a-better-pass-456")
    assert sam.post(url, headers=H).status_code == 404                                # someone else's answer
    assert admin.post(f"/api/messages/{msg['message_id']}/export/nonsense/link", headers=H).status_code == 404


def test_a_made_up_token_is_refused(client):
    assert client.get("/api/export/dl/" + "x" * 32).status_code == 404
