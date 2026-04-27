"""Public types for the tiered context store."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

BackendKind = Literal[
    "redis",
    "sqlite-memory",
    "sqlite-disk",
    "mysql",
    "postgres",
    "mongodb",
]


class ContextStore(ABC):
    """Sync key-value store interface, mirrored across every backend."""

    kind: BackendKind

    @abstractmethod
    def get(self, key: str) -> str | None: ...

    @abstractmethod
    def set(self, key: str, value: str, *, ttl_ms: int | None = None) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> bool: ...

    @abstractmethod
    def list(self, prefix: str | None = None) -> list[str]: ...

    @abstractmethod
    def close(self) -> None: ...


@dataclass(frozen=True)
class ProbeAttempt:
    kind: BackendKind
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class StoreInfo:
    cache: BackendKind
    backing: BackendKind | None
    attempts: tuple[ProbeAttempt, ...]
