"""Build a tiered ContextStore: cache (Redis -> SQLite) + optional backing."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from ccc.store.adapters.mongodb import open_mongo
from ccc.store.adapters.mysql import open_mysql
from ccc.store.adapters.postgres import open_postgres
from ccc.store.adapters.redis import open_redis
from ccc.store.adapters.sqlite import open_sqlite
from ccc.store.config import StoreConfig, load_config
from ccc.store.types import BackendKind, ContextStore, ProbeAttempt, StoreInfo


def _try_open_cache(
    cfg: StoreConfig, attempts: list[ProbeAttempt]
) -> ContextStore:
    if cfg.redis_url and not cfg.disable_redis:
        try:
            store = open_redis(
                url=cfg.redis_url,
                namespace=cfg.namespace,
                probe_timeout_ms=cfg.probe_timeout_ms,
            )
            attempts.append(ProbeAttempt(kind="redis", ok=True))
            return store
        except Exception as exc:
            attempts.append(
                ProbeAttempt(kind="redis", ok=False, error=str(exc))
            )
    if not cfg.disable_sqlite_memory:
        try:
            store = open_sqlite(
                path=":memory:",
                namespace=cfg.namespace,
                kind="sqlite-memory",
            )
            attempts.append(ProbeAttempt(kind="sqlite-memory", ok=True))
            return store
        except Exception as exc:
            attempts.append(
                ProbeAttempt(kind="sqlite-memory", ok=False, error=str(exc))
            )
    store = open_sqlite(
        path=cfg.sqlite_path,
        namespace=cfg.namespace,
        kind="sqlite-disk",
    )
    attempts.append(ProbeAttempt(kind="sqlite-disk", ok=True))
    return store


def _try_open_backing(
    cfg: StoreConfig, attempts: list[ProbeAttempt]
) -> ContextStore | None:
    if cfg.mysql_url:
        store = open_mysql(
            url=cfg.mysql_url,
            namespace=cfg.namespace,
            table=cfg.table_name,
            probe_timeout_ms=cfg.probe_timeout_ms,
        )
        attempts.append(ProbeAttempt(kind="mysql", ok=True))
        return store
    if cfg.postgres_url:
        store = open_postgres(
            url=cfg.postgres_url,
            namespace=cfg.namespace,
            table=cfg.table_name,
            probe_timeout_ms=cfg.probe_timeout_ms,
        )
        attempts.append(ProbeAttempt(kind="postgres", ok=True))
        return store
    if cfg.mongo_url:
        store = open_mongo(
            url=cfg.mongo_url,
            namespace=cfg.namespace,
            collection=cfg.table_name,
            probe_timeout_ms=cfg.probe_timeout_ms,
        )
        attempts.append(ProbeAttempt(kind="mongodb", ok=True))
        return store
    return None


class TieredStore(ContextStore):
    """Cache-fronted store: reads cache first, fills from backing on miss; writes to both."""

    def __init__(self, cache: ContextStore, backing: ContextStore | None) -> None:
        self._cache = cache
        self._backing = backing
        self.kind = cache.kind

    def get(self, key: str) -> str | None:
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if self._backing is None:
            return None
        persisted = self._backing.get(key)
        if persisted is not None:
            self._cache.set(key, persisted)
        return persisted

    def set(self, key: str, value: str, *, ttl_ms: int | None = None) -> None:
        self._cache.set(key, value, ttl_ms=ttl_ms)
        if self._backing is not None:
            self._backing.set(key, value, ttl_ms=ttl_ms)

    def delete(self, key: str) -> bool:
        a = self._cache.delete(key)
        b = self._backing.delete(key) if self._backing is not None else False
        return a or b

    def list(self, prefix: str | None = None) -> list[str]:
        seen = set(self._cache.list(prefix))
        if self._backing is not None:
            seen.update(self._backing.list(prefix))
        return sorted(seen)

    def close(self) -> None:
        self._cache.close()
        if self._backing is not None:
            self._backing.close()


def create_store(
    config: StoreConfig | None = None,
) -> tuple[ContextStore, StoreInfo]:
    """Open a tiered store. Returns (store, info) where info reports probes."""
    cfg = load_config(config)
    attempts: list[ProbeAttempt] = []
    cache = _try_open_cache(cfg, attempts)
    backing = _try_open_backing(cfg, attempts)
    store: ContextStore = TieredStore(cache, backing) if backing else cache
    info = StoreInfo(
        cache=cast(BackendKind, cache.kind),
        backing=cast("BackendKind | None", backing.kind if backing else None),
        attempts=tuple(attempts),
    )
    # Quiet the unused-import warning on `replace` while leaving the import
    # available for callers who manipulate StoreConfig copies.
    _ = replace
    return store, info
