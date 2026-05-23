"""Promote a per-click DOM meta blob into a stable CSS selector + fallback.

The in-page JS shim (see `session_manager._SELECTOR_JS`) sends per-event
metadata: tag, id, name, role, aria-label, data-testid/qa/cy, placeholder,
and a raw nth-of-type CSS path. This module picks the most stable selector
that uniquely identifies the element and writes the raw path as a
fallback so the runtime has two shots if the primary breaks.

Stability ladder (in order):
    1. data-testid / data-qa / data-cy / data-track (test-friendly hooks)
    2. [name="..."] / [type="submit"] / [aria-label="..."]
    3. #id (last resort because frameworks regenerate it)
    4. tag[role="..."]
    5. The raw nth-of-type path from the shim

The output is meant to be consumed by Playwright's CSS engine — every
selector here is plain CSS, no Playwright-specific extensions, so the
existing runtime ([backend/hub/providers/playwright_provider.py]) can use
it without changes.
"""

from __future__ import annotations

from typing import Optional

# Attributes that uniquely identify a test-friendly hook. Listed in
# preference order — the first one present wins.
_TEST_HOOK_ATTRS = ("data-testid", "data-qa", "data-cy", "data-track")

# Attributes treated as "stable enough" for production selectors.
_STABLE_ATTRS = ("name", "aria-label")


def _attr(meta: dict, key: str) -> Optional[str]:
    val = meta.get(key)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _escape_attr_value(value: str) -> str:
    """Escape an attribute value for inclusion in a CSS selector."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def pick_selector(meta: Optional[dict]) -> tuple[str, Optional[str]]:
    """Return ``(primary_selector, fallback_selector)`` from the shim's meta.

    Both values are CSS selector strings (or ``None`` for the fallback when
    we have no useful secondary). Callers should always honour the
    fallback — Playwright runtime tries the primary first and the fallback
    if the primary returns zero matches.
    """
    if not meta or not isinstance(meta, dict):
        return ("body", None)

    tag = _attr(meta, "tag") or "*"
    raw_path = _attr(meta, "_raw_path") or _attr(meta, "path") or None

    # 1. data-* test hooks
    for hook in _TEST_HOOK_ATTRS:
        v = _attr(meta, hook)
        if v:
            primary = f'[{hook}="{_escape_attr_value(v)}"]'
            return (primary, raw_path)

    # 2. [name=...] — extremely common on forms; survives most redesigns
    name = _attr(meta, "name")
    if name:
        primary = f'{tag}[name="{_escape_attr_value(name)}"]'
        return (primary, raw_path)

    # 2b. [type="submit"] — the canonical "the button" selector
    type_attr = _attr(meta, "type")
    if tag == "button" or (tag == "input" and type_attr in {"submit", "button"}):
        if type_attr in {"submit", "button"}:
            primary = f'{tag}[type="{type_attr}"]'
            return (primary, raw_path)

    # 2c. aria-label is a strong semantic hook
    aria = _attr(meta, "aria-label")
    if aria:
        primary = f'{tag}[aria-label="{_escape_attr_value(aria)}"]'
        return (primary, raw_path)

    # 3. role + tag
    role = _attr(meta, "role")
    if role:
        primary = f'{tag}[role="{_escape_attr_value(role)}"]'
        return (primary, raw_path)

    # 4. id (last because frameworks regenerate it)
    elem_id = _attr(meta, "id")
    if elem_id:
        # CSS identifier escaping is restrictive; prefer attribute form
        # which always works regardless of special characters.
        primary = f'{tag}[id="{_escape_attr_value(elem_id)}"]'
        return (primary, raw_path)

    # 5. fall back to the raw nth-of-type path from the shim
    if raw_path:
        return (raw_path, None)

    # 6. last resort
    return (tag, None)


def is_password_field(meta: Optional[dict]) -> bool:
    """True if the field looks like a credential we must never persist plain."""
    if not meta:
        return False
    if _attr(meta, "type") == "password":
        return True
    name = (_attr(meta, "name") or "").lower()
    elem_id = (_attr(meta, "id") or "").lower()
    return any(
        token in haystack
        for haystack in (name, elem_id)
        for token in ("password", "passwd", "pwd", "pin", "cvv")
        if haystack
    )
