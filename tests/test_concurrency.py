import asyncio
import time
from unittest.mock import AsyncMock, patch
import pytest
from tripmate.graph.workflow import parallel_specialists_node
from tripmate.graph.state import TravelState
from tripmate.cache.ttl_cache import BoundedAsyncTTLCache as AsyncTTLCache
from tripmate.schemas.agents import StructuredAgentOutput, VerificationStatus


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
    
    # TTL Expiration via simulated time advance (avoids flaky wall-clock sleep)
    future_time = time.time() + 2.0
    with patch("time.time", return_value=future_time):
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

    dummy_flight = StructuredAgentOutput(
        agent_name="flight_agent",
        status="success",
        result={"flights": [{"price": 850}]},
    )
    dummy_hotel = StructuredAgentOutput(
        agent_name="hotel_agent",
        status="success",
        result={"hotels": [{"price": 120}]},
    )
    dummy_weather = StructuredAgentOutput(
        agent_name="weather_agent",
        status="success",
        result={"temp": 22},
    )

    with patch("tripmate.graph.workflow._run_agent_with_events") as mock_run:
        async def side_effect(agent_name, agent_obj, llm, query, context=None):
            if agent_name == "flight_agent":
                return dummy_flight
            elif agent_name == "hotel_agent":
                return dummy_hotel
            elif agent_name == "weather_agent":
                return dummy_weather
            return StructuredAgentOutput(agent_name=agent_name, summary="ok")
        mock_run.side_effect = side_effect

        results = await parallel_specialists_node(state)
        
        assert "flight_results" in results
        assert "hotel_results" in results
        assert "weather_results" in results
        assert "metrics" in results
        assert "parallel_specialists_total" in results["metrics"]["agent_latencies"]
        assert "flights" in results["flight_results"]
