# Evaluation

All numbers are from the real model (Qwen2.5-0.5B-Instruct, 4-bit, CPU only) on the synthetic retail demo data,
on an Apple-silicon laptop. **Execution accuracy** means the result table equals the table produced by the
hand-written gold query. It is the number to quote; per-field accuracies are in the raw output files.

## The honest numbers

A question set is only evidence the **first** time it is run. After fixes are made from its failures it becomes
a regression test. So each set below has a "first run" (untuned) and a "now" column.

| Set | Written | Questions | First run (untuned) | Now (after fixes) |
|---|---|---|---|---|
| `questions.py` (gold) | while building the rules | 48 | 80% model alone, 100% with rules | 100% |
| `heldout.py` | after the rules were tuned | 50 | **78%** (39/50)* | 100% (tuned) |
| `heldout2.py` | after round-1 fixes | 40 | **85%** (34/40) | 100% (tuned) |
| `heldout3.py` | after round-2 fixes | 30 | **83%** (25/30) with matching by meaning, **73%** (22/30) without | 87% (26/30) and 3 more answered by asking |

\* two of those 11 misses were mistakes in the gold file itself (a miscounted date, and "last month" taken from the
wrong day), so the system's true first-run score was about 82%.

**What to say in a report:** a small model with rules around it gets about 80-85% on questions it has never
seen, and roughly 100% on questions that were used to build it. The second number is not the one to quote.
The first-run raw outputs are kept in `docs/heldout_round1_raw.txt`, `docs/heldout2_round1_raw.txt` and
`docs/heldout3_round1_*embeddings.txt`.

Latency: median 0.7-0.8 s, 95th percentile 1.4-2.1 s per question, 4 performance cores, no GPU.

## What the failures taught (and what was changed)

| Found by | Problem | Fix |
|---|---|---|
| held-out 1 | "per quarter", "growing", "distributed" did not signal a trend / distribution | wider keyword rules (`nlu/rules.py`) |
| held-out 1 | "lowest" / "bottom 5" returned the highest | the query frame gained an `order` field, set by rules, never by the model |
| held-out 1 | "sub-category" (hyphen) not recognised | hyphens between words are spaces |
| held-out 1 | "the Technology category by month" grouped by category instead of filtering | a value next to its column name is a filter |
| held-out 1 | "highest revenue store" returned ten stores | a singular dimension with a superlative means one |
| held-out 1 | spell-fixer rewrote plurals ("products" to "product") | plurals of known words are left alone |
| held-out 2 | month names ("December 2025") ignored | month-name date parsing |
| held-out 2 | "West" exists in two columns, both were filtered | pick the column named next to it, else ask |
| held-out 2 | "profitable" not seen as "profit" | suffixes -able / -ability |
| held-out 3 | unknown words ("shop") unmatched | matching by meaning with a small embedding model (claim 7) |
| held-out 3 | "units sold by town" silently became one total | an unexplained word after by/per/each now triggers a question |
| first run | the model invented `top_n`, filters and groupings | every one of those must be backed by the question |

## Matching by meaning (patent claim 7), measured

A 35 MB embedding model compares unexplained words with the dataset's own vocabulary. Strict settings
(similarity at least 0.80 and a clear lead over the runner-up) mean it fired on about a third of paraphrases in a
direct test, with **no false matches on greetings and filler words**. On the third held-out set it moved the
first-run score from 73% to 83%. It is weak at telling domain words apart: "town", "outlet" and "pieces" were
not matched, which is why the clarifying question matters more than the embeddings.

## Fine-tuned model, measured (held-out 4 and two unseen schemas)

Full report: `docs/FINETUNING.md`; raw runs in `docs/results/v2/`. Final-answer accuracy, all three run through the same pipeline. Held-out 4 was frozen before training.
Round 2 is the default model.

| Set | Rules | Original | Round 1 | **Round 2** |
|---|---|---|---|---|
| held-out 4 (233 cases) | `always` | 84.1% | 85.8% | 84.1% (same as the original, p = 1.0) |
| held-out 4 | `fired` | 77.7% | 87.1% | 85.8% (vs original p = 0.0005) |
| held-out 4 | `off` (model alone) | 50.2% | 83.3% | 80.3% (vs original p < 0.0001) |
| Online Retail II (55) | `always` / `off` | 74.5% / 38.2% | 76.4% / 78.2% | 76.4% / 76.4% |
| Wholesale customers (51) | `always` / `off` | 86.3% / 45.1% | **13.7%** / 15.7% | 88.2% / 92.2% |

Round 1 broke Wholesale (it picked the generic metric when a question named two); round 2's data covers that case. Wholesale is therefore a regression check, not an unseen score, for round 2.
The honest summary: with the rules on, the fine-tuned model is as accurate as the original; its gain is what the model does by itself and a shorter prompt. It is not faster.

## Known limits

* The data is synthetic and the questions were written by the same team, in English only.
* Questions are single-turn in the harness; follow-ups are covered by unit tests, not by this score.
* Accuracy on a real company's data will be lower until its terms are added on the Definitions page.
  Use the thumbs-down button and the Administration page to collect real failures, then add them here.

## How to run

```
python eval/run_eval.py --set gold|heldout|heldout2|heldout3|heldout4|online_retail|wholesale [--show-failures] [--no-embeddings]
                        [--rules always|fired|off] [--model path/to/other.gguf] [--prompt-style full|compact]
                        [--out run.jsonl] [--no-sequences]
python eval/compare.py a.jsonl b.jsonl      # paired McNemar test between two runs
```

* `--rules always` (default, same as the app): keyword rules decide the question type and aggregation, and their
  fallbacks decide when no keyword fires. `fired`: the model decides when no keyword fires. `off`: no keyword rules
  (grounding, dates and the SQL check still apply). Use these to see what the model contributes, e.g. base vs fine-tuned.
* `--model` runs another GGUF file, such as a fine-tuned model, through the same questions.
* The report also prints **model alone (before rules)**: how often the model's own frame had the right intent,
  metric column and grouping. Failures show the model's raw frame next to the final one.
