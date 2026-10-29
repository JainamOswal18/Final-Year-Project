import json
import random
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "finetune"), str(ROOT / "eval")]

import build_data  # noqa: E402
import synth  # noqa: E402
from locallens.query.frame import QueryFrame, build_schema  # noqa: E402


def small():
    return build_data.build(6, 25, 3, build_data.test_questions(), n_val=2)


def test_same_seed_gives_the_same_data():
    a, b = small(), small()
    assert [e["messages"][-1]["content"] for e in a[0]] == [e["messages"][-1]["content"] for e in b[0]]


def test_train_and_validation_use_different_schemas():
    train, val, _ = small()
    assert {e["meta"]["schema"] for e in train}.isdisjoint({e["meta"]["schema"] for e in val})


def test_no_test_question_is_in_the_training_data():
    held = build_data.test_questions()
    train, val, _ = small()
    assert not any(synth.norm(e["meta"]["question"]) in held for e in train + val)


def test_every_answer_is_a_valid_frame_in_the_schemas_field_order():
    train, _, _ = small()
    assert train
    for e in train:
        out = json.loads(e["messages"][-1]["content"])
        QueryFrame.model_validate(out)
        assert list(out) == [k for k in synth.FRAME_KEYS if k in out]
        assert e["messages"][-2]["role"] == "user" and e["messages"][0]["role"] == "system"


def test_answers_only_name_columns_of_their_schema():
    rng = random.Random(1)
    sc = synth.make_schema(rng, 0)
    gen = synth.Gen(sc, rng)
    props = build_schema(sc.reg)["properties"]
    for _ in range(40):
        q, info = gen.make(rng.choice(["comparison", "summary", "ranking", "trend"]))
        fr = synth.build_frame(sc, info, synth.preprocess(q, sc.reg, sc.today))
        if fr:
            assert fr["metric"]["column"] in props["metric"]["properties"]["column"]["enum"]
            assert fr["dimension"] in props["dimension"]["enum"]


def test_followup_prompts_carry_the_previous_frame():
    train, _, _ = small()
    fu = [e for e in train if e["meta"]["kind"] == "followup"]
    assert fu and all("Previous frame: " in e["messages"][-2]["content"] for e in fu)


def test_wide_schemas_teach_the_specific_metric_over_the_generic_word():
    rng = random.Random(11)
    sc = synth.make_schema(rng, 0, wide=True)
    gen = synth.Gen(sc, rng)
    both = alone = 0
    for _ in range(300):
        q, info = gen.make(rng.choice(["summary", "comparison", "ranking"]))
        pre = synth.preprocess(q, sc.reg, sc.today)
        hinted = set(pre.column_hints.values())
        if info["m"] in sc.group_cols and sc.total in hinted:
            both += 1                                   # "bakery sales": two hints, the group column is the answer
        if info["m"] == sc.total and not (set(sc.group_cols) & hinted):
            alone += 1                                  # "total sales": the generic total is the answer
    assert both > 20 and alone > 20


def test_training_vocabulary_stays_apart_from_the_wholesale_test():
    banned = {"fresh", "milk", "grocery", "frozen", "dairy", "deli", "delicatessen", "cleaning", "detergents", "spend"}
    names = set(synth.GROUP_COLUMNS) | set(synth.GENERIC_WORDS)
    assert not names & banned and "spend" not in " ".join(synth.GENERIC_WORDS)
