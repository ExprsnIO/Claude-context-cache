"""Tests for create_store fallback ordering."""

from __future__ import annotations

from ccc.store import StoreConfig, create_store


def test_factory_falls_back_to_sqlite_memory_when_no_redis() -> None:
    cfg = StoreConfig(redis_url=None, sqlite_path=":memory:")
    store, info = create_store(cfg)
    try:
        assert store.kind == "sqlite-memory"
        assert info.cache == "sqlite-memory"
        assert info.backing is None
    finally:
        store.close()


def test_factory_falls_back_to_sqlite_disk_when_memory_disabled(tmp_path) -> None:
    cfg = StoreConfig(
        sqlite_path=str(tmp_path / "store.sqlite"),
        disable_sqlite_memory=True,
    )
    store, info = create_store(cfg)
    try:
        assert store.kind == "sqlite-disk"
        assert info.cache == "sqlite-disk"
        store.set("k", "v")
        assert store.get("k") == "v"
    finally:
        store.close()


def test_factory_records_failed_redis_probe() -> None:
    # Port 1 is reserved/closed; the redis adapter will fail fast.
    cfg = StoreConfig(redis_url="redis://127.0.0.1:1", probe_timeout_ms=200)
    store, info = create_store(cfg)
    try:
        assert store.kind == "sqlite-memory"
        redis_attempts = [a for a in info.attempts if a.kind == "redis"]
        assert redis_attempts, "redis attempt should be recorded"
        assert redis_attempts[0].ok is False
    finally:
        store.close()
