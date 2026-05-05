"""Widen Sentinel detection type fields.

Revision ID: 0055
Revises: 0054
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    for table_name in ("sentinel_analysis_log", "sentinel_analysis_cache"):
        if _has_column(table_name, "detection_type"):
            op.alter_column(
                table_name,
                "detection_type",
                existing_type=sa.String(length=30),
                type_=sa.String(length=64),
                existing_nullable=False,
            )


def downgrade() -> None:
    for table_name in ("sentinel_analysis_log", "sentinel_analysis_cache"):
        if _has_column(table_name, "detection_type"):
            if table_name == "sentinel_analysis_cache":
                op.execute(
                    sa.text(
                        "DELETE FROM sentinel_analysis_cache "
                        "WHERE char_length(detection_type) > 30"
                    )
                )
            else:
                op.execute(
                    sa.text(
                        "UPDATE sentinel_analysis_log "
                        "SET detection_type = left(detection_type, 30) "
                        "WHERE char_length(detection_type) > 30"
                    )
                )
            op.alter_column(
                table_name,
                "detection_type",
                existing_type=sa.String(length=64),
                type_=sa.String(length=30),
                existing_nullable=False,
            )
