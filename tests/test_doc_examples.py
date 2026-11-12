"""
tests/test_doc_examples.py — Doc-example verification suite.

Runs documented curl/Python payload examples from README.md against endpoint handlers
and asserts the exact documented status codes, payloads, and response fields.

Covers:
- GET /api/v1/health
- GET /api/v1/liveness
- GET /api/v1/readiness
- GET /api/v1/status
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- GET /api/v1/auth/me
- POST /api/v1/auth/forgot-password
- POST /api/v1/travel
- POST /api/v1/travel/approve
- GET /api/v1/watchlists
- POST /api/v1/watchlists
- GET /api/v1/watchlists/{id}
- GET /api/v1/alerts
- POST /api/v1/financial/calculate
- POST /api/v1/financial/convert
- POST /api/v1/tasks/submit
- GET /api/v1/tasks/{id}
- GET /api/v1/tasks
- GET /api/v1/runs/{id}
- GET /api/v1/runs/{id}/metrics
- POST /api/v1/ai/agents/{name}/invoke

Run with:
    pytest tests/test_doc_examples.py -v
"""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from tripmate.config.settings import settings
from tripmate.database.store import store
from tripmate.schemas import (
    AIAgentInvokeRequest,
    ApprovalRequest,
    CurrencyConversionRequest,
    FinancialCalculationRequest,
    ForgotPasswordRequest,
    TravelRequest,
    UserLoginRequest,
    UserRegisterRequest,
    WatchlistCreateRequest,
)

# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------


def _run(coro_or_val):
    """Executes a coroutine safely without creating a Windows socket-based event loop."""
    if not inspect.iscoroutine(coro_or_val):
        return coro_or_val
    stack = [coro_or_val]
    val = None
    exc = None
    while stack:
        curr = stack[-1]
        try:
            if exc is not None:
                to_raise = exc
                exc = None
                res = curr.throw(to_raise)
            else:
                res = curr.send(val)
            val = None
            if inspect.iscoroutine(res):
                stack.append(res)
            else:
                val = res
        except StopIteration as stop:
            stack.pop()
            val = stop.value
            exc = None
        except Exception as e:
            stack.pop()
            if not stack:
                raise
            exc = e
            val = None
    return val


def _mock_request(path: str = "/api/v1/test", method: str = "GET") -> Request:
    req = MagicMock(spec=Request)
    req.method = method
    req.url = MagicMock()
    req.url.path = path
    req.state = MagicMock()
    req.state.request_id = "req_doc_example_123"
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    req.headers = {}
    return req


@pytest.fixture(autouse=True)
def direct_to_thread(monkeypatch):
    """Executes asyncio.to_thread callables immediately in the test thread."""

    async def _direct(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", _direct)


# ---------------------------------------------------------------------------
# 1. Health & Status Telemetry Examples
# ---------------------------------------------------------------------------


class TestHealthDocExamples:
    def test_health_telemetry_documented_fields(self):
        """Documented GET /api/v1/health returns status ok, service, version, and telemetry blocks."""
        from tripmate.api.v1.routes.health import health_telemetry

        req = _mock_request("/api/v1/health")
        res = _run(health_telemetry(req))
        assert res["status"] == "ok"
        assert res["service"] == settings.APP_NAME
        assert res["version"] == settings.APP_VERSION
        assert "features" in res
        assert "database" in res
        assert "cache_stats" in res
        assert "task_queue" in res
        assert "circuit_breakers" in res

    def test_liveness_documented_fields(self):
        """Documented GET /api/v1/liveness returns status alive and service."""
        from tripmate.api.v1.routes.health import liveness_probe

        res = _run(liveness_probe())
        assert res["status"] == "alive"
        assert res["service"] == settings.APP_NAME

    def test_readiness_probe_documented_fields(self):
        """Documented GET /api/v1/readiness returns status ready or not_ready."""
        from tripmate.api.v1.routes.health import readiness_probe

        resp = Response()
        res = _run(readiness_probe(resp))
        assert res["status"] in ("ready", "not_ready")
        assert "database" in res

    def test_status_telemetry_documented_fields(self):
        """Documented GET /api/v1/status returns APIResponse envelope with OPERATIONAL status."""
        from tripmate.api.v1.routes.status import get_system_status

        req = _mock_request("/api/v1/status")
        res = _run(get_system_status(req))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True
        assert body["data"]["status"] == "OPERATIONAL"
        assert body["data"]["service"] == settings.APP_NAME
        assert body["data"]["version"] == settings.APP_VERSION


# ---------------------------------------------------------------------------
# 2. Authentication Examples
# ---------------------------------------------------------------------------


class TestAuthDocExamples:
    def test_register_documented_example(self):
        """Documented POST /api/v1/auth/register creates user and returns JWT token."""
        from tripmate.api.v1.routes.auth import register

        req = _mock_request("/api/v1/auth/register", "POST")
        payload = UserRegisterRequest(
            username="doc_example_user_01",
            email="doc_example_01@example.com",
            password="StrongPassword123!",
            role="user",
        )
        try:
            res = _run(register(payload, req))
            body = res.model_dump() if hasattr(res, "model_dump") else res
            assert body["success"] is True
            assert "access_token" in body["data"]
            assert body["data"]["token_type"] == "bearer"
        except HTTPException as exc:
            # Idempotent across repeated test runs
            assert exc.status_code == 400

    def test_login_invalid_credentials_documented_error(self):
        """Documented POST /api/v1/auth/login invalid credentials returns 401."""
        from tripmate.api.v1.routes.auth import login

        req = _mock_request("/api/v1/auth/login", "POST")
        payload = UserLoginRequest(
            username_or_email="nonexistent_user_999",
            password="wrong_password",
        )
        with pytest.raises(HTTPException) as excinfo:
            _run(login(payload, req))
        assert excinfo.value.status_code == 401
        detail = excinfo.value.detail
        assert isinstance(detail, dict)
        assert detail.get("code") == "INVALID_CREDENTIALS"

    def test_auth_me_documented_example(self):
        """Documented GET /api/v1/auth/me returns authenticated user identity."""
        from tripmate.api.v1.routes.auth import get_me
        from tripmate.database.store import hash_password

        # Ensure user exists in store for profile retrieval
        created = store.create_user(
            username="doc_user_me",
            email="doc_user_me@example.com",
            password_hash=hash_password("Pass123!"),
            role="user",
        )
        req = _mock_request("/api/v1/auth/me")
        res = _run(get_me(req, current_user=created))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True
        assert body["data"]["username"] == "doc_user_me"

    def test_forgot_password_documented_flow(self):
        """Documented POST /api/v1/auth/forgot-password returns 200 with receipt message."""
        from tripmate.api.v1.routes.auth import forgot_password

        req = _mock_request("/api/v1/auth/forgot-password", "POST")
        payload = ForgotPasswordRequest(email="someone@example.com")
        res = _run(forgot_password(payload, req))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True
        assert "message" in body["data"]


# ---------------------------------------------------------------------------
# 3. Travel Workflows & Human-in-the-Loop Approval
# ---------------------------------------------------------------------------


class TestTravelDocExamples:
    def test_travel_execution_documented_response(self, monkeypatch):
        """Documented POST /api/v1/travel returns run_id, thread_id, status, and answer."""
        from tripmate.api.v1.routes.travel import create_travel_plan
        from tripmate.services.travel_service import travel_service

        async def fake_execute(user_input, thread_id, user_id=None):
            return {
                "run_id": "run_doc_001",
                "thread_id": thread_id,
                "status": "COMPLETED",
                "answer": "Documented 3-day Paris itinerary.",
            }

        monkeypatch.setattr(travel_service, "execute_travel_plan", fake_execute)

        req = _mock_request("/api/v1/travel", "POST")
        payload = TravelRequest(
            message="Plan a 3-day trip to Paris for 2",
            thread_id="travel_thread_12345",
        )
        res = _run(create_travel_plan(payload, req, current_user={"id": "doc_user"}))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True
        assert body["data"]["run_id"] == "run_doc_001"
        assert body["data"]["status"] == "COMPLETED"

    def test_approve_rejection_without_feedback_returns_400(self):
        """Documented POST /api/v1/travel/approve requires feedback when approved=false."""
        from tripmate.api.v1.routes.approval import approve_travel_plan

        req = _mock_request("/api/v1/travel/approve", "POST")
        payload = ApprovalRequest(
            thread_id="thread_doc_test",
            approved=False,
            feedback="",
        )
        res = _run(approve_travel_plan(payload, req, current_user={"id": "doc_user"}))
        assert isinstance(res, JSONResponse)
        assert res.status_code == 400

    def test_approve_success_documented_flow(self, monkeypatch):
        """Documented POST /api/v1/travel/approve resumes workflow upon approval."""
        from tripmate.api.v1.routes.approval import approve_travel_plan
        from tripmate.services.travel_service import travel_service

        async def fake_resume(thread_id, approved, feedback="", user_id=None):
            return {
                "run_id": "run_doc_001",
                "thread_id": thread_id,
                "status": "COMPLETED",
                "approved": approved,
            }

        monkeypatch.setattr(travel_service, "resume_travel_plan", fake_resume)

        req = _mock_request("/api/v1/travel/approve", "POST")
        payload = ApprovalRequest(
            thread_id="thread_doc_test",
            approved=True,
            feedback="Looks great, approve it!",
        )
        res = _run(approve_travel_plan(payload, req, current_user={"id": "doc_user"}))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True


# ---------------------------------------------------------------------------
# 4. Watchlists & Alerts Examples
# ---------------------------------------------------------------------------


class TestWatchlistDocExamples:
    def test_list_watchlists_documented_response(self):
        """Documented GET /api/v1/watchlists returns array of watchlist items."""
        from tripmate.api.v1.routes.watchlists import list_watchlists

        req = _mock_request("/api/v1/watchlists")
        res = _run(list_watchlists(req, current_user={"id": "doc_user"}))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True
        assert isinstance(body["data"], list)

    def test_create_and_get_watchlist_documented_flow(self):
        """Documented POST and GET /api/v1/watchlists creates and reads watchlist."""
        from tripmate.api.v1.routes.watchlists import create_watchlist, get_watchlist

        req = _mock_request("/api/v1/watchlists", "POST")
        payload = WatchlistCreateRequest(
            title="Tokyo Cherry Blossom Flights",
            target_type="flight",
            target_value="JFK-HND",
            threshold_price=850.0,
            notes="Spring travel alert",
        )
        created = _run(create_watchlist(payload, req, current_user={"id": "doc_user_wl"}))
        body_created = created.model_dump() if hasattr(created, "model_dump") else created
        assert body_created["success"] is True
        item_id = body_created["data"]["id"]

        get_res = _run(get_watchlist(item_id, req, current_user={"id": "doc_user_wl"}))
        body_get = get_res.model_dump() if hasattr(get_res, "model_dump") else get_res
        assert body_get["success"] is True
        assert body_get["data"]["id"] == item_id
        assert body_get["data"]["threshold_price"] == 850.0

    def test_get_nonexistent_watchlist_returns_404(self):
        """Documented GET /api/v1/watchlists/{id} missing item returns 404."""
        from tripmate.api.v1.routes.watchlists import get_watchlist

        req = _mock_request("/api/v1/watchlists/nonexistent-id")
        with pytest.raises(HTTPException) as excinfo:
            _run(get_watchlist("nonexistent-id", req, current_user={"id": "doc_user"}))
        assert excinfo.value.status_code == 404

    def test_list_alerts_documented_response(self):
        """Documented GET /api/v1/alerts returns notification list."""
        from tripmate.api.v1.routes.alerts import list_alerts

        req = _mock_request("/api/v1/alerts")
        res = _run(list_alerts(req, current_user={"id": "doc_user"}))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True
        assert isinstance(body["data"], list)


# ---------------------------------------------------------------------------
# 5. Financial Calculation Examples
# ---------------------------------------------------------------------------


class TestFinancialDocExamples:
    def test_financial_calculate_documented_formula(self):
        """Documented POST /api/v1/financial/calculate calculates itemized trip totals."""
        from tripmate.api.v1.routes.financial import calculate_finances

        req = _mock_request("/api/v1/financial/calculate", "POST")
        payload = FinancialCalculationRequest(
            flight_estimate=450.0,
            hotel_nightly_rate=150.0,
            nights=2,
            daily_food_allowance=60.0,
            activities_budget=150.0,
            tax_rate_pct=10.0,
            contingency_buffer_pct=10.0,
            currency="USD",
        )
        res = _run(calculate_finances(payload, req, current_user={"id": "doc_user"}))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True
        data = body["data"]
        # Subtotal = 450 + 300 + 120 + 150 = 1020.0
        assert data["subtotal"] == 1020.0
        assert data["taxes_and_fees"] == 102.0
        assert data["contingency_buffer"] == 102.0
        assert data["grand_total"] == 1224.0

    def test_financial_convert_unsupported_currency_returns_400(self):
        """Documented POST /api/v1/financial/convert with unsupported currency returns 400."""
        from tripmate.api.v1.routes.financial import convert_currency

        req = _mock_request("/api/v1/financial/convert", "POST")
        payload = CurrencyConversionRequest(
            amount=100.0,
            from_currency="USD",
            to_currency="XYZ",
        )
        with pytest.raises(HTTPException) as excinfo:
            _run(convert_currency(payload, req, current_user={"id": "doc_user"}))
        assert excinfo.value.status_code == 400


# ---------------------------------------------------------------------------
# 6. Background Task Examples
# ---------------------------------------------------------------------------


class TestTasksDocExamples:
    def test_submit_unregistered_task_returns_400(self):
        """Documented POST /api/v1/tasks/submit with unknown handler returns 400."""
        from tripmate.api.v1.routes.tasks import TaskSubmitRequest, submit_task

        req = _mock_request("/api/v1/tasks/submit", "POST")
        payload = TaskSubmitRequest(
            task_name="nonexistent_task_type",
            payload={},
        )
        with pytest.raises(HTTPException) as excinfo:
            _run(submit_task(payload, req, current_user={"id": "doc_user"}))
        assert excinfo.value.status_code == 400

    def test_get_nonexistent_task_returns_404(self):
        """Documented GET /api/v1/tasks/{id} missing task returns 404."""
        from tripmate.api.v1.routes.tasks import get_task_status

        req = _mock_request("/api/v1/tasks/nonexistent-task-id")
        with pytest.raises(HTTPException) as excinfo:
            _run(get_task_status("nonexistent-task-id", req, current_user={"id": "doc_user"}))
        assert excinfo.value.status_code == 404

    def test_list_tasks_documented_response(self):
        """Documented GET /api/v1/tasks returns list of submitted tasks."""
        from tripmate.api.v1.routes.tasks import list_tasks

        req = _mock_request("/api/v1/tasks")
        res = _run(list_tasks(req, status_filter=None, limit=50, current_user={"id": "doc_user"}))
        body = res.model_dump() if hasattr(res, "model_dump") else res
        assert body["success"] is True
        assert isinstance(body["data"], list)


# ---------------------------------------------------------------------------
# 7. Run Observability Examples
# ---------------------------------------------------------------------------


class TestRunsDocExamples:
    def test_get_nonexistent_run_returns_404(self):
        """Documented GET /api/v1/runs/{id} missing run returns 404."""
        from tripmate.api.v1.routes.runs import get_run_details

        req = _mock_request("/api/v1/runs/nonexistent-run-id")
        with pytest.raises(HTTPException) as excinfo:
            _run(get_run_details("nonexistent-run-id", req, user_identity="doc_user"))
        assert excinfo.value.status_code == 404

    def test_get_nonexistent_run_metrics_returns_404(self):
        """Documented GET /api/v1/runs/{id}/metrics missing run returns 404."""
        from tripmate.api.v1.routes.runs import get_run_metrics

        req = _mock_request("/api/v1/runs/nonexistent-run-id/metrics")
        with pytest.raises(HTTPException) as excinfo:
            _run(get_run_metrics("nonexistent-run-id", req, user_identity="doc_user"))
        assert excinfo.value.status_code == 404


# ---------------------------------------------------------------------------
# 8. AI Direct Invocations
# ---------------------------------------------------------------------------


class TestAIDocExamples:
    def test_invoke_unregistered_agent_returns_404(self):
        """Documented POST /api/v1/ai/agents/{name}/invoke missing agent returns 404."""
        from tripmate.api.v1.routes.ai import invoke_agent

        req = _mock_request("/api/v1/ai/agents/nonexistent_agent/invoke", "POST")
        payload = AIAgentInvokeRequest(query="find me a flight", context={})
        with pytest.raises(HTTPException) as excinfo:
            _run(invoke_agent("nonexistent_agent", payload, req, current_user={"id": "doc_user"}))
        assert excinfo.value.status_code == 404
