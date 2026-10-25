"""Evaluate the real model against the gold questions.

Usage: python eval/run_eval.py [--set gold|heldout] [--limit N] [--show-failures]
Reports per-field accuracy, execution accuracy (result table equals the gold frame's),
chart-type match, and p50/p95 latency.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import argparse
import statistics
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import questions as gold_set  # noqa: E402
import heldout  # noqa: E402
import heldout2  # noqa: E402
import heldout3  # noqa: E402

from locallens.data import demo

from locallens.data import engine

from locallens.data import ingest

from locallens.core import pipeline  # noqa: E402
from locallens.viz.charts import build_spec  # noqa: E402
from locallens.query.frame import QueryFrame  # noqa: E402
from locallens.data.profiler import profile  # noqa: E402
from locallens.core.session import Session  # noqa: E402
from locallens.query.sqlgen import build_sql  # noqa: E402


def gold_result(frame: QueryFrame, reg, con, sql: str | None = None) -> tuple[pd.DataFrame, str]:
    df = engine.run(con, sql or build_sql(frame, reg))
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
    ap.add_argument("--start", type=int, default=0, help="skip the first N questions")
    ap.add_argument("--set", choices=["gold", "heldout", "heldout2", "heldout3"], default="gold", help="which question set to run")
    ap.add_argument("--show-failures", action="store_true")
    ap.add_argument("--no-embeddings", action="store_true", help="turn off matching by meaning (claim 7) to measure what it adds")
    ap.add_argument("--rules", choices=list(pipeline.RULES_MODES), default="always",
                    help="always: rules also decide when no keyword fires; fired: only when one fires; off: no keyword rules")
    ap.add_argument("--model", type=Path, help="GGUF file to test instead of the default (e.g. a fine-tuned model)")
    args = ap.parse_args()

    reg = demo.demo_registry()
    con = ingest.prepare(reg)
    today = pipeline.data_today(con, reg)
    assert today.year == 2025 and today.month >= 10, f"gold dates assume data ends in Q4 2025, got {today}"

    from locallens.nlu.slm import SLM

    slm = SLM(args.model) if args.model else SLM()
    print("model:", args.model or "default", "| rules:", args.rules)
    slm.llm.create_chat_completion(messages=[{"role": "user", "content": "hi"}], max_tokens=1)  # warm-up

    term_index = None
    emb_path = Path(__file__).resolve().parent.parent / "models" / "bge-small-en-v1.5-q8_0.gguf"
    if not args.no_embeddings and emb_path.exists():
        from locallens.nlu.embeddings import LlamaEmbedder, TermIndex

        term_index = TermIndex(LlamaEmbedder(emb_path), reg)
    print("matching by meaning:", "on" if term_index else "off")
    items = {"gold": gold_set, "heldout": heldout, "heldout2": heldout2, "heldout3": heldout3}[args.set].QUESTIONS[args.start: args.limit]
    n = len(items)
    hits = dict(intent=0, metric=0, dimension=0, time=0, filters=0, execution=0, chart=0)
    raw_hits = dict(intent=0, metric_column=0, dimension=0)   # the model's own answer, before rules and grounding
    lat, fails, asked = [], [], 0
    for q, gold, gold_chart, *extra in items:
        g = QueryFrame.model_validate(gold)
        gdf, _ = gold_result(g, reg, con, extra[0] if extra else None)
        res = pipeline.ask(q, reg, con, slm, Session(), term_index=term_index, rules_mode=args.rules)
        if res.timings_ms.get("total"):
            lat.append(res.timings_ms["total"])
        if res.raw_frame:
            rf = QueryFrame.model_validate_json(res.raw_frame)
            raw_hits["intent"] += rf.intent == g.intent
            raw_hits["metric_column"] += rf.metric.column == g.metric.column
            raw_hits["dimension"] += rf.dimension == g.dimension
        f = res.frame
        if res.clarification:
            asked += 1
            fails.append((q, f"asked: {res.clarification.message}"))
            continue
        if f is None or res.error:
            fails.append((q, res.error or "no answer"))
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
            fails.append((q, f"got {f.model_dump_json()}\n     want {g.model_dump_json()}\n     model {res.raw_frame}"))

    print(f"\n{n} questions")
    for k, v in hits.items():
        print(f"  {k:<10} {pct(v, n)}  ({v}/{n})")
    print("  model alone (before rules):", ", ".join(f"{k} {pct(v, n).strip()}" for k, v in raw_hits.items()))
    if asked:
        print(f"  asked a clarifying question instead of answering: {asked} (counted as not answered above)")
    if lat:
        qs = statistics.quantiles(lat, n=20)
        print(f"  latency    p50 {statistics.median(lat):.0f} ms | p95 {qs[18]:.0f} ms | max {max(lat):.0f} ms")
    if args.show_failures:
        print("\nFailures:")
        for q, why in fails:
            print(f" - {q}\n     {why}")


if __name__ == "__main__":
    main()
