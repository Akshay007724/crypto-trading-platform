"""Token-bucket rate limiter + per-source circuit breaker.

Deterministic, no I/O — one instance per upstream API (Kraken, Finnhub),
shared across every tool call that hits that source.
"""

from __future__ import annotations

import time


class RateLimitExceeded(Exception):
    pass


class CircuitOpenError(Exception):
    pass


class TokenBucket:
    def __init__(self, rate_per_s: float, capacity: int, clock=time.monotonic):
        self._rate = rate_per_s
        self._capacity = capacity
        self._tokens = float(capacity)
        self._clock = clock
        self._last = clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)

    def try_acquire(self, n: int = 1) -> bool:
        self._refill()
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False

    def acquire(self, n: int = 1) -> None:
        if not self.try_acquire(n):
            raise RateLimitExceeded


class CircuitBreaker:
    """Opens after `failure_threshold` consecutive failures; half-opens for
    one trial call after `reset_after_s`."""

    def __init__(self, failure_threshold: int = 5, reset_after_s: float = 30.0, clock=time.monotonic):
        self._threshold = failure_threshold
        self._reset_after = reset_after_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        return self._clock() - self._opened_at < self._reset_after

    def before_call(self) -> None:
        if self.is_open:
            raise CircuitOpenError

    def on_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._threshold:
            self._opened_at = self._clock()


class RateGovernor:
    """Bundles a TokenBucket + CircuitBreaker per named source."""

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

    def register(self, source: str, rate_per_s: float, capacity: int, failure_threshold: int = 5, reset_after_s: float = 30.0) -> None:
        self._buckets[source] = TokenBucket(rate_per_s, capacity)
        self._breakers[source] = CircuitBreaker(failure_threshold, reset_after_s)

    def guard(self, source: str) -> None:
        self._breakers[source].before_call()
        self._buckets[source].acquire()

    def record_success(self, source: str) -> None:
        self._breakers[source].on_success()

    def record_failure(self, source: str) -> None:
        self._breakers[source].on_failure()


def call_with_backoff(fn, *, retries: int = 3, base_delay_s: float = 0.5, sleep=time.sleep):
    """Plain exponential backoff, no new dependency."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - deliberately broad, re-raised after retries
            last_exc = exc
            if attempt < retries - 1:
                sleep(base_delay_s * (2**attempt))
    assert last_exc is not None
    raise last_exc
