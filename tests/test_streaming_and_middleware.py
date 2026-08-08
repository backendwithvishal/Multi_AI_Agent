"""
Streaming & Correlation Middleware Test Suite

Tests request correlation ID generation (`X-Request-ID`), custom ID preservation, and SSE streaming validation.
"""

# pyrefly: ignore [missing-import]
import pytest
from httpx import AsyncClient, ASGITransport
from app import app


@pytest.mark.asyncio
async def test_request_id_middleware():
    """Tests automatic X-Request-ID header generation."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"].startswith("req_")


@pytest.mark.asyncio
async def test_custom_request_id_preserved():
    """Tests preservation of caller-supplied custom X-Request-ID header."""
    custom_id = "req_custom_test_12345"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == custom_id


@pytest.mark.asyncio
async def test_sse_streaming_endpoint_empty_message():
    """Tests validation error when sending empty prompt to SSE stream endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/travel/stream", json={"message": "   "})
        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Message cannot be empty."
