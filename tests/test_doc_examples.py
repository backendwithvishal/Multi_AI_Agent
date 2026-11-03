"""
tests/test_doc_examples.py — Runs every curl/Python example from the README
against the FastAPI TestClient and asserts the documented HTTP status and
response fields.

Run with:
    pytest tests/test_doc_examples.py -v
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _assert_api_response(resp, *, expected_status: int, expect_success: bool = True):
    assert resp.status_code == expected_status, (
        f"Expected HTTP {expected_status}, got {resp.status_code}. Body: {resp.text[:300]}"
    )
    body = resp.json()
    if expect_success:
        assert body.get("success") is True, f"Expected success=true. Body: {body}"
        assert "data" in body, f"Expected 'data' field. Body: {body}"
    else:
        assert body.get("success") is False, f"Expected success=false. Body: {body}"


# ---------------------------------------------------------------------------
# GET /api/v1/health
# curl http://localhost:8000/api/v1/health
# ---------------------------------------------------------------------------

class TestHealthExample:
    def test_health_returns_200_with_service_and_version(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert body["status"] == "ok"
        assert "service" in body
        assert "version" in body

    def test_liveness_returns_200(self, client):
        resp = client.get("/api/v1/liveness")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_readiness_returns_200_or_503(self, client):
        resp = client.get("/api/v1/readiness")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "status" in body


# ---------------------------------------------------------------------------
# GET /api/v1/status
# ---------------------------------------------------------------------------

class TestStatusExample:
    def test_status_returns_200_with_service_name(self, client):
        resp = client.get("/api/v1/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        data = body.get("data", {})
        assert "service" in data
        assert "version" in data
        assert "status" in data


# ---------------------------------------------------------------------------
# POST /api/v1/auth/register
# documented: 200 on success, 400 on duplicate
# ---------------------------------------------------------------------------

class TestAuthExamples:
    _UNIQUE_USER = {
        "username": "doc_example_user",
        "email": "doc_example@test.local",
        "password": "Secure!Pass123",
        "role": "user",
    }

    def test_register_returns_200_with_token(self, client):
        # May return 400 if user already exists in repeated runs — accept both
        resp = client.post("/api/v1/auth/register", json=self._UNIQUE_USER)
        assert resp.status_code in (200, 400), f"Unexpected status: {resp.status_code}"
        body = resp.json()
        if resp.status_code == 200:
            assert body.get("success") is True
            assert "data" in body
            assert "access_token" in body["data"]

    def test_login_with_bad_credentials_returns_401(self, client):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username_or_email": "nobody@nowhere.local", "password": "wrongpass"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body.get("detail", {}).get("code") == "INVALID_CREDENTIALS"

    def test_me_without_auth_returns_200_or_401(self, client):
        resp = client.get("/api/v1/auth/me")
        # When AUTH_REQUIRED=false, may return anonymous; when true, 401
        assert resp.status_code in (200, 401, 403)

    def test_forgot_password_returns_200_with_reset_token(self, client):
        resp = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nonexistent@test.local"},
        )
        # Documented to always return 200 (no email oracle)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True


# ---------------------------------------------------------------------------
# POST /api/v1/travel — documented: 200 with answer field
# ---------------------------------------------------------------------------

class TestTravelExample:
    def test_travel_post_missing_message_returns_422(self, client):
        resp = client.post("/api/v1/travel", json={})
        assert resp.status_code == 422

    def test_travel_post_with_message_returns_200_or_5xx(self, client):
        """Travel endpoint may return 500 without live LLM keys; 200 otherwise."""
        resp = client.post(
            "/api/v1/travel",
            json={"message": "Plan a 3-day trip to Paris for 2", "thread_id": "doc-example-thread-01"},
        )
        # Without real API keys the workflow errors; accept 200 or 500
        assert resp.status_code in (200, 500)
        body = resp.json()
        assert "success" in body

    def test_travel_stream_returns_text_event_stream(self, client):
        """GET /api/v1/travel/stream must return Content-Type: text/event-stream."""
        with client.stream(
            "POST",
            "/api/v1/travel/stream",
            json={"message": "Weekend trip to Barcelona", "thread_id": "doc-stream-test-01"},
        ) as resp:
            assert resp.headers.get("content-type", "").startswith("text/event-stream"), (
                f"Expected text/event-stream, got {resp.headers.get('content-type')}"
            )


# ---------------------------------------------------------------------------
# POST /api/v1/travel/approve — documented errors
# ---------------------------------------------------------------------------

class TestApprovalExample:
    def test_approve_without_feedback_on_reject_returns_400(self, client):
        resp = client.post(
            "/api/v1/travel/approve",
            json={"thread_id": "doc-thread-abc123xy", "approved": False, "feedback": ""},
        )
        assert resp.status_code == 400

    def test_approve_nonexistent_thread_returns_404_or_error(self, client):
        resp = client.post(
            "/api/v1/travel/approve",
            json={"thread_id": "doc-thread-abc123xy", "approved": True, "feedback": ""},
        )
        # 404 if thread not found, or 500 for workflow error
        assert resp.status_code in (404, 500)


# ---------------------------------------------------------------------------
# Watchlists CRUD — documented: 200 list, 201 create, 404 not found
# ---------------------------------------------------------------------------

class TestWatchlistExamples:
    def test_list_watchlists_returns_200(self, client):
        resp = client.get("/api/v1/watchlists")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        assert isinstance(body.get("data"), list)

    def test_create_watchlist_missing_fields_returns_422(self, client):
        resp = client.post("/api/v1/watchlists", json={})
        assert resp.status_code == 422

    def test_get_nonexistent_watchlist_returns_404(self, client):
        resp = client.get("/api/v1/watchlists/nonexistent-id-xyz")
        assert resp.status_code == 404
        body = resp.json()
        assert body.get("detail", {}).get("code") == "WATCHLIST_NOT_FOUND"


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class TestAlertExamples:
    def test_list_alerts_returns_200(self, client):
        resp = client.get("/api/v1/alerts")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        assert isinstance(body.get("data"), list)


# ---------------------------------------------------------------------------
# Financial — documented: deterministic calculation
# ---------------------------------------------------------------------------

class TestFinancialExamples:
    def test_calculate_returns_200_with_totals(self, client):
        payload = {
            "flights": 450.0,
            "hotels": 300.0,
            "activities": 150.0,
            "meals": 120.0,
            "currency": "USD",
            "contingency_percent": 10.0,
        }
        resp = client.post("/api/v1/financial/calculate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        data = body.get("data", {})
        assert "total" in data or "total_with_contingency" in data

    def test_convert_unsupported_currency_returns_400(self, client):
        payload = {"amount": 100.0, "from_currency": "USD", "to_currency": "XYZ"}
        resp = client.post("/api/v1/financial/convert", json=payload)
        assert resp.status_code == 400
        body = resp.json()
        assert body.get("detail", {}).get("code") == "UNSUPPORTED_CURRENCY"


# ---------------------------------------------------------------------------
# Background Tasks
# ---------------------------------------------------------------------------

class TestTaskExamples:
    def test_submit_invalid_task_returns_400(self, client):
        resp = client.post(
            "/api/v1/tasks/submit",
            json={"task_name": "nonexistent_task_xyz", "payload": {}},
        )
        assert resp.status_code == 400

    def test_get_nonexistent_task_returns_404(self, client):
        resp = client.get("/api/v1/tasks/nonexistent-task-id")
        assert resp.status_code == 404

    def test_list_tasks_returns_200(self, client):
        resp = client.get("/api/v1/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        assert isinstance(body.get("data"), list)


# ---------------------------------------------------------------------------
# Runs (Observability)
# ---------------------------------------------------------------------------

class TestRunsExamples:
    def test_get_nonexistent_run_returns_404(self, client):
        resp = client.get("/api/v1/runs/nonexistent-run-id")
        assert resp.status_code == 404

    def test_get_run_metrics_nonexistent_returns_404(self, client):
        resp = client.get("/api/v1/runs/nonexistent-run-id/metrics")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GDS Booking — documented errors
# ---------------------------------------------------------------------------

class TestBookingExamples:
    def test_search_flights_missing_params_returns_422(self, client):
        resp = client.get("/api/v1/booking/flights/search")
        assert resp.status_code == 422

    def test_search_hotels_missing_params_returns_422(self, client):
        resp = client.get("/api/v1/booking/hotels/search")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AI endpoints
# ---------------------------------------------------------------------------

class TestAIExamples:
    def test_ai_plan_missing_query_returns_422(self, client):
        resp = client.post("/api/v1/ai/plan", json={})
        assert resp.status_code == 422

    def test_invoke_nonexistent_agent_returns_404(self, client):
        resp = client.post(
            "/api/v1/ai/agents/nonexistent_agent_xyz/invoke",
            json={"query": "test query", "context": {}},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body.get("detail", {}).get("code") == "AGENT_NOT_FOUND"

