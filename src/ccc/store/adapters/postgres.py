"""Postgres adapter (lazy import of `psycopg`)."""

from __future__ import annotations

import re
import time

from ccc.store.config import strip_namespace, with_namespace
from ccc.store.types import ContextStore

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _import_psycopg():
    try:
        import psycopg  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "postgres backend requested but the 'psycopg' package is not installed. "
            "Run `pip install 'psycopg[binary]'` or unset CCC_POSTGRES_URL."
        ) from exc
    return psycopg


def _quote_ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise ValueError(f"invalid postgres identifier: {name!r}")
    return f'"{name}"'


class PostgresAdapter(ContextStore):
    kind = "postgres"

    def __init__(
        self,
        *,
        url: str,
        namespace: str,
        table: str,
        probe_timeout_ms: int,
    ) -> None:
        psycopg = _import_psycopg()
        timeout_s = max(probe_timeout_ms // 1000, 1)
        self._conn = psycopg.connect(url, connect_timeout=timeout_s, autocommit=True)
        self._namespace = namespace
        self._table = table
        t = _quote_ident(table)
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {t} (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL,
                  expires_at BIGINT NULL,
                  updated_at BIGINT NOT NULL
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS {_quote_ident(table + '_expires_idx')} "
                f"ON {t}(expires_at) WHERE expires_at IS NOT NULL"
            )

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _sweep(self) -> None:
        t = _quote_ident(self._table)
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {t} WHERE expires_at IS NOT NULL AND expires_at < %s",
                (self._now_ms(),),
            )

    def get(self, key: str) -> str | None:
        self._sweep()
        t = _quote_ident(self._table)
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT value FROM {t} WHERE key = %s",
                (with_namespace(self._namespace, key),),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str, *, ttl_ms: int | None = None) -> None:
        now = self._now_ms()
        expires_at = now + ttl_ms if ttl_ms else None
        t = _quote_ident(self._table)
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {t} (key, value, expires_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (key) DO UPDATE SET
                  value = EXCLUDED.value,
                  expires_at = EXCLUDED.expires_at,
                  updated_at = EXCLUDED.updated_at
                """,
                (with_namespace(self._namespace, key), value, expires_at, now),
            )

    def delete(self, key: str) -> bool:
        t = _quote_ident(self._table)
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {t} WHERE key = %s",
                (with_namespace(self._namespace, key),),
            )
            return cur.rowcount > 0

    def list(self, prefix: str | None = None) -> list[str]:
        self._sweep()
        t = _quote_ident(self._table)
        match = with_namespace(self._namespace, f"{prefix or ''}%")
        with self._conn.cursor() as cur:
            cur.execute(f"SELECT key FROM {t} WHERE key LIKE %s", (match,))
            return [strip_namespace(self._namespace, r[0]) for r in cur.fetchall()]

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


def open_postgres(
    *, url: str, namespace: str, table: str, probe_timeout_ms: int
) -> PostgresAdapter:
    return PostgresAdapter(
        url=url, namespace=namespace, table=table, probe_timeout_ms=probe_timeout_ms
    )
