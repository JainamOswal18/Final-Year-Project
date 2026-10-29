# Fine-tuning the frame-filling model

*Branch `pipeline-for-finetuning`. Test set frozen with the git tag `heldout4-locked`. Every number below comes from a file in `docs/results/`.*

## The result in one paragraph

We fine-tuned Qwen2.5-0.5B-Instruct (LoRA, 7,612 synthetic examples, 1 h 38 min on a free Colab T4) to fill the query frame.
On questions it had never seen, **the model's own answer is right 95% of the time, up from 38%**. With the app's keyword rules
switched off, **final-answer accuracy goes from 50% to 84%**; with the rules on it goes from 82% to 86%, and the fine-tuned model
was never worse than the original on any question (0 losses, 8 gains, p = 0.008). The same holds on a real company's invoice data
it had never seen (Online Retail II: 35% → 78% without rules). **But on a third, differently shaped dataset (Wholesale customers)
it fails badly, 14% against the original's 86%**, because it picks the generic metric whenever a question names two. So the fine-tuned model
ships as an option, not as the default, until that is fixed (see "The failure").

## What was trained

| | |
|---|---|
| Base model | Qwen2.5-0.5B-Instruct (Apache-2.0), the model the app already uses |
| Method | 16-bit LoRA: rank 16, alpha 32, all linear layers (8.8 M trainable weights, 1.75%), loss on the answer only |
| Settings | 2 epochs (952 steps), effective batch 16, lr 2e-4 cosine with 5% warm-up, fp16 on a Colab T4, max length 2048 |
| Time | 1 h 38 min (Colab). The same recipe also runs on a Mac (`finetune/train_mlx.py`); see "What went wrong on the way" |
| Loss | training loss 0.0053 (step 100) → 0.00015 (end); validation loss 0.0058 → 0.00028, on schemas never seen in training; smooth, no divergence |
| Merge and export | LoRA merged into the fp16 base, converted to GGUF, then quantised to **Q8_0** (676 MB) and **Q4_K_M** (491 MB) |

The training prompt is **exactly** what the app sends: `finetune/` builds it with the app's own `build_messages()` (one function shared
by the app and the data builder, so they cannot drift). Two prompt styles were trained together: `full` (system text, columns, 6 fixed
examples, the 3 closest verified examples) and `compact` (system text and columns only, about 590 tokens against 1,110).
The model never writes SQL: it fills the same typed frame as before, still constrained by the JSON schema built from the dataset's columns.

## The data (our own, so no licence applies)

`finetune/synth.py` generates random retail datasets and questions about them; `finetune/build_data.py` builds the files.

* **110 schemas** (96 train, 14 validation): renamed columns (`sales_amt`, `net_revenue`, `Sales Value`, `orders_qty`), shuffled order,
  1 to 3 synonyms each, Indian cities, states and categories as values, sometimes two date columns, business measures, April to March financial year.
* **7,612 training and 1,104 validation examples**, split **by schema**, so validation measures transfer to datasets never seen.
* Mix: comparison, summary, trend, ranking, follow-ups (with the previous frame in the prompt), proportion, distribution, Hinglish, and "which metric?" cases. Half `full` prompts, half `compact`.
* An example is kept only when the app's own pre-processing would hand it to the model with the metric and the group-by already pointed out by its hints.
* **Overlap with the test set is removed**: 48 same-as-a-test-question and 84 near-identical (fuzzy match 90 or more) examples were dropped; the closest remaining training question to any test question scores 89.5 of 100.
* Licences: `finetune/DATA_LICENSES.md`. nvBench, WikiSQL and other public sets were **not used** (licences unclear or no retail value). data.gov.in needs a registered key, so it was left out.

## The test sets

* **`eval/heldout4.py`: 204 questions and 29 two-to-three-turn conversations**, written before any training data existed and frozen with the tag `heldout4-locked`.
  Every question is tagged (`vocab`, `agg`, `intent_no_keyword`, `followup`, `should_ask`, `hinglish`, `indian_fy`, `typo`, `multi_table`). 12 expect a refusal or a clarifying question. Conversations are scored on the final turn.
* **`eval/cross_online_retail.py`: 55 questions** on UCI Online Retail II (CC BY 4.0): spaced column names, no profit, revenue is a calculated column, 43 countries.
* **`eval/cross_wholesale.py`: 51 questions** on UCI Wholesale customers (CC BY 4.0): six spend columns and **no date column**.
* The four older sets (gold, held-out 1 to 3) are kept as a regression check.

Honest caveats: the developer wrote the questions *and* the training templates, so phrasing overlap is possible even after the removal above; no retail practitioner has reviewed them.
After the first baseline run five gold answers were corrected (question text untouched, model output not consulted); they are listed in the header of `heldout4.py`.
Accuracy is **execution accuracy**: the result table equals the gold frame's result table. Intervals are 95% Wilson; comparisons are paired exact McNemar tests on the same questions.

## Results

### Held-out 4 (233 cases: 192 answerable, 12 should-ask, 29 conversations)

Final answer correct, original model (full prompt) against fine-tuned (Q8_0, compact prompt):

| Keyword rules | Original | Fine-tuned | Only original right | Only fine-tuned right | p |
|---|---|---|---|---|---|
| `always` (the app today) | 82.4% | **85.8%** | 0 | 8 | 0.008 |
| `fired` (model decides intent when no keyword fires) | 74.7% | **87.1%** | 2 | 31 | < 0.0001 |
| `off` (the model alone) | 50.2% | **83.7%** | 3 | 81 | < 0.0001 |

On the 192 answerable questions: execution 84.4% → **87.5%** (`always`), 75.0% → **89.1%** (`fired`), 46.4% → **84.9%** (`off`).

The model's own frame (right intent, metric column and grouping, before any rules): **38.0% → 95.3%**
(intent 56.8% → 97.4%, grouping 59.4% → 97.9%, metric column 97.9% → 100%).

Per question type, `off` mode (what the model contributes by itself):

| Type | n | Original | Fine-tuned |
|---|---|---|---|
| aggregation words (average, largest, ...) | 21 | 19% | **81%** |
| intent with no trigger word | 23 | 30% | **87%** |
| Hinglish | 19 | 21% | **84%** |
| Indian financial year | 19 | 58% | **100%** |
| follow-ups (final turn) | 29 | 55% | **79%** |
| unusual retail words (outlet, town, GMV) | 23 | 26% | 48% |
| typos | 12 | 75% | 92% |

With the rules on (`always`) the gains shrink, because the rules already fix most of what the original model gets wrong: that is the point of the rules.
**Where the fine-tune still adds with rules on:** aggregation words (52% → 67%), financial-year questions (89% → 100%), follow-ups (72% → 79%).

Refusing or asking when it should: 9 of 12 either way (75%); the three misses are "what's the weather in Mumbai", "write me a poem about sales", "delete all orders" (the pipeline answers them; not a model issue).
Over-asking (asking when it should answer): original 4 of 192, fine-tuned 0 of 192.

### Unseen schemas

| Dataset | Rules | Original | Fine-tuned | |
|---|---|---|---|---|
| Online Retail II (55) | `off` | 34.5% | **78.2%** | 0 lost, 24 gained, p < 0.0001 |
| Online Retail II | `always` | 74.5% | 76.4% | 0 lost, 1 gained |
| **Wholesale customers (51)** | `always` | **86.3%** | **13.7%** | 37 lost, 0 gained |
| **Wholesale customers** | `off` | 45.1% | 15.7% | |

### Regression on the older sets (`always`)

| Set | Original | Fine-tuned |
|---|---|---|
| gold (48) | 100% | 100% |
| held-out 1 (50) | 96% | 98% |
| held-out 2 (40) | 95% | 97.5% |
| held-out 3 (30) | 96.7% | 100% |

### Quantisation, prompt style, speed

* **Q4_K_M gives the same answers as Q8_0** on held-out 4: 0 differences in 233 cases. Q4_K_M is 491 MB, Q8_0 is 676 MB.
* **Compact and full prompts are equal** (85.8% and 85.4%, 1 difference). The original model cannot use the compact prompt (10% on held-out 4: it over-asks), because it needs the examples; the fine-tuned model does not.
* **Speed does not improve.** Quiet machine (Apple M5, CPU only, 120 questions): original Q4_K_M p50 **786 ms**, p95 1,590 ms; fine-tuned Q8_0 compact p50 **906 ms**, p95 1,518 ms; fine-tuned Q4_K_M compact p50 918 ms, p95 1,691 ms; fine-tuned Q8_0 full p50 977 ms. The shorter prompt does not buy time at this size. All stay under the 2 s patent target at p95 on this machine; this is **not** the 4-core target machine, which still has to be measured.

## The failure: more than one metric in the question

On Wholesale customers the model answered `total_spend` to nearly every question ("fresh spend by channel", "milk spend by region", ...).
Cause, checked on the raw frames: the dataset has a measure called *total spend* with the synonym *spend*, and the columns are *Fresh*, *Milk*, ...
So "fresh spend" gives **two** metric hints (`fresh = Fresh`, `spend = total_spend`). The original model picked the specific one; **the fine-tuned model always picks the generic one**.
Our training data never contained a question with two competing metric hints, so it learned nothing about this case, and the rules do not repair it
(they override the model's metric only when exactly one metric is named). It is a data gap, not a defect of the method.

Planned fix (round 2, not done): add training questions where a qualifier maps to one metric and a generic word ("spend", "sales", "value") maps to another measure,
with the specific one as the answer; retrain; then re-run this set. Caveat for that run: the failure class was found by the Wholesale test, so the Wholesale result becomes a regression check, no longer a first-run unseen score.
A cheap code-level safeguard is also possible (prefer the metric whose phrase is more specific when two are hinted).

## Decision

* **The original model stays the default.** The fine-tuned model wins clearly on held-out 4 and Online Retail but loses badly on Wholesale; a default must not.
* The fine-tuned model is **opt-in**: `LOCALLENS_MODEL_PATH=models/finetuned/locallens-colab-q4_k_m.gguf LOCALLENS_PROMPT_STYLE=compact` (and optionally `LOCALLENS_RULES=fired`).
* When round 2 passes (Wholesale back near 86% with the other sets unchanged), switch the default model, the prompt style to `compact` and the rules mode to `fired` (87.1% against 85.8% with `always` on held-out 4; to be confirmed on the new data).

## Viva framing: what each change contributed

1. **Pipeline groundwork** (commit `5a9e7e1`, before any training): retail synonyms, "pieces" sums quantity, schema field order. Held-out 3 went from 86.7% to 96.7% with the *original* model.
2. **Pipeline fixes found by the new tests**: Hinglish date words ("pichle mahine"), numeric group-by columns shown as labels (a crash on `Customer ID`), and a real-model embedding test.
3. **Fine-tuning**: on top of the above, +3.4 points with the rules on, +12 with `fired`, +33 with the model alone; and a model that no longer needs the examples in its prompt.

## What went wrong on the way (so you do not repeat it)

* The first local training run on the Mac **diverged** at about step 110 (loss 0.1 → 9). The mlx-lm LoRA multiplier `scale` = 20 is about ten times a PEFT `alpha / rank` of 2. With `scale` 2 and lr 2e-4 it trained smoothly.
* The Colab session was reset once (a restart came back on a TPU with all files gone). `train.ipynb` does not save progress; if you run it, leave the tab alone for the 1 h 40 min.
* Colab's newest transformers removed `warmup_ratio` (now `warmup_steps=0.05`), and its old `torchao` stops `peft`; both are handled in the notebook.
* llama.cpp's own converter and quantiser tool were not used (building third-party code was blocked). `finetune/export_gguf.py` does the conversion with the small `gguf` library and the `llama-cpp-python` quantiser, copying the tokenizer from the base GGUF; it was verified on the base model first (same answers as the official GGUF). Because of this, **no importance-matrix calibration** was done for Q4_K_M; Q4_K_M matched Q8_0 without it.

## Not verified

* One training run, one seed: no estimate of run-to-run spread.
* Test questions and training templates share an author. The overlap was filtered, not eliminated.
* Held-out 4 is the same *dataset* family as the demo (synthetic retail); only the two UCI sets are other schemas.
* No retail practitioner has reviewed the questions. The Wholesale failure shows how a schema choice can change the picture.
* Speed was measured on an M5 laptop, not the 4-core machine; peak memory was not re-measured with the fine-tuned model.
* Whether llama.cpp's JSON-schema grammar enforces the schema's property order was not tested directly; the raw frames in the logs follow the schema order.
* The Colab notebook was run end to end once, with the fixes above. A fresh Colab image may need further changes.

## Reproduce

```
python -I finetune/fetch_external.py                      # the two evaluation datasets (needs internet)
python -I finetune/build_data.py --schemas 110 --per-schema 80 --val-schemas 14
# train: finetune/train.ipynb on Colab (T4), or  ~/ft-env/bin/python finetune/train_mlx.py --model <Qwen2.5-0.5B-Instruct> --out finetune/runs/r --scale 2 --lr 2e-4
~/ft-env/bin/python finetune/export_gguf.py --stage f16 --fused finetune/runs/colab/fused --name locallens-colab
.venv/bin/python    finetune/export_gguf.py --stage quant --name locallens-colab
python eval/run_eval.py --set heldout4 --model models/finetuned/locallens-colab-q4_k_m.gguf --prompt-style compact --rules fired --out run.jsonl --show-failures
python eval/compare.py docs/results/base_full_fired_heldout4.jsonl run.jsonl
```
