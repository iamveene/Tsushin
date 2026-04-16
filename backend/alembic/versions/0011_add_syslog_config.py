"""Add tenant_syslog_config table for syslog streaming.

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add tenant_syslog_config table (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'tenant_syslog_config' not in existing_tables:
        op.create_table(
            'tenant_syslog_config',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenant.id'), unique=True, nullable=False),
            sa.Column('enabled', sa.Boolean(), server_default='false'),
            sa.Column('host', sa.String(255), nullable=True),
            sa.Column('port', sa.Integer(), server_default='514'),
            sa.Column('protocol', sa.String(10), server_default="'tcp'"),
            sa.Column('facility', sa.Integer(), server_default='1'),
            sa.Column('app_name', sa.String(48), server_default="'tsushin'"),
            sa.Column('tls_ca_cert_encrypted', sa.Text(), nullable=True),
            sa.Column('tls_client_cert_encrypted', sa.Text(), nullable=True),
            sa.Column('tls_client_key_encrypted', sa.Text(), nullable=True),
            sa.Column('tls_verify', sa.Boolean(), server_default='true'),
            sa.Column('event_categories', sa.Text(), nullable=True),
            sa.Column('last_successful_send', sa.DateTime(), nullable=True),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('last_error_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_tenant_syslog_config_tenant_id', 'tenant_syslog_config', ['tenant_id'])
        print("[Migration 0011] Created tenant_syslog_config table")


def downgrade() -> None:
    """Remove tenant_syslog_config table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'tenant_syslog_config' in inspector.get_table_names():
        op.drop_table('tenant_syslog_config')
