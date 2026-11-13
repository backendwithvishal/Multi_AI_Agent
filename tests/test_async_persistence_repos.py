"""
Unit & Integration Tests for Async Persistence Repositories & Concurrency State
"""

import time

import pytest

from tripmate.repositories.store_repositories import (
    audit_log_repository,
    booking_repository,
    itinerary_repository,
    trip_repository,
    workflow_run_repository,
)


def test_trip_and_itinerary_repositories():
    uid = "user_repo_test_01"

    # 1. Create Trip
    trip = trip_repository.create(
        user_id=uid,
        title="Alpine Ski Trip",
        destination="Zermatt, Switzerland",
        start_date="2026-12-15",
        end_date="2026-12-22",
        budget=5000.0,
    )
    assert trip["id"].startswith("trip_")
    assert trip["title"] == "Alpine Ski Trip"
    assert trip["budget"] == 5000.0

    # 2. Retrieve Trip
    fetched = trip_repository.get_by_id(trip["id"], user_id=uid)
    assert fetched is not None
    assert fetched["destination"] == "Zermatt, Switzerland"

    # IDOR check: other user cannot retrieve
    assert trip_repository.get_by_id(trip["id"], user_id="other_user") is None

    # 3. Update Trip
    updated = trip_repository.update(trip["id"], uid, {"budget": 5500.0})
    assert updated is not None
    assert updated["budget"] == 5500.0

    # 4. Create Itinerary
    itin = itinerary_repository.create(
        trip_id=trip["id"],
        user_id=uid,
        content="Day 1: Arrive Zurich, train to Zermatt.",
        day_plans={"day_1": ["Zurich", "Zermatt"]},
    )
    assert itin["id"].startswith("itin_")
    assert itin["trip_id"] == trip["id"]

    # 5. List Itineraries
    itins = itinerary_repository.list_by_trip(trip["id"], uid)
    assert len(itins) >= 1

    # 6. Delete Itinerary
    assert itinerary_repository.delete(itin["id"], uid) is True
    assert itinerary_repository.get_by_id(itin["id"], uid) is None

    # 7. Delete Trip
    assert trip_repository.delete(trip["id"], uid) is True
    assert trip_repository.get_by_id(trip["id"], uid) is None


def test_booking_repository_price_lock_and_expiry_relock():
    offer_id = "fl_offer_swiss_123"
    uid = "user_relock_test"

    # 1. Initial price lock
    lock1 = booking_repository.lock_price(
        offer_id=offer_id,
        offer_type="flight",
        total_price=450.0,
        currency="USD",
        user_id=uid,
    )
    assert lock1["lock_id"].startswith("lock_")
    assert lock1["locked_price"] == 450.0
    assert lock1["status"] in ("LOCKED", "ACTIVE")

    # 2. Simulate expiry
    lock1["expires_at"] = int(time.time()) - 10
    lock1["status"] = "EXPIRED"

    # 3. Re-lock after expiry should succeed (partial index allows re-locking when previous lock is not ACTIVE)
    lock2 = booking_repository.lock_price(
        offer_id=offer_id,
        offer_type="flight",
        total_price=475.0,
        currency="USD",
        user_id=uid,
    )
    assert lock2["lock_id"].startswith("lock_")
    assert lock2["locked_price"] == 475.0
    assert lock2["lock_id"] != lock1["lock_id"]

    # 4. Attempt reservation by another user must be rejected
    with pytest.raises(ValueError, match="does not belong to user"):
        booking_repository.create_reservation(
            user_id="other_attacker_uid",
            lock_id=lock2["lock_id"],
            passenger_name="Attacker",
            passenger_email="attacker@test.com",
        )

    # 5. Reserve offer
    reservation = booking_repository.create_reservation(
        user_id=uid,
        lock_id=lock2["lock_id"],
        passenger_name="Alice Smith",
        passenger_email="alice@tripmate.test",
        special_requests="Aisle seat",
    )
    assert reservation["booking_id"].startswith("bk_")
    assert reservation["pnr_code"] is not None
    assert reservation["booking_status"] == "CONFIRMED"

    # 6. Second reservation with redeemed lock must raise ValueError
    with pytest.raises(ValueError, match="already been redeemed"):
        booking_repository.create_reservation(
            user_id=uid,
            lock_id=lock2["lock_id"],
            passenger_name="Alice Smith",
            passenger_email="alice@tripmate.test",
        )


def test_workflow_run_and_audit_log_repositories():
    run_id = f"run_test_{int(time.time() * 1000)}"
    uid = "user_audit_run_test"

    # 1. Create Workflow Run
    run = workflow_run_repository.create(
        run_id=run_id,
        user_id=uid,
        thread_id="th_123",
        status="RUNNING",
        query="Trip to Iceland",
        metrics={"token_count": 1200},
    )
    assert run["run_id"] == run_id

    # 2. Update Run
    updated = workflow_run_repository.update(run_id, {"status": "COMPLETED", "itinerary": "Day 1: Reykjavik"})
    assert updated is not None
    assert updated["status"] == "COMPLETED"

    # 3. Retrieve Run
    fetched = workflow_run_repository.get_by_id(run_id, user_id=uid)
    assert fetched is not None
    assert fetched["status"] == "COMPLETED"

    # 4. Record Audit Log
    log = audit_log_repository.record(
        actor="user_audit_run_test",
        action="trip_created",
        target_id="trip_999",
        status="success",
        details={"ip": "127.0.0.1"},
    )
    assert log["id"].startswith("aud_")
    assert log["actor"] == "user_audit_run_test"

    logs = audit_log_repository.list_logs(limit=10, actor="user_audit_run_test")
    assert len(logs) >= 1
