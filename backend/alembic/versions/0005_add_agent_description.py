"""Add description column to agent table.

The public API v1 previously derived `description` from the first line of
`system_prompt`.  This adds a dedicated nullable TEXT column so that
description can be set and updated independently.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add description column to agent table (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('agent')]
    if 'description' not in columns:
        op.add_column('agent', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove description column from agent table."""
    op.drop_column('agent', 'description')
