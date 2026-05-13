"""GitHub trigger helpers and trigger entry point."""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime
from typing import Any, ClassVar, Optional

from sqlalchemy.orm import Session

from channels.trigger import Trigger
from channels.types import TriggerEvent


DEFAULT_GITHUB_EVENTS = ("push", "pull_request")
_EVENT_RE = re.compile(r"^[a-z0-9_.-]+$")


def normalize_github_events(events: Optional[list[str]]) -> list[str]:
    """Return normalized GitHub event names, preserving caller order."""
    source = list(events or DEFAULT_GITHUB_EVENTS)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in source:
        event = str(item or "").strip().lower()
        if not event:
            continue
        if event != "*" and not _EVENT_RE.match(event):
            raise ValueError("GitHub event names may only contain letters, digits, dots, underscores, or hyphens")
        if event not in seen:
            normalized.append(event)
            seen.add(event)
    if not normalized:
        raise ValueError("At least one GitHub event is required")
    return normalized


def normalize_path_filters(path_filters: Optional[list[str]]) -> Optional[list[str]]:
    """Trim and de-duplicate GitHub path glob filters."""
    if path_filters is None:
        return None
    normalized: list[str] = []
    seen: set[str] = set()
    for item in path_filters:
        value = str(item or "").strip()
        if not value:
            continue
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    return normalized or None


def normalize_repo_part(value: str, field_name: str) -> str:
    """Normalize a GitHub owner/repository segment without changing case."""
    normalized = str(value or "").strip().strip("/")
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if "/" in normalized:
        raise ValueError(f"{field_name} must not contain '/'")
    return normalized


def preview_secret(secret: str) -> str:
    """Return a stable preview for sensitive token fields."""
    value = str(secret or "")
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def generate_webhook_secret() -> str:
    """Generate a GitHub webhook shared secret."""
    return "ghwhsec_" + secrets.token_urlsafe(32)


def encrypt_pat_token(db: Session, tenant_id: str, plaintext: str) -> str:
    """Encrypt a GitHub PAT with the shared per-tenant TokenEncryption pattern."""
    from hub.security import TokenEncryption
    from services.encryption_key_service import get_api_key_encryption_key

    master_key = get_api_key_encryption_key(db)
    if not master_key:
        raise RuntimeError("GitHub PAT encryption key unavailable")
    return TokenEncryption(master_key.encode()).encrypt(plaintext, tenant_id)


def decrypt_pat_token(db: Session, tenant_id: str, encrypted: str) -> str:
    """Decrypt a GitHub PAT encrypted by encrypt_pat_token."""
    from hub.security import TokenEncryption
    from services.encryption_key_service import get_api_key_encryption_key

    master_key = get_api_key_encryption_key(db)
    if not master_key:
        raise RuntimeError("GitHub PAT encryption key unavailable")
    return TokenEncryption(master_key.encode()).decrypt(encrypted, tenant_id)


def encrypt_webhook_secret(db: Session, tenant_id: str, plaintext: str) -> str:
    """Encrypt a GitHub webhook secret with the webhook encryption key."""
    from hub.security import TokenEncryption
    from services.encryption_key_service import get_webhook_encryption_key

    master_key = get_webhook_encryption_key(db)
    if not master_key:
        raise RuntimeError("GitHub webhook encryption key unavailable")
    return TokenEncryption(master_key.encode()).encrypt(plaintext, tenant_id)


def decrypt_webhook_secret(db: Session, tenant_id: str, encrypted: str) -> str:
    """Decrypt a GitHub webhook secret encrypted by encrypt_webhook_secret."""
    from hub.security import TokenEncryption
    from services.encryption_key_service import get_webhook_encryption_key

    master_key = get_webhook_encryption_key(db)
    if not master_key:
        raise RuntimeError("GitHub webhook encryption key unavailable")
    return TokenEncryption(master_key.encode()).decrypt(encrypted, tenant_id)


def verify_github_signature(raw_body: bytes, signature_header: Optional[str], secret: str) -> bool:
    """Validate GitHub's X-Hub-Signature-256 header."""
    if not signature_header or not secret:
        return False
    provided = signature_header.strip()
    if not provided.startswith("sha256="):
        return False
    provided_hex = provided[len("sha256="):]
    expected_hex = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_hex, expected_hex)


def github_event_allowed(configured_events: Optional[list[str]], event_type: str) -> bool:
    """Return whether a GitHub delivery event is enabled for an instance."""
    normalized_event = str(event_type or "").strip().lower()
    if not normalized_event:
        return False
    events = normalize_github_events(configured_events)
    return "*" in events or normalized_event in events


def extract_repository(payload: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """Extract repository owner/name from a GitHub webhook payload."""
    repository = payload.get("repository") if isinstance(payload, dict) else None
    if not isinstance(repository, dict):
        return None, None

    name = repository.get("name")
    owner = None
    owner_payload = repository.get("owner")
    if isinstance(owner_payload, dict):
        owner = owner_payload.get("login") or owner_payload.get("name")
    if not owner and isinstance(repository.get("full_name"), str) and "/" in repository["full_name"]:
        owner = repository["full_name"].split("/", 1)[0]
    return (str(owner) if owner else None, str(name) if name else None)


def repository_matches(payload: dict[str, Any], repo_owner: str, repo_name: str) -> bool:
    """Return whether a payload belongs to the configured repository."""
    owner, name = extract_repository(payload)
    return (
        bool(owner)
        and bool(name)
        and owner.lower() == repo_owner.lower()
        and name.lower() == repo_name.lower()
    )


def extract_branch(event_type: str, payload: dict[str, Any]) -> Optional[str]:
    """Extract the most relevant branch for common GitHub webhook events."""
    event = str(event_type or "").lower()
    if event == "push":
        ref = payload.get("ref")
        if isinstance(ref, str):
            return ref.removeprefix("refs/heads/")

    pull_request = payload.get("pull_request")
    if isinstance(pull_request, dict):
        base = pull_request.get("base")
        if isinstance(base, dict) and base.get("ref"):
            return str(base["ref"])
        head = pull_request.get("head")
        if isinstance(head, dict) and head.get("ref"):
            return str(head["ref"])

    ref = payload.get("ref")
    return str(ref) if ref else None


def branch_matches(branch_filter: Optional[str], event_type: str, payload: dict[str, Any]) -> bool:
    """Return whether the event branch matches a comma-separated glob filter."""
    patterns = _split_filter_patterns(branch_filter)
    if not patterns:
        return True
    branch = extract_branch(event_type, payload)
    if not branch:
        return False
    return any(fnmatch.fnmatchcase(branch, pattern) for pattern in patterns)


def extract_changed_paths(payload: dict[str, Any]) -> list[str]:
    """Extract changed paths from push-like payloads."""
    paths: list[str] = []
    seen: set[str] = set()

    def add_path(value: Any) -> None:
        if isinstance(value, str) and value and value not in seen:
            paths.append(value)
            seen.add(value)

    commits = payload.get("commits")
    if isinstance(commits, list):
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            for field in ("added", "modified", "removed"):
                values = commit.get(field)
                if isinstance(values, list):
                    for path in values:
                        add_path(path)

    head_commit = payload.get("head_commit")
    if isinstance(head_commit, dict):
        for field in ("added", "modified", "removed"):
            values = head_commit.get(field)
            if isinstance(values, list):
                for path in values:
                    add_path(path)

    return paths


def path_matches(path_filters: Optional[list[str]], payload: dict[str, Any]) -> bool:
    """Return whether changed paths match any configured glob."""
    filters = normalize_path_filters(path_filters)
    if not filters:
        return True
    paths = extract_changed_paths(payload)
    if not paths:
        return False
    return any(fnmatch.fnmatchcase(path, pattern) for path in paths for pattern in filters)


def author_matches(author_filter: Optional[str], payload: dict[str, Any]) -> bool:
    """Return whether sender/pusher/commit author fields match a glob filter."""
    patterns = _split_filter_patterns(author_filter)
    if not patterns:
        return True
    candidates = _author_candidates(payload)
    return any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates for pattern in patterns)


def github_filters_match(instance: Any, event_type: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
    """Evaluate GitHub-specific filters for an instance and payload."""
    if not github_event_allowed(getattr(instance, "events", None), event_type):
        return False, "event_not_enabled"
    if not repository_matches(payload, getattr(instance, "repo_owner", ""), getattr(instance, "repo_name", "")):
        return False, "repository_mismatch"
    if not branch_matches(getattr(instance, "branch_filter", None), event_type, payload):
        return False, "branch_filter_no_match"
    if not path_matches(getattr(instance, "path_filters", None), payload):
        return False, "path_filter_no_match"
    if not author_matches(getattr(instance, "author_filter", None), payload):
        return False, "author_filter_no_match"
    return True, None


def build_dispatch_payload(
    *,
    instance_id: int,
    delivery_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build the payload persisted by TriggerDispatchService."""
    owner, name = extract_repository(payload)
    branch = extract_branch(event_type, payload)
    return {
        "github_trigger_id": instance_id,
        "github_event": event_type,
        "delivery_id": delivery_id,
        "repository": {
            "owner": owner,
            "name": name,
            "full_name": f"{owner}/{name}" if owner and name else None,
        },
        "action": payload.get("action"),
        "branch": branch,
        "changed_paths": extract_changed_paths(payload),
        "sender": payload.get("sender"),
        "raw_event": payload,
    }


def sender_key_for_payload(instance_id: int, payload: dict[str, Any]) -> str:
    """Return a stable sender key for GitHub webhook dispatch."""
    sender = payload.get("sender")
    login = sender.get("login") if isinstance(sender, dict) else None
    if not login:
        pusher = payload.get("pusher")
        if isinstance(pusher, dict):
            login = pusher.get("name") or pusher.get("email")
    return f"github_{instance_id}_{login or 'unknown'}"[:255]


def occurred_at_for_payload(payload: dict[str, Any]) -> datetime:
    """Best-effort occurred-at extraction from GitHub payload timestamps."""
    candidates = [
        (payload.get("head_commit") or {}).get("timestamp") if isinstance(payload.get("head_commit"), dict) else None,
        (payload.get("pull_request") or {}).get("updated_at") if isinstance(payload.get("pull_request"), dict) else None,
        payload.get("updated_at"),
    ]
    for value in candidates:
        if not isinstance(value, str) or not value:
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
    return datetime.utcnow()


def _split_filter_patterns(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _author_candidates(payload: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    def add(value: Any) -> None:
        if value is not None:
            text = str(value).strip()
            if text and text not in candidates:
                candidates.append(text)

    sender = payload.get("sender")
    if isinstance(sender, dict):
        add(sender.get("login"))
    pusher = payload.get("pusher")
    if isinstance(pusher, dict):
        add(pusher.get("name"))
        add(pusher.get("email"))
    pull_request = payload.get("pull_request")
    if isinstance(pull_request, dict):
        user = pull_request.get("user")
        if isinstance(user, dict):
            add(user.get("login"))
    commits = payload.get("commits")
    if isinstance(commits, list):
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            author = commit.get("author")
            if isinstance(author, dict):
                add(author.get("username"))
                add(author.get("name"))
                add(author.get("email"))
            committer = commit.get("committer")
            if isinstance(committer, dict):
                add(committer.get("username"))
                add(committer.get("name"))
                add(committer.get("email"))
    return candidates


class GitHubTrigger(Trigger):
    """GitHub trigger entry point; webhook delivery happens via FastAPI."""

    channel_type: ClassVar[str] = "github"
    delivery_mode: ClassVar[str] = "push"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = False

    def __init__(self, db_session: Session, github_instance_id: int, logger: logging.Logger):
        self.db = db_session
        self.github_instance_id = github_instance_id
        self.logger = logger

    async def start(self) -> None:
        """No persistent connection is required for GitHub webhooks."""
        return None

    async def stop(self) -> None:
        """No persistent connection is required for GitHub webhooks."""
        return None

    async def poll_or_receive(self) -> list[TriggerEvent]:
        """GitHub events are received by the public inbound route."""
        return []

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        """Wake-event persistence is handled by TriggerDispatchService."""
        return None
