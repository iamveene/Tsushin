"""Shared helpers for extracting assistant responses from agent/playground results."""

from typing import Optional


def extract_response_text(result: dict) -> Optional[str]:
    """Return the first non-empty assistant text from an agent result dict.

    BUG-504/BUG-511: Agents sometimes return tool-only results with an empty
    ``message``/``answer`` while the real reply lives in ``tool_result``.
    This helper preserves the original empty-string sentinel when no tool
    fallback is available so callers can still distinguish "no response" from
    "no key".
    """
    empty_primary = None

    for key in ("message", "answer"):
        if key not in result:
            continue
        value = result.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value
            if empty_primary is None:
                empty_primary = value
            continue
        return str(value)

    tool_result = result.get("tool_result")
    if tool_result is not None:
        return tool_result if isinstance(tool_result, str) else str(tool_result)

    return empty_primary
