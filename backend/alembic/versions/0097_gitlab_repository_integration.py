"""add gitlab repository integration

Revision ID: 0097
Revises: 0096
Create Date: 2026-05-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0097"
down_revision: Union[str, None] = "0096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_table(name: str) -> bool:
    return name in _tables()


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _has_table("gitlab_integration"):
        op.create_table(
            "gitlab_integration",
            sa.Column("id", sa.Integer(), sa.ForeignKey("hub_integration.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="gitlab"),
            sa.Column("auth_method", sa.String(length=20), nullable=False, server_default="pat"),
            sa.Column("pat_token_encrypted", sa.Text(), nullable=True),
            sa.Column("pat_token_preview", sa.String(length=32), nullable=True),
            sa.Column("default_namespace", sa.String(length=255), nullable=True),
            sa.Column("default_project", sa.String(length=255), nullable=True),
            sa.Column("default_project_path", sa.String(length=500), nullable=True),
            sa.Column("provider_mode", sa.String(length=16), nullable=False, server_default="programmatic"),
        )

    if "idx_gitlab_integration_provider" not in _indexes("gitlab_integration"):
        op.create_index("idx_gitlab_integration_provider", "gitlab_integration", ["provider"])
    if "idx_gitlab_integration_default_project_path" not in _indexes("gitlab_integration"):
        op.create_index("idx_gitlab_integration_default_project_path", "gitlab_integration", ["default_project_path"])

    if not _has_table("gitlab_channel_instance"):
        op.create_table(
            "gitlab_channel_instance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
            sa.Column("integration_name", sa.String(length=100), nullable=False),
            sa.Column("gitlab_integration_id", sa.Integer(), sa.ForeignKey("gitlab_integration.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("project_path", sa.String(length=500), nullable=False),
            sa.Column("webhook_secret_encrypted", sa.Text(), nullable=True),
            sa.Column("webhook_secret_preview", sa.String(length=32), nullable=True),
            sa.Column("events", sa.JSON(), nullable=True),
            sa.Column("branch_filter", sa.String(length=255), nullable=True),
            sa.Column("path_filters", sa.JSON(), nullable=True),
            sa.Column("author_filter", sa.String(length=255), nullable=True),
            sa.Column("trigger_criteria", sa.JSON(), nullable=True),
            sa.Column("default_agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="SET NULL"), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("health_status", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("health_status_reason", sa.String(length=500), nullable=True),
            sa.Column("last_health_check", sa.DateTime(), nullable=True),
            sa.Column("last_activity_at", sa.DateTime(), nullable=True),
            sa.Column("last_cursor", sa.String(length=255), nullable=True),
            sa.Column("last_delivery_id", sa.String(length=128), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    indexes = _indexes("gitlab_channel_instance")
    if "idx_gitlab_channel_instance_tenant" not in indexes:
        op.create_index("idx_gitlab_channel_instance_tenant", "gitlab_channel_instance", ["tenant_id"])
    if "idx_gitlab_channel_instance_status" not in indexes:
        op.create_index("idx_gitlab_channel_instance_status", "gitlab_channel_instance", ["status"])
    if "idx_gitlab_channel_instance_project" not in indexes:
        op.create_index("idx_gitlab_channel_instance_project", "gitlab_channel_instance", ["tenant_id", "project_path"])
    if "idx_gitlab_channel_instance_default_agent_id" not in indexes:
        op.create_index("idx_gitlab_channel_instance_default_agent_id", "gitlab_channel_instance", ["default_agent_id"])
    if "idx_gitlab_channel_instance_gitlab_integration_id" not in indexes:
        op.create_index("idx_gitlab_channel_instance_gitlab_integration_id", "gitlab_channel_instance", ["gitlab_integration_id"])


def downgrade() -> None:
    if _has_table("gitlab_channel_instance"):
        for index_name in (
            "idx_gitlab_channel_instance_gitlab_integration_id",
            "idx_gitlab_channel_instance_default_agent_id",
            "idx_gitlab_channel_instance_project",
            "idx_gitlab_channel_instance_status",
            "idx_gitlab_channel_instance_tenant",
        ):
            if index_name in _indexes("gitlab_channel_instance"):
                op.drop_index(index_name, table_name="gitlab_channel_instance")
        op.drop_table("gitlab_channel_instance")

    if _has_table("gitlab_integration"):
        for index_name in (
            "idx_gitlab_integration_default_project_path",
            "idx_gitlab_integration_provider",
        ):
            if index_name in _indexes("gitlab_integration"):
                op.drop_index(index_name, table_name="gitlab_integration")
        op.drop_table("gitlab_integration")

    if _has_table("hub_integration"):
        op.execute("DELETE FROM hub_integration WHERE type = 'gitlab'")
