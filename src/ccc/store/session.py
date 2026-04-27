"""Session manager: lazy open, idle teardown, atexit cleanup."""

from __future__ import annotations

import atexit
import threading
from typing import Callable, TypeVar

from ccc.store.config import StoreConfig
from ccc.store.factory import create_store
from ccc.store.types import ContextStore, StoreInfo

T = TypeVar("T")

DEFAULT_IDLE_SECONDS = 5 * 60


class Session(ContextStore):
    """Lifecycle wrapper: opens on first use, closes on idle / process exit."""

    def __init__(
        self,
        config: StoreConfig | None = None,
        *,
        idle_timeout_seconds: float | None = DEFAULT_IDLE_SECONDS,
        install_atexit: bool = True,
    ) -> None:
        self._config = config
        self._idle = idle_timeout_seconds
        self._lock = threading.RLock()
        self._store: ContextStore | None = None
        self._info: StoreInfo | None = None
        self._timer: threading.Timer | None = None
        self._atexit_installed = False
        self._install_atexit = install_atexit
        # Default kind is reported as sqlite-memory until an open happens.
        self.kind = "sqlite-memory"

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        self._ensure_open()

    def info(self) -> StoreInfo:
        self._ensure_open()
        assert self._info is not None
        return self._info

    def close(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            store = self._store
            self._store = None
            self._info = None
            if store is not None:
                store.close()

    def __enter__(self) -> "Session":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- KV API -------------------------------------------------------------

    def get(self, key: str) -> str | None:
        with self._lock:
            store = self._ensure_open()
            self._touch()
            return store.get(key)

    def set(self, key: str, value: str, *, ttl_ms: int | None = None) -> None:
        with self._lock:
            store = self._ensure_open()
            self._touch()
            store.set(key, value, ttl_ms=ttl_ms)

    def delete(self, key: str) -> bool:
        with self._lock:
            store = self._ensure_open()
            self._touch()
            return store.delete(key)

    def list(self, prefix: str | None = None) -> list[str]:
        with self._lock:
            store = self._ensure_open()
            self._touch()
            return store.list(prefix)

    # -- internals ----------------------------------------------------------

    def _ensure_open(self) -> ContextStore:
        with self._lock:
            if self._store is not None:
                return self._store
            store, info = create_store(self._config)
            self._store = store
            self._info = info
            self.kind = store.kind
            if self._install_atexit and not self._atexit_installed:
                atexit.register(self.close)
                self._atexit_installed = True
            return store

    def _touch(self) -> None:
        if self._idle is None or self._idle <= 0:
            return
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            timer = threading.Timer(self._idle, self.close)
            timer.daemon = True
            timer.start()
            self._timer = timer


def with_session(
    fn: Callable[[Session], T],
    config: StoreConfig | None = None,
) -> T:
    """Open a session, run `fn`, close it — for one-shot scripts."""
    session = Session(config, install_atexit=False)
    try:
        return fn(session)
    finally:
        session.close()
