"""GitHub commit-polling trigger — notify on WhatsApp when commits land on a branch.

Mirrors :class:`channels.github_projects.trigger.GitHubProjectsTrigger` (interval
polling + the notification-only auto-flow), but commits on a branch are **linear**,
so this advances a single ``last_seen_sha`` cursor (like ``channels.jira.trigger``)
instead of diffing a per-item snapshot — no extra state table needed.

GitHub *does* emit ``push`` webhooks, but they can't reach this deployment (the
public origin sits behind a Cloudflare WAF source-IP allowlist), so we poll the
REST commits API **outbound** and diff SHAs. Each new commit is composed into a
deterministic WhatsApp message (``payload["message"]``) and dispatched; the bound
system-managed Flow's Notification node renders ``{{source.payload.message}}`` —
**no LLM call per commit.**

The diff/compose/dedupe helpers are module-level **pure functions** so they unit
test on plain dicts with no PAT or DB.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Optional

from sqlalchemy.orm import Session

from channels.trigger import Trigger
from channels.types import HealthResult, TriggerEvent
from hub.github.github_repository_service import GitHubRepositoryError, GitHubRepositoryService
from models import GitHubCommitsChannelInstance
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService


logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL = 300
# Newest-first page size AND the per-poll emission cap. If more than this many
# commits land between two polls the oldest overflow is skipped (the cursor still
# jumps to the newest SHA, so we never re-walk them) — a deliberate flood guard.
_DEFAULT_MAX_COMMITS = 20
_EVENT_TYPE = "github_commits.commit"


def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO8601 string to a naive-UTC datetime (matches the rest of the codebase)."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@dataclass(frozen=True)
class GitHubCommitsPollResult:
    """Summary of one GitHub commits trigger poll."""

    instance_id: int
    tenant_id: str
    status: str
    fetched_count: int = 0
    event_count: int = 0
    dispatched_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    seeded: bool = False
    reason: Optional[str] = None
    dispatch_statuses: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = field(default_factory=datetime.utcnow)


# --------------------------------------------------------------------------- pure diff/compose

def commit_sha(commit: dict[str, Any]) -> Optional[str]:
    sha = commit.get("sha") if isinstance(commit, dict) else None
    return str(sha) if sha else None


def short_sha(sha: Optional[str]) -> str:
    return (sha or "")[:7] if sha else "???????"


def commit_summary(commit: dict[str, Any]) -> str:
    """First non-empty line of the commit message, trimmed."""
    body = (commit.get("commit") or {}).get("message") if isinstance(commit, dict) else None
    text = str(body or "").strip()
    if not text:
        return "(no message)"
    first_line = text.splitlines()[0].strip()
    return (first_line[:200]) if first_line else "(no message)"


def commit_author(commit: dict[str, Any]) -> str:
    """Prefer the GitHub login, fall back to the git author name."""
    if not isinstance(commit, dict):
        return "unknown"
    gh_author = commit.get("author")
    if isinstance(gh_author, dict) and gh_author.get("login"):
        return str(gh_author["login"])
    git_author = (commit.get("commit") or {}).get("author") or {}
    name = git_author.get("name") if isinstance(git_author, dict) else None
    return str(name) if name else "unknown"


def commit_timestamp(commit: dict[str, Any]) -> Optional[str]:
    git_author = (commit.get("commit") or {}).get("author") if isinstance(commit, dict) else None
    if isinstance(git_author, dict):
        return git_author.get("date")
    return None


def compute_new_commits(
    stored_sha: Optional[str],
    commits: list[dict[str, Any]],
    *,
    is_first_poll: bool,
) -> list[dict[str, Any]]:
    """Pure diff of GitHub's newest-first commit page → new commits **oldest-first**.

    **First poll seeds silently** (returns ``[]``) so an initial sync never
    backfills the branch's whole history as notifications.

    When ``stored_sha`` is not present in the fetched page — the cursor "fell off
    the end" because more than the page size landed at once, or the branch was
    force-pushed — every fetched commit is treated as new. The dispatch-side
    dedupe (one claim per SHA) still prevents duplicate notifications.
    """
    if is_first_poll:
        return []
    new_list: list[dict[str, Any]] = []
    for commit in commits or []:
        sha = commit_sha(commit)
        if stored_sha and sha and sha == stored_sha:
            break
        new_list.append(commit)
    new_list.reverse()  # oldest-first → notifications arrive in commit order
    return new_list


def compose_message(commit: dict[str, Any], repo_full: str, branch: Optional[str]) -> str:
    """Deterministic WhatsApp text for one commit (no LLM)."""
    ref = f"{repo_full}@{branch}" if branch else repo_full
    who = commit_author(commit)
    summary = commit_summary(commit)
    sha = commit_sha(commit)
    url = commit.get("html_url") if isinstance(commit, dict) else None
    url_suffix = f" {url}" if url else ""
    return f'🔨 New commit on {ref}: "{summary}" — {who} ({short_sha(sha)}).{url_suffix}'


def dedupe_key(instance_id: int, sha: Optional[str]) -> str:
    """Stable per-commit dedupe key (claimed once in ``ChannelEventDedupe``)."""
    return f"gh_commit:{instance_id}:{sha or 'unknown'}"


# --------------------------------------------------------------------------- trigger

class GitHubCommitsTrigger(Trigger):
    """Poll a repo branch's commits, diff SHAs, dispatch per-commit notifications."""

    channel_type: ClassVar[str] = "github_commits"
    delivery_mode: ClassVar[str] = "poll"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = False
    text_chunk_limit: ClassVar[int] = 16000

    def __init__(
        self,
        db_session: Session,
        instance_id: int,
        log: logging.Logger,
        dispatcher: Optional[TriggerDispatchService] = None,
    ) -> None:
        self.db = db_session
        self.instance_id = instance_id
        self.logger = log
        self.dispatcher = dispatcher or TriggerDispatchService(db_session)

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def poll_or_receive(self) -> list[TriggerEvent]:
        """Scheduler-driven polling uses ``poll_active``; nothing to return here."""
        return []

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        """Forward an already-normalized TriggerEvent through the dispatcher (parity with Jira)."""
        self.dispatcher.dispatch(
            TriggerDispatchInput(
                trigger_type=event.trigger_type,
                instance_id=event.instance_id,
                event_type=event.event_type,
                dedupe_key=event.dedupe_key,
                payload=event.payload,
                occurred_at=event.occurred_at,
                importance=event.importance,
                explicit_agent_id=event.matched_agent_id,
            )
        )

    def validate_recipient(self, recipient: str) -> bool:
        return True

    async def health_check(self) -> HealthResult:
        instance = self._load_instance()
        if instance is None:
            return HealthResult(healthy=False, status="error", detail="GitHub commits trigger not found")
        if not instance.is_active or instance.status == "paused":
            return HealthResult(healthy=False, status="paused", detail="GitHub commits trigger paused")
        return HealthResult(
            healthy=(instance.health_status == "healthy"),
            status=instance.health_status or "unknown",
            detail=instance.health_status_reason,
        )

    def _load_instance(self) -> Optional[GitHubCommitsChannelInstance]:
        return (
            self.db.query(GitHubCommitsChannelInstance)
            .filter_by(id=self.instance_id)
            .first()
        )

    def _event_to_dispatch_input(
        self,
        commit: dict[str, Any],
        instance: GitHubCommitsChannelInstance,
        repo_full: str,
        branch: Optional[str],
    ) -> TriggerDispatchInput:
        sha = commit_sha(commit)
        message = compose_message(commit, repo_full, branch)
        payload = {
            # The Notification node renders {{source.payload.message}} verbatim.
            "message": message,
            "notification_state": "commit",
            "repo": repo_full,
            "repo_owner": instance.repo_owner,
            "repo_name": instance.repo_name,
            "branch": branch,
            "sha": sha,
            "short_sha": short_sha(sha),
            "commit_message": commit_summary(commit),
            "author": commit_author(commit),
            "url": commit.get("html_url"),
            "committed_at": commit_timestamp(commit),
        }
        return TriggerDispatchInput(
            trigger_type=self.channel_type,
            instance_id=instance.id,
            event_type=_EVENT_TYPE,
            dedupe_key=dedupe_key(instance.id, sha),
            payload=payload,
            occurred_at=_parse_iso(commit_timestamp(commit)) or datetime.utcnow(),
            importance="normal",
            explicit_agent_id=instance.default_agent_id,
            sender_key=commit_author(commit),
            source_id=sha,
        )

    @classmethod
    async def poll_active(
        cls,
        db: Session,
        *,
        dispatcher_factory: Optional[type[TriggerDispatchService]] = None,
        force: bool = False,
    ) -> list[GitHubCommitsPollResult]:
        """Poll every due active GitHub commits trigger."""
        rows = (
            db.query(GitHubCommitsChannelInstance)
            .filter(
                GitHubCommitsChannelInstance.is_active == True,  # noqa: E712
                GitHubCommitsChannelInstance.status == "active",
            )
            .order_by(GitHubCommitsChannelInstance.id.asc())
            .all()
        )
        results: list[GitHubCommitsPollResult] = []
        for instance in rows:
            if not force and not cls._is_due(instance):
                results.append(
                    GitHubCommitsPollResult(
                        instance_id=instance.id,
                        tenant_id=instance.tenant_id,
                        status="skipped",
                        reason="poll_interval_not_elapsed",
                    )
                )
                continue
            results.append(
                await cls.poll_instance(db, instance, dispatcher_factory=dispatcher_factory, force=True)
            )
        return results

    @classmethod
    async def poll_instance(
        cls,
        db: Session,
        instance: GitHubCommitsChannelInstance,
        *,
        dispatcher_factory: Optional[type[TriggerDispatchService]] = None,
        force: bool = False,
    ) -> GitHubCommitsPollResult:
        """Poll one repo branch: fetch commits → diff SHAs → dispatch → advance cursor."""
        if not instance.is_active or instance.status != "active":
            return GitHubCommitsPollResult(
                instance_id=instance.id, tenant_id=instance.tenant_id,
                status="skipped", reason="inactive_instance",
            )
        if not force and not cls._is_due(instance):
            return GitHubCommitsPollResult(
                instance_id=instance.id, tenant_id=instance.tenant_id,
                status="skipped", reason="poll_interval_not_elapsed",
            )

        started_at = datetime.utcnow()
        try:
            service = GitHubRepositoryService(db, instance.tenant_id, instance.github_integration_id)
            branch = (instance.branch or "").strip() or None
            commits = await service.list_commits(
                instance.repo_owner,
                instance.repo_name,
                sha=branch,
                max_results=_DEFAULT_MAX_COMMITS,
            )
            is_first_poll = instance.seeded_at is None
            new_commits = compute_new_commits(instance.last_seen_sha, commits, is_first_poll=is_first_poll)
            repo_full = f"{instance.repo_owner}/{instance.repo_name}"

            dispatcher = (dispatcher_factory or TriggerDispatchService)(db)
            adapter = cls(db, instance.id, logging.getLogger(__name__), dispatcher)
            dispatch_statuses: list[str] = []
            for commit in new_commits:
                result = dispatcher.dispatch(adapter._event_to_dispatch_input(commit, instance, repo_full, branch))
                dispatch_statuses.append(result.status)

            # Advance the cursor to the newest fetched SHA so the next poll only
            # walks commits above it (and overflow beyond the page is not re-walked).
            if commits:
                newest = commit_sha(commits[0])
                if newest:
                    instance.last_seen_sha = newest

            instance.last_health_check = started_at
            instance.health_status = "healthy"
            instance.health_status_reason = None
            if is_first_poll:
                instance.seeded_at = started_at
            if any(s == "dispatched" for s in dispatch_statuses):
                instance.last_activity_at = started_at
            db.add(instance)
            db.commit()

            return GitHubCommitsPollResult(
                instance_id=instance.id,
                tenant_id=instance.tenant_id,
                status="ok",
                fetched_count=len(commits),
                event_count=len(new_commits),
                dispatched_count=sum(1 for s in dispatch_statuses if s == "dispatched"),
                duplicate_count=sum(1 for s in dispatch_statuses if s == "duplicate"),
                skipped_count=sum(1 for s in dispatch_statuses if s not in {"dispatched", "duplicate"}),
                seeded=is_first_poll,
                dispatch_statuses=dispatch_statuses,
            )
        except Exception as exc:  # noqa: BLE001 — surface as unhealthy, never crash the poll loop
            reason = (
                f"github_commits_poll_failed:{str(exc)[:300]}"
                if isinstance(exc, GitHubRepositoryError)
                else f"github_commits_poll_failed:{type(exc).__name__}"
            )
            logging.getLogger(__name__).warning(
                "GitHub commits trigger %s poll failed: %s", instance.id, type(exc).__name__
            )
            return cls._mark_unhealthy(db, instance, reason=reason, status="error")

    @staticmethod
    def _is_due(instance: GitHubCommitsChannelInstance) -> bool:
        if instance.last_health_check is None:
            return True
        elapsed = (datetime.utcnow() - instance.last_health_check).total_seconds()
        return elapsed >= int(instance.poll_interval_seconds or _DEFAULT_POLL_INTERVAL)

    @staticmethod
    def _mark_unhealthy(
        db: Session,
        instance: GitHubCommitsChannelInstance,
        *,
        reason: str,
        status: str,
    ) -> GitHubCommitsPollResult:
        db.rollback()
        instance.last_health_check = datetime.utcnow()
        instance.health_status = "unhealthy"
        instance.health_status_reason = reason[:500]
        db.add(instance)
        db.commit()
        return GitHubCommitsPollResult(
            instance_id=instance.id,
            tenant_id=instance.tenant_id,
            status=status,
            reason=reason,
        )
