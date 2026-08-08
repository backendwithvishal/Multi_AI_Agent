import asyncio
# pyrefly: ignore [missing-import]
import pytest
from tripmate.integrations.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException, CircuitState
from tripmate.cache.ttl_cache import BoundedAsyncTTLCache


@pytest.mark.asyncio
async def test_circuit_breaker_state_transitions():
    breaker = CircuitBreaker("test_service", failure_threshold=2, cooldown_seconds=0.5)

    async def failing_func():
        raise RuntimeError("Downstream API timeout")

    # Call 1: Failure
    with pytest.raises(RuntimeError):
        await breaker.call(failing_func)
    assert breaker.state == CircuitState.CLOSED

    # Call 2: Failure -> Transitions to OPEN
    with pytest.raises(RuntimeError):
        await breaker.call(failing_func)
    assert breaker.state == CircuitState.OPEN

    # Call 3: Rejected immediately due to OPEN state
    with pytest.raises(CircuitBreakerOpenException):
        await breaker.call(failing_func)

    # Wait for cooldown
    await asyncio.sleep(0.6)

    # Call 4: Transitions to HALF_OPEN, then succeeds
    async def succeeding_func():
        return "success"

    res = await breaker.call(succeeding_func)
    assert res == "success"
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_bounded_ttl_cache_eviction():
    cache = BoundedAsyncTTLCache(default_ttl_seconds=3600, max_entries=2)
    await cache.set("ns", "k1", "v1")
    await cache.set("ns", "k2", "v2")
    await cache.set("ns", "k3", "v3")

    stats = cache.get_stats()
    assert stats["cached_entries"] <= 2
