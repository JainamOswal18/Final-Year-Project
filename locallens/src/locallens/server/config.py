"""Server settings. Every value can be set with a LOCALLENS_* environment variable."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"LOCALLENS_{name}", default)


@dataclass
class Settings:
    host: str = field(default_factory=lambda: _env("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(_env("PORT", "8000")))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(ROOT / "data" / "server"))))
    model_path: Path = field(default_factory=lambda: Path(_env("MODEL_PATH", str(ROOT / "models" / "qwen2.5-0.5b-instruct-q4_k_m.gguf"))))
    embed_model_path: Path = field(default_factory=lambda: Path(_env("EMBED_MODEL_PATH", str(ROOT / "models" / "bge-small-en-v1.5-q8_0.gguf"))))
    use_embeddings: bool = field(default_factory=lambda: _env("EMBEDDINGS", "1") == "1")
    web_dir: Path = field(default_factory=lambda: Path(_env("WEB_DIR", str(ROOT / "web" / "dist"))))
    n_ctx: int = field(default_factory=lambda: int(_env("N_CTX", "2048")))
    n_threads: int | None = field(default_factory=lambda: int(_env("N_THREADS", "0")) or None)
    model_time_budget_s: float = field(default_factory=lambda: float(_env("MODEL_TIME_BUDGET_S", "30")))
    preload_model: bool = field(default_factory=lambda: _env("PRELOAD_MODEL", "1") == "1")
    session_hours: float = field(default_factory=lambda: float(_env("SESSION_HOURS", "12")))
    secure_cookies: bool = field(default_factory=lambda: _env("SECURE_COOKIES", "0") == "1")  # set 1 behind HTTPS
    max_upload_mb: int = field(default_factory=lambda: int(_env("MAX_UPLOAD_MB", "200")))
    max_result_rows: int = field(default_factory=lambda: int(_env("MAX_RESULT_ROWS", "5000")))
    login_max_failures: int = field(default_factory=lambda: int(_env("LOGIN_MAX_FAILURES", "5")))
    login_lock_minutes: float = field(default_factory=lambda: float(_env("LOGIN_LOCK_MINUTES", "5")))
    cache_datasets: int = field(default_factory=lambda: int(_env("CACHE_DATASETS", "8")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def datasets_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"
