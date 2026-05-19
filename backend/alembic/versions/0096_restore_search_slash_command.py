"""Restore the /search slash command.

Revision ID: 0096
Revises: 0095
Create Date: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0096"
down_revision: Union[str, None] = "0095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEARCH_COMMAND = {
    "tenant_id": "_system",
    "category": "tool",
    "command_name": "search",
    "language_code": "en",
    "pattern": r"^/search\s+(.+)$",
    "aliases": ["s"],
    "description": "Search the web from an explicit query",
    "help_text": "Usage: /search <query>\nExample: /search latest AI news",
    "permission_required": None,
    "is_enabled": True,
    "handler_type": "built-in",
    "handler_config": {},
    "sort_order": 47,
}


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("slash_command"):
        return

    bind = op.get_bind()
    existing_id = bind.execute(
        sa.text(
            """
            SELECT id FROM slash_command
            WHERE tenant_id = :tenant_id
              AND command_name = :command_name
              AND language_code = :language_code
            """
        ),
        SEARCH_COMMAND,
    ).scalar()

    json_params = [
        sa.bindparam("aliases", type_=sa.JSON()),
        sa.bindparam("handler_config", type_=sa.JSON()),
    ]

    if existing_id:
        stmt = sa.text(
            """
            UPDATE slash_command
            SET category = :category,
                pattern = :pattern,
                aliases = :aliases,
                description = :description,
                help_text = :help_text,
                permission_required = :permission_required,
                is_enabled = :is_enabled,
                handler_type = :handler_type,
                handler_config = :handler_config,
                sort_order = :sort_order,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ).bindparams(*json_params)
        bind.execute(stmt, {**SEARCH_COMMAND, "id": existing_id})
        return

    stmt = sa.text(
        """
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern, aliases,
            description, help_text, permission_required, is_enabled,
            handler_type, handler_config, sort_order, created_at, updated_at
        ) VALUES (
            :tenant_id, :category, :command_name, :language_code, :pattern, :aliases,
            :description, :help_text, :permission_required, :is_enabled,
            :handler_type, :handler_config, :sort_order, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """
    ).bindparams(*json_params)
    bind.execute(stmt, SEARCH_COMMAND)


def downgrade() -> None:
    if not _table_exists("slash_command"):
        return

    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM slash_command
            WHERE tenant_id = '_system'
              AND command_name = 'search'
              AND language_code = 'en'
            """
        )
    )
