"""GitLab merge-request trigger criteria envelope + evaluator."""

from __future__ import annotations

from typing import Any

from channels.gitlab.trigger import (
    author_matches,
    branch_matches,
    extract_branch,
    normalize_gitlab_event_type,
    normalize_path_filters,
    path_matches,
)


SUPPORTED_MR_EVENTS: frozenset[str] = frozenset({"merge_request"})

SUPPORTED_MR_ACTIONS: tuple[str, ...] = (
    "open",
    "reopen",
    "update",
    "close",
    "merge",
    "approved",
    "unapproved",
    "approval",
    "unapproval",
)

DEFAULT_MR_ACTIONS: tuple[str, ...] = ("open",)
VALID_ORDERING: frozenset[str] = frozenset({"oldest_first", "newest_first"})
DEFAULT_ORDERING = "oldest_first"

_ALLOWED_FILTER_KEYS: frozenset[str] = frozenset(
    {
        "branch_filter",
        "path_filters",
        "author_filter",
        "exclude_drafts",
        "title_contains",
        "body_contains",
    }
)


def validate_merge_request_criteria(criteria: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalize a GitLab merge-request criteria envelope."""
    if not isinstance(criteria, dict):
        raise ValueError("criteria must be an object")

    version = criteria.get("criteria_version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError("criteria_version must be an integer >= 1")

    event = str(criteria.get("event") or "merge_request").strip().lower()
    if event not in SUPPORTED_MR_EVENTS:
        raise ValueError(f"unsupported event: {event}")

    actions = _normalize_actions(criteria.get("actions"))

    filters_raw = criteria.get("filters") or {}
    if not isinstance(filters_raw, dict):
        raise ValueError("filters must be an object")
    unknown = set(filters_raw) - _ALLOWED_FILTER_KEYS
    if unknown:
        raise ValueError(f"unknown filter keys: {sorted(unknown)}")
    filters = _normalize_filters(filters_raw)

    ordering = str(criteria.get("ordering") or DEFAULT_ORDERING).strip().lower()
    if ordering not in VALID_ORDERING:
        raise ValueError(f"ordering must be one of {sorted(VALID_ORDERING)}")

    return {
        "criteria_version": version,
        "event": event,
        "actions": actions,
        "filters": filters,
        "ordering": ordering,
    }


def evaluate_merge_request_criteria(
    payload: dict[str, Any],
    criteria: dict[str, Any],
) -> tuple[bool, str]:
    """Evaluate a GitLab webhook ``payload`` against a MR criteria envelope."""
    criteria = validate_merge_request_criteria(criteria)

    if not isinstance(payload, dict):
        return False, "payload_not_object"

    expected_event = criteria["event"]
    payload_event = _payload_event(payload)
    if payload_event and payload_event != expected_event:
        return False, f"event_mismatch:{payload_event}"

    attrs = payload.get("object_attributes")
    if not isinstance(attrs, dict):
        return False, "missing_object_attributes"

    action = str(attrs.get("action") or payload.get("action") or "").strip().lower()
    actions = criteria["actions"]
    if action not in actions:
        return False, f"action_mismatch:{action or 'none'}"

    filters = criteria["filters"]

    branch_filter = filters.get("branch_filter")
    if branch_filter:
        if not branch_matches(branch_filter, "merge_request", payload):
            extracted = extract_branch("merge_request", payload) or "unknown"
            return False, f"branch_no_match:{branch_filter}:{extracted}"

    path_filters = filters.get("path_filters")
    if path_filters and not path_matches(path_filters, payload):
        return False, "path_no_match"

    author_filter = filters.get("author_filter")
    if author_filter and not author_matches(author_filter, payload):
        return False, f"author_no_match:{author_filter}"

    if filters.get("exclude_drafts") and _is_draft(attrs):
        return False, "draft_excluded"

    title_contains = filters.get("title_contains")
    if title_contains and title_contains.lower() not in str(attrs.get("title") or "").lower():
        return False, "title_no_match"

    body_contains = filters.get("body_contains")
    if body_contains and body_contains.lower() not in str(attrs.get("description") or "").lower():
        return False, "body_no_match"

    return True, "matched"


def _normalize_actions(raw: Any) -> list[str]:
    if raw is None:
        return list(DEFAULT_MR_ACTIONS)
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("actions must be a string or list of strings")

    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("actions entries must be strings")
        action = item.strip().lower()
        if not action:
            continue
        if action not in SUPPORTED_MR_ACTIONS:
            raise ValueError(f"unsupported action: {action}")
        if action not in seen:
            normalized.append(action)
            seen.add(action)
    return normalized or list(DEFAULT_MR_ACTIONS)


def _normalize_filters(raw: dict[str, Any]) -> dict[str, Any]:
    branch_filter = raw.get("branch_filter")
    if branch_filter is not None:
        branch_filter = str(branch_filter).strip() or None

    path_filters = normalize_path_filters(raw.get("path_filters"))

    author_filter = raw.get("author_filter")
    if author_filter is not None:
        author_filter = str(author_filter).strip() or None

    exclude_drafts = raw.get("exclude_drafts", False)
    if not isinstance(exclude_drafts, bool):
        raise ValueError("exclude_drafts must be a boolean")

    title_contains = raw.get("title_contains")
    if title_contains is not None:
        if not isinstance(title_contains, str):
            raise ValueError("title_contains must be a string")
        title_contains = title_contains.strip() or None

    body_contains = raw.get("body_contains")
    if body_contains is not None:
        if not isinstance(body_contains, str):
            raise ValueError("body_contains must be a string")
        body_contains = body_contains.strip() or None

    return {
        "branch_filter": branch_filter,
        "path_filters": path_filters,
        "author_filter": author_filter,
        "exclude_drafts": exclude_drafts,
        "title_contains": title_contains,
        "body_contains": body_contains,
    }


def _payload_event(payload: dict[str, Any]) -> str | None:
    raw = payload.get("object_kind") or payload.get("event_name")
    event = normalize_gitlab_event_type(raw)
    return event or None


def _is_draft(attrs: dict[str, Any]) -> bool:
    if bool(attrs.get("draft") or attrs.get("work_in_progress")):
        return True
    title = str(attrs.get("title") or "").strip().lower()
    return title.startswith("draft:") or title.startswith("wip:")
