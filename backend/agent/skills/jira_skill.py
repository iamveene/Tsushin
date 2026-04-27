"""Ticket Management skill — Jira provider.

Lets agents search/read/act on tickets in a connected Jira Cloud instance.
The skill is provider-shaped (Jira today, Linear/ServiceNow/etc. later).

Capability gating happens at *tool-spec* time, not at execution time:
``get_mcp_tool_definition()`` is overridden as an instance method that reads
``self._config['capabilities']`` and filters the ``action`` enum to only
the enabled actions. So an agent with read-only capabilities never sees
``update`` / ``add_comment`` / ``transition`` in its tool spec, and the LLM
cannot propose them. ``execute_tool()`` keeps a defensive capability check
as defense-in-depth for any code path that bypasses the spec.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from hub.jira.jira_ticket_service import (
    JiraIssueSummary,
    JiraSkillError,
    JiraTicketService,
)


logger = logging.getLogger(__name__)


# Map LLM ``action`` enum value → capability key in AgentSkill.config
_ACTION_TO_CAPABILITY: Dict[str, str] = {
    "search": "search_tickets",
    "read": "read_ticket",
    "read_comments": "read_comments",
    "update": "update_ticket",
    "add_comment": "add_comment",
    "transition": "transition_ticket",
}

# Display order for the ``action`` enum and capability list.
_ACTION_ORDER: List[str] = ["search", "read", "read_comments", "update", "add_comment", "transition"]


class JiraSkill(BaseSkill):
    """Ticket Management skill — Jira provider.

    Single tool ``ticket_operation`` whose ``action`` enum is filtered per
    agent based on the enabled capabilities. Implementation supports six
    actions; default config enables only the three read actions.
    """

    skill_type = "ticket_management"
    skill_name = "Ticket Management"
    skill_description = (
        "Search, read, and (when enabled) act on tickets in a connected ticketing "
        "system. Today: Atlassian Jira via REST API."
    )
    execution_mode = "tool"
    # Tool-only — no keyword/legacy path. Wizard-visible so it appears in the
    # agent creation wizard once a Jira integration exists.
    wizard_visible = True

    def __init__(self) -> None:
        super().__init__()
        self._jira_service: Optional[JiraTicketService] = None
        self._integration_id: Optional[int] = None

    def set_db_session(self, db) -> None:  # noqa: ANN001 — match BaseSkill
        super().set_db_session(db)
        self._jira_service = None  # invalidate cache

    # ----------------------------------------------------------------- helpers

    def _resolve_integration_id(self, config: Optional[Dict[str, Any]]) -> Optional[int]:
        config = config or getattr(self, "_config", {}) or {}
        integration_id = config.get("integration_id")
        if integration_id:
            try:
                return int(integration_id)
            except (TypeError, ValueError):
                return None
        # Fallback to AgentSkillIntegration row.
        agent_id = getattr(self, "_agent_id", None)
        if not agent_id or not self._db_session:
            return None
        try:
            from models import AgentSkillIntegration

            row = (
                self._db_session.query(AgentSkillIntegration)
                .filter(
                    AgentSkillIntegration.agent_id == agent_id,
                    AgentSkillIntegration.skill_type == self.skill_type,
                )
                .first()
            )
            if row and row.integration_id:
                return int(row.integration_id)
        except Exception as e:  # pragma: no cover — defensive
            logger.warning("JiraSkill: error loading skill integration: %s", e)
        return None

    def _get_jira_service(self, config: Optional[Dict[str, Any]] = None) -> JiraTicketService:
        if self._jira_service is not None:
            return self._jira_service
        integration_id = self._resolve_integration_id(config)
        if not integration_id:
            raise JiraSkillError(
                "Jira integration not configured. Open the agent's Skills tab and "
                "select a Jira connection for Ticket Management."
            )
        if not self._db_session:
            raise JiraSkillError("Database session unavailable for Jira skill.")
        # Resolve tenant via the agent row; AgentSkillIntegration enforces
        # tenant scoping via the agent.
        from models import Agent

        agent_id = getattr(self, "_agent_id", None)
        if not agent_id:
            raise JiraSkillError("Agent context missing for Jira skill.")
        agent = self._db_session.query(Agent).filter(Agent.id == agent_id).first()
        if agent is None:
            raise JiraSkillError(f"Agent {agent_id} not found.")
        self._jira_service = JiraTicketService(
            self._db_session, tenant_id=agent.tenant_id, integration_id=integration_id
        )
        self._integration_id = integration_id
        return self._jira_service

    def _enabled_actions(self, config: Optional[Dict[str, Any]] = None) -> List[str]:
        """Return the list of action names whose capability is enabled."""
        config = config or getattr(self, "_config", {}) or {}
        defaults = self.get_default_config().get("capabilities", {})
        capabilities = config.get("capabilities", {}) or {}
        enabled: List[str] = []
        for action in _ACTION_ORDER:
            cap_key = _ACTION_TO_CAPABILITY[action]
            default_entry = defaults.get(cap_key, {}) or {}
            override_entry = capabilities.get(cap_key, {}) or {}
            merged = {**default_entry, **override_entry}
            if merged.get("enabled", False):
                enabled.append(action)
        return enabled

    def _is_capability_enabled(self, config: Optional[Dict[str, Any]], action: str) -> bool:
        return action in set(self._enabled_actions(config))

    # ------------------------------------------------------------ legacy path

    async def can_handle(self, message: InboundMessage) -> bool:
        # Tool-only skill — no keyword routing.
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        return SkillResult(
            success=False,
            output="Ticket Management skill is tool-only; invoke via the LLM tool call.",
            metadata={"error": "legacy_disabled"},
        )

    # ----------------------------------------------------------- tool spec

    @classmethod
    def get_mcp_tool_definition(cls) -> Optional[Dict[str, Any]]:  # type: ignore[override]
        """Return the FULL MCP-compliant tool definition (all six actions).

        This is intentionally a classmethod returning the unfiltered spec so
        ``SkillManager._find_skill_by_tool_name`` can match the LLM's tool name
        ('ticket_operation') back to this skill class for dispatch.

        Per-agent capability filtering happens at *send time* in the instance
        methods :py:meth:`to_openai_tool` / :py:meth:`to_anthropic_tool` /
        :py:meth:`get_per_agent_mcp_tool_definition`, which read
        ``self._config['capabilities']`` and rebuild the ``action`` enum.
        """
        return cls._build_full_mcp_tool_definition()

    def get_per_agent_mcp_tool_definition(self) -> Optional[Dict[str, Any]]:
        """Per-agent MCP tool definition with the ``action`` enum filtered to enabled capabilities.

        Returns None if the agent has no enabled capabilities (the tool is then
        omitted from the LLM's tool list entirely).
        """
        return self._build_filtered_mcp_tool_definition()

    @classmethod
    def _build_full_mcp_tool_definition(cls) -> Dict[str, Any]:
        return cls._build_mcp_tool_definition_for_actions(_ACTION_ORDER)

    def _build_filtered_mcp_tool_definition(self) -> Optional[Dict[str, Any]]:
        actions = self._enabled_actions()
        if not actions:
            return None
        return self.__class__._build_mcp_tool_definition_for_actions(actions)

    @classmethod
    def _build_mcp_tool_definition_for_actions(cls, actions: List[str]) -> Dict[str, Any]:
        properties: Dict[str, Any] = {
            "action": {
                "type": "string",
                "enum": actions,
                "description": (
                    "Operation to perform. "
                    "'search' (JQL search), 'read' (single-issue details), "
                    "'read_comments' (issue comments)."
                    + (" 'update' (modify fields), 'add_comment' (post a comment), 'transition' (move workflow state)." if any(a in actions for a in ("update", "add_comment", "transition")) else "")
                ),
            },
            "jql": {
                "type": "string",
                "description": (
                    "JQL query for 'search'. Examples: "
                    "'project = JSM AND statusCategory != Done', "
                    "'project = OPS AND assignee = currentUser() AND text ~ \"vpn\"', "
                    "'key = JSM-193570'. Use Jira's JQL syntax."
                ),
            },
            "issue_key": {
                "type": "string",
                "description": "Issue key (e.g., 'JSM-193570') for 'read', 'read_comments', 'update', 'add_comment', 'transition'.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of issues to return (search) or comments (read_comments).",
                "default": 25,
                "minimum": 1,
                "maximum": 100,
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional Jira field names to fetch (search). If omitted, a sensible default set is used.",
            },
        }
        if "update" in actions:
            properties["fields_update"] = {
                "type": "object",
                "additionalProperties": True,
                "description": (
                    "Field map for 'update'. Example: {\"summary\": \"new summary\", "
                    "\"priority\": {\"name\": \"High\"}, \"labels\": [\"x\", \"y\"]}."
                ),
            }
        if "add_comment" in actions:
            properties["comment"] = {
                "type": "string",
                "description": "Plain-text body for 'add_comment'.",
            }
        if "transition" in actions:
            properties["transition_id"] = {
                "type": "string",
                "description": (
                    "Transition id for 'transition'. Use 'list_transitions' shape: caller may first issue "
                    "a 'read' to inspect available transitions if needed, or pass a known id."
                ),
            }
            properties["transition_name"] = {
                "type": "string",
                "description": "Optional transition name (case-insensitive). If provided, it's resolved to an id by listing transitions.",
            }

        return {
            "name": "ticket_operation",
            "title": "Ticket Management",
            "description": (
                "Interact with the connected ticketing system (Jira). "
                "Use this tool when the user asks about tickets/issues — "
                "to find tickets by status/type/keyword/project, fetch a "
                "specific ticket by key, or read its comments."
            ),
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": ["action"],
            },
            "annotations": {
                "destructive": any(a in actions for a in ("update", "transition")),
                "idempotent": False,
                "audience": ["user"],
            },
        }

    def to_openai_tool(self) -> Optional[Dict[str, Any]]:  # type: ignore[override]
        # Per-agent: action enum filtered by enabled capabilities. None = no
        # capabilities enabled → omit the tool entirely from the LLM tool list.
        mcp_def = self._build_filtered_mcp_tool_definition()
        if not mcp_def:
            return None
        return {
            "type": "function",
            "function": {
                "name": mcp_def["name"],
                "description": mcp_def["description"],
                "parameters": mcp_def["inputSchema"],
            },
        }

    def to_anthropic_tool(self) -> Optional[Dict[str, Any]]:  # type: ignore[override]
        mcp_def = self._build_filtered_mcp_tool_definition()
        if not mcp_def:
            return None
        return {
            "name": mcp_def["name"],
            "description": mcp_def["description"],
            "input_schema": mcp_def["inputSchema"],
        }

    # --------------------------------------------------------- execute_tool

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any],
    ) -> SkillResult:
        action = (arguments or {}).get("action")
        if not action or action not in _ACTION_ORDER:
            return SkillResult(
                success=False,
                output=f"Unknown action '{action}'. Use one of: {', '.join(_ACTION_ORDER)}.",
                metadata={"error": "invalid_action"},
            )

        # Defense-in-depth: even if the action somehow leaked into the tool
        # spec, refuse here too.
        if not self._is_capability_enabled(config, action):
            cap_key = _ACTION_TO_CAPABILITY[action]
            return SkillResult(
                success=False,
                output=(
                    f"Action '{action}' is disabled for this agent. "
                    f"Ask an admin to enable the '{cap_key}' capability in the "
                    "agent's Ticket Management skill settings."
                ),
                metadata={"error": "capability_disabled", "action": action, "capability": cap_key},
            )

        try:
            jira = self._get_jira_service(config)
        except JiraSkillError as e:
            return SkillResult(
                success=False,
                output=str(e),
                metadata={"error": "not_configured"},
            )

        try:
            if action == "search":
                return await self._action_search(jira, arguments)
            if action == "read":
                return await self._action_read(jira, arguments)
            if action == "read_comments":
                return await self._action_read_comments(jira, arguments)
            if action == "update":
                return await self._action_update(jira, arguments)
            if action == "add_comment":
                return await self._action_add_comment(jira, arguments)
            if action == "transition":
                return await self._action_transition(jira, arguments)
        except JiraSkillError as e:
            logger.info("JiraSkill action=%s failed: %s", action, e)
            return SkillResult(
                success=False,
                output=str(e),
                metadata={"error": "jira_error", "status_code": e.status_code, "action": action},
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.error("JiraSkill action=%s unexpected error: %s", action, e, exc_info=True)
            return SkillResult(
                success=False,
                output=f"Unexpected error performing Jira {action}: {e}",
                metadata={"error": "unexpected", "action": action},
            )

        return SkillResult(
            success=False,
            output=f"Action '{action}' is not implemented.",
            metadata={"error": "not_implemented"},
        )

    # ----------------------------------------------- per-action implementations

    async def _action_search(self, jira: JiraTicketService, arguments: Dict[str, Any]) -> SkillResult:
        jql = (arguments.get("jql") or "").strip()
        if not jql:
            return SkillResult(
                success=False,
                output="JQL is required for 'search'. Example: 'project = JSM AND statusCategory != Done'.",
                metadata={"error": "missing_jql"},
            )
        max_results = int(arguments.get("max_results") or 25)
        fields = arguments.get("fields") or None

        issues = await jira.search(jql, max_results=max_results, fields=fields)

        if not issues:
            return SkillResult(
                success=True,
                output=f"No tickets found for JQL: `{jql}`",
                metadata={"action": "search", "count": 0, "jql": jql},
            )

        lines = [f"Found {len(issues)} ticket(s) for JQL `{jql}`:\n"]
        for i, issue in enumerate(issues, 1):
            lines.append(
                f"{i}. **{issue.key}** [{issue.issuetype}] [{issue.status}] — {issue.summary}"
            )
            if issue.assignee:
                lines.append(f"   Assignee: {issue.assignee}")
            lines.append(f"   {issue.url}")
        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "action": "search",
                "count": len(issues),
                "jql": jql,
                "issues": [_issue_summary_to_dict(i) for i in issues],
            },
        )

    async def _action_read(self, jira: JiraTicketService, arguments: Dict[str, Any]) -> SkillResult:
        key = (arguments.get("issue_key") or "").strip()
        if not key:
            return SkillResult(
                success=False,
                output="'issue_key' is required for 'read'.",
                metadata={"error": "missing_issue_key"},
            )
        data = await jira.get_issue(key)
        summary = _summarize_issue_dict(jira.site_url, data)
        lines = [
            f"**{summary['key']}** — {summary['summary']}",
            f"Status: {summary['status']} ({summary.get('status_category') or 'unknown'})",
            f"Type: {summary['issuetype']}    Priority: {summary.get('priority') or '—'}",
            f"Assignee: {summary.get('assignee') or '—'}    Reporter: {summary.get('reporter') or '—'}",
            f"Project: {summary.get('project') or '—'}    Updated: {summary.get('updated') or '—'}",
        ]
        if summary.get("description"):
            lines.append("")
            lines.append("Description:")
            lines.append(summary["description"][:1500])
        lines.append("")
        lines.append(summary["url"])
        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={"action": "read", "issue": summary},
        )

    async def _action_read_comments(self, jira: JiraTicketService, arguments: Dict[str, Any]) -> SkillResult:
        key = (arguments.get("issue_key") or "").strip()
        if not key:
            return SkillResult(
                success=False,
                output="'issue_key' is required for 'read_comments'.",
                metadata={"error": "missing_issue_key"},
            )
        max_results = int(arguments.get("max_results") or 50)
        comments = await jira.get_comments(key, max_results=max_results)
        if not comments:
            return SkillResult(
                success=True,
                output=f"No comments on {key}.",
                metadata={"action": "read_comments", "count": 0, "issue_key": key},
            )
        lines = [f"Comments on **{key}** ({len(comments)}):\n"]
        for i, c in enumerate(comments, 1):
            head = f"{i}. {c.get('author') or 'unknown'}"
            if c.get("created"):
                head += f" — {c['created']}"
            lines.append(head)
            body = (c.get("body") or "").strip()
            if body:
                lines.append("    " + body[:800].replace("\n", "\n    "))
            lines.append("")
        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "action": "read_comments",
                "count": len(comments),
                "issue_key": key,
                "comments": comments,
            },
        )

    async def _action_update(self, jira: JiraTicketService, arguments: Dict[str, Any]) -> SkillResult:
        key = (arguments.get("issue_key") or "").strip()
        fields_update = arguments.get("fields_update")
        if not key:
            return SkillResult(success=False, output="'issue_key' is required for 'update'.", metadata={"error": "missing_issue_key"})
        if not isinstance(fields_update, dict) or not fields_update:
            return SkillResult(success=False, output="'fields_update' object is required for 'update'.", metadata={"error": "missing_fields"})
        await jira.update_issue(key, fields_update)
        changed = ", ".join(sorted(fields_update.keys()))
        return SkillResult(
            success=True,
            output=f"Updated {key} fields: {changed}.",
            metadata={"action": "update", "issue_key": key, "changed_fields": list(fields_update.keys())},
        )

    async def _action_add_comment(self, jira: JiraTicketService, arguments: Dict[str, Any]) -> SkillResult:
        key = (arguments.get("issue_key") or "").strip()
        body = (arguments.get("comment") or "").strip()
        if not key:
            return SkillResult(success=False, output="'issue_key' is required for 'add_comment'.", metadata={"error": "missing_issue_key"})
        if not body:
            return SkillResult(success=False, output="'comment' is required for 'add_comment'.", metadata={"error": "missing_comment"})
        result = await jira.add_comment(key, body)
        return SkillResult(
            success=True,
            output=f"Comment added to {key}.",
            metadata={"action": "add_comment", "issue_key": key, "comment_id": result.get("id")},
        )

    async def _action_transition(self, jira: JiraTicketService, arguments: Dict[str, Any]) -> SkillResult:
        key = (arguments.get("issue_key") or "").strip()
        transition_id = (arguments.get("transition_id") or "").strip()
        transition_name = (arguments.get("transition_name") or "").strip().lower()
        if not key:
            return SkillResult(success=False, output="'issue_key' is required for 'transition'.", metadata={"error": "missing_issue_key"})
        if not transition_id and not transition_name:
            return SkillResult(success=False, output="'transition_id' or 'transition_name' is required for 'transition'.", metadata={"error": "missing_transition"})
        if not transition_id:
            transitions = await jira.list_transitions(key)
            for t in transitions:
                if str(t.get("name", "")).strip().lower() == transition_name:
                    transition_id = str(t.get("id"))
                    break
            if not transition_id:
                names = ", ".join(str(t.get("name")) for t in transitions if t.get("name"))
                return SkillResult(
                    success=False,
                    output=f"Transition '{transition_name}' not available for {key}. Available: {names or '(none)'}.",
                    metadata={"error": "unknown_transition", "available": names},
                )
        await jira.transition_issue(key, transition_id)
        return SkillResult(
            success=True,
            output=f"Transitioned {key} (transition id {transition_id}).",
            metadata={"action": "transition", "issue_key": key, "transition_id": transition_id},
        )

    # ----------------------------------------------------------- defaults & schema

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "execution_mode": "tool",
            "enabled": True,
            "integration_id": None,
            "capabilities": {
                "search_tickets": {
                    "enabled": True,
                    "label": "Search tickets",
                    "description": "JQL search across tickets",
                },
                "read_ticket": {
                    "enabled": True,
                    "label": "Read ticket",
                    "description": "Fetch one ticket's fields",
                },
                "read_comments": {
                    "enabled": True,
                    "label": "Read comments",
                    "description": "Fetch a ticket's comments",
                },
                "update_ticket": {
                    "enabled": False,
                    "label": "Update ticket",
                    "description": "Modify ticket fields (off by default)",
                },
                "add_comment": {
                    "enabled": False,
                    "label": "Add comment",
                    "description": "Post a comment on a ticket (off by default)",
                },
                "transition_ticket": {
                    "enabled": False,
                    "label": "Transition ticket",
                    "description": "Move a ticket through its workflow (off by default)",
                },
            },
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        base = super().get_config_schema()
        base["properties"]["execution_mode"] = {
            "type": "string",
            "enum": ["tool"],
            "title": "Execution Mode",
            "default": "tool",
        }
        base["properties"]["integration_id"] = {
            "type": ["integer", "null"],
            "title": "Jira Connection",
            "description": "Select which Jira connection (Hub > API and Tools) this agent uses.",
            "default": None,
        }
        cap_props: Dict[str, Any] = {}
        for cap in [
            "search_tickets",
            "read_ticket",
            "read_comments",
            "update_ticket",
            "add_comment",
            "transition_ticket",
        ]:
            cap_props[cap] = {
                "type": "object",
                "properties": {"enabled": {"type": "boolean", "default": cap in {"search_tickets", "read_ticket", "read_comments"}}},
            }
        base["properties"]["capabilities"] = {
            "type": "object",
            "title": "Capabilities",
            "properties": cap_props,
        }
        return base

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        return {
            "expected_intents": [
                "Search tickets by JQL",
                "Read a specific ticket by key",
                "Read comments on a ticket",
                "Update a ticket's fields (only when capability enabled)",
                "Add a comment to a ticket (only when capability enabled)",
                "Transition a ticket through its workflow (only when capability enabled)",
            ],
            "expected_patterns": [
                "ticket", "issue", "jira", "JQL", "JSM-", "OPS-", "status", "type",
                "Pen Test", "comment", "transition", "assignee", "project",
            ],
            "risk_notes": (
                "Read access exposes ticket content (potentially sensitive). "
                "Write actions (update/add_comment/transition) are off by default and gated by capability."
            ),
            "risk_level": "medium",
        }


# ----------------------------------------------------------------- helpers

def _issue_summary_to_dict(s: JiraIssueSummary) -> Dict[str, Any]:
    return {
        "key": s.key,
        "summary": s.summary,
        "status": s.status,
        "issuetype": s.issuetype,
        "priority": s.priority,
        "assignee": s.assignee,
        "reporter": s.reporter,
        "project": s.project,
        "updated": s.updated,
        "url": s.url,
    }


def _summarize_issue_dict(site_url: str, issue: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize a raw issue dict from /rest/api/3/issue/{key}."""
    fields = issue.get("fields") or {}
    status_obj = fields.get("status") or {}
    sc_obj = status_obj.get("statusCategory") or {}
    issuetype = (fields.get("issuetype") or {}).get("name") or "Unknown"
    priority = (fields.get("priority") or {}).get("name") if fields.get("priority") else None
    assignee = (fields.get("assignee") or {}).get("displayName") if fields.get("assignee") else None
    reporter = (fields.get("reporter") or {}).get("displayName") if fields.get("reporter") else None
    project = (fields.get("project") or {}).get("key") if fields.get("project") else None
    description_raw = fields.get("description")
    description: Optional[str] = None
    if isinstance(description_raw, dict):
        # ADF — flatten to text
        from hub.jira.jira_ticket_service import _adf_to_text  # local import to avoid cycle

        description = _adf_to_text(description_raw)
    elif isinstance(description_raw, str):
        description = description_raw
    key = issue.get("key") or ""
    url = f"{site_url.rstrip('/')}/browse/{key}" if key else site_url
    return {
        "key": key,
        "summary": fields.get("summary") or "",
        "status": status_obj.get("name") or "Unknown",
        "status_category": sc_obj.get("name"),
        "issuetype": issuetype,
        "priority": priority,
        "assignee": assignee,
        "reporter": reporter,
        "project": project,
        "updated": fields.get("updated"),
        "description": description,
        "url": url,
    }
