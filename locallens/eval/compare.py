"""Compare two eval runs on the same questions (the --out files of run_eval.py): accuracy, per-tag change, paired McNemar test.

    python eval/compare.py docs/results/base_full_always_heldout4.jsonl docs/results/ft_compact_always_heldout4.jsonl

McNemar (exact, two-sided) looks only at the questions where exactly one run is right: b = A right and B wrong,
c = A wrong and B right. If the two runs were equally good, b and c would split about evenly; p is the chance of a split at
least this uneven. It uses the SAME questions, so it is far more sensitive than comparing two accuracy intervals.
"""
from __future__ import annotations

import json
import sys
from math import comb
from pathlib import Path


def load(path: str) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def compare(a: list[dict], b: list[dict]) -> dict:
    assert [r["q"] for r in a] == [r["q"] for r in b], "the two runs must cover the same questions in the same order"
    ok_a, ok_b = [bool(r["ok"]) for r in a], [bool(r["ok"]) for r in b]
    only_a = sum(x and not y for x, y in zip(ok_a, ok_b))
    only_b = sum(y and not x for x, y in zip(ok_a, ok_b))
    out = {"n": len(a), "acc_a": sum(ok_a) / len(a), "acc_b": sum(ok_b) / len(a), "only_a": only_a, "only_b": only_b,
           "p": mcnemar_exact(only_a, only_b), "tags": {}}
    for t in sorted({t for r in a for t in r["tags"]}):
        idx = [i for i, r in enumerate(a) if t in r["tags"]]
        ta, tb = sum(ok_a[i] for i in idx), sum(ok_b[i] for i in idx)
        out["tags"][t] = (len(idx), ta, tb)
    return out


def main() -> None:
    a, b = load(sys.argv[1]), load(sys.argv[2])
    r = compare(a, b)
    print(f"{r['n']} cases | A {100 * r['acc_a']:.1f}% | B {100 * r['acc_b']:.1f}% | only A right: {r['only_a']} | only B right: {r['only_b']} | McNemar p = {r['p']:.4f}")
    for t, (n, ta, tb) in r["tags"].items():
        print(f"  {t:<20} n={n:<4} A {100 * ta / n:5.1f}%  B {100 * tb / n:5.1f}%  ({tb - ta:+d})")


if __name__ == "__main__":
    main()
