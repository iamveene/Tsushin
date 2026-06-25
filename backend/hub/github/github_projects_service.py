"""Async GitHub **GraphQL** client for Projects v2 (the new Projects).

Companion to :class:`hub.github.github_repository_service.GitHubRepositoryService`
(which is REST-only). Projects v2 is GraphQL-only — the REST API does not cover
it — so this client speaks to ``https://api.github.com/graphql``.

Mirrors the REST client's construction exactly: tenant-scoped, loads its
:class:`models.GitHubIntegration` row on construction, decrypts the PAT once,
and never logs the credential.

Used by:
- the **GitHub Projects polling trigger** (board state diffing), and
- the **Code Repository skill** read actions (``list_projects`` / ``read_project``
  / ``list_project_items``).

Required PAT scope: classic ``read:project`` (fine-grained: Projects=Read). The
client surfaces a clear, actionable error when the token lacks it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from services.github_integration_service import (
    GITHUB_API_BASE_URL,
    decrypt_github_pat,
    load_github_integration,
)


logger = logging.getLogger(__name__)


_GITHUB_HTTP_TIMEOUT_SECONDS = 15.0
_ITEMS_PAGE_SIZE = 50
_MAX_ITEM_PAGES = 40  # hard ceiling (~2000 items) to bound a runaway poll
_STATUS_FIELD_NAME = "Status"


class GitHubProjectsError(Exception):
    """Raised for any expected error path the caller should surface (skill/UI).

    ``status_code`` mirrors :class:`GitHubRepositoryError` so route handlers can
    map it to an HTTP response uniformly.
    """

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# --------------------------------------------------------------------------- GraphQL documents

_PROJECT_BY_OWNER = """
query($owner: String!, $number: Int!) {
  %s(login: $owner) {
    projectV2(number: $number) { id title url number closed }
  }
}
"""

_PROJECTS_LIST = """
query($owner: String!, $first: Int!) {
  %s(login: $owner) {
    projectsV2(first: $first) {
      nodes { id title url number closed shortDescription }
    }
  }
}
"""

_PROJECT_ITEMS = """
query($projectId: ID!, $first: Int!, $after: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          type
          isArchived
          updatedAt
          content {
            ... on Issue { title number url assignees(first: 10) { nodes { login } } }
            ... on PullRequest { title number url assignees(first: 10) { nodes { login } } }
            ... on DraftIssue { title }
          }
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field { ... on ProjectV2SingleSelectField { name } }
              }
            }
          }
        }
      }
    }
  }
}
"""


class GitHubProjectsService:
    """Tenant-scoped GraphQL client bound to one ``GitHubIntegration`` row."""

    def __init__(self, db: Session, tenant_id: str, integration_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id
        integration = load_github_integration(
            db, tenant_id=tenant_id, integration_id=integration_id, require_active=False
        )
        if integration is None:
            raise GitHubProjectsError(
                f"GitHub integration {integration_id} not found for tenant {tenant_id}.",
                status_code=404,
            )
        if not integration.is_active:
            raise GitHubProjectsError(
                "GitHub integration is disabled. Re-enable it in Hub > API and Tools.",
            )
        token = decrypt_github_pat(db, tenant_id, integration.pat_token_encrypted)
        if not token:
            raise GitHubProjectsError(
                "GitHub integration is missing credentials. Edit it in Hub > API and Tools and re-enter the PAT.",
            )
        self._integration = integration
        self._endpoint = f"{GITHUB_API_BASE_URL.rstrip('/')}/graphql"
        self._token = token

    # ------------------------------------------------------------------ public

    @property
    def integration(self):
        return self._integration

    async def get_project_id(self, owner: str, number: int) -> str:
        """Resolve a board's GraphQL node id from ``owner`` + project ``number``.

        Tries the ``user`` namespace first (ByteSiege is user-owned), then falls
        back to ``organization``. Raises if neither resolves or scope is missing.
        """
        info = await self._resolve_project(owner, number)
        return info["id"]

    async def test_connection(self, owner: str, number: int) -> dict[str, Any]:
        """Verify the PAT can read the board (i.e. carries ``read:project``).

        Returns ``{ok, project_node_id, title, url, scopes}``. Raises
        :class:`GitHubProjectsError` with an actionable message on failure (the
        most important being a missing ``read:project`` scope).
        """
        info = await self._resolve_project(owner, number)
        return {
            "ok": True,
            "project_node_id": info["id"],
            "title": info.get("title"),
            "url": info.get("url"),
            "number": info.get("number"),
        }

    async def list_projects(self, owner: str, *, first: int = 20) -> list[dict[str, Any]]:
        """List the owner's Projects v2 boards (for the skill read action)."""
        first = max(1, min(int(first), 50))
        for namespace in ("user", "organization"):
            data, _ = await self._graphql(
                _PROJECTS_LIST % namespace, {"owner": owner, "first": first}
            )
            holder = (data or {}).get(namespace)
            if holder and holder.get("projectsV2"):
                nodes = holder["projectsV2"].get("nodes") or []
                return [n for n in nodes if isinstance(n, dict)]
        return []

    async def read_project(self, owner: str, number: int) -> dict[str, Any]:
        """Return one board's metadata (for the skill read action)."""
        return await self._resolve_project(owner, number)

    async def fetch_board_items(self, project_node_id: str) -> list[dict[str, Any]]:
        """Page through all items and return **normalized** snapshot dicts.

        Each dict: ``{item_node_id, content_type, title, url, status_value,
        assignees: list[str], updated_at, is_archived}``. Normalization lives
        here so the trigger's diff engine stays pure and unit-testable on plain
        dicts (no GraphQL shape leaks downstream).
        """
        items: list[dict[str, Any]] = []
        after: Optional[str] = None
        for _ in range(_MAX_ITEM_PAGES):
            data, _errors = await self._graphql(
                _PROJECT_ITEMS,
                {"projectId": project_node_id, "first": _ITEMS_PAGE_SIZE, "after": after},
            )
            node = (data or {}).get("node") or {}
            container = node.get("items") or {}
            for raw in container.get("nodes") or []:
                if isinstance(raw, dict):
                    items.append(self._normalize_item(raw))
            page = container.get("pageInfo") or {}
            if page.get("hasNextPage") and page.get("endCursor"):
                after = page["endCursor"]
                continue
            break
        return items

    # ------------------------------------------------------------------ internals

    async def _resolve_project(self, owner: str, number: int) -> dict[str, Any]:
        owner = (owner or "").strip()
        if not owner:
            raise GitHubProjectsError("Project owner is required.")
        try:
            number = int(number)
        except (TypeError, ValueError):
            raise GitHubProjectsError("Project number must be an integer.")

        last_namespace_errors: list[dict] = []
        for namespace in ("user", "organization"):
            data, errors = await self._graphql(
                _PROJECT_BY_OWNER % namespace, {"owner": owner, "number": number}
            )
            holder = (data or {}).get(namespace)
            project = holder.get("projectV2") if isinstance(holder, dict) else None
            if project:
                return project
            if errors:
                last_namespace_errors = errors
        raise GitHubProjectsError(
            f"Project #{number} not found for owner '{owner}' (checked user and organization). "
            f"Confirm the project URL and that the PAT can see it."
            + (f" Details: {last_namespace_errors[0].get('message')}" if last_namespace_errors else ""),
            status_code=404,
        )

    @staticmethod
    def _normalize_item(raw: dict[str, Any]) -> dict[str, Any]:
        content = raw.get("content") or {}
        assignees: list[str] = []
        a_holder = content.get("assignees") or {}
        for a in a_holder.get("nodes") or []:
            login = (a or {}).get("login")
            if login:
                assignees.append(login)

        status_value: Optional[str] = None
        fv_holder = raw.get("fieldValues") or {}
        for fv in fv_holder.get("nodes") or []:
            if not isinstance(fv, dict) or not fv:
                continue
            field = fv.get("field") or {}
            if str(field.get("name") or "").strip().lower() == _STATUS_FIELD_NAME.lower():
                status_value = fv.get("name")
                break

        return {
            "item_node_id": raw.get("id"),
            "content_type": raw.get("type"),
            "title": content.get("title"),
            "url": content.get("url"),
            "status_value": status_value,
            "assignees": assignees,
            "updated_at": raw.get("updatedAt"),
            "is_archived": bool(raw.get("isArchived")),
        }

    async def _graphql(
        self, query: str, variables: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """POST a GraphQL document. Returns ``(data, errors)``.

        Raises :class:`GitHubProjectsError` on transport/HTTP failures and on a
        missing ``read:project`` scope (detected from the error envelope +
        ``x-accepted-oauth-scopes`` / ``x-oauth-scopes`` headers). Non-fatal
        per-field errors (e.g. NOT_FOUND when probing user-vs-org) are returned
        for the caller to interpret.
        """
        try:
            async with httpx.AsyncClient(timeout=_GITHUB_HTTP_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    self._endpoint,
                    json={"query": query, "variables": variables},
                    headers=self._headers(),
                )
        except httpx.HTTPError as exc:  # network/timeout
            raise GitHubProjectsError(f"GitHub GraphQL request failed: {exc}") from exc

        if response.status_code == 401:
            raise GitHubProjectsError(
                "GitHub rejected the PAT (401). Re-enter a valid token in Hub > API and Tools.",
                status_code=401,
            )
        if response.status_code == 403:
            self._raise_for_scope(response)
            raise GitHubProjectsError(
                "GitHub denied the GraphQL request (403). The PAT may lack permissions or be rate-limited.",
                status_code=403,
            )
        if not (200 <= response.status_code < 300):
            raise GitHubProjectsError(
                f"GitHub GraphQL error (HTTP {response.status_code}).",
                status_code=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError:
            raise GitHubProjectsError("GitHub GraphQL returned a non-JSON response.")

        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            self._raise_for_scope(response, errors=errors)
        data = payload.get("data") if isinstance(payload, dict) else None
        return (data or {}), (errors or [])

    @staticmethod
    def _raise_for_scope(
        response: httpx.Response, errors: Optional[list[dict[str, Any]]] = None
    ) -> None:
        """Raise an actionable scope error when the PAT lacks ``read:project``."""
        accepted = response.headers.get("x-accepted-oauth-scopes", "")
        have = response.headers.get("x-oauth-scopes", "")
        blob = " ".join(
            str((e or {}).get("message", "")) + " " + str((e or {}).get("type", ""))
            for e in (errors or [])
        ).lower()
        scope_signal = (
            "insufficient_scopes" in blob
            or "read:project" in blob
            or "resource not accessible" in blob
            or ("project" in (accepted or "").lower() and "project" not in (have or "").lower())
        )
        if scope_signal:
            raise GitHubProjectsError(
                "The configured GitHub PAT is missing the 'read:project' scope required to read "
                "Projects v2 boards. Re-scope the token in GitHub (classic: add 'read:project'; "
                "fine-grained: Projects = Read) and update it in Hub > API and Tools. "
                f"(token scopes: '{have or 'unknown'}')",
                status_code=403,
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
