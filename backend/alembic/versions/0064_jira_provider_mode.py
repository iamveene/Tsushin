"""Add provider_mode to jira_integration.

Revision ID: 0064
Revises: 0063
Create Date: 2026-04-25

Adds a `provider_mode` column to jira_integration so the Hub UI can
distinguish between Programmatic (REST API, default) and Agentic
(Atlassian Remote MCP, coming soon) connection modes. Existing rows
are backfilled to 'programmatic'.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0064"
down_revision: Union[str, None] = "0063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("jira_integration", "provider_mode"):
        op.add_column(
            "jira_integration",
            sa.Column(
                "provider_mode",
                sa.String(length=16),
                nullable=False,
                server_default="programmatic",
            ),
        )
        # Backfill any pre-existing NULLs (server_default applies to new rows;
        # this is belt-and-suspenders for rows inserted in the same transaction
        # as the schema change on certain DB engines).
        op.execute("UPDATE jira_integration SET provider_mode = 'programmatic' WHERE provider_mode IS NULL")


def downgrade() -> None:
    if _has_column("jira_integration", "provider_mode"):
        op.drop_column("jira_integration", "provider_mode")
