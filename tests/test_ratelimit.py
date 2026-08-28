from hft.data_plane.ratelimit import CircuitBreaker, CircuitOpenError, RateGovernor, TokenBucket, call_with_backoff


def test_token_bucket_denies_when_empty():
    bucket = TokenBucket(rate_per_s=1.0, capacity=1, clock=lambda: 0.0)

    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False


def test_token_bucket_refills_over_time():
    t = {"now": 0.0}
    bucket = TokenBucket(rate_per_s=1.0, capacity=1, clock=lambda: t["now"])

    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False
    t["now"] = 1.0
    assert bucket.try_acquire() is True


def test_circuit_breaker_opens_after_threshold_failures():
    breaker = CircuitBreaker(failure_threshold=2, reset_after_s=100.0)
    breaker.on_failure()
    assert breaker.is_open is False
    breaker.on_failure()
    assert breaker.is_open is True


def test_circuit_breaker_half_opens_after_reset_window():
    t = {"now": 0.0}
    breaker = CircuitBreaker(failure_threshold=1, reset_after_s=10.0, clock=lambda: t["now"])
    breaker.on_failure()
    assert breaker.is_open is True
    t["now"] = 11.0
    assert breaker.is_open is False


def test_rate_governor_guard_raises_when_circuit_open():
    governor = RateGovernor()
    governor.register("test", rate_per_s=1.0, capacity=1, failure_threshold=1, reset_after_s=100.0)
    governor.record_failure("test")
    try:
        governor.guard("test")
        assert False, "expected CircuitOpenError"
    except CircuitOpenError:
        pass


def test_call_with_backoff_retries_then_succeeds():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError("boom")
        return "ok"

    result = call_with_backoff(flaky, retries=3, base_delay_s=0.0, sleep=lambda _: None)
    assert result == "ok"
    assert attempts["n"] == 3
