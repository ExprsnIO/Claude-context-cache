"""Tests for the SQLite adapter (memory + disk)."""

from __future__ import annotations

import time

from ccc.store.adapters.sqlite import open_sqlite


def test_sqlite_memory_set_get_delete_round_trip() -> None:
    store = open_sqlite(path=":memory:", namespace="", kind="sqlite-memory")
    try:
        store.set("foo", "bar")
        assert store.get("foo") == "bar"
        assert store.delete("foo") is True
        assert store.get("foo") is None
    finally:
        store.close()


def test_sqlite_memory_list_with_prefix_and_namespace() -> None:
    store = open_sqlite(path=":memory:", namespace="ns", kind="sqlite-memory")
    try:
        store.set("a/1", "x")
        store.set("a/2", "y")
        store.set("b/1", "z")
        assert sorted(store.list("a/")) == ["a/1", "a/2"]
        assert sorted(store.list()) == ["a/1", "a/2", "b/1"]
    finally:
        store.close()


def test_sqlite_memory_ttl_expires_entries() -> None:
    store = open_sqlite(path=":memory:", namespace="", kind="sqlite-memory")
    try:
        store.set("temp", "soon", ttl_ms=30)
        assert store.get("temp") == "soon"
        time.sleep(0.05)
        assert store.get("temp") is None
    finally:
        store.close()


def test_sqlite_disk_persists_across_reopens(tmp_path) -> None:
    path = str(tmp_path / "store.sqlite")
    a = open_sqlite(path=path, namespace="", kind="sqlite-disk")
    a.set("durable", "yes")
    a.close()
    b = open_sqlite(path=path, namespace="", kind="sqlite-disk")
    try:
        assert b.get("durable") == "yes"
    finally:
        b.close()
