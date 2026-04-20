"""Add allow_target_skills column to agent_communication_permission.

v0.7.2: Controls whether the target agent is allowed to use its own skills
(gmail, sandboxed_tools, shell, etc.) when invoked via A2A. Defaults to
False to preserve the previous "LLM-knowledge-only" behavior for every
existing row. The depth limit, rate limiting, permission check, and
Sentinel analysis still bound any skill activity, so enabling this is
safe for pairs where the source explicitly trusts the target to fetch
data on its behalf (e.g. delegating "check my email" to a mailbox-owner
agent).

Column is added with a server default so every existing row is backfilled
automatically by PostgreSQL.

Revision ID: 0040
Revises: 0039
Create Date: 2026-04-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0040'
down_revision: Union[str, None] = '0039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'agent_communication_permission' not in existing_tables:
        return

    cols = [c['name'] for c in inspector.get_columns('agent_communication_permission')]
    if 'allow_target_skills' in cols:
        return

    op.add_column(
        'agent_communication_permission',
        sa.Column(
            'allow_target_skills',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'agent_communication_permission' not in existing_tables:
        return

    cols = [c['name'] for c in inspector.get_columns('agent_communication_permission')]
    if 'allow_target_skills' not in cols:
        return

    op.drop_column('agent_communication_permission', 'allow_target_skills')
