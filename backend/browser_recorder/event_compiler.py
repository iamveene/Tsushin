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

import json
from typing import Any, Iterable, Optional

from .models import RecordedEvent
from .selector_strategy import is_password_field, pick_selector


# Reasonable defaults — UI can override after the user reviews the compiled
# config in BrowserAutomationConfigPanel.
_DEFAULT_TIMEOUT_PER_STEP = 15
_BASE_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Structured "event timeline" capture
# ---------------------------------------------------------------------------
#
# A plain `marker.extract` compiles to `tool_action: extract` = innerText of
# the marked region. That's fine for a single value, but postal-tracking
# pages render a *timeline* of events, and the canonical notification needs
# structured fields (latest status/when/location, an event count, and a
# stable dedupe key). When the user marks the timeline region with the
# "timeline" capture kind, the recorder compiles an `execute_script` node
# whose JS parses the timeline into that structured shape — so a recording
# made entirely through the UI yields the same structured message a
# hand-authored flow would, with no manual config.
#
# The parser is resilient: it resolves a root from the marked selector and
# falls back to the Correios container / document, then reads the common
# ".ship-steps li.step" timeline shape. `latest_event_key` is a deterministic
# FNV-1a hash so re-runs on the same delivered event produce the same dedupe
# slug (e.g. "22-05-2026-15-46:objeto-entregue-ao-destinata:yl79uz").
_TIMELINE_PARSER_JS = r"""() => {
  const tracking_code = __TRACKING_CODE_JSON__;
  const root = document.querySelector(__ROOT_SELECTOR_JSON__) || document.querySelector('#tabs-rastreamento') || document.body;
  const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const slug = (value) => clean(value)
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  const hash = (value) => {
    let h = 2166136261;
    const text = String(value || '');
    for (let i = 0; i < text.length; i += 1) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return (h >>> 0).toString(36);
  };
  const parseEvent = (node, index) => {
    const status = clean(node.querySelector('.text-head')?.textContent || node.querySelector('strong')?.textContent || node.querySelector('h3, h4, h5')?.textContent || '');
    const text = clean(node.textContent || '');
    const dateMatch = text.match(/(\d{2}\/\d{2}\/\d{4})\s*(?:às|as)?\s*(\d{2}:\d{2})?/i);
    const at = dateMatch ? [dateMatch[1], dateMatch[2]].filter(Boolean).join(' ') : '';
    const fragments = Array.from(node.querySelectorAll('p, span, div')).map((el) => clean(el.textContent)).filter(Boolean).filter((value, idx, all) => all.indexOf(value) === idx);
    const location = fragments.find((value) => value !== status && value !== at && /(Unidade|Agência|Agencia|Centro|CTE|CDD|CEE|Objeto|BRASIL|[A-Z]{2}$)/.test(value)) || '';
    return { index, status, at, location, text };
  };
  const nodes = Array.from(root?.querySelectorAll('.ship-steps li.step, .ship-steps li, li.step') || []);
  const events = nodes.map(parseEvent).filter((event) => event.status || event.text);
  const latest = events[0] || {};
  const latest_status = latest.status || latest.text || '';
  const latest_at = latest.at || '';
  const latest_location = latest.location || '';
  const full_event_key = [latest_status, latest_at, latest_location].map(slug).filter(Boolean).join(':') || 'no-event';
  const latest_event_key = [slug(latest_at).slice(0, 16) || 'no-date', slug(latest_status).slice(0, 28) || 'status', hash([latest_status, latest_at, latest_location, latest.text].join('|'))].join(':').slice(0, 64);
  return {
    tracking_code,
    latest_status,
    latest_at,
    latest_location,
    event_count: events.length,
    events,
    latest_event_key,
    full_event_key,
    record_kind: 'postal_tracking_status',
    provider: 'correios',
    subject_key: tracking_code,
    period_key: latest_event_key,
    status: latest_status || 'unknown',
    title: `Correios ${tracking_code} - ${latest_status || 'unknown'}`,
    dedupe_key: `postal_tracking_status:correios:${tracking_code}:${latest_event_key}`
  };
}"""


def _timeline_parser_script(tracking_code: str, root_selector: str) -> str:
    """Render the timeline parser JS with the recorded code + marked root."""
    return (
        _TIMELINE_PARSER_JS
        .replace("__TRACKING_CODE_JSON__", json.dumps(tracking_code or ""))
        .replace("__ROOT_SELECTOR_JSON__", json.dumps(root_selector or "#tabs-rastreamento"))
    )


def _tracking_code_from_rows(selectors: list[dict[str, Any]]) -> str:
    """Pull the recorded tracking code from the fill rows.

    Prefers a fill whose selector names the tracking input (`objeto`), else
    the first non-vault fill value. This is the value the user actually
    typed during recording — never hardcoded.
    """
    fallback = ""
    for row in selectors:
        if row.get("action") != "fill":
            continue
        value = str(row.get("value") or "")
        if not value or value.startswith(("pvh_", "op://")):
            continue
        sel = (row.get("selector") or "").lower()
        if "objeto" in sel:
            return value
        if not fallback:
            fallback = value
    return fallback


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


_ROOT_SELECTORS = {"body", "html", "*", "document"}


def _looks_like_result_region(sel: str) -> bool:
    """True if a selector names a content/result region (not page chrome).

    Used to (a) decide whether a captcha success_selector / auto wait_for is
    trustworthy and (b) pick the timeline parser's root. On captcha-gated
    sites the results don't render at record-time, so a marked selector often
    resolves to noise (a carousel) — we only trust content-looking selectors
    and otherwise fall back to a known container.
    """
    s = (sel or "").lower()
    if not s:
        return False
    for keyword in (
        "ship-step", "ship_step", "result", "tracking",
        "rastreamento", "evento", "events", "timeline",
        "status-list", "history",
    ):
        if keyword in s:
            return True
    return False


def _row_fill(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("field_meta") or {}
    primary, fallback = pick_selector(meta)
    # Prefer the explicit selector if the relay supplied one (e.g., from
    # marker.vault flows where the UI provides a precise selector).
    if payload.get("selector"):
        primary = payload["selector"]
    # BUG-768 defence in depth: a document-root selector means the relay
    # couldn't resolve the focused element. Surface this via a marker the
    # API layer rejects rather than silently shipping a broken row.
    if primary and primary.strip() in _ROOT_SELECTORS:
        primary = None
    row: dict[str, Any] = {
        "action": "fill",
        "selector": primary,
        "value": payload.get("value", ""),
    }
    if not primary:
        row["_needs_selector"] = True
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
    if primary and primary.strip() in _ROOT_SELECTORS:
        primary = None
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
    # A "timeline" capture means the user marked an event list (e.g. a
    # postal-tracking timeline). It compiles to a structured execute_script
    # parser instead of a plain innerText extract — see
    # compile_events_into_nodes.
    if str(payload.get("capture_kind") or "").strip() == "timeline":
        row["capture_kind"] = "timeline"
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

    Fill rows whose selector couldn't be resolved (`_needs_selector`) are
    skipped — they can't be a valid value_target and would compile to a
    `body` selector at runtime (BUG-768).
    """
    for idx, row in enumerate(selectors):
        if row.get("action") != "solve_captcha":
            continue
        for j in range(idx + 1, len(selectors)):
            other = selectors[j]
            if other.get("action") != "fill":
                continue
            target = other.get("selector")
            if not target or target.strip() in _ROOT_SELECTORS:
                continue
            row["value_target"] = target
            break


def _dedupe_consecutive_clicks(selectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse two consecutive identical click rows into one.

    The recorder captures every mousePressed as a click event. If the user
    re-clicks the same input (e.g. because they didn't realise focus was
    needed, BUG-767), both clicks landed in the compiled flow as separate
    steps. The duplicate just slows replay and confuses the StepLedger.
    """
    out: list[dict[str, Any]] = []
    for row in selectors:
        if (
            row.get("action") == "click"
            and out
            and out[-1].get("action") == "click"
            and out[-1].get("selector") == row.get("selector")
        ):
            continue
        out.append(row)
    return out


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
    selectors = _dedupe_consecutive_clicks(selectors)
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


# ---------------------------------------------------------------------------
# Multi-FlowNode compile (the production-ready output)
# ---------------------------------------------------------------------------
#
# `compile_events` packs every captured action into ONE FlowNode's
# selectors[] array, but the runtime's BrowserAutomationStepHandler only
# executes the top-level `tool_action` (one action per FlowNode). That
# means a recorded multi-action flow (navigate → fill → solve_captcha →
# click → extract) compiled with the single-FlowNode shape would only
# replay the navigate at runtime — the rest is dead weight.
#
# `compile_events_into_nodes` splits the same event stream into ONE
# FlowNode per browser action, matching the canonical multi-step pattern
# (e.g. flow "Postal Track | Correios | AD468811215BR" in prod). Each
# node carries its single selector row + the right `tool_action`, and
# all nodes share a `browser_session_profile_name` so the inner Chromium
# session carries across steps. The output is a list ready to feed into
# `POST /api/flows/{id}/steps` one entry at a time.


def _slug_host(url: str) -> str:
    """Derive a short profile name from a URL host."""
    if not url:
        return "session"
    from urllib.parse import urlparse
    host = urlparse(url).hostname or "session"
    # Drop common top-level/www noise so "linkcorreios.com.br" → "linkcorreios"
    parts = host.replace("www.", "").split(".")
    return parts[0] if parts else "session"


def _node_base(profile_name: str, tool_action: str, *, timeout: int = 30) -> dict[str, Any]:
    """Shared FlowNode.config_json skeleton for a recorder-emitted node.

    Mirrors canonical multi-step flows like Postal Track | Correios |
    AD468811215BR (flow #26 in prod): session_persistence=True +
    session_ttl_seconds=1800 is enough for the Playwright context to
    carry across nodes within a single FlowRun (the BrowserSessionManager
    keys sessions by tenant+agent). Setting `browser_session_profile_name`
    here would point at a stored profile that doesn't exist for fresh
    recordings — leave it unset so the runtime uses the ephemeral
    in-FlowRun session.
    """
    return {
        "use_tool_mode": True,
        "tool_action": tool_action,
        "mode": "container",
        "provider_type": "playwright",
        "selectors": [],
        "browser_secret_references": [],
        "timeout_seconds": timeout,
        "session_persistence": True,
        "session_ttl_seconds": 1800,
    }


def compile_events_into_nodes(events: Iterable[RecordedEvent]) -> list[dict[str, Any]]:
    """Compile a recording into a LIST of FlowNode-ready dicts.

    Each dict shape:
        {
            "name": "<step_name>",
            "type": "browser_automation",
            "config_json": { ... single-action config ... },
            "timeout_seconds": int,
        }

    Caller is expected to POST each dict to
    ``POST /api/flows/{id}/steps`` (FlowNodeCreate schema). Positions can
    be assigned by the caller from list order, or by reading the
    ``_recorder_position`` hint we include for convenience.

    Notable behaviour vs the single-FlowNode `compile_events`:
      - First navigate becomes its own FlowNode with `tool_action="navigate"`
        and the top-level `url` field set.
      - Each subsequent fill/click/extract is its own FlowNode with
        `tool_action` matching the action and a single-row `selectors[]`.
      - `solve_captcha` rows keep their `value_target`; the placeholder
        fill the user typed into the captcha input AFTER marking the
        captcha is dropped (the runtime's solve_captcha skill fills the
        target via LLM-vision OCR — manual placeholder is dead weight).
      - `browser_secret_references` ride with the node that contains the
        referenced selectors[0].value, not centrally.
      - All nodes share `browser_session_profile_name=recorder_<host>`
        so the browser session survives across the chain.
    """
    # Reuse the legacy compiler to do dedup / coalesce / captcha wiring,
    # then split the resulting selectors[] into per-action nodes.
    legacy = compile_events(events)
    selectors: list[dict[str, Any]] = list(legacy.get("selectors") or [])
    secret_refs: list[dict[str, Any]] = list(legacy.get("browser_secret_references") or [])
    initial_url: Optional[str] = legacy.get("url")
    profile = _slug_host(initial_url or "")

    # Track which selector indices have a vault reference pointing at them
    # so we can ship the matching browser_secret_references with the node
    # that owns selectors[0].
    refs_by_index: dict[int, list[dict[str, Any]]] = {}
    for ref in secret_refs:
        target = (ref.get("target") or "").strip()
        # target shape: selectors[<int>].value
        if target.startswith("selectors[") and target.endswith("].value"):
            try:
                idx = int(target[len("selectors["):-len("].value")])
                refs_by_index.setdefault(idx, []).append(ref)
            except ValueError:
                pass

    # If the captcha placeholder fill landed on the same selector as the
    # solve_captcha's value_target, drop it — runtime fills it via OCR.
    captcha_targets: set[str] = {
        row.get("value_target") or ""
        for row in selectors
        if row.get("action") == "solve_captcha" and row.get("value_target")
    }
    pruned_selectors: list[dict[str, Any]] = []
    pruned_refs_by_index: dict[int, list[dict[str, Any]]] = {}
    for orig_idx, row in enumerate(selectors):
        if (
            row.get("action") == "fill"
            and row.get("selector") in captcha_targets
            and not (row.get("value") or "").startswith(("pvh_", "op://"))
        ):
            continue  # drop placeholder XXXXXX captcha fill
        new_idx = len(pruned_selectors)
        pruned_selectors.append(row)
        if orig_idx in refs_by_index:
            # Re-target refs to the new index
            for ref in refs_by_index[orig_idx]:
                pruned_refs_by_index.setdefault(new_idx, []).append({
                    **ref,
                    "target": "selectors[0].value",  # always 0 in single-row nodes
                })

    nodes: list[dict[str, Any]] = []
    # The recorded tracking code (typed into the `objeto` input) parameterizes
    # the timeline parser + the notification subject. Never hardcoded.
    tracking_code = _tracking_code_from_rows(pruned_selectors)

    # First node: navigate (if we have an initial URL)
    if initial_url:
        cfg = _node_base(profile, "navigate", timeout=30)
        cfg["url"] = initial_url
        nodes.append({
            "name": f"open_{profile}",
            "type": "browser_automation",
            "config_json": cfg,
            "timeout_seconds": 30,
            "_recorder_position": len(nodes) + 1,
        })

    # One node per selector row (single-row selectors[])
    for idx, row in enumerate(pruned_selectors):
        action = row.get("action") or "navigate"

        # Structured "event timeline" capture → wait_for(root) +
        # execute_script(parser). The wait_for always targets a concrete
        # content selector (the marked root, or the Correios container as a
        # fallback) so it never compiles to an empty selector that fails at
        # replay. The execute_script returns the structured tracking object a
        # downstream data_transform + notification template consume.
        if action == "extract" and row.get("capture_kind") == "timeline":
            # The marked selector is only trusted when it looks like a content
            # region — on a captcha-gated page the timeline isn't rendered at
            # record-time, so a marked point often resolves to chrome
            # (carousel/footer). Fall back to the Correios container; the
            # parser JS itself also falls back to document at runtime.
            marked = (row.get("selector") or "").strip()
            root_sel = marked if _looks_like_result_region(marked) else "#tabs-rastreamento"
            wait_cfg = _node_base(profile, "wait_for", timeout=30)
            wait_cfg["selectors"] = [{
                "action": "wait_for",
                "selector": root_sel,
                "state": "visible",
                "timeout_ms": 30000,
            }]
            nodes.append({
                "name": "wait_tracking_result",
                "type": "browser_automation",
                "config_json": wait_cfg,
                "timeout_seconds": 30,
                "_recorder_position": len(nodes) + 1,
            })
            es_cfg = _node_base(profile, "execute_script", timeout=60)
            es_cfg["selectors"] = {"extraction_root": root_sel}
            es_cfg["output_alias"] = "extract_tracking"
            es_cfg["tool_arguments"] = {
                "script": _timeline_parser_script(tracking_code, root_sel),
            }
            nodes.append({
                "name": "extract_tracking",
                "type": "browser_automation",
                "config_json": es_cfg,
                "timeout_seconds": 60,
                "_recorder_position": len(nodes) + 1,
            })
            continue

        # tool_action mapping — most actions are 1:1; navigate inside
        # selectors[] (mid-recording redirect) becomes a navigate FlowNode
        # whose top-level url comes from the row's selector field.
        tool_action = action
        cfg = _node_base(profile, tool_action, timeout=30)
        if action == "navigate":
            # mid-flow navigation captured in selectors[]
            cfg["url"] = row.get("selector") or ""
            # No selectors[] for a navigate node
            cfg["selectors"] = []
        else:
            # Strip the outer "action" since tool_action already carries it;
            # the row is otherwise the canonical {selector, value, ...} shape.
            row_copy = {k: v for k, v in row.items()}
            row_copy.pop("_needs_vault", None)  # never leak this to the runtime
            cfg["selectors"] = [row_copy]
        if idx in pruned_refs_by_index:
            cfg["browser_secret_references"] = pruned_refs_by_index[idx]

        # Pick a step name that's descriptive without being verbose
        def _shortname(row: dict[str, Any]) -> str:
            sel = row.get("selector") or ""
            for token in ("name=\"", "id=\"", "name='", "id='"):
                if token in sel:
                    start = sel.index(token) + len(token)
                    end = sel.find('"', start) if '"' in token else sel.find("'", start)
                    if end > start:
                        return sel[start:end]
            return sel.split(">")[-1].strip()[:24] or action

        name = f"{action}_{_shortname(row)}"[:48]
        if action == "extract" and row.get("as"):
            name = f"extract_{row.get('as')}"
        elif action == "solve_captcha":
            name = "solve_captcha"
        elif action == "wait_for_url":
            name = "wait_for_url"
        nodes.append({
            "name": name,
            "type": "browser_automation",
            "config_json": cfg,
            "timeout_seconds": 30,
            "_recorder_position": len(nodes) + 1,
        })

    nodes = _combine_captcha_chain(nodes)
    _wire_timeline_success_selector(nodes)
    # Re-number positions after the combine
    for new_pos, n in enumerate(nodes, start=1):
        n["_recorder_position"] = new_pos
    return nodes


def _wire_timeline_success_selector(nodes: list[dict[str, Any]]) -> None:
    """Give the captcha solver a success_selector when a timeline follows it.

    Without one, `solve_captcha` OCRs + submits correctly but can't *confirm*
    the results loaded, so it reports a false-negative "CAPTCHA was not solved"
    and the run ends `completed_with_errors` even though everything worked. The
    timeline root (`#tabs-rastreamento`, the same selector the wait_for/parser
    target) only renders AFTER a successful search — verified: on a failed
    captcha the wait_for for it times out — so it's a sound success barrier.
    """
    timeline_root: Optional[str] = None
    for n in nodes:
        cfg = n.get("config_json") or {}
        if cfg.get("tool_action") == "execute_script" and cfg.get("output_alias") == "extract_tracking":
            sels = cfg.get("selectors")
            if isinstance(sels, dict):
                timeline_root = sels.get("extraction_root")
            break
    if not timeline_root:
        return
    for n in nodes:
        cfg = n.get("config_json") or {}
        if cfg.get("tool_action") == "solve_captcha":
            args = cfg.setdefault("tool_arguments", {})
            args.setdefault("success_selector", timeline_root)
            break


def _combine_captcha_chain(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse the captcha sequence into one canonical solve_captcha node.

    The recorder emits atomic-per-action FlowNodes:
        ... fill(objeto) → solve_captcha(marker) → click(submit) → extract(result)

    The runtime's `solve_captcha` action expects ALL captcha-related
    selectors as a DICT (not list) on the SAME FlowNode:
        {
          "tool_action": "solve_captcha",
          "selectors": {
            "captcha_image":  "#captcha_image",
            "captcha_input":  "#captcha",
            "captcha_submit": "#b-pesquisar",
            "result_selector": "#result-panel"
          }
        }
    because solve_captcha is a *combined* skill — it OCRs the image,
    fills the input, clicks submit, and waits for the result panel.
    Separate fill/click/extract FlowNodes would race against this combined
    skill at runtime.

    If a solve_captcha row is present AND followed by a click row AND
    (optionally) an extract row, we combine them into one canonical
    FlowNode. Otherwise the chain stays atomic.
    """
    captcha_idx = next(
        (i for i, n in enumerate(nodes)
         if (n.get("config_json") or {}).get("tool_action") == "solve_captcha"),
        None,
    )
    if captcha_idx is None:
        return nodes

    cfg_captcha = nodes[captcha_idx]["config_json"]
    sels = cfg_captcha.get("selectors") or []
    if not sels:
        return nodes
    captcha_image_sel = sels[0].get("selector")
    captcha_input_sel = sels[0].get("value_target")
    if not (captcha_image_sel and captcha_input_sel):
        return nodes

    # Walk forward to find the submit click.
    #
    # BUG-773: previously this picked the FIRST click after solve_captcha,
    # which is almost always the click *into* the captcha text input (the
    # user clicks to focus, then types). Skip clicks whose selector
    # resolves to a text/captcha input — they're focus-only and not the
    # actual form submit.
    def _looks_like_submit(row_selector: str) -> bool:
        sel = (row_selector or "").lower()
        if not sel:
            return False
        # Anything that walks like a submit button: button[type=submit],
        # input[type=submit], element id/name containing "submit"/"pesquisar"/
        # "search"/"consultar"/"buscar"/"go", or a bare <button> selector.
        if "button" in sel or "type=\"submit\"" in sel or "type='submit'" in sel:
            return True
        for keyword in ("pesquisar", "submit", "consultar", "buscar", "search"):
            if keyword in sel:
                return True
        return False

    def _is_text_input(row_selector: str) -> bool:
        sel = (row_selector or "").lower()
        if not sel:
            return False
        # input#captcha, input[name="captcha"], input[type="text"], etc.
        return sel.startswith("input") and "type=\"submit\"" not in sel and "button" not in sel

    submit_idx = None
    fallback_idx = None
    for i in range(captcha_idx + 1, len(nodes)):
        cfg = nodes[i].get("config_json") or {}
        if cfg.get("tool_action") != "click":
            continue
        sels = cfg.get("selectors") or []
        sel = sels[0].get("selector") if sels else ""
        if _looks_like_submit(sel):
            submit_idx = i
            break
        if fallback_idx is None and not _is_text_input(sel):
            fallback_idx = i
    if submit_idx is None:
        submit_idx = fallback_idx
    if submit_idx is None:
        return nodes  # no usable submit click — keep atomic

    submit_cfg = nodes[submit_idx]["config_json"]
    submit_sels = submit_cfg.get("selectors") or []
    submit_sel = submit_sels[0].get("selector") if submit_sels else None
    if not submit_sel:
        return nodes

    extract_idx = next(
        (i for i in range(submit_idx + 1, len(nodes))
         if (nodes[i].get("config_json") or {}).get("tool_action") == "extract"),
        None,
    )
    extract_sel = None
    if extract_idx is not None:
        ext_sels = nodes[extract_idx]["config_json"].get("selectors") or []
        if ext_sels:
            extract_sel = ext_sels[0].get("selector")

    # BUG-774: previously we passed whatever the recorder captured as the
    # extract selector (often a noise region like the carousel image because
    # results don't render at record-time on captcha-gated sites) as
    # success_selector. At runtime that selector matches immediately —
    # before the real results have loaded — and the captcha skill exits
    # before the page settles. Restrict success_selector to selectors that
    # look like content regions; otherwise leave it unset and let the
    # subsequent wait_for step (auto-inserted below if missing) gate things.
    # (`_looks_like_result_region` is module-level so the timeline-capture
    # path can reuse the same content-region heuristic.)
    result_sel = extract_sel if _looks_like_result_region(extract_sel or "") else None

    # BUG-776: if the recorder didn't capture a wait_for step between
    # submit and extract, insert one targeting the extract's selector
    # (when it's content-like) — without it the runtime's extract races
    # the page reload that the captcha submission triggers and pulls
    # empty/wrong content.
    wait_for_node: Optional[dict[str, Any]] = None
    has_wait_between = False
    if extract_idx is not None:
        for i in range(submit_idx + 1, extract_idx):
            if (nodes[i].get("config_json") or {}).get("tool_action") in ("wait_for", "wait_for_url"):
                has_wait_between = True
                break
        # Never auto-insert a wait_for with an empty/whitespace selector — at
        # replay that raises `wait_for_selector: Unexpected token "" while
        # parsing css selector ""` (observed on flow #271 run #50171). Require
        # a concrete content-region selector.
        if (
            not has_wait_between
            and (extract_sel or "").strip()
            and _looks_like_result_region(extract_sel or "")
        ):
            wait_cfg = _node_base(
                (cfg_captcha.get("browser_session_profile_name") or ""),
                "wait_for",
                timeout=30,
            )
            wait_cfg["selectors"] = [{
                "action": "wait_for",
                "selector": extract_sel,
                "state": "visible",
                "timeout_ms": 30000,
            }]
            wait_for_node = {
                "name": "wait_tracking_result",
                "type": "browser_automation",
                "config_json": wait_cfg,
                "timeout_seconds": 30,
            }

    # Canonical solve_captcha uses `tool_arguments` (not `selectors`) with
    # the specific keys the BrowserAutomationSkill expects:
    #   selector         → captcha image
    #   input_selector   → captcha text input
    #   submit_selector  → submit button
    #   success_selector → element that appears on success (acts as a wait barrier)
    # Verified against prod flow #26's solve_captcha config.
    #
    # The runtime defaults `solver_provider` to "ollama" with a 60s
    # httpx ReadTimeout per attempt and NO retry on solver exceptions
    # (only retries on empty guesses). On tenants where Ollama is on a
    # cold model or under load, ReadTimeout fires before the OCR is done
    # and the whole captcha step fails. Emitting `solver_timeout_seconds:
    # 120` gives the Ollama call breathing room; that's also a no-op
    # when a tenant has Gemini configured as the default provider
    # (Gemini calls don't honour this param directly but its native
    # timeout is generous).
    captcha_args: dict[str, Any] = {
        "selector": captcha_image_sel,
        "input_selector": captcha_input_sel,
        "submit_selector": submit_sel,
        # Default to the Gemini provider — Gemini-Flash-Lite vision is
        # significantly faster (typically <10s) than a cold Ollama
        # multimodal model load (60-180s). Tenants without a Gemini
        # provider configured can override to "ollama" by editing the
        # solve_captcha step after recording; the runtime falls back
        # gracefully and the bumped timeout keeps Ollama viable.
        "solver_provider": "gemini",
        "solver_timeout_seconds": 120,
    }
    if result_sel:
        captcha_args["success_selector"] = result_sel

    combined: dict[str, Any] = {
        "name": "solve_captcha",
        "type": "browser_automation",
        # Bumped timeout — solve_captcha invokes LLM-vision OCR which can
        # take 30-90s per attempt + retries. Canonical flow #26 uses 1300s.
        "timeout_seconds": 1300,
        "config_json": {
            "use_tool_mode": True,
            "tool_action": "solve_captcha",
            "mode": "container",
            "provider_type": "playwright",
            "tool_arguments": captcha_args,
            "browser_secret_references": [],
            "timeout_seconds": 1300,
            "session_persistence": True,
            "session_ttl_seconds": 1800,
        },
    }

    # Remove the captcha, click, and (if present) extract nodes; insert combined.
    # BUG-776: keep the extract step separately so we can interpose a wait_for
    # between the combined solve_captcha (which submits) and the extract.
    drop_indices = {captcha_idx, submit_idx}
    kept = [n for i, n in enumerate(nodes) if i not in drop_indices]
    insert_pos = sum(1 for i in range(captcha_idx) if i not in drop_indices)
    insert_items: list[dict[str, Any]] = [combined]
    if wait_for_node is not None:
        insert_items.append(wait_for_node)
    kept[insert_pos:insert_pos] = insert_items
    return kept


# ---------------------------------------------------------------------------
# Group compile shape — wraps the multi-FlowNode list in a single
# `browser_group` parent so the flow editor and watcher can render one
# collapsible card per recording instead of N flat browser_automation rows
# interleaved with surrounding notification / message / gate steps.
# ---------------------------------------------------------------------------


def _target_host(events: Iterable[RecordedEvent]) -> str:
    """Pull the first navigate URL's host so the group header can show it."""
    for ev in events:
        if ev.kind == "navigate":
            url = (ev.payload or {}).get("url") or ""
            if not url:
                continue
            from urllib.parse import urlparse
            host = urlparse(url).hostname or url
            return host.replace("www.", "")
    return "browser session"


def _group_driver(events: Iterable[RecordedEvent]) -> str:
    """Derive a single driver label for the group from per-event drivers.

    Returns "human", "agent", or "mixed". Falls back to "human" if no event
    carried a driver (very old sessions or unit-test fixtures that bypass
    `RecordingSession.append_event`).
    """
    seen: set[str] = set()
    for ev in events:
        if ev.recorded_driver:
            seen.add(ev.recorded_driver)
    if not seen:
        return "human"
    if len(seen) == 1:
        return next(iter(seen))
    return "mixed"


def _action_screenshots(events: list[RecordedEvent]) -> list[Optional[str]]:
    """Pick one screenshot per "action-bearing" event in original order.

    The multi-node compiler emits one FlowNode per navigate, fill (post-
    coalesce), click, marker.captcha (becomes solve_captcha), marker.extract,
    and marker.vault. We walk events in order and emit the screenshot
    captured at the moment of each such action so the group's child rows
    can render a per-step thumbnail.

    Returns one entry per action event. Length will roughly match the
    compiled child node list; callers zip with `min(len(...), len(...))`.
    """
    out: list[Optional[str]] = []
    last_fill_selector: Optional[str] = None
    for ev in events:
        kind = ev.kind
        # Coalesce sequential fills on the same selector — only keep the
        # screenshot from the final keystroke so the thumbnail reflects the
        # completed input. This mirrors `_coalesce_fills`.
        if kind == "fill":
            sel = (ev.payload or {}).get("selector")
            if sel and sel == last_fill_selector and out:
                out[-1] = ev.screenshot_b64 or out[-1]
                continue
            last_fill_selector = sel
            out.append(ev.screenshot_b64)
            continue
        last_fill_selector = None
        if kind in ("navigate", "click", "marker.captcha", "marker.extract", "marker.vault"):
            out.append(ev.screenshot_b64)
            continue
        # load / key / other plumbing events don't map to a FlowNode
    return out


def _notify_slug(recipient: str) -> str:
    base = _slugify((recipient or "").lstrip("@"), default="recipient")
    return f"notify_{base}"[:48]


def _build_tracking_trailing_nodes(
    tracking_code: str,
    notify_recipient: Optional[str],
) -> list[dict[str, Any]]:
    """Trailing data_transform + notification for a timeline-capture flow.

    These ride AFTER the browser group so the recorder, driven entirely from
    the UI, produces the full canonical pipeline: the execute_script node
    returns the structured tracking object; `normalize_tracking` surfaces it
    as `data_preview.*`; the notification templates the canonical message.
    No footer — the message ends at the Dedupe line.
    """
    normalize = {
        "name": "normalize_tracking",
        "type": "data_transform",
        "config_json": {
            "transform_mode": "json_path",
            "source_step": "extract_tracking",
            "source_path": "metadata.result",
            "output_alias": "normalize_tracking",
        },
        "timeout_seconds": 15,
    }
    nodes: list[dict[str, Any]] = [normalize]

    recipient = (notify_recipient or "").strip()
    if recipient:
        code = tracking_code or ""
        message_template = (
            f"Correios {code} update\n"
            "Status: {{normalize_tracking.data_preview.latest_status}}\n"
            "When: {{normalize_tracking.data_preview.latest_at}}\n"
            "Location: {{normalize_tracking.data_preview.latest_location}}\n"
            "Events: {{normalize_tracking.data_preview.event_count}}\n"
            "Dedupe: {{normalize_tracking.data_preview.latest_event_key}}"
        )
        nodes.append({
            "name": _notify_slug(recipient),
            "type": "notification",
            "config_json": {
                "channel": "whatsapp",
                "recipient": recipient,
                "recipients": [recipient],
                "message_template": message_template,
            },
            "timeout_seconds": 30,
            # Per user-guide §9 the trailing notification observes the flow's
            # result; it must never propagate its own delivery failure.
            "on_failure": "continue",
        })
    return nodes


def compile_events_into_group(
    events: Iterable[RecordedEvent],
    *,
    recording_id: str,
    notify_recipient: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Return a `browser_group` parent + annotated child nodes.

    Shape (all fields land in FlowNode.config_json after the caller persists):

        {
            "group_node": {
                "name": "browser_group_<host>",
                "type": "browser_group",
                "config_json": {
                    "group_recording_id": <recording_id>,
                    "recorded_driver": "human"|"agent"|"mixed",
                    "recorded_at": <iso8601>,
                    "target_host": <host>,
                    "child_count": <int>,
                    "event_count": <int>,
                },
            },
            "child_nodes": [
                # Same shape as compile_events_into_nodes() entries, with
                # group_recording_id + group_index + recorded_driver +
                # recorded_at + screenshot_b64 inlined into config_json so
                # the BrowserGroupStep card can render them without a
                # separate fetch.
                ...
            ],
        }

    Returns None if the event stream produced zero compilable children.
    """
    event_list = list(events)
    children = compile_events_into_nodes(event_list)
    if not children:
        return None

    import datetime as _dt
    recorded_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    host = _target_host(event_list)
    driver = _group_driver(event_list)
    shots = _action_screenshots(event_list)

    for idx, child in enumerate(children):
        cfg = child.setdefault("config_json", {})
        cfg["group_recording_id"] = recording_id
        cfg["group_index"] = idx
        cfg["recorded_driver"] = driver
        cfg["recorded_at"] = recorded_at
        if idx < len(shots) and shots[idx]:
            cfg["screenshot_b64"] = shots[idx]

    group_node = {
        "name": f"browser_group_{host}"[:48],
        "type": "browser_group",
        "config_json": {
            "group_recording_id": recording_id,
            "recorded_driver": driver,
            "recorded_at": recorded_at,
            "target_host": host,
            "child_count": len(children),
            "event_count": len(event_list),
        },
        # The parent is a pure UI marker — its handler is a no-op (see
        # BrowserGroupStepHandler in backend/flows/flow_engine.py), so a
        # very short timeout is plenty.
        "timeout_seconds": 5,
        "_recorder_position": 0,
    }

    # When the recording captured a structured "event timeline", auto-wire the
    # trailing data_transform + notification so the UI-only recording yields
    # the full canonical pipeline. These live OUTSIDE the browser group (they
    # aren't browser steps) and the caller inserts them after the children.
    has_timeline = any(
        (c.get("config_json") or {}).get("output_alias") == "extract_tracking"
        and (c.get("config_json") or {}).get("tool_action") == "execute_script"
        for c in children
    )
    trailing_nodes: list[dict[str, Any]] = []
    if has_timeline:
        tracking_code = _tracking_code_from_rows(
            (compile_events(event_list).get("selectors") or [])
        )
        trailing_nodes = _build_tracking_trailing_nodes(tracking_code, notify_recipient)

    return {
        "group_node": group_node,
        "child_nodes": children,
        "trailing_nodes": trailing_nodes,
    }
