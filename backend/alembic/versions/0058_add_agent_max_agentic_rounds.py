"""Add per-agent agentic loop limits.

Revision ID: 0058
Revises: 0057
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0058"
down_revision: Union[str, None] = "0057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    existing = _columns("agent")
    if not existing:
        return
    if "max_agentic_rounds" not in existing:
        op.add_column(
            "agent",
            sa.Column("max_agentic_rounds", sa.Integer(), nullable=True, server_default="1"),
        )
    if "max_agentic_loop_bytes" not in existing:
        op.add_column(
            "agent",
            sa.Column("max_agentic_loop_bytes", sa.Integer(), nullable=True, server_default="8192"),
        )


def downgrade() -> None:
    existing = _columns("agent")
    if "max_agentic_loop_bytes" in existing:
        op.drop_column("agent", "max_agentic_loop_bytes")
    if "max_agentic_rounds" in existing:
        op.drop_column("agent", "max_agentic_rounds")
