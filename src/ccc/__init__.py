"""Cache Claude topic contexts and emit handoff documents."""

__version__ = "0.1.0"

from ccc.source_cache import (
    CachedRead,
    close_source_session,
    gather_context_sources_cached,
    get_source_session,
    read_source_cached,
)
from ccc.store import (
    BackendKind,
    ContextStore,
    ProbeAttempt,
    Session,
    StoreConfig,
    StoreInfo,
    create_store,
    with_session,
)

__all__ = [
    "BackendKind",
    "CachedRead",
    "ContextStore",
    "ProbeAttempt",
    "Session",
    "StoreConfig",
    "StoreInfo",
    "__version__",
    "close_source_session",
    "create_store",
    "gather_context_sources_cached",
    "get_source_session",
    "read_source_cached",
    "with_session",
]
