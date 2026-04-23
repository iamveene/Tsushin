"""Validation helpers for trigger criteria payloads.

The criteria envelope is intentionally small in Phase 1. Trigger-specific
filters live inside ``filters`` and are validated by each trigger later; this
module enforces the shared shape so bad rows do not enter the control plane.
"""

from __future__ import annotations

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
