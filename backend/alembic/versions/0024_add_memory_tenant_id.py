"""
BUG-LOG-015: Add tenant_id column to memory table for DB-level tenant isolation.

Previously, the Memory table only had `agent_id` as an isolation boundary —
effective isolation depended on every query site remembering to scope by
agent_ids belonging to the caller's tenant. This migration adds `tenant_id`
directly to the Memory model so isolation can be enforced at the row level
(defense-in-depth), and adds a composite index to keep per-tenant reads fast.

Steps:
  1. Add nullable `tenant_id` VARCHAR(50) column
  2. Backfill from agent table (memory.tenant_id := agent.tenant_id where
     agent.id = memory.agent_id)
  3. Delete orphan memory rows whose agent_id no longer exists
  4. Make tenant_id NOT NULL
  5. Add composite index (tenant_id, agent_id, sender_key)

Revision ID: 0024
Revises: 0023
"""
from alembic import op
import sqlalchemy as sa


revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'memory' not in inspector.get_table_names():
        # Fresh install — table will be created by ORM metadata with tenant_id already present.
        return

    existing_columns = {col['name'] for col in inspector.get_columns('memory')}

    # Step 1: add nullable tenant_id column (idempotent)
    if 'tenant_id' not in existing_columns:
        op.add_column('memory', sa.Column('tenant_id', sa.String(50), nullable=True))

    # Step 2: backfill from agent table
    op.execute(
        """
        UPDATE memory
           SET tenant_id = agent.tenant_id
          FROM agent
         WHERE memory.agent_id = agent.id
           AND memory.tenant_id IS NULL
        """
    )

    # Step 3: delete orphan rows (agent_id no longer exists OR agent has null tenant_id)
    # These rows cannot be safely assigned to any tenant and would block the NOT NULL constraint.
    orphan_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM memory WHERE tenant_id IS NULL")
    ).scalar() or 0
    if orphan_count > 0:
        print(f"[0024_add_memory_tenant_id] Deleting {orphan_count} orphan memory row(s) with no tenant binding")
        op.execute("DELETE FROM memory WHERE tenant_id IS NULL")

    # Step 4: make column NOT NULL
    op.alter_column('memory', 'tenant_id', existing_type=sa.String(50), nullable=False)

    # Step 5: composite index for per-tenant lookups
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('memory')}
    if 'idx_memory_tenant_agent_sender' not in existing_indexes:
        op.create_index(
            'idx_memory_tenant_agent_sender',
            'memory',
            ['tenant_id', 'agent_id', 'sender_key'],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'memory' not in inspector.get_table_names():
        return

    existing_indexes = {idx['name'] for idx in inspector.get_indexes('memory')}
    if 'idx_memory_tenant_agent_sender' in existing_indexes:
        op.drop_index('idx_memory_tenant_agent_sender', table_name='memory')

    existing_columns = {col['name'] for col in inspector.get_columns('memory')}
    if 'tenant_id' in existing_columns:
        op.drop_column('memory', 'tenant_id')
