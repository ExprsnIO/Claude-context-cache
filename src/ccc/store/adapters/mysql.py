"""MySQL adapter (lazy import of `pymysql`)."""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse

from ccc.store.config import strip_namespace, with_namespace
from ccc.store.types import ContextStore

_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _import_pymysql():
    try:
        import pymysql  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "mysql backend requested but the 'pymysql' package is not installed. "
            "Run `pip install pymysql` or unset CCC_MYSQL_URL."
        ) from exc
    return pymysql


class MysqlAdapter(ContextStore):
    kind = "mysql"

    def __init__(
        self,
        *,
        url: str,
        namespace: str,
        table: str,
        probe_timeout_ms: int,
    ) -> None:
        if not _TABLE_RE.match(table):
            raise ValueError(f"invalid mysql table name: {table!r}")
        pymysql = _import_pymysql()
        parsed = urlparse(url)
        self._conn = pymysql.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "",
            password=parsed.password or "",
            database=(parsed.path.lstrip("/") if parsed.path else None) or None,
            connect_timeout=max(probe_timeout_ms // 1000, 1),
            autocommit=True,
        )
        self._namespace = namespace
        self._table = table
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{table}` (
                  `key` VARCHAR(512) PRIMARY KEY,
                  `value` LONGTEXT NOT NULL,
                  `expires_at` BIGINT NULL,
                  `updated_at` BIGINT NOT NULL,
                  INDEX (`expires_at`)
                )
                """
            )

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _sweep(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM `{self._table}` WHERE expires_at IS NOT NULL AND expires_at < %s",
                (self._now_ms(),),
            )

    def get(self, key: str) -> str | None:
        self._sweep()
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT `value` FROM `{self._table}` WHERE `key` = %s",
                (with_namespace(self._namespace, key),),
            )
            row = cur.fetchone()
        return row[0] if row else None

    def set(self, key: str, value: str, *, ttl_ms: int | None = None) -> None:
        now = self._now_ms()
        expires_at = now + ttl_ms if ttl_ms else None
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO `{self._table}` (`key`, `value`, `expires_at`, `updated_at`)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  `value` = VALUES(`value`),
                  `expires_at` = VALUES(`expires_at`),
                  `updated_at` = VALUES(`updated_at`)
                """,
                (with_namespace(self._namespace, key), value, expires_at, now),
            )

    def delete(self, key: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM `{self._table}` WHERE `key` = %s",
                (with_namespace(self._namespace, key),),
            )
            return cur.rowcount > 0

    def list(self, prefix: str | None = None) -> list[str]:
        self._sweep()
        match = with_namespace(self._namespace, f"{prefix or ''}%")
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT `key` FROM `{self._table}` WHERE `key` LIKE %s",
                (match,),
            )
            return [strip_namespace(self._namespace, r[0]) for r in cur.fetchall()]

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass


def open_mysql(
    *, url: str, namespace: str, table: str, probe_timeout_ms: int
) -> MysqlAdapter:
    return MysqlAdapter(
        url=url, namespace=namespace, table=table, probe_timeout_ms=probe_timeout_ms
    )
