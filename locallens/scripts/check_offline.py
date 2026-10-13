"""Run the REAL model + pipeline with all network connections blocked. Fails loudly if anything dials out."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import socket


def blocked(*a, **k):
    raise RuntimeError("network access attempted")


socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
socket.getaddrinfo = blocked

from locallens import demo, ingest, pipeline  # noqa: E402
from locallens.session import Session  # noqa: E402
from locallens.slm import SLM  # noqa: E402

reg = demo.demo_registry()
con = ingest.prepare(reg)
slm = SLM()
for q in ["Compare profit across categories", "Show monthly sales for 2024 by region", "Total revenue last year"]:
    res = pipeline.ask(q, reg, con, slm, Session())
    assert not res.error, res.error
    print(f"OK offline: {q!r} -> {res.chart.type} in {res.timings_ms['total']:.0f} ms")
print("No network calls were made.")
