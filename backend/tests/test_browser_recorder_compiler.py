"""Unit tests for the browser-recorder event compiler.

These tests are pure — no Playwright, no DB. They feed synthetic
RecordedEvent sequences into compile_events() and assert the output shape
matches what BrowserAutomationStepHandler reads.

Reference shape: the Correios postal-tracking flow described in
.private/BROWSER_RECORDER_RESEARCH.md §2.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from browser_recorder.event_compiler import compile_events  # noqa: E402
from browser_recorder.models import RecordedEvent  # noqa: E402
from browser_recorder.selector_strategy import (  # noqa: E402
    is_password_field,
    pick_selector,
)


# ---------------------------------------------------------------------------
# Selector ladder
# ---------------------------------------------------------------------------


def test_selector_prefers_data_testid_over_everything():
    primary, fallback = pick_selector({
        "tag": "input",
        "data-testid": "tracking-input",
        "id": "objs",
        "name": "objetos",
    })
    assert primary == '[data-testid="tracking-input"]'


def test_selector_falls_back_to_name_attr():
    primary, _ = pick_selector({"tag": "input", "name": "objetos"})
    assert primary == 'input[name="objetos"]'


def test_selector_button_type_submit():
    primary, _ = pick_selector({"tag": "button", "type": "submit"})
    assert primary == 'button[type="submit"]'


def test_selector_aria_label():
    primary, _ = pick_selector({"tag": "a", "aria-label": "Rastrear"})
    assert primary == 'a[aria-label="Rastrear"]'


def test_selector_escapes_quotes_in_attr_value():
    primary, _ = pick_selector({"tag": "input", "name": 'weird"name'})
    assert '\\"' in primary


def test_password_detection_by_type():
    assert is_password_field({"type": "password"})
    assert is_password_field({"type": "text", "name": "userPassword"})
    assert is_password_field({"type": "text", "id": "pin_code"})
    assert not is_password_field({"type": "text", "name": "email"})


# ---------------------------------------------------------------------------
# Event compiler — happy path
# ---------------------------------------------------------------------------


def _events_correios_shaped():
    """Synthetic events resembling a Correios tracking recording.

    Sequence:
      1. user opens linkcorreios.com.br             → navigate
      2. (auto) load event                          → load
      3. types tracking code into objetos input     → fill (coalesces typing)
      4. marks the captcha image                    → marker.captcha
      5. clicks submit                              → click
      6. (auto) load event                          → load
      7. marks the result panel as output           → marker.extract
    """
    return [
        RecordedEvent("navigate", {"url": "https://www.linkcorreios.com.br/"}),
        RecordedEvent("load", {"url": "https://www.linkcorreios.com.br/"}),
        RecordedEvent("fill", {
            "selector": 'input[name="objetos"]',
            "value": "AD",
            "field_meta": {"tag": "input", "name": "objetos", "type": "text"},
        }),
        RecordedEvent("fill", {
            "selector": 'input[name="objetos"]',
            "value": "468811215BR",
            "field_meta": {"tag": "input", "name": "objetos", "type": "text"},
        }),
        RecordedEvent("marker.captcha", {
            "rect": [10, 200, 120, 40],
            "selector": "img.captcha",
            "meta": {"tag": "img"},
        }),
        RecordedEvent("click", {
            "x": 320, "y": 280,
            "selector": 'button[type="submit"]',
            "meta": {"tag": "button", "type": "submit"},
        }),
        RecordedEvent("load", {"url": "https://www.linkcorreios.com.br/?objeto=AD468811215BR"}),
        RecordedEvent("marker.extract", {
            "rect": [0, 400, 800, 200],
            "selector": ".rastreamento-resultado",
            "meta": {"tag": "div", "data-testid": "rastreamento-resultado"},
            "as": "delivery status",
        }),
    ]


def test_correios_compile_basic_shape():
    config = compile_events(_events_correios_shaped())

    # The top-level shape matches what BrowserAutomationStepHandler expects
    assert config["use_tool_mode"] is True
    assert config["mode"] == "container"
    assert config["provider_type"] == "playwright"
    assert config["url"] == "https://www.linkcorreios.com.br/"
    assert config["session_persistence"] is False
    assert isinstance(config["timeout_seconds"], int)
    assert config["browser_secret_references"] == []


def test_compile_emits_top_level_tool_action():
    """BrowserAutomationStepHandler rejects the step with
    'Missing tool_action for browser automation step' when the top-level
    config_json doesn't carry a `tool_action` field. The manual config
    panel sets this via its dropdown (default 'navigate'); the recorder
    must mirror that default so a saved recording runs at execution time
    without any additional manual editing. Regression test for the
    Correios+Notify-Vini E2E loop.
    """
    config = compile_events(_events_correios_shaped())
    assert config.get("tool_action") == "navigate"

    # Even an empty recording emits the tool_action — the flow editor
    # surfaces it whether the user keeps the dropdown default or not.
    empty = compile_events([])
    assert empty.get("tool_action") == "navigate"


def test_correios_actions_in_order():
    config = compile_events(_events_correios_shaped())
    actions = [s["action"] for s in config["selectors"]]
    # Expected sequence — see research doc §2
    assert actions[0] == "fill"
    assert actions[1] == "solve_captcha"
    assert actions[2] == "click"
    # wait_for_url is added because the click is followed by a load
    assert "wait_for_url" in actions
    assert actions[-1] == "extract"


def test_correios_fill_coalesces_typing():
    config = compile_events(_events_correios_shaped())
    fills = [s for s in config["selectors"] if s["action"] == "fill"]
    assert len(fills) == 1
    assert fills[0]["value"] == "AD468811215BR"


def test_correios_captcha_value_target_points_at_next_fill():
    # In the canonical Correios shape, the captcha solve targets a captcha
    # text input that follows. Our synthetic sequence has solve_captcha
    # without a following fill, so value_target should be absent. Add a
    # fill after the captcha and re-check.
    events = list(_events_correios_shaped())
    captcha_idx = next(i for i, e in enumerate(events) if e.kind == "marker.captcha")
    events.insert(captcha_idx + 1, RecordedEvent("fill", {
        "selector": 'input[name="captcha"]',
        "value": "",
        "field_meta": {"tag": "input", "name": "captcha"},
    }))
    config = compile_events(events)
    captcha_row = next(s for s in config["selectors"] if s["action"] == "solve_captcha")
    assert captcha_row["value_target"] == 'input[name="captcha"]'


def test_extract_as_is_slugified():
    config = compile_events(_events_correios_shaped())
    extract = next(s for s in config["selectors"] if s["action"] == "extract")
    assert extract["as"] == "delivery_status"


# ---------------------------------------------------------------------------
# Password / vault wiring
# ---------------------------------------------------------------------------


def test_password_field_emits_needs_vault_marker():
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/login"}),
        RecordedEvent("fill", {
            "selector": 'input[name="password"]',
            "value": "leaked-plaintext-pw",
            "field_meta": {"tag": "input", "name": "password", "type": "password"},
        }),
    ]
    config = compile_events(events)
    fill = next(s for s in config["selectors"] if s["action"] == "fill")
    # The compiler refuses to silently emit a password — it marks the row
    # so the API/UI layer rejects the compile until vault is wired.
    assert fill.get("_needs_vault") is True


def test_marker_vault_swaps_plaintext_for_handle():
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/login"}),
        RecordedEvent("fill", {
            "selector": 'input[name="password"]',
            "value": "leaked",
            "field_meta": {"tag": "input", "name": "password", "type": "password"},
        }),
        RecordedEvent("marker.vault", {
            "selector": 'input[name="password"]',
            "reference": "pvh_abc123",
        }),
    ]
    config = compile_events(events)
    fill = next(s for s in config["selectors"] if s["action"] == "fill")
    assert fill["value"] == "pvh_abc123"
    assert "_needs_vault" not in fill
    refs = config["browser_secret_references"]
    assert len(refs) == 1
    assert refs[0]["reference"] == "pvh_abc123"
    # target points at the fill row's index in selectors[]
    assert refs[0]["target"].startswith("selectors[")
    assert refs[0]["target"].endswith("].value")


def test_marker_vault_rejects_non_pvh_reference():
    events = [
        RecordedEvent("navigate", {"url": "https://example.com"}),
        RecordedEvent("fill", {"selector": "input", "value": "x", "field_meta": {"tag": "input"}}),
        RecordedEvent("marker.vault", {"selector": "input", "reference": "not-a-handle"}),
    ]
    config = compile_events(events)
    # Bad reference is silently dropped — defence in depth happens at the
    # API/UI layers; the compiler just refuses to wire it.
    assert config["browser_secret_references"] == []


def test_marker_vault_accepts_op_uri():
    """The PasswordVaultReferencePicker emits op://vault/item/field URIs.

    These need to round-trip through the recorder as first-class secret
    refs — the flow runtime's resolver tries pvh_ first then falls back
    to a vault lookup against op:// URIs.
    """
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/login"}),
        RecordedEvent("fill", {
            "selector": 'input[name="password"]',
            "value": "tmp",
            "field_meta": {"tag": "input", "name": "password", "type": "password"},
        }),
        RecordedEvent("marker.vault", {
            "selector": 'input[name="password"]',
            "reference": "op://Tsushin Prod/Correios/password",
        }),
    ]
    config = compile_events(events)
    fill = next(s for s in config["selectors"] if s["action"] == "fill")
    assert fill["value"] == "op://Tsushin Prod/Correios/password"
    assert "_needs_vault" not in fill
    assert len(config["browser_secret_references"]) == 1
    assert config["browser_secret_references"][0]["reference"].startswith("op://")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_events_produces_safe_skeleton():
    config = compile_events([])
    assert config["selectors"] == []
    assert config["browser_secret_references"] == []
    assert "url" not in config  # no first navigate → no top-level url


def test_dedup_navigate_collapses_redirects():
    # Two framenavigated events to the same URL (e.g., HTTP→HTTPS redirect)
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("click", {
            "selector": "button", "meta": {"tag": "button"},
        }),
    ]
    config = compile_events(events)
    actions = [s["action"] for s in config["selectors"]]
    # The first navigate sets top-level url; the dup is dropped; only the
    # click remains in selectors[].
    assert actions == ["click"]
    assert config["url"] == "https://example.com/"


def test_focus_click_before_fill_is_deduped():
    """A click that focuses an input before typing should not survive
    into the compiled selectors[]. The runtime's `fill` action focuses
    the element itself, so the click row is dead weight.

    Without dedupe the Correios recording would emit:
        [0] click input[name=id]
        [1] fill  input[name=id]  value=AD468811215BR
    With dedupe only the fill remains.
    """
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("click", {
            "x": 100, "y": 200,
            "selector": 'input[name="id"]',
            "meta": {"tag": "input", "name": "id", "type": "text"},
        }),
        RecordedEvent("fill", {
            "selector": 'input[name="id"]',
            "value": "AD468811215BR",
            "field_meta": {"tag": "input", "name": "id", "type": "text"},
        }),
    ]
    config = compile_events(events)
    actions = [s["action"] for s in config["selectors"]]
    assert actions == ["fill"]
    assert config["selectors"][0]["value"] == "AD468811215BR"


def test_click_then_fill_on_different_selector_is_preserved():
    """The dedupe only kicks in when the click and fill target the same
    selector — clicking elsewhere and then filling a different field
    must keep both rows."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("click", {
            "selector": "button.open-form",
            "meta": {"tag": "button"},
        }),
        RecordedEvent("fill", {
            "selector": 'input[name="id"]',
            "value": "AD",
            "field_meta": {"tag": "input", "name": "id"},
        }),
    ]
    config = compile_events(events)
    actions = [s["action"] for s in config["selectors"]]
    assert actions == ["click", "fill"]


def test_mid_recording_navigate_emits_row():
    events = [
        RecordedEvent("navigate", {"url": "https://a.example/"}),
        RecordedEvent("click", {"selector": "a", "meta": {"tag": "a"}}),
        RecordedEvent("navigate", {"url": "https://b.example/"}),  # different host
        RecordedEvent("click", {"selector": "button", "meta": {"tag": "button"}}),
    ]
    config = compile_events(events)
    actions = [s["action"] for s in config["selectors"]]
    assert actions.count("navigate") == 1
    assert "click" in actions
    assert config["url"] == "https://a.example/"
