"""Agent Teams Phase 1 schema foundation.

Revision ID: 0083
Revises: 0082
Create Date: 2026-05-04

This is intentionally schema-only: no orchestrator, API, trigger dispatch,
Sentinel hook, memory-read behavior, or frontend surface changes land here.
The added tables and nullable cross-reference columns are inert until later
Agent Teams phases wire services around them.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0083"
down_revision: Union[str, None] = "0082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    return {fk["name"] for fk in _inspector().get_foreign_keys(table_name)}


def _fk_names_for_columns(table_name: str, columns: list[str], referred_table: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    names = set()
    for fk in _inspector().get_foreign_keys(table_name):
        if fk.get("constrained_columns") == columns and fk.get("referred_table") == referred_table and fk.get("name"):
            names.add(fk["name"])
    return names


def _unique_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {uq["name"] for uq in _inspector().get_unique_constraints(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str], **kwargs) -> None:
    if _has_table(table_name) and name not in _index_names(table_name):
        op.create_index(name, table_name, columns, **kwargs)


def _drop_index_if_exists(name: str, table_name: str) -> None:
    if _has_table(table_name) and name in _index_names(table_name):
        op.drop_index(name, table_name=table_name)


def _create_unique_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and name not in _unique_names(table_name):
        op.create_unique_constraint(name, table_name, columns)


def _drop_unique_if_exists(name: str, table_name: str) -> None:
    if _has_table(table_name) and name in _unique_names(table_name):
        op.drop_constraint(name, table_name, type_="unique")


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


def upgrade() -> None:
    _create_unique_if_missing("uq_agent_tenant_id_id", "agent", ["tenant_id", "id"])
    _create_unique_if_missing("uq_wake_event_tenant_id_id", "wake_event", ["tenant_id", "id"])
    _create_unique_if_missing(
        "uq_agent_comm_perm_tenant_id_id",
        "agent_communication_permission",
        ["tenant_id", "id"],
    )

    if not _has_table("agent_team"):
        op.create_table(
            "agent_team",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("goal_text", sa.Text(), nullable=True),
            sa.Column("topology", sa.String(length=16), nullable=False, server_default="line"),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
            sa.Column("coordinator_agent_id", sa.Integer(), nullable=True),
            sa.Column("max_steps", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("max_total_tokens", sa.Integer(), nullable=True),
            sa.Column("max_concurrent_runs", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("tools_json", sa.JSON(), nullable=True),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["coordinator_agent_id"], ["agent.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["tenant_id", "coordinator_agent_id"],
                ["agent.tenant_id", "agent.id"],
                name="fk_agent_team_tenant_coordinator_agent",
            ),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("tenant_id", "name", name="uq_agent_team_tenant_name"),
            sa.UniqueConstraint("tenant_id", "id", name="uq_agent_team_tenant_id_id"),
        )

    if not _has_table("agent_team_member"):
        op.create_table(
            "agent_team_member",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False, server_default="member"),
            sa.Column("execution_order", sa.Integer(), nullable=True),
            sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("position_x", sa.Float(), nullable=True),
            sa.Column("position_y", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "team_id"], ["agent_team.tenant_id", "agent_team.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["tenant_id", "agent_id"], ["agent.tenant_id", "agent.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("team_id", "agent_id", name="uq_agent_team_member_team_agent"),
            sa.UniqueConstraint("agent_id", name="uq_agent_team_member_agent"),
            sa.UniqueConstraint("tenant_id", "id", name="uq_agent_team_member_tenant_id_id"),
        )

    if not _has_table("agent_team_trigger"):
        op.create_table(
            "agent_team_trigger",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("trigger_kind", sa.String(length=32), nullable=False),
            sa.Column("config_json", sa.JSON(), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "team_id"], ["agent_team.tenant_id", "agent_team.id"], ondelete="CASCADE"),
        )

    if not _has_table("agent_team_run"):
        op.create_table(
            "agent_team_run",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
            sa.Column("trigger_event_id", sa.Integer(), nullable=True),
            sa.Column("goal_text_snapshot", sa.Text(), nullable=True),
            sa.Column("topology_snapshot", sa.String(length=16), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("total_steps", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completed_steps", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_steps", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("final_output_summary", sa.Text(), nullable=True),
            sa.Column("error_json", sa.JSON(), nullable=True),
            sa.Column("total_input_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_output_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_cost_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "team_id"], ["agent_team.tenant_id", "agent_team.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["trigger_event_id"], ["wake_event.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["tenant_id", "trigger_event_id"],
                ["wake_event.tenant_id", "wake_event.id"],
                name="fk_agent_team_run_tenant_trigger_event",
            ),
            sa.UniqueConstraint("tenant_id", "id", name="uq_agent_team_run_tenant_id_id"),
            sa.UniqueConstraint("tenant_id", "team_id", "id", name="uq_agent_team_run_tenant_team_id_id"),
        )

    if not _has_table("agent_team_member_run"):
        op.create_table(
            "agent_team_member_run",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("team_run_id", sa.Integer(), nullable=False),
            sa.Column("agent_team_member_id", sa.Integer(), nullable=True),
            sa.Column("agent_id", sa.Integer(), nullable=True),
            sa.Column("step_index", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("input_context_json", sa.JSON(), nullable=True),
            sa.Column("output_text", sa.Text(), nullable=True),
            sa.Column("output_summary", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sentinel_decision_json", sa.JSON(), nullable=True),
            sa.Column("error_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "team_run_id"], ["agent_team_run.tenant_id", "agent_team_run.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["agent_team_member_id"],
                ["agent_team_member.id"],
                name="fk_agent_team_member_run_member_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id", "agent_team_member_id"],
                ["agent_team_member.tenant_id", "agent_team_member.id"],
                name="fk_agent_team_member_run_tenant_member",
            ),
            sa.ForeignKeyConstraint(["tenant_id", "agent_id"], ["agent.tenant_id", "agent.id"], ondelete="RESTRICT"),
        )

    if not _has_table("team_run_scratch"):
        op.create_table(
            "team_run_scratch",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("team_run_id", sa.Integer(), nullable=False),
            sa.Column("key", sa.String(length=255), nullable=False),
            sa.Column("value_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "team_id"], ["agent_team.tenant_id", "agent_team.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "team_id", "team_run_id"], ["agent_team_run.tenant_id", "agent_team_run.team_id", "agent_team_run.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("tenant_id", "team_run_id", "key", name="uq_team_run_scratch_tenant_run_key"),
        )

    if not _has_table("agent_team_member_a2a_snapshot"):
        op.create_table(
            "agent_team_member_a2a_snapshot",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("team_id", sa.Integer(), nullable=False),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("permission_id", sa.Integer(), nullable=True),
            sa.Column("permission_payload_json", sa.JSON(), nullable=False),
            sa.Column("disabled_at", sa.DateTime(), nullable=True),
            sa.Column("restored_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "team_id"], ["agent_team.tenant_id", "agent_team.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["tenant_id", "agent_id"], ["agent.tenant_id", "agent.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["permission_id"], ["agent_communication_permission.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["tenant_id", "permission_id"],
                ["agent_communication_permission.tenant_id", "agent_communication_permission.id"],
                name="fk_agent_team_a2a_snapshot_tenant_permission",
            ),
            sa.UniqueConstraint(
                "tenant_id",
                "team_id",
                "agent_id",
                "permission_id",
                name="uq_agent_team_a2a_snapshot_tenant_permission",
            ),
        )

    _add_column_if_missing("agent", sa.Column("is_team_member", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    _add_column_if_missing("agent", sa.Column("current_team_id", sa.Integer(), nullable=True))
    _add_column_if_missing("agent", sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    _create_fk_if_missing(
        "fk_agent_current_team_id_agent_team",
        "agent",
        "agent_team",
        ["current_team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    _create_fk_if_missing(
        "fk_agent_tenant_current_team",
        "agent",
        "agent_team",
        ["tenant_id", "current_team_id"],
        ["tenant_id", "id"],
    )

    _create_fk_if_missing(
        "fk_agent_team_tenant_coordinator_agent",
        "agent_team",
        "agent",
        ["tenant_id", "coordinator_agent_id"],
        ["tenant_id", "id"],
    )
    _create_fk_if_missing(
        "fk_agent_team_run_tenant_trigger_event",
        "agent_team_run",
        "wake_event",
        ["tenant_id", "trigger_event_id"],
        ["tenant_id", "id"],
    )
    for fk_name in _fk_names_for_columns(
        "agent_team_member_run",
        ["agent_team_member_id"],
        "agent_team_member",
    ):
        if fk_name != "fk_agent_team_member_run_member_id":
            _drop_fk_if_exists(fk_name, "agent_team_member_run")
    for fk_name in _fk_names_for_columns(
        "agent_team_member_run",
        ["tenant_id", "agent_team_member_id"],
        "agent_team_member",
    ):
        _drop_fk_if_exists(fk_name, "agent_team_member_run")
    _create_fk_if_missing(
        "fk_agent_team_member_run_member_id",
        "agent_team_member_run",
        "agent_team_member",
        ["agent_team_member_id"],
        ["id"],
        ondelete="SET NULL",
    )
    _create_fk_if_missing(
        "fk_agent_team_member_run_tenant_member",
        "agent_team_member_run",
        "agent_team_member",
        ["tenant_id", "agent_team_member_id"],
        ["tenant_id", "id"],
    )
    _create_fk_if_missing(
        "fk_agent_team_a2a_snapshot_tenant_permission",
        "agent_team_member_a2a_snapshot",
        "agent_communication_permission",
        ["tenant_id", "permission_id"],
        ["tenant_id", "id"],
    )
    _create_unique_if_missing(
        "uq_agent_team_a2a_snapshot_tenant_permission",
        "agent_team_member_a2a_snapshot",
        ["tenant_id", "team_id", "agent_id", "permission_id"],
    )

    _add_column_if_missing("agent_communication_session", sa.Column("team_run_id", sa.Integer(), nullable=True))
    _create_fk_if_missing(
        "fk_agent_comm_session_team_run_id_agent_team_run",
        "agent_communication_session",
        "agent_team_run",
        ["team_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _add_column_if_missing("memory", sa.Column("team_run_id", sa.Integer(), nullable=True))
    _create_fk_if_missing(
        "fk_memory_team_run_id_agent_team_run",
        "memory",
        "agent_team_run",
        ["team_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _add_column_if_missing("case_memory", sa.Column("team_run_id", sa.Integer(), nullable=True))
    _create_fk_if_missing(
        "fk_case_memory_team_run_id_agent_team_run",
        "case_memory",
        "agent_team_run",
        ["team_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    _create_index_if_missing("ix_agent_current_team_id", "agent", ["current_team_id"])
    _create_index_if_missing("ix_agent_team_tenant_status", "agent_team", ["tenant_id", "status"])
    _create_index_if_missing("ix_agent_team_coordinator_agent_id", "agent_team", ["coordinator_agent_id"])
    _create_index_if_missing("ix_agent_team_created_by_user_id", "agent_team", ["created_by_user_id"])
    _create_index_if_missing("ix_agent_team_member_tenant_team", "agent_team_member", ["tenant_id", "team_id"])
    _create_index_if_missing("ix_agent_team_member_agent", "agent_team_member", ["agent_id"])
    _create_index_if_missing("ix_agent_team_trigger_tenant_kind", "agent_team_trigger", ["tenant_id", "trigger_kind"])
    _create_index_if_missing("ix_agent_team_trigger_team_enabled", "agent_team_trigger", ["team_id", "is_enabled"])
    _create_index_if_missing("ix_agent_team_run_tenant_status_started", "agent_team_run", ["tenant_id", "status", "started_at"])
    _create_index_if_missing("ix_agent_team_run_team_started", "agent_team_run", ["team_id", "started_at"])
    _create_index_if_missing("ix_agent_team_run_trigger_event", "agent_team_run", ["trigger_event_id"])
    _create_index_if_missing("ix_agent_team_member_run_tenant", "agent_team_member_run", ["tenant_id", "team_run_id"])
    _create_index_if_missing("ix_agent_team_member_run_run_step", "agent_team_member_run", ["team_run_id", "step_index"])
    _create_index_if_missing("ix_agent_team_member_run_agent", "agent_team_member_run", ["agent_id", "started_at"])
    _create_index_if_missing("ix_team_run_scratch_tenant_run", "team_run_scratch", ["tenant_id", "team_run_id"])
    _create_index_if_missing("ix_team_run_scratch_team", "team_run_scratch", ["team_id"])
    _create_index_if_missing("ix_agent_team_a2a_snapshot_tenant_team", "agent_team_member_a2a_snapshot", ["tenant_id", "team_id"])
    _create_index_if_missing("ix_agent_team_a2a_snapshot_agent", "agent_team_member_a2a_snapshot", ["agent_id"])
    _create_index_if_missing("ix_agent_team_a2a_snapshot_permission_id", "agent_team_member_a2a_snapshot", ["permission_id"])
    _create_index_if_missing("ix_agent_comm_session_team_run_id", "agent_communication_session", ["team_run_id"])
    _create_index_if_missing("ix_agent_comm_session_tenant_team_run", "agent_communication_session", ["tenant_id", "team_run_id"])
    _create_index_if_missing("ix_memory_team_run_id", "memory", ["team_run_id"])
    _create_index_if_missing("idx_memory_tenant_agent_sender_team_run", "memory", ["tenant_id", "agent_id", "sender_key", "team_run_id"])
    _create_index_if_missing("ix_case_memory_team_run_id", "case_memory", ["team_run_id"])
    _create_index_if_missing("ix_case_memory_tenant_team_run", "case_memory", ["tenant_id", "team_run_id"])


def downgrade() -> None:
    _drop_index_if_exists("ix_case_memory_tenant_team_run", "case_memory")
    _drop_index_if_exists("ix_case_memory_team_run_id", "case_memory")
    _drop_index_if_exists("idx_memory_tenant_agent_sender_team_run", "memory")
    _drop_index_if_exists("ix_memory_team_run_id", "memory")
    _drop_index_if_exists("ix_agent_comm_session_tenant_team_run", "agent_communication_session")
    _drop_index_if_exists("ix_agent_comm_session_team_run_id", "agent_communication_session")
    _drop_index_if_exists("ix_agent_current_team_id", "agent")

    _drop_fk_if_exists("fk_case_memory_team_run_id_agent_team_run", "case_memory")
    _drop_column_if_exists("case_memory", "team_run_id")
    _drop_fk_if_exists("fk_memory_team_run_id_agent_team_run", "memory")
    _drop_column_if_exists("memory", "team_run_id")
    _drop_fk_if_exists("fk_agent_comm_session_team_run_id_agent_team_run", "agent_communication_session")
    _drop_column_if_exists("agent_communication_session", "team_run_id")
    _drop_fk_if_exists("fk_agent_tenant_current_team", "agent")
    _drop_fk_if_exists("fk_agent_current_team_id_agent_team", "agent")
    _drop_column_if_exists("agent", "is_internal")
    _drop_column_if_exists("agent", "current_team_id")
    _drop_column_if_exists("agent", "is_team_member")

    for index_name, table_name in (
        ("ix_agent_team_a2a_snapshot_permission_id", "agent_team_member_a2a_snapshot"),
        ("ix_agent_team_a2a_snapshot_agent", "agent_team_member_a2a_snapshot"),
        ("ix_agent_team_a2a_snapshot_tenant_team", "agent_team_member_a2a_snapshot"),
        ("ix_team_run_scratch_team", "team_run_scratch"),
        ("ix_team_run_scratch_tenant_run", "team_run_scratch"),
        ("ix_agent_team_member_run_agent", "agent_team_member_run"),
        ("ix_agent_team_member_run_run_step", "agent_team_member_run"),
        ("ix_agent_team_member_run_tenant", "agent_team_member_run"),
        ("ix_agent_team_run_trigger_event", "agent_team_run"),
        ("ix_agent_team_run_team_started", "agent_team_run"),
        ("ix_agent_team_run_tenant_status_started", "agent_team_run"),
        ("ix_agent_team_trigger_team_enabled", "agent_team_trigger"),
        ("ix_agent_team_trigger_tenant_kind", "agent_team_trigger"),
        ("ix_agent_team_member_agent", "agent_team_member"),
        ("ix_agent_team_member_tenant_team", "agent_team_member"),
        ("ix_agent_team_created_by_user_id", "agent_team"),
        ("ix_agent_team_coordinator_agent_id", "agent_team"),
        ("ix_agent_team_tenant_status", "agent_team"),
    ):
        _drop_index_if_exists(index_name, table_name)

    _drop_fk_if_exists("fk_agent_team_a2a_snapshot_tenant_permission", "agent_team_member_a2a_snapshot")
    _drop_unique_if_exists("uq_agent_team_a2a_snapshot_tenant_permission", "agent_team_member_a2a_snapshot")
    _drop_fk_if_exists("fk_agent_team_member_run_tenant_member", "agent_team_member_run")
    _drop_fk_if_exists("fk_agent_team_member_run_member_id", "agent_team_member_run")
    _drop_fk_if_exists("fk_agent_team_run_tenant_trigger_event", "agent_team_run")
    _drop_fk_if_exists("fk_agent_team_tenant_coordinator_agent", "agent_team")

    for table_name in (
        "agent_team_member_a2a_snapshot",
        "team_run_scratch",
        "agent_team_member_run",
        "agent_team_run",
        "agent_team_trigger",
        "agent_team_member",
        "agent_team",
    ):
        if _has_table(table_name):
            op.drop_table(table_name)

    _drop_unique_if_exists("uq_agent_comm_perm_tenant_id_id", "agent_communication_permission")
    _drop_unique_if_exists("uq_wake_event_tenant_id_id", "wake_event")
    _drop_unique_if_exists("uq_agent_tenant_id_id", "agent")
