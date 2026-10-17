"""One-time model download. This is the only step that needs internet.

Usage: python scripts/download_model.py            # the language model (about 490 MB) and the embedding model (35 MB)
       python scripts/download_model.py --no-embeddings
"""
import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download

DEST = Path(__file__).resolve().parents[1] / "models"
MODELS = {
    "language": ("Qwen/Qwen2.5-0.5B-Instruct-GGUF", "qwen2.5-0.5b-instruct-q4_k_m.gguf"),
    "embeddings": ("CompendiumLabs/bge-small-en-v1.5-gguf", "bge-small-en-v1.5-q8_0.gguf"),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embeddings", action="store_true", help="skip the optional 35 MB term-matching model")
    args = ap.parse_args()
    DEST.mkdir(exist_ok=True)
    for kind, (repo, name) in MODELS.items():
        if kind == "embeddings" and args.no_embeddings:
            continue
        path = hf_hub_download(repo_id=repo, filename=name, local_dir=DEST)
        print(f"{kind} model ready: {path}")


if __name__ == "__main__":
    main()
