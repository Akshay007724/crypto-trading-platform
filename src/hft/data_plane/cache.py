"""Sync Redis cache for quotes / order-book snapshots (TTL'd).

Streamlit runs sync, so this wraps the sync `redis` client — separate from
`hft.storage.redis_bus.RedisTickBus`, which is the async pub/sub bus used by
the ingestion service. Falls back to an in-process dict if Redis is
unreachable, so the deterministic terminal still works with no Redis running.
"""

from __future__ import annotations

import json
import time

try:
    import redis as redis_sync
except ImportError:  # pragma: no cover - redis-py ships with requirements.txt
    redis_sync = None


class QuoteCache:
    def __init__(self, redis_url: str, ttl_s: int = 5):
        self._ttl = ttl_s
        self._fallback: dict[str, tuple[float, str]] = {}
        self._client = None
        if redis_sync is not None:
            try:
                client = redis_sync.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
                client.ping()
                self._client = client
            except Exception:  # noqa: BLE001 - any connectivity issue -> fallback mode
                self._client = None

    def _key(self, kind: str, symbol: str) -> str:
        return f"cache:{kind}:{symbol}"

    def set(self, kind: str, symbol: str, payload: dict) -> None:
        key = self._key(kind, symbol)
        body = json.dumps(payload)
        if self._client is not None:
            try:
                self._client.setex(key, self._ttl, body)
                return
            except Exception:  # noqa: BLE001 - any connectivity issue -> fallback mode
                self._client = None
        self._fallback[key] = (time.monotonic() + self._ttl, body)

    def get(self, kind: str, symbol: str) -> dict | None:
        key = self._key(kind, symbol)
        if self._client is not None:
            try:
                body = self._client.get(key)
                return json.loads(body) if body else None
            except Exception:  # noqa: BLE001 - any connectivity issue -> fallback mode
                self._client = None
        entry = self._fallback.get(key)
        if entry is None:
            return None
        expires_at, body = entry
        if time.monotonic() > expires_at:
            del self._fallback[key]
            return None
        return json.loads(body)
