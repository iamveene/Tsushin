"""v0.7.0 Trigger Case Memory MVP — agent-callable retrieval skill.

Tool-mode skill (single ``find_similar_past_cases`` tool) that returns
ranked past cases for the calling agent. Default scope is ``agent`` for
chat invocation; trigger-origin contexts can pass ``trigger_kind`` to
narrow recall.

Skill registration is gated on ``case_memory_enabled()`` in
``agent/skills/__init__.py`` — the skill is invisible (and
non-executable) when the feature flag is off.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from agent.skills.base import BaseSkill, InboundMessage, SkillResult


logger = logging.getLogger(__name__)


class FindSimilarPastCasesSkill(BaseSkill):
    """Retrieve similar past trigger cases for the current agent."""

    skill_type = "find_similar_past_cases"
    skill_name = "Find Similar Past Cases"
    skill_description = (
        "Retrieve similar past trigger-driven cases handled by this agent. "
        "Use when the user asks 'have we seen this before?' or you need to "
        "compare a current incident against past actions and outcomes."
    )
    execution_mode = "tool"
    applies_to: List[str] = ["text"]
    auto_enabled_for: List[str] = []
    wizard_visible = True

    # ----------------------------------------------------------------- legacy

    async def can_handle(self, message: InboundMessage) -> bool:
        # Tool-only skill — never matches via keyword/legacy routing.
        return False

    async def process(
        self, message: InboundMessage, config: Dict[str, Any]
    ) -> SkillResult:
        return SkillResult(
            success=False,
            output=(
                "find_similar_past_cases is a tool-only skill — invoke it via "
                "the LLM tool call."
            ),
            metadata={"error": "legacy_disabled"},
        )

    # -------------------------------------------------------------- tool spec

    @classmethod
    def get_mcp_tool_definition(cls) -> Optional[Dict[str, Any]]:
        return {
            "name": "find_similar_past_cases",
            "title": "Find Similar Past Cases",
            "description": (
                "Search past trigger-driven cases for ones similar to a given "
                "subject or incident description. Returns ranked cases with "
                "problem/action/outcome summaries."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Free-text description of the current incident, "
                            "ticket subject, or other matter to find prior "
                            "cases for."
                        ),
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["agent", "trigger_kind", "tenant"],
                        "description": (
                            "Which cases to consider. 'agent' (default for "
                            "chat) recalls everything this agent has handled. "
                            "'trigger_kind' (default when invoked by a "
                            "trigger) restricts to the same channel kind. "
                            "'tenant' is operator/debug-only."
                        ),
                        "default": "agent",
                    },
                    "k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "default": 3,
                    },
                    "min_similarity": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "default": 0.65,
                    },
                    "trigger_kind": {
                        "type": "string",
                        "description": (
                            "Channel kind to filter on when scope='trigger_kind'. "
                            "Examples: 'jira', 'github', 'email', 'webhook'."
                        ),
                    },
                    "include_failed": {
                        "type": "boolean",
                        "default": True,
                    },
                },
                "required": ["query"],
            },
            "annotations": {
                "destructive": False,
                "idempotent": True,
                "audience": ["assistant"],
            },
        }

    # ---------------------------------------------------------- execute_tool

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any],
    ) -> SkillResult:
        from services.case_memory_service import search_similar_cases

        query = (arguments or {}).get("query") or ""
        if not isinstance(query, str) or not query.strip():
            return SkillResult(
                success=False,
                output="`query` is required for find_similar_past_cases.",
                metadata={"error": "missing_query"},
            )

        # Scope selection — caller may override; otherwise pick a sensible
        # default based on invocation context. A trigger-origin invocation
        # passes ``trigger_kind`` via metadata; a chat invocation does not.
        invocation_meta = getattr(message, "metadata", None) or {}
        invocation_trigger_kind = (
            invocation_meta.get("trigger_kind")
            if isinstance(invocation_meta, dict)
            else None
        )
        config_trigger_kind = (config or {}).get("trigger_kind")

        scope = arguments.get("scope")
        if scope not in ("agent", "trigger_kind", "tenant"):
            scope = (
                "trigger_kind"
                if (invocation_trigger_kind or config_trigger_kind)
                else "agent"
            )

        trigger_kind = (
            arguments.get("trigger_kind")
            or invocation_trigger_kind
            or config_trigger_kind
        )

        k = int(arguments.get("k") or 3)
        min_similarity = float(arguments.get("min_similarity") or 0.65)
        include_failed = bool(arguments.get("include_failed", True))

        agent_id = getattr(self, "_agent_id", None)
        if agent_id is None:
            return SkillResult(
                success=False,
                output="Agent context missing for find_similar_past_cases.",
                metadata={"error": "no_agent_context"},
            )

        if not self._db_session:
            return SkillResult(
                success=False,
                output="Database session unavailable for find_similar_past_cases.",
                metadata={"error": "no_db_session"},
            )

        # Resolve tenant_id via the agent row.
        from models import Agent

        agent = (
            self._db_session.query(Agent).filter(Agent.id == agent_id).first()
        )
        if agent is None:
            return SkillResult(
                success=False,
                output=f"Agent {agent_id} not found.",
                metadata={"error": "agent_not_found"},
            )

        try:
            results = search_similar_cases(
                self._db_session,
                tenant_id=agent.tenant_id,
                agent_id=agent_id,
                query=query,
                scope=scope,
                k=k,
                min_similarity=min_similarity,
                vector="problem",
                trigger_kind=trigger_kind,
                include_failed=include_failed,
            )
        except Exception as exc:  # noqa: BLE001 — surface to caller as tool error
            logger.exception("find_similar_past_cases: search failed")
            return SkillResult(
                success=False,
                output=f"Case-memory search failed: {exc}",
                metadata={"error": "search_failed"},
            )

        if not results:
            return SkillResult(
                success=True,
                output="No similar past cases found above the similarity threshold.",
                metadata={"cases": [], "scope": scope},
            )

        readable = json.dumps(results, indent=2, ensure_ascii=False, default=str)
        return SkillResult(
            success=True,
            output=f"Similar past cases (top {len(results)}):\n{readable}",
            metadata={"cases": results, "scope": scope, "trigger_kind": trigger_kind},
        )
