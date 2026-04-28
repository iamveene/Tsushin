"""github trigger requires Hub integration link (v0.7.0-fix Phase 3)

Adds `github_channel_instance.github_integration_id` FK and drops the
per-trigger credential columns (`auth_method`, `installation_id`,
`pat_token_encrypted`, `pat_token_preview`). Pre-flight DB had 0 rows so
backfill is a no-op; for environments with pre-existing rows the upgrade
fails fast with a clear message — operators must create a tenant
GitHubIntegration and re-run.

Revision ID: 0072
Revises: 0071
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0072"
down_revision: Union[str, None] = "0071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "github_channel_instance" not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns("github_channel_instance")}

    # If any rows exist, refuse to migrate — operators must reconcile manually.
    row_count = bind.execute(sa.text("SELECT count(*) FROM github_channel_instance")).scalar() or 0
    if row_count and "github_integration_id" not in existing_cols:
        raise RuntimeError(
            f"Cannot migrate {row_count} GitHub trigger rows: per-trigger PAT was "
            "removed in v0.7.0-fix Phase 3. Create a Hub GitHubIntegration "
            "(POST /api/hub/github-integrations) and update each trigger to "
            "reference it before re-running this migration."
        )

    # Add nullable FK first so we can index it; flip to NOT NULL afterwards
    # because the table is empty in every environment we care about.
    if "github_integration_id" not in existing_cols:
        op.add_column(
            "github_channel_instance",
            sa.Column(
                "github_integration_id",
                sa.Integer(),
                sa.ForeignKey("github_integration.id", ondelete="RESTRICT"),
                nullable=True,
            ),
        )
        op.create_index(
            "idx_github_channel_instance_github_integration_id",
            "github_channel_instance",
            ["github_integration_id"],
        )
        op.alter_column(
            "github_channel_instance",
            "github_integration_id",
            existing_type=sa.Integer(),
            nullable=False,
        )

    for col in ("pat_token_encrypted", "pat_token_preview", "auth_method", "installation_id"):
        if col in existing_cols:
            op.drop_column("github_channel_instance", col)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "github_channel_instance" not in inspector.get_table_names():
        return

    existing_cols = {c["name"] for c in inspector.get_columns("github_channel_instance")}
    if "auth_method" not in existing_cols:
        op.add_column(
            "github_channel_instance",
            sa.Column("auth_method", sa.String(length=20), nullable=False, server_default="pat"),
        )
    if "installation_id" not in existing_cols:
        op.add_column(
            "github_channel_instance",
            sa.Column("installation_id", sa.String(length=64), nullable=True),
        )
    if "pat_token_encrypted" not in existing_cols:
        op.add_column(
            "github_channel_instance",
            sa.Column("pat_token_encrypted", sa.Text(), nullable=True),
        )
    if "pat_token_preview" not in existing_cols:
        op.add_column(
            "github_channel_instance",
            sa.Column("pat_token_preview", sa.String(length=32), nullable=True),
        )

    if "github_integration_id" in {c["name"] for c in inspector.get_columns("github_channel_instance")}:
        try:
            op.drop_index("idx_github_channel_instance_github_integration_id", table_name="github_channel_instance")
        except Exception:
            pass
        op.drop_column("github_channel_instance", "github_integration_id")
