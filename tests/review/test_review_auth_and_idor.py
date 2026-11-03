"""
Failing Proof-of-Concept Tests for Security Review: Authentication & IDOR Gaps
Author: External Security Reviewer

These tests assert correct defensive security behavior against discovered vulnerabilities
in the codebase. They fail against the current unpatched implementation.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app import app
from tripmate.config.settings import settings
from tripmate.database.store import store, generate_token
from tripmate.services.travel_service import RUN_STORE
from tripmate.api.dependencies import validate_thread_ownership


@pytest.fixture(autouse=True)
def ensure_test_mode(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "METRICS_PROTECTED", True)


@pytest.mark.asyncio
async def test_unauthenticated_flight_search_should_be_rejected_401():
    """
    VULNERABILITY: Booking endpoints lack authentication dependencies.
    File: tripmate/api/v1/routes/booking.py:38
    Expected: 401 Unauthorized for unauthenticated requests.
    Current: Returns 200/502 without authenticating the user.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/booking/flights/search?origin=JFK&destination=LHR&departure_date=2026-12-01")
        assert res.status_code == 401, f"Expected 401 Unauthorized, got {res.status_code}"


@pytest.mark.asyncio
async def test_unauthenticated_hotel_search_should_be_rejected_401():
    """
    VULNERABILITY: Booking hotel search endpoint lacks authentication.
    File: tripmate/api/v1/routes/booking.py:71
    Expected: 401 Unauthorized.
    Current: Returns 200/502 without checking identity.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/booking/hotels/search?city_code=NYC&check_in_date=2026-12-01&check_out_date=2026-12-05")
        assert res.status_code == 401, f"Expected 401 Unauthorized, got {res.status_code}"


@pytest.mark.asyncio
async def test_metrics_ip_spoofing_via_forwarded_for_should_be_rejected():
    """
    VULNERABILITY: /metrics unconditionally trusts X-Forwarded-For from untrusted remote peers.
    File: tripmate/api/v1/routes/metrics.py:20
    Expected: 403 Forbidden when an untrusted peer spoofs X-Forwarded-For: 127.0.0.1.
    Current: Bypasses auth because client IP is taken from header without verifying peer.
    """
    transport = ASGITransport(app=app, client=("203.0.113.195", 54321))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Untrusted public client spoofing loopback in header
        res = await client.get("/api/v1/metrics", headers={"X-Forwarded-For": "127.0.0.1"})
        assert res.status_code == 403, f"Expected 403 Forbidden for spoofed proxy header, got {res.status_code}"


@pytest.mark.asyncio
async def test_runs_idor_cross_user_isolation():
    """
    VULNERABILITY: GET /api/v1/runs/{run_id} allows any user to read other users' runs.
    File: tripmate/api/v1/routes/runs.py:26
    Expected: 404 or 403 when User B attempts to read User A's private run.
    Current: Returns 200 OK with full run telemetry and user queries.
    """
    # Create User A and User B
    user_a = {"id": "user_a_priv_1", "username": "usera", "role": "user"}
    user_b = {"id": "user_b_priv_2", "username": "userb", "role": "user"}
    store.create_user(user_a["username"], "user_a@test.com", "hash_pw_1", role="user")
    store.create_user(user_b["username"], "user_b@test.com", "hash_pw_2", role="user")
    token_b = generate_token(user_b["id"], user_b["username"], role="user")

    # Seed User A's run in RUN_STORE
    victim_run_id = "run_victim_test_001"
    RUN_STORE[victim_run_id] = {
        "run_id": victim_run_id,
        "user_id": user_a["id"],
        "answer": "Private itinerary details for User A",
        "selected_agents": ["flight_agent"],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/runs/{victim_run_id}",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res.status_code in (403, 404), (
            f"Expected 403/404 for cross-user run inspection, got {res.status_code} with data {res.text}"
        )


@pytest.mark.asyncio
async def test_runs_replay_unauthorized_user_rejection():
    """
    VULNERABILITY: POST /api/v1/runs/{run_id}/replay executes runs without verifying caller ownership.
    File: tripmate/api/v1/routes/runs.py:96
    Expected: 403/404 when unauthorized user replays another user's run.
    Current: Runs the workflow without verifying ownership.
    """
    user_b = {"id": "user_b_priv_2", "username": "userb", "role": "user"}
    token_b = generate_token(user_b["id"], user_b["username"], role="user")

    victim_run_id = "run_victim_replay_002"
    RUN_STORE[victim_run_id] = {
        "run_id": victim_run_id,
        "user_id": "user_a_priv_1",
        "answer": "Plan a 3-day trip to Tokyo",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/runs/{victim_run_id}/replay",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert res.status_code in (403, 404), (
            f"Expected 403/404 for unauthorized replay, got {res.status_code}"
        )


@pytest.mark.asyncio
async def test_price_lock_idor_reservation_by_different_user_rejected():
    """
    VULNERABILITY: Price locks in booking do not record or verify owning user.
    File: tripmate/api/v1/routes/booking.py:102, 123
    Expected: User B cannot reserve a fare locked by User A.
    Current: Any user can reserve any lock_id.
    """
    token_a = generate_token("user_lock_a", "usera", role="user")
    token_b = generate_token("user_lock_b", "userb", role="user")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # User A locks a price
        lock_res = await client.post(
            "/api/v1/booking/price-lock",
            json={
                "offer_id": "fl_test_001",
                "offer_type": "flight",
                "total_price": 450.0,
                "currency": "USD",
            },
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert lock_res.status_code == 200
        lock_id = lock_res.json()["data"]["lock_id"]

        # User B attempts to hijack/reserve User A's price lock
        reserve_res = await client.post(
            "/api/v1/booking/reserve",
            json={
                "lock_id": lock_id,
                "passenger_name": "Bob Attacker",
                "passenger_email": "bob@evil.com",
            },
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert reserve_res.status_code in (400, 403, 404), (
            f"Expected rejection when reserving another user's lock, got {reserve_res.status_code}"
        )


@pytest.mark.asyncio
async def test_stream_travel_rejects_unowned_thread_before_streaming_headers():
    """
    VULNERABILITY: POST /api/v1/travel/stream yields SSE data before checking thread ownership,
    committing HTTP 200 OK headers before ownership validation occurs.
    File: tripmate/services/travel_service.py:224-233
    Expected: HTTP 404 status code directly on response without streaming.
    Current: Returns 200 OK text/event-stream before ownership check.
    """
    store.register_thread_owner("thread_owner_victim", "user_victim_99")
    token_attacker = generate_token("user_attacker_99", "attacker", role="user")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/travel/stream",
            json={
                "message": "Continue trip planning",
                "thread_id": "thread_owner_victim",
            },
            headers={"Authorization": f"Bearer {token_attacker}"},
        )
        # Should return 404 HTTP status, NOT 200 OK with stream
        assert res.status_code == 404, (
            f"Expected HTTP 404 for unowned thread stream, but received HTTP {res.status_code}"
        )


@pytest.mark.asyncio
async def test_validate_thread_ownership_rejects_none_user_id():
    """
    VULNERABILITY: validate_thread_ownership allows None request_user_id to access owned threads.
    File: tripmate/api/dependencies.py:185
    Expected: Raises HTTPException(404) when request_user_id is None for an existing owned thread.
    Current: Evaluates (None and registered != None) to False, returning True.
    """
    store.register_thread_owner("thread_owned_by_someone", "user_legit_owner")
    with pytest.raises(Exception) as excinfo:
        await validate_thread_ownership("thread_owned_by_someone", request_user_id=None)
    assert "404" in str(excinfo.value) or getattr(excinfo.value, "status_code", None) == 404
