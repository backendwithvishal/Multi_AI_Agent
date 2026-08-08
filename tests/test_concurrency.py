import asyncio
import time
# pyrefly: ignore [missing-import]
import pytest
from backend import parallel_specialists_node, TravelState
from backend_cache import AsyncTTLCache


@pytest.mark.asyncio
async def test_async_ttl_cache_operations():
    cache = AsyncTTLCache(default_ttl_seconds=1)
    
    # Test Cache Miss
    val = await cache.get("test", "key1")
    assert val is None
    
    # Test Cache Set & Hit
    await cache.set("test", "key1", {"data": "hello"})
    val = await cache.get("test", "key1")
    assert val == {"data": "hello"}
    
    # Stats Verification
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["cached_entries"] == 1
    
    # TTL Expiration
    await asyncio.sleep(1.1)
    expired_val = await cache.get("test", "key1")
    assert expired_val is None


@pytest.mark.asyncio
async def test_parallel_specialists_execution_mocked():
    state: TravelState = {
        "user_query": "Plan a quick trip to Tokyo",
        "selected_agents": ["flight_agent", "hotel_agent", "weather_agent"],
        "llm_calls": 0,
        "metrics": {"agent_latencies": {}},
    }

    # Execute parallel node
    results = await parallel_specialists_node(state)
    
    assert "flight_results" in results
    assert "hotel_results" in results
    assert "weather_results" in results
    assert "metrics" in results
    assert "parallel_specialists_total" in results["metrics"]["agent_latencies"]
