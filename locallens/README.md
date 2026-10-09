# LocalLens

Offline natural-language -> chart. Ask a question about retail data in plain English; a small
language model fills a typed query frame, templates build the SQL, rules pick the chart.
Nothing leaves the machine. Implements the faculty patent *A System and Method for
Privacy-Preserving Offline Language-to-Visualization Conversion*.

**The model never writes SQL.** It only fills a fixed frame (intent, metric, dimension, time,
filters) whose column fields are limited to the columns you tagged. Everything after it is
deterministic: grounding checks, SQL templates, a sqlglot validator, DuckDB, chart rules.

## Setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate    # use 3.11-3.12
pip install -r requirements.txt
python scripts/make_synthetic_data.py                    # demo data -> data/synthetic/
python scripts/download_model.py                         # the only step that needs internet (~490 MB)
streamlit run app.py                                     # http://127.0.0.1:8501
```

Windows: if `llama-cpp-python` tries to compile, install a prebuilt CPU wheel instead:
`pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`

## Using it

1. **Data** page: *Load synthetic retail demo*, or upload CSV/Excel/Parquet tables, tag each column
   (metric / dimension / date), add synonyms, declare joins, then *Apply*.
2. **Chat** page: ask a question. Open *How I read this* to see the frame, SQL and chart rule.
   Ambiguous terms trigger a clarification; short follow-ups ("now only 2025") reuse the last frame.
3. **Settings**: saved chart preferences (stored in `prefs.json`).

## Layout

```
src/locallens/   registry, ingest, preprocess, rules, slm, frame, sqlgen, validator,
                 engine, profiler, charts (+ charts_rules.yaml), prefs, session, pipeline
app.py           Streamlit UI only (the pipeline has no UI code)
scripts/         make_synthetic_data, download_model, try_slm, try_app, check_offline
eval/            questions.py (40 gold questions), run_eval.py
tests/           unit + pipeline tests (76)
```

## Verify

```bash
pytest                                              # no model needed
PYTHONPATH=src python eval/run_eval.py --show-failures   # real model on the gold set
PYTHONPATH=src python scripts/check_offline.py     # real model with the network blocked
```

## Notes

- "Today" for relative dates ("last quarter") is the latest date in the data, so demos always have rows.
- The gold set was used while building the rule layer, so its score is optimistic. Add held-out
  questions before quoting accuracy in the report.
- Not built yet: Power BI / Tableau export (patent claim 13, needs a Windows demo machine),
  fine-tuned model, login/RBAC, voice.
