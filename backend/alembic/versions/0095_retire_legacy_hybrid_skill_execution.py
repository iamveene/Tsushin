"""Retire legacy and hybrid skill execution config.

Revision ID: 0095
Revises: 0094
Create Date: 2026-05-19
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0095"
down_revision: Union[str, None] = "0094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


RAW_TEXT_CONFIG_SKILLS = {
    "agent_switcher",
    "shell",
    "gmail",
    "image",
    "web_search",
    "flight_search",
    "automation",
    "flows",
    "scheduler",
    "browser_automation",
    "scheduler_query",
}

RETIRED_CONFIG_KEYS = {
    "execution_mode",
    "keywords",
    "trigger_keywords",
    "trigger_mode",
    "use_ai_fallback",
}
RETIRED_AI_MODEL_CONFIG_SKILLS = {
    "agent_switcher",
    "shell",
    "gmail",
    "web_search",
    "flight_search",
    "automation",
    "flows",
    "scheduler",
    "scheduler_query",
}


def _table_exists(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return name in inspector.get_table_names()


def _as_dict(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _json_update(table: str, column: str, row_id: int, value: Any) -> None:
    bind = op.get_bind()
    stmt = sa.text(f"UPDATE {table} SET {column} = :value WHERE id = :id").bindparams(
        sa.bindparam("value", type_=sa.JSON())
    )
    bind.execute(stmt, {"value": value, "id": row_id})


def _quoted(values: set[str]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in sorted(values))


def _clean_agent_skill_configs_postgres() -> None:
    bind = op.get_bind()
    retired_checks = ", ".join(f"'{key}'" for key in sorted(RETIRED_CONFIG_KEYS))
    retired_ops = " ".join(f"- '{key}'" for key in sorted(RETIRED_CONFIG_KEYS))
    ai_skill_list = _quoted(RETIRED_AI_MODEL_CONFIG_SKILLS)

    bind.execute(
        sa.text(
            f"""
            UPDATE agent_skill
            SET config = CASE
                WHEN skill_type IN ({ai_skill_list})
                    THEN ((COALESCE(config::jsonb, '{{}}'::jsonb) {retired_ops}) - 'ai_model')::json
                ELSE (COALESCE(config::jsonb, '{{}}'::jsonb) {retired_ops})::json
            END
            WHERE config IS NOT NULL
              AND (
                  COALESCE(config::jsonb, '{{}}'::jsonb) ?| ARRAY[{retired_checks}]
                  OR (
                      skill_type IN ({ai_skill_list})
                      AND COALESCE(config::jsonb, '{{}}'::jsonb) ? 'ai_model'
                  )
              )
            """
        )
    )


def _clean_agent_skill_configs() -> None:
    if not _table_exists("agent_skill"):
        return

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _clean_agent_skill_configs_postgres()
        return

    rows = bind.execute(sa.text("SELECT id, skill_type, config FROM agent_skill")).fetchall()
    for row in rows:
        cfg = _as_dict(row.config)
        if cfg is None:
            continue

        changed = False
        for key in RETIRED_CONFIG_KEYS:
            if key in cfg:
                cfg.pop(key, None)
                changed = True
        if row.skill_type in RETIRED_AI_MODEL_CONFIG_SKILLS and "ai_model" in cfg:
            cfg.pop("ai_model", None)
            changed = True

        if changed:
            _json_update("agent_skill", "config", row.id, cfg)


def _clean_custom_skills() -> None:
    if not _table_exists("custom_skill"):
        return

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, execution_mode, trigger_mode, trigger_keywords FROM custom_skill")
    ).fetchall()
    for row in rows:
        updates: dict[str, Any] = {}
        if row.execution_mode not in ("tool", "passive"):
            updates["execution_mode"] = "tool"
        if row.trigger_mode != "llm_decided":
            updates["trigger_mode"] = "llm_decided"
        parsed_keywords = row.trigger_keywords
        if isinstance(parsed_keywords, str):
            try:
                parsed_keywords = json.loads(parsed_keywords)
            except (TypeError, ValueError):
                parsed_keywords = []
        if parsed_keywords:
            updates["trigger_keywords"] = []

        if not updates:
            continue

        set_parts = []
        params: dict[str, Any] = {"id": row.id}
        bindparams = []
        for key, value in updates.items():
            set_parts.append(f"{key} = :{key}")
            params[key] = value
            if key == "trigger_keywords":
                bindparams.append(sa.bindparam(key, type_=sa.JSON()))

        stmt = sa.text(f"UPDATE custom_skill SET {', '.join(set_parts)} WHERE id = :id")
        if bindparams:
            stmt = stmt.bindparams(*bindparams)
        bind.execute(stmt, params)


def _upsert_slash_command(command: dict[str, Any]) -> None:
    if not _table_exists("slash_command"):
        return

    bind = op.get_bind()
    existing = bind.execute(
        sa.text(
            """
            SELECT id FROM slash_command
            WHERE tenant_id = :tenant_id
              AND command_name = :command_name
              AND language_code = :language_code
            """
        ),
        command,
    ).first()

    json_params = [
        sa.bindparam("aliases", type_=sa.JSON()),
        sa.bindparam("handler_config", type_=sa.JSON()),
    ]
    if existing:
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
        bind.execute(stmt, {**command, "id": existing.id})
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
    bind.execute(stmt, command)


def _seed_programmatic_skill_commands() -> None:
    commands = [
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "image",
            "language_code": "en",
            "pattern": r"^/(?:image|imagem)\s+(.+)$",
            "aliases": ["imagem"],
            "description": "Generate an image from an explicit prompt",
            "help_text": "Usage: /image <prompt>\nExample: /image a clean product mockup of a solar-powered backpack",
            "permission_required": None,
            "is_enabled": True,
            "handler_type": "built-in",
            "handler_config": {"skill_type": "image"},
            "sort_order": 80,
        },
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "flights",
            "language_code": "en",
            "pattern": r"^/(?:flights|flight|voos)\s+(.+)$",
            "aliases": ["flight", "voos"],
            "description": "Search flights from an explicit travel request",
            "help_text": "Usage: /flights <origin> to <destination> on <date>\nExample: /flights GRU to FCO on 2026-05-21",
            "permission_required": None,
            "is_enabled": True,
            "handler_type": "built-in",
            "handler_config": {"skill_type": "flight_search"},
            "sort_order": 81,
        },
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "browser",
            "language_code": "en",
            "pattern": r"^/browser\s+(.+)$",
            "aliases": [],
            "description": "Control a browser from an explicit instruction",
            "help_text": "Usage: /browser <instruction>\nExample: /browser navigate to https://example.com and take a screenshot",
            "permission_required": None,
            "is_enabled": True,
            "handler_type": "built-in",
            "handler_config": {"skill_type": "browser_automation"},
            "sort_order": 82,
        },
    ]
    for command in commands:
        _upsert_slash_command(command)


def upgrade() -> None:
    _clean_agent_skill_configs()
    _clean_custom_skills()
    _seed_programmatic_skill_commands()


def downgrade() -> None:
    if not _table_exists("slash_command"):
        return
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM slash_command
            WHERE tenant_id = '_system'
              AND command_name IN ('image', 'flights')
            """
        )
    )
