"""Smoke test: run real questions through the real model on the demo data and print timings."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import sys
import time

from locallens.data import demo

from locallens.data import ingest

from locallens.core import pipeline
from locallens.core.session import Session
from locallens.nlu.slm import SLM

QUESTIONS = sys.argv[1:] or [
    "Show monthly sales for 2024 by region",
    "Compare profit across categories",
    "Top 5 products by profit",
    "What share of sales comes from each customer segment?",
    "What is the distribution of order sales?",
    "Total revenue last year",
    "Show monthly revenue for Q3 2025",
    "compare revnue by categry",
]

reg = demo.demo_registry()
con = ingest.prepare(reg)
t = time.perf_counter()
slm = SLM()
print(f"model load: {time.perf_counter() - t:.1f}s")
for q in QUESTIONS:
    res = pipeline.ask(q, reg, con, slm, Session())
    ms = res.timings_ms.get("total", 0)
    print(f"\nQ: {q}\n  {ms:.0f} ms (slm {res.timings_ms.get('slm', 0):.0f})")
    if res.error:
        print("  ERROR:", res.error)
    elif res.clarification:
        print("  CLARIFY:", res.clarification.message, res.clarification.options)
    else:
        print("  chart:", res.chart.type, "| rows:", len(res.df))
        print("  sql:", res.sql)
