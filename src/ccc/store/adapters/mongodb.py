"""MongoDB adapter (lazy import of `pymongo`)."""

from __future__ import annotations

import re
import time

from ccc.store.config import strip_namespace, with_namespace
from ccc.store.types import ContextStore


def _import_pymongo():
    try:
        import pymongo  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "mongodb backend requested but the 'pymongo' package is not installed. "
            "Run `pip install pymongo` or unset CCC_MONGO_URL."
        ) from exc
    return pymongo


def _escape_regex(s: str) -> str:
    return re.escape(s)


class MongoAdapter(ContextStore):
    kind = "mongodb"

    def __init__(
        self,
        *,
        url: str,
        namespace: str,
        collection: str,
        probe_timeout_ms: int,
    ) -> None:
        pymongo = _import_pymongo()
        self._client = pymongo.MongoClient(
            url, serverSelectionTimeoutMS=probe_timeout_ms
        )
        # Force a server-selection round-trip so probes fail fast.
        self._client.admin.command("ping")
        db = self._client.get_default_database()
        if db is None:
            raise RuntimeError(
                "mongodb URL must include a database, e.g. mongodb://host:27017/dbname"
            )
        self._collection = db[collection]
        self._collection.create_index(
            "expiresAt",
            partialFilterExpression={"expiresAt": {"$type": "long"}},
        )
        self._namespace = namespace

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    def _sweep(self) -> None:
        self._collection.delete_many({"expiresAt": {"$lt": self._now_ms()}})

    def get(self, key: str) -> str | None:
        self._sweep()
        doc = self._collection.find_one({"_id": with_namespace(self._namespace, key)})
        return doc["value"] if doc else None

    def set(self, key: str, value: str, *, ttl_ms: int | None = None) -> None:
        now = self._now_ms()
        expires_at = now + ttl_ms if ttl_ms else None
        self._collection.update_one(
            {"_id": with_namespace(self._namespace, key)},
            {"$set": {"value": value, "expiresAt": expires_at, "updatedAt": now}},
            upsert=True,
        )

    def delete(self, key: str) -> bool:
        result = self._collection.delete_one(
            {"_id": with_namespace(self._namespace, key)}
        )
        return result.deleted_count > 0

    def list(self, prefix: str | None = None) -> list[str]:
        self._sweep()
        match = with_namespace(self._namespace, prefix or "")
        query = (
            {"_id": {"$regex": f"^{_escape_regex(match)}"}}
            if match
            else {}
        )
        return [
            strip_namespace(self._namespace, doc["_id"])
            for doc in self._collection.find(query, {"_id": 1})
        ]

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass


def open_mongo(
    *, url: str, namespace: str, collection: str, probe_timeout_ms: int
) -> MongoAdapter:
    return MongoAdapter(
        url=url,
        namespace=namespace,
        collection=collection,
        probe_timeout_ms=probe_timeout_ms,
    )
