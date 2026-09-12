"""
Legacy API Endpoint Test Suite

Verifies root metadata, legacy health probes, empty message validation, and approval feedback validation.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app import app
from tripmate.config.settings import settings


@pytest.mark.asyncio
async def test_root_endpoint():
    """Tests GET / root metadata endpoint returning clean JSON."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")
        data = response.json()
        assert data["name"] == settings.APP_NAME
        assert "Multi-Agent AI" in data["description"]
        assert data["version"] == settings.APP_VERSION
        assert data["status"] == "operational"
        assert data["environment"] == settings.APP_ENV
        assert data["api_base"] == "/api/v1"
        assert data["docs"] == "/docs"
        assert data["health"] == "/api/v1/health"
        assert data["status_endpoint"] == "/api/v1/status"




@pytest.mark.asyncio
async def test_health_endpoint():
    """Tests GET /health operational status endpoint."""
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
    """Tests validation error when sending empty message to POST /api/travel."""
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
    """Tests validation error when rejecting an itinerary without feedback."""
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
