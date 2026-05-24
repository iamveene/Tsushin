"""Browser-Use agent driving the same Page object the human recorder uses.

The bet: the human and the agent both produce identical RecordedEvent
streams, so the same event_compiler reduces either into FlowNode
config_json. The user picks the cheapest tool for the job — recording
themselves for known sites, prompting an agent for unfamiliar ones.

All Browser-Use / LangChain imports happen lazily inside `start_agent_loop`
so the routes_recorder layer can detect missing dependencies via
ImportError and return 501 cleanly — humans driving the recorder don't
need browser-use installed for their flow to work.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from .models import RecordedEvent, RecordingDriver, RecordingSession

logger = logging.getLogger(__name__)


# Conservative defaults — Opus for planning (more reliable for "next click"
# decisions on novel pages), Haiku for the per-step interactions that
# don't need deep reasoning. Browser-Use's ChatAnthropic accepts any str
# model name; we pick from its Literal-validated set so the SDK doesn't
# warn. Operators can override via the request body.
_DEFAULT_PLANNER_MODEL = "claude-opus-4-5"
_DEFAULT_STEP_MODEL = "claude-haiku-4-5-20251001"


async def _emit_event(session: RecordingSession, kind: str, payload: dict[str, Any]) -> None:
    """Append an event to the session and push it down the WS relay if any."""
    evt = session.append_event(kind, payload)
    if session.relay_send is not None:
        try:
            await session.relay_send({
                "type": "event",
                "kind": evt.kind,
                "payload": evt.payload,
                "screenshot_b64": evt.screenshot_b64,
                "recorded_driver": evt.recorded_driver,
                "ts": evt.ts,
            })
        except Exception:
            # WS may be reconnecting; the event is still in session.events
            pass


def _resolve_anthropic_key(tenant_id: str, db) -> str:
    """Resolve the tenant's Anthropic API key the same way AIClient does.

    Tsushin stores provider credentials per-tenant in the ProviderInstance
    table (not as a global env var) so multi-tenancy isolation is
    preserved. We use the same lookup path the existing AIClient takes:
    default-keyed instance for vendor='anthropic' → resolve_api_key.
    """
    # Lazy import — the service module pulls in SQLAlchemy + the model
    # graph, which we don't need at module import time.
    from services.provider_instance_service import ProviderInstanceService

    instance = ProviderInstanceService.get_default_keyed_instance(
        vendor="anthropic", tenant_id=tenant_id, db=db,
    )
    if not instance:
        raise RuntimeError(
            "No active default Anthropic provider instance for this tenant. "
            "Configure one under Hub > Providers before starting an agentic recording.",
        )
    api_key = ProviderInstanceService.resolve_api_key(instance, db)
    if not api_key:
        raise RuntimeError(
            "Anthropic provider instance found but its API key could not be resolved.",
        )
    return api_key


def _build_llms(planner_model: str, step_model: str, anthropic_api_key: str):
    """Construct Browser-Use's native ChatAnthropic clients for the dual-LLM split.

    Browser-Use 0.12+ ships its own ChatAnthropic (under browser_use.llm.anthropic)
    that exposes the `.provider` attribute the Agent loop expects. The
    earlier attempt to feed it a langchain_anthropic.ChatAnthropic instance
    failed with AttributeError on `.provider` — these two `ChatAnthropic`
    classes have the same name but are NOT interchangeable.
    """
    from browser_use import ChatAnthropic  # noqa: F401

    planner = ChatAnthropic(model=planner_model, api_key=anthropic_api_key, temperature=0)
    step = ChatAnthropic(model=step_model, api_key=anthropic_api_key, temperature=0)
    return planner, step


async def start_agent_loop(
    *,
    session: RecordingSession,
    prompt: str,
    tenant_id: str,
    db,
    planner_model: Optional[str] = None,
    step_model: Optional[str] = None,
) -> None:
    """Kick off a Browser-Use Agent driving the session's existing Page.

    Side-effects:
      - session.current_driver = RecordingDriver.AGENT
      - session.agent_task = asyncio.Task wrapping the agent loop
      - As the agent acts, events stream into session.events via _emit_event;
        the compiler (Phase 2) is driver-agnostic, so the produced
        config_json is identical to what a human recording would yield.

    Pausing: callers flip session.agent_paused; this coroutine yields on
    each step and waits while it's True. Resuming clears the flag.

    Raises ImportError if browser-use isn't installed — surfaced as 501
    by the route handler.
    """
    # Lazy imports keep human-driven recording working when browser-use
    # is uninstalled. Both imports are required for the dual-LLM Agent;
    # we surface either ImportError up the stack.
    from browser_use import Agent  # noqa: F401

    anthropic_api_key = _resolve_anthropic_key(tenant_id, db)
    planner, step = _build_llms(
        planner_model or _DEFAULT_PLANNER_MODEL,
        step_model or _DEFAULT_STEP_MODEL,
        anthropic_api_key=anthropic_api_key,
    )

    # Browser-Use accepts an existing Playwright Page through its
    # `page` kwarg on recent versions. If your installed version uses a
    # different name, the import-error path catches that for the user.
    agent = Agent(
        task=prompt,
        llm=planner,
        page_extraction_llm=step,
        page=session.page,
    )

    # Stash the agent on the session so pause/resume from the route
    # handler can call into Browser-Use's native pause/resume APIs.
    session.agent_handle = agent

    def _translate_action(action_dict: dict, interacted_element) -> list[tuple[str, dict]]:
        """Map a Browser-Use action dict into RecordedEvent (kind, payload) tuples.

        Browser-Use actions are tagged unions like ``{"go_to_url": {"url": ...}}``,
        ``{"click_element_by_index": {"index": 3}}``, ``{"input_text":
        {"index": 3, "text": "AD..."}}``. We translate the subset that
        maps cleanly to the recorder's event vocabulary so the compiler
        produces a real FlowNode from an agentic recording.

        Returns a list because some actions emit more than one event
        (e.g., input_text emits both a click on the field and a fill).
        """
        out: list[tuple[str, dict]] = []
        if not action_dict:
            return out

        # interacted_element comes from agent.history[-1].state.interacted_element[idx]
        # — a DOMHistoryElement-ish object with attributes like xpath, attributes
        elem_attrs = {}
        elem_xpath = None
        if interacted_element is not None:
            try:
                elem_attrs = dict(getattr(interacted_element, "attributes", None) or {})
                elem_xpath = getattr(interacted_element, "xpath", None)
            except Exception:
                pass

        def _selector_for(meta: dict, xpath: Optional[str] = None) -> Optional[str]:
            # Mirror selector_strategy.pick_selector preferences inline so we
            # don't need to wrangle the meta-blob shape conversion.
            for k in ("data-testid", "data-qa", "data-cy", "data-track"):
                if meta.get(k):
                    return f'[{k}="{meta[k]}"]'
            if meta.get("name"):
                tag = (meta.get("tag") or "*").lower()
                return f'{tag}[name="{meta["name"]}"]'
            if meta.get("aria-label"):
                tag = (meta.get("tag") or "*").lower()
                return f'{tag}[aria-label="{meta["aria-label"]}"]'
            if meta.get("id"):
                tag = (meta.get("tag") or "*").lower()
                return f'{tag}[id="{meta["id"]}"]'
            # Fall back to xpath conversion (very rough)
            return xpath

        # Browser-Use action name → (recorder event kind, payload extractor)
        for act_name, args in action_dict.items():
            if act_name == "go_to_url":
                url = (args or {}).get("url")
                if url:
                    out.append(("navigate", {"url": url}))
            elif act_name == "click_element_by_index":
                meta = {"tag": elem_attrs.get("tag", "*"), **elem_attrs}
                sel = _selector_for(meta, elem_xpath)
                out.append(("click", {"selector": sel, "meta": meta}))
            elif act_name == "input_text":
                meta = {"tag": elem_attrs.get("tag", "input"), **elem_attrs}
                sel = _selector_for(meta, elem_xpath)
                text = (args or {}).get("text", "")
                out.append(("fill", {"selector": sel, "value": text, "field_meta": meta}))
            elif act_name == "extract_content":
                meta = {"tag": elem_attrs.get("tag", "*"), **elem_attrs}
                sel = _selector_for(meta, elem_xpath) or "body"
                goal = (args or {}).get("goal") or (args or {}).get("query") or "captured_value"
                out.append(("marker.extract", {"selector": sel, "meta": meta, "as": goal}))
            elif act_name in ("scroll_down", "scroll_up"):
                # Scroll isn't in our action vocabulary; record as a metadata
                # event so the user can see it in the StepLedger but it gets
                # dropped at compile time.
                out.append((f"agent.scroll", {"direction": act_name.split("_")[1]}))
            # done / search_google / switch_tab / open_tab / close_tab not
            # mapped — they're either terminal or out of scope for v1.1.
        return out

    async def _on_step_end(agent_obj) -> None:
        """Browser-Use callback after every step. Translates the agent's
        actions into RecordedEvents so the compiler produces a real
        FlowNode from an agentic recording — same shape a human would
        record."""
        last_action_repr = None
        translated_count = 0
        translation_error = None
        try:
            history = getattr(agent_obj, "history", None)
            steps = getattr(history, "history", None) if history else None
            if steps:
                last_step = steps[-1]
                model_output = getattr(last_step, "model_output", None)
                actions = getattr(model_output, "action", None) or []
                state = getattr(last_step, "state", None)
                interacted_list = getattr(state, "interacted_element", None) or []
                for idx, action_obj in enumerate(actions):
                    try:
                        action_dict = (
                            action_obj.model_dump(exclude_none=True)
                            if hasattr(action_obj, "model_dump")
                            else (dict(action_obj) if action_obj else {})
                        )
                    except Exception as inner:
                        translation_error = f"action[{idx}].model_dump: {inner!s}"
                        action_dict = {}
                    elem = interacted_list[idx] if idx < len(interacted_list) else None
                    for kind, payload in _translate_action(action_dict, elem):
                        await _emit_event(session, kind, payload)
                        translated_count += 1
                if actions:
                    try:
                        raw = actions[0].model_dump(exclude_none=True) if hasattr(actions[0], "model_dump") else {}
                        last_action_repr = json.dumps(raw)[:300]
                    except Exception as inner:
                        translation_error = f"action[0].repr: {inner!s}"
        except Exception as e:
            translation_error = f"on_step_end: {type(e).__name__}: {e!s}"
            logger.debug("agentic step translation failed", exc_info=True)
        payload: dict[str, Any] = {"action": last_action_repr, "translated": translated_count}
        if translation_error:
            payload["error"] = translation_error
        await _emit_event(session, "agent.step", payload)

    async def _on_step_start(agent_obj) -> None:
        # Honour pause requests cooperatively — Browser-Use's native
        # pause() pauses the run loop until resume() is called, so this
        # is mostly a no-op safety net for the flag-driven path.
        if session.agent_paused:
            try:
                agent_obj.pause()
            except Exception:
                pass

    async def _emit_full_history(agent_obj) -> int:
        """After the agent finishes, walk its full action history and
        emit translated RecordedEvents. Browser-Use's history.history
        isn't necessarily populated at on_step_end time (callback fires
        before append) — reading post-run is the robust path.
        """
        translated = 0
        try:
            history = getattr(agent_obj, "history", None)
            steps = getattr(history, "history", None) if history else None
            if not steps:
                return 0
            for step in steps:
                model_output = getattr(step, "model_output", None)
                actions = getattr(model_output, "action", None) or []
                state = getattr(step, "state", None)
                interacted_list = getattr(state, "interacted_element", None) or []
                for idx, action_obj in enumerate(actions):
                    try:
                        action_dict = (
                            action_obj.model_dump(exclude_none=True)
                            if hasattr(action_obj, "model_dump")
                            else (dict(action_obj) if action_obj else {})
                        )
                    except Exception:
                        action_dict = {}
                    elem = interacted_list[idx] if idx < len(interacted_list) else None
                    for kind, payload in _translate_action(action_dict, elem):
                        await _emit_event(session, kind, payload)
                        translated += 1
        except Exception:
            logger.debug("agentic post-run history emit failed", exc_info=True)
        return translated

    async def _run() -> None:
        await _emit_event(session, "agent.start", {"prompt": prompt})
        try:
            await agent.run(
                max_steps=50,  # bounded — recordings shouldn't sprawl forever
                on_step_start=_on_step_start,
                on_step_end=_on_step_end,
            )
        except asyncio.CancelledError:
            await _emit_event(session, "agent.cancelled", {})
            raise
        except Exception as e:
            logger.exception("Agentic recording failed for session %s", session.session_id)
            await _emit_event(session, "agent.error", {"message": str(e)[:500]})
            raise
        else:
            # Post-run translation pass — reliable place to convert
            # Browser-Use's action history into the recorder's event
            # vocabulary so the compiler emits a real FlowNode.
            translated = await _emit_full_history(agent)
            await _emit_event(session, "agent.complete", {"translated_actions": translated})
        finally:
            session.current_driver = None

    session.current_driver = RecordingDriver.AGENT
    session.agent_paused = False
    # Replace any prior agent task (defence — caller already gated on this)
    if session.agent_task and not session.agent_task.done():
        session.agent_task.cancel()
        try:
            await session.agent_task
        except (asyncio.CancelledError, Exception):
            pass
    session.agent_task = asyncio.create_task(_run(), name=f"recorder-agent-{session.session_id}")
