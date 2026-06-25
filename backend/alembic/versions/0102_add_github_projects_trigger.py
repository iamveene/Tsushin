"""Add GitHub Projects v2 polling trigger + per-item snapshot tables.

Creates:
  - ``github_projects_channel_instance`` — trigger config (mirrors
    ``jira_channel_instance``; polls the Projects v2 GraphQL API on an interval).
  - ``github_projects_item_state`` — per-item snapshot used to diff board state
    between polls (detects new card / assignment / Status move).

Revision ID: 0102
Revises: 0101
Create Date: 2026-06-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0102"
down_revision: Union[str, None] = "0101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _has_table("github_projects_channel_instance"):
        op.create_table(
            "github_projects_channel_instance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
            sa.Column("integration_name", sa.String(length=100), nullable=False),
            sa.Column("github_integration_id", sa.Integer(), sa.ForeignKey("github_integration.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("project_owner", sa.String(length=100), nullable=False),
            sa.Column("project_number", sa.Integer(), nullable=False),
            sa.Column("project_node_id", sa.String(length=64), nullable=True),
            sa.Column("project_name", sa.String(length=255), nullable=True),
            sa.Column("trigger_criteria", sa.JSON(), nullable=True),
            sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="300"),
            sa.Column("default_agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="SET NULL"), nullable=True),
            sa.Column("notify_recipient_raw", sa.String(length=100), nullable=True),
            sa.Column("notification_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("health_status", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("health_status_reason", sa.String(length=500), nullable=True),
            sa.Column("last_health_check", sa.DateTime(), nullable=True),
            sa.Column("last_activity_at", sa.DateTime(), nullable=True),
            sa.Column("seeded_at", sa.DateTime(), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    ghp_indexes = _indexes("github_projects_channel_instance")
    for name, cols in (
        ("idx_ghp_channel_instance_tenant", ["tenant_id"]),
        ("idx_ghp_channel_instance_status", ["status"]),
        ("idx_ghp_channel_instance_default_agent_id", ["default_agent_id"]),
        ("idx_ghp_channel_instance_github_integration_id", ["github_integration_id"]),
        ("idx_ghp_channel_instance_project", ["tenant_id", "project_owner", "project_number"]),
    ):
        if name not in ghp_indexes:
            op.create_index(name, "github_projects_channel_instance", cols)

    if not _has_table("github_projects_item_state"):
        op.create_table(
            "github_projects_item_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("instance_id", sa.Integer(), sa.ForeignKey("github_projects_channel_instance.id", ondelete="CASCADE"), nullable=False),
            sa.Column("item_node_id", sa.String(length=64), nullable=False),
            sa.Column("content_type", sa.String(length=20), nullable=True),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("url", sa.Text(), nullable=True),
            sa.Column("status_value", sa.String(length=255), nullable=True),
            sa.Column("assignees_json", sa.JSON(), nullable=True),
            sa.Column("last_updated_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("instance_id", "item_node_id", name="uq_ghp_item_state_instance_item"),
        )

    state_indexes = _indexes("github_projects_item_state")
    if "idx_ghp_item_state_instance" not in state_indexes:
        op.create_index("idx_ghp_item_state_instance", "github_projects_item_state", ["instance_id"])


def downgrade() -> None:
    if _has_table("github_projects_item_state"):
        if "idx_ghp_item_state_instance" in _indexes("github_projects_item_state"):
            op.drop_index("idx_ghp_item_state_instance", table_name="github_projects_item_state")
        op.drop_table("github_projects_item_state")

    if _has_table("github_projects_channel_instance"):
        for index_name in (
            "idx_ghp_channel_instance_project",
            "idx_ghp_channel_instance_github_integration_id",
            "idx_ghp_channel_instance_default_agent_id",
            "idx_ghp_channel_instance_status",
            "idx_ghp_channel_instance_tenant",
        ):
            if index_name in _indexes("github_projects_channel_instance"):
                op.drop_index(index_name, table_name="github_projects_channel_instance")
        op.drop_table("github_projects_channel_instance")
