"""The small language model: question (+ tagged schema) -> QueryFrame.

The model never writes SQL. Its output is forced into the frame's JSON schema, where
every column field is an enum of the user's tagged columns.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from rapidfuzz import fuzz

from ..query.frame import INTENTS, QueryFrame, build_schema
from .preprocess import Preprocessed
from ..data.registry import Registry

DEFAULT_MODEL = Path(__file__).resolve().parents[3] / "models" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"

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
        if c.tag == "ignore" or not c.flat_name or c.error:
            continue
        desc = f" - {c.description}" if c.description else ""
        extra = f" synonyms: {', '.join(c.synonyms)}" if c.synonyms else ""
        vals = f" values: {', '.join(c.samples[:6])}" if c.samples else ""
        lines.append(f"- {c.flat_name} ({c.tag}){desc}{extra}{vals}")
    for m in reg.active_measures():
        desc = f" - {m.description}" if m.description else ""
        syn = [m.label, *m.synonyms] if m.label else m.synonyms
        extra = f" synonyms: {', '.join(syn)}" if syn else ""
        lines.append(f"- {m.name} (metric){desc}{extra}")
    return "\n".join(lines)


def similar_examples(reg: Registry, question: str, k: int = 3) -> list[tuple[str, dict]]:
    """The user's verified questions closest to this one, least similar first (the last example counts most)."""
    scored = sorted(((fuzz.token_set_ratio(question.lower(), e.question.lower()), e) for e in reg.examples),
                    key=lambda x: x[0])
    return [(e.question, e.frame) for score, e in scored[-k:] if score >= 50]


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


PROMPT_STYLES = ("full", "compact")


def build_messages(pre: Preprocessed, reg: Registry, prev: QueryFrame | None = None, style: str = "full") -> list[dict]:
    """The exact chat the model receives. One function for the app and for fine-tuning data, so they cannot drift.

    full: system text, columns, 6 fixed examples and the closest verified examples.
    compact: system text and columns only (a fine-tuned model does not need the examples; the prompt is much shorter)."""
    if style not in PROMPT_STYLES:
        raise ValueError(f"style must be one of {PROMPT_STYLES}")
    about = f"\n\nAbout the data: {reg.description}" if reg.description else ""
    system = f"{SYSTEM}{about}\n\nColumns:\n{describe_columns(reg)}"
    messages = [{"role": "system", "content": system}]
    if style == "full":
        for q, frame in [*_examples(reg), *similar_examples(reg, pre.text)]:
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
    return messages


class GenerationTimeout(TimeoutError):
    """The model did not finish within its time budget (machine overloaded or generation stalled)."""


class SLM:
    def __init__(self, model_path: str | Path = DEFAULT_MODEL, n_ctx: int = 2048, n_threads: int | None = None,
                 time_budget_s: float = 30.0, prompt_style: str | None = None):
        self.time_budget_s = time_budget_s
        self.prompt_style = prompt_style or os.environ.get("LOCALLENS_PROMPT_STYLE", "full")
        from llama_cpp import Llama  # imported lazily so the rest of the package works without it

        if not Path(model_path).exists():
            raise FileNotFoundError(f"Model not found at {model_path}. Run: python scripts/download_model.py")
        self.llm = Llama(
            model_path=str(model_path), n_ctx=n_ctx, n_threads=n_threads,
            n_gpu_layers=0,  # CPU only, matching the patent's no-GPU claim
            verbose=False,
        )

    def _tokens(self, messages: list[dict]) -> int:
        return len(self.llm.tokenize("".join(m["content"] for m in messages).encode())) + 12 * len(messages)

    def _fit(self, messages: list[dict]) -> list[dict]:
        """Keep the prompt inside the context window: drop few-shot examples (oldest first) if needed."""
        budget = self.llm.n_ctx() - 320          # room for the answer
        while self._tokens(messages) > budget and len(messages) > 2:
            del messages[1:3]                    # one example = a user and an assistant message
        if self._tokens(messages) > budget:
            raise ValueError("The dataset definition (columns, descriptions) is too long for the model. "
                             "Shorten descriptions or tag fewer columns.")
        return messages

    def fill_frame(
        self, pre: Preprocessed, reg: Registry, prev: QueryFrame | None = None
    ) -> tuple[QueryFrame, str]:
        schema = build_schema(reg)
        messages = build_messages(pre, reg, prev, self.prompt_style)
        messages = self._fit(messages)
        stream = self.llm.create_chat_completion(
            messages=messages,
            response_format={"type": "json_object", "schema": schema},
            temperature=0.0,
            max_tokens=256,
            stream=True,
        )
        started, parts = time.monotonic(), []
        for chunk in stream:
            parts.append(chunk["choices"][0]["delta"].get("content") or "")
            if time.monotonic() - started > self.time_budget_s:
                stream.close()
                raise GenerationTimeout(
                    f"The language model did not answer within {self.time_budget_s:.0f} s. "
                    "The machine may be busy; please try again.")
        raw = "".join(parts)
        return QueryFrame.model_validate_json(raw), raw
