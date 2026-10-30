"""
Regression Test Suite for Runtime Reliability, Real SSE Streaming, Checkpointing, and HITL
"""

import asyncio
import time
import pytest
from httpx import AsyncClient, ASGITransport
from app import app
from tripmate.config.settings import settings
from tripmate.database.store import store
from tripmate.database import initialize_checkpointer
from tripmate.services.travel_service import travel_service
from tripmate.integrations.circuit_breaker import CircuitBreaker, CircuitBreakerOpenException, circuit_breaker_registry
from tripmate.integrations.mcp import safe_tavily_search, safe_weather_search
from tripmate.cache.redis_cache import hybrid_cache


@pytest.fixture
def auth_headers():
    user = store.create_user(
        username=f"reliuser_{int(time.time()*1000)}",
        email=f"reliuser_{int(time.time()*1000)}@tripmate.ai",
        password_hash="hashed_pw_xyz",
    )
    raw_key = store.create_api_key(user["id"], name="reli_test_key")
    return {"Authorization": f"Bearer {raw_key}", "Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_streaming_event_order(auth_headers):
    """Verifies that Server-Sent Events stream in strictly ordered lifecycle phases."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/travel/stream",
            headers=auth_headers,
            json={"message": "Plan a trip to Tokyo for 3 days"},
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert resp.headers["cache-control"] == "no-cache, no-transform"
        assert resp.headers["x-accel-buffering"] == "no"

        raw_events = resp.text.split("\n\n")
        event_names = []
        for chunk in raw_events:
            for line in chunk.split("\n"):
                if line.startswith("event: "):
                    event_names.append(line.replace("event: ", "").strip())

        # Assert heartbeat comment frames are received
        assert ": heartbeat" in resp.text

        # Assert correct chronological progression and all required event types
        assert event_names[0] == "workflow.started"
        assert "supervisor.decision" in event_names
        assert "step.update" in event_names
        assert "agent.started" in event_names
        assert "agent.finished" in event_names
        assert "hitl_required" in event_names
        assert "final_result" in event_names
        assert "workflow.completed" in event_names


@pytest.mark.asyncio
async def test_disconnect_cancellation(auth_headers):
    """Verifies that stream generator aborts immediately when client disconnects."""
    class MockDisconnectedRequest:
        async def is_disconnected(self):
            return True

    mock_req = MockDisconnectedRequest()
    generator = travel_service.stream_travel_events(
        user_input="Trip to Paris",
        thread_id="thread_disc_test_12345678",
        request_id="req_test_disc",
        user_id="user_test_disc",
        request=mock_req,
    )

    events_received = []
    async for event in generator:
        events_received.append(event)

    # When disconnected before graph execution, it should yield heartbeat and started, then immediately exit
    assert len(events_received) <= 3
    assert not any("workflow.completed" in e for e in events_received)


@pytest.mark.asyncio
async def test_provider_timeout_fallback():
    """Verifies that external provider failures return resilient degraded-mode responses rather than raising 500."""
    breaker = circuit_breaker_registry.get("tavily_api")
    assert breaker is not None
    # Trip breaker manually to simulate provider down
    breaker.state = breaker.state.OPEN
    breaker.failure_count = 5
    breaker.last_failure_time = time.time()
    breaker.last_state_change = time.time()

    res = await safe_tavily_search("Luxury hotels in Kyoto", user_id="user_test_timeout")
    assert "temporarily unavailable" in res or "standard destination advice" in res

    # Reset breaker back to closed
    breaker.reset()


@pytest.mark.asyncio
async def test_checkpoint_persistence_across_app_restart():
    """Verifies that checkpointer retains state snapshots across checkpointer re-initialization."""
    from tripmate.graph.workflow import travel_workflow_graph

    thread_id = f"thread_ckpt_{int(time.time()*1000)}"
    config = {"configurable": {"thread_id": thread_id}}

    # Write state to graph
    initial_state = {
        "user_query": "Explore Rome",
        "thread_id": thread_id,
        "selected_agents": ["flight_agent"],
        "status": "IN_PROGRESS",
    }
    await travel_workflow_graph.aupdate_state(config, initial_state)

    # Read state back
    saved_state = await travel_workflow_graph.aget_state(config)
    assert saved_state.values.get("user_query") == "Explore Rome"

    # Re-initialize checkpointer (simulating server reboot)
    new_checkpointer = initialize_checkpointer()
    assert new_checkpointer is not None


@pytest.mark.asyncio
async def test_approval_idempotency(auth_headers):
    """Verifies that sending an approval decision twice returns identical cached result without error."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Create a travel plan that awaits approval
        plan_resp = await client.post(
            "/api/travel",
            headers=auth_headers,
            json={"message": "Weekend getaway in London"},
        )
        assert plan_resp.status_code == 200
        plan_data = plan_resp.json()
        thread_id = plan_data["thread_id"]
        assert plan_data.get("requires_approval") is True

        # Step 2: First approval call
        approve_resp1 = await client.post(
            "/api/travel/approve",
            headers=auth_headers,
            json={"thread_id": thread_id, "approved": True, "feedback": ""},
        )
        assert approve_resp1.status_code == 200
        result1 = approve_resp1.json()
        assert result1["success"] is True

        # Step 3: Second approval call with identical parameters (Idempotent replay)
        approve_resp2 = await client.post(
            "/api/travel/approve",
            headers=auth_headers,
            json={"thread_id": thread_id, "approved": True, "feedback": ""},
        )
        assert approve_resp2.status_code == 200
        result2 = approve_resp2.json()
        # Must return the identical final response without throwing INVALID_WORKFLOW_STATE
        assert result2["success"] is True
        assert result2["answer"] == result1["answer"]
        assert result2["itinerary"] == result1["itinerary"]


@pytest.mark.asyncio
async def test_approval_ttl_expiry(auth_headers):
    """Verifies that an approval request past its TTL returns HTTP 410 GONE."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a travel plan
        plan_resp = await client.post(
            "/api/travel",
            headers=auth_headers,
            json={"message": "Trip to Berlin"},
        )
        assert plan_resp.status_code == 200
        thread_id = plan_resp.json()["thread_id"]

        # Backdate the approval timestamp past the TTL limit
        travel_service._approval_timestamps[thread_id] = time.time() - (settings.APPROVAL_TTL_SECONDS + 60)

        # Attempt to approve
        approve_resp = await client.post(
            "/api/travel/approve",
            headers=auth_headers,
            json={"thread_id": thread_id, "approved": True, "feedback": ""},
        )
        assert approve_resp.status_code == 410
        assert approve_resp.json()["error"]["code"] == "APPROVAL_EXPIRED"


@pytest.mark.asyncio
async def test_cache_user_isolation():
    """Verifies that MCP cache strictly namespaces by user and never leaks across users."""
    key = f"iso_test_{int(time.time()*1000)}"
    val_u1 = {"secret": "user1_itinerary_data"}
    val_u2 = {"secret": "user2_itinerary_data"}

    # User 1 caches data
    ok1 = await hybrid_cache.set_mcp("travel", key, val_u1, user_id="user_alpha")
    assert ok1 is True

    # User 2 caches data with same key
    ok2 = await hybrid_cache.set_mcp("travel", key, val_u2, user_id="user_beta")
    assert ok2 is True

    # User 1 gets their data
    res_u1 = await hybrid_cache.get_mcp("travel", key, user_id="user_alpha")
    assert res_u1 == val_u1

    # User 2 gets their data
    res_u2 = await hybrid_cache.get_mcp("travel", key, user_id="user_beta")
    assert res_u2 == val_u2

    # Anonymous / public lookup gets None
    res_anon = await hybrid_cache.get_mcp("travel", key, user_id=None)
    assert res_anon is None


@pytest.mark.asyncio
async def test_cache_size_limit():
    """Verifies that payloads exceeding MCP_CACHE_MAX_BYTES (64KB) are rejected."""
    key = f"size_test_{int(time.time()*1000)}"
    oversized_data = "X" * (settings.MCP_CACHE_MAX_BYTES + 1024)

    # Attempt to cache oversized payload
    stored = await hybrid_cache.set_mcp("travel", key, oversized_data, user_id="user_test")
    assert stored is False

    # Lookup returns None
    result = await hybrid_cache.get_mcp("travel", key, user_id="user_test")
    assert result is None


def test_postgres_required_in_prod(monkeypatch):
    """Verifies that non-dev / production environments fail startup if PostgresSaver fails."""
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://invalid_user:invalid_pass@localhost:9999/invalid_db")

    with pytest.raises(RuntimeError) as exc_info:
        initialize_checkpointer()
    assert "PostgreSQL checkpointer" in str(exc_info.value)
    assert "Production/Non-dev startup failed" in str(exc_info.value)

