"""Run-scoped scratch tools for Agent Team executions."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from models import AgentTeamRun
from services.team_run_scratch_service import TeamRunScratchService


class TeamScratchSkill(BaseSkill):
    """Internal team-run scratchpad skill, exposed only inside team execution."""

    skill_type = "team_scratch"
    skill_name = "Team Scratch"
    skill_description = "Read and write scratch values scoped to the current Agent Team run"
    execution_mode = "tool"
    wizard_visible = False

    def __init__(self):
        super().__init__()
        self.db_session: Optional[Session] = None
        self._current_tool_name: Optional[str] = None

    def set_db_session(self, db: Session):
        super().set_db_session(db)
        self.db_session = db

    def is_tool_enabled(self, config: Optional[Dict[str, Any]] = None) -> bool:
        config = config or getattr(self, "_config", {}) or {}
        return bool(config.get("team_run_id"))

    async def can_handle(self, message: InboundMessage) -> bool:
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        return SkillResult(
            success=False,
            output="Team scratch is only available as a team-run tool call.",
            metadata={"skip_ai": True},
        )

    @classmethod
    def get_all_mcp_tool_definitions(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "team_scratch_set",
                "title": "Set Team Scratch",
                "description": "Store a JSON-serializable value in the current Agent Team run scratchpad.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Scratch key to create or replace"},
                        "value": {
                            "description": "JSON-serializable scratch value",
                        },
                    },
                    "required": ["key", "value"],
                },
                "annotations": {
                    "destructive": False,
                    "idempotent": True,
                    "audience": ["agent"],
                },
            },
            {
                "name": "team_scratch_get",
                "title": "Get Team Scratch",
                "description": "Read one value from the current Agent Team run scratchpad.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "key": {"type": "string", "description": "Scratch key to read"},
                    },
                    "required": ["key"],
                },
                "annotations": {
                    "destructive": False,
                    "idempotent": True,
                    "audience": ["agent"],
                },
            },
            {
                "name": "team_scratch_list",
                "title": "List Team Scratch",
                "description": "List scratch keys stored for the current Agent Team run.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                "annotations": {
                    "destructive": False,
                    "idempotent": True,
                    "audience": ["agent"],
                },
            },
        ]

    @classmethod
    def get_mcp_tool_definition(cls):
        return None

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: Optional[InboundMessage] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> SkillResult:
        config = config or {}
        team_run_id = config.get("team_run_id")
        tenant_id = config.get("tenant_id")
        db = config.get("db") or self.db_session
        if not db or not tenant_id or team_run_id is None:
            return SkillResult(
                success=False,
                output="Team scratch is only available inside an Agent Team run.",
                metadata={"skip_ai": True, "error": "team_run_context_required"},
            )

        run = (
            db.query(AgentTeamRun)
            .filter(
                AgentTeamRun.id == int(team_run_id),
                AgentTeamRun.tenant_id == tenant_id,
            )
            .first()
        )
        if run is None:
            return SkillResult(
                success=False,
                output="Team scratch run scope was not found.",
                metadata={"skip_ai": True, "error": "team_run_not_found"},
            )

        service = TeamRunScratchService(db)
        tool_name = self._current_tool_name or "team_scratch_get"
        try:
            if tool_name == "team_scratch_set":
                key = str(arguments.get("key") or "").strip()
                if not key:
                    return SkillResult(
                        success=False,
                        output="Scratch key is required.",
                        metadata={"skip_ai": True, "error": "missing_key"},
                    )
                value = self._coerce_value(arguments.get("value"))
                service.set(
                    tenant_id=tenant_id,
                    team_id=run.team_id,
                    team_run_id=run.id,
                    key=key,
                    value=value,
                )
                return SkillResult(
                    success=True,
                    output=f"Stored team scratch value for key '{key}'.",
                    metadata={"skip_ai": True, "key": key},
                )

            if tool_name == "team_scratch_list":
                keys = service.list_keys(tenant_id=tenant_id, team_id=run.team_id, team_run_id=run.id)
                return SkillResult(
                    success=True,
                    output=json.dumps({"keys": keys}, ensure_ascii=False),
                    metadata={"skip_ai": False, "keys": keys},
                )

            key = str(arguments.get("key") or "").strip()
            if not key:
                return SkillResult(
                    success=False,
                    output="Scratch key is required.",
                    metadata={"skip_ai": True, "error": "missing_key"},
                )
            value = service.get(
                tenant_id=tenant_id,
                team_id=run.team_id,
                team_run_id=run.id,
                key=key,
            )
            return SkillResult(
                success=True,
                output=json.dumps({"key": key, "value": value}, ensure_ascii=False),
                metadata={"skip_ai": False, "key": key, "found": value is not None},
            )
        except Exception as exc:
            return SkillResult(
                success=False,
                output=f"Team scratch operation failed: {exc}",
                metadata={"skip_ai": True, "error": type(exc).__name__},
            )

    @staticmethod
    def _coerce_value(value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped and (stripped[0] in "[{\"" or stripped in ("true", "false", "null")):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return value
        return value
