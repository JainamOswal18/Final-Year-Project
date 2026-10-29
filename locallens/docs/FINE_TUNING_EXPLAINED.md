# LocalLens fine-tuning, explained from scratch

One document, plain English. If you remember nothing about this work, read this and you can explain it, defend it and re-run it.
The detailed engineering report is `docs/FINETUNING.md`; this file is the story.

---

## 1. What LocalLens is, in four lines

You type a question about a spreadsheet ("sales by region last quarter"). LocalLens answers with a chart. It all runs on your own computer, with no internet and no cloud AI.
A **small language model** (Qwen2.5-0.5B, half a billion parameters, 491 MB) does one narrow job: it reads the question and fills in a short form, the **query frame**.
Everything after that is ordinary code that cannot make things up: the frame is turned into SQL from fixed templates, the SQL is checked, DuckDB runs it, and rules choose the chart.

**The query frame** is a small JSON form:

| Field | Meaning | Example |
|---|---|---|
| intent | what kind of question | trend, comparison, ranking, proportion, distribution, summary |
| metric | which number, and how to combine it | `sales_amt`, SUM |
| dimension | what to split by | `region` |
| time | which date column, grouping, range | `order_date`, month, 2025-01-01 to 2025-12-31 |
| filters | restrictions | `region = "East"` |
| top_n, order | for rankings | 5, descending |
| ambiguous | what the model could not decide | `["metric"]` → the app asks you |

The model is also *forced* to write only valid frames: its output is constrained by a schema built from your dataset's real column names, so it cannot invent a column.
This is the core of the patent: the model never writes SQL and never sees your data rows, only the column names and the question.

Before the model runs, the app does some preparation (fix spelling, turn "last month" or "FY25" into dates, attach "column hints" such as *revenue = sales_amt*).
After it runs, **rules** fix the cheap, obvious mistakes (for example, "average" in the question forces AVG).

## 2. Why fine-tune at all

The off-the-shelf 0.5B model is general-purpose. It is only decent at this job because the prompt hands it about a dozen worked examples every time (a long, 1,100-token prompt),
and the keyword rules rescue it when it slips. With the rules switched off, it gets only **half** of the questions right.
Fine-tuning means: show the model thousands of (question → correct frame) pairs so it learns the job itself.

Goals we set:

1. A model that understands retail questions much better **on its own**.
2. A **shorter prompt** (no worked examples needed).
3. No loss of safety: it must not get worse on datasets it has not seen.
4. All of it provably free of leaks (no test question in the training data) and honestly measured.

## 3. How we fine-tuned (the method, simply)

**LoRA.** Instead of retraining all 500 million numbers, we freeze them and train a small add-on: 8.8 million new numbers (1.75% of the model) attached to every layer.
It is cheaper, faster and can't wreck what the model already knows. At the end the add-on is merged back into the model, so it runs exactly like before.

**"Loss on the answer only."** The model is graded only on the frame it writes, not on re-reading the question and column list. This focuses learning on the job.

**The training prompt is the real prompt.** The training examples are built with the app's own code (`build_messages`, `preprocess`), so what the model sees in training is exactly what it sees in the app.
That includes the date and column hints. Two prompt styles were trained together: **full** (system text, columns, fixed examples) and **compact** (system text and columns only, about 590 tokens instead of 1,110).

**Conversion.** The trained model is converted to the GGUF file format the app uses, then shrunk (quantised) to **Q4_K_M** (491 MB, the same size as the original) with no loss in answers. Q8_0 (676 MB) gave the same answers on all 233 test cases in round 1.
We wrote our own small exporter (`finetune/export_gguf.py`) because building llama.cpp's converter was blocked in this environment; it was first verified on the original model, producing the same answers as the official file.

## 4. The data (all our own, no licence issues)

There is no public dataset for this task, so we **generated** the training data (`finetune/synth.py`, `finetune/build_data.py`).

* **110 invented retail schemas.** Each is a random table: random column names (`sales_amt`, `Revenue`, `net_value`, ...), random synonyms, a date column or not, categories like region, store, product. This stops the model memorising one table.
* **About 80 questions per schema**, written from templates and word lists, in these proportions: comparison 20%, summary 17%, trend 15%, ranking 15%, follow-up 11%, Hinglish 7%, proportion 7%, distribution 5%, ambiguous 3%.
  Questions are also "dressed" with fillers, typos and polite wrappers so they sound less robotic. Hinglish means Hindi-English mixes such as "pichle mahine ki sales".
* **Each example is checked.** We keep a question only if the app's own preprocessing resolves the metric and the group-by from it, so the label is something the app could actually act on.
* **Follow-ups** carry the previous frame in the prompt ("now only for East" → keeps the metric, adds a filter).
* **Split by schema, not by row.** 14 schemas were held out for validation, so validation measures transfer to tables the model never saw.
* **Leak removal.** Any question equal to a test question was removed, and so was anything at least 90% similar to one (fuzzy match). Closest remaining training question to any test question: 88.9 out of 100.
* **Result:** round 1 trained on 7,612 examples; round 2 on **7,624** (validation: 1,107). Round 2 used 80% compact and 20% full prompts. The median example is about 600 tokens.

## 5. The test sets (how we know it works)

Training numbers mean nothing; unseen-question numbers do. We built a **locked test set before training** and never trained on it.

| Set | Size | What it is |
|---|---|---|
| **Held-out 4** | 233 cases: 192 answerable questions, 12 that should be refused or asked about, 29 multi-turn conversations | Our main test, frozen with git tag `heldout4-locked`. Tagged by difficulty: typos, Hinglish, Indian financial year, odd vocabulary, no-keyword intent, follow-ups |
| **Online Retail II** | 55 questions | A *real company's* invoice data (UCI, CC BY 4.0). Different columns, different wording |
| **Wholesale customers** | 51 questions | A different shape again (UCI, CC BY 4.0): no date column, spend split into Fresh/Milk/Grocery columns |
| gold, held-out 1, 2, 3 | 48 / 50 / 40 / 30 | Older sets, kept as a check that nothing got worse |

**What "accuracy" means:** *execution accuracy*. We run the model's final query and the correct query and compare the **result tables**. If they match, it's correct, however the frame was worded. That is the fairest measure.

**Three "rules" settings**, to separate what the model does from what the rules rescue:
`always` (the app's default: rules also decide intent and aggregation when no keyword fires), `fired` (rules act only when a keyword fires, the model decides otherwise), `off` (model alone).

Statistics: 95% intervals, and paired exact tests (McNemar) that count only questions where two models *differ*. "p" below is from that test; below about 0.05 means a real difference, not luck.

## 6. What happened, in order

**Step A, baseline.** We first measured the *original* model on the new test set. Its own frame was right only **38%** of the time; with the rules on, final accuracy 82%; with rules off, 50%.
Along the way the new tests exposed real app bugs, which we fixed before training so they would not be blamed on, or credited to, the model:
Hinglish date words, a crash when grouping by a numeric ID column (`Customer ID`), and some wrong gold answers in our own test set (documented in `eval/heldout4.py`).

**Round 1 (Google Colab, free T4 GPU, 1 h 38 min).** 2 epochs, 952 steps. Results were very good on two sets and terrible on one:

* Held-out 4: model's own frame right **38% → 95%**; model alone 50% → 83%; never worse than the original with rules on (0 lost, 8 gained, p = 0.008).
* Online Retail II (model alone): 35% → 78%.
* **Wholesale: 86% → 14%.** A disaster, so the model could not be made the default.

**The failure, simply.** In the Wholesale data there is a column per product group (Fresh, Milk, Grocery) *and* a measure called "total spend" whose synonym is "spend".
So "fresh spend by channel" has two candidate metrics: *Fresh* (specific) and *total spend* (generic). The right answer is the specific one.
Our training data never contained a question with two competing candidates, so the model learned "when in doubt, pick the generic one" and did so every time. The rules don't repair it.
It was a **gap in the data, not a flaw in the method.** (This is exactly why we test on datasets of a different shape.)

**Round 2 (this Mac, MLX, about 65 minutes, no Colab).**

* New "wide" schemas (3 in every 10): product-group columns plus a generic total whose synonym is a generic word. "Bakery sales" → the bakery column; "total sales" → the total. About 1,270 examples involve this case. The word lists deliberately exclude the Wholesale vocabulary, so we weren't training on the answer; a unit test enforces it.
* Training settings: LoRA rank 16, 1.5 epochs, learning rate 2e-4. (A first local attempt blew up because a scale setting was 20 instead of 2; fixed.)
* The first round-2 evaluation fixed Wholesale (86% again) but exposed two code problems: the model sometimes asked "which metric?" on "Compare X by Y" even though both were named, and it crashed on a nonsense filter against a numeric ID column. We fixed these **in code** (small grounding rules in `core/pipeline.py`), not by retraining:
  a field named in the question is no longer treated as ambiguous; a word filter on a numeric-ID column is dropped; a database error becomes a polite message instead of a crash.
* Then we re-ran **everything** with all three models (original, round 1, round 2) through the *same* final code, so the comparison is fair.

## 7. The final numbers

Final-answer accuracy, same code for all three:

| Test | Original | Round 1 | **Round 2 (now default)** |
|---|---|---|---|
| Held-out 4, rules `always` (233) | 84.1% | 85.8% | **84.1%** |
| Held-out 4, rules `fired` | 77.7% | 87.1% | **85.8%** |
| Held-out 4, model alone (`off`) | 50.2% | 83.3% | **80.3%** |
| Online Retail II, `always` / `off` | 74.5% / 38.2% | 76.4% / 78.2% | **76.4% / 76.4%** |
| Wholesale, `always` / `off` | 86.3% / 45.1% | 13.7% / 15.7% | **88.2% / 92.2%** |
| gold / held-out 1 / 2 / 3 | 100 / 100 / 95 / 100 | 100 / 98 / 97.5 / 100 | **100 / 98 / 100 / 100** |

Model's own frame (intent + metric + grouping all right) on the 192 answerable questions: original 38%, round 1 95%, round 2 87.5%. Round 2's metric column alone is right 99% of the time.

Is it real? (paired tests, held-out 4):

* Round 2 vs original, rules on: 4 worse, 4 better, p = 1.0 → **no difference**.
* Round 2 vs original, `fired`: 5 worse, 24 better, p = 0.0005 → **real gain**.
* Round 2 vs original, model alone: 8 worse, 78 better, p < 0.0001 → **very large gain**.
* Round 2 vs round 1: 4 worse, 0 better with rules on (p = 0.13); 8 worse, 1 better with rules off (p = 0.04) → round 2 is slightly weaker than round 1 on the main set. That is the price of fixing Wholesale.
* Q4_K_M vs Q8_0 for round 2: 85.0% vs 84.1%, two questions differ, no real difference.

Refusing/asking: the model asks for clarification correctly on 75% of the 12 should-ask cases and never over-asked on the 192 answerable ones.

**Speed:** median about 0.85 s per question, 95th percentile about 1.5 s (Apple M-series, CPU only). Same as the original (0.7 to 0.8 s). The shorter prompt does not buy speed at this model size.

## 8. What it means (the honest summary)

* With the app's rules on (the default setup), the fine-tuned model is **as accurate as the original, not better.** The rules were already rescuing the original model.
* The real gains: the model **understands on its own** (50% → 80% with rules off), it **no longer needs worked examples in its prompt** (half the length), and it handles Hinglish, Indian financial years and unusual wording much better by itself. With the rules in `fired` mode it is clearly better (78% → 86%).
* It is **not faster.**
* Round 2 is ~2% below round 1 on the main set, in exchange for no catastrophic failure on a differently shaped dataset. Wholesale is now a regression check, not a fresh test, because it was used to find the gap.
* For a viva: lead with "we found a failure with an independent dataset, diagnosed it to a specific data gap, closed it, and re-measured everything", not with a single headline percentage.

## 9. What is in the app now

* **Default model:** if the file `models/locallens-q4_k_m.gguf` exists, the app uses it with the compact prompt. If not, it falls back to the original Qwen model with the full prompt. Override with `LOCALLENS_MODEL_PATH` and `LOCALLENS_PROMPT_STYLE`.
  The file is 491 MB and **is not in git**, so a fresh clone uses the original model until you copy it in or rebuild it (section 10).
* **Rules mode** stays `always` (`LOCALLENS_RULES` = `always`, `fired`, `off`). `fired` scored 1.7 points higher but that is within noise, and `always` is safer on unfamiliar data.
* **Other additions on the way:** Hinglish date words, labels for numeric group-by columns, the three grounding fixes above, and tests (382 pass).

## 10. How to reproduce

You need a Mac or Linux box with about 16 GB RAM and the base model (`Qwen2.5-0.5B-Instruct`, Apache-2.0).

```
# 1. evaluation datasets (needs internet once)
python -I finetune/fetch_external.py

# 2. training data (round 2 settings)
python -I finetune/build_data.py --schemas 110 --per-schema 80 --val-schemas 14 \
    --wide-share 3 --compact-share 0.8 --seed 17 --out finetune/data_r2

# 3. train on a Mac (about 65 min); Colab alternative: finetune/train.ipynb
~/ft-env/bin/python finetune/train_mlx.py --model <Qwen2.5-0.5B-Instruct folder> \
    --data finetune/data_r2 --out finetune/runs/r2 --epochs 1.5

# 4. export to GGUF, then shrink to Q4_K_M
~/ft-env/bin/python finetune/export_gguf.py --stage f16 --fused finetune/runs/r2/fused --name locallens-r2
.venv/bin/python    finetune/export_gguf.py --stage quant --name locallens-r2
cp models/finetuned/locallens-r2-q4_k_m.gguf models/locallens-q4_k_m.gguf

# 5. measure
python eval/run_eval.py --set heldout4 --show-failures --out run.jsonl
python eval/compare.py docs/results/v2/base_always_heldout4.jsonl run.jsonl
```

Eval options: `--set heldout4|online_retail|wholesale|gold|heldout|heldout2|heldout3`, `--rules always|fired|off`, `--prompt-style full|compact`, `--model <gguf>`.
All raw results of this work are in `docs/results/` (the `v2/` folder is the fair three-way comparison).

Gotchas learned: on a Mac the MLX LoRA `scale` must be about 2, not 20 (it diverges); batch 2 without gradient checkpointing fits in 16 GB;
Colab sessions can reset (the first run was lost at ~70%); building llama.cpp tools was blocked, hence the custom exporter.

## 11. What is not proven yet

* **One training run, one seed.** We don't know the run-to-run spread.
* **Same author wrote training templates and test questions.** Overlap was removed, but style similarity can remain. No retail practitioner has reviewed the test questions.
* **Held-out 4 is synthetic retail**; only Online Retail II and Wholesale are truly different data.
* **Speed and memory on the 4-core target laptop** are unmeasured (only on the development Mac).
* **Other domains** (healthcare, finance, logistics) are not trained. The patent mentions them; only retail is done.
* **Optional round 3** would add "compare X by Y" contrast questions and more date-range arithmetic to win back the ~2% round 2 lost against round 1.

## 12. The rest of this session's changes (outside fine-tuning)

* **Power BI export:** explicit measures so charts draw; the `.pbip` zip must be fully extracted first; README says to click "Refresh now" once.
* **Windows helper** (`install.bat`, `locallens://` link): the link matcher now accepts the `locallens://open/?u=` form browsers produce.
* **UI:** the "Recent chats" sidebar list was fixed.
* **Mapping spreadsheet** (`Functionality_Mapping_Table (1).xlsx`), row F12, updated with the current fine-tuning status and numbers.
