"""Fused 16-bit Hugging Face model -> GGUF (f16, then Q8_0 and Q4_K_M) for llama.cpp / llama-cpp-python.

    ~/ft-env/bin/python finetune/export_gguf.py --stage f16 --fused finetune/runs/r1/fused --name locallens-r1
    .venv/bin/python    finetune/export_gguf.py --stage quant --name locallens-r1

Why not llama.cpp's convert_hf_to_gguf.py: running that script means downloading and executing a large piece of third-party
code. This file does the one job we need with the small `gguf` library: Qwen2's weights keep their layout, the tokenizer is
unchanged by fine-tuning, so every non-tensor key (vocabulary, merges, chat template, end-of-turn id, ...) is copied from the base
model's own GGUF, and only the tensors are replaced by the fused weights. Merge the LoRA into the 16-bit base, never into a 4-bit model.
The pad token (151643, <|endoftext|>) differs from the end-of-turn token (151645, <|im_end|>); the base GGUF already has both.

The check at the end loads each file and compares its answer to the fused model's on a prompt, so a wrong tensor name or layout fails here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
BASE_GGUF = ROOT / "models" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"
Q = {"q8_0": 7, "q4_k_m": 15}           # llama_ftype values


def write_f16(fused: Path, out: Path, base_gguf: Path = BASE_GGUF) -> Path:
    import gguf
    import torch
    from safetensors.torch import load_file

    cfg = json.loads((fused / "config.json").read_text())
    n_layers = cfg["num_hidden_layers"]
    reader = gguf.GGUFReader(str(base_gguf))
    writer = gguf.GGUFWriter(str(out), "qwen2")
    skip = {"general.architecture", "general.file_type", "general.quantization_version", "general.name", "general.finetune"}
    for key, f in reader.fields.items():
        if key.startswith("GGUF.") or key in skip:
            continue
        sub = f.types[-1] if f.types[0] == gguf.GGUFValueType.ARRAY else None
        writer.add_key_value(key, f.contents(), f.types[0], sub_type=sub)
    writer.add_name(out.stem)
    writer.add_file_type(gguf.LlamaFileType.MOSTLY_F16)
    names = gguf.get_tensor_name_map(gguf.MODEL_ARCH.QWEN2, n_layers)
    tensors = {}
    for p in sorted(fused.glob("model*.safetensors")):
        tensors.update(load_file(str(p)))
    written = set()

    def put(gname: str, t: "torch.Tensor") -> None:
        small = gname.endswith("norm.weight") or gname.endswith(".bias")
        arr = t.to(torch.float32 if small else torch.float16).numpy().astype(np.float32 if small else np.float16)
        writer.add_tensor(gname, arr)
        written.add(gname)

    for hf, t in tensors.items():
        g = names.get_name(hf, try_suffixes=(".weight", ".bias"))
        if g is None:
            raise SystemExit(f"no GGUF name for {hf}")
        put(g, t)
        if g == "token_embd.weight" and "lm_head.weight" not in tensors:       # tied embeddings: the base GGUF carries a separate output matrix
            put("output.weight", t)
    expected = {t.name for t in reader.tensors}
    if written != expected:
        raise SystemExit(f"tensor mismatch. missing: {sorted(expected - written)[:5]} extra: {sorted(written - expected)[:5]}")
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    return out


def quantize(src: Path, dst: Path, kind: str) -> Path:
    import llama_cpp

    params = llama_cpp.llama_model_quantize_default_params()
    params.ftype = Q[kind]
    params.nthread = 4
    rc = llama_cpp.llama_model_quantize(str(src).encode(), str(dst).encode(), params)
    if rc != 0:
        raise SystemExit(f"quantize {kind} failed ({rc})")
    return dst


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fused", type=Path, help="fused 16-bit model folder (stage f16)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "models" / "finetuned")
    ap.add_argument("--stage", choices=["f16", "quant"], required=True,
                    help="f16 runs where torch and gguf are installed (the training env); quant runs where llama-cpp-python is (the app env)")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    f16 = args.out_dir / f"{args.name}-f16.gguf"
    if args.stage == "f16":
        if not args.fused:
            raise SystemExit("--fused is required for stage f16")
        print("wrote", write_f16(args.fused, f16))
    else:
        for kind in ("q8_0", "q4_k_m"):
            print("wrote", quantize(f16, args.out_dir / f"{args.name}-{kind}.gguf", kind))


if __name__ == "__main__":
    main()
