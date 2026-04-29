"""Trigger Memory Recap config (per-trigger).

Revision ID: 0076
Revises: 0075
Create Date: 2026-04-29

Adds the ``trigger_recap_config`` table — one row per
``(tenant_id, trigger_kind, trigger_instance_id)``. When ``enabled`` is
True and ``TSN_CASE_MEMORY_ENABLED`` is set, the trigger dispatcher
expands the row's Jinja2 ``query_template`` against the redacted wake
event payload, runs ``case_memory_service.search_similar_cases`` with
the configured ``scope`` / ``k`` / ``min_similarity`` / ``vector_kind``,
renders the configured ``format_template`` with the result set, and
attaches the rendered text to the queue payload under ``memory_recap``.

The trigger-instance pointer is intentionally a *semantic* FK (mirrors
``flow_trigger_binding``) — there is no single target table for the
four supported kinds (email | jira | github | webhook). Application
code is responsible for cleanup on trigger DELETE.

Postgres- and SQLite-friendly: no provider-specific column types are
used so the test fixtures (in-memory SQLite) build cleanly.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0076"
down_revision: Union[str, None] = "0075"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_FORMAT_TEMPLATE = (
    "## Past Cases ({{ count }} match{% if count != 1 %}es{% endif %})\n"
    "{% for c in cases %}\n"
    "- **[{{ c.outcome_label or 'unknown' }}]** sim={{ '%.3f'|format(c.similarity) }} | "
    "{{ (c.problem_summary or '')[:300] }}\n"
    "  Action: {{ (c.action_summary or '')[:300] }}\n"
    "{% endfor %}"
)


def upgrade() -> None:
    op.create_table(
        "trigger_recap_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(length=50),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 'email' | 'jira' | 'github' | 'webhook' (semantic FK)
        sa.Column("trigger_kind", sa.String(length=32), nullable=False),
        sa.Column("trigger_instance_id", sa.Integer(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        # Jinja2 template expanded against the redacted payload.
        sa.Column("query_template", sa.Text(), nullable=False, server_default=""),
        # 'agent' | 'trigger_kind' | 'trigger_instance' (default trigger_instance).
        sa.Column(
            "scope",
            sa.String(length=24),
            nullable=False,
            server_default="trigger_instance",
        ),
        sa.Column("k", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "min_similarity",
            sa.Float(),
            nullable=False,
            server_default="0.35",
        ),
        sa.Column(
            "vector_kind",
            sa.String(length=16),
            nullable=False,
            server_default="problem",
        ),
        sa.Column(
            "include_failed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "format_template",
            sa.Text(),
            nullable=False,
            server_default=_DEFAULT_FORMAT_TEMPLATE,
        ),
        # 'prepend_user_msg' | 'system_addendum'
        sa.Column(
            "inject_position",
            sa.String(length=24),
            nullable=False,
            server_default="prepend_user_msg",
        ),
        sa.Column(
            "max_recap_chars",
            sa.Integer(),
            nullable=False,
            server_default="1500",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "trigger_kind",
            "trigger_instance_id",
            name="uq_trigger_recap_config_unique",
        ),
    )

    op.create_index(
        "ix_trigger_recap_config_lookup",
        "trigger_recap_config",
        ["tenant_id", "trigger_kind", "trigger_instance_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trigger_recap_config_lookup", table_name="trigger_recap_config"
    )
    op.drop_table("trigger_recap_config")
