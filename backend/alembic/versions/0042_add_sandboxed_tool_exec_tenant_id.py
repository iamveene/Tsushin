"""Add tenant_id column to sandboxed_tool_executions.

BUG-614 v0.7.3: The playground debug endpoint
(``routes_playground.py::get_playground_debug``) joins
``sandboxed_tool_executions`` with a ``e.tenant_id`` filter so a tenant
only sees their own tool-call history. The model had no such column —
the query was silently returning zero rows on some driver combinations
and failing outright on others, so the playground's "Recent tool calls"
panel looked permanently empty for every tenant.

This migration:
  1. Adds ``tenant_id VARCHAR(50) NULL`` with an index.
  2. Backfills tenant_id for every existing row via the join
     ``sandboxed_tool_executions -> agent_run -> agent -> agent.tenant_id``.
  3. Leaves legacy rows with NULL tenant_id intact (the playground
     query already treats NULL / empty / 'default' as "unscoped legacy"
     so they stay visible until they age out).

Column stays nullable because:
  - Manual executions (no agent_run_id) have no agent to backfill from.
  - The playground endpoint's filter accepts NULL / '' / 'default' as
    legacy-visible rows.

Revision ID: 0042
Revises: 0041
Create Date: 2026-04-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0042'
down_revision: Union[str, None] = '0041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'sandboxed_tool_executions' not in existing_tables:
        # Brand-new deployments that have never seen the sandboxed tools
        # feature yet — nothing to migrate; models.py will create the
        # table with the column baked in via ORM metadata bootstrap.
        return

    cols = [c['name'] for c in inspector.get_columns('sandboxed_tool_executions')]
    if 'tenant_id' not in cols:
        op.add_column(
            'sandboxed_tool_executions',
            sa.Column('tenant_id', sa.String(length=50), nullable=True),
        )

    # Create the index if it isn't already there — be defensive because
    # ``add_column`` does not create indexes and running the migration
    # twice under PostgreSQL would otherwise crash on duplicate index.
    existing_idx = {ix['name'] for ix in inspector.get_indexes('sandboxed_tool_executions')}
    idx_name = 'ix_sandboxed_tool_executions_tenant_id'
    if idx_name not in existing_idx:
        op.create_index(
            idx_name,
            'sandboxed_tool_executions',
            ['tenant_id'],
        )

    # Backfill tenant_id for rows that have one resolvable.
    # Only attempt if both dependency tables exist — dev/test containers
    # sometimes spin up with subsets of tables when alembic runs before
    # app bootstrap finishes.
    if 'agent_run' in existing_tables and 'agent' in existing_tables:
        bind.execute(
            sa.text(
                """
                UPDATE sandboxed_tool_executions AS e
                SET tenant_id = a.tenant_id
                FROM agent_run AS r
                JOIN agent AS a ON a.id = r.agent_id
                WHERE e.agent_run_id = r.id
                  AND e.tenant_id IS NULL
                  AND a.tenant_id IS NOT NULL
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'sandboxed_tool_executions' not in existing_tables:
        return

    existing_idx = {ix['name'] for ix in inspector.get_indexes('sandboxed_tool_executions')}
    idx_name = 'ix_sandboxed_tool_executions_tenant_id'
    if idx_name in existing_idx:
        op.drop_index(idx_name, table_name='sandboxed_tool_executions')

    cols = [c['name'] for c in inspector.get_columns('sandboxed_tool_executions')]
    if 'tenant_id' in cols:
        op.drop_column('sandboxed_tool_executions', 'tenant_id')
