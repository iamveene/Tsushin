"""Code Repository skill — GitHub provider.

Lets agents search/read/act on repositories, pull requests, and issues in a
connected code-repository service. The skill is provider-shaped so we can add
Bitbucket / GitLab later without touching the dispatch contract.

Capability gating happens at *tool-spec* time, not at execution time:
``get_per_agent_mcp_tool_definition()`` reads ``self._config['capabilities']``
and filters the ``action`` enum (and the schema's write-only properties) to
only the enabled actions. ``execute_tool()`` keeps a defensive capability
check as defense-in-depth for any code path that bypasses the spec.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from hub.github.github_repository_service import (
    GitHubIssueSummary,
    GitHubPullRequestSummary,
    GitHubRepositoryError,
    GitHubRepositoryService,
)


logger = logging.getLogger(__name__)


# Map LLM ``action`` enum value → capability key in AgentSkill.config
_ACTION_TO_CAPABILITY: Dict[str, str] = {
    "search_repos": "search_repos",
    "list_pull_requests": "list_pull_requests",
    "read_pull_request": "read_pull_request",
    "list_issues": "list_issues",
    "read_issue": "read_issue",
    "create_issue": "create_issue",
    "add_pr_comment": "add_pr_comment",
    # PR workflow write actions — full agent-driven PR lifecycle support.
    "approve_pull_request": "approve_pull_request",
    "request_changes": "request_changes",
    "merge_pull_request": "merge_pull_request",
    "close_pull_request": "close_pull_request",
    "close_issue": "close_issue",
}

# Display order for the ``action`` enum and capability list.
_ACTION_ORDER: List[str] = [
    "search_repos",
    "list_pull_requests",
    "read_pull_request",
    "list_issues",
    "read_issue",
    "create_issue",
    "add_pr_comment",
    "approve_pull_request",
    "request_changes",
    "merge_pull_request",
    "close_pull_request",
    "close_issue",
]

_READ_ACTIONS = {
    "search_repos",
    "list_pull_requests",
    "read_pull_request",
    "list_issues",
    "read_issue",
}
_WRITE_ACTIONS = {
    "create_issue",
    "add_pr_comment",
    "approve_pull_request",
    "request_changes",
    "merge_pull_request",
    "close_pull_request",
    "close_issue",
}


class CodeRepositorySkill(BaseSkill):
    """Code Repository skill — GitHub provider.

    Single tool ``repository_operation`` whose ``action`` enum is filtered
    per agent based on enabled capabilities. Implementation supports seven
    actions; default config enables only the five read actions.
    """

    skill_type = "code_repository"
    skill_name = "Code Repository"
    skill_description = (
        "Search repos, read pull requests and issues, and (when enabled) post "
        "comments / create issues. Today: GitHub via REST API."
    )
    execution_mode = "tool"
    # Tool-only — no keyword/legacy path. Wizard-visible so it appears in the
    # agent creation wizard once a GitHub integration exists.
    wizard_visible = True

    def __init__(self) -> None:
        super().__init__()
        self._repo_service: Optional[GitHubRepositoryService] = None
        self._integration_id: Optional[int] = None

    def set_db_session(self, db) -> None:  # noqa: ANN001 — match BaseSkill
        super().set_db_session(db)
        self._repo_service = None  # invalidate cache

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
            logger.warning("CodeRepositorySkill: error loading skill integration: %s", e)
        return None

    def _get_repo_service(
        self, config: Optional[Dict[str, Any]] = None
    ) -> GitHubRepositoryService:
        if self._repo_service is not None:
            return self._repo_service
        integration_id = self._resolve_integration_id(config)
        if not integration_id:
            raise GitHubRepositoryError(
                "GitHub integration not configured. Open the agent's Skills tab and "
                "select a GitHub connection for Code Repository."
            )
        if not self._db_session:
            raise GitHubRepositoryError("Database session unavailable for code_repository skill.")
        from models import Agent

        agent_id = getattr(self, "_agent_id", None)
        if not agent_id:
            raise GitHubRepositoryError("Agent context missing for code_repository skill.")
        agent = self._db_session.query(Agent).filter(Agent.id == agent_id).first()
        if agent is None:
            raise GitHubRepositoryError(f"Agent {agent_id} not found.")
        self._repo_service = GitHubRepositoryService(
            self._db_session, tenant_id=agent.tenant_id, integration_id=integration_id
        )
        self._integration_id = integration_id
        return self._repo_service

    def _enabled_actions(self, config: Optional[Dict[str, Any]] = None) -> List[str]:
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
            output="Code Repository skill is tool-only; invoke via the LLM tool call.",
            metadata={"error": "legacy_disabled"},
        )

    # ----------------------------------------------------------- tool spec

    @classmethod
    def get_mcp_tool_definition(cls) -> Optional[Dict[str, Any]]:  # type: ignore[override]
        """Return the FULL MCP-compliant tool definition (all seven actions).

        Same pattern as JiraSkill: SkillManager._find_skill_by_tool_name needs
        the classmethod path to return the unfiltered spec so 'repository_operation'
        resolves back to this class for dispatch. Per-agent filtering happens
        in the instance methods at send time.
        """
        return cls._build_full_mcp_tool_definition()

    def get_per_agent_mcp_tool_definition(self) -> Optional[Dict[str, Any]]:
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
        any_write = any(a in actions for a in _WRITE_ACTIONS)
        properties: Dict[str, Any] = {
            "action": {
                "type": "string",
                "enum": actions,
                "description": (
                    "Operation to perform. "
                    "'search_repos' (free-text repo search), "
                    "'list_pull_requests' (PRs in a repo), "
                    "'read_pull_request' (single PR detail), "
                    "'list_issues' (issues in a repo, PRs filtered out), "
                    "'read_issue' (single issue detail)."
                    + (
                        " Write actions: 'create_issue', 'add_pr_comment', "
                        "'approve_pull_request' (submit APPROVE review), "
                        "'request_changes' (submit REQUEST_CHANGES review with required body), "
                        "'merge_pull_request' (merge via merge/squash/rebase), "
                        "'close_pull_request' (close without merging), "
                        "'close_issue'."
                        if any_write
                        else ""
                    )
                ),
            },
            "query": {
                "type": "string",
                "description": (
                    "Free-text query for 'search_repos'. Examples: "
                    "'tsushin org:my-org', 'language:python stars:>100', "
                    "'topic:agent-framework'. Uses GitHub's repo search syntax."
                ),
            },
            "owner": {
                "type": "string",
                "description": "Repository owner (user or org). Required for repo-scoped actions.",
            },
            "repo": {
                "type": "string",
                "description": "Repository name. Required for repo-scoped actions.",
            },
            "pr_number": {
                "type": "integer",
                "description": "Pull request number for 'read_pull_request' and 'add_pr_comment'.",
                "minimum": 1,
            },
            "issue_number": {
                "type": "integer",
                "description": "Issue number for 'read_issue'.",
                "minimum": 1,
            },
            "state": {
                "type": "string",
                "enum": ["open", "closed", "all"],
                "description": "State filter for 'list_pull_requests' and 'list_issues'.",
                "default": "open",
            },
            "max_results": {
                "type": "integer",
                "description": (
                    "Maximum number of results to return for list/search actions."
                ),
                "default": 20,
                "minimum": 1,
                "maximum": 100,
            },
        }
        if "create_issue" in actions:
            properties["title"] = {
                "type": "string",
                "description": "Issue title for 'create_issue'.",
            }
            properties["labels"] = {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional labels to apply for 'create_issue'.",
            }
        # `body` is shared by create_issue, add_pr_comment, approve_pull_request
        # (optional review note), and request_changes. Always expose if any of
        # those actions is enabled.
        if any(a in actions for a in ("create_issue", "add_pr_comment", "approve_pull_request", "request_changes")):
            properties["body"] = {
                "type": "string",
                "description": (
                    "Body content. For 'create_issue': issue body (markdown). "
                    "For 'add_pr_comment': comment body. For 'approve_pull_request': "
                    "optional review note. For 'request_changes': required review feedback."
                ),
            }
        if "merge_pull_request" in actions:
            properties["merge_method"] = {
                "type": "string",
                "enum": ["merge", "squash", "rebase"],
                "description": "Merge method for 'merge_pull_request'.",
                "default": "merge",
            }
            properties["commit_title"] = {
                "type": "string",
                "description": "Optional commit title for the merge commit.",
            }
            properties["commit_message"] = {
                "type": "string",
                "description": "Optional commit message body for the merge commit.",
            }

        return {
            "name": "repository_operation",
            "title": "Code Repository",
            "description": (
                "Interact with the connected code-repository service (GitHub). "
                "Use this tool when the user asks about repositories, pull "
                "requests, or issues — to search repos, list/read PRs and "
                "issues, and (when enabled) post comments or open issues."
            ),
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": ["action"],
            },
            "annotations": {
                "destructive": any_write,
                "idempotent": False,
                "audience": ["user"],
            },
        }

    def to_openai_tool(self) -> Optional[Dict[str, Any]]:  # type: ignore[override]
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

        if not self._is_capability_enabled(config, action):
            cap_key = _ACTION_TO_CAPABILITY[action]
            return SkillResult(
                success=False,
                output=(
                    f"Action '{action}' is disabled for this agent. "
                    f"Ask an admin to enable the '{cap_key}' capability in the "
                    "agent's Code Repository skill settings."
                ),
                metadata={
                    "error": "capability_disabled",
                    "action": action,
                    "capability": cap_key,
                },
            )

        try:
            repo = self._get_repo_service(config)
        except GitHubRepositoryError as e:
            return SkillResult(
                success=False,
                output=str(e),
                metadata={"error": "not_configured"},
            )

        try:
            if action == "search_repos":
                return await self._action_search_repos(repo, arguments)
            if action == "list_pull_requests":
                return await self._action_list_pull_requests(repo, arguments)
            if action == "read_pull_request":
                return await self._action_read_pull_request(repo, arguments)
            if action == "list_issues":
                return await self._action_list_issues(repo, arguments)
            if action == "read_issue":
                return await self._action_read_issue(repo, arguments)
            if action == "create_issue":
                return await self._action_create_issue(repo, arguments)
            if action == "add_pr_comment":
                return await self._action_add_pr_comment(repo, arguments)
            if action == "approve_pull_request":
                return await self._action_approve_pull_request(repo, arguments)
            if action == "request_changes":
                return await self._action_request_changes(repo, arguments)
            if action == "merge_pull_request":
                return await self._action_merge_pull_request(repo, arguments)
            if action == "close_pull_request":
                return await self._action_close_pull_request(repo, arguments)
            if action == "close_issue":
                return await self._action_close_issue(repo, arguments)
        except GitHubRepositoryError as e:
            logger.info("CodeRepositorySkill action=%s failed: %s", action, e)
            return SkillResult(
                success=False,
                output=str(e),
                metadata={
                    "error": "github_error",
                    "status_code": e.status_code,
                    "action": action,
                },
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.error(
                "CodeRepositorySkill action=%s unexpected error: %s",
                action,
                e,
                exc_info=True,
            )
            return SkillResult(
                success=False,
                output=f"Unexpected error performing GitHub {action}: {e}",
                metadata={"error": "unexpected", "action": action},
            )

        return SkillResult(
            success=False,
            output=f"Action '{action}' is not implemented.",
            metadata={"error": "not_implemented"},
        )

    # ----------------------------------------------- per-action implementations

    def _resolve_owner_repo(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
        owner = (arguments.get("owner") or "").strip() or repo_service.default_owner
        repo = (arguments.get("repo") or "").strip() or repo_service.default_repo
        return owner, repo

    async def _action_search_repos(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        query = (arguments.get("query") or "").strip()
        if not query:
            return SkillResult(
                success=False,
                output="'query' is required for 'search_repos'.",
                metadata={"error": "missing_query"},
            )
        max_results = int(arguments.get("max_results") or 10)
        items = await repo_service.search_repositories(query, max_results=max_results)
        if not items:
            return SkillResult(
                success=True,
                output=f"No repositories matched query: `{query}`",
                metadata={"action": "search_repos", "count": 0, "query": query},
            )
        lines = [f"Found {len(items)} repositor{'y' if len(items) == 1 else 'ies'} for `{query}`:\n"]
        compact: list[Dict[str, Any]] = []
        for i, repo in enumerate(items, 1):
            full = repo.get("full_name") or "?"
            desc = (repo.get("description") or "").strip()
            stars = repo.get("stargazers_count")
            url = repo.get("html_url") or ""
            lines.append(f"{i}. **{full}** — stars: {stars or 0}")
            if desc:
                lines.append(f"   {desc}")
            if url:
                lines.append(f"   {url}")
            compact.append({
                "full_name": full,
                "description": desc,
                "stars": stars,
                "url": url,
            })
        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "action": "search_repos",
                "count": len(items),
                "query": query,
                "items": compact,
            },
        )

    async def _action_list_pull_requests(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        if not owner or not repo:
            return SkillResult(
                success=False,
                output="'owner' and 'repo' are required for 'list_pull_requests'.",
                metadata={"error": "missing_owner_repo"},
            )
        state = (arguments.get("state") or "open").strip().lower()
        max_results = int(arguments.get("max_results") or 20)
        prs = await repo_service.list_pull_requests(
            owner, repo, state=state, max_results=max_results
        )
        if not prs:
            return SkillResult(
                success=True,
                output=f"No {state} pull requests in {owner}/{repo}.",
                metadata={
                    "action": "list_pull_requests",
                    "count": 0,
                    "owner": owner,
                    "repo": repo,
                    "state": state,
                },
            )
        lines = [f"Found {len(prs)} {state} PR(s) in `{owner}/{repo}`:\n"]
        for i, pr in enumerate(prs, 1):
            lines.append(f"{i}. **#{pr.number}** [{pr.state}] — {pr.title}")
            head_base = []
            if pr.head_branch:
                head_base.append(f"head: {pr.head_branch}")
            if pr.base_branch:
                head_base.append(f"base: {pr.base_branch}")
            if pr.author:
                head_base.append(f"by {pr.author}")
            if head_base:
                lines.append(f"   {'    '.join(head_base)}")
            if pr.url:
                lines.append(f"   {pr.url}")
        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "action": "list_pull_requests",
                "count": len(prs),
                "owner": owner,
                "repo": repo,
                "state": state,
                "pull_requests": [_pr_summary_to_dict(p) for p in prs],
            },
        )

    async def _action_read_pull_request(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        number = arguments.get("pr_number")
        if not owner or not repo or not number:
            return SkillResult(
                success=False,
                output="'owner', 'repo' and 'pr_number' are required for 'read_pull_request'.",
                metadata={"error": "missing_args"},
            )
        data = await repo_service.get_pull_request(owner, repo, int(number))
        title = data.get("title") or ""
        state = data.get("state") or "unknown"
        author = (data.get("user") or {}).get("login") if isinstance(data.get("user"), dict) else None
        body = (data.get("body") or "").strip()
        head = (data.get("head") or {}).get("ref") if isinstance(data.get("head"), dict) else None
        base = (data.get("base") or {}).get("ref") if isinstance(data.get("base"), dict) else None
        url = data.get("html_url") or ""
        lines = [
            f"**{owner}/{repo}#{number}** — {title}",
            f"State: {state}    Author: {author or '—'}",
            f"Head: {head or '—'} → Base: {base or '—'}",
        ]
        if body:
            lines.append("")
            lines.append("Description:")
            lines.append(body[:1500])
        if url:
            lines.append("")
            lines.append(url)
        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "action": "read_pull_request",
                "owner": owner,
                "repo": repo,
                "pr_number": int(number),
                "title": title,
                "state": state,
                "author": author,
                "url": url,
            },
        )

    async def _action_list_issues(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        if not owner or not repo:
            return SkillResult(
                success=False,
                output="'owner' and 'repo' are required for 'list_issues'.",
                metadata={"error": "missing_owner_repo"},
            )
        state = (arguments.get("state") or "open").strip().lower()
        max_results = int(arguments.get("max_results") or 20)
        issues = await repo_service.list_issues(
            owner, repo, state=state, max_results=max_results
        )
        if not issues:
            return SkillResult(
                success=True,
                output=f"No {state} issues in {owner}/{repo}.",
                metadata={
                    "action": "list_issues",
                    "count": 0,
                    "owner": owner,
                    "repo": repo,
                    "state": state,
                },
            )
        lines = [f"Found {len(issues)} {state} issue(s) in `{owner}/{repo}`:\n"]
        for i, issue in enumerate(issues, 1):
            head = f"{i}. **#{issue.number}** [{issue.state}] — {issue.title}"
            lines.append(head)
            sub = []
            if issue.author:
                sub.append(f"by {issue.author}")
            if issue.labels:
                sub.append(f"labels: {', '.join(issue.labels)}")
            if sub:
                lines.append(f"   {'    '.join(sub)}")
            if issue.url:
                lines.append(f"   {issue.url}")
        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "action": "list_issues",
                "count": len(issues),
                "owner": owner,
                "repo": repo,
                "state": state,
                "issues": [_issue_summary_to_dict(i) for i in issues],
            },
        )

    async def _action_read_issue(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        number = arguments.get("issue_number")
        if not owner or not repo or not number:
            return SkillResult(
                success=False,
                output="'owner', 'repo' and 'issue_number' are required for 'read_issue'.",
                metadata={"error": "missing_args"},
            )
        data = await repo_service.get_issue(owner, repo, int(number))
        title = data.get("title") or ""
        state = data.get("state") or "unknown"
        author = (data.get("user") or {}).get("login") if isinstance(data.get("user"), dict) else None
        body = (data.get("body") or "").strip()
        url = data.get("html_url") or ""
        labels_raw = data.get("labels") or []
        labels: list[str] = []
        for lbl in labels_raw:
            if isinstance(lbl, dict) and lbl.get("name"):
                labels.append(str(lbl["name"]))
        lines = [
            f"**{owner}/{repo}#{number}** — {title}",
            f"State: {state}    Author: {author or '—'}",
        ]
        if labels:
            lines.append(f"Labels: {', '.join(labels)}")
        if body:
            lines.append("")
            lines.append("Description:")
            lines.append(body[:1500])
        if url:
            lines.append("")
            lines.append(url)
        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "action": "read_issue",
                "owner": owner,
                "repo": repo,
                "issue_number": int(number),
                "title": title,
                "state": state,
                "author": author,
                "labels": labels,
                "url": url,
            },
        )

    async def _action_create_issue(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        title = (arguments.get("title") or "").strip()
        body = arguments.get("body")
        labels = arguments.get("labels")
        if not owner or not repo:
            return SkillResult(
                success=False,
                output="'owner' and 'repo' are required for 'create_issue'.",
                metadata={"error": "missing_owner_repo"},
            )
        if not title:
            return SkillResult(
                success=False,
                output="'title' is required for 'create_issue'.",
                metadata={"error": "missing_title"},
            )
        if labels is not None and not isinstance(labels, list):
            return SkillResult(
                success=False,
                output="'labels' must be an array of strings.",
                metadata={"error": "invalid_labels"},
            )
        result = await repo_service.create_issue(
            owner, repo, title, body=body if isinstance(body, str) else None, labels=labels
        )
        number = result.get("number")
        url = result.get("html_url")
        return SkillResult(
            success=True,
            output=f"Created issue #{number} in {owner}/{repo}: {title}\n{url or ''}".strip(),
            metadata={
                "action": "create_issue",
                "owner": owner,
                "repo": repo,
                "issue_number": number,
                "url": url,
            },
        )

    async def _action_add_pr_comment(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        number = arguments.get("pr_number")
        body = (arguments.get("body") or "").strip()
        if not owner or not repo or not number:
            return SkillResult(
                success=False,
                output="'owner', 'repo' and 'pr_number' are required for 'add_pr_comment'.",
                metadata={"error": "missing_args"},
            )
        if not body:
            return SkillResult(
                success=False,
                output="'body' is required for 'add_pr_comment'.",
                metadata={"error": "missing_body"},
            )
        result = await repo_service.add_pr_comment(owner, repo, int(number), body)
        comment_id = result.get("id")
        url = result.get("html_url")
        return SkillResult(
            success=True,
            output=f"Comment added to {owner}/{repo}#{number}.\n{url or ''}".strip(),
            metadata={
                "action": "add_pr_comment",
                "owner": owner,
                "repo": repo,
                "pr_number": int(number),
                "comment_id": comment_id,
                "url": url,
            },
        )

    async def _action_approve_pull_request(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        number = arguments.get("pr_number")
        body = (arguments.get("body") or "").strip() or None
        if not owner or not repo or not number:
            return SkillResult(success=False, output="'owner', 'repo' and 'pr_number' are required for 'approve_pull_request'.", metadata={"error": "missing_args"})
        result = await repo_service.approve_pull_request(owner, repo, int(number), body)
        return SkillResult(
            success=True,
            output=f"Approved {owner}/{repo}#{number}.",
            metadata={"action": "approve_pull_request", "owner": owner, "repo": repo, "pr_number": int(number), "review_id": result.get("id")},
        )

    async def _action_request_changes(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        number = arguments.get("pr_number")
        body = (arguments.get("body") or "").strip()
        if not owner or not repo or not number:
            return SkillResult(success=False, output="'owner', 'repo' and 'pr_number' are required for 'request_changes'.", metadata={"error": "missing_args"})
        if not body:
            return SkillResult(success=False, output="'body' is required when requesting changes.", metadata={"error": "missing_body"})
        result = await repo_service.request_changes(owner, repo, int(number), body)
        return SkillResult(
            success=True,
            output=f"Requested changes on {owner}/{repo}#{number}.",
            metadata={"action": "request_changes", "owner": owner, "repo": repo, "pr_number": int(number), "review_id": result.get("id")},
        )

    async def _action_merge_pull_request(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        number = arguments.get("pr_number")
        merge_method = (arguments.get("merge_method") or "merge").strip().lower()
        commit_title = arguments.get("commit_title") or None
        commit_message = arguments.get("commit_message") or None
        if not owner or not repo or not number:
            return SkillResult(success=False, output="'owner', 'repo' and 'pr_number' are required for 'merge_pull_request'.", metadata={"error": "missing_args"})
        result = await repo_service.merge_pull_request(owner, repo, int(number), merge_method=merge_method, commit_title=commit_title, commit_message=commit_message)
        return SkillResult(
            success=True,
            output=f"Merged {owner}/{repo}#{number} via {merge_method}. SHA: {result.get('sha','?')}",
            metadata={"action": "merge_pull_request", "owner": owner, "repo": repo, "pr_number": int(number), "merge_method": merge_method, "merged_sha": result.get("sha"), "merged": result.get("merged")},
        )

    async def _action_close_pull_request(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        number = arguments.get("pr_number")
        if not owner or not repo or not number:
            return SkillResult(success=False, output="'owner', 'repo' and 'pr_number' are required for 'close_pull_request'.", metadata={"error": "missing_args"})
        result = await repo_service.close_pull_request(owner, repo, int(number))
        return SkillResult(
            success=True,
            output=f"Closed {owner}/{repo}#{number} (without merging).",
            metadata={"action": "close_pull_request", "owner": owner, "repo": repo, "pr_number": int(number), "state": result.get("state")},
        )

    async def _action_close_issue(
        self,
        repo_service: GitHubRepositoryService,
        arguments: Dict[str, Any],
    ) -> SkillResult:
        owner, repo = self._resolve_owner_repo(repo_service, arguments)
        number = arguments.get("issue_number")
        if not owner or not repo or not number:
            return SkillResult(success=False, output="'owner', 'repo' and 'issue_number' are required for 'close_issue'.", metadata={"error": "missing_args"})
        result = await repo_service.close_issue(owner, repo, int(number))
        return SkillResult(
            success=True,
            output=f"Closed {owner}/{repo}#{number} (issue).",
            metadata={"action": "close_issue", "owner": owner, "repo": repo, "issue_number": int(number), "state": result.get("state")},
        )

    # ----------------------------------------------------------- defaults & schema

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "execution_mode": "tool",
            "enabled": True,
            "integration_id": None,
            "capabilities": {
                "search_repos": {
                    "enabled": True,
                    "label": "Search repositories (read)",
                    "description": "Free-text search across GitHub repositories",
                },
                "list_pull_requests": {
                    "enabled": True,
                    "label": "List pull requests (read)",
                    "description": "List PRs in a repo by state",
                },
                "read_pull_request": {
                    "enabled": True,
                    "label": "Read pull request (read)",
                    "description": "Fetch one PR's details",
                },
                "list_issues": {
                    "enabled": True,
                    "label": "List issues (read)",
                    "description": "List issues in a repo by state (PRs filtered out)",
                },
                "read_issue": {
                    "enabled": True,
                    "label": "Read issue (read)",
                    "description": "Fetch one issue's details",
                },
                "create_issue": {
                    "enabled": False,
                    "label": "Create issue (write — off by default)",
                    "description": "Open a new issue in the repo",
                },
                "add_pr_comment": {
                    "enabled": False,
                    "label": "Add PR comment (write — off by default)",
                    "description": "Post a comment on a pull request",
                },
                "approve_pull_request": {
                    "enabled": False,
                    "label": "Approve pull request (write — off by default)",
                    "description": "Submit an APPROVE review on a PR",
                },
                "request_changes": {
                    "enabled": False,
                    "label": "Request changes (write — off by default)",
                    "description": "Submit a REQUEST_CHANGES review on a PR",
                },
                "merge_pull_request": {
                    "enabled": False,
                    "label": "Merge pull request (write — off by default)",
                    "description": "Merge a PR via merge/squash/rebase",
                },
                "close_pull_request": {
                    "enabled": False,
                    "label": "Close pull request (write — off by default)",
                    "description": "Close a PR without merging",
                },
                "close_issue": {
                    "enabled": False,
                    "label": "Close issue (write — off by default)",
                    "description": "Close an issue",
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
            "title": "GitHub Connection",
            "description": "Select which GitHub connection (Hub > API and Tools) this agent uses.",
            "default": None,
        }
        cap_props: Dict[str, Any] = {}
        for cap in [
            "search_repos",
            "list_pull_requests",
            "read_pull_request",
            "list_issues",
            "read_issue",
            "create_issue",
            "add_pr_comment",
            "approve_pull_request",
            "request_changes",
            "merge_pull_request",
            "close_pull_request",
            "close_issue",
        ]:
            cap_props[cap] = {
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "default": cap in _READ_ACTIONS,
                    }
                },
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
                "Search GitHub repositories by query",
                "List pull requests in a repo",
                "Read a specific pull request",
                "List issues in a repo",
                "Read a specific issue",
                "Open an issue (only when capability enabled)",
                "Comment on a pull request (only when capability enabled)",
            ],
            "expected_patterns": [
                "github", "repo", "repository", "pull request", "PR",
                "issue", "owner", "branch", "merge", "commit", "stars",
            ],
            "risk_notes": (
                "Read access exposes potentially private code metadata. "
                "Write actions (create_issue / add_pr_comment) are off by "
                "default and gated by capability."
            ),
            "risk_level": "medium",
        }


# ----------------------------------------------------------------- helpers


def _pr_summary_to_dict(p: GitHubPullRequestSummary) -> Dict[str, Any]:
    return {
        "number": p.number,
        "title": p.title,
        "state": p.state,
        "author": p.author,
        "base_branch": p.base_branch,
        "head_branch": p.head_branch,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
        "url": p.url,
    }


def _issue_summary_to_dict(i: GitHubIssueSummary) -> Dict[str, Any]:
    return {
        "number": i.number,
        "title": i.title,
        "state": i.state,
        "author": i.author,
        "labels": list(i.labels),
        "created_at": i.created_at,
        "url": i.url,
    }
