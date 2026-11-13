"""Unit tests for SQLAlchemy 2.0 ORM models in tripmate.database.models."""

from datetime import datetime, timezone
from decimal import Decimal

from tripmate.database.models import (
    Alert,
    ApiKey,
    Asset,
    AuditLog,
    Base,
    Booking,
    Itinerary,
    PasswordResetToken,
    PriceLock,
    ThreadOwnership,
    Trip,
    UsageBudget,
    User,
    Watchlist,
    WorkflowRun,
)


def test_models_metadata_tables():
    """Verify all platform tables are defined in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {
        "users",
        "trips",
        "itineraries",
        "bookings",
        "price_locks",
        "watchlists",
        "alerts",
        "assets",
        "audit_logs",
        "workflow_runs",
        "password_reset_tokens",
        "thread_ownership",
        "api_keys",
        "usage_budgets",
    }
    assert expected_tables.issubset(table_names)


def test_model_instantiations():
    """Verify model instances can be created with expected fields."""
    now = datetime.now(timezone.utc)

    user = User(
        id="usr_001",
        username="testuser",
        email="test@example.com",
        password_hash="hash123",
        role="user",
        created_at=now,
    )
    assert user.id == "usr_001"
    assert user.email == "test@example.com"

    trip = Trip(
        id="trip_001",
        user_id="usr_001",
        title="Tokyo Adventure",
        destination="Tokyo",
        budget=Decimal("2500.00"),
        status="PLANNING",
        created_at=now,
        updated_at=now,
    )
    assert trip.destination == "Tokyo"
    assert trip.budget == Decimal("2500.00")

    itinerary = Itinerary(
        id="itin_001",
        trip_id="trip_001",
        user_id="usr_001",
        content="Day 1: Shibuya",
        day_plans={"day1": ["Shibuya", "Shinjuku"]},
        status="DRAFT",
        created_at=now,
    )
    assert itinerary.trip_id == "trip_001"

    booking = Booking(
        id="bk_001",
        user_id="usr_001",
        trip_id="trip_001",
        offer_id="off_123",
        offer_type="flight",
        total_price=Decimal("450.00"),
        currency="USD",
        gds_pnr="ABC123XYZ",
        stripe_payment_intent_id="pi_12345",
        status="CONFIRMED",
        created_at=now,
    )
    assert booking.gds_pnr == "ABC123XYZ"
    assert booking.total_price == Decimal("450.00")

    price_lock = PriceLock(
        id="lck_001",
        user_id="usr_001",
        offer_id="off_123",
        offer_type="flight",
        total_price=Decimal("450.00"),
        currency="USD",
        status="ACTIVE",
        expires_at=int(now.timestamp()) + 900,
        created_at=now,
    )
    assert price_lock.status == "ACTIVE"

    watchlist = Watchlist(
        id="w_001",
        user_id="usr_001",
        title="SFO to NRT",
        target_type="flight",
        target_value="SFO-NRT",
        threshold_price=Decimal("600.00"),
        current_price_estimate=Decimal("650.00"),
        currency="USD",
        active=True,
        created_at=now,
    )
    assert watchlist.active is True

    alert = Alert(
        id="alt_001",
        user_id="usr_001",
        title="Price dropped",
        message="Flight dropped below $600",
        alert_type="price_drop",
        severity="info",
        read=False,
        channel="IN_APP",
        created_at=now,
    )
    assert alert.channel == "IN_APP"

    asset = Asset(
        id="ast_001",
        user_id="usr_001",
        asset_type="itinerary_pdf",
        storage_key="s3://bucket/test.pdf",
        scan_status="clean",
        size_bytes=1024,
        created_at=now,
    )
    assert asset.scan_status == "clean"

    audit = AuditLog(
        id="aud_001",
        actor="usr_001",
        action="trip.create",
        target_id="trip_001",
        ip_address="127.0.0.1",
        status="success",
        details={"source": "api"},
        created_at=now,
    )
    assert audit.action == "trip.create"

    run = WorkflowRun(
        id="run_001",
        user_id="usr_001",
        thread_id="th_001",
        status="RUNNING",
        created_at=now,
    )
    assert run.status == "RUNNING"

    reset = PasswordResetToken(
        token="tok_123",
        user_id="usr_001",
        expires_at=int(now.timestamp()) + 3600,
        used=False,
    )
    assert reset.used is False

    thread_own = ThreadOwnership(
        thread_id="th_001",
        user_id="usr_001",
        created_at=now,
    )
    assert thread_own.user_id == "usr_001"

    api_key = ApiKey(
        id="key_001",
        key_hash="hash_abc",
        user_id="usr_001",
        name="test key",
        created_at=now,
    )
    assert api_key.name == "test key"

    budget = UsageBudget(
        id="bg_001",
        user_id="usr_001",
        date_str="2026-11-13",
        token_count=1000,
        request_count=5,
        updated_at=now,
    )
    assert budget.token_count == 1000
