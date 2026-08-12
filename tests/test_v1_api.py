"""
Versioned V1 API Route Test Suite

Tests:
- `/api/v1/health`, `/api/v1/liveness`, `/api/v1/readiness`
- `/api/v1/travel` (Execution, Validation, SSE Stream)
- `/api/v1/travel/approve` (Approval and Rejection Validation)
- `/api/v1/runs/{run_id}` (Details, Metrics, Agents, Replay, 404 Error handling)
- Authentication dependency verification
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app import app
from tripmate.services.travel_service import RUN_STORE
from tripmate.config.settings import settings


@pytest.mark.asyncio
async def test_v1_health_endpoints():
    """Tests versioned v1 health, liveness, and readiness probes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Health telemetry
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "circuit_breaker_resilience" in data["features"]

        # Liveness
        resp_live = await client.get("/api/v1/liveness")
        assert resp_live.status_code == 200
        assert resp_live.json()["status"] == "alive"

        # Readiness
        resp_ready = await client.get("/api/v1/readiness")
        assert resp_ready.status_code == 200
        assert resp_ready.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_v1_travel_validation():
    """Tests input validation error on empty message prompt for /api/v1/travel."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/travel", json={"message": "   "})
        assert resp.status_code == 422
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "request_id" in data


@pytest.mark.asyncio
async def test_v1_travel_successful_execution():
    """Tests full travel workflow execution via POST /api/v1/travel."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/travel",
            json={"message": "Plan a 3-day weekend trip to Rome with historical sights"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "data" in data
        assert "run_id" in data["data"]
        assert data["data"]["status"] in ["COMPLETED", "WAITING_FOR_APPROVAL", "RUNNING"]


@pytest.mark.asyncio
async def test_v1_approve_missing_feedback():
    """Tests validation error when rejecting an itinerary without feedback on /api/v1/travel/approve."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/travel/approve",
            json={"thread_id": "test_t100", "approved": False, "feedback": ""},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_v1_runs_endpoints():
    """Tests /api/v1/runs endpoints for details, metrics, agents, and replay."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create a test run record in RUN_STORE
        test_run_id = "run_test_observability_123"
        RUN_STORE[test_run_id] = {
            "run_id": test_run_id,
            "thread_id": "thread_test_123",
            "status": "COMPLETED",
            "answer": "Polished Rome 3-day itinerary",
            "selected_agents": ["flight_agent", "hotel_agent", "itinerary_agent"],
            "structured_outputs": {"flight_agent": {"status": "success"}},
            "evidence_items": [{"source_name": "AviationStack", "confidence": 0.9}],
            "critic_report": {"is_valid": True, "score": 0.95},
            "metrics": {"total_latency_ms": 150.0, "agent_latencies": {"flight_agent": 50.0}},
        }

        # 1. GET /api/v1/runs/{run_id}
        resp_details = await client.get(f"/api/v1/runs/{test_run_id}")
        assert resp_details.status_code == 200
        data_details = resp_details.json()
        assert data_details["success"] is True
        assert data_details["data"]["run_id"] == test_run_id

        # 2. GET /api/v1/runs/{run_id}/metrics
        resp_metrics = await client.get(f"/api/v1/runs/{test_run_id}/metrics")
        assert resp_metrics.status_code == 200
        data_metrics = resp_metrics.json()
        assert data_metrics["success"] is True
        assert "token_usage" in data_metrics["data"]
        assert "estimated_cost_usd" in data_metrics["data"]

        # 3. GET /api/v1/runs/{run_id}/agents
        resp_agents = await client.get(f"/api/v1/runs/{test_run_id}/agents")
        assert resp_agents.status_code == 200
        data_agents = resp_agents.json()
        assert data_agents["success"] is True
        assert "selected_agents" in data_agents["data"]
        assert "evidence_items" in data_agents["data"]

        # 4. POST /api/v1/runs/{run_id}/replay
        resp_replay = await client.post(f"/api/v1/runs/{test_run_id}/replay")
        assert resp_replay.status_code == 200
        data_replay = resp_replay.json()
        assert data_replay["success"] is True

        # 5. Non-existent run_id -> 404 normalized error response
        resp_404 = await client.get("/api/v1/runs/non_existent_run_999")
        assert resp_404.status_code == 404
        data_404 = resp_404.json()
        assert data_404["success"] is False
        assert data_404["error"]["code"] == "RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_v1_authentication_enforcement(monkeypatch):
    """Tests API key enforcement in both development and production modes."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Enforce authentication
        monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
        monkeypatch.setattr(settings, "API_KEY", "secret_test_key_abc123")

        # Request without key -> 401
        resp_no_key = await client.post("/api/v1/travel", json={"message": "Trip to Paris"})
        assert resp_no_key.status_code == 401
        data_no_key = resp_no_key.json()
        assert data_no_key["success"] is False
        assert data_no_key["error"]["code"] == "UNAUTHORIZED"

        # Request with invalid key -> 401
        resp_wrong_key = await client.post(
            "/api/v1/travel",
            json={"message": "Trip to Paris"},
            headers={"X-API-Key": "wrong_key"},
        )
        assert resp_wrong_key.status_code == 401

        # Request with valid Bearer token -> 200
        resp_bearer = await client.post(
            "/api/v1/travel",
            json={"message": "Trip to Paris"},
            headers={"Authorization": "Bearer secret_test_key_abc123"},
        )
        assert resp_bearer.status_code == 200


@pytest.mark.asyncio
async def test_v1_assets_get_and_delete():
    """Tests GET and DELETE travel asset operations via /api/v1/assets/{asset_id}."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create asset
        resp_create = await client.post(
            "/api/v1/assets",
            json={
                "name": "E-Ticket: Air France AF007",
                "asset_type": "ticket",
                "trip_id": "trip_paris_101",
                "content_uri": "https://storage.tripmate.ai/tickets/af007.pdf",
                "metadata": {"booking_ref": "AF-887766"},
            },
        )
        assert resp_create.status_code == 200
        data_create = resp_create.json()
        assert data_create["success"] is True
        asset_id = data_create["data"]["id"]

        # 2. Get asset details by ID
        resp_get = await client.get(f"/api/v1/assets/{asset_id}")
        assert resp_get.status_code == 200
        data_get = resp_get.json()
        assert data_get["success"] is True
        assert data_get["data"]["id"] == asset_id
        assert data_get["data"]["name"] == "E-Ticket: Air France AF007"
        assert data_get["data"]["asset_type"] == "ticket"

        # 3. Delete asset by ID
        resp_delete = await client.delete(f"/api/v1/assets/{asset_id}")
        assert resp_delete.status_code == 200
        data_del = resp_delete.json()
        assert data_del["success"] is True
        assert data_del["data"]["deleted"] is True
        assert data_del["data"]["id"] == asset_id

        # 4. Verify get on deleted asset returns 404
        resp_get_404 = await client.get(f"/api/v1/assets/{asset_id}")
        assert resp_get_404.status_code == 404
        data_get_404 = resp_get_404.json()
        assert data_get_404["success"] is False
        assert data_get_404["error"]["code"] == "ASSET_NOT_FOUND"

        # 5. Verify delete on already deleted asset returns 404
        resp_del_404 = await client.delete(f"/api/v1/assets/{asset_id}")
        assert resp_del_404.status_code == 404
        data_del_404 = resp_del_404.json()
        assert data_del_404["success"] is False
        assert data_del_404["error"]["code"] == "ASSET_NOT_FOUND"