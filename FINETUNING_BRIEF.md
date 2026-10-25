# Brief: fine-tune LocalLens's language model for retail questions

You are taking over a final-year project. Read this whole brief before you start. It holds every decision made so far, so you don't need to ask about any of it again.

## 1. The project

- **Repo:** `JainamOswal18/Final-Year-Project` on GitHub. The product is in `locallens/`.
- **What it does:** **LocalLens** turns a plain-language question about your data into a chart. Everything runs offline on one machine.
- **Where it comes from:** it implements a faculty patent, *"A System and Method for Privacy-Preserving Offline Language-to-Visualization Conversion"* (spec in the repo root, `.docx`).
- **Read first:**
  - `locallens/docs/ARCHITECTURE.md`: the pipeline and the claim map
  - `locallens/docs/EVAL.md`: how accuracy is measured, and the honest numbers
  - `locallens/docs/PATENT_MAP.md`: patent claims to code
  - `Functionality_Mapping_Table (1).xlsx` in the repo root: the feature-status sheet used for reviews

**How a question flows** (`src/locallens/core/pipeline.py`):

1. **Prepare** (`nlu/preprocess.py`): fix spelling, resolve dates (Indian financial year, April start by default), find column and value mentions, map retail synonyms (`nlu/retail_terms.py`), and match unknown words by meaning with bge-small embeddings (`nlu/embeddings.py`).
2. **Gate:** refuse chatter. Ask a clarifying question when a word could mean two columns, or when a "by <word>" is unexplained (`unknown_group_term`).
3. **Model** (`nlu/slm.py`): **Qwen2.5-0.5B-Instruct, Q4_K_M GGUF**, run by llama-cpp-python on CPU with `n_ctx=2048` and temperature 0.
   - It fills in a typed **query frame** (`query/frame.py`, `QueryFrame`): intent, metric (column + agg), dimension, time (column, grain, start, end), filters, top_n, order, ambiguous.
   - Its output is constrained by a JSON schema built from the dataset's real columns (`build_schema`), so it can't name a column that doesn't exist.
   - The prompt contains a system text, the column list, 6 fixed examples (`_examples`), the 3 closest verified examples, the question, and the code's hints in `[...]` brackets. On follow-ups it also contains the previous frame. **The model never writes SQL.**
4. **Rules** (`nlu/rules.py` `infer`, `pipeline._apply_rules`): keywords set intent, time grain, aggregation, top_n and order. Grounding then drops anything the model made up: filters must appear in the question, and the group-by column must be mentioned (`_ground_filters`, `_ground_dimension`, `_ground_metric`).
5. **SQL** (`query/sqlgen.py`, `query/validator.py`): one template per intent, checked with sqlglot. It runs in DuckDB over Parquet files.
6. **Chart** (`data/profiler.py`, `viz/charts.py`, `viz/charts_rules.yaml`): picked by rule; the browser draws it with Vega-Lite.

**The six intents:** trend, comparison, distribution, proportion, ranking, summary.

**Current accuracy** (EVAL.md): about 80–85% execution accuracy on unseen held-out questions the first time they're run. Median latency is 0.75 s and p95 is about 2 s on a 4-core CPU. The patent target is under 2 s, CPU only.

## 2. Decisions already made (don't reopen these)

- **Fine-tune the language model** for retail data. This turns patent claim 7 / mapping row F12 ("domain-adapted SLM") from Partial into Implemented. `docs/PATENT_MAP.md` currently says fine-tuning is "Not done, by choice"; update it when you finish.
- **Build for commercial use, even though the current use is academic.** Training data may only come from **MIT, BSD, Apache-2.0, CC0, CC BY, GODL-India** or our own synthetic data. Datasets under **CC BY-SA, non-commercial or unknown licenses** may be used **for evaluation only, never for training**.
- **Indian retail context:** April–March financial year, INR, and terms like SKU, MRP, GMV, footfall, kirana, outlet and basket size. Include Indian English and some Hinglish.
- **Keep the rules and the safety checks.** Grounding, the SQL validator, date resolution, `order`, `top_n` and the clarification gates all stay. Only intent and aggregation may be handed to the model, and only through the `fired` rules mode (§3).
- **Be honest in the docs.** Report first-run numbers on sets nobody tuned against, give confidence intervals, and say what wasn't verified. The existing EVAL.md is the model to follow.

## 3. Already done: branch `pipeline-for-finetuning` (commit `5a9e7e1`)

Start from this branch. It is pushed and not merged into `main`.

| Change | Where |
|---|---|
| Retail synonym list ("outlet" → store, "town" → city, "pieces" → quantity, SKU, zone, GMV, MRP, footfall, kirana, …). A word is mapped only when exactly one dataset column fits. | `nlu/retail_terms.py`, `preprocess._add_glossary_hints` |
| "number of pieces/units" sums quantity instead of counting rows | `nlu/rules.py` |
| Rules switch `LOCALLENS_RULES` / `pipeline.ask(rules_mode=...)`: **`always`** (default, old behaviour), **`fired`** (the model decides intent and aggregation when no keyword fires), **`off`** (no keyword rules; for measuring the model alone) | `nlu/rules.py` (`intent_is_fallback`), `pipeline._apply_rules`, `server/config.py` |
| The JSON schema now lists `time` 4th, matching `QueryFrame` and the prompt's examples. Before, the grammar forced `time` last while the examples put it 4th. | `query/frame.py` `build_schema` |
| Square brackets are stripped from questions, so users can't fake the code's `[column hints: …]` | `preprocess.preprocess` |
| Eval: `--rules always\|fired\|off`, `--model path.gguf`, and a "model alone (before rules)" accuracy line; failures show the model's raw frame | `eval/run_eval.py` |
| Tests | `tests/test_retail_terms.py`; 361 passed, 1 skipped |

**Not measured yet:** none of this has been run with the real model. Hugging Face was blocked in the previous environment.

**Not done yet:** letting the model resolve a completely unknown grouping word instead of asking. Proposed approach: call the model; accept its dimension only if the embedding similarity between the unknown word and that column's phrases is at least about 0.6; otherwise ask. Pick the threshold by measuring.

## 4. Why fine-tuning alone doesn't help (read before training)

The rules and grounding overwrite most of what the model produces. A better model only shows up in the score where its output survives:

| Aspect | Does the model's output reach the answer? | Training priority |
|---|---|---|
| Follow-ups ("now the average", "split by month", "only 2024"): merging with the previous frame | Yes; rules don't run on follow-ups | **High** |
| Choosing the metric when none, or several, are named | Yes (`_ground_metric` only overrides when exactly one is named) | **High** |
| `ambiguous`: knowing when to ask instead of guessing | Yes; any entry triggers a clarification | **High**. Measure both over-asking and under-asking. |
| Indian English / Hinglish ("pichle mahine ki sale", "outlet-wise GMV") | Partly (also needs the rule regexes and date parser) | Medium–high |
| Intent on paraphrases with no keyword | Only in `fired` mode | Medium |
| COUNT vs SUM vs AVG with no keyword | Only in `fired` mode | Medium |
| Date column choice, filter operators (`>`, `in`) | Yes | Medium |
| Typos, joined column names, prompt injection | Already handled in code | Low; don't spend effort |

## 5. What to build, in order

### Step A: measure the baseline (needs the model)

- Run `python scripts/download_model.py`. It needs `huggingface.co` to be reachable, and possibly `cdn-lfs.huggingface.co` / `*.hf.co`. In a Claude cloud environment, the user has to allow these domains in the environment's Network access settings.
- Run `python eval/run_eval.py --set <gold|heldout|heldout2|heldout3> --show-failures` with `--rules always`, `fired` and `off`.
- Save the outputs under `docs/` (for example `docs/baseline_<set>_<mode>.txt`).
- Check that `heldout3`'s 4 known failures ("units sold by town", "sales for each outlet", "how much did each town spend", "number of pieces sold per category") are now fixed by branch §3.

### Step B: a new locked test set (write it before any training data exists)

- **At least 200 questions** in `eval/heldout4.py`, in the same format as `eval/heldout3.py`: `(question, gold_frame_dict, gold_chart_type[, gold_sql])`.
- Tag each question with the aspects it exercises: `vocab`, `agg`, `intent_no_keyword`, `followup`, `should_ask`, `hinglish`, `indian_fy`, `typo`, `multi_table`. Add the tags as an extra field or a parallel dict.
- Follow-ups need a **multi-turn harness**. Today follow-ups are only unit-tested. Add sequences of (turn 1, turn 2, …) to `run_eval.py`, scored on the final frame.
- Prefer questions written by people other than the developer, ideally people with retail experience. Freeze the set with a git tag (`heldout4-locked`) before generating training data.
- Report confidence intervals. At 30 questions, one question is worth 3.3 points.
- **Cross-schema tests:** add at least one real retail dataset with different column names as an eval dataset:
  - **UCI Online Retail II** (CC BY 4.0, https://archive.ics.uci.edu/dataset/502/online+retail+ii). Revenue has to be a calculated column, Quantity × Price.
  - An Indian dataset from **data.gov.in** (GODL-India), for example daily retail commodity prices by centre.

  Write a registry (column tags and synonyms) for each, plus 50+ questions. None of these schemas or their synonyms may appear in training data.

### Step C: build the training data (target 4–6k examples)

Every example must be **exactly the prompt the app sends**: the same messages `SLM.fill_frame` builds, from system text and column list through hints and the previous frame. The answer must be the frame JSON **in the schema's field order and spacing**.

Write `finetune/build_prompt.py`, which reuses `slm.py`'s prompt-building code. Refactor `fill_frame` so the messages are built by a pure function that both paths call. Don't copy it.

Suggested mix:

| Share | Source | Notes |
|---|---|---|
| ~40% | **Synthetic over real retail schemas** | Use templates × retail vocabulary × schema variation. The gold frame comes from the template. Optionally paraphrase questions with a larger LLM once, offline, then spot-check by hand. |
| ~20% | **nvBench** (https://github.com/TsinghuaDatabaseGroup/nvBench, MIT on the repo) | Map: line chart → trend (binning gives the grain), pie → proportion, bar + GROUP BY → comparison, ORDER BY + LIMIT → ranking, line with a grouping → trend with a dimension. Drop scatter charts, joins and nested queries. **License check:** nvBench is built from Spider's databases and queries, and Spider is CC BY-SA 4.0. Decide whether the MIT label is enough. If unsure, treat nvBench as eval-only and increase the synthetic share. |
| ~10–15% | **WikiSQL** (believed BSD-3; verify) | Single table, aggregation plus WHERE. Good for agg choice and filter operators. Labels are known to be noisy, so filter them. |
| ~10% | **Follow-ups, synthetic** | SParC/CoSQL are likely CC BY-SA, so use them for eval only. Generate (previous frame, follow-up, new frame) triples. |
| ~10% | **When to ask** | Ambiguous questions → `ambiguous` set; chatter → refusal path; injection attempts. nvBench 2.0 (ambiguous queries) only if its license is permissive. |
| ~5% | **Hinglish / Indian English** | Synthetic. Makadi (Hinglish Spider) only if its license is permissive. |

**Rules for building the data:**

- **Schema randomisation:**
  - **Names:** rename columns (`sales_amt`, `revenue`, `net_sales`, `amt`, `Sales Value`) and add table prefixes (`orders_qty`).
  - **Columns:** shuffle their order, add and drop columns, and vary the synonyms and descriptions.

  Otherwise the model memorises the demo schema and breaks on uploaded datasets.
- **Prompt variety:**
  - Mix examples with and without the 3 retrieved few-shots.
  - Include the date and column hints the code would actually add.
  - Include the previous frame for follow-ups.
- **Dedupe** near-identical questions, and keep a train/validation split by **schema**, not by row.
- **Licenses:** record the source and license of every example in `finetune/DATA_LICENSES.md`. Verify each license from the official source and link it. Unverified means eval-only.

### Step D: training (needs a GPU; deliver a notebook the user runs on Colab)

- `finetune/train.ipynb` (Colab). Unsloth, or Hugging Face TRL `SFTTrainer` with PEFT.
- **16-bit LoRA, not QLoRA:** r = 16, alpha = 16–32, all linear layers, learning rate 1e-4 to 2e-4, 2–3 epochs, effective batch 16. Compute the loss on the answer only.
- **T4 note:** a Colab T4 has **no bf16**, so use fp16.
- Stop on held-out **frame accuracy**, not on training loss.
- **Candidate models** (keep CPU latency under 2 s in mind):
  - Qwen2.5-0.5B-Instruct (baseline)
  - Qwen2.5-1.5B-Instruct (about 3× the compute; may fit if the fine-tune drops the 6 fixed examples and the prompt gets shorter)
  - Qwen3-0.6B (turn thinking off and train with the template's empty think block)

  Qwen3.5-0.8B and Gemma 3 270M are riskier: check that the llama.cpp bundled in llama-cpp-python 0.3.x runs them, and check the licenses.
- **GGUF export:**
  - Merge the LoRA into the **fp16** base, never into a 4-bit model.
  - Convert with a llama.cpp version that matches the installed llama-cpp-python.
  - Keep the ChatML chat template inside the GGUF.
  - **Set a pad token different from `<|im_end|>`.** This is a common Qwen bug where the model never learns to stop.
  - Produce **both Q8_0 and Q4_K_M**. Tiny models lose more at 4-bit. If you use Q4, calibrate it with an imatrix built from task prompts.
- **Wiring:** drop the file into `locallens/models/`. The app loads it via `LOCALLENS_MODEL_PATH`; the eval via `--model`. Keep the base model as the default until the fine-tuned one wins.

### Step E: evaluation and write-up

- **Comparison grid:** {base, fine-tuned} × rules {always, fired, off} × {Q4, Q8}, on heldout4, the cross-schema sets, and the old gold and heldout sets (regression check: they must stay at about 100%).
- **Statistics:** use a paired McNemar test on the same questions. Report per-field and per-tag accuracy for both the raw model frame and the final result. Also report how often the system asks when it shouldn't, and fails to ask when it should.
- **Latency:** p50 and p95 plus prompt tokens on a 4-core CPU. Note the machine.
- **Pick the default** model and rules mode from the numbers. If the fine-tuned model wins with `fired`, make `fired` the default and update the tests.
- **Docs to update:** `docs/EVAL.md` (new section: base vs fine-tuned, with first-run numbers), `docs/ARCHITECTURE.md`, `docs/PATENT_MAP.md` (claim 7), and the mapping spreadsheet's F12 row and Non-Functional sheet.
- **Viva framing:** present the pipeline fixes and the fine-tune gain **separately**, so each one's contribution is visible.

## 6. Code conventions

- Python 3.11+. Match the surrounding style: short docstrings that say *why*, few comments, small functions. Use Pydantic models for data.
- **Tests:** `cd locallens && pytest -q` must stay green. Test model-dependent logic with the `FakeSLM` pattern in `tests/test_pipeline.py`; fixtures `sreg`/`scon` are in `tests/conftest.py`. Web: `cd locallens/web && npm ci && npm run typecheck && npm test && npm run build`. CI runs both (`.github/workflows`).
- New code goes in `locallens/finetune/`: data builders, converters, prompt export, notebook, licenses. Keep large downloaded datasets and model files out of git; add `.gitignore` entries.
- Downloaded datasets are untrusted: put them in their own directory, and don't execute anything from them.
- Work on a branch, commit in small logical steps, and don't merge into `main` without the user's approval.

## 7. Things to verify (flagged as uncertain earlier)

- Licenses for Spider, SParC, CoSQL, WikiSQL, nvBench 2.0, Makadi, Olist, Rossmann, Instacart, NLV and Quda. Also whether nvBench's MIT label holds, given it is derived from Spider.
- Whether llama.cpp's JSON-schema grammar actually enforces the schema's property order. The §3 fix assumes it does; check with the real model by looking at raw outputs.
- Whether llama-cpp-python 0.3.x supports any newer model you pick.

## 8. Deliverables checklist

- [ ] Baseline eval outputs saved (Step A)
- [ ] `eval/heldout4.py` (200+ tagged questions, locked with a git tag), multi-turn harness, and cross-schema datasets with their questions
- [ ] `finetune/`: prompt export (shared with `slm.py`), converters, synthetic generator, `DATA_LICENSES.md`, train/val JSONL
- [ ] `finetune/train.ipynb` (Colab) plus GGUF export steps
- [ ] Results grid, and docs updated (EVAL, ARCHITECTURE, PATENT_MAP, mapping sheet)
- [ ] Optional: model-assisted resolution of unknown words, with a measured similarity threshold
