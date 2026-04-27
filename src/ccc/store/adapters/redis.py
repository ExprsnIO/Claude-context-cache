"""Redis adapter (lazy import of the `redis` package)."""

from __future__ import annotations

from ccc.store.config import strip_namespace, with_namespace
from ccc.store.types import ContextStore


def _import_redis():
    try:
        import redis  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "redis backend requested but the 'redis' package is not installed. "
            "Run `pip install redis` or unset CCC_REDIS_URL."
        ) from exc
    return redis


class RedisAdapter(ContextStore):
    kind = "redis"

    def __init__(self, *, url: str, namespace: str, probe_timeout_ms: int) -> None:
        redis = _import_redis()
        timeout_s = max(probe_timeout_ms / 1000, 0.1)
        self._client = redis.Redis.from_url(
            url,
            socket_connect_timeout=timeout_s,
            socket_timeout=timeout_s,
            decode_responses=True,
        )
        self._client.ping()
        self._namespace = namespace

    def get(self, key: str) -> str | None:
        return self._client.get(with_namespace(self._namespace, key))

    def set(self, key: str, value: str, *, ttl_ms: int | None = None) -> None:
        self._client.set(
            with_namespace(self._namespace, key),
            value,
            px=ttl_ms,
        )

    def delete(self, key: str) -> bool:
        return self._client.delete(with_namespace(self._namespace, key)) > 0

    def list(self, prefix: str | None = None) -> list[str]:
        match = with_namespace(self._namespace, f"{prefix or ''}*")
        return [
            strip_namespace(self._namespace, k)
            for k in self._client.scan_iter(match=match)
        ]

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


def open_redis(*, url: str, namespace: str, probe_timeout_ms: int) -> RedisAdapter:
    return RedisAdapter(url=url, namespace=namespace, probe_timeout_ms=probe_timeout_ms)
