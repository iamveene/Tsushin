"""Drop unused agent_team.tools_json column.

The team-level "shared tools" pool was stored in this JSON column but never
read at runtime — agents resolve their sandboxed tools from per-agent and
per-persona configuration. Removing the dead column.

Revision ID: 0091
Revises: 0090
Create Date: 2026-05-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0091"
down_revision: Union[str, None] = "0090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "tools_json" in _columns("agent_team"):
        op.drop_column("agent_team", "tools_json")


def downgrade() -> None:
    if "tools_json" not in _columns("agent_team"):
        op.add_column("agent_team", sa.Column("tools_json", sa.JSON(), nullable=True))
