"""Add asr_instance table for Track D Whisper/Speaches instances.

Track D introduces per-tenant ASR instances that mirror the existing
Kokoro/SearXNG container lifecycle pattern while preserving the current
OpenAI Whisper transcription path as a fallback.

This migration:
1. Creates the `asr_instance` table for tenant-scoped Whisper/Speaches rows.
2. Stores runtime URL, encrypted API token, default model, and container
   metadata needed by the backend-only Track D checkpoint.

Idempotency is guarded via `sa.inspect(bind)` so partially-applied schemas
remain safe to re-run.

Revision ID: 0048
Revises: 0046
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0048"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("asr_instance"):
        op.create_table(
            "asr_instance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False, index=True),
            sa.Column("vendor", sa.String(length=20), nullable=False, server_default="speaches"),
            sa.Column("instance_name", sa.String(length=100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("base_url", sa.String(length=500), nullable=True),
            sa.Column("auth_username", sa.String(length=50), nullable=True, server_default="tsushin"),
            sa.Column("api_token_encrypted", sa.Text(), nullable=True),
            sa.Column(
                "default_model",
                sa.String(length=200),
                nullable=True,
                server_default="Systran/faster-distil-whisper-small.en",
            ),
            sa.Column("health_status", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("health_status_reason", sa.String(length=500), nullable=True),
            sa.Column("last_health_check", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_auto_provisioned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("container_name", sa.String(length=200), nullable=True),
            sa.Column("container_id", sa.String(length=80), nullable=True),
            sa.Column("container_port", sa.Integer(), nullable=True),
            sa.Column("container_status", sa.String(length=20), nullable=False, server_default="none"),
            sa.Column("container_image", sa.String(length=200), nullable=True),
            sa.Column("volume_name", sa.String(length=150), nullable=True),
            sa.Column("mem_limit", sa.String(length=20), nullable=True),
            sa.Column("cpu_quota", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint("tenant_id", "instance_name", name="uq_asr_instance_tenant_name"),
        )
        op.create_index("idx_asri_tenant_vendor", "asr_instance", ["tenant_id", "vendor"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("asr_instance"):
        try:
            op.drop_index("idx_asri_tenant_vendor", table_name="asr_instance")
        except Exception:
            pass
        op.drop_table("asr_instance")
