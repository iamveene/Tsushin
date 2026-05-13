"""Async GitHub REST client used by the Code Repository skill.

Read/write counterpart to the GitHub trigger webhook receiver. Mirrors
:class:`hub.jira.jira_ticket_service.JiraTicketService` exactly: tenant-scoped,
loads its :class:`models.GitHubIntegration` row on construction, decrypts the
PAT once, and never logs the credential.

Capabilities:
- ``search_repositories`` — GET ``/search/repositories?q=...``
- ``list_pull_requests`` — GET ``/repos/{o}/{r}/pulls?state=...``
- ``get_pull_request`` — GET ``/repos/{o}/{r}/pulls/{number}``
- ``list_issues`` — GET ``/repos/{o}/{r}/issues?state=...`` (filters PRs out)
- ``get_issue`` — GET ``/repos/{o}/{r}/issues/{number}``
- ``get_repository`` — GET ``/repos/{o}/{r}`` (used by test-connection)
- ``create_issue`` — POST ``/repos/{o}/{r}/issues`` (write — gated by skill)
- ``add_pr_comment`` — POST ``/repos/{o}/{r}/issues/{number}/comments`` (write)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from models import GitHubIntegration
from services.github_integration_service import (
    GITHUB_API_BASE_URL,
    decrypt_github_pat,
    load_github_integration,
)


logger = logging.getLogger(__name__)


_GITHUB_HTTP_TIMEOUT_SECONDS = 15.0

# GitHub allows letters, digits, dashes, dots, and underscores in repo
# owners/names. Reject anything that doesn't match — it would either 404 or
# leak path traversal upstream.
_GITHUB_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_owner(owner: str) -> str:
    if not owner or not _GITHUB_OWNER_REPO_RE.match(owner):
        raise GitHubRepositoryError(
            f"Invalid owner '{owner}'. Owners must match [A-Za-z0-9._-]+."
        )
    return owner


def _validate_repo(repo: str) -> str:
    if not repo or not _GITHUB_OWNER_REPO_RE.match(repo):
        raise GitHubRepositoryError(
            f"Invalid repo '{repo}'. Repos must match [A-Za-z0-9._-]+."
        )
    return repo


class GitHubRepositoryError(Exception):
    """Raised for any expected error path the skill should surface to the LLM."""

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class GitHubPullRequestSummary:
    number: int
    title: str
    state: str
    author: Optional[str]
    base_branch: Optional[str]
    head_branch: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    url: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class GitHubIssueSummary:
    number: int
    title: str
    state: str
    author: Optional[str]
    labels: list[str]
    created_at: Optional[str]
    url: str
    raw: dict[str, Any]


def _summarize_pr(pr: dict[str, Any]) -> GitHubPullRequestSummary:
    user = pr.get("user") or {}
    base = pr.get("base") or {}
    head = pr.get("head") or {}
    return GitHubPullRequestSummary(
        number=int(pr.get("number") or 0),
        title=pr.get("title") or "",
        state=pr.get("state") or "unknown",
        author=user.get("login") if isinstance(user, dict) else None,
        base_branch=base.get("ref") if isinstance(base, dict) else None,
        head_branch=head.get("ref") if isinstance(head, dict) else None,
        created_at=pr.get("created_at"),
        updated_at=pr.get("updated_at"),
        url=pr.get("html_url") or "",
        raw=pr,
    )


def _summarize_issue(issue: dict[str, Any]) -> GitHubIssueSummary:
    user = issue.get("user") or {}
    raw_labels = issue.get("labels") or []
    labels: list[str] = []
    for lbl in raw_labels:
        if isinstance(lbl, dict) and lbl.get("name"):
            labels.append(str(lbl["name"]))
        elif isinstance(lbl, str):
            labels.append(lbl)
    return GitHubIssueSummary(
        number=int(issue.get("number") or 0),
        title=issue.get("title") or "",
        state=issue.get("state") or "unknown",
        author=user.get("login") if isinstance(user, dict) else None,
        labels=labels,
        created_at=issue.get("created_at"),
        url=issue.get("html_url") or "",
        raw=issue,
    )


class GitHubRepositoryService:
    """Thin async client over the GitHub REST API v3.

    One instance is bound to one :class:`models.GitHubIntegration` row
    (tenant-scoped). The PAT is decrypted on construction and held in
    memory only — no plaintext is logged.
    """

    def __init__(self, db: Session, tenant_id: str, integration_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id
        integration = load_github_integration(
            db, tenant_id=tenant_id, integration_id=integration_id, require_active=False
        )
        if integration is None:
            raise GitHubRepositoryError(
                f"GitHub integration {integration_id} not found for tenant {tenant_id}.",
                status_code=404,
            )
        if not integration.is_active:
            raise GitHubRepositoryError(
                "GitHub integration is disabled. Re-enable it in Hub > API and Tools.",
            )
        token = decrypt_github_pat(db, tenant_id, integration.pat_token_encrypted)
        if not token:
            raise GitHubRepositoryError(
                "GitHub integration is missing credentials. Edit it in Hub > API and Tools and re-enter the PAT.",
            )
        self._integration = integration
        self._site_url = GITHUB_API_BASE_URL.rstrip("/")
        self._token = token

    # ------------------------------------------------------------------ public

    @property
    def integration(self) -> GitHubIntegration:
        return self._integration

    @property
    def site_url(self) -> str:
        return self._site_url

    @property
    def default_owner(self) -> Optional[str]:
        return self._integration.default_owner

    @property
    def default_repo(self) -> Optional[str]:
        return self._integration.default_repo

    # ---- read actions

    async def search_repositories(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        if not query or not query.strip():
            raise GitHubRepositoryError("Query must not be empty.")
        per_page = max(1, min(int(max_results), 100))
        url = f"{self._site_url}/search/repositories"
        data = await self._get(url, params={"q": query.strip(), "per_page": per_page})
        items = data.get("items") if isinstance(data, dict) else None
        return list(items) if isinstance(items, list) else []

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        max_results: int = 20,
    ) -> list[GitHubPullRequestSummary]:
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        state = (state or "open").strip().lower()
        if state not in {"open", "closed", "all"}:
            raise GitHubRepositoryError(
                f"Invalid state '{state}'. Must be one of: open, closed, all."
            )
        per_page = max(1, min(int(max_results), 100))
        url = f"{self._site_url}/repos/{owner}/{repo}/pulls"
        data = await self._get(url, params={"state": state, "per_page": per_page})
        if not isinstance(data, list):
            return []
        return [_summarize_pr(pr) for pr in data if isinstance(pr, dict)]

    async def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not number:
            raise GitHubRepositoryError("PR number is required.")
        url = f"{self._site_url}/repos/{owner}/{repo}/pulls/{int(number)}"
        data = await self._get(url)
        if not isinstance(data, dict):
            raise GitHubRepositoryError(f"Unexpected response shape for PR #{number}.")
        return data

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        max_results: int = 20,
    ) -> list[GitHubIssueSummary]:
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        state = (state or "open").strip().lower()
        if state not in {"open", "closed", "all"}:
            raise GitHubRepositoryError(
                f"Invalid state '{state}'. Must be one of: open, closed, all."
            )
        per_page = max(1, min(int(max_results), 100))
        url = f"{self._site_url}/repos/{owner}/{repo}/issues"
        data = await self._get(url, params={"state": state, "per_page": per_page})
        if not isinstance(data, list):
            return []
        # GitHub's /issues endpoint returns PRs alongside issues. Filter PRs out
        # so the LLM sees a clean issues-only list (PRs are returned separately
        # by list_pull_requests).
        result: list[GitHubIssueSummary] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            if "pull_request" in item:
                continue
            result.append(_summarize_issue(item))
        return result

    async def get_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not number:
            raise GitHubRepositoryError("Issue number is required.")
        url = f"{self._site_url}/repos/{owner}/{repo}/issues/{int(number)}"
        data = await self._get(url)
        if not isinstance(data, dict):
            raise GitHubRepositoryError(f"Unexpected response shape for issue #{number}.")
        return data

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        """Used by test-connection to verify both auth and repo accessibility."""
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        url = f"{self._site_url}/repos/{owner}/{repo}"
        data = await self._get(url)
        if not isinstance(data, dict):
            raise GitHubRepositoryError(
                f"Unexpected response shape for repo {owner}/{repo}."
            )
        return data

    # ---- write actions (capability-gated upstream by the skill caller)

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        *,
        body: Optional[str] = None,
        labels: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not title or not title.strip():
            raise GitHubRepositoryError("Issue title is required.")
        payload: dict[str, Any] = {"title": title.strip()}
        if body is not None and body.strip():
            payload["body"] = body
        if labels:
            payload["labels"] = [str(lbl) for lbl in labels if str(lbl).strip()]
        url = f"{self._site_url}/repos/{owner}/{repo}/issues"
        data = await self._post(url, json_body=payload)
        return data if isinstance(data, dict) else {}

    async def add_pr_comment(
        self,
        owner: str,
        repo: str,
        number: int,
        body: str,
    ) -> dict[str, Any]:
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not number:
            raise GitHubRepositoryError("PR number is required.")
        if not body or not body.strip():
            raise GitHubRepositoryError("Comment body must not be empty.")
        # Note: GitHub treats PRs as issues for the basic comment endpoint —
        # this is the canonical way to comment on a PR thread.
        url = f"{self._site_url}/repos/{owner}/{repo}/issues/{int(number)}/comments"
        data = await self._post(url, json_body={"body": body})
        return data if isinstance(data, dict) else {}

    # ---- PR workflow write actions (capability-gated upstream by the skill) ----

    async def approve_pull_request(
        self,
        owner: str,
        repo: str,
        number: int,
        body: Optional[str] = None,
    ) -> dict[str, Any]:
        """POST a PR review with event=APPROVE — the agent's "accept" action."""
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not number:
            raise GitHubRepositoryError("PR number is required.")
        url = f"{self._site_url}/repos/{owner}/{repo}/pulls/{int(number)}/reviews"
        payload: dict[str, Any] = {"event": "APPROVE"}
        if body and body.strip():
            payload["body"] = body
        data = await self._post(url, json_body=payload)
        return data if isinstance(data, dict) else {}

    async def request_changes(
        self,
        owner: str,
        repo: str,
        number: int,
        body: str,
    ) -> dict[str, Any]:
        """POST a PR review with event=REQUEST_CHANGES."""
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not number:
            raise GitHubRepositoryError("PR number is required.")
        if not body or not body.strip():
            raise GitHubRepositoryError("Body is required when requesting changes.")
        url = f"{self._site_url}/repos/{owner}/{repo}/pulls/{int(number)}/reviews"
        data = await self._post(url, json_body={"event": "REQUEST_CHANGES", "body": body})
        return data if isinstance(data, dict) else {}

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        number: int,
        merge_method: str = "merge",
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> dict[str, Any]:
        """PUT /repos/{o}/{r}/pulls/{n}/merge. merge_method ∈ {merge, squash, rebase}."""
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not number:
            raise GitHubRepositoryError("PR number is required.")
        if merge_method not in ("merge", "squash", "rebase"):
            raise GitHubRepositoryError(f"Invalid merge_method '{merge_method}'. Use one of: merge, squash, rebase.")
        url = f"{self._site_url}/repos/{owner}/{repo}/pulls/{int(number)}/merge"
        payload: dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        if commit_message:
            payload["commit_message"] = commit_message
        data = await self._put(url, json_body=payload)
        return data if isinstance(data, dict) else {}

    async def close_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        """PATCH the PR's underlying issue to state=closed (without merging)."""
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not number:
            raise GitHubRepositoryError("PR number is required.")
        url = f"{self._site_url}/repos/{owner}/{repo}/pulls/{int(number)}"
        data = await self._patch(url, json_body={"state": "closed"})
        return data if isinstance(data, dict) else {}

    async def close_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        owner = _validate_owner(owner)
        repo = _validate_repo(repo)
        if not number:
            raise GitHubRepositoryError("Issue number is required.")
        url = f"{self._site_url}/repos/{owner}/{repo}/issues/{int(number)}"
        data = await self._patch(url, json_body={"state": "closed"})
        return data if isinstance(data, dict) else {}

    # ----------------------------------------------------------------- private

    async def _get(self, url: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        async with httpx.AsyncClient(timeout=_GITHUB_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params, headers=self._headers())
        return self._handle_response(response)

    async def _post(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        expect_no_content: bool = False,
    ) -> Any:
        async with httpx.AsyncClient(timeout=_GITHUB_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=json_body, headers=self._headers())
        if expect_no_content and 200 <= response.status_code < 300 and not response.content:
            return None
        return self._handle_response(response)

    async def _put(self, url: str, *, json_body: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=_GITHUB_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.put(url, json=json_body, headers=self._headers())
        return self._handle_response(response)

    async def _patch(self, url: str, *, json_body: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=_GITHUB_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.patch(url, json=json_body, headers=self._headers())
        return self._handle_response(response)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _handle_response(response: httpx.Response) -> Any:
        if 200 <= response.status_code < 300:
            if not response.content:
                return None
            try:
                return response.json()
            except ValueError:
                return None
        # GitHub error envelope: {"message": "...", "documentation_url": "..."}
        message: str
        try:
            payload = response.json()
            if isinstance(payload, dict):
                msg = payload.get("message")
                message = str(msg) if msg else f"HTTP {response.status_code}"
            else:
                message = f"HTTP {response.status_code}"
        except ValueError:
            message = f"HTTP {response.status_code}"
        raise GitHubRepositoryError(
            f"GitHub API error ({response.status_code}): {message}",
            status_code=response.status_code,
        )
