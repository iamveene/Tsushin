"""Async Jira REST client used by the Ticket Management skill.

This is the read/write counterpart to the polling client in
``backend/channels/jira/trigger.py``: same Basic-auth + httpx pattern, same
``/rest/api/3/search/jql`` endpoint, same site-URL normalization. It is
intentionally a separate file (not an extension of the trigger module) so
the agent runtime never imports trigger / continuous-agent symbols.

Capabilities:
- ``search`` — JQL search via POST ``/rest/api/3/search/jql``
- ``get_issue`` — GET ``/rest/api/3/issue/{key}`` (with optional comment expand)
- ``get_comments`` — GET ``/rest/api/3/issue/{key}/comment``
- ``update_issue`` — PUT ``/rest/api/3/issue/{key}`` (write — gated by skill)
- ``add_comment`` — POST ``/rest/api/3/issue/{key}/comment`` (write — gated)
- ``list_transitions`` — GET ``/rest/api/3/issue/{key}/transitions``
- ``transition_issue`` — POST ``/rest/api/3/issue/{key}/transitions`` (write)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from channels.jira.utils import normalize_jira_site_url
from models import JiraIntegration
from services.jira_integration_service import (
    decrypt_jira_token,
    load_jira_integration,
)


logger = logging.getLogger(__name__)


_JIRA_HTTP_TIMEOUT_SECONDS = 15.0

# Default field list for search responses — mirrors the trigger client so a
# skill response and a wake-event payload have parity. Callers can override
# per-request.
DEFAULT_SEARCH_FIELDS: list[str] = [
    "summary",
    "status",
    "statusCategory",
    "issuetype",
    "project",
    "priority",
    "reporter",
    "assignee",
    "created",
    "updated",
    "labels",
]


class JiraSkillError(Exception):
    """Raised for any expected error path the skill should surface to the LLM."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class JiraIssueSummary:
    key: str
    summary: str
    status: str
    issuetype: str
    priority: Optional[str]
    assignee: Optional[str]
    reporter: Optional[str]
    project: Optional[str]
    updated: Optional[str]
    url: str
    raw: dict[str, Any]


def _safe_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        # Atlassian Document Format (ADF). Walk the tree and join text leaves.
        return _adf_to_text(value)
    return str(value)


def _adf_to_text(node: dict[str, Any]) -> str:
    parts: list[str] = []

    def _walk(n: Any) -> None:
        if isinstance(n, dict):
            text = n.get("text")
            if isinstance(text, str):
                parts.append(text)
            for child in n.get("content", []) or []:
                _walk(child)
        elif isinstance(n, list):
            for child in n:
                _walk(child)

    _walk(node)
    return "\n".join(p for p in parts if p)


def _summarize_issue(site_url: str, issue: dict[str, Any]) -> JiraIssueSummary:
    fields = issue.get("fields") or {}
    status = (fields.get("status") or {}).get("name") or "Unknown"
    issuetype = (fields.get("issuetype") or {}).get("name") or "Unknown"
    priority = (fields.get("priority") or {}).get("name") if fields.get("priority") else None
    assignee = (fields.get("assignee") or {}).get("displayName") if fields.get("assignee") else None
    reporter = (fields.get("reporter") or {}).get("displayName") if fields.get("reporter") else None
    project = (fields.get("project") or {}).get("key") if fields.get("project") else None
    updated = fields.get("updated")
    key = issue.get("key") or ""
    site = normalize_jira_site_url(site_url).rstrip("/")
    url = f"{site}/browse/{key}" if key else site
    return JiraIssueSummary(
        key=key,
        summary=fields.get("summary") or "",
        status=status,
        issuetype=issuetype,
        priority=priority,
        assignee=assignee,
        reporter=reporter,
        project=project,
        updated=updated,
        url=url,
        raw=issue,
    )


class JiraTicketService:
    """Thin async client over the Jira Cloud REST API.

    One instance is bound to one ``JiraIntegration`` row (tenant-scoped).
    The integration's encrypted API token is decrypted on construction and
    held in memory only — no plaintext is logged.
    """

    def __init__(self, db: Session, tenant_id: str, integration_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id
        integration = load_jira_integration(
            db, tenant_id=tenant_id, integration_id=integration_id, require_active=False
        )
        if integration is None:
            raise JiraSkillError(
                f"Jira integration {integration_id} not found for tenant {tenant_id}.",
                status_code=404,
            )
        if not integration.is_active:
            raise JiraSkillError(
                "Jira integration is disabled. Re-enable it in Hub > API and Tools.",
            )
        token = decrypt_jira_token(db, tenant_id, integration.api_token_encrypted)
        if not integration.auth_email or not token:
            raise JiraSkillError(
                "Jira integration is missing credentials. Edit it in Hub > API and Tools and re-enter the API token.",
            )
        self._integration = integration
        self._site_url = normalize_jira_site_url(integration.site_url).rstrip("/")
        self._auth = (integration.auth_email, token)

    # ------------------------------------------------------------------ public

    @property
    def integration(self) -> JiraIntegration:
        return self._integration

    @property
    def site_url(self) -> str:
        return self._site_url

    @property
    def default_project_key(self) -> Optional[str]:
        return self._integration.project_key

    async def search(
        self,
        jql: str,
        *,
        max_results: int = 25,
        fields: Optional[list[str]] = None,
    ) -> list[JiraIssueSummary]:
        if not jql or not jql.strip():
            raise JiraSkillError("JQL must not be empty.")
        url = f"{self._site_url}/rest/api/3/search/jql"
        payload: dict[str, Any] = {
            "jql": jql.strip(),
            "maxResults": max(1, min(int(max_results), 100)),
            "fields": fields or DEFAULT_SEARCH_FIELDS,
        }
        data = await self._post(url, json_body=payload)
        raw_issues = data.get("issues") if isinstance(data, dict) else None
        if not isinstance(raw_issues, list):
            return []
        return [
            _summarize_issue(self._site_url, issue)
            for issue in raw_issues
            if isinstance(issue, dict)
        ]

    async def get_issue(
        self,
        issue_key: str,
        *,
        expand_comments: bool = False,
    ) -> dict[str, Any]:
        if not issue_key:
            raise JiraSkillError("Issue key is required.")
        params: dict[str, Any] = {}
        if expand_comments:
            params["expand"] = "renderedFields"
        url = f"{self._site_url}/rest/api/3/issue/{issue_key}"
        data = await self._get(url, params=params)
        if not isinstance(data, dict):
            raise JiraSkillError(f"Unexpected response shape for issue {issue_key}.")
        return data

    async def get_comments(self, issue_key: str, *, max_results: int = 50) -> list[dict[str, Any]]:
        if not issue_key:
            raise JiraSkillError("Issue key is required.")
        url = f"{self._site_url}/rest/api/3/issue/{issue_key}/comment"
        data = await self._get(url, params={"maxResults": max(1, min(int(max_results), 100))})
        if not isinstance(data, dict):
            return []
        comments = data.get("comments") or []
        result: list[dict[str, Any]] = []
        for c in comments:
            if not isinstance(c, dict):
                continue
            result.append(
                {
                    "id": c.get("id"),
                    "author": (c.get("author") or {}).get("displayName"),
                    "created": c.get("created"),
                    "updated": c.get("updated"),
                    "body": _safe_text(c.get("body")),
                }
            )
        return result

    # ---- write actions (capability-gated by the skill caller; not enabled by default)

    async def update_issue(self, issue_key: str, fields: dict[str, Any]) -> None:
        if not issue_key:
            raise JiraSkillError("Issue key is required.")
        if not isinstance(fields, dict) or not fields:
            raise JiraSkillError("Fields payload is required for update.")
        url = f"{self._site_url}/rest/api/3/issue/{issue_key}"
        await self._put(url, json_body={"fields": fields}, expect_no_content=True)

    async def add_comment(self, issue_key: str, body: str) -> dict[str, Any]:
        if not issue_key:
            raise JiraSkillError("Issue key is required.")
        if not body or not body.strip():
            raise JiraSkillError("Comment body must not be empty.")
        url = f"{self._site_url}/rest/api/3/issue/{issue_key}/comment"
        # Atlassian Document Format envelope for plain text bodies.
        adf_body = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": body}],
                }
            ],
        }
        data = await self._post(url, json_body={"body": adf_body})
        return data if isinstance(data, dict) else {}

    async def list_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        if not issue_key:
            raise JiraSkillError("Issue key is required.")
        url = f"{self._site_url}/rest/api/3/issue/{issue_key}/transitions"
        data = await self._get(url)
        if not isinstance(data, dict):
            return []
        transitions = data.get("transitions") or []
        return [t for t in transitions if isinstance(t, dict)]

    async def transition_issue(self, issue_key: str, transition_id: str) -> None:
        if not issue_key:
            raise JiraSkillError("Issue key is required.")
        if not transition_id:
            raise JiraSkillError("Transition id is required.")
        url = f"{self._site_url}/rest/api/3/issue/{issue_key}/transitions"
        await self._post(
            url,
            json_body={"transition": {"id": str(transition_id)}},
            expect_no_content=True,
        )

    # ----------------------------------------------------------------- private

    async def _get(self, url: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        async with httpx.AsyncClient(timeout=_JIRA_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params, auth=self._auth, headers=self._headers())
        return self._handle_response(response)

    async def _post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        expect_no_content: bool = False,
    ) -> Any:
        async with httpx.AsyncClient(timeout=_JIRA_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=json_body, auth=self._auth, headers=self._headers())
        if expect_no_content and 200 <= response.status_code < 300 and not response.content:
            return None
        return self._handle_response(response)

    async def _put(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        expect_no_content: bool = False,
    ) -> Any:
        async with httpx.AsyncClient(timeout=_JIRA_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.put(url, json=json_body, auth=self._auth, headers=self._headers())
        if expect_no_content and 200 <= response.status_code < 300 and not response.content:
            return None
        return self._handle_response(response)

    @staticmethod
    def _headers() -> dict[str, str]:
        return {"Accept": "application/json", "Content-Type": "application/json"}

    @staticmethod
    def _handle_response(response: httpx.Response) -> Any:
        if 200 <= response.status_code < 300:
            if not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                return None
        # Build a friendly error. Jira often returns {"errorMessages": [...]}.
        message: str
        try:
            payload = response.json()
            if isinstance(payload, dict):
                msgs = payload.get("errorMessages") or []
                if isinstance(msgs, list) and msgs:
                    message = "; ".join(str(m) for m in msgs)
                else:
                    errs = payload.get("errors")
                    message = str(errs) if errs else f"HTTP {response.status_code}"
            else:
                message = f"HTTP {response.status_code}"
        except ValueError:
            message = f"HTTP {response.status_code}"
        raise JiraSkillError(
            f"Jira API error ({response.status_code}): {message}",
            status_code=response.status_code,
        )
