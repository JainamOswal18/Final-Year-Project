"""Evaluate the real model against the gold questions.

Usage: python eval/run_eval.py [--set gold|heldout] [--limit N] [--show-failures]
Reports per-field accuracy, execution accuracy (result table equals the gold frame's),
chart-type match, and p50/p95 latency.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import argparse
import json
import statistics
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import questions as gold_set  # noqa: E402
import heldout  # noqa: E402
import heldout2  # noqa: E402
import heldout3  # noqa: E402
import heldout4  # noqa: E402
import cross_online_retail  # noqa: E402
import cross_wholesale  # noqa: E402

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


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for k hits out of n (percent). At n = 30 one question is 3.3 points."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return 100 * (centre - half), 100 * (centre + half)


def ci(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{pct(k, n).strip()} [{lo:.0f}-{hi:.0f}]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", type=int, default=0, help="skip the first N questions")
    ap.add_argument("--set", choices=["gold", "heldout", "heldout2", "heldout3", "heldout4", "online_retail", "wholesale"], default="gold", help="which question set to run")
    ap.add_argument("--prompt-style", choices=["full", "compact"], help="prompt the model gets (default: the model's own default, env LOCALLENS_PROMPT_STYLE)")
    ap.add_argument("--out", type=Path, help="write one JSON line per question (for paired tests between runs)")
    ap.add_argument("--no-sequences", action="store_true", help="heldout4: skip the multi-turn conversations")
    ap.add_argument("--show-failures", action="store_true")
    ap.add_argument("--no-embeddings", action="store_true", help="turn off matching by meaning (claim 7) to measure what it adds")
    ap.add_argument("--rules", choices=list(pipeline.RULES_MODES), default="always",
                    help="always: rules also decide when no keyword fires; fired: only when one fires; off: no keyword rules")
    ap.add_argument("--model", type=Path, help="GGUF file to test instead of the default (e.g. a fine-tuned model)")
    args = ap.parse_args()

    cross = {"online_retail": cross_online_retail, "wholesale": cross_wholesale}.get(args.set)
    reg = cross.registry() if cross else demo.demo_registry()
    con = ingest.prepare(reg)
    today = pipeline.data_today(con, reg)
    if not cross:
        assert today.year == 2025 and today.month >= 10, f"gold dates assume data ends in Q4 2025, got {today}"

    from locallens.nlu.slm import SLM

    slm = SLM(args.model, prompt_style=args.prompt_style) if args.model else SLM(prompt_style=args.prompt_style)
    print("model:", args.model or "default", "| prompt:", slm.prompt_style, "| rules:", args.rules)
    slm.llm.create_chat_completion(messages=[{"role": "user", "content": "hi"}], max_tokens=1)  # warm-up

    term_index = None
    emb_path = Path(__file__).resolve().parent.parent / "models" / "bge-small-en-v1.5-q8_0.gguf"
    if not args.no_embeddings and emb_path.exists():
        from locallens.nlu.embeddings import LlamaEmbedder, TermIndex

        term_index = TermIndex(LlamaEmbedder(emb_path), reg)
    print("matching by meaning:", "on" if term_index else "off")
    mod = {"gold": gold_set, "heldout": heldout, "heldout2": heldout2, "heldout3": heldout3, "heldout4": heldout4,
           "online_retail": cross_online_retail, "wholesale": cross_wholesale}[args.set]
    items = mod.QUESTIONS[args.start: args.limit]
    tags_of = getattr(mod, "TAGS", {})
    fy_reg = reg.model_copy(update={"fiscal_start_month": 4})      # questions tagged indian_fy use the April-March year
    hits = dict(intent=0, metric=0, dimension=0, time=0, filters=0, execution=0, chart=0)
    raw_hits = dict(intent=0, metric_column=0, dimension=0)   # the model's own answer, before rules and grounding
    lat, fails, asked, rows = [], [], 0, []
    answerable = n_ask = 0
    answered_wrongly = 0
    for q, gold, gold_chart, *extra in items:
        tg = tags_of.get(q, set())
        rg = fy_reg if "indian_fy" in tg else reg
        res = pipeline.ask(q, rg, con, slm, Session(), term_index=term_index, rules_mode=args.rules)
        if res.timings_ms.get("total"):
            lat.append(res.timings_ms["total"])
        if gold is None:                                       # the right behaviour is to ask or to refuse
            n_ask += 1
            ok = res.df is None and bool(res.clarification or res.error)
            answered_wrongly += not ok
            rows.append(dict(q=q, kind="should_ask", tags=sorted(tg), ok=bool(ok), asked=bool(res.clarification), raw_ok=None))
            if not ok:
                fails.append((q, f"should have asked or refused, but answered: {res.frame.model_dump_json() if res.frame else '?'}"))
            continue
        answerable += 1
        g = QueryFrame.model_validate(gold)
        gdf, gchart = gold_result(g, reg, con, extra[0] if extra and extra[0] else None)
        gold_chart = gold_chart or gchart
        raw_ok = None
        if res.raw_frame:
            rf = QueryFrame.model_validate_json(res.raw_frame)
            raw_hits["intent"] += rf.intent == g.intent
            raw_hits["metric_column"] += rf.metric.column == g.metric.column
            raw_hits["dimension"] += rf.dimension == g.dimension
            raw_ok = rf.intent == g.intent and rf.metric.column == g.metric.column and rf.dimension == g.dimension
        f = res.frame
        row = dict(q=q, kind="question", tags=sorted(tg), ok=False, asked=bool(res.clarification), raw_ok=raw_ok,
                   ms=res.timings_ms.get("total"))
        rows.append(row)
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
        row["ok"] = bool(ok)
        hits["execution"] += ok
        hits["chart"] += bool(res.chart) and res.chart.type == gold_chart
        if not ok:
            fails.append((q, f"got {f.model_dump_json()}\n     want {g.model_dump_json()}\n     model {res.raw_frame}"))

    seq_rows = []
    if args.set == "heldout4" and not args.no_sequences:
        for tg, turns in heldout4.SEQUENCES:
            rg = fy_reg if "indian_fy" in tg else reg
            session, res = Session(), None
            for q, _ in turns:
                res = pipeline.ask(q, rg, con, slm, session, term_index=term_index, rules_mode=args.rules,
                                   followup=pipeline.is_followup(q, session, rg))
                if res.timings_ms.get("total"):
                    lat.append(res.timings_ms["total"])
            gold_final = QueryFrame.model_validate(turns[-1][1])
            gdf, _ = gold_result(gold_final, reg, con)
            ok = res.df is not None and not res.error and not res.clarification and same(res.df, gdf)
            seq_rows.append(dict(q=" -> ".join(t[0] for t in turns), kind="sequence", tags=sorted(tg), ok=bool(ok), asked=False, raw_ok=None))
            if not ok:
                got = res.frame.model_dump_json() if res.frame else (res.error or "asked")
                fails.append((" -> ".join(t[0] for t in turns), f"final turn got {got}\n     want {gold_final.model_dump_json()}"))

    n = answerable
    print(f"\n{n + n_ask + len(seq_rows)} cases: {n} answerable questions" + (f", {n_ask} that should be refused or asked about" if n_ask else "")
          + (f", {len(seq_rows)} multi-turn conversations" if seq_rows else ""))
    for k, v in hits.items():
        print(f"  {k:<10} {pct(v, n)}  ({v}/{n})")
    print("  model alone (before rules):", ", ".join(f"{k} {pct(v, n).strip()}" for k, v in raw_hits.items()))
    if asked:
        print(f"  asked a clarifying question instead of answering: {asked} (counted as not answered above)")
    if n_ask:
        print(f"  should-ask handled correctly: {ci(n_ask - answered_wrongly, n_ask)}  |  over-asking: {asked}/{n}  |  under-asking: {answered_wrongly}/{n_ask}")
    if lat:
        qs = statistics.quantiles(lat, n=20)
        print(f"  latency    p50 {statistics.median(lat):.0f} ms | p95 {qs[18]:.0f} ms | max {max(lat):.0f} ms")
    allrows = rows + seq_rows
    if tags_of:
        print(f"\n  execution accuracy (95% interval) | model alone: intent+metric+dimension right")
        print(f"  {'all answerable':<20} {ci(hits['execution'], n):<18} {ci(sum(bool(r['raw_ok']) for r in rows if r['kind'] == 'question'), n)}")
        by_tag = sorted({t for r in allrows for t in r["tags"]})
        for t in by_tag:
            sel = [r for r in allrows if t in r["tags"]]
            if t == "should_ask":
                continue
            raw = [r for r in sel if r["raw_ok"] is not None]
            print(f"  {t:<20} {ci(sum(r['ok'] for r in sel), len(sel)):<18} {ci(sum(bool(r['raw_ok']) for r in raw), len(raw)) if raw else '-':<18} n={len(sel)}")
        if seq_rows:
            print(f"  {'multi-turn (final)':<20} {ci(sum(r['ok'] for r in seq_rows), len(seq_rows))}  n={len(seq_rows)}")
    if args.out:
        args.out.write_text("\n".join(json.dumps(r) for r in allrows) + "\n")
    if args.show_failures:
        print("\nFailures:")
        for q, why in fails:
            print(f" - {q}\n     {why}")


if __name__ == "__main__":
    main()
