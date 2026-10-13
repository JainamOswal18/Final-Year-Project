"""LocalLens: offline natural-language -> chart. Run: streamlit run app.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))  # so `streamlit run app.py` works without installing

from locallens import demo, export_pbi, ingest, pipeline, prefs as prefs_store
from locallens.frame import INTENTS
from locallens.registry import Join, Registry
from locallens.session import Session

ROOT = Path(__file__).parent
UPLOADS = ROOT / "data" / "uploads"
EXPORTS = ROOT / "exports"
REGISTRY_DIR = ROOT / "data" / "registry"

st.set_page_config(page_title="LocalLens", layout="wide")


# ---- shared state -----------------------------------------------------------
@st.cache_resource(show_spinner="Loading the language model (first run only)...")
def get_slm():
    from locallens.slm import SLM

    return SLM()


def ss(key, default=None):
    return st.session_state.setdefault(key, default)


def load_dataset(reg: Registry) -> None:
    con = ingest.prepare(reg)
    st.session_state.update(reg=reg, con=con, session=Session(), messages=[])
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    reg.save(REGISTRY_DIR / f"{reg.name}.json")


# ---- Data page ----------------------------------------------------------------
def page_data() -> None:
    st.header("Data")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("Load synthetic retail demo", type="primary"):
            load_dataset(demo.demo_registry())
            st.success("Demo data loaded. Go to Chat.")
    with c2:
        files = st.file_uploader("...or upload your own tables", type=["csv", "xlsx", "parquet"],
                                 accept_multiple_files=True)
    if files:
        UPLOADS.mkdir(parents=True, exist_ok=True)
        tables = {}
        for f in files:
            path = UPLOADS / f.name
            path.write_bytes(f.getbuffer())
            tables[Path(f.name).stem] = str(path)
        if st.session_state.get("upload_key") != sorted(tables):
            main = st.selectbox("Main (fact) table", list(tables))
            st.session_state.draft = ingest.new_registry_from_files("my_dataset", tables, main)
            st.session_state.upload_key = sorted(tables)

    draft: Registry | None = st.session_state.get("draft")
    if not draft:
        st.info("Load the demo or upload files, then tag each column as metric, dimension or date.")
        return

    draft.main_table = st.selectbox("Main (fact) table", list(draft.tables),
                                    index=list(draft.tables).index(draft.main_table))
    st.subheader("Tag columns")
    st.caption("Metric = a number you sum or average. Dimension = a category you group by. "
               "Date = a time column. Add synonyms users might type, comma-separated.")
    df = pd.DataFrame([{"table": c.table, "column": c.name, "tag": c.tag, "synonyms": ", ".join(c.synonyms)}
                       for c in draft.columns])
    edited = st.data_editor(
        df, hide_index=True, width="stretch", disabled=["table", "column"],
        column_config={"tag": st.column_config.SelectboxColumn(options=["metric", "dimension", "date", "ignore"])},
        key="tag_editor",
    )
    for c, (_, row) in zip(draft.columns, edited.iterrows()):
        c.tag = row["tag"]
        c.synonyms = [s.strip() for s in str(row["synonyms"]).split(",") if s.strip()]

    st.subheader("Joins")
    names = list(draft.tables)
    jdf = pd.DataFrame([j.model_dump() for j in draft.joins],
                       columns=["left", "left_key", "right", "right_key"])
    jedit = st.data_editor(
        jdf, num_rows="dynamic", hide_index=True, width="stretch", key="join_editor",
        column_config={"left": st.column_config.SelectboxColumn(options=names),
                       "right": st.column_config.SelectboxColumn(options=names)},
    )
    draft.joins = [Join(**r) for r in jedit.dropna().to_dict("records")]

    if st.button("Apply and load dataset", type="primary"):
        try:
            load_dataset(draft.model_copy(deep=True))
            st.success("Dataset loaded. Go to Chat.")
        except Exception as e:
            st.error(f"Could not build the dataset: {e}")


# ---- Chat page ----------------------------------------------------------------
def render_export(res: pipeline.Result, key: str) -> None:
    """Open in Power BI (claim 13): a self-contained .pbip project, zipped for download."""
    try:
        pbip = export_pbi.export_powerbi(res.df, res.chart, res.question, EXPORTS,
                                         prefs_store.load().get("sort", "desc"))
    except export_pbi.ExportError as e:
        st.caption(f"Power BI export unavailable: {e}")
        return
    st.download_button("Open in Power BI (download project)", export_pbi.zip_project(pbip),
                       file_name=f"{pbip.stem}.zip", mime="application/zip", key=f"pbi_{key}")
    st.caption(f"Unzip, then open {pbip.name} in Power BI Desktop (Windows). Also saved in {pbip.parent}")


def render_result(res: pipeline.Result, key: str = "") -> None:
    if res.error:
        st.warning(res.error)
        return
    if res.chart is None:
        return
    if res.chart.type == "kpi":
        st.metric(res.df.columns[0].replace("_", " "), f"{res.df.iloc[0, 0]:,.2f}")
    else:
        st.vega_lite_chart(res.df, res.chart.spec, width="stretch")
        if res.chart.fallback:
            st.dataframe(res.df, width="stretch")
            st.caption("I wasn't sure which chart fits, so here is the data and a best-guess chart.")
    render_export(res, key)
    with st.expander("How I read this"):
        st.markdown(f"**Intent:** `{res.frame.intent}` &nbsp; **Chart:** `{res.chart.type}` ({res.chart.reason})")
        if res.corrections:
            st.markdown("**Spelling fixed:** " + ", ".join(f"{a} -> {b}" for a, b in res.corrections))
        st.markdown("**Query frame**")
        st.json(json.loads(res.frame.model_dump_json()), expanded=False)
        st.markdown("**SQL**")
        st.code(res.sql, language="sql")
        t = res.timings_ms
        st.caption(" · ".join(f"{k} {v:.0f} ms" for k, v in t.items()))


def run_question(question: str, overrides: dict | None = None) -> None:
    session: Session = st.session_state.session
    followup = pipeline.is_followup(question, session)
    res = pipeline.ask(question, st.session_state.reg, st.session_state.con, get_slm(),
                       session, prefs_store.load(), followup=followup, overrides=overrides)
    st.session_state.messages.append((question, res))


def page_chat() -> None:
    st.header("Ask your data")
    if "reg" not in st.session_state:
        st.info("Load a dataset on the Data page first.")
        return
    try:
        get_slm()
    except FileNotFoundError as e:
        st.error(str(e))
        return

    for i, (q, res) in enumerate(st.session_state.messages):
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            render_result(res, str(i))

    session: Session = st.session_state.session
    if session.pending:
        p = session.pending
        st.info(p.message)
        cols = st.columns(len(p.options))
        for col, opt in zip(cols, p.options):
            if col.button(opt, key=f"opt_{opt}"):
                run_question(p.question, {p.field: opt})
                st.rerun()

    if q := st.chat_input("e.g. Show monthly sales for 2024 by region"):
        run_question(q)
        st.rerun()


# ---- Settings page ------------------------------------------------------------
def page_settings() -> None:
    st.header("Chart preferences")
    p = prefs_store.load()
    p["sort"] = st.radio("Sort bars", ["desc", "asc"], index=["desc", "asc"].index(p["sort"]), horizontal=True)
    choices = {"trend": ["line"], "comparison": ["bar", "hbar", "donut"],
               "ranking": ["hbar", "bar"], "proportion": ["donut", "bar", "hbar"]}
    for intent, opts in choices.items():
        cur = p["chart_overrides"].get(intent, "(automatic)")
        pick = st.selectbox(f"{intent.title()} chart", ["(automatic)"] + opts,
                            index=(["(automatic)"] + opts).index(cur) if cur in opts + ["(automatic)"] else 0)
        if pick == "(automatic)":
            p["chart_overrides"].pop(intent, None)
        else:
            p["chart_overrides"][intent] = pick
    if st.button("Save preferences", type="primary"):
        prefs_store.save(p)
        st.success("Saved.")


page = st.sidebar.radio("LocalLens", ["Chat", "Data", "Settings"])
st.sidebar.caption("Everything runs on this machine. No data leaves it.")
{"Chat": page_chat, "Data": page_data, "Settings": page_settings}[page]()
