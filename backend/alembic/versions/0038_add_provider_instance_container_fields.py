"""Add container lifecycle columns to provider_instance

Pulls forward Ollama auto-provisioning schema (O1) from the v0.7.0 roadmap
into v0.6.0-patch.5. Extends ``provider_instance`` with the same container
lifecycle columns present on ``vector_store_instance`` + ``tts_instance``,
plus Ollama-specific ``gpu_enabled`` and ``pulled_models`` fields.

All new columns are nullable or have safe defaults so existing rows
(e.g. host-Ollama tenants with ``is_auto_provisioned=false``) are unaffected.

Every column-add is guarded by ``Inspector.get_columns()``; re-running against
a DB where the columns already exist is a no-op. Mirrors the idempotent
idiom used throughout ``backend/alembic/versions/``.

Revision ID: 0038
Revises: 0037
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0038'
down_revision: Union[str, None] = '0037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_COLUMNS = [
    ('is_auto_provisioned', sa.Column('is_auto_provisioned', sa.Boolean(), nullable=False, server_default=sa.false())),
    ('container_name', sa.Column('container_name', sa.String(length=200), nullable=True)),
    ('container_id', sa.Column('container_id', sa.String(length=80), nullable=True)),
    ('container_port', sa.Column('container_port', sa.Integer(), nullable=True)),
    ('container_status', sa.Column('container_status', sa.String(length=20), nullable=False, server_default='none')),
    ('container_image', sa.Column('container_image', sa.String(length=200), nullable=True)),
    ('volume_name', sa.Column('volume_name', sa.String(length=150), nullable=True)),
    ('gpu_enabled', sa.Column('gpu_enabled', sa.Boolean(), nullable=False, server_default=sa.false())),
    ('pulled_models', sa.Column('pulled_models', sa.JSON(), nullable=True, server_default='[]')),
    ('mem_limit', sa.Column('mem_limit', sa.String(length=20), nullable=True)),
    ('cpu_quota', sa.Column('cpu_quota', sa.Integer(), nullable=True)),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('provider_instance'):
        return

    existing_cols = {c['name'] for c in inspector.get_columns('provider_instance')}
    for col_name, col_def in NEW_COLUMNS:
        if col_name not in existing_cols:
            op.add_column('provider_instance', col_def)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('provider_instance'):
        return

    existing_cols = {c['name'] for c in inspector.get_columns('provider_instance')}
    for col_name, _ in reversed(NEW_COLUMNS):
        if col_name in existing_cols:
            op.drop_column('provider_instance', col_name)
