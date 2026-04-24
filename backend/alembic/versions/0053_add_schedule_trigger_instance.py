"""Add schedule trigger instance.

Revision ID: 0053
Revises: 0052
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0053"
down_revision: Union[str, None] = "0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "schedule_channel_instance" not in inspector.get_table_names():
        op.create_table(
            "schedule_channel_instance",
            sa.Column("id", sa.Integer(), primary_key=True),
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
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    indexes = _indexes("schedule_channel_instance")
    if "idx_schedule_channel_instance_tenant" not in indexes:
        op.create_index("idx_schedule_channel_instance_tenant", "schedule_channel_instance", ["tenant_id"])
    if "idx_schedule_channel_instance_status" not in indexes:
        op.create_index("idx_schedule_channel_instance_status", "schedule_channel_instance", ["status"])
    if "idx_schedule_channel_instance_next_fire_at" not in indexes:
        op.create_index("idx_schedule_channel_instance_next_fire_at", "schedule_channel_instance", ["next_fire_at"])
    if "idx_schedule_channel_instance_default_agent_id" not in indexes:
        op.create_index("idx_schedule_channel_instance_default_agent_id", "schedule_channel_instance", ["default_agent_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "schedule_channel_instance" not in inspector.get_table_names():
        return
    for index_name in (
        "idx_schedule_channel_instance_default_agent_id",
        "idx_schedule_channel_instance_next_fire_at",
        "idx_schedule_channel_instance_status",
        "idx_schedule_channel_instance_tenant",
    ):
        if index_name in _indexes("schedule_channel_instance"):
            op.drop_index(index_name, table_name="schedule_channel_instance")
    op.drop_table("schedule_channel_instance")
