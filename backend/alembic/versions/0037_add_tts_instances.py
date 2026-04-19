"""Add tts_instance table + config.default_tts_instance_id

Pulls forward the Kokoro TTS auto-provisioning schema from the v0.7.0 roadmap
(K1) into v0.6.0-patch.5. Mirrors the shape of VectorStoreInstance so tenants
can manage per-tenant Kokoro containers the same way they manage Qdrant /
MongoDB vector stores.

1. ``tts_instance`` — per-tenant TTS provider instances. ``vendor='kokoro'``
   is the only supported vendor in this release; ``speaches``/Whisper lands
   in v0.7.0. Container lifecycle columns mirror VectorStoreInstance.
2. ``config.default_tts_instance_id`` — tenant-wide default TTS instance FK
   (mirror of ``config.default_vector_store_instance_id``).

Both operations are idempotency-guarded via ``sa.inspect(bind)`` so re-running
against a DB where the schema was partially applied is a no-op.

Revision ID: 0037
Revises: 0035
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0037'
down_revision: Union[str, None] = '0036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('tts_instance'):
        op.create_table(
            'tts_instance',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(length=50), nullable=False, index=True),
            sa.Column('vendor', sa.String(length=20), nullable=False),
            sa.Column('instance_name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('base_url', sa.String(length=500), nullable=True),
            sa.Column('health_status', sa.String(length=20), nullable=False, server_default='unknown'),
            sa.Column('health_status_reason', sa.String(length=500), nullable=True),
            sa.Column('last_health_check', sa.DateTime(), nullable=True),
            sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('is_auto_provisioned', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('container_name', sa.String(length=200), nullable=True),
            sa.Column('container_id', sa.String(length=80), nullable=True),
            sa.Column('container_port', sa.Integer(), nullable=True),
            sa.Column('container_status', sa.String(length=20), nullable=False, server_default='none'),
            sa.Column('container_image', sa.String(length=200), nullable=True),
            sa.Column('volume_name', sa.String(length=150), nullable=True),
            sa.Column('mem_limit', sa.String(length=20), nullable=True),
            sa.Column('cpu_quota', sa.Integer(), nullable=True),
            sa.Column('default_voice', sa.String(length=50), nullable=True, server_default='pf_dora'),
            sa.Column('default_speed', sa.Float(), nullable=True, server_default='1.0'),
            sa.Column('default_language', sa.String(length=10), nullable=True, server_default='pt'),
            sa.Column('default_format', sa.String(length=10), nullable=True, server_default='opus'),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint('tenant_id', 'instance_name', name='uq_tts_instance_tenant_name'),
        )
        op.create_index('idx_tsi_tenant_vendor', 'tts_instance', ['tenant_id', 'vendor'])

    if inspector.has_table('config'):
        existing_cols = [c['name'] for c in inspector.get_columns('config')]
        if 'default_tts_instance_id' not in existing_cols:
            op.add_column(
                'config',
                sa.Column(
                    'default_tts_instance_id',
                    sa.Integer(),
                    sa.ForeignKey('tts_instance.id', ondelete='SET NULL'),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table('config'):
        existing_cols = [c['name'] for c in inspector.get_columns('config')]
        if 'default_tts_instance_id' in existing_cols:
            op.drop_column('config', 'default_tts_instance_id')

    if inspector.has_table('tts_instance'):
        # Index is dropped automatically when the table is dropped on PostgreSQL;
        # best-effort drop_index for other dialects.
        try:
            op.drop_index('idx_tsi_tenant_vendor', table_name='tts_instance')
        except Exception:
            pass
        op.drop_table('tts_instance')
