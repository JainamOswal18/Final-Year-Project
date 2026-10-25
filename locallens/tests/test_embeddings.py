"""Claim 7: matching by meaning. Logic is tested with a stand-in embedder; one test uses the real model if present."""
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from locallens.core import pipeline
from locallens.nlu.embeddings import LlamaEmbedder, TermIndex, semantic_matches
from locallens.nlu.preprocess import preprocess
from tests.test_pipeline import FakeSLM, M

TODAY = date(2025, 12, 31)


class FakeEmbedder:
    """Words become vectors along hand-made 'meaning' axes, so similarity is exact and predictable."""
    AXES = {"store": ["store", "boutique", "outlet"], "sales": ["sales", "revenue", "turnover", "takings"], "profit": ["profit", "earnings"],
            "region": ["region", "area", "geography"]}

    def vec(self, text):
        v = np.zeros(len(self.AXES) + 1)
        for i, words in enumerate(self.AXES.values()):
            if any(w in text for w in words):
                v[i] = 1.0
        if not v.any():
            v[-1] = 1.0
        return v

    def embed(self, texts):
        m = np.array([self.vec(t) for t in texts])
        return m / np.linalg.norm(m, axis=1, keepdims=True)


@pytest.fixture()
def index(sreg):
    return TermIndex(FakeEmbedder(), sreg)


def test_an_unknown_word_is_matched_to_the_column_it_means(sreg, index):
    pre = preprocess("sales by boutique", sreg, TODAY, index)
    assert pre.semantic == [("boutique", "store_name")] and pre.column_hints["boutique"] == "store_name"
    # "area" is as close to the customer region as to the store region: two equal candidates, so it is refused
    assert preprocess("profit by area", sreg, TODAY, index).semantic == []


def test_words_with_no_close_meaning_are_left_alone(sreg, index):
    pre = preprocess("hello there, bananas and football", sreg, TODAY, index)
    assert pre.semantic == []
    assert not pipeline.looks_like_data_question(pre, sreg)


def test_direct_matches_are_never_second_guessed(sreg, index):
    pre = preprocess("sales by store", sreg, TODAY, index)
    assert pre.semantic == [] and pre.column_hints["store"] == "store_name"


def test_without_an_index_nothing_changes(sreg):
    assert preprocess("sales by boutique", sreg, TODAY).semantic == []


def test_helper_words_and_known_vocabulary_are_skipped(sreg, index):
    assert semantic_matches("show total", set(), index, {"show", "total"}) == []
    assert semantic_matches("sales", set(), index, set()) == []          # already a known word


def test_ambiguous_meaning_is_refused(sreg):
    class Tie(FakeEmbedder):
        def vec(self, text):
            return np.array([1.0, 1.0, 0, 0, 0]) if "boutique" in text else super().vec(text)
    assert preprocess("sales by boutique", sreg, TODAY, TermIndex(Tie(), sreg)).semantic == []


def test_the_match_reaches_the_answer(sreg, scon, index):
    slm = FakeSLM({"intent": "comparison", "metric": M, "dimension": "store_name"})
    res = pipeline.ask("sales by boutique", sreg, scon, slm, term_index=index)
    assert res.error == "" and res.semantic == [("boutique", "store_name")] and res.frame.dimension == "store_name"


@pytest.mark.skipif(not Path("models/bge-small-en-v1.5-q8_0.gguf").exists(), reason="embedding model not downloaded")
def test_real_embedding_model_finds_synonyms_and_rejects_chatter(sreg):
    index = TermIndex(LlamaEmbedder("models/bge-small-en-v1.5-q8_0.gguf"), sreg)
    assert preprocess("sales by boutique", sreg, TODAY, index).column_hints.get("boutique") == "store_name"
    assert preprocess("profit by area", sreg, TODAY, index).column_hints.get("area") == "store_region"
    for chatter in ("hi there", "hello", "thanks a lot", "what is the weather", "please give me bananas"):
        assert preprocess(chatter, sreg, TODAY, index).semantic == [], chatter


def test_plural_forms_are_matched(sreg, index):
    assert preprocess("top 3 boutiques by profit", sreg, TODAY, index).semantic == [("boutiques", "store_name")]


def test_function_words_are_never_matched(sreg):
    class Greedy(FakeEmbedder):
        def vec(self, text):
            return self.AXES and np.array([1.0, 0, 0, 0, 0])      # everything looks like "store"
    idx = TermIndex(Greedy(), sreg)
    assert semantic_matches("much many give tell each every", set(), idx, set()) == []
