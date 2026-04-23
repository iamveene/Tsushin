"""Add platform-wide agentic loop bounds.

Revision ID: 0057
Revises: 0049
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0057"
down_revision: Union[str, None] = "0049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing = _columns("config")
    if not existing:
        return
    if "platform_min_agentic_rounds" not in existing:
        op.add_column(
            "config",
            sa.Column("platform_min_agentic_rounds", sa.Integer(), nullable=True, server_default="1"),
        )
    if "platform_max_agentic_rounds" not in existing:
        op.add_column(
            "config",
            sa.Column("platform_max_agentic_rounds", sa.Integer(), nullable=True, server_default="8"),
        )


def downgrade() -> None:
    existing = _columns("config")
    if "platform_max_agentic_rounds" in existing:
        op.drop_column("config", "platform_max_agentic_rounds")
    if "platform_min_agentic_rounds" in existing:
        op.drop_column("config", "platform_min_agentic_rounds")
