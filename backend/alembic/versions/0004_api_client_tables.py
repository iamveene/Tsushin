"""Add API client tables for Public API v1.

Supports OAuth2 client credentials authentication, token tracking,
and request audit logging for programmatic API access.

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create api_client, api_client_token, and api_request_log tables."""

    # --- api_client ---
    op.create_table(
        'api_client',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('client_id', sa.String(50), unique=True, nullable=False),
        sa.Column('client_secret_hash', sa.String(255), nullable=False),
        sa.Column('client_secret_prefix', sa.String(12), nullable=False),
        sa.Column('role', sa.String(30), server_default='api_agent_only'),
        sa.Column('custom_scopes', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1'),
        sa.Column('rate_limit_rpm', sa.Integer(), server_default='60'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_api_client_tenant_id', 'api_client', ['tenant_id'])
    op.create_index('ix_api_client_client_id', 'api_client', ['client_id'], unique=True)
    op.create_index('uq_api_client_tenant_name', 'api_client', ['tenant_id', 'name'], unique=True)
    op.create_index('ix_api_client_prefix', 'api_client', ['client_secret_prefix'])

    # --- api_client_token ---
    op.create_table(
        'api_client_token',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('api_client_id', sa.Integer(), sa.ForeignKey('api_client.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(255), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('issued_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
    )
    op.create_index('ix_api_client_token_client', 'api_client_token', ['api_client_id'])
    op.create_index('ix_api_client_token_hash', 'api_client_token', ['token_hash'])

    # --- api_request_log ---
    op.create_table(
        'api_request_log',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('api_client_id', sa.Integer(), sa.ForeignKey('api_client.id'), nullable=False),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('path', sa.String(500), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_api_request_log_client', 'api_request_log', ['api_client_id'])
    op.create_index('ix_api_request_log_created', 'api_request_log', ['created_at'])


def downgrade() -> None:
    """Drop API client tables in reverse order."""
    op.drop_table('api_request_log')
    op.drop_table('api_client_token')
    op.drop_table('api_client')
