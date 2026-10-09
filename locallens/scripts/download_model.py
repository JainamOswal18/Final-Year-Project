"""One-time model download. This is the only step that needs internet.

Usage: python scripts/download_model.py
"""
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = "Qwen/Qwen2.5-0.5B-Instruct-GGUF"
FILE = "qwen2.5-0.5b-instruct-q4_k_m.gguf"
DEST = Path(__file__).resolve().parents[1] / "models"


def main() -> None:
    DEST.mkdir(exist_ok=True)
    path = hf_hub_download(repo_id=REPO, filename=FILE, local_dir=DEST)
    print(f"Model ready: {path}")


if __name__ == "__main__":
    main()
