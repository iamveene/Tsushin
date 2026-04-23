"""Add continuous-agent control-plane models.

Revision numbering note: Track A2 owns slot 0047, but the integrated release
branch already reached Alembic head 0059 before this continuation worktree was
spawned. To keep a single linear chain, 0047 intentionally revises 0059 and
0050 revises 0047.

Revision ID: 0047
Revises: 0059
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0047"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if table_name in _tables() and name not in _indexes(table_name):
        op.create_index(name, table_name, columns)


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_name in _tables() and column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if table_name in _tables() and column_name in _columns(table_name):
        op.drop_column(table_name, column_name)


def _drop_index_if_exists(name: str, table_name: str) -> None:
    if table_name in _tables() and name in _indexes(table_name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    tables = _tables()

    if "delivery_policy" not in tables:
        op.create_table(
            "delivery_policy",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("batch_window_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("dedupe_window_seconds", sa.Integer(), nullable=False, server_default="300"),
            sa.Column("quiet_hours", JSONB(), nullable=True),
            sa.Column("importance_threshold", sa.String(length=16), nullable=False, server_default="normal"),
            sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("tenant_id", "name", name="uq_delivery_policy_tenant_name"),
        )
    _create_index_if_missing("ix_delivery_policy_tenant_active", "delivery_policy", ["tenant_id", "is_active"])

    if "budget_policy" not in tables:
        op.create_table(
            "budget_policy",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("max_runs_per_day", sa.Integer(), nullable=True),
            sa.Column("max_agentic_runs_per_day", sa.Integer(), nullable=True),
            sa.Column("max_tokens_per_day", sa.BigInteger(), nullable=True),
            sa.Column("max_tool_invocations_per_day", sa.Integer(), nullable=True),
            sa.Column("on_exhaustion", sa.String(length=32), nullable=False, server_default="pause"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("tenant_id", "name", name="uq_budget_policy_tenant_name"),
        )
    _create_index_if_missing("ix_budget_policy_tenant_active", "budget_policy", ["tenant_id", "is_active"])

    if "continuous_agent" not in tables:
        op.create_table(
            "continuous_agent",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=True),
            sa.Column("execution_mode", sa.String(length=16), nullable=False, server_default="hybrid"),
            sa.Column("delivery_policy_id", sa.Integer(), sa.ForeignKey("delivery_policy.id", ondelete="SET NULL"), nullable=True),
            sa.Column("budget_policy_id", sa.Integer(), sa.ForeignKey("budget_policy.id", ondelete="SET NULL"), nullable=True),
            sa.Column("approval_policy_id", sa.Integer(), sa.ForeignKey("sentinel_profile.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("is_system_owned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    _create_index_if_missing("ix_continuous_agent_tenant_status", "continuous_agent", ["tenant_id", "status"])
    _create_index_if_missing("ix_continuous_agent_agent", "continuous_agent", ["agent_id"])

    if "continuous_subscription" not in tables:
        op.create_table(
            "continuous_subscription",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("continuous_agent_id", sa.Integer(), sa.ForeignKey("continuous_agent.id", ondelete="CASCADE"), nullable=False),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("channel_instance_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=True),
            sa.Column("delivery_policy_id", sa.Integer(), sa.ForeignKey("delivery_policy.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
            sa.Column("is_system_owned", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    _create_index_if_missing("ix_continuous_subscription_tenant_status", "continuous_subscription", ["tenant_id", "status"])
    _create_index_if_missing(
        "ix_continuous_subscription_instance",
        "continuous_subscription",
        ["tenant_id", "channel_type", "channel_instance_id"],
    )

    if "wake_event" not in tables:
        op.create_table(
            "wake_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("continuous_agent_id", sa.Integer(), sa.ForeignKey("continuous_agent.id", ondelete="SET NULL"), nullable=True),
            sa.Column("continuous_subscription_id", sa.Integer(), sa.ForeignKey("continuous_subscription.id", ondelete="SET NULL"), nullable=True),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("channel_instance_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("dedupe_key", sa.String(length=512), nullable=False),
            sa.Column("importance", sa.String(length=16), nullable=False, server_default="normal"),
            sa.Column("payload_ref", sa.String(length=512), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                "tenant_id",
                "channel_type",
                "channel_instance_id",
                "dedupe_key",
                name="uq_wake_event_dedupe",
            ),
        )
    _create_index_if_missing("ix_wake_event_tenant_occurred", "wake_event", ["tenant_id", "occurred_at"])
    _create_index_if_missing("ix_wake_event_continuous_agent", "wake_event", ["continuous_agent_id", "occurred_at"])
    _create_index_if_missing("ix_wake_event_subscription", "wake_event", ["continuous_subscription_id", "occurred_at"])

    if "continuous_run" not in tables:
        op.create_table(
            "continuous_run",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("continuous_agent_id", sa.Integer(), sa.ForeignKey("continuous_agent.id", ondelete="CASCADE"), nullable=False),
            sa.Column("wake_event_ids", JSONB(), nullable=True),
            sa.Column("execution_mode", sa.String(length=16), nullable=True),
            sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.Column("watcher_run_ref", sa.String(length=128), nullable=True),
            sa.Column("memory_refs", JSONB(), nullable=True),
            sa.Column("run_threat_signals", JSONB(), nullable=True),
            sa.Column("outcome_state", JSONB(), nullable=True),
            sa.Column("agentic_scratchpad", JSONB(), nullable=True),
            sa.Column("run_type", sa.String(length=32), nullable=False, server_default="continuous"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    _create_index_if_missing("ix_continuous_run_tenant_status", "continuous_run", ["tenant_id", "status", "started_at"])
    _create_index_if_missing("ix_continuous_run_agent_started", "continuous_run", ["continuous_agent_id", "started_at"])

    for table_name in ("custom_skill", "flow_definition"):
        _add_column_if_missing(
            table_name,
            sa.Column("is_system_owned", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        _add_column_if_missing(
            table_name,
            sa.Column("editable_by_tenant", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        _add_column_if_missing(
            table_name,
            sa.Column("deletable_by_tenant", sa.Boolean(), nullable=False, server_default=sa.true()),
        )


def downgrade() -> None:
    for table_name in ("flow_definition", "custom_skill"):
        _drop_column_if_exists(table_name, "deletable_by_tenant")
        _drop_column_if_exists(table_name, "editable_by_tenant")
        _drop_column_if_exists(table_name, "is_system_owned")

    _drop_index_if_exists("ix_continuous_run_agent_started", "continuous_run")
    _drop_index_if_exists("ix_continuous_run_tenant_status", "continuous_run")
    if "continuous_run" in _tables():
        op.drop_table("continuous_run")

    _drop_index_if_exists("ix_wake_event_subscription", "wake_event")
    _drop_index_if_exists("ix_wake_event_continuous_agent", "wake_event")
    _drop_index_if_exists("ix_wake_event_tenant_occurred", "wake_event")
    if "wake_event" in _tables():
        op.drop_table("wake_event")

    _drop_index_if_exists("ix_continuous_subscription_instance", "continuous_subscription")
    _drop_index_if_exists("ix_continuous_subscription_tenant_status", "continuous_subscription")
    if "continuous_subscription" in _tables():
        op.drop_table("continuous_subscription")

    _drop_index_if_exists("ix_continuous_agent_agent", "continuous_agent")
    _drop_index_if_exists("ix_continuous_agent_tenant_status", "continuous_agent")
    if "continuous_agent" in _tables():
        op.drop_table("continuous_agent")

    _drop_index_if_exists("ix_budget_policy_tenant_active", "budget_policy")
    if "budget_policy" in _tables():
        op.drop_table("budget_policy")

    _drop_index_if_exists("ix_delivery_policy_tenant_active", "delivery_policy")
    if "delivery_policy" in _tables():
        op.drop_table("delivery_policy")
