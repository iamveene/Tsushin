"""Add per-agent timezone column.

Adds ``agent.timezone`` (nullable IANA timezone string, e.g. "America/Sao_Paulo").
NULL means "use the system default" (``constants.agent_config.DEFAULT_AGENT_TIMEZONE``).
This drives the agent's injected "current time" and relative-reminder parsing so
scheduling is computed in the agent's local zone instead of the container's UTC —
the root cause of reminders landing ~3 hours late.

Additive, nullable column with no server_default → metadata-only on PostgreSQL
(no table rewrite), safe on the multi-tenant ``agent`` table.

Revision ID: 0104
Revises: 0103
Create Date: 2026-07-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0104"
down_revision: Union[str, None] = "0103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _has_column("agent", "timezone"):
        op.add_column("agent", sa.Column("timezone", sa.String(length=50), nullable=True))


def downgrade() -> None:
    if _has_column("agent", "timezone"):
        op.drop_column("agent", "timezone")
