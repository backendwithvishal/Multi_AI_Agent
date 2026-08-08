"""
Security & Input Guardrail Test Suite

Tests prompt injection rejection ('drop table') and security headers enforcement ('nosniff', 'DENY', 'XSS-Protection').
"""

# pyrefly: ignore [missing-import]
import pytest
from httpx import AsyncClient, ASGITransport
from app import app
from tripmate.agents.guardrail import deterministic_input_check


def test_deterministic_guardrail_checks():
    """Tests input guardrail blocking disallowed SQL injection attack pattern."""
    is_valid, reason = deterministic_input_check("Please drop table users;")
    assert is_valid is False
    assert "drop table" in reason

    is_valid_clean, _ = deterministic_input_check("Plan a 5 day trip to Rome")
    assert is_valid_clean is True


@pytest.mark.asyncio
async def test_security_headers_present():
    """Tests presence of security headers on HTTP response."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["X-XSS-Protection"] == "1; mode=block"
