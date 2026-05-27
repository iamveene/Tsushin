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

from browser_recorder.event_compiler import (  # noqa: E402
    compile_events,
    compile_events_into_group,
    compile_events_into_nodes,
)
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


def test_compile_into_nodes_emits_one_node_per_action():
    """Resolves task #28: the runtime executes a single tool_action per
    FlowNode, so the recorder must emit one FlowNode per browser action
    (matching the canonical multi-step pattern of flow #26). The legacy
    single-FlowNode shape from compile_events() doesn't replay the
    chain — only navigate runs.
    """
    nodes = compile_events_into_nodes(_events_correios_shaped())
    actions = [n["config_json"]["tool_action"] for n in nodes]

    # First node is the navigate; subsequent nodes follow the chain.
    assert actions[0] == "navigate"
    assert "fill" in actions
    assert "solve_captcha" in actions
    assert "click" in actions
    assert "extract" in actions

    # Each node has exactly one selector row (except navigate which has none)
    for n in nodes:
        sels = n["config_json"]["selectors"]
        if n["config_json"]["tool_action"] == "navigate":
            assert sels == []
        else:
            assert len(sels) == 1, f"node {n['name']!r} should have 1 selector, got {len(sels)}"


def test_compile_into_nodes_session_persistence_shared_across_nodes():
    """All nodes must have session_persistence=True so the Playwright
    context (cookies, captcha state, redirects) carries across the chain
    at runtime. We mirror canonical flow #26's pattern: persistence on
    + session_ttl_seconds=1800, with NO browser_session_profile_name
    (the runtime keys sessions by tenant+agent within a FlowRun and
    setting a profile name would point at a non-existent stored profile)."""
    nodes = compile_events_into_nodes(_events_correios_shaped())
    for n in nodes:
        cfg = n["config_json"]
        assert cfg["session_persistence"] is True
        assert cfg["session_ttl_seconds"] == 1800
        assert "browser_session_profile_name" not in cfg


def test_compile_into_nodes_drops_placeholder_captcha_fill():
    """When the user marks the captcha image AND then types a placeholder
    into the captcha input (before clicking submit), the recorder records
    both events. The runtime's solve_captcha skill fills the captcha
    input via OCR — the placeholder fill is dead weight that would
    overwrite the OCR'd value. Multi-node compile drops it.
    """
    events = [
        RecordedEvent("navigate", {"url": "https://rastreamento.correios.com.br/app/index.php"}),
        RecordedEvent("fill", {
            "selector": 'input[name="objeto"]', "value": "AD468811215BR",
            "field_meta": {"tag": "input", "name": "objeto"},
        }),
        RecordedEvent("marker.captcha", {
            "rect": [101, 313, 424, 158],
            "selector": "img#captcha_image",
            "meta": {"tag": "img", "id": "captcha_image"},
        }),
        # Placeholder typed into the captcha field — should be dropped
        RecordedEvent("fill", {
            "selector": 'input[name="captcha"]', "value": "XXXXXX",
            "field_meta": {"tag": "input", "name": "captcha"},
        }),
        RecordedEvent("click", {
            "selector": 'button[name="b-pesquisar"]',
            "meta": {"tag": "button", "name": "b-pesquisar"},
        }),
    ]
    nodes = compile_events_into_nodes(events)
    actions = [n["config_json"]["tool_action"] for n in nodes]
    # After combine: navigate, fill (objeto), solve_captcha_combined.
    # click was folded into solve_captcha; placeholder captcha fill was dropped.
    assert "solve_captcha" in actions
    assert actions.count("fill") == 1  # only objeto, no placeholder captcha fill
    assert actions.count("click") == 0  # submit got folded into solve_captcha
    # Canonical solve_captcha uses DICT selectors with named keys
    captcha_node = next(n for n in nodes if n["config_json"]["tool_action"] == "solve_captcha")
    # Canonical uses `tool_arguments` with specific keys
    args = captcha_node["config_json"]["tool_arguments"]
    assert isinstance(args, dict)
    assert args.get("input_selector") == 'input[name="captcha"]'
    assert args.get("submit_selector") == 'button[name="b-pesquisar"]'


def test_compile_into_nodes_combines_captcha_chain_into_canonical_node():
    """The runtime's solve_captcha is a COMBINED skill (OCR + fill +
    submit + wait for result). When the recorder captures the canonical
    captcha sequence (marker.captcha → fill captcha_input → click
    submit → marker.extract result), the multi-FlowNode compiler should
    combine those into ONE solve_captcha FlowNode with selectors as a
    DICT (canonical shape), matching how `Postal Track | Correios | …`
    (flow #26 in prod) is structured."""
    events = [
        RecordedEvent("navigate", {"url": "https://rastreamento.correios.com.br/app/index.php"}),
        RecordedEvent("fill", {
            "selector": 'input[name="objeto"]', "value": "AD468811215BR",
            "field_meta": {"tag": "input", "name": "objeto"},
        }),
        RecordedEvent("marker.captcha", {
            "rect": [101, 313, 424, 158],
            "selector": "img#captcha_image",
            "meta": {"tag": "img", "id": "captcha_image"},
        }),
        RecordedEvent("fill", {
            "selector": 'input[name="captcha"]', "value": "XXXXXX",
            "field_meta": {"tag": "input", "name": "captcha"},
        }),
        RecordedEvent("click", {
            "selector": 'button[name="b-pesquisar"]',
            "meta": {"tag": "button", "name": "b-pesquisar"},
        }),
        RecordedEvent("marker.extract", {
            "rect": [100, 500, 1080, 200],
            "selector": "#result-panel",
            "meta": {"tag": "div", "id": "result-panel"},
            "as": "delivery_status",
        }),
    ]
    nodes = compile_events_into_nodes(events)
    actions = [n["config_json"]["tool_action"] for n in nodes]
    assert actions.count("solve_captcha") == 1
    assert actions.count("click") == 0, "click should be folded into solve_captcha"
    # BUG-774/776: extract is now KEPT separate (matches canonical flow #33
    # pattern: solve_captcha + wait_for + extract). Lets the user upgrade
    # extract → execute_script for structured tracking output without
    # losing the captcha-skill's reliability barrier.
    assert actions.count("extract") == 1, "extract must stay as its own step"
    assert actions.count("wait_for") == 1, "wait_for must auto-insert between captcha and extract"
    assert actions.index("solve_captcha") < actions.index("wait_for") < actions.index("extract")

    captcha_node = next(n for n in nodes if n["config_json"]["tool_action"] == "solve_captcha")
    # Canonical uses `tool_arguments` (not `selectors`) with specific keys
    args = captcha_node["config_json"]["tool_arguments"]
    assert isinstance(args, dict)
    assert args.get("selector") == "img#captcha_image"
    assert args.get("input_selector") == 'input[name="captcha"]'
    assert args.get("submit_selector") == 'button[name="b-pesquisar"]'
    assert args.get("success_selector") == "#result-panel"
    # Solver defaults to gemini (fast cloud OCR); ollama fallback via
    # tenant edit. solver_timeout_seconds keeps Ollama viable too.
    assert args.get("solver_provider") == "gemini"
    assert args.get("solver_timeout_seconds") == 120
    # `selectors` field should NOT be set on solve_captcha nodes
    assert "selectors" not in captcha_node["config_json"] or not captcha_node["config_json"].get("selectors")


def test_compile_into_nodes_keeps_vault_reference_with_owning_node():
    """When a fill row references a vault entry, the matching
    browser_secret_references row must ride with the node that owns
    that fill — re-targeted to selectors[0].value (because each node
    has only one selector)."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/login"}),
        RecordedEvent("fill", {
            "selector": 'input[name="password"]', "value": "leaked",
            "field_meta": {"tag": "input", "name": "password", "type": "password"},
        }),
        RecordedEvent("marker.vault", {
            "selector": 'input[name="password"]',
            "reference": "op://Tsushin/Vault/password",
        }),
    ]
    nodes = compile_events_into_nodes(events)
    # Find the fill node
    fill_node = next(n for n in nodes if n["config_json"]["tool_action"] == "fill")
    sel0 = fill_node["config_json"]["selectors"][0]
    assert sel0.get("value") == "op://Tsushin/Vault/password"
    refs = fill_node["config_json"]["browser_secret_references"]
    assert len(refs) == 1
    assert refs[0].get("reference") == "op://Tsushin/Vault/password"
    # Target re-pointed to selectors[0].value (single-row per node)
    assert refs[0].get("target") == "selectors[0].value"


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


# ---------------------------------------------------------------------------
# Group compile shape — wraps multi-FlowNode children in a browser_group
# parent so the editor + watcher render one collapsible card per recording.
# ---------------------------------------------------------------------------


def test_compile_into_group_returns_parent_plus_children():
    result = compile_events_into_group(
        _events_correios_shaped(),
        recording_id="rec_abc123",
    )
    assert result is not None
    parent = result["group_node"]
    children = result["child_nodes"]

    assert parent["type"] == "browser_group"
    assert parent["config_json"]["group_recording_id"] == "rec_abc123"
    assert parent["config_json"]["child_count"] == len(children)
    assert parent["config_json"]["target_host"] == "linkcorreios.com.br"

    # Children are the same shape as compile_events_into_nodes, but annotated
    flat = compile_events_into_nodes(_events_correios_shaped())
    assert len(children) == len(flat)
    for idx, child in enumerate(children):
        cfg = child["config_json"]
        assert cfg["group_recording_id"] == "rec_abc123"
        assert cfg["group_index"] == idx
        assert child["type"] == "browser_automation"


def test_compile_into_group_empty_events_returns_none():
    assert compile_events_into_group([], recording_id="rec_empty") is None


def test_compile_into_group_attaches_per_event_screenshots():
    """Each child's config_json carries the screenshot captured at the
    moment the action's source event was recorded, so the BrowserGroupStep
    card can render a thumbnail next to the action label."""
    events = [
        RecordedEvent(
            "navigate",
            {"url": "https://example.com/"},
            screenshot_b64="SHOT_NAV",
        ),
        RecordedEvent(
            "fill",
            {
                "selector": 'input[name="q"]', "value": "hello",
                "field_meta": {"tag": "input", "name": "q"},
            },
            screenshot_b64="SHOT_FILL",
        ),
    ]
    result = compile_events_into_group(events, recording_id="rec_shots")
    children = result["child_nodes"]
    # First child is the navigate; second is the fill
    assert children[0]["config_json"].get("screenshot_b64") == "SHOT_NAV"
    fill_child = next(c for c in children if c["config_json"]["tool_action"] == "fill")
    assert fill_child["config_json"].get("screenshot_b64") == "SHOT_FILL"


def test_compile_into_group_driver_label_is_homogeneous_when_one_source():
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}, recorded_driver="human"),
        RecordedEvent(
            "fill",
            {"selector": 'input[name="q"]', "value": "x", "field_meta": {"tag": "input", "name": "q"}},
            recorded_driver="human",
        ),
    ]
    result = compile_events_into_group(events, recording_id="rec_h")
    assert result["group_node"]["config_json"]["recorded_driver"] == "human"
    for child in result["child_nodes"]:
        assert child["config_json"]["recorded_driver"] == "human"


def test_compile_into_group_driver_label_is_mixed_when_both_drivers_present():
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}, recorded_driver="human"),
        RecordedEvent(
            "fill",
            {"selector": 'input[name="q"]', "value": "x", "field_meta": {"tag": "input", "name": "q"}},
            recorded_driver="agent",
        ),
    ]
    result = compile_events_into_group(events, recording_id="rec_mixed")
    assert result["group_node"]["config_json"]["recorded_driver"] == "mixed"


def test_compile_into_group_screenshot_uses_last_fill_in_coalesce_streak():
    """Sequential fills on the same selector should expose ONE child with
    the screenshot of the final keystroke (matching the compiler's fill
    coalesce), not the first keystroke."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}, screenshot_b64="NAV"),
        RecordedEvent("fill", {
            "selector": 'input[name="q"]', "value": "h",
            "field_meta": {"tag": "input", "name": "q"},
        }, screenshot_b64="SHOT_H"),
        RecordedEvent("fill", {
            "selector": 'input[name="q"]', "value": "i",
            "field_meta": {"tag": "input", "name": "q"},
        }, screenshot_b64="SHOT_HI"),
    ]
    result = compile_events_into_group(events, recording_id="rec_coalesce")
    fill_child = next(c for c in result["child_nodes"] if c["config_json"]["tool_action"] == "fill")
    assert fill_child["config_json"].get("screenshot_b64") == "SHOT_HI"


# ---------------------------------------------------------------------------
# Regression: BUG-768 — compiler must never emit body as a fill selector
# ---------------------------------------------------------------------------


def test_bug768_fill_with_no_selector_marked_needs_selector_not_body():
    """When the relay couldnt resolve a focused selector and ships a
    fill event with selector=None, the compiler must flag _needs_selector
    rather than silently falling back to body (which the runtime then
    rejects as "Element not found or not fillable: body")."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("fill", {
            "selector": None,
            "value": "AD468811215BR",
            "field_meta": None,
        }),
    ]
    cfg = compile_events(events)
    fill_rows = [r for r in cfg["selectors"] if r["action"] == "fill"]
    assert len(fill_rows) == 1
    assert fill_rows[0].get("_needs_selector") is True
    assert fill_rows[0]["selector"] is None
    # And critically: no row anywhere ships a body selector
    for row in cfg["selectors"]:
        assert (row.get("selector") or "").strip() not in {"body", "html", "*", "document"}


def test_bug768_explicit_body_selector_is_scrubbed():
    """If a stale event somehow arrives with selector=body, the compiler
    must scrub it instead of trusting the broken value."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("fill", {
            "selector": "body",
            "value": "AD468811215BR",
            "field_meta": {"tag": "body"},
        }),
    ]
    cfg = compile_events(events)
    fill_rows = [r for r in cfg["selectors"] if r["action"] == "fill"]
    assert fill_rows[0]["selector"] is None
    assert fill_rows[0].get("_needs_selector") is True


def test_bug768_captcha_value_target_skips_unresolved_fill():
    """solve_captcha rows must not point value_target at a fill with no
    real selector — that was the exact runtime failure on Run #2934
    ("Element not found or not fillable: body")."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("marker.captcha", {
            "selector": "img#captcha_image",
            "meta": {"tag": "img", "id": "captcha_image"},
        }),
        # Bad fill — no selector resolution
        RecordedEvent("fill", {"selector": None, "value": "XXXXXX", "field_meta": None}),
        # Good fill later — captcha should point at THIS, not the broken one
        RecordedEvent("fill", {
            "selector": "input[name=\"captcha\"]",
            "value": "XXXXXX",
            "field_meta": {"tag": "input", "name": "captcha"},
        }),
    ]
    cfg = compile_events(events)
    captcha_rows = [r for r in cfg["selectors"] if r["action"] == "solve_captcha"]
    assert captcha_rows
    target = captcha_rows[0].get("value_target")
    assert target == "input[name=\"captcha\"]"


# ---------------------------------------------------------------------------
# Regression: BUG-771 — consecutive identical clicks must collapse
# ---------------------------------------------------------------------------


def test_bug771_two_consecutive_clicks_on_same_selector_collapse():
    """User re-clicked the same input because focus wasnt grabbed
    (BUG-767). The compiler should emit ONE click row, not two."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("click", {
            "selector": "input#objeto",
            "meta": {"tag": "input", "id": "objeto"},
        }),
        RecordedEvent("click", {
            "selector": "input#objeto",
            "meta": {"tag": "input", "id": "objeto"},
        }),
    ]
    cfg = compile_events(events)
    click_rows = [r for r in cfg["selectors"] if r["action"] == "click"]
    assert len(click_rows) == 1


def test_bug771_consecutive_clicks_on_different_selectors_preserved():
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("click", {
            "selector": "input#a",
            "meta": {"tag": "input", "id": "a"},
        }),
        RecordedEvent("click", {
            "selector": "input#b",
            "meta": {"tag": "input", "id": "b"},
        }),
    ]
    cfg = compile_events(events)
    click_rows = [r for r in cfg["selectors"] if r["action"] == "click"]
    assert len(click_rows) == 2


def test_bug773_combine_captcha_picks_submit_button_not_input_click():
    """Compiler must skip the focus-click into the captcha input and pick
    the actual submit button (button[name=b-pesquisar] / button#submit)."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("fill", {
            "selector": "input[name=\"objeto\"]",
            "value": "AD468811215BR",
            "field_meta": {"tag": "input", "name": "objeto"},
        }),
        RecordedEvent("marker.captcha", {
            "selector": "img#captcha_image",
            "meta": {"tag": "img", "id": "captcha_image"},
        }),
        RecordedEvent("click", {  # focus-click into captcha input (should be skipped)
            "selector": "input#captcha",
            "meta": {"tag": "input", "id": "captcha"},
        }),
        RecordedEvent("fill", {
            "selector": "input#captcha",
            "value": "XXXXXX",
            "field_meta": {"tag": "input", "id": "captcha"},
        }),
        RecordedEvent("click", {  # actual submit
            "selector": "button[name=\"b-pesquisar\"]",
            "meta": {"tag": "button", "name": "b-pesquisar"},
        }),
        RecordedEvent("marker.extract", {
            "selector": "#tabs-rastreamento .ship-steps",
            "as": "delivery_status",
        }),
    ]
    children = compile_events_into_nodes(events)
    captcha_node = next(c for c in children if (c["config_json"] or {}).get("tool_action") == "solve_captcha")
    assert captcha_node["config_json"]["tool_arguments"]["submit_selector"] == "button[name=\"b-pesquisar\"]"


def test_bug774_combine_captcha_skips_noise_extract_selector():
    """When the recorder captures extract on a noise region (carousel)
    because results don't render at record-time, success_selector must NOT
    pick that up — otherwise the runtime sees a 'success' that's actually
    pre-load carousel content."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("fill", {
            "selector": "input#objeto", "value": "AD468811215BR",
            "field_meta": {"tag": "input", "id": "objeto"},
        }),
        RecordedEvent("marker.captcha", {
            "selector": "img#captcha_image",
            "meta": {"tag": "img", "id": "captcha_image"},
        }),
        RecordedEvent("fill", {
            "selector": "input#captcha", "value": "XXXXXX",
            "field_meta": {"tag": "input", "id": "captcha"},
        }),
        RecordedEvent("click", {
            "selector": "button[name=\"b-pesquisar\"]",
            "meta": {"tag": "button", "name": "b-pesquisar"},
        }),
        RecordedEvent("marker.extract", {
            "selector": "div#carouselExampleControls > div > div:nth-of-type(1) > a > img",
            "as": "delivery_status",
        }),
    ]
    children = compile_events_into_nodes(events)
    captcha_node = next(c for c in children if (c["config_json"] or {}).get("tool_action") == "solve_captcha")
    assert "success_selector" not in captcha_node["config_json"]["tool_arguments"], \
        "noise extract selector must not become success_selector"


def test_bug774_combine_captcha_uses_content_region_extract_selector():
    """When the recorder captures extract on a content-region selector
    (.ship-steps, etc.) — that IS a valid success_selector."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("fill", {
            "selector": "input#objeto", "value": "AD468811215BR",
            "field_meta": {"tag": "input", "id": "objeto"},
        }),
        RecordedEvent("marker.captcha", {
            "selector": "img#captcha_image",
            "meta": {"tag": "img", "id": "captcha_image"},
        }),
        RecordedEvent("fill", {
            "selector": "input#captcha", "value": "XXXXXX",
            "field_meta": {"tag": "input", "id": "captcha"},
        }),
        RecordedEvent("click", {
            "selector": "button[name=\"b-pesquisar\"]",
            "meta": {"tag": "button", "name": "b-pesquisar"},
        }),
        RecordedEvent("marker.extract", {
            "selector": "#tabs-rastreamento .ship-steps",
            "as": "delivery_status",
        }),
    ]
    children = compile_events_into_nodes(events)
    captcha_node = next(c for c in children if (c["config_json"] or {}).get("tool_action") == "solve_captcha")
    assert captcha_node["config_json"]["tool_arguments"].get("success_selector") == "#tabs-rastreamento .ship-steps"


def test_bug776_auto_inserts_wait_for_between_captcha_and_extract():
    """If the recorder didn't capture a wait_for step, the compiler must
    auto-insert one between the combined solve_captcha (which submits) and
    the extract — extract races the page reload otherwise."""
    events = [
        RecordedEvent("navigate", {"url": "https://example.com/"}),
        RecordedEvent("fill", {
            "selector": "input#objeto", "value": "AD468811215BR",
            "field_meta": {"tag": "input", "id": "objeto"},
        }),
        RecordedEvent("marker.captcha", {
            "selector": "img#captcha_image",
            "meta": {"tag": "img", "id": "captcha_image"},
        }),
        RecordedEvent("fill", {
            "selector": "input#captcha", "value": "XXXXXX",
            "field_meta": {"tag": "input", "id": "captcha"},
        }),
        RecordedEvent("click", {
            "selector": "button[name=\"b-pesquisar\"]",
            "meta": {"tag": "button", "name": "b-pesquisar"},
        }),
        RecordedEvent("marker.extract", {
            "selector": "#tabs-rastreamento .ship-steps",
            "as": "delivery_status",
        }),
    ]
    children = compile_events_into_nodes(events)
    actions = [(c["config_json"] or {}).get("tool_action") for c in children]
    # Expected order: navigate, solve_captcha, wait_for, extract
    captcha_pos = actions.index("solve_captcha")
    wait_pos = actions.index("wait_for")
    extract_pos = actions.index("extract")
    assert captcha_pos < wait_pos < extract_pos, f"wait_for must be between captcha and extract — got actions {actions}"
    wait_node = children[wait_pos]
    wait_sel = (wait_node["config_json"]["selectors"][0] or {}).get("selector")
    assert wait_sel == "#tabs-rastreamento .ship-steps"
