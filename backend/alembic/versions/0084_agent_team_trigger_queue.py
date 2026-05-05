"""Agent Teams trigger queue substrate.

Revision ID: 0084
Revises: 0083
Create Date: 2026-05-05

Adds team-owned queue metadata so trigger dispatch can enqueue
``message_queue.message_type='team_run'`` rows without binding them to a
single agent. Existing agent queue rows remain agent-keyed.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0084"
down_revision: Union[str, None] = "0083"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_TYPES = (
    "inbound_message",
    "trigger_event",
    "continuous_task",
    "flow_run_triggered",
    "case_index",
)
_NEW_TYPES = (*_OLD_TYPES, "team_run")


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(col["name"] == column_name for col in _inspector().get_columns(table_name))


def _index_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {idx["name"] for idx in _inspector().get_indexes(table_name)}


def _fk_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {fk["name"] for fk in _inspector().get_foreign_keys(table_name) if fk.get("name")}


def _constraint_exists(table: str, name: str, constraint_type: str = "CHECK") -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE table_name = :tbl AND constraint_name = :name "
                "AND constraint_type = :constraint_type"
            ),
            {"tbl": table, "name": name, "constraint_type": constraint_type},
        ).first()
    )


def _types_csv(types: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in types)


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and name not in _index_names(table_name):
        op.create_index(name, table_name, columns)


def _drop_index_if_exists(name: str, table_name: str) -> None:
    if _has_table(table_name) and name in _index_names(table_name):
        op.drop_index(name, table_name=table_name)


def _create_fk_if_missing(
    name: str,
    source_table: str,
    referent_table: str,
    local_cols: list[str],
    remote_cols: list[str],
    *,
    ondelete: str | None = None,
) -> None:
    if _has_table(source_table) and name not in _fk_names(source_table):
        op.create_foreign_key(
            name,
            source_table,
            referent_table,
            local_cols,
            remote_cols,
            ondelete=ondelete,
        )


def _drop_fk_if_exists(name: str, table_name: str) -> None:
    if _has_table(table_name) and name in _fk_names(table_name):
        op.drop_constraint(name, table_name, type_="foreignkey")


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def _set_agent_id_nullable(nullable: bool) -> None:
    if _has_table("message_queue") and _has_column("message_queue", "agent_id"):
        op.alter_column(
            "message_queue",
            "agent_id",
            existing_type=sa.Integer(),
            nullable=nullable,
        )


def _replace_message_type_check(types: tuple[str, ...]) -> None:
    if not _has_table("message_queue"):
        return
    if _constraint_exists("message_queue", "ck_message_queue_message_type"):
        op.drop_constraint(
            "ck_message_queue_message_type",
            "message_queue",
            type_="check",
        )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_message_queue_message_type",
            "message_queue",
            f"message_type IN ({_types_csv(types)})",
        )


def _create_agent_or_team_check() -> None:
    if op.get_bind().dialect.name != "postgresql" or not _has_table("message_queue"):
        return
    if not _constraint_exists("message_queue", "ck_mq_agent_or_team_run"):
        op.create_check_constraint(
            "ck_mq_agent_or_team_run",
            "message_queue",
            "((message_type = 'team_run' AND agent_id IS NULL AND team_id IS NOT NULL AND team_run_id IS NOT NULL) "
            "OR (message_type != 'team_run' AND agent_id IS NOT NULL))",
        )


def _drop_agent_or_team_check() -> None:
    if _constraint_exists("message_queue", "ck_mq_agent_or_team_run"):
        op.drop_constraint("ck_mq_agent_or_team_run", "message_queue", type_="check")


def upgrade() -> None:
    if not _has_table("message_queue"):
        return

    _add_column_if_missing("message_queue", sa.Column("team_id", sa.Integer(), nullable=True))
    _add_column_if_missing("message_queue", sa.Column("team_run_id", sa.Integer(), nullable=True))
    _set_agent_id_nullable(True)

    _create_index_if_missing("ix_mq_team_id", "message_queue", ["team_id"])
    _create_index_if_missing("ix_mq_team_run_id", "message_queue", ["team_run_id"])
    _create_index_if_missing("ix_mq_tenant_team_status", "message_queue", ["tenant_id", "team_id", "status"])

    _drop_fk_if_exists("fk_mq_team_id_agent_team", "message_queue")
    _drop_fk_if_exists("fk_mq_team_run_id_agent_team_run", "message_queue")
    _create_fk_if_missing(
        "fk_mq_tenant_team",
        "message_queue",
        "agent_team",
        ["tenant_id", "team_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    _create_fk_if_missing(
        "fk_mq_tenant_team_run",
        "message_queue",
        "agent_team_run",
        ["tenant_id", "team_run_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )

    _replace_message_type_check(_NEW_TYPES)
    _create_agent_or_team_check()


def downgrade() -> None:
    if not _has_table("message_queue"):
        return

    op.execute("DELETE FROM message_queue WHERE message_type = 'team_run'")
    _drop_agent_or_team_check()
    _replace_message_type_check(_OLD_TYPES)

    _drop_fk_if_exists("fk_mq_tenant_team_run", "message_queue")
    _drop_fk_if_exists("fk_mq_tenant_team", "message_queue")
    _drop_fk_if_exists("fk_mq_team_run_id_agent_team_run", "message_queue")
    _drop_fk_if_exists("fk_mq_team_id_agent_team", "message_queue")
    _drop_index_if_exists("ix_mq_tenant_team_status", "message_queue")
    _drop_index_if_exists("ix_mq_team_run_id", "message_queue")
    _drop_index_if_exists("ix_mq_team_id", "message_queue")
    _drop_column_if_exists("message_queue", "team_run_id")
    _drop_column_if_exists("message_queue", "team_id")
    _set_agent_id_nullable(False)
