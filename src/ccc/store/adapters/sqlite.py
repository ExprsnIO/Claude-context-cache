"""SQLite adapter (in-memory and on-disk)."""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Literal

from ccc.store.config import strip_namespace, with_namespace
from ccc.store.types import ContextStore

SqliteKind = Literal["sqlite-memory", "sqlite-disk"]


class SqliteAdapter(ContextStore):
    def __init__(self, *, path: str, namespace: str, kind: SqliteKind) -> None:
        self.kind = kind
        self._namespace = namespace
        if kind == "sqlite-disk":
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self._conn = sqlite3.connect(
            ":memory:" if kind == "sqlite-memory" else path,
            isolation_level=None,
            # The Session may close us from its idle-timer thread; the
            # surrounding Session lock keeps reads/writes single-threaded.
            check_same_thread=False,
        )
        if kind == "sqlite-disk":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS ccc_context (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at INTEGER,
                updated_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ccc_context_expires_idx
                ON ccc_context(expires_at) WHERE expires_at IS NOT NULL;
            """
        )

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _sweep(self) -> None:
        self._conn.execute(
            "DELETE FROM ccc_context WHERE expires_at IS NOT NULL AND expires_at < ?",
            (self._now_ms(),),
        )

    def get(self, key: str) -> str | None:
        self._sweep()
        row = self._conn.execute(
            "SELECT value, expires_at FROM ccc_context WHERE key = ?",
            (with_namespace(self._namespace, key),),
        ).fetchone()
        if row is None:
            return None
        value, expires_at = row
        if expires_at is not None and expires_at < self._now_ms():
            self._conn.execute(
                "DELETE FROM ccc_context WHERE key = ?",
                (with_namespace(self._namespace, key),),
            )
            return None
        return value

    def set(self, key: str, value: str, *, ttl_ms: int | None = None) -> None:
        now = self._now_ms()
        expires_at = now + ttl_ms if ttl_ms else None
        self._conn.execute(
            """
            INSERT INTO ccc_context (key, value, expires_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value = excluded.value,
              expires_at = excluded.expires_at,
              updated_at = excluded.updated_at
            """,
            (with_namespace(self._namespace, key), value, expires_at, now),
        )

    def delete(self, key: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM ccc_context WHERE key = ?",
            (with_namespace(self._namespace, key),),
        )
        return cursor.rowcount > 0

    def list(self, prefix: str | None = None) -> list[str]:
        self._sweep()
        if prefix is not None:
            full = with_namespace(self._namespace, prefix)
            rows = self._conn.execute(
                "SELECT key FROM ccc_context WHERE key LIKE ?",
                (f"{full}%",),
            ).fetchall()
        elif self._namespace:
            rows = self._conn.execute(
                "SELECT key FROM ccc_context WHERE key LIKE ?",
                (f"{self._namespace}:%",),
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT key FROM ccc_context").fetchall()
        return [strip_namespace(self._namespace, r[0]) for r in rows]

    def close(self) -> None:
        self._conn.close()


def open_sqlite(*, path: str, namespace: str, kind: SqliteKind) -> SqliteAdapter:
    return SqliteAdapter(path=path, namespace=namespace, kind=kind)
