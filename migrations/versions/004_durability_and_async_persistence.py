"""Add trips, itineraries, bookings, price_locks, audit_logs, workflow_runs and schema extensions

Revision ID: 004_durability_and_async_persistence
Revises: 003_api_keys_and_budgets
Create Date: 2026-11-13 22:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004_durability_and_async_persistence"
down_revision: Union[str, None] = "003_api_keys_and_budgets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Trips table (owner-scoped travel projects)
    op.create_table(
        "trips",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("destination", sa.String(length=128), nullable=False),
        sa.Column("start_date", sa.String(length=32), nullable=True),
        sa.Column("end_date", sa.String(length=32), nullable=True),
        sa.Column("budget", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PLANNING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trips_user_id", "trips", ["user_id"])

    # 2. Itineraries table (belongs to trip, cascades on trip/user delete)
    op.create_table(
        "itineraries",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("trip_id", sa.String(length=64), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("day_plans", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="DRAFT"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_itineraries_trip_id", "itineraries", ["trip_id"])
    op.create_index("ix_itineraries_user_id", "itineraries", ["user_id"])

    # 3. Bookings table (financial/regulatory record: SET NULL on delete for GDPR anonymization)
    op.create_table(
        "bookings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("trip_id", sa.String(length=64), sa.ForeignKey("trips.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("offer_id", sa.String(length=128), nullable=False),
        sa.Column("offer_type", sa.String(length=32), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("passenger_name", sa.String(length=128), nullable=True),
        sa.Column("passenger_email", sa.String(length=128), nullable=True),
        sa.Column("special_requests", sa.Text(), nullable=True),
        sa.Column("gds_pnr", sa.String(length=64), nullable=True),
        sa.Column("stripe_payment_intent_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CONFIRMED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_trip_id", "bookings", ["trip_id"])
    op.create_index("ix_bookings_gds_pnr", "bookings", ["gds_pnr"])
    op.create_index("ix_bookings_stripe_pi", "bookings", ["stripe_payment_intent_id"])

    # 4. Price Locks table (with partial unique index on ACTIVE locks for re-locking after expiry)
    op.create_table(
        "price_locks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("offer_id", sa.String(length=128), nullable=False),
        sa.Column("offer_type", sa.String(length=32), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_price_locks_user_id", "price_locks", ["user_id"])
    op.create_index(
        "uq_price_locks_active_offer_user",
        "price_locks",
        ["offer_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    # 5. Audit logs table (immutable audit records, no cascade on user delete)
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("hash", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_actor", "audit_logs", ["actor"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # 6. Workflow runs table (replaces in-memory RUN_STORE)
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("thread_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="RUNNING"),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("itinerary", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("events", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])
    op.create_index("ix_workflow_runs_thread_id", "workflow_runs", ["thread_id"])

    # 7. Alter existing tables
    # Watchlists: add last_checked_at
    op.add_column("watchlists", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))

    # Alerts: add channel
    op.add_column(
        "alerts",
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="IN_APP"),
    )

    # Assets: add storage_key and scan_status, backfill existing rows as 'clean', default new rows to 'pending'
    op.add_column("assets", sa.Column("storage_key", sa.String(length=256), nullable=True))
    op.add_column(
        "assets",
        sa.Column("scan_status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.execute("UPDATE assets SET scan_status = 'clean' WHERE scan_status IS NULL OR scan_status = 'pending'")


def downgrade() -> None:
    # 1. Revert alterations on existing tables
    op.drop_column("assets", "scan_status")
    op.drop_column("assets", "storage_key")
    op.drop_column("alerts", "channel")
    op.drop_column("watchlists", "last_checked_at")

    # 2. Drop new tables in reverse dependency order
    op.drop_index("ix_workflow_runs_thread_id", "workflow_runs")
    op.drop_index("ix_workflow_runs_user_id", "workflow_runs")
    op.drop_table("workflow_runs")

    op.drop_index("ix_audit_logs_created_at", "audit_logs")
    op.drop_index("ix_audit_logs_actor", "audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("uq_price_locks_active_offer_user", "price_locks")
    op.drop_index("ix_price_locks_user_id", "price_locks")
    op.drop_table("price_locks")

    op.drop_index("ix_bookings_stripe_pi", "bookings")
    op.drop_index("ix_bookings_gds_pnr", "bookings")
    op.drop_index("ix_bookings_trip_id", "bookings")
    op.drop_index("ix_bookings_user_id", "bookings")
    op.drop_table("bookings")

    op.drop_index("ix_itineraries_user_id", "itineraries")
    op.drop_index("ix_itineraries_trip_id", "itineraries")
    op.drop_table("itineraries")

    op.drop_index("ix_trips_user_id", "trips")
    op.drop_table("trips")

