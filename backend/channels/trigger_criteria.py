"""Validation helpers for trigger criteria payloads.

The criteria envelope is intentionally small in Phase 1. Trigger-specific
filters live inside ``filters`` and are validated by each trigger later; this
module enforces the shared shape so bad rows do not enter the control plane.
"""

from __future__ import annotations

import re
from typing import Any


VALID_WINDOW_MODES = {"since_instance_start", "since_cursor", "sliding_lookback"}
VALID_ORDERING = {"oldest_first", "newest_first"}
VALID_DEDUPE_SCOPES = {"instance", "tenant"}


class TriggerCriteria:
    """Validate the shared criteria envelope used by Trigger instances."""

    @staticmethod
    def validate(data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise ValueError("trigger criteria must be an object")

        missing = {"criteria_version", "filters", "window", "ordering"} - set(data)
        if missing:
            raise ValueError(f"trigger criteria missing required fields: {sorted(missing)}")

        version = data["criteria_version"]
        if not isinstance(version, int) or version < 1:
            raise ValueError("criteria_version must be an integer >= 1")

        if not isinstance(data["filters"], dict):
            raise ValueError("filters must be an object")

        window = data["window"]
        if not isinstance(window, dict):
            raise ValueError("window must be an object")
        mode = window.get("mode")
        if mode not in VALID_WINDOW_MODES:
            raise ValueError(f"window.mode must be one of {sorted(VALID_WINDOW_MODES)}")
        lookback = window.get("lookback_seconds")
        if lookback is not None and (not isinstance(lookback, int) or lookback < 0):
            raise ValueError("window.lookback_seconds must be an integer >= 0")

        if data["ordering"] not in VALID_ORDERING:
            raise ValueError(f"ordering must be one of {sorted(VALID_ORDERING)}")

        rate_limit = data.get("rate_limit")
        if rate_limit is not None:
            if not isinstance(rate_limit, dict):
                raise ValueError("rate_limit must be an object")
            max_events = rate_limit.get("max_events_per_poll")
            if max_events is not None and (not isinstance(max_events, int) or max_events < 1):
                raise ValueError("rate_limit.max_events_per_poll must be an integer >= 1")

        dedupe_scope = data.get("dedupe_scope")
        if dedupe_scope is not None and dedupe_scope not in VALID_DEDUPE_SCOPES:
            raise ValueError(f"dedupe_scope must be one of {sorted(VALID_DEDUPE_SCOPES)}")

        return data


def validate_criteria(data: dict[str, Any]) -> dict[str, Any]:
    return TriggerCriteria.validate(data)


def evaluate_payload_criteria(payload: dict[str, Any], criteria: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Return whether payload satisfies trigger criteria.

    v0.7.0 criteria are intentionally AND-only. If no JSONPath matchers are
    configured, the payload passes after the shared envelope is valid.
    """
    if not criteria:
        return True, None

    criteria = validate_criteria(criteria)
    filters = criteria.get("filters") or {}
    matchers = (
        filters.get("jsonpath_matchers")
        or filters.get("jsonpath")
        or filters.get("matchers")
        or []
    )
    if not matchers:
        return True, None
    if not isinstance(matchers, list):
        raise ValueError("filters.jsonpath_matchers must be a list")

    for index, matcher in enumerate(matchers):
        if not isinstance(matcher, dict):
            raise ValueError("JSONPath matcher must be an object")
        path = str(matcher.get("path") or matcher.get("jsonpath") or "").strip()
        if not path:
            raise ValueError("JSONPath matcher path is required")
        operator = str(matcher.get("operator") or "exists").strip().lower()
        expected = matcher.get("value", matcher.get("expected"))
        values = _jsonpath_values(payload, path)
        if not _match_values(values, operator, expected):
            return False, f"jsonpath_matcher_{index}_failed"

    return True, None


def _jsonpath_values(payload: dict[str, Any], path: str) -> list[Any]:
    try:
        from jsonpath_ng import parse

        expression = parse(path)
        return [match.value for match in expression.find(payload)]
    except ImportError:
        return _simple_jsonpath_values(payload, path)


def _simple_jsonpath_values(payload: dict[str, Any], path: str) -> list[Any]:
    """Small fallback for tests/dev if jsonpath-ng is not installed yet."""
    if path == "$":
        return [payload]
    if not path.startswith("$."):
        raise ValueError("JSONPath must start with '$.'")

    current: list[Any] = [payload]
    for raw_part in path[2:].split("."):
        if not raw_part:
            return []
        part = raw_part
        explode = False
        index: int | None = None
        if part.endswith("[*]"):
            explode = True
            part = part[:-3]
        else:
            index_match = re.match(r"^(.+)\[(\d+)\]$", part)
            if index_match:
                part = index_match.group(1)
                index = int(index_match.group(2))

        next_values: list[Any] = []
        for item in current:
            if not isinstance(item, dict) or part not in item:
                continue
            value = item[part]
            if explode:
                if isinstance(value, list):
                    next_values.extend(value)
            elif index is not None:
                if isinstance(value, list) and index < len(value):
                    next_values.append(value[index])
            else:
                next_values.append(value)
        current = next_values
    return current


def _match_values(values: list[Any], operator: str, expected: Any) -> bool:
    if operator == "exists":
        return bool(values)
    if operator == "not_exists":
        return not values
    if operator == "equals":
        return any(value == expected for value in values)
    if operator == "not_equals":
        return bool(values) and all(value != expected for value in values)
    if operator == "contains":
        return any(_contains(value, expected) for value in values)
    if operator == "in":
        if not isinstance(expected, list):
            raise ValueError("operator 'in' expects a list value")
        return any(value in expected for value in values)
    if operator == "regex":
        if not isinstance(expected, str):
            raise ValueError("operator 'regex' expects a string value")
        pattern = re.compile(expected)
        return any(isinstance(value, str) and pattern.search(value) for value in values)
    raise ValueError(f"unsupported JSONPath matcher operator: {operator}")


def _contains(value: Any, expected: Any) -> bool:
    if isinstance(value, str):
        return str(expected) in value
    if isinstance(value, list):
        return expected in value
    if isinstance(value, dict):
        return expected in value.values() or expected in value.keys()
    return False
