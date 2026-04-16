"""Add audit_event table for tenant-scoped audit logging.

Creates the audit_event table and adds audit_retention_days column to tenant.

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add audit_event table and audit_retention_days to tenant (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Create audit_event table
    if 'audit_event' not in existing_tables:
        op.create_table(
            'audit_event',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenant.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
            sa.Column('action', sa.String(100), nullable=False),
            sa.Column('resource_type', sa.String(50), nullable=True),
            sa.Column('resource_id', sa.String(100), nullable=True),
            sa.Column('details', JSONB(), nullable=True),
            sa.Column('ip_address', sa.String(50), nullable=True),
            sa.Column('user_agent', sa.String(500), nullable=True),
            sa.Column('channel', sa.String(20), nullable=True),
            sa.Column('severity', sa.String(10), server_default='info'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_audit_event_tenant_id', 'audit_event', ['tenant_id'])
        op.create_index('ix_audit_event_user_id', 'audit_event', ['user_id'])
        op.create_index('ix_audit_event_action', 'audit_event', ['action'])
        op.create_index('ix_audit_event_created_at', 'audit_event', ['created_at'])
        op.create_index('ix_audit_event_tenant_created', 'audit_event', ['tenant_id', 'created_at'])
        op.create_index('ix_audit_event_tenant_action', 'audit_event', ['tenant_id', 'action'])
        print("[Migration 0010] Created audit_event table with indexes")

    # Add audit_retention_days to tenant table
    existing_columns = [col['name'] for col in inspector.get_columns('tenant')]
    if 'audit_retention_days' not in existing_columns:
        op.add_column('tenant', sa.Column('audit_retention_days', sa.Integer(), server_default='90', nullable=True))
        print("[Migration 0010] Added audit_retention_days column to tenant")


def downgrade() -> None:
    """Remove audit_event table and audit_retention_days from tenant."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'audit_event' in existing_tables:
        op.drop_table('audit_event')

    existing_columns = [col['name'] for col in inspector.get_columns('tenant')]
    if 'audit_retention_days' in existing_columns:
        op.drop_column('tenant', 'audit_retention_days')
