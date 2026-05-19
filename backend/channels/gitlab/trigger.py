"""GitLab repository trigger helpers."""

from __future__ import annotations

import hmac
import logging
import re
import secrets
from datetime import datetime
from typing import Any, ClassVar, Optional

from sqlalchemy.orm import Session

from channels.repository.events import canonical_event, event_class
from channels.repository.trigger import (
    author_matches as repository_author_matches,
    branch_matches as repository_branch_matches,
    normalize_path_filters,
    path_matches as repository_path_matches,
)
from channels.trigger import Trigger
from channels.types import TriggerEvent


DEFAULT_GITLAB_EVENTS = ("push", "merge_request")
_EVENT_RE = re.compile(r"^[a-z0-9_. -]+$", re.IGNORECASE)


def normalize_gitlab_events(events: Optional[list[str]]) -> list[str]:
    source = list(events or DEFAULT_GITLAB_EVENTS)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in source:
        value = str(item or "").strip().lower().replace(" hook", "").replace(" ", "_")
        if not value:
            continue
        if value != "*" and not _EVENT_RE.match(value):
            raise ValueError("GitLab event names may only contain letters, digits, spaces, dots, underscores, or hyphens")
        if value not in seen:
            normalized.append(value)
            seen.add(value)
    if not normalized:
        raise ValueError("At least one GitLab event is required")
    return normalized


def normalize_project_path(value: str) -> str:
    normalized = "/".join(part for part in str(value or "").strip().strip("/").split("/") if part)
    if not normalized or "/" not in normalized:
        raise ValueError("project_path must include namespace and project")
    return normalized


def preview_secret(secret: str) -> str:
    value = str(secret or "")
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def generate_webhook_secret() -> str:
    return "glwhsec_" + secrets.token_urlsafe(32)


def encrypt_webhook_secret(db: Session, tenant_id: str, plaintext: str) -> str:
    from hub.security import TokenEncryption
    from services.encryption_key_service import get_webhook_encryption_key

    master_key = get_webhook_encryption_key(db)
    if not master_key:
        raise RuntimeError("GitLab webhook encryption key unavailable")
    return TokenEncryption(master_key.encode()).encrypt(plaintext, tenant_id)


def decrypt_webhook_secret(db: Session, tenant_id: str, encrypted: str) -> str:
    from hub.security import TokenEncryption
    from services.encryption_key_service import get_webhook_encryption_key

    master_key = get_webhook_encryption_key(db)
    if not master_key:
        raise RuntimeError("GitLab webhook encryption key unavailable")
    return TokenEncryption(master_key.encode()).decrypt(encrypted, tenant_id)


def verify_gitlab_token(token_header: Optional[str], secret: str) -> bool:
    if not token_header or not secret:
        return False
    return hmac.compare_digest(token_header.strip(), secret)


def gitlab_event_allowed(configured_events: Optional[list[str]], event_type: str) -> bool:
    event = _normalize_event_name(event_type)
    events = normalize_gitlab_events(configured_events)
    return "*" in events or event in events or canonical_event("gitlab", event) in events


def normalize_gitlab_event_type(event_type: Any) -> str:
    return _normalize_event_name(str(event_type or ""))


def project_matches(payload: dict[str, Any], project_path: str) -> bool:
    path = extract_project_path(payload)
    return bool(path) and path.lower() == project_path.lower()


def extract_project_path(payload: dict[str, Any]) -> Optional[str]:
    project = payload.get("project")
    if isinstance(project, dict):
        path = project.get("path_with_namespace") or project.get("web_url", "").split("gitlab.com/")[-1]
        if path:
            return str(path).removesuffix(".git")
    attrs = payload.get("object_attributes")
    if isinstance(attrs, dict) and attrs.get("target_project_id"):
        return None
    return None


def extract_branch(event_type: str, payload: dict[str, Any]) -> Optional[str]:
    event = _normalize_event_name(event_type)
    attrs = payload.get("object_attributes") if isinstance(payload, dict) else None
    if event == "push":
        ref = payload.get("ref")
        if isinstance(ref, str):
            return ref.removeprefix("refs/heads/")
    if event == "tag_push":
        ref = payload.get("ref")
        if isinstance(ref, str):
            return ref.removeprefix("refs/tags/")
    if isinstance(attrs, dict):
        return attrs.get("target_branch") or attrs.get("source_branch") or attrs.get("ref")
    return None


def extract_changed_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
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
                        add(path)
    return paths


def branch_matches(branch_filter: Optional[str], event_type: str, payload: dict[str, Any]) -> bool:
    return repository_branch_matches(branch_filter, extract_branch(event_type, payload))


def path_matches(path_filters: Optional[list[str]], payload: dict[str, Any]) -> bool:
    return repository_path_matches(path_filters, extract_changed_paths(payload))


def author_matches(author_filter: Optional[str], payload: dict[str, Any]) -> bool:
    actor = _actor(payload)
    candidates = [
        str(actor.get(key))
        for key in ("username", "name", "email")
        if actor.get(key)
    ]
    commits = payload.get("commits")
    if isinstance(commits, list):
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            author = commit.get("author")
            if isinstance(author, dict):
                for key in ("name", "email"):
                    value = author.get(key)
                    if value and str(value) not in candidates:
                        candidates.append(str(value))
    return repository_author_matches(author_filter, candidates)


def gitlab_filters_match(instance: Any, event_type: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
    """Evaluate GitLab-specific filters for an instance and payload."""
    if not gitlab_event_allowed(getattr(instance, "events", None), event_type):
        return False, "event_not_enabled"
    if not project_matches(payload, getattr(instance, "project_path", "")):
        return False, "project_mismatch"
    if not branch_matches(getattr(instance, "branch_filter", None), event_type, payload):
        return False, "branch_filter_no_match"
    if not path_matches(getattr(instance, "path_filters", None), payload):
        return False, "path_filter_no_match"
    if not author_matches(getattr(instance, "author_filter", None), payload):
        return False, "author_filter_no_match"
    return True, None


def build_dispatch_payload(*, instance_id: int, delivery_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = _normalize_event_name(event_type)
    attrs = payload.get("object_attributes") if isinstance(payload.get("object_attributes"), dict) else {}
    project_path = extract_project_path(payload)
    branch = extract_branch(event, payload)
    source_branch = attrs.get("source_branch")
    target_branch = attrs.get("target_branch")
    obj = _object_payload(event, payload, attrs)
    return {
        "repository_trigger_id": instance_id,
        "gitlab_trigger_id": instance_id,
        "provider": "gitlab",
        "provider_event": event,
        "gitlab_event": event,
        "canonical_event": canonical_event("gitlab", event),
        "event_class": event_class("gitlab", event),
        "delivery_id": delivery_id,
        "repository": {
            "owner": project_path.rsplit("/", 1)[0] if project_path and "/" in project_path else None,
            "name": project_path.rsplit("/", 1)[1] if project_path and "/" in project_path else None,
            "full_name": project_path,
            "project_path": project_path,
            "provider_project_id": (payload.get("project") or {}).get("id") if isinstance(payload.get("project"), dict) else None,
        },
        "project": {
            "path": project_path,
            "path_with_namespace": project_path,
            "id": (payload.get("project") or {}).get("id") if isinstance(payload.get("project"), dict) else None,
        },
        "action": attrs.get("action") or attrs.get("state") or payload.get("event_name"),
        "ref": payload.get("ref") or attrs.get("ref"),
        "branch": branch,
        "source_branch": source_branch,
        "target_branch": target_branch,
        "tag": branch if event == "tag_push" else None,
        "changed_paths": extract_changed_paths(payload),
        "commit_count": len(payload.get("commits") or []) if isinstance(payload.get("commits"), list) else None,
        "message": _commit_message(payload),
        "actor": _actor(payload),
        "object": obj,
        "status": attrs.get("status"),
        "pipeline_source": attrs.get("source"),
        "raw_event": payload,
    }


def sender_key_for_payload(instance_id: int, payload: dict[str, Any]) -> str:
    actor = _actor(payload)
    return f"gitlab_{instance_id}_{actor.get('username') or actor.get('name') or 'unknown'}"[:255]


def occurred_at_for_payload(payload: dict[str, Any]) -> datetime:
    attrs = payload.get("object_attributes") if isinstance(payload.get("object_attributes"), dict) else {}
    candidates = [
        attrs.get("updated_at"),
        attrs.get("created_at"),
        payload.get("created_at"),
        payload.get("updated_at"),
        (payload.get("commits") or [{}])[-1].get("timestamp") if isinstance(payload.get("commits"), list) and payload.get("commits") else None,
    ]
    for value in candidates:
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
    return datetime.utcnow()


def _normalize_event_name(event_type: str) -> str:
    return str(event_type or "").strip().lower().replace(" hook", "").replace(" ", "_")


def _actor(payload: dict[str, Any]) -> dict[str, Any]:
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    return {
        "id": user.get("id") or payload.get("user_id"),
        "username": user.get("username") or payload.get("user_username") or payload.get("user_name"),
        "name": user.get("name") or payload.get("user_name"),
        "email": user.get("email") or payload.get("user_email"),
    }


def _object_payload(event: str, payload: dict[str, Any], attrs: dict[str, Any]) -> dict[str, Any]:
    labels = attrs.get("labels")
    if isinstance(labels, list):
        labels = [item.get("title") if isinstance(item, dict) else item for item in labels]
    return {
        "type": {
            "merge_request": "pull_request",
            "note": "comment",
            "tag_push": "release",
        }.get(event, event),
        "iid": attrs.get("iid") or attrs.get("noteable_iid"),
        "number": attrs.get("iid") or attrs.get("noteable_iid"),
        "title": attrs.get("title") or attrs.get("noteable_title"),
        "body": attrs.get("description") or attrs.get("note") or attrs.get("message"),
        "url": attrs.get("url") or attrs.get("web_url"),
        "state": attrs.get("state"),
        "draft": _is_draft(attrs),
        "labels": labels or [],
        "target_type": attrs.get("noteable_type"),
        "target_title": attrs.get("noteable_title"),
        "status": attrs.get("status"),
    }


def _is_draft(attrs: dict[str, Any]) -> bool:
    title = str(attrs.get("title") or "").lower()
    return bool(attrs.get("work_in_progress") or attrs.get("draft") or title.startswith("draft:") or title.startswith("wip:"))


def _commit_message(payload: dict[str, Any]) -> Optional[str]:
    commits = payload.get("commits")
    if isinstance(commits, list) and commits:
        last = commits[-1]
        if isinstance(last, dict):
            return last.get("message")
    return None


class GitLabTrigger(Trigger):
    """GitLab trigger entry point; webhook delivery happens via FastAPI."""

    channel_type: ClassVar[str] = "gitlab"
    delivery_mode: ClassVar[str] = "push"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = False

    def __init__(self, db_session: Session, gitlab_instance_id: int, logger: logging.Logger):
        self.db = db_session
        self.gitlab_instance_id = gitlab_instance_id
        self.logger = logger

    async def start(self) -> None:
        """No persistent connection is required for GitLab webhooks."""
        return None

    async def stop(self) -> None:
        """No persistent connection is required for GitLab webhooks."""
        return None

    async def poll_or_receive(self) -> list[TriggerEvent]:
        """GitLab events are received by the public inbound route."""
        return []

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        """Wake-event persistence is handled by TriggerDispatchService."""
        return None
