"""
Unit & Integration Tests for Platform Upgrades

Tests:
- Dynamic Agent Registry
- Dynamic Planner & Task DAGs
- Critic & Validation Agent
- Model Router
- Runs Observability API
"""

import pytest
from tripmate.agents.registry import agent_registry
from tripmate.agents.planner import planner
from tripmate.agents.critic import critic_agent
from tripmate.services.model_router import model_router, ModelTier
from tripmate.services.travel_service import travel_service, RUN_STORE
from tripmate.schemas.agents import EvidenceItem, EvidenceType, VerificationStatus


def test_agent_registry():
    agents = agent_registry.list_agents()
    agent_names = {a.name for a in agents}
    assert "flight_agent" in agent_names
    assert "hotel_agent" in agent_names
    assert "weather_agent" in agent_names
    assert "budget_agent" in agent_names
    assert "itinerary_agent" in agent_names


@pytest.mark.asyncio
async def test_dynamic_planner_fallback():
    plan = await planner.create_plan(None, "Plan a 3-day trip to Paris under $1000")
    assert len(plan.tasks) >= 4
    task_agents = {t.agent for t in plan.tasks}
    assert "flight_agent" in task_agents
    assert "hotel_agent" in task_agents


@pytest.mark.asyncio
async def test_critic_agent_fallback():
    report = await critic_agent.evaluate_plan(
        None,
        "Trip query",
        {"destination": "Paris"},
        {"flight_results": "OK"},
        "Draft itinerary",
    )
    assert report.is_valid is True
    assert report.score > 0.5


def test_evidence_item_schema():
    ev = EvidenceItem(
        source_name="OpenWeather",
        source_type=EvidenceType.API,
        status=VerificationStatus.VERIFIED,
        confidence=0.95,
    )
    assert ev.confidence == 0.95
    assert ev.source_type == EvidenceType.API


@pytest.mark.asyncio
async def test_runs_observability_persistence():
    result = await travel_service.execute_travel_plan("Test query to Rome")
    run_id = result.get("run_id")
    assert run_id is not None
    assert run_id in RUN_STORE
    assert RUN_STORE[run_id]["status"] in ["COMPLETED", "WAITING_FOR_APPROVAL", "RUNNING"]


@pytest.mark.asyncio
async def test_redis_hybrid_cache():
    from tripmate.cache.redis_cache import hybrid_cache
    
    async def sample_async_func():
        return {"data": "cached_val"}
    
    res = await hybrid_cache.get_or_set("test_ns", "key_1", sample_async_func)
    assert res == {"data": "cached_val"}
    
    res_cached = await hybrid_cache.get("test_ns", "key_1")
    assert res_cached == {"data": "cached_val"}

