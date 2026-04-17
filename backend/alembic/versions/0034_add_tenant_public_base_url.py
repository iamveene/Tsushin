"""Add tenant.public_base_url for Slack HTTP / Discord Interactions setup hints.

Tenants that integrate Slack (HTTP Events mode) or Discord (Interactions endpoint)
need to paste a publicly-reachable HTTPS URL into the third-party portal. This
column lets each tenant configure their own public base URL so the Tsushin UI can
render the exact webhook/interactions URL with a copy button instead of relying on
the user to assemble it manually.

Nullable on purpose — when unset, the UI shows a "configure first" warning.

Revision ID: 0034
Revises: 0033
"""
revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tenant")}
    if "public_base_url" not in cols:
        op.add_column(
            "tenant",
            sa.Column("public_base_url", sa.String(length=512), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("tenant")}
    if "public_base_url" in cols:
        op.drop_column("tenant", "public_base_url")
