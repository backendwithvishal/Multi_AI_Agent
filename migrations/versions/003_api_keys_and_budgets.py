"""Add api_keys and usage_budgets tables

Revision ID: 003_api_keys_and_budgets
Revises: 002_align_schema
Create Date: 2026-10-30 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_api_keys_and_budgets"
down_revision: Union[str, None] = "002_align_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. API Keys table for per-user hashed API key authentication
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("key_hash", sa.String(length=64), unique=True, nullable=False),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False, server_default="default"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    # 2. Daily token usage & cost budget tracking table
    op.create_table(
        "usage_budgets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.String(length=64), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date_str", sa.String(length=16), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "date_str", name="uq_user_date_budget"),
    )
    op.create_index("ix_usage_budgets_user_date", "usage_budgets", ["user_id", "date_str"])


def downgrade() -> None:
    op.drop_index("ix_usage_budgets_user_date", "usage_budgets")
    op.drop_table("usage_budgets")
    op.drop_index("ix_api_keys_user_id", "api_keys")
    op.drop_index("ix_api_keys_key_hash", "api_keys")
    op.drop_table("api_keys")
