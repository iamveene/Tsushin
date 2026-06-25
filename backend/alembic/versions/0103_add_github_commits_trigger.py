"""Add GitHub commit-polling trigger table.

Creates ``github_commits_channel_instance`` — trigger config that polls a repo
branch's commits on an interval (REST), advancing a single ``last_seen_sha``
cursor and dispatching a notification-only flow on each new commit. Mirrors
``github_projects_channel_instance`` but, because commits on a branch are
linear, needs no per-item snapshot table (just the cursor).

Revision ID: 0103
Revises: 0102
Create Date: 2026-06-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0103"
down_revision: Union[str, None] = "0102"
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
    if not _has_table("github_commits_channel_instance"):
        op.create_table(
            "github_commits_channel_instance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False),
            sa.Column("integration_name", sa.String(length=100), nullable=False),
            sa.Column("github_integration_id", sa.Integer(), sa.ForeignKey("github_integration.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("repo_owner", sa.String(length=100), nullable=False),
            sa.Column("repo_name", sa.String(length=100), nullable=False),
            sa.Column("branch", sa.String(length=255), nullable=True),
            sa.Column("last_seen_sha", sa.String(length=64), nullable=True),
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

    ghc_indexes = _indexes("github_commits_channel_instance")
    for name, cols in (
        ("idx_ghc_channel_instance_tenant", ["tenant_id"]),
        ("idx_ghc_channel_instance_status", ["status"]),
        ("idx_ghc_channel_instance_default_agent_id", ["default_agent_id"]),
        ("idx_ghc_channel_instance_github_integration_id", ["github_integration_id"]),
        ("idx_ghc_channel_instance_repo", ["tenant_id", "repo_owner", "repo_name"]),
    ):
        if name not in ghc_indexes:
            op.create_index(name, "github_commits_channel_instance", cols)


def downgrade() -> None:
    if _has_table("github_commits_channel_instance"):
        for index_name in (
            "idx_ghc_channel_instance_repo",
            "idx_ghc_channel_instance_github_integration_id",
            "idx_ghc_channel_instance_default_agent_id",
            "idx_ghc_channel_instance_status",
            "idx_ghc_channel_instance_tenant",
        ):
            if index_name in _indexes("github_commits_channel_instance"):
                op.drop_index(index_name, table_name="github_commits_channel_instance")
        op.drop_table("github_commits_channel_instance")
