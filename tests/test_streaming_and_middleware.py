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


@pytest.mark.asyncio
async def test_rate_limiter_proxy_ip_handling():
    """Tests that rate limiter correctly respects X-Forwarded-For and X-Real-IP headers."""
    from tripmate.middleware import SlidingWindowRateLimiter
    from fastapi import FastAPI
    from starlette.requests import Request
    from starlette.responses import Response

    test_app = FastAPI()
    limiter = SlidingWindowRateLimiter(test_app, max_requests=2, window_seconds=10, protected_prefixes=("/api/",))

    # Simulate Request with X-Forwarded-For
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "headers": [(b"x-forwarded-for", b"203.0.113.195, 70.41.3.18")],
    }
    req = Request(scope)
    extracted_ip = limiter._get_client_ip(req)
    assert extracted_ip == "203.0.113.195"

    # Simulate Request with X-Real-IP
    scope_real = {
        "type": "http",
        "method": "GET",
        "path": "/api/test",
        "headers": [(b"x-real-ip", b"198.51.100.4")],
    }
    req_real = Request(scope_real)
    assert limiter._get_client_ip(req_real) == "198.51.100.4"

