"""Compile a recorded event stream into a FlowNode.config_json dict.

The output shape matches what `BrowserAutomationStepHandler.execute()` in
[backend/flows/flow_engine.py] reads, so the existing runtime can replay
the recorded flow with **no executor changes**. That is the whole bet of
the recorder feature.

Public surface:
    compile_events(events: list[RecordedEvent]) -> dict

The dict is ready to assign to `FlowNode.config_json` (after `json.dumps`).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .models import RecordedEvent
from .selector_strategy import is_password_field, pick_selector


# Reasonable defaults — UI can override after the user reviews the compiled
# config in BrowserAutomationConfigPanel.
_DEFAULT_TIMEOUT_PER_STEP = 15
_BASE_TIMEOUT = 30


def _slugify(text: str, default: str = "captured") -> str:
    """Convert a free-form string into a snake_case identifier."""
    out: list[str] = []
    last_was_sep = True
    for ch in (text or "").strip().lower():
        if ch.isalnum():
            out.append(ch)
            last_was_sep = False
        elif not last_was_sep:
            out.append("_")
            last_was_sep = True
    slug = "".join(out).strip("_")
    return slug or default


def _coalesce_fills(events: list[RecordedEvent]) -> list[RecordedEvent]:
    """Collapse consecutive `fill` events on the same selector into one.

    Browser keystroke streams emit many small `Input.insertText` calls; the
    user-meaningful action is "the final value typed into this field". We
    keep the last value and drop the intermediates so the compiled
    `selectors[]` array doesn't carry per-character noise.

    (The companion click-before-fill dedupe runs *after* row emission in
    ``_dedupe_focus_click_then_fill`` — the click's payload selector
    comes from the in-page shim and may differ in spelling from the
    fill's selector even when both target the same element. Comparing
    after both rows have run through pick_selector gives a canonical
    string to compare.)
    """
    out: list[RecordedEvent] = []
    for ev in events:
        if (
            ev.kind == "fill"
            and out
            and out[-1].kind == "fill"
            and out[-1].payload.get("selector") == ev.payload.get("selector")
        ):
            # Concatenate or replace — `Input.insertText` semantics are
            # *insert at cursor*, but since we don't track cursor position
            # we treat sequential typing on the same field as appending.
            prior = out[-1].payload.get("value") or ""
            new = ev.payload.get("value") or ""
            out[-1].payload["value"] = prior + new
            out[-1].payload["field_meta"] = (
                ev.payload.get("field_meta") or out[-1].payload.get("field_meta")
            )
            continue
        out.append(ev)
    return out


def _dedupe_focus_click_then_fill(selectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop a click row immediately followed by a fill on the same selector.

    Runs after row emission so both rows have the canonical selector
    string from ``pick_selector``. The click was just focusing the
    field before typing — Playwright's ``fill`` action focuses the
    element itself, so the click row is dead weight at replay time.
    """
    out: list[dict[str, Any]] = []
    for row in selectors:
        if (
            row.get("action") == "fill"
            and out
            and out[-1].get("action") == "click"
            and out[-1].get("selector") == row.get("selector")
        ):
            out.pop()
        out.append(row)
    return out


def _dedupe_navigate(events: list[RecordedEvent]) -> list[RecordedEvent]:
    """Drop `navigate` events that immediately follow the same URL.

    `Page.framenavigated` fires both on user goto AND on internal Chrome
    redirects (e.g., HTTP→HTTPS). Without dedupe we'd emit duplicate
    `navigate` rows in the compiled config.
    """
    out: list[RecordedEvent] = []
    last_url: Optional[str] = None
    for ev in events:
        if ev.kind == "navigate":
            url = (ev.payload or {}).get("url")
            if url == last_url:
                continue
            last_url = url
        out.append(ev)
    return out


def _row_click(meta: Optional[dict], selector_hint: Optional[str]) -> dict[str, Any]:
    primary, fallback = pick_selector(meta or {})
    if not primary or primary == "body":
        # The shim couldn't resolve a useful selector; fall back to the
        # hint (raw CSS path) the relay supplied at click time.
        if selector_hint:
            primary = selector_hint
    row: dict[str, Any] = {
        "action": "click",
        "selector": primary,
    }
    if fallback and fallback != primary:
        row["fallback_selector"] = fallback
    return row


def _row_fill(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("field_meta") or {}
    primary, fallback = pick_selector(meta)
    # Prefer the explicit selector if the relay supplied one (e.g., from
    # marker.vault flows where the UI provides a precise selector).
    if payload.get("selector"):
        primary = payload["selector"]
    row: dict[str, Any] = {
        "action": "fill",
        "selector": primary,
        "value": payload.get("value", ""),
    }
    if fallback and fallback != primary:
        row["fallback_selector"] = fallback
    if is_password_field(meta) and not _is_vault_handle(payload.get("value")):
        # Defence in depth: the compiler refuses to emit a plaintext
        # password value. The frontend should have already swapped this
        # for a pvh_ handle via the ToolPalette vault tile. If it didn't,
        # we mark the row so the API layer can reject the compile call.
        row["_needs_vault"] = True
    return row


def _is_vault_handle(value: Any) -> bool:
    """True if `value` is a vault-resolvable reference, not raw plaintext.

    The runtime accepts both the short-lived in-memory `pvh_` handles and
    the canonical `op://vault/item/field` URI form used by stored
    `browser_secret_references`. Either shape is safe to persist.
    """
    return isinstance(value, str) and (value.startswith("pvh_") or value.startswith("op://"))


def _row_captcha(payload: dict[str, Any]) -> dict[str, Any]:
    primary, fallback = pick_selector(payload.get("meta") or {})
    if payload.get("selector"):
        primary = payload["selector"]
    row: dict[str, Any] = {
        "action": "solve_captcha",
        "selector": primary,
    }
    if fallback and fallback != primary:
        row["fallback_selector"] = fallback
    return row


def _row_extract(payload: dict[str, Any]) -> dict[str, Any]:
    primary, fallback = pick_selector(payload.get("meta") or {})
    if payload.get("selector"):
        primary = payload["selector"]
    as_name = _slugify(payload.get("as") or "captured_value")
    row: dict[str, Any] = {
        "action": "extract",
        "selector": primary,
        "as": as_name,
    }
    if fallback and fallback != primary:
        row["fallback_selector"] = fallback
    return row


def _attach_vault(
    selectors: list[dict[str, Any]],
    secret_refs: list[dict[str, Any]],
    vault_payload: dict[str, Any],
) -> None:
    """Wire a `marker.vault` event into the last matching fill row.

    The UX flow is: user types into a password field → ToolPalette yellow
    chip → user picks a vault entry → frontend sends `marker.vault`. By
    the time this event arrives, the corresponding `fill` row already
    exists in `selectors`; we just swap its value for the pvh_ handle and
    append a row to `browser_secret_references` mapping the handle onto
    the right `selectors[N].value` target.
    """
    target_selector = vault_payload.get("selector")
    reference = vault_payload.get("reference")
    if not reference or not _is_vault_handle(reference):
        return

    # Walk from the end backward to find the most recent fill row whose
    # selector matches. If we can't find one, attach a new fill row so the
    # reference is still wired (defensive — shouldn't happen in normal UX).
    for idx in range(len(selectors) - 1, -1, -1):
        row = selectors[idx]
        if row.get("action") == "fill" and row.get("selector") == target_selector:
            row["value"] = reference
            row.pop("_needs_vault", None)
            secret_refs.append({
                "reference": reference,
                "target": f"selectors[{idx}].value",
            })
            return

    # No matching fill — synthesize one so we don't silently lose the wire.
    new_idx = len(selectors)
    selectors.append({
        "action": "fill",
        "selector": target_selector or "body",
        "value": reference,
    })
    secret_refs.append({
        "reference": reference,
        "target": f"selectors[{new_idx}].value",
    })


def _captcha_value_targets(selectors: list[dict[str, Any]]) -> None:
    """For each solve_captcha row, set `value_target` to the next fill row.

    The runtime's `solve_captcha` handler takes the LLM-decoded text and
    fills `value_target`'s selector. Without `value_target` the recorded
    captcha doesn't actually inject anywhere. The recorder picks the
    *next* `fill` row as the implicit target — matches the Correios shape
    in §2 of the research doc.
    """
    for idx, row in enumerate(selectors):
        if row.get("action") != "solve_captcha":
            continue
        for j in range(idx + 1, len(selectors)):
            if selectors[j].get("action") == "fill":
                row["value_target"] = selectors[j].get("selector")
                break


def compile_events(events: Iterable[RecordedEvent]) -> dict[str, Any]:
    """Compile a recording into a FlowNode.config_json dict.

    Args:
        events: ordered list of RecordedEvent (oldest first)

    Returns:
        dict ready to JSON-serialize into ``FlowNode.config_json``.
    """
    ordered = list(events)
    ordered = _dedupe_navigate(ordered)
    ordered = _coalesce_fills(ordered)

    selectors: list[dict[str, Any]] = []
    secret_refs: list[dict[str, Any]] = []
    initial_url: Optional[str] = None

    for ev in ordered:
        kind = ev.kind
        payload = ev.payload or {}

        if kind == "navigate":
            url = payload.get("url")
            if initial_url is None:
                initial_url = url
            else:
                # Mid-recording navigation — emit an explicit navigate row
                # so replay reproduces it. We don't emit one for the very
                # first navigation; that's captured by top-level `url`.
                selectors.append({"action": "navigate", "selector": url or ""})
            continue

        if kind == "load":
            # Only emit a wait_for_url if the *next* event is racy (i.e.,
            # a click/fill that happens immediately after navigation). For
            # v1 we always emit one if a load follows a navigate — it's
            # cheap insurance and Playwright's wait_for_url is idempotent.
            if selectors and selectors[-1].get("action") in ("click", "navigate"):
                url = payload.get("url") or ""
                # url_contains rather than exact match — query strings vary
                if url:
                    selectors.append({
                        "action": "wait_for_url",
                        "selector": "",  # not used by wait_for_url
                        "url_contains": url,
                        "timeout_ms": 15000,
                    })
            continue

        if kind == "click":
            selectors.append(_row_click(payload.get("meta"), payload.get("selector")))
            continue

        if kind == "fill":
            selectors.append(_row_fill(payload))
            continue

        if kind == "marker.captcha":
            selectors.append(_row_captcha(payload))
            continue

        if kind == "marker.extract":
            selectors.append(_row_extract(payload))
            continue

        if kind == "marker.vault":
            _attach_vault(selectors, secret_refs, payload)
            continue

        # Unknown kinds are silently dropped — Phase 2 only handles the
        # event types Phase 1's relay emits.

    selectors = _dedupe_focus_click_then_fill(selectors)
    _captcha_value_targets(selectors)

    # Compute a reasonable timeout — sum of per-step timeouts with a
    # generous floor. The user can override in the config panel afterward.
    timeout = _BASE_TIMEOUT + len(selectors) * _DEFAULT_TIMEOUT_PER_STEP

    config: dict[str, Any] = {
        "use_tool_mode": True,
        # `tool_action` is the canonical entry-point action the runtime
        # reads (BrowserAutomationStepHandler at flow_engine.py:4040
        # rejects the step with "Missing tool_action" if absent). The
        # manual config panel defaults this to "navigate" via its dropdown;
        # the recorder mirrors that default so a saved recording runs at
        # execution time without any additional manual editing.
        "tool_action": "navigate",
        "mode": "container",
        "provider_type": "playwright",
        "selectors": selectors,
        "browser_secret_references": secret_refs,
        "timeout_seconds": timeout,
        "session_persistence": False,
    }
    if initial_url:
        config["url"] = initial_url
    return config
