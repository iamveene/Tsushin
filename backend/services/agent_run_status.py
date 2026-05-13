"""Helpers for deriving operator-facing agent run status."""

from __future__ import annotations

from typing import Any, Mapping, Optional


_ERROR_INDICATORS = (
    "command failed",
    "curl: (",
    "error executing",
    "error:",
    "exception:",
    "execution error",
    "exit code:",
    "failed to",
    "malformed",
    "not found",
    "permission denied",
    "timed out",
    "timeout",
    "traceback",
    "url rejected",
)


def determine_agent_run_status(
    result: Optional[Mapping[str, Any]] = None,
    *,
    current_status: Optional[str] = None,
    output_text: Optional[str] = None,
) -> str:
    """Return a fail-closed display status for an agent execution result."""
    result = result or {}
    if result.get("error"):
        return "error"

    if current_status and current_status.lower() not in {"success", "completed"}:
        return current_status

    answer = " ".join(
        str(value or "")
        for value in (
            output_text,
            result.get("answer"),
            result.get("output_preview"),
            result.get("tool_result"),
        )
    ).lower()
    if answer and any(indicator in answer for indicator in _ERROR_INDICATORS):
        return "error"

    return current_status or "success"
