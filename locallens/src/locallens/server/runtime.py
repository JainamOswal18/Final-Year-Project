"""Process-wide state: database, the one language model, and loaded datasets."""
from __future__ import annotations

import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

import duckdb

from ..data import ingest
from ..data.registry import Registry
from .config import Settings
from .db import Database
from .links import LinkStore
from .security import LoginThrottle

log = logging.getLogger("locallens")


@dataclass
class LoadedDataset:
    id: str
    reg: Registry
    con: duckdb.DuckDBPyConnection
    term_index: object | None = None                       # embedded vocabulary (claim 7), when available
    lock: threading.RLock = field(default_factory=threading.RLock)   # a DuckDB connection is not thread-safe


class Runtime:
    def __init__(self, settings: Settings, slm_factory: Callable[[], object] | None = None):
        self.settings = settings
        for d in (settings.data_dir, settings.datasets_dir, settings.exports_dir, settings.log_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.db = Database(settings.db_path)
        self.links = LinkStore()
        self.throttle = LoginThrottle(settings.login_max_failures, settings.login_lock_minutes)
        self._slm_factory = slm_factory or self._default_slm
        self._slm = None
        self._slm_lock = threading.Lock()
        self._embedder = None
        self._embedder_tried = False
        self.model_error = ""
        self.ask_lock = threading.Lock()                   # the model answers one question at a time
        self._cache: OrderedDict[str, LoadedDataset] = OrderedDict()
        self._cache_lock = threading.Lock()

    # ---- model ---------------------------------------------------------------------
    def _default_slm(self):
        from ..nlu.slm import SLM

        return SLM(model_path=self.settings.model_path, n_ctx=self.settings.n_ctx,
                   n_threads=self.settings.n_threads, time_budget_s=self.settings.model_time_budget_s)

    def slm(self):
        with self._slm_lock:
            if self._slm is None:
                try:
                    self._slm = self._slm_factory()
                    self.model_error = ""
                except Exception as e:  # missing model file, bad install...
                    self.model_error = str(e)
                    raise
            return self._slm

    def embedder(self):
        """The optional embedding model: None if disabled or its file is missing (the app works without it)."""
        with self._slm_lock:
            if not self._embedder_tried:
                self._embedder_tried = True
                if self.settings.use_embeddings and self.settings.embed_model_path.exists():
                    try:
                        from ..nlu.embeddings import LlamaEmbedder

                        self._embedder = LlamaEmbedder(self.settings.embed_model_path)
                    except Exception as e:
                        log.warning("embedding model not loaded: %s", e)
            return self._embedder

    @property
    def model_loaded(self) -> bool:
        return self._slm is not None

    def preload(self) -> None:
        def run():
            try:
                self.slm()
                log.info("language model loaded")
            except Exception as e:
                log.warning("language model not loaded: %s", e)

        threading.Thread(target=run, name="model-preload", daemon=True).start()

    # ---- datasets -------------------------------------------------------------------
    def dataset_dir(self, dataset_id: str):
        return self.settings.datasets_dir / dataset_id

    def registry_from_row(self, row) -> Registry:
        """The stored registry keeps file names; resolve them to this machine's paths."""
        reg = Registry.model_validate(json.loads(row["registry_json"]))
        d = self.dataset_dir(row["id"])
        reg.tables = {t: str(d / f) for t, f in reg.tables.items()}
        return reg

    def registry_to_json(self, reg: Registry) -> str:
        from pathlib import Path

        stored = reg.model_copy(deep=True)
        stored.tables = {t: Path(p).name for t, p in reg.tables.items()}
        return stored.model_dump_json()

    def load_dataset(self, dataset_id: str) -> LoadedDataset:
        with self._cache_lock:
            hit = self._cache.get(dataset_id)
            if hit:
                self._cache.move_to_end(dataset_id)
                return hit
        row = self.db.one("SELECT * FROM datasets WHERE id = ?", (dataset_id,))
        if row is None:
            raise KeyError(dataset_id)
        reg = self.registry_from_row(row)
        con = ingest.prepare(reg)
        loaded = LoadedDataset(dataset_id, reg, con, self._term_index(reg))
        with self._cache_lock:
            self._cache[dataset_id] = loaded
            while len(self._cache) > self.settings.cache_datasets:
                _, old = self._cache.popitem(last=False)
                old.con.close()
        return loaded

    def _term_index(self, reg: Registry):
        emb = self.embedder()
        if emb is None:
            return None
        try:
            from ..nlu.embeddings import TermIndex

            return TermIndex(emb, reg)
        except Exception as e:
            log.warning("term index not built: %s", e)
            return None

    def invalidate(self, dataset_id: str) -> None:
        with self._cache_lock:
            old = self._cache.pop(dataset_id, None)
        if old:
            with old.lock:
                old.con.close()
