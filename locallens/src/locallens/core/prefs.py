"""Saved chart preferences (patent: persisted user preferences), local JSON file."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "prefs.json"
DEFAULTS: dict = {"chart_overrides": {}, "sort": "desc", "default_agg": "SUM"}


def load(path: Path = DEFAULT_PATH) -> dict:
    try:
        return {**DEFAULTS, **json.loads(path.read_text())}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def save(prefs: dict, path: Path = DEFAULT_PATH) -> None:
    path.write_text(json.dumps(prefs, indent=2))
