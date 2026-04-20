"""Add emergency_stop column to tenant.

v0.7.3: The existing emergency-stop kill switch lived on the singleton
``config`` row, which made it a global flag even though tenant owners
could toggle it via /api/system/emergency-stop. This migration introduces
a per-tenant column so each tenant owner can halt only their own
traffic, while the existing ``config.emergency_stop`` becomes the
admin-only GLOBAL kill switch.

Column is added with a server default so every existing row is
backfilled automatically by PostgreSQL.

Revision ID: 0041
Revises: 0040
Create Date: 2026-04-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0041'
down_revision: Union[str, None] = '0040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'tenant' not in existing_tables:
        return

    cols = [c['name'] for c in inspector.get_columns('tenant')]
    if 'emergency_stop' in cols:
        return

    op.add_column(
        'tenant',
        sa.Column(
            'emergency_stop',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'tenant' not in existing_tables:
        return

    cols = [c['name'] for c in inspector.get_columns('tenant')]
    if 'emergency_stop' not in cols:
        return

    op.drop_column('tenant', 'emergency_stop')
