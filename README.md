# Final-Year-Project: LocalLens

A final-year project that turns the faculty patent *"A System and Method for Privacy-Preserving Offline
Language-to-Visualization Conversion"* (specification dated 18.02.2026, included here as a `.docx`) into a working product:
ask a question about your data in plain language, get a chart, with a small language model running entirely on your own machine.

| | |
|---|---|
| **The product** | [`locallens/`](locallens/) — start there: [`locallens/README.md`](locallens/README.md) |
| **How it works, and how it maps to the patent claims** | [`locallens/docs/ARCHITECTURE.md`](locallens/docs/ARCHITECTURE.md) |
| **How accurate it is (measured on questions it had not seen)** | [`locallens/docs/EVAL.md`](locallens/docs/EVAL.md) |
| **The patent** | `Comp Spec_Privacy-Preserving Offline Language_18.02.2026.docx` |

```bash
cd locallens && ./start.sh        # Windows: start.bat   ->  http://127.0.0.1:8000
```
