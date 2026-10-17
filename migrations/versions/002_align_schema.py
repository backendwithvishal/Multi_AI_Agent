"""Align schema with application models

Revision ID: 002_align_schema
Revises: 001_initial_schema
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002_align_schema"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Align alerts table: add alert_type and is_read columns
    op.add_column(
        "alerts",
        sa.Column("alert_type", sa.String(length=32), nullable=False, server_default="price_drop"),
    )
    op.add_column(
        "alerts",
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
    )

    # 2. Align assets table: add name, trip_id, content_uri, metadata, and make legacy columns nullable
    op.add_column(
        "assets",
        sa.Column("name", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("trip_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("content_uri", sa.Text(), nullable=True),
    )
    op.add_column(
        "assets",
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.alter_column("assets", "title", existing_type=sa.String(length=128), nullable=True)
    op.alter_column("assets", "content", existing_type=sa.Text(), nullable=True)
    op.create_index("ix_assets_trip_id", "assets", ["trip_id"])


def downgrade() -> None:
    op.drop_index("ix_assets_trip_id", "assets")
    op.alter_column("assets", "content", existing_type=sa.Text(), nullable=False)
    op.alter_column("assets", "title", existing_type=sa.String(length=128), nullable=False)
    op.drop_column("assets", "metadata")
    op.drop_column("assets", "content_uri")
    op.drop_column("assets", "trip_id")
    op.drop_column("assets", "name")
    op.drop_column("alerts", "is_read")
    op.drop_column("alerts", "alert_type")
