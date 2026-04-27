"""Tests for the Session lifecycle wrapper."""

from __future__ import annotations

import time

from ccc.store import Session, StoreConfig, with_session


def test_session_lazily_opens_on_first_call() -> None:
    session = Session(
        StoreConfig(sqlite_path=":memory:"),
        idle_timeout_seconds=0,
        install_atexit=False,
    )
    try:
        session.set("hello", "world")
        assert session.get("hello") == "world"
        assert session.kind == "sqlite-memory"
    finally:
        session.close()


def test_session_idle_timeout_closes_underlying_store() -> None:
    session = Session(
        StoreConfig(sqlite_path=":memory:"),
        idle_timeout_seconds=0.05,
        install_atexit=False,
    )
    try:
        session.set("k", "v")
        time.sleep(0.15)
        # After idle close, accessing again opens a fresh in-memory store.
        assert session.get("k") is None
    finally:
        session.close()


def test_with_session_scopes_lifecycle() -> None:
    captured = {}

    def body(s: Session) -> str | None:
        s.set("ping", "pong")
        captured["kind"] = s.kind
        return s.get("ping")

    result = with_session(body, StoreConfig(sqlite_path=":memory:"))
    assert result == "pong"
    assert captured["kind"] == "sqlite-memory"
