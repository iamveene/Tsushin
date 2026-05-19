"""Provider-neutral helpers for repository webhook triggers."""

from __future__ import annotations

import fnmatch
import re
import secrets
from datetime import datetime
from typing import Any, Optional


_EVENT_RE = re.compile(r"^[a-z0-9_.-]+$")


def normalize_repository_events(
    events: Optional[list[str]],
    *,
    defaults: tuple[str, ...],
    provider_name: str,
    aliases: Optional[dict[str, str]] = None,
) -> list[str]:
    """Return normalized repository event names, preserving caller order."""
    source = list(events or defaults)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in source:
        event = normalize_event_name(item, aliases=aliases)
        if not event:
            continue
        if event != "*" and not _EVENT_RE.match(event):
            raise ValueError(
                f"{provider_name} event names may only contain letters, digits, dots, underscores, or hyphens"
            )
        if event not in seen:
            normalized.append(event)
            seen.add(event)
    if not normalized:
        raise ValueError(f"At least one {provider_name} event is required")
    return normalized


def normalize_event_name(value: Any, *, aliases: Optional[dict[str, str]] = None) -> str:
    """Normalize provider event names and common webhook header labels."""
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    normalized = raw.replace(" ", "_").replace("-", "_")
    if normalized.endswith("_hook"):
        normalized = normalized[: -len("_hook")]
    if aliases and normalized in aliases:
        return aliases[normalized]
    return normalized


def normalize_path_filters(path_filters: Optional[list[str]]) -> Optional[list[str]]:
    """Trim and de-duplicate repository path glob filters."""
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


def normalize_repo_segment(value: str, field_name: str) -> str:
    """Normalize one owner/repo segment without changing case."""
    normalized = str(value or "").strip().strip("/")
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if "/" in normalized:
        raise ValueError(f"{field_name} must not contain '/'")
    return normalized


def normalize_project_path(value: str, field_name: str = "project_path") -> str:
    """Normalize a provider project path such as ``group/subgroup/project``."""
    normalized = str(value or "").strip().strip("/")
    if not normalized:
        raise ValueError(f"{field_name} is required")
    if "//" in normalized or any(not part.strip() for part in normalized.split("/")):
        raise ValueError(f"{field_name} must be a slash-separated project path")
    return normalized


def preview_secret(secret: str) -> str:
    """Return a stable preview for sensitive token fields."""
    value = str(secret or "")
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def generate_webhook_secret(prefix: str) -> str:
    """Generate a repository webhook shared secret."""
    return prefix + secrets.token_urlsafe(32)


def repository_event_allowed(
    configured_events: Optional[list[str]],
    event_type: str,
    *,
    defaults: tuple[str, ...],
    provider_name: str,
    aliases: Optional[dict[str, str]] = None,
) -> bool:
    """Return whether a repository delivery event is enabled for an instance."""
    normalized_event = normalize_event_name(event_type, aliases=aliases)
    if not normalized_event:
        return False
    events = normalize_repository_events(
        configured_events,
        defaults=defaults,
        provider_name=provider_name,
        aliases=aliases,
    )
    return "*" in events or normalized_event in events


def branch_matches(branch_filter: Optional[str], branch: Optional[str]) -> bool:
    """Return whether the branch matches a comma-separated glob filter."""
    patterns = split_filter_patterns(branch_filter)
    if not patterns:
        return True
    if not branch:
        return False
    return any(fnmatch.fnmatchcase(branch, pattern) for pattern in patterns)


def path_matches(path_filters: Optional[list[str]], paths: list[str]) -> bool:
    """Return whether changed paths match any configured glob."""
    filters = normalize_path_filters(path_filters)
    if not filters:
        return True
    if not paths:
        return False
    return any(fnmatch.fnmatchcase(path, pattern) for path in paths for pattern in filters)


def author_matches(author_filter: Optional[str], candidates: list[str]) -> bool:
    """Return whether any candidate author matches a comma-separated glob filter."""
    patterns = split_filter_patterns(author_filter)
    if not patterns:
        return True
    return any(fnmatch.fnmatchcase(candidate, pattern) for candidate in candidates for pattern in patterns)


def split_filter_patterns(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def add_unique_text(candidates: list[str], value: Any) -> None:
    if value is not None:
        text = str(value).strip()
        if text and text not in candidates:
            candidates.append(text)


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
