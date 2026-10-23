# Patent map: what the patent says, what is built, what is pending

Source: "A System and Method for Privacy-Preserving Offline Language-to-Visualization Conversion" (spec dated 18.02.2026).
Status key: **Done** = built and tested. **Partial** = built, with a stated gap. **Not done** = not built. **Beyond** = built but not in the patent.

## 1. The 14 claims

| Claim | What it requires | Where in the code | Status | Gap / note |
|---|---|---|---|---|
| 1 | Offline system: UI, local small model, extract entities, find intent, build query, run it locally, analyse result, pick chart, show it | `core/pipeline.py`, `server/`, `web/`; `scripts/check_offline.py` | **Done** | Offline proven by blocking all network calls. Downloading the models is a one-time online step. |
| 2 | Metric = number field, dimension = category field, temporal = time field | `data/registry.py` tags, `query/frame.py` | **Done** | Fiscal period supported (fiscal-year start month). |
| 3 | Token analysis mapped to schema metadata, stored in a structured form with fixed fields | `nlu/preprocess.py`, `query/frame.py` (`QueryFrame`) | **Done** | |
| 4 | Intent from the small model, one of a fixed set of IDs | `nlu/slm.py`, `nlu/rules.py` | **Done** | Model plus keyword rules. No separate trained classifier head (the description mentions one). |
| 5 | SQL from a predefined template, schema check before running | `query/sqlgen.py`, `query/validator.py` | **Done** | The model never writes SQL. |
| 6 | Result analysis: columns, types, time order, aggregation level, dimensionality, cardinality | `data/profiler.py` | **Partial** | Columns, types, time order and cardinality are measured. Aggregation level and dimensionality come from the question type. |
| 7 | Domain adaptation with local embeddings; fixed context window | `nlu/embeddings.py`, `data/semantic.py`, `nlu/slm.py` | **Done** | Domain-adapted via locally stored embeddings and a semantic layer (custom metrics, rules, descriptions, verified examples). Prompt fitted to 2048 tokens. Embeddings help with about a third of unseen paraphrases. The model weights are not fine-tuned (not part of the claim). |
| 8 | Query validation plus deterministic templates | `query/validator.py` (sqlglot) | **Done** | |
| 9 | Chart chosen from number of dimensions, time, aggregation, categorical vs continuous | `viz/charts.py`, `charts_rules.yaml` | **Done** | |
| 10 | Config has chart ID, axis mapping, aggregation, sort, render metadata, from stored rules | Vega-Lite spec, rules file, saved preferences | **Done** | |
| 11 | Time data to line charts, category data to bar charts | `charts_rules.yaml` | **Done** | |
| 12 | Small model, no GPU | Qwen2.5-0.5B Q4, CPU only | **Done** | 1.0 GB peak with both models loaded (Apple M5, measured 2026-10-24). Speed measured on one machine only. |
| 13 | Result and chart config go to Tableau or Power BI through an API adapter | `viz/adapters.py`, `viz/export_pbi.py`, `server/helper.py` | **Partial** | Power BI built as a file export (`.pbip` project) with a Windows one-click helper (untested on Windows). Passes Microsoft's schema checks. **Not yet opened in Power BI Desktop.** No Tableau. Not a live API call. |
| 14 | The same as claim 1, written as a method (steps 202 to 216) | `core/pipeline.py` | **Done** | |

## 2. Features in the description (not in the claims)

| Feature in the patent | Status | What we have / what is missing |
|---|---|---|
| Runs with no internet, nothing leaves the device | **Done** | `check_offline.py`; no telemetry; strict content-security policy |
| Nothing leaves the trusted network | **Done** | On-premise server. No TLS built in: put it behind an HTTPS proxy. |
| Local web UI | **Done** | React app served by the local server |
| Query suggestions | **Done** | Suggestion chips from the dataset's own columns; examples on refusal |
| Auto-completion while typing | **Done** | Typeahead finishes column names, synonyms and category values (`nlu/typeahead.py`) |
| Spelling normalisation | **Done** | rapidfuzz against column names, synonyms and keywords |
| Input validation / syntactic checks | **Done** | Non-data questions refused; length limits |
| Semantic disambiguation | **Done** | A value in two columns, an unknown word after "by", or an ambiguous metric gives a clarifying question |
| Command-line or voice interface | **Not done** | |
| Desktop app or BI-tool plugin | **Not done** | Browser only |
| Model size 50M to 500M, 4 or 8-bit | **Done** | 0.49B parameters, 4-bit |
| Memory footprint below 4-8 GB | **Done** | 1.0 GB peak with both models loaded. Not yet measured on an 8 GB Windows laptop. |
| Response under 2 seconds | **Partial** | Median about 0.8 s. Worst cases 1.7 to 3.9 s on the test sets. Under machine load it can stall. A 30 s limit makes it fail fast. |
| Schema registry (terms to columns, tables, relationships), updated offline by an admin | **Done** | Columns page: tags, synonyms, descriptions, joins |
| Derived metrics ("sales growth", "churn rate") | **Partial** | Users can define metrics (e.g. profit margin) on the Definitions page. No built-in growth or period-over-period calculation. |
| Constrained decoding, schema-aware | **Done** | JSON-schema grammar limits columns to real ones |
| No access to unauthorised tables or columns | **Done** | Validator allowlist; per-user dataset access |
| Run against local DB, embedded DB, CSV or Parquet | **Done** | DuckDB; CSV, Excel, Parquet and SQLite uploads; multi-table joins |
| Locally synchronised data warehouse, other live databases | **Not done** | No connectors to Postgres, SQL Server, etc. |
| Encrypted data vault | **Not done** | Data files are not encrypted at rest |
| Statistical properties (variance, skew) of the result | **Not done** | |
| Chart types: line, multi-line, bar, horizontal bar, donut, histogram, scatter, KPI | **Done** | |
| Chart types: area, box plot, stacked, heat map, grouped bar | **Not done** | |
| Histogram bins from data variance | **Not done** | Fixed bin rule |
| Axis labels, colours, sort | **Done** | |
| Tick intervals, smoothing, colour gradients, annotations | **Partial** | Interactive tooltips only |
| ML-based chart recommendation trained on history | **Not done** | Rules plus saved preferences |
| Default chart policy when intent is unclear | **Done** | Table plus a best-guess bar |
| Query refinement from ambiguity / missing parameters | **Done** | Clarifying-question buttons |
| User feedback and iterative refinement | **Done** | Follow-ups ("now only for Technology"). Fixed a context-loss bug on 2026-10-22. |
| Persistent preferences (chart style, aggregation default, sorting) | **Done** | Preferences page, per user: sort, chart per question type, default aggregation |
| Access control: login and roles | **Done** | scrypt passwords, sessions, lockout, admin and user roles |
| Fine-tuning on domain vocabulary (healthcare, finance, logistics, etc.) | **Not done, by choice** | Domain adaptation is done through embeddings and the semantic layer instead (claim 7). Demo data is retail only. |
| Supervised training on paired question and query data | **Not done** | Eval question sets exist (128 questions) but no training set |
| Learning from human feedback (RLHF) | **Not done** | Thumbs and "Mark as correct" are stored; "Mark as correct" is used as a prompt example, not for training |
| Intent classifier head or separate classifier | **Not done** | Model plus rules instead |
| Runs on desktop, laptop, tablet, phone, edge device | **Partial** | Laptops and a shared server work. Phone and tablet only through a browser (layout not checked visually). Windows and edge/ARM not tested. |

## 3. Built beyond the patent

Financial calendar (April start by default; Q1 FY25, FY 2024-25 and bare Q2 are understood; year and quarter grouping and chart labels follow it), chart requests in chat ("make it a pie chart"), "use this average unless I say otherwise" preference, Semantic layer (custom metrics, calculated columns, business rules, fiscal year), verified examples shown to the model, upload with automatic tagging and join guessing, private and shared datasets, private chats, audit log, admin user management, feedback review, CSV export, held-out evaluation sets with honest accuracy numbers, one-command start scripts, CI workflow.

## 4. What is pending, in priority order

**Verify before the faculty demo**
1. Open a generated `.pbip` in Power BI Desktop on the Windows laptop (claim 13 is unproven until then).
2. Run `start.bat` and confirm `llama-cpp-python` installs on Windows.
3. Measure speed and memory on the weakest 8 GB laptop.
4. Check that the CI workflow passes on GitHub (never run).

**Patent gaps, largest first**
5. Fine-tuning is no longer planned: domain adaptation is through embeddings and the semantic layer.
6. Tableau adapter (claim 13 says "at least one", so Power BI alone can satisfy it).
7. More chart types (area, box, stacked, heat map, grouped) and variance-based histogram bins.
8. Growth and period-over-period measures.
9. Trained intent classifier (auto-completion is now done).
10. Connectors for other databases; encryption at rest.

**Quality and hardening**
11. Accuracy on unseen questions is about 80 to 85%. Known weak spots: unfamiliar words ("town", "outlet", "pieces"); changing the chart or ranking in a follow-up depends on the small model.
12. Latency tail: the slowest questions take 4 s or more.
13. HTTPS and single sign-on; password-reset flow; zip-bomb defence for Excel uploads; phone layout check.
