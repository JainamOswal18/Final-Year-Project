"""Domain term matching with a small local embedding model (patent claim 7).

The dataset's own vocabulary (column names, synonyms, descriptions, metric labels) is embedded once and
kept in memory. A word in the question that matches nothing by spelling is compared with that vocabulary,
so "shop" can mean the store column. It is deliberately strict: it only fires on a clear, unambiguous
match, only for words plain matching missed, and never overrides a direct match.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from ..data.registry import Registry

MIN_SIMILARITY = 0.80      # cosine similarity needed to accept a match
MIN_MARGIN = 0.08          # and how far it must beat the next-best column
MAX_MATCHES = 3
WORD = re.compile(r"[A-Za-z]{4,}")
FUNCTION_WORDS = {"much", "many", "give", "tell", "list", "each", "every", "with", "from", "that", "this", "have", "been", "would",
                  "could", "there", "their", "where", "about", "into", "than", "then", "also", "only", "were", "does", "also",
                  "your", "yours", "ours", "some", "such", "over", "under", "between", "whose", "while", "these", "those"}


def _stems(word: str) -> list[str]:
    out = [word]
    if word.endswith("ies") and len(word) > 5:
        out.append(word[:-3] + "y")
    elif word.endswith("es") and len(word) > 5:
        out.append(word[:-2])
    if word.endswith("s") and len(word) > 4:
        out.append(word[:-1])
    return out


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


class LlamaEmbedder:
    """bge-small-en-v1.5 (35 MB GGUF) run by llama.cpp on the CPU."""

    def __init__(self, model_path: str | Path):
        from llama_cpp import Llama

        if not Path(model_path).exists():
            raise FileNotFoundError(f"Embedding model not found at {model_path}. Run: python scripts/download_model.py --embeddings")
        self._llm = Llama(model_path=str(model_path), embedding=True, n_ctx=512, n_gpu_layers=0, verbose=False)
        self._lock = threading.Lock()

    def embed(self, texts: list[str]) -> np.ndarray:
        with self._lock:
            data = self._llm.create_embedding(texts)["data"]
        v = np.array([d["embedding"] for d in data], dtype=float)
        if v.ndim == 3:                       # one vector per token -> average
            v = v.mean(axis=1)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


@dataclass
class SemanticMatch:
    word: str
    entity: str
    similarity: float


class TermIndex:
    """Embedded vocabulary of one dataset."""

    def __init__(self, embedder: Embedder, reg: Registry):
        self.embedder = embedder
        phrases: list[str] = []
        owners: list[str] = []
        for e in reg.entities():
            for p in {e.flat_name.replace("_", " "), *(s.lower().strip() for s in e.synonyms if s.strip())}:
                phrases.append(p)
                owners.append(e.flat_name)
        for c in reg.columns:
            if c.description and c.flat_name and not c.error:
                phrases.append(c.description.lower())
                owners.append(c.flat_name)
        for m in reg.active_measures():
            if m.description:
                phrases.append(m.description.lower())
                owners.append(m.name)
        self.phrases, self.owners = phrases, owners
        self.vectors = embedder.embed(phrases) if phrases else np.zeros((0, 1))
        self.known = {w for p in phrases for w in WORD.findall(p)}

    def match(self, word: str) -> SemanticMatch | None:
        if not len(self.vectors):
            return None
        sims = self.vectors @ self.embedder.embed([word])[0]
        best: dict[str, float] = {}
        for s, o in zip(sims, self.owners):
            best[o] = max(best.get(o, -1.0), float(s))
        ranked = sorted(best.items(), key=lambda kv: -kv[1])
        top_entity, top = ranked[0]
        runner = ranked[1][1] if len(ranked) > 1 else -1.0
        if top >= MIN_SIMILARITY and top - runner >= MIN_MARGIN:
            return SemanticMatch(word, top_entity, top)
        return None


def semantic_matches(text: str, covered: set[str], index: TermIndex, skip_words: set[str]) -> list[SemanticMatch]:
    """Words the lexical pass left unexplained, matched by meaning. `covered` holds words already used."""
    out, seen = [], set()
    for w in WORD.findall(text.lower()):
        forms = _stems(w)
        if w in FUNCTION_WORDS or any(f in covered or f in skip_words or f in index.known for f in forms) or w in seen:
            continue
        seen.add(w)
        hits = [m for m in (index.match(f) for f in forms) if m]
        if hits:
            best = max(hits, key=lambda m: m.similarity)
            out.append(SemanticMatch(w, best.entity, best.similarity))
        if len(out) >= MAX_MATCHES:
            break
    return out
