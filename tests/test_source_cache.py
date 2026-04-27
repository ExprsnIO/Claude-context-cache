"""Tests for the source-cache wrapper."""

from __future__ import annotations

import os
import time

import pytest

from ccc.source_cache import (
    close_source_session,
    gather_context_sources_cached,
    get_source_session,
    read_source_cached,
)
from ccc.state import State
from ccc.store import StoreConfig


@pytest.fixture(autouse=True)
def isolated_session():
    close_source_session()
    get_source_session(StoreConfig(sqlite_path=":memory:"))
    yield
    close_source_session()


def test_read_source_cached_miss_then_hit(tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("alpha", encoding="utf-8")

    first = read_source_cached(path)
    assert first.cache_hit is False
    assert first.text == "alpha"

    second = read_source_cached(path)
    assert second.cache_hit is True
    assert second.text == "alpha"


def test_read_source_cached_invalidates_on_mtime_change(tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("alpha", encoding="utf-8")

    first = read_source_cached(path)
    assert first.cache_hit is False

    path.write_text("alpha-and-beta", encoding="utf-8")
    future = time.time() + 5
    os.utime(path, (future, future))

    second = read_source_cached(path)
    assert second.cache_hit is False
    assert second.text == "alpha-and-beta"

    third = read_source_cached(path)
    assert third.cache_hit is True
    assert third.text == "alpha-and-beta"


def test_gather_context_sources_cached_returns_label_text_pairs(tmp_path) -> None:
    a = tmp_path / "a.txt"
    a.write_text("alpha", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_text("beta", encoding="utf-8")

    state = State()
    state.add_context_source(str(a), "labelA", a.stat().st_size)
    state.add_context_source(str(b), "labelB", b.stat().st_size)

    assert gather_context_sources_cached(state) == [
        ("labelA", "alpha"),
        ("labelB", "beta"),
    ]


def test_gather_context_sources_cached_skips_vanished(tmp_path) -> None:
    a = tmp_path / "a.txt"
    a.write_text("alpha", encoding="utf-8")

    state = State()
    state.add_context_source(str(a), "labelA", a.stat().st_size)
    state.add_context_source(str(tmp_path / "missing.txt"), "labelMissing", 0)

    assert gather_context_sources_cached(state) == [("labelA", "alpha")]
