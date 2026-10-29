"""Build the fine-tuning data: finetune/data/{train,val}.jsonl, plus stats.json.

    python -I finetune/build_data.py [--schemas 96] [--per-schema 80] [--seed 7]

Every line is {"messages": [system, (examples...), user, assistant], "meta": {...}}: the prompt is built by the
app's own build_messages(), the last message is the frame the model must write. Train and validation use DIFFERENT
schemas (split by schema, not by row), so validation measures transfer to datasets the model never saw.
Questions that equal a test question (heldout sets, cross-schema sets) are removed before writing.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "eval"), str(ROOT / "finetune")]

import synth  # noqa: E402
from locallens.nlu.preprocess import preprocess  # noqa: E402

OUT = ROOT / "finetune" / "data"
MIX = [("trend", .15), ("comparison", .20), ("ranking", .15), ("proportion", .07), ("distribution", .05), ("summary", .17),
       ("followup", .11), ("ambiguous", .03), ("hinglish", .07)]
SOURCES = {"synthetic": "our own templates and vocabulary (finetune/synth.py)"}


def test_questions() -> set[str]:
    """Every question of every evaluation set: none may appear in the training data."""
    import cross_online_retail
    import cross_wholesale
    import heldout
    import heldout2
    import heldout3
    import heldout4
    import questions as gold

    qs = set()
    for mod in (gold, heldout, heldout2, heldout3, heldout4, cross_online_retail, cross_wholesale):
        qs |= {synth.norm(q[0]) for q in mod.QUESTIONS}
    for _, turns in heldout4.SEQUENCES:
        qs |= {synth.norm(t[0]) for t in turns}
    return qs


def build(n_schemas: int, per_schema: int, seed: int, held_out: set[str], n_val: int = 16, wide_share: int = 3, compact_share: float = 0.5) -> tuple[list[dict], list[dict], dict]:
    rng = random.Random(seed)
    train, val = [], []
    seen: set[tuple] = set()
    dropped = Counter()
    for i in range(n_schemas):
        sc = synth.make_schema(rng, i, wide=(i % 10) < wide_share)
        gen = synth.Gen(sc, rng)
        verified = synth.verified_examples(gen, rng.choice([0, 0, 1, 2, 3]))
        from locallens.data.registry import Example
        sc.reg.examples = [Example(**e) for e in verified]
        bucket = val if i >= n_schemas - n_val else train
        made = 0
        tries = 0
        while made < per_schema and tries < per_schema * 6:
            tries += 1
            kind = rng.choices([k for k, _ in MIX], [w for _, w in MIX])[0]
            style = "compact" if rng.random() < compact_share else "full"
            meta = {"schema": i, "kind": kind}
            if kind == "followup":
                base_kind = rng.choice(["comparison", "summary", "trend", "ranking", "proportion"])
                q0, info0 = gen.make(base_kind)
                pre0 = preprocess(q0, sc.reg, sc.today)
                if not synth.resolves(sc, pre0, info0):
                    dropped["followup base unresolved"] += 1
                    continue
                prev = synth.build_frame(sc, info0, pre0)
                if prev is None:
                    continue
                fu = synth.followup(gen, prev)
                if fu is None:
                    continue
                question, fr, _ = fu
                ex = synth.make_example(sc, synth.dress(question, rng) if rng.random() < .3 else question, fr, prev, style, meta)
            else:
                question, info = gen.make(kind)
                pre = preprocess(question, sc.reg, sc.today)
                if kind != "hinglish" and not synth.resolves(sc, pre, info):
                    dropped[f"{kind} unresolved"] += 1
                    continue
                if kind == "hinglish":
                    hinted = set(pre.column_hints.values())
                    if info["m"] not in hinted or (info.get("dim") and info["dim"] not in hinted) or pre.ambiguous_terms:
                        dropped["hinglish unresolved"] += 1
                        continue
                fr = synth.build_frame(sc, info, pre)
                if fr is None:
                    dropped[f"{kind} no date"] += 1
                    continue
                ex = synth.make_example(sc, synth.dress(question, rng) if rng.random() < .4 else question, fr, None, style, meta)
            if ex is None:
                continue
            qn = synth.norm(ex["meta"]["question"])
            if qn in held_out:
                dropped["same as a test question"] += 1
                continue
            key = (i, qn, ex["messages"][-1]["content"], style)
            if key in seen:
                dropped["duplicate"] += 1
                continue
            seen.add(key)
            bucket.append(ex)
            made += 1
    return train, val, dict(dropped)


def drop_near_test(examples: list[dict], held_list: list[str], cutoff: float = 90) -> tuple[list[dict], int]:
    """Also drop questions that are all but identical (fuzzy match >= 90) to a test question."""
    from rapidfuzz import fuzz, process

    keep, dropped = [], 0
    for ex in examples:
        hit = process.extractOne(synth.norm(ex["meta"]["question"]), held_list, scorer=fuzz.ratio, score_cutoff=cutoff)
        if hit:
            dropped += 1
        else:
            keep.append(ex)
    return keep, dropped


def token_filter(examples: list[dict], limit: int) -> tuple[list[dict], int]:
    """Drop examples longer than the prompt budget the app enforces (n_ctx 2048 minus room for the answer)."""
    from locallens.nlu.slm import DEFAULT_MODEL
    from llama_cpp import Llama

    llm = Llama(model_path=str(DEFAULT_MODEL), vocab_only=True, verbose=False)
    keep, dropped = [], 0
    for ex in examples:
        n = len(llm.tokenize("".join(m["content"] for m in ex["messages"]).encode())) + 12 * len(ex["messages"])
        ex["meta"]["tokens"] = n
        if n <= limit:
            keep.append(ex)
        else:
            dropped += 1
    return keep, dropped


def leakage(train: list[dict]) -> dict:
    """How close are the test questions to the training questions? (fuzzy match, 0-100)."""
    from rapidfuzz import fuzz, process
    import heldout4

    pool = list({synth.norm(e["meta"]["question"]) for e in train})
    scores = []
    for q, *_ in heldout4.QUESTIONS:
        hit = process.extractOne(synth.norm(q), pool, scorer=fuzz.ratio)
        scores.append(hit[1])
    scores.sort()
    n = len(scores)
    return {"heldout4_questions": n, "median_closest_training_question": round(scores[n // 2], 1),
            "share_ge_90": round(sum(s >= 90 for s in scores) / n, 3), "share_ge_95": round(sum(s >= 95 for s in scores) / n, 3), "max": round(scores[-1], 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--schemas", type=int, default=96)
    ap.add_argument("--per-schema", type=int, default=80)
    ap.add_argument("--val-schemas", type=int, default=16)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--wide-share", type=int, default=3, help="out of every 10 schemas, how many are wide (product-group columns plus a generic total)")
    ap.add_argument("--compact-share", type=float, default=0.5, help="share of examples with the compact prompt")
    ap.add_argument("--out", type=Path, help="write the files here instead of finetune/data")
    ap.add_argument("--token-limit", type=int, default=2048 - 320)
    args = ap.parse_args()
    held = test_questions()
    train, val, dropped = build(args.schemas, args.per_schema, args.seed, held, args.val_schemas, args.wide_share, args.compact_share)
    held_list = sorted(held)
    train, near_t = drop_near_test(train, held_list)
    val, near_v = drop_near_test(val, held_list)
    dropped["nearly the same as a test question"] = near_t + near_v
    train, td = token_filter(train, args.token_limit)
    val, vd = token_filter(val, args.token_limit)
    out = args.out or OUT
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("val", val)):
        (out / f"{name}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    stats = {
        "seed": args.seed, "schemas": args.schemas, "train": len(train), "val": len(val),
        "dropped": {**dropped, "over the token limit": td + vd},
        "kinds": dict(Counter(r["meta"]["kind"] for r in train)), "styles": dict(Counter(r["meta"]["style"] for r in train)),
        "tokens": {"median": sorted(r["meta"]["tokens"] for r in train)[len(train) // 2], "max": max(r["meta"]["tokens"] for r in train)},
        "followups_with_previous_frame": sum("Previous frame" in r["messages"][-2]["content"] for r in train),
        "leakage_vs_heldout4": leakage(train), "sources": SOURCES,
    }
    (out / "stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
