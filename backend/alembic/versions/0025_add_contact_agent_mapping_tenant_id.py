"""
BUG-LOG-012: Add tenant_id column to contact_agent_mapping for tenant isolation.

Previously ContactAgentMapping had no tenant_id, allowing cross-tenant
agent assignment. This migration adds tenant_id, backfills from the
agent table, and adds an index for tenant-scoped lookups.

Steps:
  1. Add nullable tenant_id VARCHAR(100) column
  2. Backfill from agent table (mapping.tenant_id := agent.tenant_id)
  3. Add index on tenant_id for fast tenant-scoped lookups

Note: tenant_id is kept nullable to support legacy rows where the
agent may have been deleted. New rows always set tenant_id explicitly.

Revision ID: 0025
Revises: 0024
"""
from alembic import op
import sqlalchemy as sa


revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'contact_agent_mapping' not in inspector.get_table_names():
        # Table does not exist yet — ORM will create it with tenant_id
        return

    existing_columns = {col['name'] for col in inspector.get_columns('contact_agent_mapping')}

    # Step 1: Add nullable tenant_id column (idempotent)
    if 'tenant_id' not in existing_columns:
        op.add_column(
            'contact_agent_mapping',
            sa.Column('tenant_id', sa.String(100), nullable=True)
        )

    # Step 2: Backfill from agent table
    op.execute(
        """
        UPDATE contact_agent_mapping
           SET tenant_id = agent.tenant_id
          FROM agent
         WHERE contact_agent_mapping.agent_id = agent.id
           AND contact_agent_mapping.tenant_id IS NULL
        """
    )

    # Step 3: Add index for tenant-scoped lookups (idempotent)
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('contact_agent_mapping')}
    if 'ix_contact_agent_mapping_tenant_id' not in existing_indexes:
        op.create_index(
            'ix_contact_agent_mapping_tenant_id',
            'contact_agent_mapping',
            ['tenant_id'],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'contact_agent_mapping' not in inspector.get_table_names():
        return

    existing_indexes = {idx['name'] for idx in inspector.get_indexes('contact_agent_mapping')}
    if 'ix_contact_agent_mapping_tenant_id' in existing_indexes:
        op.drop_index('ix_contact_agent_mapping_tenant_id', table_name='contact_agent_mapping')

    existing_columns = {col['name'] for col in inspector.get_columns('contact_agent_mapping')}
    if 'tenant_id' in existing_columns:
        op.drop_column('contact_agent_mapping', 'tenant_id')
