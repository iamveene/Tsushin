"""
v0.7.0 Phase 0 queue router.

Centralizes the new MessageQueue.message_type discriminator while preserving
the existing channel handlers in QueueWorker. Phase 0 intentionally keeps
trigger/continuous rows resolved to an agent before enqueueing.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class QueueRouter:
    """Dispatch queue items by message_type, then by existing channel handlers."""

    async def dispatch(self, worker: Any, db: Any, item: Any) -> Any:
        message_type = getattr(item, "message_type", None) or "inbound_message"
        if message_type == "inbound_message":
            return await self._dispatch_inbound_message(worker, db, item)
        if message_type == "trigger_event":
            return await self._dispatch_trigger_event(worker, db, item)
        if message_type == "continuous_task":
            return await self._dispatch_continuous_task(worker, db, item)
        raise ValueError(f"Unknown message_type: {message_type}")

    async def _dispatch_inbound_message(self, worker: Any, db: Any, item: Any) -> Any:
        channel = item.channel
        if channel == "playground":
            return await worker._process_playground_message(db, item)
        if channel == "whatsapp":
            await worker._process_whatsapp_message(db, item)
            return None
        if channel == "telegram":
            await worker._process_telegram_message(db, item)
            return None
        if channel == "webhook":
            return await worker._process_webhook_message(db, item)
        if channel == "api":
            return await worker._process_api_message(db, item)
        if channel == "slack":
            await worker._process_slack_message(db, item)
            return None
        if channel == "discord":
            await worker._process_discord_message(db, item)
            return None
        raise ValueError(f"Unknown channel: {channel}")

    async def _dispatch_trigger_event(self, worker: Any, db: Any, item: Any) -> Any:
        # Phase 0 has no Trigger base yet; webhook keeps its current path.
        if item.channel == "webhook":
            return await worker._process_webhook_message(db, item)
        raise NotImplementedError(
            f"trigger_event routing for channel '{item.channel}' lands after the Channel/Trigger split"
        )

    async def _dispatch_continuous_task(self, worker: Any, db: Any, item: Any) -> Any:
        """BUG-702: consume a ``continuous_task`` queue row.

        Loads the related ``continuous_run`` + ``wake_event`` + ``continuous_agent``
        + ``agent`` rows, applies ``ContinuousBudgetLimiter`` for the agent's
        ``BudgetPolicy`` (BUG-715 wiring), builds a prompt from the agent's
        ``system_prompt`` plus the wake-event payload (read from
        ``payload_ref`` if available), invokes ``AgentService.process_message``,
        and persists run state.

        System-owned managed flows (Email triage, Jira-to-WhatsApp) bypass this
        path via inline dispatch in their channel triggers. Producers must NOT
        enqueue ``continuous_task`` rows for system-owned subscriptions.
        """
        from models import (
            Agent,
            BudgetPolicy,
            ContinuousAgent,
            ContinuousRun,
            WakeEvent,
        )
        from services.continuous_agent_service import (
            BudgetDecision,
            BudgetKind,
            ContinuousBudgetLimiter,
        )

        payload = item.payload or {}
        run_id: Optional[int] = payload.get("continuous_run_id")
        wake_event_id: Optional[int] = payload.get("wake_event_id")

        if run_id is None:
            raise ValueError("continuous_task payload missing 'continuous_run_id'")

        run = (
            db.query(ContinuousRun)
            .filter(
                ContinuousRun.id == run_id,
                ContinuousRun.tenant_id == item.tenant_id,
            )
            .first()
        )
        if run is None:
            logger.warning(
                "continuous_task queue item %s references missing continuous_run %s; skipping",
                getattr(item, "id", None),
                run_id,
            )
            return {"status": "skipped", "reason": "continuous_run_not_found"}

        # Idempotency: if another worker already finished/started this run,
        # don't re-run. We only proceed when status is the initial queued state.
        if run.status not in ("queued",):
            logger.info(
                "continuous_run %s already in status %s; skipping queue item %s",
                run.id,
                run.status,
                getattr(item, "id", None),
            )
            return {"status": "skipped", "reason": f"run_status_{run.status}"}

        continuous_agent = (
            db.query(ContinuousAgent)
            .filter(
                ContinuousAgent.id == run.continuous_agent_id,
                ContinuousAgent.tenant_id == item.tenant_id,
            )
            .first()
        )
        if continuous_agent is None:
            self_fail_run(db, run, "continuous_agent_not_found")
            return {"status": "failed", "reason": "continuous_agent_not_found"}

        agent = (
            db.query(Agent)
            .filter(
                Agent.id == continuous_agent.agent_id,
                Agent.tenant_id == item.tenant_id,
            )
            .first()
        )
        if agent is None:
            self_fail_run(db, run, "agent_not_found")
            return {"status": "failed", "reason": "agent_not_found"}

        wake_event = None
        if wake_event_id is not None:
            wake_event = (
                db.query(WakeEvent)
                .filter(
                    WakeEvent.id == wake_event_id,
                    WakeEvent.tenant_id == item.tenant_id,
                )
                .first()
            )

        # BUG-715: Apply BudgetPolicy via ContinuousBudgetLimiter before running.
        budget_decision: Optional[BudgetDecision] = None
        if continuous_agent.budget_policy_id is not None:
            policy = (
                db.query(BudgetPolicy)
                .filter(
                    BudgetPolicy.id == continuous_agent.budget_policy_id,
                    BudgetPolicy.tenant_id == item.tenant_id,
                )
                .first()
            )
            if policy is not None and policy.is_active:
                limiter = _get_budget_limiter(worker)
                check = limiter.check(
                    tenant_id=item.tenant_id,
                    continuous_agent_id=continuous_agent.id,
                    policy=policy,
                    budget_kind=BudgetKind.RUN,
                    amount=1,
                )
                if not check.allowed:
                    budget_decision = check.decision
                    logger.warning(
                        "continuous_run %s blocked by BudgetPolicy %s (decision=%s)",
                        run.id,
                        policy.id,
                        budget_decision.value,
                    )
                    if budget_decision == BudgetDecision.PAUSE:
                        run.status = "paused_budget"
                    elif budget_decision == BudgetDecision.NOTIFY_ONLY:
                        run.status = "skipped"
                    else:
                        # DEGRADE_TO_HYBRID: still run but flag the mode change.
                        run.execution_mode = "hybrid"
                    run.outcome_state = {
                        "budget": {
                            "decision": budget_decision.value,
                            "policy_id": policy.id,
                            "limit": check.limit,
                            "remaining": check.remaining,
                        }
                    }
                    if budget_decision in (
                        BudgetDecision.PAUSE,
                        BudgetDecision.NOTIFY_ONLY,
                    ):
                        run.finished_at = datetime.utcnow()
                        if wake_event is not None:
                            wake_event.status = "filtered"
                            db.add(wake_event)
                        db.add(run)
                        db.commit()
                        return {
                            "status": "skipped",
                            "reason": "budget_exhausted",
                            "decision": budget_decision.value,
                            "budget_decision": budget_decision.value,
                            "continuous_run_id": run.id,
                        }

        # Mark running and persist before invoking the agent.
        run.status = "running"
        run.started_at = run.started_at or datetime.utcnow()
        if wake_event is not None:
            wake_event.status = "claimed"
            db.add(wake_event)
        db.add(run)
        db.commit()

        # Build the prompt from the agent's system prompt + wake-event payload.
        wake_payload = _read_wake_payload(wake_event)
        user_message = _build_continuous_user_message(
            wake_event=wake_event,
            payload=wake_payload,
            wake_payload_overrides=payload.get("wake_payload"),
            event_type=payload.get("event_type"),
            channel_type=payload.get("channel_type"),
            importance=payload.get("importance"),
        )

        # BUG #26: emit Watcher Graph View activity around the wake-driven
        # invocation. AgentService.process_message bypasses agent/router.py
        # (which is the only path that emits agent_processing for chat-driven
        # runs), so without these calls the agent node never glows when a
        # trigger fires.
        wake_channel_type = payload.get("channel_type") or "trigger"
        sender_key = item.sender_key or f"continuous:{continuous_agent.id}"
        try:
            from services.watcher_activity_service import (
                emit_agent_processing_async,
                emit_continuous_run_async,
            )

            emit_agent_processing_async(
                tenant_id=run.tenant_id,
                agent_id=agent.id,
                status="start",
                sender_key=sender_key,
                channel=wake_channel_type,
            )
        except Exception:
            pass

        try:
            result = await _invoke_agent_for_continuous_run(
                db=db,
                agent=agent,
                continuous_agent=continuous_agent,
                run=run,
                sender_key=sender_key,
                message_text=user_message,
            )
            answer = (result or {}).get("answer") or ""
            error_text = (result or {}).get("error")
            if error_text:
                run.status = "failed"
                outcome = run.outcome_state or {}
                outcome["error"] = str(error_text)
                run.outcome_state = outcome
            else:
                run.status = "succeeded"
                outcome = run.outcome_state or {}
                outcome["answer"] = answer
                if "tokens" in (result or {}):
                    outcome["tokens"] = result.get("tokens")
                run.outcome_state = outcome
                if wake_event is not None:
                    wake_event.status = "processed"
                    db.add(wake_event)
        except Exception as exc:  # noqa: BLE001 — last-resort error path
            logger.exception(
                "continuous_run %s failed during agent dispatch", run.id
            )
            run.status = "failed"
            outcome = run.outcome_state or {}
            outcome["error"] = f"{type(exc).__name__}: {exc}"
            run.outcome_state = outcome
            if wake_event is not None:
                wake_event.status = "failed"
                db.add(wake_event)
        finally:
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            try:
                emit_agent_processing_async(
                    tenant_id=run.tenant_id,
                    agent_id=agent.id,
                    status="end",
                    sender_key=sender_key,
                    channel=wake_channel_type,
                )
                emit_continuous_run_async(
                    tenant_id=run.tenant_id,
                    continuous_run_id=run.id,
                    continuous_agent_id=continuous_agent.id,
                    status=run.status,
                    wake_event_ids=run.wake_event_ids or [],
                    channel_type=wake_channel_type,
                )
            except Exception:
                pass

        return {
            "status": "completed" if run.status == "succeeded" else run.status,
            "continuous_run_id": run.id,
            "answer": (run.outcome_state or {}).get("answer"),
            "budget_decision": budget_decision.value if budget_decision else None,
        }


def self_fail_run(db: Any, run: Any, reason: str) -> None:
    """Mark the run failed with a structured outcome and finished_at."""
    run.status = "failed"
    outcome = run.outcome_state or {}
    outcome["error"] = reason
    run.outcome_state = outcome
    run.finished_at = datetime.utcnow()
    db.add(run)
    db.commit()


def _get_budget_limiter(worker: Any):
    """Reuse a worker-supplied limiter when present, otherwise the singleton.

    Tests can attach a deterministic limiter to the worker fixture; production
    falls through to the module singleton from continuous_agent_service.
    """
    from services.continuous_agent_service import budget_limiter

    candidate = getattr(worker, "budget_limiter", None)
    return candidate or budget_limiter


def _read_wake_payload(wake_event: Any) -> dict:
    """Read the wake-event payload file written by TriggerDispatchService.

    The payload is stored on disk by the dispatcher under
    ``backend/data/wake_events/<filename>.json``. We swallow IO errors and
    return an empty dict so the agent still gets a useful prompt rather than
    failing the run on a transient FS issue.
    """
    if wake_event is None:
        return {}
    payload_ref = getattr(wake_event, "payload_ref", None)
    if not payload_ref:
        return {}
    try:
        backend_root = Path(__file__).resolve().parents[1]
        candidate = Path(payload_ref)
        if not candidate.is_absolute():
            # payload_ref is stored relative to the repo root, e.g.
            # "backend/data/wake_events/<file>.json". On host, backend_root is
            # "<repo>/backend"; in the container, backend_root is "/app". In
            # both cases the file lives at "<backend_root>/data/wake_events/...",
            # so when payload_ref is repo-rooted ("backend/...") we strip the
            # "backend/" prefix and re-anchor on backend_root. When it's
            # already backend-rooted (e.g. "data/wake_events/..."), join
            # directly. Avoids the prior "<repo_root>/backend/data/..." path
            # which only works on the host (in the container it resolves to
            # "/backend/data/..." and the file isn't there).
            parts = candidate.parts
            if parts and parts[0] == "backend":
                candidate = backend_root.joinpath(*parts[1:])
            else:
                candidate = backend_root / candidate
        if not candidate.exists():
            return {}
        document = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            return document
    except Exception as exc:  # noqa: BLE001 — non-fatal
        logger.warning("Failed to read wake payload at %s: %s", payload_ref, exc)
    return {}


def _build_continuous_user_message(
    *,
    wake_event: Any,
    payload: dict,
    wake_payload_overrides: Any = None,
    event_type: Optional[str] = None,
    channel_type: Optional[str] = None,
    importance: Optional[str] = None,
) -> str:
    """Build the user-side prompt for a continuous run.

    Mirrors the inline pattern the system-owned managed flows use: a structured
    block describing the trigger + payload, asking the agent to take action.
    Any sensitive fields were already redacted by the dispatcher when the
    payload was written to disk.
    """
    resolved_event_type = (
        event_type
        or (getattr(wake_event, "event_type", None) if wake_event is not None else None)
        or payload.get("event_type")
        or "trigger"
    )
    resolved_channel_type = (
        channel_type
        or (getattr(wake_event, "channel_type", None) if wake_event is not None else None)
        or payload.get("trigger_type")
        or "trigger"
    )
    resolved_importance = (
        importance
        or (getattr(wake_event, "importance", None) if wake_event is not None else None)
        or payload.get("importance")
        or "normal"
    )

    body = wake_payload_overrides if wake_payload_overrides is not None else payload.get("payload", payload)
    try:
        rendered = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        rendered = repr(body)

    return (
        f"A {resolved_channel_type} {resolved_event_type} event fired "
        f"(importance={resolved_importance}). Take appropriate action based on the payload below.\n\n"
        f"Event payload:\n```json\n{rendered}\n```"
    )


async def _invoke_agent_for_continuous_run(
    *,
    db: Any,
    agent: Any,
    continuous_agent: Any,
    run: Any,
    sender_key: str,
    message_text: str,
) -> dict:
    """Invoke ``AgentService.process_message`` for a continuous run.

    Kept as a free function so tests can monkeypatch a stub without having to
    construct a full AgentService graph.
    """
    from agent.agent_service import AgentService

    config = {
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "system_prompt": agent.system_prompt,
        "memory_size": getattr(agent, "memory_size", None) or 1000,
        "context_message_count": getattr(agent, "context_message_count", None) or 10,
        "context_char_limit": getattr(agent, "context_char_limit", None) or 1000,
        "enable_semantic_search": getattr(agent, "enable_semantic_search", False),
        "semantic_search_results": getattr(agent, "semantic_search_results", 5),
        "semantic_similarity_threshold": getattr(agent, "semantic_similarity_threshold", 0.3),
        "run_type": "continuous",
        "continuous_agent_context": {
            "tenant_id": run.tenant_id,
            "agent_id": agent.id,
            "continuous_agent_id": continuous_agent.id,
            "continuous_run_id": run.id,
            "mode": continuous_agent.execution_mode,
            "sender_key": sender_key,
        },
    }

    service = AgentService(
        config,
        contact_service=None,
        db=db,
        agent_id=agent.id,
        token_tracker=None,
        tenant_id=agent.tenant_id,
        persona_id=getattr(agent, "persona_id", None),
    )
    return await service.process_message(
        sender_key=sender_key,
        message_text=message_text,
        original_query=message_text,
    )


queue_router = QueueRouter()
