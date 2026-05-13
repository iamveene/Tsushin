"""Add GitHub Hub Integration table.

Revision ID: 0065
Revises: 0064
Create Date: 2026-04-25

Adds the ``github_integration`` table — a polymorphic subclass of
``hub_integration`` that stores tenant-scoped GitHub connection settings
(PAT today, GitHub App reserved for the future). Mirrors the shape of the
``jira_integration`` table introduced in 0062 so the agent runtime can pull
PR/issue data via the REST API the same way it queries Jira.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0065"
down_revision: Union[str, None] = "0064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_table(table_name: str) -> bool:
    return table_name in _table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _has_table("github_integration"):
        op.create_table(
            "github_integration",
            sa.Column(
                "id",
                sa.Integer(),
                sa.ForeignKey("hub_integration.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="github"),
            sa.Column("auth_method", sa.String(length=20), nullable=False, server_default="pat"),
            sa.Column("pat_token_encrypted", sa.Text(), nullable=True),
            sa.Column("pat_token_preview", sa.String(length=32), nullable=True),
            sa.Column("default_owner", sa.String(length=100), nullable=True),
            sa.Column("default_repo", sa.String(length=100), nullable=True),
            sa.Column(
                "provider_mode",
                sa.String(length=16),
                nullable=False,
                server_default="programmatic",
            ),
        )
    else:
        # Idempotent: add any missing columns on pre-existing tables.
        if not _has_column("github_integration", "provider"):
            op.add_column(
                "github_integration",
                sa.Column("provider", sa.String(length=32), nullable=False, server_default="github"),
            )
        if not _has_column("github_integration", "auth_method"):
            op.add_column(
                "github_integration",
                sa.Column("auth_method", sa.String(length=20), nullable=False, server_default="pat"),
            )
        if not _has_column("github_integration", "pat_token_encrypted"):
            op.add_column("github_integration", sa.Column("pat_token_encrypted", sa.Text(), nullable=True))
        if not _has_column("github_integration", "pat_token_preview"):
            op.add_column("github_integration", sa.Column("pat_token_preview", sa.String(length=32), nullable=True))
        if not _has_column("github_integration", "default_owner"):
            op.add_column("github_integration", sa.Column("default_owner", sa.String(length=100), nullable=True))
        if not _has_column("github_integration", "default_repo"):
            op.add_column("github_integration", sa.Column("default_repo", sa.String(length=100), nullable=True))
        if not _has_column("github_integration", "provider_mode"):
            op.add_column(
                "github_integration",
                sa.Column(
                    "provider_mode",
                    sa.String(length=16),
                    nullable=False,
                    server_default="programmatic",
                ),
            )

    # Belt-and-suspenders backfill — server_default covers new rows but some
    # engines (notably older SQLite) won't apply defaults to rows inserted in
    # the same migration transaction.
    op.execute("UPDATE github_integration SET provider = 'github' WHERE provider IS NULL")
    op.execute("UPDATE github_integration SET auth_method = 'pat' WHERE auth_method IS NULL")
    op.execute("UPDATE github_integration SET provider_mode = 'programmatic' WHERE provider_mode IS NULL")

    if "idx_github_integration_provider" not in _indexes("github_integration"):
        op.create_index("idx_github_integration_provider", "github_integration", ["provider"])
    if "idx_github_integration_default_owner" not in _indexes("github_integration"):
        op.create_index("idx_github_integration_default_owner", "github_integration", ["default_owner"])


def downgrade() -> None:
    if _has_table("github_integration"):
        for index_name in (
            "idx_github_integration_default_owner",
            "idx_github_integration_provider",
        ):
            if index_name in _indexes("github_integration"):
                op.drop_index(index_name, table_name="github_integration")
        op.drop_table("github_integration")

    if _has_table("hub_integration"):
        op.execute("DELETE FROM hub_integration WHERE type = 'github'")
