"""Datasets: upload, tag, define metrics and rules, preview."""
from __future__ import annotations

import json
import logging
import secrets
import shutil
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from ..data import autoprep, demo, ingest, semantic
from ..nlu import typeahead
from ..data.registry import CALC_TABLE, IDENT, Registry
from .auth import audit, current_user, runtime
from .runtime import Runtime
from .serialize import table_payload

router = APIRouter(prefix="/api")
log = logging.getLogger("locallens")


# ---- access ------------------------------------------------------------------------------
def dataset_row(rt: Runtime, user, dataset_id: str, *, write: bool = False):
    """404 (not 403) for anything the user may not touch, so ids reveal nothing."""
    row = rt.db.one("SELECT d.*, u.username AS owner_name FROM datasets d JOIN users u ON u.id = d.owner_id "
                    "WHERE d.id = ?", (dataset_id,))
    if row is None:
        raise HTTPException(404, "No such dataset.")
    mine = row["owner_id"] == user["id"] or user["role"] == "admin"
    if not (mine or (row["visibility"] == "shared" and not write)):
        raise HTTPException(404, "No such dataset.")
    return row


def _summary(rt: Runtime, row, user) -> dict:
    return {"id": row["id"], "name": row["name"], "visibility": row["visibility"], "owner": row["owner_name"],
            "can_edit": row["owner_id"] == user["id"] or user["role"] == "admin",
            "updated_at": row["updated_at"], "created_at": row["created_at"]}


# ---- storage helpers -------------------------------------------------------------------------
def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    try:
        df.to_parquet(path, index=False)
    except Exception:                                         # mixed-type object columns
        fixed = df.copy()
        for c in fixed.columns:
            if pd.api.types.is_object_dtype(fixed[c]):
                fixed[c] = fixed[c].astype("string")
        fixed.to_parquet(path, index=False)


def _finish_registry(rt: Runtime, dataset_id: str, reg: Registry) -> Registry:
    """Load once so samples/values are filled and definitions are checked."""
    con = ingest.prepare(reg)
    con.close()
    return reg


def _insert(rt: Runtime, dataset_id: str, owner_id: int, name: str, reg: Registry) -> None:
    rt.db.run("INSERT INTO datasets (id, owner_id, name, registry_json) VALUES (?, ?, ?, ?)",
              (dataset_id, owner_id, name, rt.registry_to_json(reg)))


def create_demo_dataset(rt: Runtime, user) -> str:
    dataset_id = secrets.token_hex(8)
    d = rt.dataset_dir(dataset_id)
    d.mkdir(parents=True)
    try:
        reg = demo.demo_registry()
        for t, path in list(reg.tables.items()):
            out = d / f"{t}.parquet"
            _write_parquet(pd.read_csv(path), out)
            reg.tables[t] = str(out)
        _finish_registry(rt, dataset_id, reg)
        _insert(rt, dataset_id, user["id"], "Retail demo", reg)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    return dataset_id


# ---- routes ----------------------------------------------------------------------------------------
@router.get("/datasets")
def list_datasets(user=Depends(current_user), rt: Runtime = Depends(runtime)):
    rows = rt.db.all("SELECT d.*, u.username AS owner_name FROM datasets d JOIN users u ON u.id = d.owner_id "
                     "WHERE d.owner_id = ? OR d.visibility = 'shared' ORDER BY d.updated_at DESC", (user["id"],))
    return [_summary(rt, r, user) for r in rows]


@router.post("/datasets", status_code=201)
def create_dataset(name: str = Form(..., max_length=80), files: list[UploadFile] = File(...),
                   user=Depends(current_user), rt: Runtime = Depends(runtime)):
    name = name.strip()
    if not name:
        raise HTTPException(422, "Give the dataset a name.")
    if not files or len(files) > 20:
        raise HTTPException(422, "Upload between 1 and 20 files.")
    dataset_id = secrets.token_hex(8)
    d = rt.dataset_dir(dataset_id)
    tmp = d / "_upload"
    tmp.mkdir(parents=True)
    limit = rt.settings.max_upload_mb * 1024 * 1024
    try:
        frames: list[tuple[str, pd.DataFrame]] = []
        total = 0
        for i, f in enumerate(files):
            fname = Path(f.filename or f"file{i}").name
            dest = tmp / f"{i}{Path(fname).suffix.lower()}"
            with open(dest, "wb") as out:
                while chunk := f.file.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise HTTPException(413, f"The upload is larger than {rt.settings.max_upload_mb} MB.")
                    out.write(chunk)
            for t, df in autoprep.read_upload(dest, fname).items():
                frames.append((t, autoprep.clean_frame(df)))
        tables = autoprep.unique_table_names(frames)
        if len(tables) > autoprep.MAX_TABLES:
            raise autoprep.UploadError(f"Too many tables (limit {autoprep.MAX_TABLES}).")
        paths = {}
        for t, df in tables.items():
            if df.empty:
                raise autoprep.UploadError(f"Table {t!r} has no rows.")
            _write_parquet(df, d / f"{t}.parquet")
            paths[t] = str(d / f"{t}.parquet")
        reg = autoprep.build_registry(name, tables, paths)
        _finish_registry(rt, dataset_id, reg)
        shutil.rmtree(tmp, ignore_errors=True)
        _insert(rt, dataset_id, user["id"], name, reg)
    except autoprep.UploadError as e:
        shutil.rmtree(d, ignore_errors=True)
        raise HTTPException(422, str(e)) from e
    except HTTPException:
        shutil.rmtree(d, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(d, ignore_errors=True)
        log.exception("dataset upload failed")
        raise HTTPException(422, f"Could not use these files: {str(e).splitlines()[0][:150]}") from e
    audit(rt, user["id"], "dataset_created", f"{dataset_id} {name}")
    return _summary(rt, dataset_row(rt, user, dataset_id), user)


@router.post("/datasets/demo", status_code=201)
def demo_dataset(user=Depends(current_user), rt: Runtime = Depends(runtime)):
    try:
        dataset_id = create_demo_dataset(rt, user)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    audit(rt, user["id"], "dataset_created", f"{dataset_id} demo")
    return _summary(rt, dataset_row(rt, user, dataset_id), user)


def _stats(rt: Runtime, row) -> dict:
    try:
        ds = rt.load_dataset(row["id"])
    except Exception as e:
        return {"error": str(e)[:200]}
    with ds.lock:
        tables = {t: ds.con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in ds.reg.tables}
        dates = {}
        for c in ds.reg.tagged("date"):
            lo, hi = ds.con.execute(f'SELECT min(CAST("{c.flat_name}" AS DATE)), max(CAST("{c.flat_name}" AS DATE)) FROM flat').fetchone()
            dates[c.flat_name] = [str(lo), str(hi)]
    return {"tables": tables, "date_ranges": dates}


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    row = dataset_row(rt, user, dataset_id)
    ds = rt.load_dataset(dataset_id)
    reg = ds.reg
    return {**_summary(rt, row, user), "registry": json.loads(rt.registry_to_json(reg)),
            "problems": reg.problems, "stats": _stats(rt, row)}


class DatasetPatch(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    visibility: str | None = None


@router.patch("/datasets/{dataset_id}")
def patch_dataset(dataset_id: str, body: DatasetPatch, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    row = dataset_row(rt, user, dataset_id, write=True)
    if body.visibility not in (None, "private", "shared"):
        raise HTTPException(422, "Visibility must be private or shared.")
    if body.name is not None and not body.name.strip():
        raise HTTPException(422, "Give the dataset a name.")
    rt.db.run("UPDATE datasets SET name = COALESCE(?, name), visibility = COALESCE(?, visibility), "
              "updated_at = datetime('now') WHERE id = ?", (body.name and body.name.strip(), body.visibility, dataset_id))
    audit(rt, user["id"], "dataset_updated", f"{dataset_id} {body.model_dump(exclude_none=True)}")
    return _summary(rt, dataset_row(rt, user, dataset_id), user)


@router.delete("/datasets/{dataset_id}")
def delete_dataset(dataset_id: str, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    dataset_row(rt, user, dataset_id, write=True)
    rt.invalidate(dataset_id)
    rt.db.run("DELETE FROM datasets WHERE id = ?", (dataset_id,))
    shutil.rmtree(rt.dataset_dir(dataset_id), ignore_errors=True)
    audit(rt, user["id"], "dataset_deleted", dataset_id)
    return {"ok": True}


def check_limits(reg: Registry) -> None:
    """Everything the user writes ends up in the model's prompt or the database: keep it small."""
    from ..query.frame import QueryFrame

    def too_long(label: str, text: str, n: int) -> None:
        if len(text) > n:
            raise HTTPException(422, f"{label} is too long (limit {n} characters).")

    too_long("The dataset description", reg.description, 600)
    for c in reg.columns:
        too_long(f"Description of {c.name}", c.description, 200)
        too_long(f"Expression of {c.name}", c.expression, 1000)
        if len(c.synonyms) > 12:
            raise HTTPException(422, f"{c.name}: at most 12 synonyms.")
        for sy in c.synonyms:
            too_long(f"A synonym of {c.name}", sy, 60)
    if len(reg.measures) > 50 or len(reg.rules) > 50 or len(reg.examples) > 200:
        raise HTTPException(422, "Too many measures, rules or examples (limits 50, 50 and 200).")
    for m in reg.measures:
        too_long(f"Measure {m.name} description", m.description, 200)
        too_long(f"Measure {m.name} expression", m.expression, 1000)
        for sy in m.synonyms:
            too_long(f"A synonym of {m.name}", sy, 60)
    for r in reg.rules:
        too_long(f"Rule {r.name} condition", r.condition, 1000)
        too_long(f"Rule {r.name} description", r.description, 200)
        for p in r.phrases:
            too_long(f"A phrase of {r.name}", p, 60)
    for e in reg.examples:
        too_long("An example question", e.question, 300)
        try:
            QueryFrame.model_validate({**e.frame, "rules": []})
        except Exception as err:
            raise HTTPException(422, f"Example {e.question!r} has an invalid frame.") from err


@router.put("/datasets/{dataset_id}/registry")
def put_registry(dataset_id: str, incoming: Registry, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    """Save tags, joins, descriptions, measures, rules and examples. Files and table names cannot change here."""
    row = dataset_row(rt, user, dataset_id, write=True)
    current = rt.registry_from_row(row)
    have = {(c.table, c.name) for c in current.columns if c.table != CALC_TABLE}
    sent = {(c.table, c.name) for c in incoming.columns if c.table != CALC_TABLE}
    if have != sent:
        raise HTTPException(422, "Source columns cannot be added or removed here; upload the data again instead.")
    if incoming.main_table not in current.tables:
        raise HTTPException(422, "The main table must be one of the uploaded tables.")
    for j in incoming.joins:
        for t, k in ((j.left, j.left_key), (j.right, j.right_key)):
            if t not in current.tables or (t, k) not in have:
                raise HTTPException(422, f"Join {j.left}.{j.left_key} = {j.right}.{j.right_key}: unknown table or column.")
    for c in incoming.columns:
        if c.table == CALC_TABLE and not IDENT.match(c.name):
            raise HTTPException(422, f"{c.name!r} is not a valid column name (letters, digits and underscore).")
    for c in incoming.columns:
        if c.tag not in ("metric", "dimension", "date", "ignore"):
            raise HTTPException(422, f"Unknown tag {c.tag!r}.")
    check_limits(incoming)
    incoming.tables = current.tables
    for c in incoming.columns:                                # tags from the browser are not trusted for derived fields
        c.error = ""
        if c.table != CALC_TABLE:
            c.expression = ""
    try:
        con = ingest.prepare(incoming)
        con.close()
    except Exception as e:
        raise HTTPException(422, f"Those settings could not be applied: {str(e).splitlines()[0][:200]}") from e
    rt.db.run("UPDATE datasets SET registry_json = ?, updated_at = datetime('now') WHERE id = ?",
              (rt.registry_to_json(incoming), dataset_id))
    rt.invalidate(dataset_id)
    audit(rt, user["id"], "registry_updated", dataset_id)
    ds = rt.load_dataset(dataset_id)
    return {"registry": json.loads(rt.registry_to_json(ds.reg)), "problems": ds.reg.problems}


@router.get("/datasets/{dataset_id}/preview")
def preview(dataset_id: str, table: str = Query("flat", max_length=100), limit: int = Query(50, ge=1, le=500),
            user=Depends(current_user), rt: Runtime = Depends(runtime)):
    dataset_row(rt, user, dataset_id)
    ds = rt.load_dataset(dataset_id)
    if table != "flat" and table not in ds.reg.tables:
        raise HTTPException(404, "No such table.")
    with ds.lock:
        df = ds.con.execute(f'SELECT * FROM "{table}" LIMIT {int(limit)}').df()
    return table_payload(df, limit)


class ExpressionIn(BaseModel):
    kind: str
    expression: str = Field(max_length=2000)


@router.post("/datasets/{dataset_id}/check-expression")
def check_expression(dataset_id: str, body: ExpressionIn, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    dataset_row(rt, user, dataset_id)
    ds = rt.load_dataset(dataset_id)
    with ds.lock:
        return semantic.preview_expression(ds.con, ds.reg, body.kind, body.expression)


@router.get("/datasets/{dataset_id}/complete")
def complete_text(dataset_id: str, q: str = Query("", max_length=500), user=Depends(current_user), rt: Runtime = Depends(runtime)):
    """Typeahead for the question box: column names, synonyms and category values that start like the last word typed."""
    dataset_row(rt, user, dataset_id)
    return typeahead.complete(q, rt.load_dataset(dataset_id).reg)


@router.get("/datasets/{dataset_id}/suggestions")
def suggestions(dataset_id: str, user=Depends(current_user), rt: Runtime = Depends(runtime)):
    """Starter questions built from the dataset's own definitions."""
    dataset_row(rt, user, dataset_id)
    reg = rt.load_dataset(dataset_id).reg
    out = [e.question for e in reg.examples][:3]
    import re

    metrics = reg.tagged("metric")
    dims = reg.tagged("dimension")
    # lead with the column people ask about most: sales / revenue / amount, else the first metric
    main_metric = next((c for c in metrics if re.search(r"sales|revenue|amount|amt|turnover", c.flat_name, re.I)), None) or (metrics[0] if metrics else None)
    # and a category that is not an id-like or very fine-grained one
    main_dim = next((c for c in dims if re.search(r"categor|segment|region|type|group", c.flat_name, re.I)), None) or (dims[0] if dims else None)
    m = (main_metric.synonyms[:1] or [main_metric.flat_name.replace("_", " ")])[0] if main_metric else None
    d = (main_dim.synonyms[:1] or [main_dim.flat_name.replace("_", " ")])[0] if main_dim else None
    if m:
        out.append(f"total {m}")
        if reg.tagged("date"):
            out.append(f"monthly {m}")
        if d:
            out += [f"{m} by {d}", f"top 5 {d} by {m}"]
    for ms in reg.active_measures()[:2]:
        out.append(f"{ms.label or ms.name.replace('_', ' ')}" + (f" by {d}" if d else ""))
    seen, uniq = set(), []
    for q in out:
        if q.lower() not in seen:
            seen.add(q.lower())
            uniq.append(q)
    return uniq[:8]
