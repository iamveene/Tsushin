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
        "Call this tool ONCE PER USER QUESTION whenever the user asks "
        "anything that could be answered from past incidents — "
        "'have we seen this before?', 'what did we do last time?', "
        "'list past tickets', etc. The query should be specific to the "
        "topic of the current question; do NOT reuse a prior turn's "
        "result if the new question is about a different topic. The tool "
        "is cheap (local vector search) and idempotent."
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
                "problem/action/outcome summaries. "
                "IMPORTANT: re-invoke this tool with a topic-specific `query` "
                "for EACH user question that could be informed by past cases. "
                "Do not reuse a prior turn's result if the user is asking "
                "about a different topic. To list multiple historical cases, "
                "call once per topic OR call with a broad query and a higher "
                "`k` (e.g. 10) and `min_similarity=0` to surface more results."
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
                        # k=5 captures the typical small set of past incidents
                        # for an agent without diluting the LLM's context with
                        # low-similarity noise from cross-channel cases. The
                        # caller can override with a larger k for "list all"
                        # questions.
                        "default": 5,
                    },
                    "min_similarity": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        # Default 0.0 (no filtering) so the LLM gets the full
                        # ranked top-K and can decide relevance per its
                        # reasoning. The earlier 0.65 (cosine-scale) silently
                        # rejected every real hit on the local L2 collection;
                        # 0.35 (the prior fix) still filters loosely-related
                        # matches that the LLM is better positioned to judge.
                        "default": 0.0,
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

        k = int(arguments.get("k") or 5)
        min_similarity = float(arguments.get("min_similarity") if arguments.get("min_similarity") is not None else 0.0)
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
                output=(
                    f"No past cases matched the query '{query}'. "
                    "If the user asks about a different topic next, call "
                    "this tool again with a topic-specific query — past "
                    "cases on other topics may exist."
                ),
                metadata={"cases": [], "scope": scope, "query": query},
            )

        # Render each hit as a labeled block so the LLM can clearly attribute
        # each finding to a specific case and quote the resolution back to the
        # user. Plain JSON dumps led the model to cherry-pick the top hit and
        # ignore the rest. The leading IMPORTANT block is at the top because
        # LLMs (claude-sonnet-4.6 observed) weight top-of-block instructions
        # more strongly than trailing footers.
        lines: List[str] = [
            "IMPORTANT — How to use this result:",
            (
                "  1. The cases below are scoped to the QUERY shown. They do "
                "NOT cover other topics. If the user asks a question about a "
                "different topic, you MUST call find_similar_past_cases again "
                "with a query about THAT topic — do not assume the prior "
                "result is comprehensive."
            ),
            (
                "  2. When listing past tickets, enumerate every case below "
                "by id+key — do not collapse to just the top hit."
            ),
            (
                "  3. Do not invent ticket keys. Only cite ticket keys that "
                "appear verbatim in the problem/action/outcome fields below."
            ),
            "",
            f"Found {len(results)} past case(s) for query '{query}' "
            f"(scope={scope}, ranked by similarity):",
        ]
        for idx, r in enumerate(results, start=1):
            lines.append(
                f"\n[{idx}] case_id={r.get('case_id')} "
                f"similarity={r.get('similarity', 0):.3f} "
                f"trigger={r.get('trigger_kind')!r} "
                f"origin={r.get('origin_kind')!r} "
                f"outcome_label={r.get('outcome_label')!r}"
            )
            problem = (r.get("problem_summary") or "").strip()
            action = (r.get("action_summary") or "").strip()
            outcome = (r.get("outcome_summary") or "").strip()
            wake_id = r.get("wake_event_id")
            run_ids = (r.get("continuous_run_id"), r.get("flow_run_id"))
            if problem:
                lines.append(f"  problem: {problem[:600]}")
            if action:
                lines.append(f"  action: {action[:600]}")
            if outcome:
                lines.append(f"  outcome: {outcome[:600]}")
            lines.append(
                f"  references: wake_event={wake_id} "
                f"continuous_run={run_ids[0]} flow_run={run_ids[1]}"
            )

        lines.append(
            "\nREMINDER: when the user asks a NEW question on a different "
            "topic, call this tool AGAIN with a query about the new topic. "
            "Do not assume the above results cover unrelated questions."
        )

        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "cases": results,
                "scope": scope,
                "trigger_kind": trigger_kind,
                "query": query,
            },
        )
