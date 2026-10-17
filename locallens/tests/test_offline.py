"""The server and the whole question flow work with every network connection blocked."""
import socket

import pytest
from fastapi.testclient import TestClient

from locallens.server.app import create_app
from locallens.server.config import Settings
from tests.test_server import H, PW, StubSLM


def test_full_flow_with_the_network_blocked(tmp_path, monkeypatch):
    def deny(*a, **k):
        raise AssertionError("a network connection was attempted")

    s = Settings(data_dir=tmp_path / "d", web_dir=tmp_path / "w", preload_model=False)
    c = TestClient(create_app(s, slm_factory=StubSLM), base_url="http://testserver")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    assert c.post("/api/auth/setup", json={"username": "boss", "password": PW}, headers=H).status_code == 200
    d = c.post("/api/datasets/demo", headers=H).json()["id"]
    r = c.post(f"/api/datasets/{d}/ask", json={"question": "profit margin by category"}, headers=H).json()
    assert r["response"]["error"] == "" and r["response"]["chart"]["type"] == "bar"
    assert c.get(f"/api/messages/{r['message_id']}/export/powerbi").status_code == 200
    assert c.get(f"/api/messages/{r['message_id']}/export/csv").status_code == 200
