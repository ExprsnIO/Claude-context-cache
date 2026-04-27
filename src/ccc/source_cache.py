"""Cache the read content of `state.context_sources` between calls.

Mirrors the Node `npm/src/source-cache.ts` module: cache key is a
SHA-256 content hash of the file (or of the sorted relative-path +
content-hash pairs for a directory). Hashing the bytes — not mtime
or size — means edits that produce identical content do not invalidate
the cache, and edits that change content invalidate even when the
filesystem mtime is unchanged (touch, restored backups, editors that
preserve mtime, sub-second mtime granularity).
"""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path

from ccc.state import State
from ccc.store.config import StoreConfig
from ccc.store.session import Session

SOURCE_NAMESPACE = "ccc-py-sources"
_HASH_CHUNK = 64 * 1024

_lock = threading.Lock()
_session: Session | None = None


def get_source_session(config: StoreConfig | None = None) -> Session:
    """Return a process-wide Session used for source caching."""
    global _session
    with _lock:
        if _session is None:
            cfg = StoreConfig() if config is None else config
            cfg.namespace = cfg.namespace or SOURCE_NAMESPACE
            _session = Session(cfg)
        return _session


def close_source_session() -> None:
    """Close and clear the shared source-cache Session."""
    global _session
    with _lock:
        session = _session
        _session = None
    if session is not None:
        session.close()


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(path: Path) -> str:
    if not path.is_dir():
        return f"f:{_hash_file(path)}"
    parts: list[str] = []
    for child in sorted(path.rglob("*")):
        if any(p.startswith(".") for p in child.relative_to(path).parts):
            continue
        if not child.is_file():
            continue
        try:
            digest = _hash_file(child)
        except OSError:
            continue
        rel = child.relative_to(path)
        parts.append(f"{rel}:{digest}")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"d:{digest}"


def _read_source_text(path: Path) -> str:
    if not path.is_dir():
        return path.read_text(encoding="utf-8")
    chunks: list[str] = []
    for child in sorted(path.rglob("*")):
        if not child.is_file():
            continue
        if any(p.startswith(".") for p in child.relative_to(path).parts):
            continue
        try:
            text = child.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = child.relative_to(path)
        chunks.append(f"--- {rel} ---\n{text}")
    return "\n\n".join(chunks)


@dataclass(frozen=True)
class CachedRead:
    text: str
    cache_hit: bool


def read_source_cached(path: Path) -> CachedRead:
    """Return the cached text for a source path, populating on miss."""
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        key = f"{path}:{_fingerprint(path)}"
    except OSError:
        return CachedRead(text=_read_source_text(path), cache_hit=False)
    session = get_source_session()
    try:
        cached = session.get(key)
        if cached is not None:
            return CachedRead(text=cached, cache_hit=True)
        text = _read_source_text(path)
        session.set(key, text)
        return CachedRead(text=text, cache_hit=False)
    except Exception:
        # Store failures must never break the API call — read directly.
        return CachedRead(text=_read_source_text(path), cache_hit=False)


def gather_context_sources_cached(state: State) -> list[tuple[str, str]]:
    """Read every cached source through the store; skip vanished/unreadable."""
    sources: list[tuple[str, str]] = []
    for src in state.context_sources:
        path = Path(src.path)
        if not path.exists():
            continue
        try:
            sources.append((src.label, read_source_cached(path).text))
        except OSError:
            continue
    return sources
