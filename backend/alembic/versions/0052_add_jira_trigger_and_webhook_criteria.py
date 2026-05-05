"""Add Jira trigger instance and webhook criteria.

Revision ID: 0052
Revises: 0058
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0052"
down_revision: Union[str, None] = "0058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "webhook_integration" in inspector.get_table_names():
        webhook_columns = _columns("webhook_integration")
        if "trigger_criteria" not in webhook_columns:
            op.add_column("webhook_integration", sa.Column("trigger_criteria", sa.JSON(), nullable=True))

    if "jira_channel_instance" not in inspector.get_table_names():
        op.create_table(
            "jira_channel_instance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
            sa.Column("integration_name", sa.String(length=100), nullable=False),
            sa.Column("site_url", sa.String(length=500), nullable=False),
            sa.Column("project_key", sa.String(length=64), nullable=True),
            sa.Column("jql", sa.Text(), nullable=False),
            sa.Column("auth_email", sa.String(length=255), nullable=True),
            sa.Column("api_token_encrypted", sa.Text(), nullable=True),
            sa.Column("api_token_preview", sa.String(length=32), nullable=True),
            sa.Column("trigger_criteria", sa.JSON(), nullable=True),
            sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
            sa.Column("default_agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="SET NULL"), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("health_status", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("health_status_reason", sa.String(length=500), nullable=True),
            sa.Column("last_health_check", sa.DateTime(), nullable=True),
            sa.Column("last_activity_at", sa.DateTime(), nullable=True),
            sa.Column("last_cursor", sa.String(length=255), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    indexes = _indexes("jira_channel_instance")
    if "idx_jira_channel_instance_tenant" not in indexes:
        op.create_index("idx_jira_channel_instance_tenant", "jira_channel_instance", ["tenant_id"])
    if "idx_jira_channel_instance_status" not in indexes:
        op.create_index("idx_jira_channel_instance_status", "jira_channel_instance", ["status"])
    if "idx_jira_channel_instance_default_agent_id" not in indexes:
        op.create_index("idx_jira_channel_instance_default_agent_id", "jira_channel_instance", ["default_agent_id"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "jira_channel_instance" in inspector.get_table_names():
        for index_name in (
            "idx_jira_channel_instance_default_agent_id",
            "idx_jira_channel_instance_status",
            "idx_jira_channel_instance_tenant",
        ):
            if index_name in _indexes("jira_channel_instance"):
                op.drop_index(index_name, table_name="jira_channel_instance")
        op.drop_table("jira_channel_instance")

    if "webhook_integration" in inspector.get_table_names() and "trigger_criteria" in _columns("webhook_integration"):
        op.drop_column("webhook_integration", "trigger_criteria")
