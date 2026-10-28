from datetime import date

import pytest

from locallens.nlu.preprocess import preprocess
from locallens.nlu.slm import build_messages
from locallens.query.frame import QueryFrame

TODAY = date(2025, 12, 31)


def test_full_prompt_has_the_fixed_examples_and_compact_does_not(sreg):
    pre = preprocess("monthly sales for 2024 by category", sreg, TODAY)
    full, compact = build_messages(pre, sreg), build_messages(pre, sreg, style="compact")
    assert len(full) >= 13 and len(compact) == 2
    assert full[0] == compact[0] and full[-1] == compact[-1]          # same system text and same final question
    assert "[resolved date range: 2024-01-01 to 2024-12-31" in compact[-1]["content"]
    assert "sales = sales_amt" in compact[-1]["content"]


def test_previous_frame_is_part_of_the_question(sreg):
    prev = QueryFrame.model_validate({"intent": "comparison", "metric": {"column": "sales_amt", "agg": "SUM"}, "dimension": "category"})
    msgs = build_messages(preprocess("now only 2024", sreg, TODAY), sreg, prev, "compact")
    assert msgs[-1]["content"].startswith("Previous frame: ") and "New request: now only 2024" in msgs[-1]["content"]


def test_unknown_style_is_refused(sreg):
    with pytest.raises(ValueError):
        build_messages(preprocess("total sales", sreg, TODAY), sreg, style="tiny")
