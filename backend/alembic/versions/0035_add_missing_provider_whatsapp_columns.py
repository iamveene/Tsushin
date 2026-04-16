"""Add missing columns: provider_instance.extra_config and whatsapp_mcp_instance.display_name

Two columns that exist on the SQLAlchemy models but were never backfilled into
a migration:

1. ``provider_instance.extra_config`` (JSON) — vendor-specific config such as
   vertex_ai project_id / region / service-account email. Model definition:
   ``backend/models.py:477``.
2. ``whatsapp_mcp_instance.display_name`` (String(100)) — optional human
   label for WhatsApp bot instances. Model definition:
   ``backend/models.py:2751``.

Both adds are guarded by ``Inspector.get_columns()`` so re-running against a
DB where a previous manual ALTER already added the column is a no-op. This
matches the idempotent pattern used in
``backend/alembic/versions/0006_add_provider_instances.py``.

Revision ID: 0035
Revises: 0034
Create Date: 2026-04-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0035'
down_revision: Union[str, None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('provider_instance'):
        existing_cols = [c['name'] for c in inspector.get_columns('provider_instance')]
        if 'extra_config' not in existing_cols:
            op.add_column(
                'provider_instance',
                sa.Column('extra_config', sa.JSON(), server_default='{}', nullable=True),
            )

    if inspector.has_table('whatsapp_mcp_instance'):
        existing_cols = [c['name'] for c in inspector.get_columns('whatsapp_mcp_instance')]
        if 'display_name' not in existing_cols:
            op.add_column(
                'whatsapp_mcp_instance',
                sa.Column('display_name', sa.String(length=100), nullable=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('whatsapp_mcp_instance'):
        existing_cols = [c['name'] for c in inspector.get_columns('whatsapp_mcp_instance')]
        if 'display_name' in existing_cols:
            op.drop_column('whatsapp_mcp_instance', 'display_name')

    if inspector.has_table('provider_instance'):
        existing_cols = [c['name'] for c in inspector.get_columns('provider_instance')]
        if 'extra_config' in existing_cols:
            op.drop_column('provider_instance', 'extra_config')
