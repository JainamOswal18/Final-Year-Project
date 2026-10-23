"""Ask questions, keep conversations, give feedback, export results."""
from __future__ import annotations

import json
import logging
import secrets
import time

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from ..core import pipeline
from ..core import prefs as prefs_defaults
from ..core.session import Session
from ..data import engine
from ..data.profiler import profile
from ..data.registry import Example
from ..query.frame import QueryFrame
from ..query.sqlgen import FrameError
from ..query.validator import validate_sql
from ..viz.adapters import ADAPTERS
from ..viz.charts import build_spec
from .auth import admin_user, audit, current_user, runtime
from .routes_datasets import dataset_row
from .runtime import Runtime
from .serialize import result_payload

router = APIRouter(prefix="/api")
log = logging.getLogger("locallens")


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    conversation_id: str | None = None
    overrides: dict[str, str] | None = None


class FeedbackIn(BaseModel):
    rating: int
    note: str = Field(default="", max_length=500)


class PrefsIn(BaseModel):
    sort: str = "desc"
    chart_overrides: dict[str, str] = Field(default_factory=dict)
    default_agg: str = "SUM"


DEFAULT_AGGS = ("SUM", "AVG", "MAX", "MIN")
VALID_OVERRIDE_KEYS = {"metric", "dimension", "time", "filter"}
CHART_CHOICES = {"trend": {"line"}, "comparison": {"bar", "hbar", "donut"},
                 "ranking": {"hbar", "bar"}, "proportion": {"donut", "bar", "hbar"}}


# ---- preferences ---------------------------------------------------------------------
def load_prefs(rt: Runtime, user_id: int) -> dict:
    row = rt.db.one("SELECT json FROM prefs WHERE user_id = ?", (user_id,))
    try:
        return {**prefs_defaults.DEFAULTS, **(json.loads(row["json"]) if row else {})}
    except json.JSONDecodeError:
        return dict(prefs_defaults.DEFAULTS)


@router.get("/prefs")
def get_prefs(user=Depends(current_user), rt: Runtime = Depends(runtime)):
    p = load_prefs(rt, user["id"])
    return {"sort": p["sort"], "chart_overrides": p["chart_overrides"], "default_agg": p["default_agg"],
            "default_aggs": list(DEFAULT_AGGS), "choices": {k: sorted(v) for k, v in CHART_CHOICES.items()}}


@router.put("/prefs")
def put_prefs(body: PrefsIn, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    if body.sort not in ("asc", "desc"):
        raise HTTPException(422, "Sort must be asc or desc.")
    if body.default_agg not in DEFAULT_AGGS:
        raise HTTPException(422, f"Default aggregation must be one of {', '.join(DEFAULT_AGGS)}.")
    for intent, chart in body.chart_overrides.items():
        if chart not in CHART_CHOICES.get(intent, set()):
            raise HTTPException(422, f"{chart!r} is not available for {intent}.")
    with rt.db.tx() as c:
        c.execute("INSERT INTO prefs (user_id, json) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET json = excluded.json",
                  (user["id"], json.dumps(body.model_dump())))
    return get_prefs(user, rt)


# ---- conversations ---------------------------------------------------------------------
def _conversation(rt: Runtime, user, cid: str):
    row = rt.db.one("SELECT * FROM conversations WHERE id = ? AND user_id = ?", (cid, user["id"]))
    if row is None:
        raise HTTPException(404, "No such conversation.")
    return row


def _message(rt: Runtime, user, mid: str):
    row = rt.db.one("SELECT m.*, c.dataset_id FROM messages m JOIN conversations c ON c.id = m.conversation_id "
                    "WHERE m.id = ? AND m.user_id = ?", (mid, user["id"]))
    if row is None:
        raise HTTPException(404, "No such message.")
    return row


@router.get("/datasets/{dataset_id}/conversations")
def list_conversations(dataset_id: str, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    dataset_row(rt, user, dataset_id)
    rows = rt.db.all("SELECT id, title, updated_at FROM conversations WHERE user_id = ? AND dataset_id = ? "
                     "ORDER BY updated_at DESC LIMIT 100", (user["id"], dataset_id))
    return [dict(r) for r in rows]


@router.get("/conversations/{cid}")
def get_conversation(cid: str, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    conv = _conversation(rt, user, cid)
    msgs = rt.db.all("SELECT id, question, response_json, rating, created_at FROM messages "
                     "WHERE conversation_id = ? ORDER BY created_at, rowid", (cid,))
    return {"id": cid, "title": conv["title"], "dataset_id": conv["dataset_id"],
            "messages": [{"id": m["id"], "rating": m["rating"], "created_at": m["created_at"],
                          "response": json.loads(m["response_json"])} for m in msgs]}


@router.delete("/conversations/{cid}")
def delete_conversation(cid: str, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    _conversation(rt, user, cid)
    rt.db.run("DELETE FROM conversations WHERE id = ?", (cid,))
    return {"ok": True}


# ---- asking --------------------------------------------------------------------------------
@router.post("/datasets/{dataset_id}/ask")
def ask(dataset_id: str, body: AskIn, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    dataset_row(rt, user, dataset_id)
    overrides = body.overrides or None
    if overrides and (set(overrides) - VALID_OVERRIDE_KEYS):
        raise HTTPException(422, "Unknown override.")
    ds = rt.load_dataset(dataset_id)

    session = Session()
    conv = None
    if body.conversation_id:
        conv = _conversation(rt, user, body.conversation_id)
        if conv["dataset_id"] != dataset_id:
            raise HTTPException(404, "No such conversation.")
        if conv["last_frame"]:
            session.last_frame = QueryFrame.model_validate_json(conv["last_frame"])
    question = " ".join(body.question.split())
    followup = pipeline.is_followup(question, session, ds.reg) and not overrides

    if not rt.ask_lock.acquire(timeout=90):
        raise HTTPException(503, "The assistant is busy with other questions. Try again in a moment.")
    started = time.perf_counter()
    try:
        try:
            slm = rt.slm()
        except Exception as e:
            raise HTTPException(503, f"The language model is not available: {str(e)[:200]}") from e
        with ds.lock:
            res = pipeline.ask(question, ds.reg, ds.con, slm, session, load_prefs(rt, user["id"]),
                               followup=followup, overrides=overrides, term_index=ds.term_index)
    finally:
        rt.ask_lock.release()

    payload = result_payload(res, ds.reg, rt.settings.max_result_rows)
    payload["followup"] = followup
    cid = conv["id"] if conv else secrets.token_hex(8)
    mid = secrets.token_hex(8)
    last = res.frame.model_dump_json() if (res.frame and not res.error and res.clarification is None) else (conv["last_frame"] if conv else None)
    with rt.db.tx() as c:
        if conv is None:
            c.execute("INSERT INTO conversations (id, user_id, dataset_id, title, last_frame) VALUES (?, ?, ?, ?, ?)",
                      (cid, user["id"], dataset_id, question[:60], last))
        else:
            c.execute("UPDATE conversations SET last_frame = ?, updated_at = datetime('now') WHERE id = ?", (last, cid))
        c.execute("INSERT INTO messages (id, conversation_id, user_id, question, response_json) VALUES (?, ?, ?, ?, ?)",
                  (mid, cid, user["id"], question, json.dumps(payload)))
    log.info("ask user=%s dataset=%s ms=%.0f ok=%s", user["username"], dataset_id,
             (time.perf_counter() - started) * 1000, not res.error)
    return {"conversation_id": cid, "message_id": mid, "response": payload}


# ---- feedback, examples, export -----------------------------------------------------------------
@router.post("/messages/{mid}/feedback")
def feedback(mid: str, body: FeedbackIn, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    _message(rt, user, mid)
    if body.rating not in (-1, 0, 1):
        raise HTTPException(422, "Rating must be -1, 0 or 1.")
    rt.db.run("UPDATE messages SET rating = ?, rating_note = ? WHERE id = ?", (body.rating or None, body.note, mid))
    return {"ok": True}


@router.post("/messages/{mid}/example")
def save_example(mid: str, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    """Mark an answer as correct: its question and frame become a few-shot example for this dataset."""
    msg = _message(rt, user, mid)
    row = dataset_row(rt, user, msg["dataset_id"], write=True)
    payload = json.loads(msg["response_json"])
    if not payload.get("frame") or payload.get("error"):
        raise HTTPException(422, "Only a successful answer can be saved as an example.")
    reg = rt.registry_from_row(row)
    if any(e.question.lower() == msg["question"].lower() for e in reg.examples):
        return {"ok": True, "already": True}
    if len(reg.examples) >= 200:
        raise HTTPException(422, "This dataset already has 200 examples.")
    frame = {k: v for k, v in payload["frame"].items() if k not in ("rules", "order")}
    reg.examples.append(Example(question=msg["question"], frame=frame))
    rt.db.run("UPDATE datasets SET registry_json = ?, updated_at = datetime('now') WHERE id = ?",
              (rt.registry_to_json(reg), row["id"]))
    rt.invalidate(row["id"])
    return {"ok": True, "already": False}


def _csv_safe(v):
    """Stop spreadsheet formula injection: a text cell starting with = + - @ is shown, never run."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


@router.get("/messages/{mid}/export/{kind}")
def export(mid: str, kind: str, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    msg = _message(rt, user, mid)
    dataset_row(rt, user, msg["dataset_id"])
    payload = json.loads(msg["response_json"])
    if not payload.get("sql") or not payload.get("frame"):
        raise HTTPException(422, "There is nothing to export for this answer.")
    ds = rt.load_dataset(msg["dataset_id"])
    try:
        validate_sql(payload["sql"], ds.reg)
        with ds.lock:
            df = engine.run(ds.con, payload["sql"])
    except FrameError as e:
        raise HTTPException(422, str(e)) from e
    safe_name = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in msg["question"])[:40].strip() or "result"
    if kind == "csv":
        out = df.copy()
        for c in out.columns:
            if not (pd.api.types.is_numeric_dtype(out[c]) or pd.api.types.is_datetime64_any_dtype(out[c])):
                out[c] = out[c].map(_csv_safe)
        return Response(out.to_csv(index=False), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'})
    adapter = ADAPTERS.get(kind)
    if adapter is None:
        raise HTTPException(404, "No such export.")
    prefs = load_prefs(rt, user["id"])
    try:
        chart = build_spec(df, payload["frame"]["intent"], profile(df), prefs, payload.get("chart_forced"))
    except FrameError as e:
        raise HTTPException(422, str(e)) from e
    if not adapter.supports(chart.type):
        raise HTTPException(422, f"{adapter.label} cannot show a {chart.type} chart.")
    exp = adapter.export(df, chart, msg["question"], prefs.get("sort", "desc"))
    audit(rt, user["id"], f"export_{kind}", mid)
    return Response(exp.content, media_type=exp.mime,
                    headers={"Content-Disposition": f'attachment; filename="{exp.filename}"'})


# ---- operator views ---------------------------------------------------------------------------
@router.get("/admin/feedback")
def admin_feedback(admin=Depends(admin_user), rt: Runtime = Depends(runtime), only_negative: bool = True):
    """Answers users rated, with their frame and SQL: raw material for new evaluation questions."""
    rows = rt.db.all(
        "SELECT m.id, m.question, m.rating, m.rating_note, m.response_json, m.created_at, u.username, c.dataset_id "
        "FROM messages m JOIN users u ON u.id = m.user_id JOIN conversations c ON c.id = m.conversation_id "
        "WHERE m.rating IS NOT NULL" + (" AND m.rating < 0" if only_negative else "") + " ORDER BY m.created_at DESC LIMIT 200")
    out = []
    for r in rows:
        p = json.loads(r["response_json"])
        out.append({"id": r["id"], "user": r["username"], "dataset_id": r["dataset_id"], "question": r["question"],
                    "rating": r["rating"], "note": r["rating_note"], "created_at": r["created_at"],
                    "frame": p.get("frame"), "sql": p.get("sql"), "error": p.get("error")})
    return out
