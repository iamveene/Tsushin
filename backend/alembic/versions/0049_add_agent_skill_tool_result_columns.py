"""Add agentic loop scratchpad and agent-skill tool-result controls.

Revision ID: 0049
Revises: 0050
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0049"
down_revision: Union[str, None] = "0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TOOL_RESULT_COLUMNS = {
    "auto_inject_results": sa.Column("auto_inject_results", sa.Boolean(), nullable=True, server_default=sa.true()),
    "skip_ai_on_data_fetch": sa.Column("skip_ai_on_data_fetch", sa.Boolean(), nullable=True, server_default=sa.false()),
    "max_result_bytes": sa.Column("max_result_bytes", sa.Integer(), nullable=True, server_default="2048"),
    "max_results_retained": sa.Column("max_results_retained", sa.Integer(), nullable=True, server_default="2"),
    "max_turns_lookback": sa.Column("max_turns_lookback", sa.Integer(), nullable=True, server_default="6"),
}


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_name in _tables() and column.name not in _columns(table_name):
        op.add_column(table_name, column.copy())


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if table_name in _tables() and column_name in _columns(table_name):
        op.drop_column(table_name, column_name)


def _migrate_legacy_config_keys() -> None:
    """Copy legacy JSON config keys into typed columns, then remove the keys."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    existing = _columns("agent_skill")
    if "config" not in existing:
        return

    for column_name in TOOL_RESULT_COLUMNS:
        if column_name not in existing:
            continue
        bind.execute(sa.text(f"""
            UPDATE agent_skill
            SET {column_name} = (config ->> :key)::boolean
            WHERE config::jsonb ? :key
              AND (config ->> :key) IN ('true', 'false')
              AND :key IN ('auto_inject_results', 'skip_ai_on_data_fetch')
        """), {"key": column_name})
        bind.execute(sa.text(f"""
            UPDATE agent_skill
            SET {column_name} = (config ->> :key)::integer
            WHERE config::jsonb ? :key
              AND (config ->> :key) ~ '^[0-9]+$'
              AND :key IN ('max_result_bytes', 'max_results_retained', 'max_turns_lookback')
        """), {"key": column_name})
        bind.execute(sa.text("""
            UPDATE agent_skill
            SET config = config::jsonb - :key
            WHERE config::jsonb ? :key
        """), {"key": column_name})


def upgrade() -> None:
    if "conversation_thread" in _tables() and "agentic_scratchpad" not in _columns("conversation_thread"):
        op.add_column("conversation_thread", sa.Column("agentic_scratchpad", JSONB(), nullable=True))

    for column in TOOL_RESULT_COLUMNS.values():
        _add_column_if_missing("agent_skill", column)

    _migrate_legacy_config_keys()


def downgrade() -> None:
    for column_name in reversed(tuple(TOOL_RESULT_COLUMNS.keys())):
        _drop_column_if_exists("agent_skill", column_name)
    _drop_column_if_exists("conversation_thread", "agentic_scratchpad")
