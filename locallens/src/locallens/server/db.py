"""SQLite storage for users, sessions, datasets, conversations, messages and preferences."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE COLLATE NOCASE,
        pw_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
        active INTEGER NOT NULL DEFAULT 1,
        must_change_password INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        last_login TEXT)""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS datasets (
        id TEXT PRIMARY KEY,
        owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        visibility TEXT NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'shared')),
        registry_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')))""",
    """CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        last_frame TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')))""",
    """CREATE TABLE IF NOT EXISTS messages (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        question TEXT NOT NULL,
        response_json TEXT NOT NULL,
        rating INTEGER,
        rating_note TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')))""",
    """CREATE TABLE IF NOT EXISTS prefs (
        user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        json TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL DEFAULT (datetime('now')),
        user_id INTEGER,
        action TEXT NOT NULL,
        detail TEXT)""",
    "CREATE INDEX IF NOT EXISTS ix_msg_conv ON messages(conversation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_conv_user ON conversations(user_id, dataset_id, updated_at)",
    "CREATE INDEX IF NOT EXISTS ix_sessions_exp ON sessions(expires_at)",
]


class Database:
    """One connection per thread (sqlite3 connections are not shareable across threads)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.tx() as c:
            for stmt in SCHEMA:
                c.execute(stmt)

    def _conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA busy_timeout=30000")
            self._local.conn = c
        return c

    @contextmanager
    def tx(self):
        c = self._conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        else:
            c.execute("COMMIT")

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        return self._conn().execute(sql, args).fetchone()

    def all(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self._conn().execute(sql, args).fetchall()

    def run(self, sql: str, args: tuple = ()) -> int:
        with self.tx() as c:
            return c.execute(sql, args).rowcount
