"""Add provider instance tables for multi-instance provider support.

Phase 21: OpenAI URL Rebase & Multi-Instance Providers.
Creates provider_instance, provider_url_policy, and provider_connection_audit
tables, and adds provider_instance_id FK to the agent table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create provider instance tables and add FK to agent (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. provider_instance
    if 'provider_instance' not in existing_tables:
        op.create_table(
            'provider_instance',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(50), nullable=False, index=True),
            sa.Column('vendor', sa.String(30), nullable=False),
            sa.Column('instance_name', sa.String(100), nullable=False),
            sa.Column('base_url', sa.String(500), nullable=True),
            sa.Column('api_key_encrypted', sa.Text(), nullable=True),
            sa.Column('available_models', sa.JSON(), server_default='[]'),
            sa.Column('is_default', sa.Boolean(), server_default=sa.text('false')),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
            sa.Column('health_status', sa.String(20), server_default='unknown'),
            sa.Column('health_status_reason', sa.String(500), nullable=True),
            sa.Column('last_health_check', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('tenant_id', 'instance_name', name='uq_provider_instance_tenant_name'),
        )
        op.create_index('idx_pi_tenant_vendor', 'provider_instance', ['tenant_id', 'vendor'])

    # 2. provider_url_policy
    if 'provider_url_policy' not in existing_tables:
        op.create_table(
            'provider_url_policy',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('scope', sa.String(10), nullable=False),
            sa.Column('tenant_id', sa.String(50), nullable=True),
            sa.Column('policy_type', sa.String(10), nullable=False),
            sa.Column('url_pattern', sa.String(500), nullable=False),
            sa.Column('description', sa.String(255), nullable=True),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )

    # 3. provider_connection_audit
    if 'provider_connection_audit' not in existing_tables:
        op.create_table(
            'provider_connection_audit',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(50), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('provider_instance_id', sa.Integer(), nullable=False),
            sa.Column('action', sa.String(30), nullable=False),
            sa.Column('resolved_ip', sa.String(45), nullable=True),
            sa.Column('base_url', sa.String(500), nullable=True),
            sa.Column('success', sa.Boolean(), nullable=False),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )

    # 4. Add provider_instance_id FK to agent table
    columns = [c['name'] for c in inspector.get_columns('agent')]
    if 'provider_instance_id' not in columns:
        op.add_column('agent', sa.Column(
            'provider_instance_id',
            sa.Integer(),
            sa.ForeignKey('provider_instance.id', ondelete='SET NULL'),
            nullable=True,
        ))


def downgrade() -> None:
    """Remove provider instance tables and FK from agent."""
    op.drop_column('agent', 'provider_instance_id')
    op.drop_table('provider_connection_audit')
    op.drop_table('provider_url_policy')
    op.drop_index('idx_pi_tenant_vendor', table_name='provider_instance')
    op.drop_table('provider_instance')
