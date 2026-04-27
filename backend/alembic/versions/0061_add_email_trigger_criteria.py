"""Add shared criteria envelope to email triggers.

Revision ID: 0061
Revises: 0060
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0061"
down_revision: Union[str, None] = "0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("email_channel_instance", "trigger_criteria"):
        op.add_column("email_channel_instance", sa.Column("trigger_criteria", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("email_channel_instance", "trigger_criteria"):
        op.drop_column("email_channel_instance", "trigger_criteria")
