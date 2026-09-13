"""
Comprehensive Test Suite for Roadmap & Platform Enhancement Features:
1. Alembic Database Migration Pipeline (P1)
2. Prometheus Observability Metrics Exporter (P2)
3. Distributed Background Task Queue & Workers (P3)
4. GDS Flight & Hotel Travel Booking Adapter (P4 / Long-term)
"""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from app import app

from tripmate.database.migrator import get_alembic_config, get_migration_history
from tripmate.middleware.metrics import metrics_registry
from tripmate.tasks.queue import task_queue, AsyncTaskQueue
from tripmate.integrations.gds import gds_client
from tripmate.database.store import generate_token


@pytest.fixture
def auth_headers():
    token = generate_token("user_demo_002", "demouser", "user")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers():
    token = generate_token("user_admin_001", "admin", "admin")
    return {"Authorization": f"Bearer {token}"}


# =========================================================
# 1. Alembic Migration Pipeline Tests (P1)
# =========================================================

def test_alembic_configuration_and_history():
    """Verifies that Alembic configuration and migration revisions are properly initialized."""
    config = get_alembic_config()
    assert config is not None
    assert config.get_main_option("script_location") is not None

    history = get_migration_history()
    assert len(history) >= 1
    assert "001_initial_schema" in history


# =========================================================
# 2. Prometheus Observability Metrics Tests (P2)
# =========================================================

@pytest.mark.asyncio
async def test_prometheus_metrics_registry():
    """Tests Prometheus metrics recording and exposition text generation."""
    metrics_registry.record_http_request("GET", "/api/v1/health", 200, 0.045)
    metrics_registry.record_agent_execution("flight_agent", "success", 0.35)

    text = metrics_registry.generate_prometheus_text()
    assert "tripmate_uptime_seconds" in text
    assert "tripmate_http_requests_total" in text
    assert "tripmate_agent_executions_total" in text
    assert 'agent="flight_agent"' in text


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoints():
    """Tests GET /metrics and GET /api/v1/metrics endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/metrics")
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        assert "tripmate_uptime_seconds" in res.text

        res_v1 = await client.get("/api/v1/metrics")
        assert res_v1.status_code == 200
        assert "tripmate_http_active_requests" in res_v1.text


# =========================================================
# 3. Background Task Queue & Worker Tests (P3)
# =========================================================

@pytest.mark.asyncio
async def test_task_queue_execution():
    """Tests task submission, worker execution, and status completion."""
    custom_queue = AsyncTaskQueue(max_concurrent_workers=2)
    
    async def sample_handler(payload):
        await asyncio.sleep(0.01)
        return {"doubled": payload.get("val", 0) * 2}

    custom_queue.register_handler("double_it", sample_handler)
    await custom_queue.start()

    try:
        record = await custom_queue.submit_task("double_it", {"val": 21}, user_id="user_test")
        assert record["status"] == "PENDING"
        task_id = record["id"]

        # Wait for completion
        for _ in range(20):
            await asyncio.sleep(0.05)
            t = custom_queue.get_task(task_id)
            if t and t["status"] == "COMPLETED":
                break

        final_task = custom_queue.get_task(task_id)
        assert final_task["status"] == "COMPLETED"
        assert final_task["result"] == {"doubled": 42}
        assert final_task["progress_percent"] == 100
    finally:
        await custom_queue.stop()


@pytest.mark.asyncio
async def test_tasks_api_lifecycle(auth_headers):
    """Tests REST endpoints: /api/v1/tasks/submit, /api/v1/tasks/{id}, /api/v1/tasks."""
    await task_queue.start()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Submit watchlist price scan task
        submit_res = await client.post(
            "/api/v1/tasks/submit",
            json={"task_name": "watchlist_price_scan", "payload": {}},
            headers=auth_headers,
        )
        assert submit_res.status_code == 200
        data = submit_res.json()["data"]
        task_id = data["id"]
        assert data["name"] == "watchlist_price_scan"

        # 2. Poll for status
        for _ in range(50):
            await asyncio.sleep(0.05)
            status_res = await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)
            assert status_res.status_code == 200
            t_data = status_res.json()["data"]
            if t_data["status"] == "COMPLETED":
                break

        assert t_data["status"] == "COMPLETED"
        assert "scanned_watchlists" in t_data["result"]

        # 3. List tasks
        list_res = await client.get("/api/v1/tasks", headers=auth_headers)
        assert list_res.status_code == 200
        tasks = list_res.json()["data"]
        assert any(t["id"] == task_id for t in tasks)


# =========================================================
# 4. GDS Travel Booking & Search Tests (P4 / Long-term)
# =========================================================

@pytest.mark.asyncio
async def test_gds_client_operations():
    """Tests GDS flight search, hotel search, price locking, and reservation."""
    # 1. Flight Search
    flights = await gds_client.search_flights("JFK", "LHR", "2026-10-01", adults=2, cabin_class="ECONOMY")
    assert flights["offers_count"] >= 1
    offer = flights["offers"][0]
    assert offer["origin"] == "JFK"
    assert offer["destination"] == "LHR"
    assert offer["total_price"] > 0

    # 2. Hotel Search
    hotels = await gds_client.search_hotels("NYC", "2026-10-01", "2026-10-05")
    assert hotels["hotels_count"] >= 1
    hotel = hotels["hotels"][0]
    assert "Grand Hyatt" in hotel["name"] or "Marriott" in hotel["name"]

    # 3. Lock Price
    lock = await gds_client.lock_price(offer["offer_id"], "flight", offer["total_price"])
    assert lock["status"] == "LOCKED"
    assert lock["locked_price"] == offer["total_price"]

    # 4. Create Reservation
    reservation = await gds_client.create_reservation(
        user_id="user_demo_002",
        lock_id=lock["lock_id"],
        passenger_name="Jane Doe",
        passenger_email="jane@example.com",
    )
    assert reservation["booking_status"] == "CONFIRMED"
    assert len(reservation["pnr_code"]) == 6
    assert reservation["booking_id"].startswith("bk_")


@pytest.mark.asyncio
async def test_booking_api_endpoints(auth_headers):
    """Tests /api/v1/booking/flights/search, /hotels/search, /price-lock, /reserve, /reservations/{id}."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Flight search
        flight_res = await client.get(
            "/api/v1/booking/flights/search",
            params={"origin": "SFO", "destination": "HND", "departure_date": "2026-11-15", "adults": 1},
            headers=auth_headers,
        )
        assert flight_res.status_code == 200
        offers = flight_res.json()["data"]["offers"]
        assert len(offers) > 0
        selected_offer = offers[0]

        # 2. Hotel search
        hotel_res = await client.get(
            "/api/v1/booking/hotels/search",
            params={"city_code": "TYO", "check_in_date": "2026-11-15", "check_out_date": "2026-11-20"},
            headers=auth_headers,
        )
        assert hotel_res.status_code == 200
        assert hotel_res.json()["data"]["hotels_count"] > 0

        # 3. Price lock
        lock_res = await client.post(
            "/api/v1/booking/price-lock",
            json={
                "offer_id": selected_offer["offer_id"],
                "offer_type": "flight",
                "total_price": selected_offer["total_price"],
                "currency": "USD",
            },
            headers=auth_headers,
        )
        assert lock_res.status_code == 200
        lock_id = lock_res.json()["data"]["lock_id"]

        # 4. Reserve
        reserve_res = await client.post(
            "/api/v1/booking/reserve",
            json={
                "lock_id": lock_id,
                "passenger_name": "Alexander Hamilton",
                "passenger_email": "alex@treasury.gov",
                "special_requests": "Window seat, vegan meal",
            },
            headers=auth_headers,
        )
        assert reserve_res.status_code == 200
        booking = reserve_res.json()["data"]
        booking_id = booking["booking_id"]
        assert booking["pnr_code"] is not None

        # 5. Lookup Reservation
        lookup_res = await client.get(f"/api/v1/booking/reservations/{booking_id}", headers=auth_headers)
        assert lookup_res.status_code == 200
        assert lookup_res.json()["data"]["passenger_name"] == "Alexander Hamilton"
