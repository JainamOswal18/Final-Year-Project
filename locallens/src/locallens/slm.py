"""The small language model: question (+ tagged schema) -> QueryFrame.

The model never writes SQL. Its output is forced into the frame's JSON schema, where
every column field is an enum of the user's tagged columns.
"""
from __future__ import annotations

import json
from pathlib import Path

from .frame import INTENTS, QueryFrame, build_schema
from .preprocess import Preprocessed
from .registry import Registry

DEFAULT_MODEL = Path(__file__).resolve().parents[2] / "models" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"

SYSTEM = """You turn analytics questions into a JSON query frame. Output JSON only.

intent is one of:
- trend: change over time ("monthly", "over time", "growth")
- comparison: compare groups ("compare", "by", "versus")
- distribution: spread of values ("distribution", "histogram")
- proportion: share of a whole ("share", "proportion", "percent")
- ranking: top/bottom items ("top 10", "best", "rank")
- summary: one total ("total", "overall", "how much")

Rules: use only the listed columns. dimension is the column to group by, else null. \
Use the resolved date range if given. List a field in "ambiguous" only if the question \
could mean more than one column."""


def describe_columns(reg: Registry) -> str:
    lines = []
    for c in reg.columns:
        if c.tag == "ignore" or not c.flat_name:
            continue
        extra = f" synonyms: {', '.join(c.synonyms)}" if c.synonyms else ""
        vals = f" values: {', '.join(c.samples[:6])}" if c.samples else ""
        lines.append(f"- {c.flat_name} ({c.tag}){extra}{vals}")
    return "\n".join(lines)


def _examples(reg: Registry) -> list[tuple[str, dict]]:
    """One example per intent, built from this dataset's own first columns."""
    m = next(iter(reg.tagged("metric")), None)
    d = next(iter(reg.tagged("dimension")), None)
    t = next(iter(reg.tagged("date")), None)
    if not (m and d):
        return []
    mm = m.synonyms[0] if m.synonyms else m.flat_name
    dd = d.synonyms[0] if d.synonyms else d.flat_name
    metric = {"column": m.flat_name, "agg": "SUM"}
    base = {"filters": [], "top_n": None, "ambiguous": []}
    time = (
        {"column": t.flat_name, "grain": "month", "start": "2024-01-01", "end": "2024-12-31"} if t else None
    )
    ex = [
        (f"monthly {mm} for 2024", {"intent": "trend", "metric": metric, "dimension": None, "time": time, **base}),
        (f"compare {mm} by {dd}", {"intent": "comparison", "metric": metric, "dimension": d.flat_name, "time": None, **base}),
        (f"top 5 {dd} by {mm}", {"intent": "ranking", "metric": metric, "dimension": d.flat_name, "time": None, **{**base, "top_n": 5}}),
        (f"what share of {mm} comes from each {dd}", {"intent": "proportion", "metric": metric, "dimension": d.flat_name, "time": None, **base}),
        (f"distribution of {mm}", {"intent": "distribution", "metric": metric, "dimension": None, "time": None, **base}),
        (f"total {mm}", {"intent": "summary", "metric": metric, "dimension": None, "time": None, **base}),
    ]
    if not t:
        for _, f in ex:
            f.pop("time", None)
    return ex


class SLM:
    def __init__(self, model_path: str | Path = DEFAULT_MODEL, n_ctx: int = 2048, n_threads: int | None = None):
        from llama_cpp import Llama  # imported lazily so the rest of the package works without it

        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model not found at {model_path}. Run: python scripts/download_model.py")
        self.llm = Llama(
            model_path=str(model_path), n_ctx=n_ctx, n_threads=n_threads,
            n_gpu_layers=0,  # CPU only, matching the patent's no-GPU claim
            verbose=False,
        )

    def fill_frame(
        self, pre: Preprocessed, reg: Registry, prev: QueryFrame | None = None
    ) -> tuple[QueryFrame, str]:
        schema = build_schema(reg)
        system = f"{SYSTEM}\n\nColumns:\n{describe_columns(reg)}"
        messages = [{"role": "system", "content": system}]
        for q, frame in _examples(reg):
            messages += [{"role": "user", "content": q}, {"role": "assistant", "content": json.dumps(frame)}]
        user = pre.text
        if pre.date_hint:
            h = pre.date_hint
            user += f"\n[resolved date range: {h.start} to {h.end}" + (f", grain {h.grain}" if h.grain else "") + "]"
        if pre.column_hints:
            user += "\n[column hints: " + ", ".join(f"{p} = {c}" for p, c in pre.column_hints.items()) + "]"
        if prev is not None:
            user = (
                f"Previous frame: {prev.model_dump_json()}\n"
                f"If the new request only changes it (e.g. 'now by region', 'only 2024'), return the full updated frame; "
                f"otherwise ignore the previous frame.\nNew request: {user}"
            )
        messages.append({"role": "user", "content": user})
        out = self.llm.create_chat_completion(
            messages=messages,
            response_format={"type": "json_object", "schema": schema},
            temperature=0.0,
            max_tokens=256,
        )
        raw = out["choices"][0]["message"]["content"]
        return QueryFrame.model_validate_json(raw), raw
