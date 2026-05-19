"""Provider-neutral repository trigger criteria validation/evaluation."""

from __future__ import annotations

import fnmatch
from typing import Any, Optional

from channels.repository.events import event_class


VALID_EVENTS = {"pull_request", "push", "issue", "comment", "release", "pipeline"}
EVENT_ALIASES = {
    "pr": "pull_request",
    "mr": "pull_request",
    "merge_request": "pull_request",
    "merge_requests": "pull_request",
    "issues": "issue",
    "issue_comment": "comment",
    "note": "comment",
    "tag": "release",
    "tag_push": "release",
    "workflow_run": "pipeline",
}
VALID_ORDERING = {"oldest_first", "newest_first"}

FILTER_KEYS = {
    "source_branch_filter",
    "target_branch_filter",
    "branch_filter",
    "tag_filter",
    "path_filters",
    "author_filter",
    "exclude_drafts",
    "title_contains",
    "body_contains",
    "labels_any",
    "labels_all",
    "state",
    "message_contains",
    "commit_count_min",
    "commit_count_max",
    "target_type",
    "target_title_contains",
    "status",
    "pipeline_source",
}


def validate_repository_criteria(criteria: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(criteria, dict):
        raise ValueError("criteria must be an object")
    version = criteria.get("criteria_version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError("criteria_version must be an integer >= 1")
    event = str(criteria.get("event") or "pull_request").strip().lower()
    event = EVENT_ALIASES.get(event, event)
    if event not in VALID_EVENTS:
        raise ValueError(f"unsupported event: {event}")
    actions = _normalize_string_list(criteria.get("actions"))
    filters_raw = criteria.get("filters") or {}
    if not isinstance(filters_raw, dict):
        raise ValueError("filters must be an object")
    unknown = set(filters_raw) - FILTER_KEYS
    if unknown:
        raise ValueError(f"unknown filter keys: {sorted(unknown)}")
    ordering = str(criteria.get("ordering") or "oldest_first").strip().lower()
    if ordering not in VALID_ORDERING:
        raise ValueError(f"ordering must be one of {sorted(VALID_ORDERING)}")
    return {
        "criteria_version": version,
        "event": event,
        "actions": actions,
        "filters": _normalize_filters(filters_raw),
        "ordering": ordering,
    }


def evaluate_repository_criteria(
    payload: dict[str, Any],
    criteria: dict[str, Any],
    *,
    provider: Optional[str] = None,
    provider_event: Optional[str] = None,
) -> tuple[bool, str]:
    criteria = validate_repository_criteria(criteria)
    if not isinstance(payload, dict):
        return False, "payload_not_object"

    raw_event = payload.get("provider_event") or payload.get("github_event") or payload.get("gitlab_event") or provider_event
    raw_provider = payload.get("provider") or provider
    if raw_provider and raw_event:
        actual_class = event_class(str(raw_provider), str(raw_event))
        if actual_class != criteria["event"]:
            return False, f"event_mismatch:{actual_class}"

    action = str(payload.get("action") or "").strip().lower()
    if criteria["actions"] and action not in criteria["actions"]:
        return False, f"action_mismatch:{action or 'none'}"

    filters = criteria["filters"]
    if filters.get("state"):
        state = str(payload.get("state") or (payload.get("object") or {}).get("state") or "").strip().lower()
        if state and state != filters["state"]:
            return False, f"state_no_match:{state}"
    if not _glob_match(filters.get("branch_filter"), payload.get("branch")):
        return False, "branch_filter_no_match"
    if not _glob_match(filters.get("source_branch_filter"), payload.get("source_branch")):
        return False, "source_branch_filter_no_match"
    if not _glob_match(filters.get("target_branch_filter"), payload.get("target_branch")):
        return False, "target_branch_filter_no_match"
    if not _glob_match(filters.get("tag_filter"), payload.get("tag")):
        return False, "tag_filter_no_match"
    if filters.get("path_filters") and not _paths_match(filters["path_filters"], payload.get("changed_paths") or []):
        return False, "path_filter_no_match"
    if filters.get("author_filter") and not _any_glob_match(filters["author_filter"], _actor_candidates(payload)):
        return False, "author_no_match"
    if filters.get("exclude_drafts") and bool((payload.get("object") or {}).get("draft")):
        return False, "draft_excluded"
    if filters.get("title_contains") and not _contains((payload.get("object") or {}).get("title"), filters["title_contains"]):
        return False, "title_substring_no_match"
    if filters.get("body_contains") and not _contains((payload.get("object") or {}).get("body"), filters["body_contains"]):
        return False, "body_substring_no_match"
    labels = [str(item).lower() for item in ((payload.get("object") or {}).get("labels") or [])]
    if filters.get("labels_any") and not any(str(label).lower() in labels for label in filters["labels_any"]):
        return False, "labels_any_no_match"
    if filters.get("labels_all") and not all(str(label).lower() in labels for label in filters["labels_all"]):
        return False, "labels_all_no_match"
    if filters.get("message_contains") and not _contains(payload.get("message"), filters["message_contains"]):
        return False, "message_substring_no_match"
    commit_count = payload.get("commit_count")
    if filters.get("commit_count_min") is not None and commit_count is not None and int(commit_count) < int(filters["commit_count_min"]):
        return False, "commit_count_below_min"
    if filters.get("commit_count_max") is not None and commit_count is not None and int(commit_count) > int(filters["commit_count_max"]):
        return False, "commit_count_above_max"
    if filters.get("target_type") and str((payload.get("object") or {}).get("target_type") or "").lower() != filters["target_type"]:
        return False, "target_type_no_match"
    if filters.get("target_title_contains") and not _contains((payload.get("object") or {}).get("target_title"), filters["target_title_contains"]):
        return False, "target_title_substring_no_match"
    if filters.get("status") and str(payload.get("status") or (payload.get("object") or {}).get("status") or "").lower() != filters["status"]:
        return False, "status_no_match"
    if filters.get("pipeline_source") and str(payload.get("pipeline_source") or "").lower() != filters["pipeline_source"]:
        return False, "pipeline_source_no_match"
    return True, "matched"


def _normalize_string_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError("actions must be a string or list of strings")
    result: list[str] = []
    for item in raw:
        value = str(item or "").strip().lower()
        if value and value not in result:
            result.append(value)
    return result


def _normalize_filters(raw: dict[str, Any]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key, value in raw.items():
        if value is None:
            filters[key] = None
        elif key in {"path_filters", "labels_any", "labels_all"}:
            filters[key] = [str(item).strip() for item in (value if isinstance(value, list) else [value]) if str(item).strip()]
        elif key == "exclude_drafts":
            if not isinstance(value, bool):
                raise ValueError("exclude_drafts must be a boolean")
            filters[key] = value
        elif key in {"commit_count_min", "commit_count_max"}:
            filters[key] = int(value)
        else:
            filters[key] = str(value).strip().lower() if key in {"state", "target_type", "status", "pipeline_source"} else str(value).strip()
    return filters


def _glob_match(patterns: Any, value: Any) -> bool:
    if not patterns:
        return True
    values = [value] if value is not None else []
    return _any_glob_match(patterns, values)


def _any_glob_match(patterns: Any, values: list[Any]) -> bool:
    if isinstance(patterns, str):
        patterns = [part.strip() for part in patterns.split(",") if part.strip()]
    if not patterns:
        return True
    normalized_values = [str(value or "").strip() for value in values if str(value or "").strip()]
    return any(fnmatch.fnmatchcase(value, pattern) for value in normalized_values for pattern in patterns)


def _paths_match(patterns: list[str], paths: list[Any]) -> bool:
    return _any_glob_match(patterns, paths)


def _contains(value: Any, needle: Any) -> bool:
    if not needle:
        return True
    return str(needle).lower() in str(value or "").lower()


def _actor_candidates(payload: dict[str, Any]) -> list[str]:
    actor = payload.get("actor")
    candidates: list[str] = []
    if isinstance(actor, dict):
        for key in ("username", "name", "email", "login"):
            value = actor.get(key)
            if value:
                candidates.append(str(value))
    sender = payload.get("sender")
    if isinstance(sender, dict):
        for key in ("login", "username", "name", "email"):
            value = sender.get(key)
            if value:
                candidates.append(str(value))
    return candidates
