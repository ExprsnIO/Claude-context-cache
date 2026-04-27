"""Env-driven config for the tiered context store."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_SQLITE_PATH = ".ccc-cache/store.sqlite"
DEFAULT_TABLE_NAME = "ccc_context"
DEFAULT_PROBE_TIMEOUT_MS = 1500


@dataclass
class StoreConfig:
    redis_url: str | None = None
    sqlite_path: str = DEFAULT_SQLITE_PATH
    disable_redis: bool = False
    disable_sqlite_memory: bool = False
    mysql_url: str | None = None
    postgres_url: str | None = None
    mongo_url: str | None = None
    table_name: str = DEFAULT_TABLE_NAME
    namespace: str = ""
    probe_timeout_ms: int = DEFAULT_PROBE_TIMEOUT_MS


def load_config(overrides: StoreConfig | None = None) -> StoreConfig:
    """Build a config from env vars, overlaying any explicit overrides."""
    env = os.environ
    cfg = StoreConfig()
    cfg.redis_url = env.get("CCC_REDIS_URL") or env.get("REDIS_URL")
    cfg.sqlite_path = env.get("CCC_SQLITE_PATH", DEFAULT_SQLITE_PATH)
    cfg.disable_redis = env.get("CCC_DISABLE_REDIS") == "1"
    cfg.disable_sqlite_memory = env.get("CCC_DISABLE_SQLITE_MEMORY") == "1"
    cfg.mysql_url = env.get("CCC_MYSQL_URL")
    cfg.postgres_url = env.get("CCC_POSTGRES_URL")
    cfg.mongo_url = env.get("CCC_MONGO_URL")
    cfg.table_name = env.get("CCC_TABLE_NAME", DEFAULT_TABLE_NAME)
    cfg.namespace = env.get("CCC_NAMESPACE", "")
    raw_timeout = env.get("CCC_PROBE_TIMEOUT_MS")
    if raw_timeout:
        try:
            cfg.probe_timeout_ms = int(raw_timeout)
        except ValueError:
            cfg.probe_timeout_ms = DEFAULT_PROBE_TIMEOUT_MS

    if overrides is not None:
        # Manual override merge: any non-default field on `overrides` wins.
        defaults = StoreConfig()
        for field_name in StoreConfig.__dataclass_fields__:
            override_val = getattr(overrides, field_name)
            if override_val != getattr(defaults, field_name):
                setattr(cfg, field_name, override_val)
    return cfg


def with_namespace(namespace: str, key: str) -> str:
    return f"{namespace}:{key}" if namespace else key


def strip_namespace(namespace: str, key: str) -> str:
    if not namespace:
        return key
    prefix = f"{namespace}:"
    return key[len(prefix):] if key.startswith(prefix) else key
