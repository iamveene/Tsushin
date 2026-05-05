"""drop schedule_channel_instance table (v0.7.0-fix Phase 2)

Schedule trigger was redundant with FlowDefinition.execution_method='scheduled'.
The user accepted destructive removal; pre-flight count showed 3 paused/test
rows on dev which were captured in the 2026-04-28 13:03:48 backup before this
migration.

Revision ID: 0071
Revises: 0070
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0071"
down_revision: Union[str, None] = "0070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "schedule_channel_instance" not in inspector.get_table_names():
        return

    # Drop indexes explicitly so a re-run is idempotent on Postgres versions
    # that don't auto-drop named indexes with the table.
    for index_name in (
        "idx_schedule_channel_instance_tenant",
        "idx_schedule_channel_instance_status",
        "idx_schedule_channel_instance_next_fire_at",
        "idx_schedule_channel_instance_default_agent_id",
    ):
        try:
            op.drop_index(index_name, table_name="schedule_channel_instance")
        except Exception:
            pass

    op.drop_table("schedule_channel_instance")


def downgrade() -> None:
    op.create_table(
        "schedule_channel_instance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
        sa.Column("integration_name", sa.String(length=100), nullable=False),
        sa.Column("cron_expression", sa.String(length=120), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("payload_template", sa.JSON(), nullable=True),
        sa.Column("trigger_criteria", sa.JSON(), nullable=True),
        sa.Column("default_agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("health_status", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("health_status_reason", sa.String(length=500), nullable=True),
        sa.Column("last_health_check", sa.DateTime(), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(), nullable=True),
        sa.Column("last_cursor", sa.String(length=255), nullable=True),
        sa.Column("next_fire_at", sa.DateTime(), nullable=True),
        sa.Column("last_fire_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("idx_schedule_channel_instance_tenant", "schedule_channel_instance", ["tenant_id"])
    op.create_index("idx_schedule_channel_instance_status", "schedule_channel_instance", ["status"])
    op.create_index("idx_schedule_channel_instance_next_fire_at", "schedule_channel_instance", ["next_fire_at"])
    op.create_index("idx_schedule_channel_instance_default_agent_id", "schedule_channel_instance", ["default_agent_id"])
