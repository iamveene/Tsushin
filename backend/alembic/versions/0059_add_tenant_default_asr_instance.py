"""Add tenant.default_asr_instance_id for Track D ASR defaults.

Track D needs a tenant-scoped default ASR target so new agent flows can use a
local Speaches/Whisper instance by default while preserving OpenAI Whisper as
the null/default fallback.

This migration:
1. Adds ``tenant.default_asr_instance_id`` with ``ON DELETE SET NULL`` to the
   existing ``asr_instance`` table introduced by revision 0048.

Idempotency is guarded via ``sa.inspect(bind)`` so partially-applied schemas
remain safe to re-run.

Revision choice: Track F owns ``0049`` and other v0.7.0 tracks occupy the
intermediate pending slots. Track D intentionally uses ``0059`` and targets
Track A's ``0051`` so root integration can merge this after Track A without
creating an Alembic multi-head.

Revision ID: 0059
Revises: 0051
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0059"
down_revision: Union[str, None] = "0051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("tenant") and inspector.has_table("asr_instance"):
        existing_cols = [c["name"] for c in inspector.get_columns("tenant")]
        if "default_asr_instance_id" not in existing_cols:
            op.add_column(
                "tenant",
                sa.Column(
                    "default_asr_instance_id",
                    sa.Integer(),
                    sa.ForeignKey("asr_instance.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("tenant"):
        existing_cols = [c["name"] for c in inspector.get_columns("tenant")]
        if "default_asr_instance_id" in existing_cols:
            op.drop_column("tenant", "default_asr_instance_id")
