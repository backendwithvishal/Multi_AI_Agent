"""
Failing Proof-of-Concept Tests for Security Review: Reliability, Limits & Middleware Gaps
Author: External Security Reviewer

These tests assert correct defensive reliability, quota enforcement, and error handling.
They fail against the current unpatched implementation.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app import app
from tripmate.config.settings import settings
from tripmate.database.store import generate_token
from tripmate.core.audit import audit_logger, AuditEventType


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)


@pytest.mark.asyncio
async def test_token_budget_per_user_enforced():
    """
    VULNERABILITY: DAILY_TOKEN_BUDGET_PER_USER is configured in settings but never enforced.
    File: tripmate/config/settings.py:182
    Expected: Once user reaches daily token budget, subsequent LLM requests return 429 DAILY_TOKEN_BUDGET_EXCEEDED.
    Current: No token accounting is checked; unlimited tokens can be consumed.
    """
    token = generate_token("user_budget_test_01", "budget_user", role="user")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Simulate high token consumption by user
        from tripmate.services.observability import calculate_cost
        # In a hardened system, a quota tracker tracks user consumption
        # Here we test that making calls beyond budget is stopped
        res = await client.post(
            "/api/v1/travel",
            json={"message": "Plan a full luxury trip to Paris and Rome with flights, 5 star hotels and fine dining"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Verify if any token budget header or quota response is present
        # In the unpatched code, no token quota checking exists whatsoever
        assert "X-TokenBudget-Remaining" in res.headers or res.status_code == 429, (
            "Expected token budget accounting headers or enforcement on travel requests"
        )


@pytest.mark.asyncio
async def test_security_headers_present_on_rate_limit_429_responses():
    """
    VULNERABILITY: SecurityHeadersMiddleware is added first (innermost), so short-circuited
    responses from SlidingWindowRateLimiter (429) lack security headers.
    File: app.py:141, tripmate/middleware/__init__.py:341
    Expected: 429 response contains X-Content-Type-Options: nosniff and Content-Security-Policy.
    Current: Rate limiter returns JSONResponse directly before SecurityHeadersMiddleware runs.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger rate limit
        res = None
        for _ in range(settings.RATE_LIMIT_REQUESTS + 5):
            res = await client.get("/api/v1/health")
            if res.status_code == 429:
                break

        assert res is not None and res.status_code == 429, f"Failed to trigger 429 rate limit: got {res.status_code if res else 'None'}"
        assert "X-Content-Type-Options" in res.headers, (
            "Missing X-Content-Type-Options header on 429 response"
        )
        assert "Content-Security-Policy" in res.headers, (
            "Missing Content-Security-Policy header on 429 response"
        )


@pytest.mark.asyncio
async def test_audit_logger_not_marking_failed_approvals_as_success():
    """
    VULNERABILITY: POST /api/v1/travel/approve records status='success' in audit log BEFORE
    resuming the workflow.
    File: tripmate/api/v1/routes/approval.py:44-53
    Expected: If thread does not exist (404), audit log records failure or does not log premature success.
    Current: Audit log permanently records success even when resume_travel_plan fails with 404.
    """
    token = generate_token("user_audit_test", "auditor", role="user")
    non_existent_thread = "thread_does_not_exist_999"

    audit_records = []
    original_record = audit_logger.record

    def capture_record(*args, **kwargs):
        audit_records.append(kwargs)
        return original_record(*args, **kwargs)

    audit_logger.record = capture_record
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/api/v1/travel/approve",
                json={"thread_id": non_existent_thread, "approved": True},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert res.status_code == 404

            # Verify that audit log does NOT contain a "success" record for this failed action
            successful_approval_records = [
                r for r in audit_records
                if r.get("event_type") == AuditEventType.APPROVAL_DECISION
                and r.get("target_id") == non_existent_thread
                and r.get("status") == "success"
            ]
            assert len(successful_approval_records) == 0, (
                "Audit log erroneously recorded status='success' for an approval that failed with 404"
            )
    finally:
        audit_logger.record = original_record


@pytest.mark.asyncio
async def test_readiness_probe_graceful_when_redis_fails_and_memory_fallback_active(monkeypatch):
    """
    VULNERABILITY: GET /health/ready returns 503 when Redis is unavailable, even though
    the system has a fully functional in-memory fallback.
    File: app.py:481-506
    Expected: If in-memory fallback is active and healthy, readiness probe should remain operational (200 OK)
    or report degraded readiness instead of hard 503 pod failure.
    Current: Hard 503 returned whenever redis ping fails.
    """
    from tripmate.cache.redis_cache import hybrid_cache

    async def mock_failed_ping():
        return False

    monkeypatch.setattr(hybrid_cache, "ping", mock_failed_ping)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health/ready")
        assert res.status_code == 200, (
            f"Expected 200 with degraded state when fallback cache is operational, got {res.status_code}"
        )
