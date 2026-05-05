"""Drop tenant.default_asr_instance_id (retire tenant-level ASR default).

Revision ID: 0078
Revises: 0077
Create Date: 2026-05-02

v0.7.0 RC — the tenant-level ASR default concept is retired. ASR instances
are assigned per agent via ``audio_transcript.config.asr_instance_id``. The
``/settings/asr`` page (which surfaced the "tenant default ASR backend"
dropdown) is gone; tenants create ASR instances in the Hub Provider Wizard
and pin them per-agent in the Audio Agents Wizard / Agent Skills Manager.

Downgrade re-adds the nullable column with the same FK-cascade shape, but
no rows are repopulated — once the column is dropped, the prior tenant-default
selection is intentionally lost.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0078"
down_revision: Union[str, None] = "0077"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("tenant")}

    if "default_asr_instance_id" in existing_cols:
        # Drop the FK constraint first if it exists (idempotent). On Postgres
        # the constraint name is auto-generated; reflection picks it up.
        for fk in inspector.get_foreign_keys("tenant"):
            if fk.get("referred_table") == "asr_instance" and "default_asr_instance_id" in (fk.get("constrained_columns") or []):
                if fk.get("name"):
                    op.drop_constraint(fk["name"], "tenant", type_="foreignkey")
                break
        op.drop_column("tenant", "default_asr_instance_id")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_cols = {c["name"] for c in inspector.get_columns("tenant")}

    if "default_asr_instance_id" not in existing_cols:
        op.add_column(
            "tenant",
            sa.Column(
                "default_asr_instance_id",
                sa.Integer(),
                nullable=True,
            ),
        )
        op.create_foreign_key(
            "tenant_default_asr_instance_id_fkey",
            "tenant",
            "asr_instance",
            ["default_asr_instance_id"],
            ["id"],
            ondelete="SET NULL",
        )
