"""Initial Schema for TripMate Platform

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('username', sa.String(length=64), unique=True, nullable=False),
        sa.Column('email', sa.String(length=128), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False, server_default='user'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])

    # 2. Watchlists table
    op.create_table(
        'watchlists',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_value', sa.String(length=256), nullable=False),
        sa.Column('threshold_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('current_price_estimate', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('currency', sa.String(length=8), nullable=False, server_default='USD'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_watchlists_user_id', 'watchlists', ['user_id'])

    # 3. Alerts table
    op.create_table(
        'alerts',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('watchlist_id', sa.String(length=64), nullable=True),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=32), nullable=False, server_default='info'),
        sa.Column('read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_alerts_user_id', 'alerts', ['user_id'])

    # 4. Assets table
    op.create_table(
        'assets',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('asset_type', sa.String(length=64), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('file_format', sa.String(length=32), nullable=False, server_default='json'),
        sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_assets_user_id', 'assets', ['user_id'])

    # 5. Password reset tokens table
    op.create_table(
        'password_reset_tokens',
        sa.Column('token', sa.String(length=128), primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('expires_at', sa.BigInteger(), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_pwd_reset_token', 'password_reset_tokens', ['token'])

    # 6. Thread ownership registry
    op.create_table(
        'thread_ownership',
        sa.Column('thread_id', sa.String(length=128), primary_key=True),
        sa.Column('user_id', sa.String(length=64), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_thread_ownership_user_id', 'thread_ownership', ['user_id'])


def downgrade() -> None:
    op.drop_table('thread_ownership')
    op.drop_table('password_reset_tokens')
    op.drop_table('assets')
    op.drop_table('alerts')
    op.drop_table('watchlists')
    op.drop_table('users')
