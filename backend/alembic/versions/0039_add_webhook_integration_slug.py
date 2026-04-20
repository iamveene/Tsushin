"""Add slug column to webhook_integration.

v0.7.1: Webhook URIs become human-readable. A new ``slug`` column stores a
globally-unique identifier used in the inbound path
``/api/webhooks/{slug}/inbound``. Existing rows are backfilled to
``wh-{id}`` so every currently-deployed URL keeps resolving (via the
slug match) in addition to the numeric-id backward-compat fallback in
the receiver route.

Column is added nullable, backfilled, then set NOT NULL + UNIQUE so the
migration is safe against any existing data.

Revision ID: 0039
Revises: 0038
Create Date: 2026-04-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0039'
down_revision: Union[str, None] = '0038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'webhook_integration' not in existing_tables:
        return

    cols = [c['name'] for c in inspector.get_columns('webhook_integration')]
    if 'slug' in cols:
        return

    # 1) add nullable so the ALTER succeeds on a populated table
    op.add_column(
        'webhook_integration',
        sa.Column('slug', sa.String(64), nullable=True),
    )

    # 2) backfill: slug = 'wh-' || id
    op.execute(
        "UPDATE webhook_integration SET slug = 'wh-' || id WHERE slug IS NULL"
    )

    # 3) enforce NOT NULL and uniqueness
    op.alter_column('webhook_integration', 'slug', nullable=False)
    op.create_index(
        'ix_webhook_integration_slug',
        'webhook_integration',
        ['slug'],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'webhook_integration' not in existing_tables:
        return

    cols = [c['name'] for c in inspector.get_columns('webhook_integration')]
    if 'slug' not in cols:
        return

    indexes = [ix['name'] for ix in inspector.get_indexes('webhook_integration')]
    if 'ix_webhook_integration_slug' in indexes:
        op.drop_index('ix_webhook_integration_slug', table_name='webhook_integration')

    op.drop_column('webhook_integration', 'slug')
