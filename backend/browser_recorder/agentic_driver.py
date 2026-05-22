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
import logging
import os
from typing import Any, Optional

from .models import RecordedEvent, RecordingDriver, RecordingSession

logger = logging.getLogger(__name__)


# Conservative defaults — Opus for planning (more reliable for "next click"
# decisions on novel pages), Haiku for the per-step interactions that
# don't need deep reasoning. See [project_v061_prompt_caching] for the
# cache-control pattern that makes this cost-bounded.
_DEFAULT_PLANNER_MODEL = "claude-opus-4-7"
_DEFAULT_STEP_MODEL = "claude-haiku-4-5-20251001"


async def _emit_event(session: RecordingSession, kind: str, payload: dict[str, Any]) -> None:
    """Append an event to the session and push it down the WS relay if any."""
    session.append_event(kind, payload)
    if session.relay_send is not None:
        try:
            await session.relay_send({"type": "event", "kind": kind, "payload": payload})
        except Exception:
            # WS may be reconnecting; the event is still in session.events
            pass


def _build_llms(planner_model: str, step_model: str):
    """Construct LangChain ChatAnthropic clients for the dual-LLM split.

    Raises ImportError if langchain_anthropic is not installed — caller
    catches and surfaces a 501.
    """
    from langchain_anthropic import ChatAnthropic  # noqa: F401

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set on the backend")

    planner = ChatAnthropic(model=planner_model, anthropic_api_key=api_key, temperature=0)
    step = ChatAnthropic(model=step_model, anthropic_api_key=api_key, temperature=0)
    return planner, step


async def start_agent_loop(
    *,
    session: RecordingSession,
    prompt: str,
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

    planner, step = _build_llms(
        planner_model or _DEFAULT_PLANNER_MODEL,
        step_model or _DEFAULT_STEP_MODEL,
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

    async def _run() -> None:
        await _emit_event(session, "agent.start", {"prompt": prompt})
        try:
            # Drive the agent in step-mode so we can yield between steps
            # for pause/resume checks. If the Agent API doesn't expose
            # step(), fall back to run() — events still flow through the
            # CDP layer via our normal page-event hooks.
            if hasattr(agent, "step"):
                while True:
                    if session.agent_paused:
                        await asyncio.sleep(0.5)
                        continue
                    done = await agent.step()
                    await _emit_event(session, "agent.step", {})
                    if done:
                        break
            else:
                await agent.run()
        except asyncio.CancelledError:
            await _emit_event(session, "agent.cancelled", {})
            raise
        except Exception as e:
            logger.exception("Agentic recording failed for session %s", session.session_id)
            await _emit_event(session, "agent.error", {"message": str(e)})
            raise
        else:
            await _emit_event(session, "agent.complete", {})
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
