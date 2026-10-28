"""LoRA fine-tuning on Apple silicon with mlx-lm (16-bit LoRA on the fp16/bf16 base, loss on the answer only).

    ~/ft-env/bin/python finetune/train_mlx.py --model <Qwen2.5-0.5B-Instruct folder> --out finetune/runs/r1 [--iters N]

The same recipe is in finetune/train.ipynb for a Colab GPU. Steps: (1) write the data in mlx-lm's folder layout,
(2) train the adapter, (3) fuse it into the 16-bit base, which finetune/export_gguf.py then converts.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LORA_KEYS = ["self_attn.q_proj", "self_attn.k_proj", "self_attn.v_proj", "self_attn.o_proj", "mlp.gate_proj", "mlp.up_proj", "mlp.down_proj"]


def prepare(out: Path) -> tuple[int, int]:
    data = out / "data"
    data.mkdir(parents=True, exist_ok=True)
    counts = []
    for src, dst in (("train", "train"), ("val", "valid")):
        rows = [json.loads(l) for l in (ROOT / "data" / f"{src}.jsonl").read_text().splitlines() if l.strip()]
        (data / f"{dst}.jsonl").write_text("\n".join(json.dumps({"messages": r["messages"]}) for r in rows) + "\n")
        counts.append(len(rows))
    return counts[0], counts[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--iters", type=int, help="optimizer steps (default: epochs x examples / effective batch)")
    ap.add_argument("--lr", type=float, default=1.5e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--scale", type=float, default=20.0, help="mlx-lm's LoRA multiplier (about alpha / rank x 10 in PEFT terms)")
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    out = args.out.resolve()
    n_train, n_val = prepare(out)
    iters = args.iters or int(args.epochs * n_train / (args.batch * args.accum))
    cfg = {
        "model": str(args.model), "train": True, "data": str(out / "data"), "fine_tune_type": "lora", "optimizer": "adamw",
        "mask_prompt": True, "num_layers": -1, "batch_size": args.batch, "grad_accumulation_steps": args.accum, "iters": iters,
        "learning_rate": args.lr, "steps_per_report": 10, "steps_per_eval": max(25, iters // 10), "val_batches": 40,
        "save_every": max(25, iters // 10), "max_seq_length": 2048, "grad_checkpoint": True, "seed": args.seed,
        "adapter_path": str(out / "adapter"),
        "lr_schedule": {"name": "cosine_decay", "warmup": max(5, iters // 20), "arguments": [args.lr, iters, args.lr / 20]},
        "lora_parameters": {"rank": args.rank, "scale": args.scale, "dropout": 0.0, "keys": LORA_KEYS},
    }
    (out / "config.yaml").write_text(json.dumps(cfg, indent=2))     # JSON is valid YAML
    print(f"{n_train} training and {n_val} validation examples, {iters} steps", flush=True)
    subprocess.run([sys.executable, "-m", "mlx_lm", "lora", "-c", str(out / "config.yaml")], check=True)
    subprocess.run([sys.executable, "-m", "mlx_lm", "fuse", "--model", str(args.model), "--adapter-path", str(out / "adapter"),
                    "--save-path", str(out / "fused"), "--dequantize"], check=True)
    print("fused model:", out / "fused")


if __name__ == "__main__":
    main()
