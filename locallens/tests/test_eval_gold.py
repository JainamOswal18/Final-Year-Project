"""The gold set itself must be valid: every gold frame runs and yields its stated chart."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
from questions import QUESTIONS  # noqa: E402

from locallens.data import engine  # noqa: E402
from locallens.viz.charts import build_spec  # noqa: E402
from locallens.query.frame import QueryFrame  # noqa: E402
from locallens.data.profiler import profile  # noqa: E402
from locallens.query.sqlgen import build_sql  # noqa: E402
from locallens.query.validator import validate_frame, validate_sql  # noqa: E402


@pytest.mark.parametrize("question,gold,chart", QUESTIONS, ids=[q[0][:40] for q in QUESTIONS])
def test_gold_frame_is_valid(sreg, scon, question, gold, chart):
    reg, con = sreg, scon
    frame = QueryFrame.model_validate(gold)
    validate_frame(frame, reg)
    sql = build_sql(frame, reg)
    validate_sql(sql, reg)
    df = engine.run(con, sql)
    assert not df.empty
    assert build_spec(df, frame.intent, profile(df)).type == chart
