"""Evaluate the real model against the gold questions.

Usage: PYTHONPATH=src python eval/run_eval.py [--limit N] [--show-failures]
Reports per-field accuracy, execution accuracy (result table equals the gold frame's),
chart-type match, and p50/p95 latency.
"""
import argparse
import statistics
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from questions import QUESTIONS  # noqa: E402

from locallens import demo, engine, ingest, pipeline  # noqa: E402
from locallens.charts import build_spec  # noqa: E402
from locallens.frame import QueryFrame  # noqa: E402
from locallens.profiler import profile  # noqa: E402
from locallens.session import Session  # noqa: E402
from locallens.sqlgen import build_sql  # noqa: E402


def gold_result(frame: QueryFrame, reg, con) -> tuple[pd.DataFrame, str]:
    df = engine.run(con, build_sql(frame, reg))
    return df, build_spec(df, frame.intent, profile(df)).type


def same(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    if a.shape != b.shape:
        return False
    a, b = a.reset_index(drop=True), b.reset_index(drop=True)
    a.columns = b.columns = range(a.shape[1])
    return all(
        (abs(a[c] - b[c]) < 0.01).all() if pd.api.types.is_numeric_dtype(a[c]) else (a[c].astype(str) == b[c].astype(str)).all()
        for c in a.columns
    )


def pct(n, d):
    return f"{100 * n / d:5.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--show-failures", action="store_true")
    args = ap.parse_args()

    reg = demo.demo_registry()
    con = ingest.prepare(reg)
    today = pipeline.data_today(con, reg)
    assert today.year == 2025 and today.month >= 10, f"gold dates assume data ends in Q4 2025, got {today}"

    from locallens.slm import SLM

    slm = SLM()
    slm.llm.create_chat_completion(messages=[{"role": "user", "content": "hi"}], max_tokens=1)  # warm-up

    items = QUESTIONS[: args.limit]
    n = len(items)
    hits = dict(intent=0, metric=0, dimension=0, time=0, filters=0, execution=0, chart=0)
    lat, fails = [], []
    for q, gold, gold_chart in items:
        g = QueryFrame.model_validate(gold)
        gdf, _ = gold_result(g, reg, con)
        res = pipeline.ask(q, reg, con, slm, Session())
        if res.timings_ms.get("total"):
            lat.append(res.timings_ms["total"])
        f = res.frame
        if f is None or res.error:
            fails.append((q, res.error or "clarification asked"))
            continue
        hits["intent"] += f.intent == g.intent
        hits["metric"] += f.metric == g.metric
        hits["dimension"] += f.dimension == g.dimension
        hits["time"] += ((f.time.start, f.time.end) if f.time else None) == ((g.time.start, g.time.end) if g.time else None)
        hits["filters"] += {(x.column, x.value.lower()) for x in f.filters} == {(x.column, x.value.lower()) for x in g.filters}
        ok = res.df is not None and same(res.df, gdf)
        hits["execution"] += ok
        hits["chart"] += bool(res.chart) and res.chart.type == gold_chart
        if not ok:
            fails.append((q, f"got {f.model_dump_json()}"))

    print(f"\n{n} questions")
    for k, v in hits.items():
        print(f"  {k:<10} {pct(v, n)}  ({v}/{n})")
    if lat:
        qs = statistics.quantiles(lat, n=20)
        print(f"  latency    p50 {statistics.median(lat):.0f} ms | p95 {qs[18]:.0f} ms | max {max(lat):.0f} ms")
    if args.show_failures:
        print("\nFailures:")
        for q, why in fails:
            print(f" - {q}\n     {why}")


if __name__ == "__main__":
    main()
