"""GitHub PR-submitted trigger criteria envelope + evaluator.

This module defines the canonical v1 ``trigger_criteria`` envelope used by
GitHub triggers when a PR-submitted style filter is configured, and the
``evaluate_pr_criteria`` evaluator the dispatch service calls before legacy
top-level ``events`` / ``branch_filter`` / ``path_filters`` / ``author_filter``
columns are consulted.

Canonical envelope shape (v1)::

    {
      "criteria_version": 1,
      "event": "pull_request",
      "actions": ["opened"],            # any subset of SUPPORTED_PR_ACTIONS
      "filters": {
        "branch_filter": "main",        # glob — empty/null = any
        "path_filters": ["backend/**"], # glob list — empty/null = any
        "author_filter": "alice",       # exact GitHub login — empty/null = any
        "draft_only": false,             # bool: true → fire ONLY for non-draft PRs
        "title_contains": null,          # case-insensitive substring (optional)
        "body_contains": null            # case-insensitive substring (optional)
      },
      "ordering": "oldest_first"
    }

Backwards compatibility:
- A trigger row with ``trigger_criteria = NULL`` keeps the legacy behavior
  (top-level columns drive filtering).
- A trigger row with ``trigger_criteria.event == "pull_request"`` switches the
  source-of-truth to this envelope; the legacy columns become read-only display
  values for the wizard.
- Other ``event`` values are reserved for future GitHub trigger envelopes
  (push, release, issue_comment, …); for now the dispatch service falls back
  to legacy filtering and logs a warning.
"""

from __future__ import annotations

from typing import Any, Optional

from channels.github.trigger import (
    author_matches,
    branch_matches,
    extract_branch,
    extract_changed_paths,
    normalize_path_filters,
    path_matches,
)


# ---------------------------------------------------------------------------
# Constants — extend SUPPORTED_PR_ACTIONS when GitHub adds new PR webhook
# actions you want to expose in the wizard.
# ---------------------------------------------------------------------------

SUPPORTED_PR_EVENTS: frozenset[str] = frozenset({"pull_request"})

SUPPORTED_PR_ACTIONS: tuple[str, ...] = (
    "opened",
    "reopened",
    "synchronize",
    "edited",
    "ready_for_review",
    "review_requested",
)

DEFAULT_PR_ACTIONS: tuple[str, ...] = ("opened",)

VALID_ORDERING: frozenset[str] = frozenset({"oldest_first", "newest_first"})

DEFAULT_ORDERING = "oldest_first"

# Allowed keys inside the ``filters`` object — anything else is rejected so a
# typo doesn't silently turn into a no-op rule.
_ALLOWED_FILTER_KEYS: frozenset[str] = frozenset(
    {
        "branch_filter",
        "path_filters",
        "author_filter",
        "draft_only",
        "title_contains",
        "body_contains",
    }
)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_pr_criteria(criteria: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalize a PR-submitted criteria envelope.

    Returns a fresh dict in canonical form (single-string ``actions`` are
    coerced to a list, missing ``actions`` defaults to ``["opened"]``,
    ``filters`` is always present, etc.). Raises ``ValueError`` with a short
    machine-friendly reason on bad input — the routes layer turns this into a
    400 with detail ``invalid_pr_criteria: <reason>``.
    """
    if not isinstance(criteria, dict):
        raise ValueError("criteria must be an object")

    version = criteria.get("criteria_version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError("criteria_version must be an integer >= 1")

    event = str(criteria.get("event") or "pull_request").strip().lower()
    if event not in SUPPORTED_PR_EVENTS:
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


def _normalize_actions(raw: Any) -> list[str]:
    if raw is None:
        return list(DEFAULT_PR_ACTIONS)
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
        if action not in SUPPORTED_PR_ACTIONS:
            raise ValueError(f"unsupported action: {action}")
        if action not in seen:
            normalized.append(action)
            seen.add(action)
    if not normalized:
        return list(DEFAULT_PR_ACTIONS)
    return normalized


def _normalize_filters(raw: dict[str, Any]) -> dict[str, Any]:
    branch_filter = raw.get("branch_filter")
    if branch_filter is not None:
        branch_filter = str(branch_filter).strip() or None

    path_filters = normalize_path_filters(raw.get("path_filters"))

    author_filter = raw.get("author_filter")
    if author_filter is not None:
        author_filter = str(author_filter).strip() or None

    draft_only = raw.get("draft_only", False)
    if not isinstance(draft_only, bool):
        raise ValueError("draft_only must be a boolean")

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
        "draft_only": draft_only,
        "title_contains": title_contains,
        "body_contains": body_contains,
    }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate_pr_criteria(
    payload: dict[str, Any],
    criteria: dict[str, Any],
) -> tuple[bool, str]:
    """Evaluate a webhook ``payload`` against a PR-submitted ``criteria`` envelope.

    Returns ``(matched, reason)``. ``reason`` is ``"matched"`` on success, or a
    short stable code on rejection — see module docstring/tests for the full
    list. The criteria is validated/normalized in-place; bad envelopes raise
    ``ValueError`` (the dispatch service maps this to ``invalid_trigger_criteria``).
    """
    criteria = validate_pr_criteria(criteria)

    if not isinstance(payload, dict):
        return False, "payload_not_object"

    expected_event = criteria["event"]
    payload_event = _payload_event(payload)
    if payload_event and payload_event != expected_event:
        return False, f"event_mismatch:{payload_event}"

    pull_request = payload.get("pull_request")
    if not isinstance(pull_request, dict):
        return False, "missing_pull_request"

    action = str(payload.get("action") or "").strip().lower()
    actions = criteria["actions"]
    if action not in actions:
        return False, f"action_mismatch:{action or 'none'}"

    filters = criteria["filters"]

    branch_filter = filters.get("branch_filter")
    if branch_filter:
        if not branch_matches(branch_filter, "pull_request", payload):
            extracted = extract_branch("pull_request", payload) or "unknown"
            return False, f"branch_no_match:{branch_filter}:{extracted}"

    path_filters = filters.get("path_filters")
    if path_filters:
        # GitHub PR webhooks do NOT include changed-files inline; that data
        # requires an extra ``GET /repos/.../pulls/{n}/files`` call that the
        # dispatch path doesn't make. If the payload happens to include
        # changed_paths (e.g. a synthetic test fixture or a future enrichment
        # pass), use it; otherwise treat path filtering as "skipped" so the
        # rule never silently drops every PR. Callers are responsible for
        # surfacing this in the wizard UI.
        changed_paths = extract_changed_paths(payload)
        if changed_paths:
            if not path_matches(path_filters, payload):
                return False, f"path_no_match:{','.join(path_filters)}"
        # else: no changed_paths in payload → skip path filtering (logged at
        # dispatch time, not here, to keep this fn pure).

    author_filter = filters.get("author_filter")
    if author_filter:
        if not author_matches(author_filter, payload):
            login = _pr_author_login(pull_request) or "unknown"
            return False, f"author_no_match:{login}"

    if filters.get("draft_only") is True:
        if pull_request.get("draft") is True:
            return False, "draft_excluded"

    title_contains = filters.get("title_contains")
    if title_contains:
        title = str(pull_request.get("title") or "")
        if title_contains.lower() not in title.lower():
            return False, "title_substring_no_match"

    body_contains = filters.get("body_contains")
    if body_contains:
        body = str(pull_request.get("body") or "")
        if body_contains.lower() not in body.lower():
            return False, "body_substring_no_match"

    return True, "matched"


def _payload_event(payload: dict[str, Any]) -> Optional[str]:
    """Best-effort event-name extraction.

    The dispatch service receives ``event_type`` separately, but the evaluator
    is also called from the wizard's dry-run endpoint where the payload may
    carry a ``_event`` hint. Most real GitHub webhook bodies do NOT include
    the event name (it's in the ``X-GitHub-Event`` header), so an absent hint
    is treated as a match — the action check below is the real gate.
    """
    for key in ("_event", "event", "x_github_event"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _pr_author_login(pull_request: dict[str, Any]) -> Optional[str]:
    user = pull_request.get("user")
    if isinstance(user, dict):
        login = user.get("login")
        if isinstance(login, str) and login.strip():
            return login.strip()
    return None
