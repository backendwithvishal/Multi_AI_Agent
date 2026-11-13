"""
Unit & Integration Tests for Trips & Itineraries API
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app import app
from tripmate.config.settings import settings
from tripmate.database.store import generate_token


@pytest.fixture
def user1_headers():
    token = generate_token("user_trip_01", "trip_user_1", role="user")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user2_headers():
    token = generate_token("user_trip_02", "trip_user_2", role="user")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_trips_unauthenticated_returns_401(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/trips")
        assert resp.status_code == 401



@pytest.mark.asyncio
async def test_trip_crud_lifecycle(user1_headers, user2_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create Trip
        create_payload = {
            "title": "Summer in Tokyo",
            "destination": "Tokyo, Japan",
            "start_date": "2026-07-01",
            "end_date": "2026-07-10",
            "budget": 3500.0,
        }
        resp = await client.post("/api/v1/trips", json=create_payload, headers=user1_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["success"] is True
        trip = data["data"]
        trip_id = trip["id"]
        assert trip["title"] == "Summer in Tokyo"
        assert trip["destination"] == "Tokyo, Japan"
        assert trip["budget"] == 3500.0

        # 2. Get Trip (Owner)
        resp_get = await client.get(f"/api/v1/trips/{trip_id}", headers=user1_headers)
        assert resp_get.status_code == 200
        assert resp_get.json()["data"]["id"] == trip_id

        # 3. Get Trip (Foreign User -> 404 IDOR Protection)
        resp_foreign = await client.get(f"/api/v1/trips/{trip_id}", headers=user2_headers)
        assert resp_foreign.status_code == 404

        # 4. List Trips
        resp_list = await client.get("/api/v1/trips", headers=user1_headers)
        assert resp_list.status_code == 200
        assert any(t["id"] == trip_id for t in resp_list.json()["data"])

        # 5. Update Trip
        resp_update = await client.put(
            f"/api/v1/trips/{trip_id}",
            json={"title": "Autumn in Tokyo", "budget": 4000.0},
            headers=user1_headers,
        )
        assert resp_update.status_code == 200
        assert resp_update.json()["data"]["title"] == "Autumn in Tokyo"
        assert resp_update.json()["data"]["budget"] == 4000.0

        # 6. Create Itinerary under Trip
        itin_payload = {
            "content": "Day 1: Arrival at Haneda, check-in, Shinjuku evening walk.",
            "day_plans": {"day_1": ["Haneda", "Shinjuku"]},
            "status": "DRAFT",
        }
        resp_itin = await client.post(
            f"/api/v1/trips/{trip_id}/itineraries",
            json=itin_payload,
            headers=user1_headers,
        )
        assert resp_itin.status_code == 201
        itin = resp_itin.json()["data"]
        itin_id = itin["id"]
        assert itin["trip_id"] == trip_id

        # 7. List Itineraries
        resp_itin_list = await client.get(f"/api/v1/trips/{trip_id}/itineraries", headers=user1_headers)
        assert resp_itin_list.status_code == 200
        assert len(resp_itin_list.json()["data"]) >= 1

        # 8. Delete Itinerary
        resp_del_itin = await client.delete(f"/api/v1/trips/{trip_id}/itineraries/{itin_id}", headers=user1_headers)
        assert resp_del_itin.status_code == 200

        # 9. Delete Trip
        resp_del = await client.delete(f"/api/v1/trips/{trip_id}", headers=user1_headers)
        assert resp_del.status_code == 200

        # 10. Verify Trip Deleted
        resp_check = await client.get(f"/api/v1/trips/{trip_id}", headers=user1_headers)
        assert resp_check.status_code == 404
