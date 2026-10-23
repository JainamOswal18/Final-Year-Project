# LocalLens

Ask questions about your data in plain language and get a chart. Everything runs on your own machine or
server: a small language model on the CPU, no GPU, no internet after the one-time model download, and your
data never leaves it. Built from the patent *"A System and Method for Privacy-Preserving Offline
Language-to-Visualization Conversion"*.

* **For people who ask questions:** a web app with sign-in, chats, charts, an explanation of how each answer was read, and export to Power BI or CSV.
* **Ask in the words you use:** "Q1 FY25", "financial year 2024-25", "make it a pie chart", "now only for Technology". The financial year starts in April unless the dataset says otherwise.
* **For people who own the data:** upload files, say what each column means, and teach it your business: your own metrics, rules, financial year and examples.
* **For the project report:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (design, security, patent claim map) and [`docs/EVAL.md`](docs/EVAL.md) (accuracy, measured honestly).

## Quick start

You need Python 3.11+ and, to build the web app, Node 20+. Internet is needed **once**, to download the models.

```bash
cd locallens
./start.sh            # Windows: start.bat
```

That script creates a virtual environment, installs everything, downloads the models (about 525 MB), builds the web
app, and starts the server at **http://127.0.0.1:8000**. Open it, create the administrator account, click
**Try the retail demo**, and ask something like *"monthly sales for 2024 by category"*.

Do it by hand instead:

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python scripts/download_model.py                        # language model + 35 MB term-matching model
(cd web && npm ci && npm run build)
python -m locallens.server
```

**Windows:** if `pip install` tries to compile `llama-cpp-python` and fails, install the prebuilt CPU build first:
`pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu`

## Using it

1. **Datasets → New dataset:** drop CSV, Excel, Parquet or SQLite files (several files become several tables).
   Column types and the joins between tables are guessed; check them on **Columns**.
2. **Definitions:** describe the data in a sentence, set the financial-year start, add your own **metrics**
   (`profit_margin = SUM(profit) / SUM(sales_amt)`), **calculated columns** and **business rules**
   ("always leave out cancelled orders", or "high value" means sales of 1000 or more). Each formula is checked live.
3. **Ask.** Each answer has a chart, a **How I read this** panel, **Open in Power BI**, **Download CSV**, and 👍/👎.
   **Mark as correct** turns an answer into an example the assistant learns from.
4. **Administration** (administrators): add people, reset passwords, review answers people flagged.

**Open in Power BI** downloads a project. Unzip it on a Windows machine and open the `.pbip` file in Power BI Desktop
(free). If Desktop asks, enable *Options → Preview features → Power BI Project (.pbip) save option* and *Store reports
using enhanced metadata format (PBIR)*, then reopen. The data is embedded in the file; nothing is uploaded.
The generated files are validated against Microsoft's published schemas (`python scripts/validate_pbip.py`), but
**have not yet been opened in Power BI Desktop** — please test that on your Windows laptop.

## Running it for a team

```bash
LOCALLENS_HOST=0.0.0.0 LOCALLENS_PORT=8000 LOCALLENS_SECURE_COOKIES=1 python -m locallens.server
```

Put it behind your company's HTTPS reverse proxy (the app does not do TLS itself), and set `SECURE_COOKIES` when it is.
Everything is stored under `data/server/` — **back that folder up**; it holds the users, datasets and chats.

| Setting (environment variable) | Default | Meaning |
|---|---|---|
| `LOCALLENS_HOST` / `LOCALLENS_PORT` | `127.0.0.1` / `8000` | where to listen |
| `LOCALLENS_DATA_DIR` | `data/server` | database, uploads, logs |
| `LOCALLENS_MODEL_PATH` | `models/qwen2.5-0.5b-instruct-q4_k_m.gguf` | language model |
| `LOCALLENS_EMBEDDINGS` | `1` | match unknown words by meaning (uses the 35 MB model if present) |
| `LOCALLENS_N_THREADS` | automatic | CPU threads for the model; use the number of fast cores |
| `LOCALLENS_MODEL_TIME_BUDGET_S` | `30` | give up on a stalled generation |
| `LOCALLENS_MAX_UPLOAD_MB` | `200` | upload size cap |
| `LOCALLENS_SESSION_HOURS` | `12` | sign-in lifetime |
| `LOCALLENS_SECURE_COOKIES` | `0` | set to `1` behind HTTPS |

Administrator tools from the command line: `python -m locallens.server create-user NAME --admin` and
`python -m locallens.server reset-password NAME`. Logs: `data/server/logs/server.log`.

## Developing

```bash
pytest                                   # 270+ tests: pipeline, rules, security, API, exports
python eval/run_eval.py --set heldout3   # accuracy with the real model (see docs/EVAL.md)
python scripts/check_offline.py          # proves a question runs with all network calls blocked
cd web && npm run dev                    # web app with hot reload on :5173, proxies /api to :8000
cd web && npm run typecheck && npm test && npm run build
```

| Folder | What is in it |
|---|---|
| `src/locallens/` | the Python package (see `docs/ARCHITECTURE.md`) |
| `web/` | the React + TypeScript app |
| `eval/` | gold and held-out question sets |
| `scripts/` | model download, demo data, offline check, Power BI schema check |
| `tests/` | automated tests |
| `data/synthetic/` | the demo retail data (seeded, regenerate with `scripts/make_synthetic_data.py`) |

## Not done yet

Fine-tuning the model on retail questions; Tableau export; single sign-on; a check of the Power BI project in
Power BI Desktop; measuring speed on the weakest team laptop (8 GB). See `docs/EVAL.md` for known accuracy limits.
