# pyrefly: ignore [missing-import]
import pytest
from httpx import AsyncClient, ASGITransport
from app import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "supervisor_agent" in data["features"]


@pytest.mark.asyncio
async def test_travel_endpoint_empty_message():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/travel", json={"message": "   "})
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Message cannot be empty."


@pytest.mark.asyncio
async def test_approve_endpoint_missing_feedback():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/travel/approve",
            json={"thread_id": "test_thread_123", "approved": False, "feedback": ""},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "feedback" in data["error"]
