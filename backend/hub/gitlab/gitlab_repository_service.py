"""Async read-only GitLab.com REST client used by repository integrations."""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from hub.github.github_repository_service import (
    GitHubIssueSummary,
    GitHubPullRequestSummary,
)
from models import GitLabIntegration
from services.gitlab_integration_service import (
    GITLAB_API_BASE_URL,
    decrypt_gitlab_pat,
    load_gitlab_integration,
    normalize_project_path,
)


logger = logging.getLogger(__name__)

_GITLAB_HTTP_TIMEOUT_SECONDS = 20.0


class GitLabRepositoryError(Exception):
    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitLabRepositoryService:
    """Thin async client over GitLab.com REST API v4."""

    def __init__(self, db: Session, tenant_id: str, integration_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id
        integration = load_gitlab_integration(
            db, tenant_id=tenant_id, integration_id=integration_id, require_active=False
        )
        if integration is None:
            raise GitLabRepositoryError(
                f"GitLab integration {integration_id} not found for tenant {tenant_id}.",
                status_code=404,
            )
        if not integration.is_active:
            raise GitLabRepositoryError("GitLab integration is disabled. Re-enable it in Hub > Developer Tools.")
        token = decrypt_gitlab_pat(db, tenant_id, integration.pat_token_encrypted)
        if not token:
            raise GitLabRepositoryError("GitLab integration is missing credentials. Edit it and re-enter the PAT.")
        self._integration = integration
        self._site_url = GITLAB_API_BASE_URL.rstrip("/")
        self._token = token

    @property
    def integration(self) -> GitLabIntegration:
        return self._integration

    @property
    def site_url(self) -> str:
        return self._site_url

    @property
    def default_owner(self) -> Optional[str]:
        return self._integration.default_namespace

    @property
    def default_repo(self) -> Optional[str]:
        return self._integration.default_project

    @property
    def default_project_path(self) -> Optional[str]:
        return self._integration.default_project_path

    async def search_repositories(self, query: str, *, max_results: int = 10) -> list[dict[str, Any]]:
        if not query or not query.strip():
            raise GitLabRepositoryError("Query must not be empty.")
        per_page = max(1, min(int(max_results), 100))
        data = await self._get(
            f"{self._site_url}/projects",
            params={"search": query.strip(), "simple": "true", "per_page": per_page},
        )
        if not isinstance(data, list):
            return []
        return [
            {
                "full_name": item.get("path_with_namespace") or item.get("name_with_namespace"),
                "description": item.get("description"),
                "stargazers_count": item.get("star_count") or 0,
                "html_url": item.get("web_url"),
                "raw": item,
            }
            for item in data
            if isinstance(item, dict)
        ]

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        max_results: int = 20,
    ) -> list[GitHubPullRequestSummary]:
        project = self._resolve_project_path(owner, repo)
        gitlab_state = _gitlab_state(state)
        data = await self._get(
            f"{self._site_url}/projects/{_quote_project(project)}/merge_requests",
            params={"state": gitlab_state, "per_page": max(1, min(int(max_results), 100))},
        )
        if not isinstance(data, list):
            return []
        return [_summarize_mr(item) for item in data if isinstance(item, dict)]

    async def get_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        project = self._resolve_project_path(owner, repo)
        data = await self._get(f"{self._site_url}/projects/{_quote_project(project)}/merge_requests/{int(number)}")
        if not isinstance(data, dict):
            raise GitLabRepositoryError(f"Unexpected response shape for MR !{number}.")
        return _mr_to_github_like(data)

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "open",
        max_results: int = 20,
    ) -> list[GitHubIssueSummary]:
        project = self._resolve_project_path(owner, repo)
        data = await self._get(
            f"{self._site_url}/projects/{_quote_project(project)}/issues",
            params={"state": _gitlab_state(state), "per_page": max(1, min(int(max_results), 100))},
        )
        if not isinstance(data, list):
            return []
        return [_summarize_issue(item) for item in data if isinstance(item, dict)]

    async def get_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        project = self._resolve_project_path(owner, repo)
        data = await self._get(f"{self._site_url}/projects/{_quote_project(project)}/issues/{int(number)}")
        if not isinstance(data, dict):
            raise GitLabRepositoryError(f"Unexpected response shape for issue #{number}.")
        return _issue_to_github_like(data)

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        project = self._resolve_project_path(owner, repo)
        data = await self._get(f"{self._site_url}/projects/{_quote_project(project)}")
        if not isinstance(data, dict):
            raise GitLabRepositoryError(f"Unexpected response shape for project {project}.")
        return data

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        *,
        body: Optional[str] = None,
        labels: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        del owner, repo, title, body, labels
        raise GitLabRepositoryError("GitLab write actions are not supported by this foundation.")

    async def add_pr_comment(self, owner: str, repo: str, number: int, body: str) -> dict[str, Any]:
        del owner, repo, number, body
        raise GitLabRepositoryError("GitLab write actions are not supported by this foundation.")

    async def approve_pull_request(
        self, owner: str, repo: str, number: int, body: Optional[str] = None
    ) -> dict[str, Any]:
        del owner, repo, number, body
        raise GitLabRepositoryError("GitLab write actions are not supported by this foundation.")

    async def request_changes(self, owner: str, repo: str, number: int, body: str) -> dict[str, Any]:
        del owner, repo, number, body
        raise GitLabRepositoryError("GitLab write actions are not supported by this foundation.")

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        number: int,
        merge_method: str = "merge",
        commit_title: Optional[str] = None,
        commit_message: Optional[str] = None,
    ) -> dict[str, Any]:
        del owner, repo, number, merge_method, commit_title, commit_message
        raise GitLabRepositoryError("GitLab write actions are not supported by this foundation.")

    async def close_pull_request(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        del owner, repo, number
        raise GitLabRepositoryError("GitLab write actions are not supported by this foundation.")

    async def close_issue(self, owner: str, repo: str, number: int) -> dict[str, Any]:
        del owner, repo, number
        raise GitLabRepositoryError("GitLab write actions are not supported by this foundation.")

    def _resolve_project_path(self, owner: Optional[str], repo: Optional[str]) -> str:
        explicit = normalize_project_path(f"{owner}/{repo}" if owner and repo else None)
        configured = normalize_project_path(self._integration.default_project_path)
        if explicit:
            return explicit
        if configured:
            return configured
        if self._integration.default_namespace and self._integration.default_project:
            return normalize_project_path(f"{self._integration.default_namespace}/{self._integration.default_project}") or ""
        raise GitLabRepositoryError("GitLab project path is required.")

    async def _get(self, url: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        async with httpx.AsyncClient(timeout=_GITLAB_HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params, headers=self._headers())
        return self._handle_response(response)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "PRIVATE-TOKEN": self._token,
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
        try:
            payload = response.json()
            message = payload.get("message") if isinstance(payload, dict) else None
        except ValueError:
            message = None
        raise GitLabRepositoryError(
            f"GitLab API error ({response.status_code}): {message or f'HTTP {response.status_code}'}",
            status_code=response.status_code,
        )


def _quote_project(project_path: str) -> str:
    normalized = normalize_project_path(project_path)
    if not normalized:
        raise GitLabRepositoryError("GitLab project path is required.")
    return quote(normalized, safe="")


def _gitlab_state(state: str) -> str:
    normalized = (state or "opened").strip().lower()
    mapping = {"open": "opened", "opened": "opened", "closed": "closed", "all": "all"}
    if normalized not in mapping:
        raise GitLabRepositoryError("Invalid state. Must be one of: open, closed, all.")
    return mapping[normalized]


def _summarize_mr(mr: dict[str, Any]) -> GitHubPullRequestSummary:
    return GitHubPullRequestSummary(
        number=int(mr.get("iid") or mr.get("id") or 0),
        title=mr.get("title") or "",
        state=mr.get("state") or "unknown",
        author=_author_username(mr.get("author")),
        base_branch=mr.get("target_branch"),
        head_branch=mr.get("source_branch"),
        created_at=mr.get("created_at"),
        updated_at=mr.get("updated_at"),
        url=mr.get("web_url") or "",
        raw=mr,
    )


def _summarize_issue(issue: dict[str, Any]) -> GitHubIssueSummary:
    return GitHubIssueSummary(
        number=int(issue.get("iid") or issue.get("id") or 0),
        title=issue.get("title") or "",
        state=issue.get("state") or "unknown",
        author=_author_username(issue.get("author")),
        labels=[str(item) for item in (issue.get("labels") or [])],
        created_at=issue.get("created_at"),
        url=issue.get("web_url") or "",
        raw=issue,
    )


def _mr_to_github_like(mr: dict[str, Any]) -> dict[str, Any]:
    author = mr.get("author") if isinstance(mr.get("author"), dict) else {}
    return {
        **mr,
        "number": mr.get("iid") or mr.get("id"),
        "title": mr.get("title"),
        "state": mr.get("state"),
        "user": {"login": _author_username(author)},
        "body": mr.get("description") or "",
        "head": {"ref": mr.get("source_branch")},
        "base": {"ref": mr.get("target_branch")},
        "html_url": mr.get("web_url"),
    }


def _issue_to_github_like(issue: dict[str, Any]) -> dict[str, Any]:
    author = issue.get("author") if isinstance(issue.get("author"), dict) else {}
    return {
        **issue,
        "number": issue.get("iid") or issue.get("id"),
        "title": issue.get("title"),
        "state": issue.get("state"),
        "user": {"login": _author_username(author)},
        "body": issue.get("description") or "",
        "html_url": issue.get("web_url"),
        "labels": [{"name": str(label)} for label in (issue.get("labels") or [])],
    }


def _author_username(author: Any) -> Optional[str]:
    if isinstance(author, dict):
        return author.get("username") or author.get("name")
    return None
