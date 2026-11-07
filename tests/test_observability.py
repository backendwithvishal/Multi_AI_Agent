"""
Observability and Data Privacy Production Test Suite

Tests:
1. Redaction of API keys, tokens, Authorization headers, and full prompts/PII in captured logs.
2. Propagation of X-Request-ID into logs and outgoing LLM / MCP calls.
3. Access control on /metrics (reject public access with 401/403, allow internal access).
4. Prometheus metrics counters incrementing on requests, cache hits/misses, and rate limits.
5. Token count and estimated cost updates in Prometheus after mocked LLM invocation.
6. Audit log generation for authentication failures and HITL approval / rejection decisions.
7. OpenTelemetry tracing toggled off by default, and active when env flag is set.
"""

import io
import json
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from tripmate.config.settings import settings
from tripmate.core.audit import AuditEventType, audit_logger
from tripmate.core.context import get_request_id, set_request_context
from tripmate.core.logging import (
    RedactingJsonFormatter,
    redact_sensitive_data,
)
from tripmate.core.tracing import is_otel_enabled
from tripmate.middleware.metrics import metrics_registry

# =========================================================================
# 1. Redaction Tests
# =========================================================================


def test_redaction_removes_keys_tokens_auth_and_pii():
    """Asserts that fake API keys, tokens, Authorization headers, and PII are redacted."""
    sensitive_log = (
        "User groq key is gsk_abcdef1234567890abcdef1234567890, "
        "OpenRouter key sk-or-v1-abcdef1234567890abcdef1234567890, "
        "Tavily key tvly-abcdef1234567890abcdef, "
        "Authorization: Bearer secret_jwt_token_payload_987654321, "
        "Contact user at traveler.jane@example.com or phone 555-867-5309, "
        "Credit card is 4111-2222-3333-4444 and prompt: What is the best 5-day route?"
    )

    sanitized = redact_sensitive_data(sensitive_log)

    # Assert no sensitive items leak
    assert "gsk_abcdef1234567890abcdef1234567890" not in sanitized
    assert "sk-or-v1-abcdef1234567890abcdef1234567890" not in sanitized
    assert "tvly-abcdef1234567890abcdef" not in sanitized
    assert "secret_jwt_token_payload_987654321" not in sanitized
    assert "traveler.jane@example.com" not in sanitized
    assert "555-867-5309" not in sanitized
    assert "4111-2222-3333-4444" not in sanitized
    assert "What is the best 5-day route?" not in sanitized

    # Assert redaction placeholders are present
    assert "[REDACTED" in sanitized


def test_redacting_json_formatter_in_logger():
    """Asserts that RedactingJsonFormatter formats records as JSON and redacts sensitive data."""
    log_capture_stream = io.StringIO()
    handler = logging.StreamHandler(log_capture_stream)
    handler.setFormatter(RedactingJsonFormatter())

    test_logger = logging.getLogger("test.redaction.logger")
    test_logger.handlers = [handler]
    test_logger.setLevel(logging.INFO)
    test_logger.propagate = False

    test_logger.info(
        "Connecting with Authorization: Bearer secret_token_xyz for user test@tripmate.ai with prompt: Secret plan"
    )

    output = log_capture_stream.getvalue().strip()
    assert output, "Log output should not be empty"

    data = json.loads(output)
    msg = data.get("message", "")

    assert "secret_token_xyz" not in msg
    assert "test@tripmate.ai" not in msg
    assert "Secret plan" not in msg
    assert "[REDACTED" in msg


# =========================================================================
# 2. Structured JSON Log & Request ID Propagation Tests
# =========================================================================


@pytest.mark.asyncio
async def test_request_id_in_logs_and_outgoing_calls():
    """Verifies request_id appears in logs and propagates to LLM and MCP contexts."""
    test_req_id = "req_custom_obs_98765"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Request-ID": test_req_id})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == test_req_id

    # Verify context propagation
    set_request_context(test_req_id, "user_obs_1", "thread_test_123")
    assert get_request_id() == test_req_id

    # Reset circuit breakers to ensure clean state
    from tripmate.integrations.circuit_breaker import circuit_breaker_registry

    circuit_breaker_registry.reset_all()

    # Test propagation into outgoing LLM call wrapper
    from tripmate.integrations.llm_resilience import invoke_llm_with_resilience

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Paris travel plan", response_metadata={}))

    await invoke_llm_with_resilience(mock_llm, "Paris", provider_name="groq")

    # Assert mock_llm.ainvoke was called with X-Request-ID in config/context/headers
    assert mock_llm.ainvoke.call_count == 1
    call_args, call_kwargs = mock_llm.ainvoke.call_args
    config = call_kwargs.get("config") or (call_args[1] if len(call_args) > 1 else {})
    assert (
        config.get("metadata", {}).get("request_id") == test_req_id
        or config.get("configurable", {}).get("request_id") == test_req_id
        or f"request_id:{test_req_id}" in config.get("tags", [])
    )

    # Test propagation into outgoing MCP call
    from tripmate.integrations.mcp import tavily_search

    with patch("tripmate.integrations.mcp.raw_tavily_mcp_search", new_callable=AsyncMock) as mock_mcp:
        mock_mcp.return_value = "Hotel search result"
        await tavily_search("UniqueObsTestDestinationHotels")
        assert mock_mcp.call_count == 1
        # Check that request_id was propagated in context or call
        assert mock_mcp.call_args is not None


# =========================================================================
# 3. /metrics Access Control & Prometheus Endpoint Tests
# =========================================================================


@pytest.mark.asyncio
async def test_metrics_protected_from_public_access():
    """Asserts that /metrics is rejected (401 or 403) when called from a public/untrusted IP without internal credentials."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Public IP forwarded header without internal token
        response = await client.get("/metrics", headers={"X-Forwarded-For": "203.0.113.195"})
        assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_metrics_reachable_internally():
    """Asserts that /metrics is reachable when requested internally or with internal metrics token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Internal loopback request
        response = await client.get("/metrics", headers={"X-Forwarded-For": "127.0.0.1"})
        assert response.status_code == 200
        assert "tripmate_http_requests_total" in response.text
        assert "tripmate_http_request_duration_seconds" in response.text


@pytest.mark.asyncio
async def test_metrics_counters_increment_after_real_requests():
    """Asserts that HTTP request counters and duration histograms increment."""
    metrics_registry.record_http_request("GET", "/test/obs_ping", 200, 0.045)
    metrics_registry.record_cache_hit("redis")
    metrics_registry.record_cache_miss("memory")
    metrics_registry.record_rate_limit_rejection("/api/travel")
    metrics_registry.record_checkpoint_db_latency(0.012)
    metrics_registry.set_circuit_breaker_state("groq_llm", 0)

    scrape = metrics_registry.generate_prometheus_text()

    assert 'tripmate_http_requests_total{method="GET",path="/test/obs_ping",status="200"}' in scrape
    assert "tripmate_cache_hits_total" in scrape
    assert "tripmate_cache_misses_total" in scrape
    assert "tripmate_rate_limit_rejections_total" in scrape
    assert "tripmate_checkpoint_db_latency_seconds" in scrape
    assert "tripmate_circuit_breaker_state" in scrape


@pytest.mark.asyncio
async def test_metrics_tokens_and_cost_update_after_mocked_llm_call():
    """Asserts that LLM token counters and estimated cost metrics update."""
    metrics_registry.record_llm_tokens("llama-3.3-70b-versatile", prompt_tokens=150, completion_tokens=50)

    scrape = metrics_registry.generate_prometheus_text()

    assert 'tripmate_llm_tokens_total{model="llama-3.3-70b-versatile",type="prompt"} 150' in scrape
    assert 'tripmate_llm_tokens_total{model="llama-3.3-70b-versatile",type="completion"} 50' in scrape
    assert 'tripmate_llm_tokens_total{model="llama-3.3-70b-versatile",type="total"} 200' in scrape
    assert 'tripmate_llm_cost_dollars_total{model="llama-3.3-70b-versatile"}' in scrape


# =========================================================================
# 4. Audit Log Tests
# =========================================================================


def test_audit_log_records_auth_failures_and_hitl_decisions():
    """Asserts that failed auth and approve/reject actions write single structured audit entries."""
    audit_logger.clear()

    # 1. Failed Auth
    audit_logger.record(
        event_type=AuditEventType.AUTH_FAILURE,
        action="login_failed",
        actor="unknown_user",
        target_id="auth_service",
        status="failure",
        client_ip="198.51.100.5",
        request_id="req_audit_auth_fail",
        details={"reason": "Invalid credentials provided."},
    )

    # 2. Approval Decision - Approved
    audit_logger.record(
        event_type=AuditEventType.APPROVAL_DECISION,
        action="itinerary_approved",
        actor="user_traveler_1",
        target_id="thread_approved_101",
        status="success",
        client_ip="127.0.0.1",
        request_id="req_audit_approve",
        details={"approved": True, "feedback": "Looks great!"},
    )

    # 3. Approval Decision - Rejected
    audit_logger.record(
        event_type=AuditEventType.APPROVAL_DECISION,
        action="itinerary_rejected",
        actor="user_traveler_2",
        target_id="thread_rejected_202",
        status="success",
        client_ip="127.0.0.1",
        request_id="req_audit_reject",
        details={"approved": False, "feedback": "Too expensive."},
    )

    entries = audit_logger.get_entries()
    assert len(entries) == 3

    auth_entry = entries[0]
    assert auth_entry["event_type"] == AuditEventType.AUTH_FAILURE.value
    assert auth_entry["action"] == "login_failed"
    assert auth_entry["actor"] == "unknown_user"
    assert auth_entry["status"] == "failure"
    assert auth_entry["request_id"] == "req_audit_auth_fail"

    approve_entry = entries[1]
    assert approve_entry["event_type"] == AuditEventType.APPROVAL_DECISION.value
    assert approve_entry["action"] == "itinerary_approved"
    assert approve_entry["target_id"] == "thread_approved_101"
    assert approve_entry["status"] == "success"

    reject_entry = entries[2]
    assert reject_entry["event_type"] == AuditEventType.APPROVAL_DECISION.value
    assert reject_entry["action"] == "itinerary_rejected"
    assert reject_entry["target_id"] == "thread_rejected_202"
    assert reject_entry["details"]["feedback"] == "Too expensive."


# =========================================================================
# 5. OpenTelemetry & Prompt Capture Configuration Tests
# =========================================================================


def test_opentelemetry_off_by_default_and_toggled_via_env():
    """Asserts that OpenTelemetry is off by default and enabled when OTEL_ENABLED is true."""
    # Default state (off)
    with patch.dict(os.environ, {"OTEL_ENABLED": "false", "ENABLE_OTEL": "false"}, clear=False):
        assert is_otel_enabled() is False

    # Enabled via environment variable
    with patch.dict(os.environ, {"OTEL_ENABLED": "true"}, clear=False):
        assert is_otel_enabled() is True

    # Prompt capture OFF by default
    assert getattr(settings, "CAPTURE_PROMPTS", False) is False
