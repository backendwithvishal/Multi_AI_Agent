# pyrefly: ignore [missing-import]
import pytest
from httpx import AsyncClient, ASGITransport
from app import app


@pytest.mark.asyncio
async def test_v1_health_endpoints():
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/travel", json={"message": "   "})
        assert resp.status_code == 422 or resp.status_code == 400


@pytest.mark.asyncio
async def test_v1_approve_missing_feedback():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/travel/approve",
            json={"thread_id": "test_t100", "approved": False, "feedback": ""},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "VALIDATION_ERROR"
