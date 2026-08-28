"""Agent output cache keyed by (intent, symbol, data_version) — controls LLM
cost by not re-running an agent for the same question against the same
underlying data. `data_version` is caller-supplied (e.g. latest quote ts
rounded to the cache TTL) so a cache hit is only ever served for genuinely
unchanged data."""

from __future__ import annotations

import time


class AgentOutputCache:
    def __init__(self, ttl_s: int = 60):
        self._ttl = ttl_s
        self._store: dict[tuple, tuple[float, dict]] = {}

    def _key(self, intent: str, symbol: str, data_version: str) -> tuple:
        return (intent, symbol, data_version)

    def get(self, intent: str, symbol: str, data_version: str) -> dict | None:
        entry = self._store.get(self._key(intent, symbol, data_version))
        if entry is None:
            return None
        expires_at, payload = entry
        if time.monotonic() > expires_at:
            del self._store[self._key(intent, symbol, data_version)]
            return None
        return payload

    def set(self, intent: str, symbol: str, data_version: str, payload: dict) -> None:
        self._store[self._key(intent, symbol, data_version)] = (time.monotonic() + self._ttl, payload)
