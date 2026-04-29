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
        if message_type == "flow_run_triggered":
            # v0.7.0 Wave 3 — Triggers↔Flows Unification.
            return await self._dispatch_flow_run_triggered(worker, db, item)
        if message_type == "case_index":
            # v0.7.0 Trigger Case Memory MVP (default-off).
            return await self._dispatch_case_index(worker, db, item)
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

        # v0.7.x Wave 1-A — Trigger Memory Recap injection. The dispatcher
        # built a recap dict (or omitted it) and stored it under
        # ``payload.memory_recap``. When ``inject_position == "system_addendum"``
        # the recap is exposed to AgentService as a system override; otherwise
        # (default ``prepend_user_msg``) the recap is prepended to the first
        # user turn so the LLM cannot ignore it. Failure here MUST NOT abort
        # the run — recap is enrichment, not load-bearing.
        system_addendum: Optional[str] = None
        try:
            recap = payload.get("memory_recap") if isinstance(payload, dict) else None
            if isinstance(recap, dict):
                rendered_text = recap.get("rendered_text")
                if isinstance(rendered_text, str) and rendered_text.strip():
                    snapshot = recap.get("config_snapshot") or {}
                    inject_position = (
                        snapshot.get("inject_position")
                        if isinstance(snapshot, dict)
                        else None
                    ) or "prepend_user_msg"
                    if inject_position == "system_addendum":
                        system_addendum = rendered_text
                    else:
                        user_message = rendered_text + "\n\n---\n\n" + user_message
                    logger.info(
                        "continuous_task: injected memory_recap "
                        "(run_id=%s mode=%s chars=%d cases=%s)",
                        run.id,
                        inject_position,
                        len(rendered_text),
                        recap.get("cases_used"),
                    )
        except Exception:
            logger.exception(
                "continuous_task: failed to inject memory_recap (run_id=%s)",
                getattr(run, "id", None),
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
            invoke_kwargs: dict = {
                "db": db,
                "agent": agent,
                "continuous_agent": continuous_agent,
                "run": run,
                "sender_key": sender_key,
                "message_text": user_message,
            }
            # Only pass ``system_addendum`` when set so older test stubs
            # that monkey-patch ``_invoke_agent_for_continuous_run`` with a
            # narrower signature still work.
            if system_addendum:
                invoke_kwargs["system_addendum"] = system_addendum
            result = await _invoke_agent_for_continuous_run(**invoke_kwargs)
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
            # v0.7.0 Trigger Case Memory MVP — enqueue a `case_index` job
            # after the run reaches a terminal status. Default-off; the
            # try/except guards the original run from any case-memory
            # bookkeeping failure.
            try:
                from config.feature_flags import case_memory_enabled

                if case_memory_enabled() and run.status in ("succeeded", "failed"):
                    wake_event_ids_list = run.wake_event_ids or []
                    case_wake_event_id = wake_event_ids_list[0] if wake_event_ids_list else wake_event_id
                    if case_wake_event_id is not None:
                        from services.message_queue_service import MessageQueueService

                        MessageQueueService(db).enqueue(
                            channel="case_memory",
                            tenant_id=item.tenant_id,
                            agent_id=agent.id,
                            sender_key=f"case:continuous_run:{run.id}",
                            payload={
                                "origin_kind": "continuous_run",
                                "continuous_run_id": run.id,
                                "wake_event_id": case_wake_event_id,
                            },
                            message_type="case_index",
                        )
            except Exception:
                logger.exception(
                    "case_memory: failed to enqueue case_index for continuous_run %s",
                    getattr(run, "id", None),
                )
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

    async def _dispatch_flow_run_triggered(self, worker: Any, db: Any, item: Any) -> Any:
        """v0.7.0 Wave 3 — consume a ``flow_run_triggered`` queue row.

        Reads the binding + flow + trigger context from ``item.payload``
        and calls ``FlowEngine.run_flow`` with the new
        ``trigger_event_id`` and ``binding_id`` correlation params. The
        SourceStepHandler exposes ``{{source.payload.*}}`` etc. to
        downstream steps via the trigger_context root merge in
        ``_build_step_context``.

        Failures here are logged but do not bubble; the legacy
        ContinuousRun path is the source of truth and will already have
        been driven by ``_dispatch_continuous_task`` for tenant-owned
        subscriptions.
        """
        from flows.flow_engine import FlowEngine

        payload = item.payload or {}
        flow_definition_id: Optional[int] = payload.get("flow_definition_id")
        binding_id: Optional[int] = payload.get("binding_id")
        trigger_event_id: Optional[int] = payload.get("trigger_event_id")
        trigger_context = payload.get("trigger_context") or {}
        tenant_id: Optional[str] = payload.get("tenant_id") or item.tenant_id

        if flow_definition_id is None:
            logger.warning(
                "flow_run_triggered queue item %s missing 'flow_definition_id'; skipping",
                getattr(item, "id", None),
            )
            return {"status": "skipped", "reason": "missing_flow_definition_id"}

        try:
            flow_engine = FlowEngine(db)
            flow_run = await flow_engine.run_flow(
                flow_definition_id=flow_definition_id,
                trigger_context=trigger_context,
                initiator="trigger",
                trigger_type="triggered",
                tenant_id=tenant_id,
                trigger_event_id=trigger_event_id,
                binding_id=binding_id,
            )
            # v0.7.0 Trigger Case Memory MVP — enqueue a `case_index` job
            # for trigger-origin FlowRuns once they reach a terminal
            # state. Manual / scheduled flows have trigger_event_id=None
            # and are intentionally skipped per MVP scope (§3 of the
            # research doc).
            try:
                from config.feature_flags import case_memory_enabled

                if (
                    case_memory_enabled()
                    and getattr(flow_run, "trigger_event_id", None) is not None
                    and getattr(flow_run, "status", None)
                    in ("completed", "completed_with_errors", "failed")
                ):
                    from services.message_queue_service import MessageQueueService

                    MessageQueueService(db).enqueue(
                        channel="case_memory",
                        tenant_id=item.tenant_id,
                        agent_id=item.agent_id,
                        sender_key=f"case:flow_run:{flow_run.id}",
                        payload={
                            "origin_kind": "flow_run",
                            "flow_run_id": flow_run.id,
                            "wake_event_id": flow_run.trigger_event_id,
                        },
                        message_type="case_index",
                    )
            except Exception:
                logger.exception(
                    "case_memory: failed to enqueue case_index for flow_run %s",
                    getattr(flow_run, "id", None),
                )

            return {
                "status": flow_run.status,
                "flow_run_id": flow_run.id,
                "flow_definition_id": flow_definition_id,
                "binding_id": binding_id,
            }
        except Exception:
            logger.exception(
                "flow_run_triggered dispatch failed: flow=%s binding=%s wake_event=%s",
                flow_definition_id,
                binding_id,
                trigger_event_id,
            )
            return {
                "status": "failed",
                "flow_definition_id": flow_definition_id,
                "binding_id": binding_id,
                "reason": "flow_engine_error",
            }

    async def _dispatch_case_index(self, worker: Any, db: Any, item: Any) -> Any:
        """v0.7.0 Trigger Case Memory MVP — handle a ``case_index`` queue row.

        Reads ``origin_kind``, the matching run id, and the wake event
        id from ``item.payload`` and calls
        ``case_memory_service.index_case``. Outcomes:
          * Success → ``mqs.mark_completed`` with a small result blob.
          * ``EmbeddingDimensionMismatch`` → ``mqs.mark_failed`` with no
            retry (we set retry_count to max so it lands in dead_letter
            on the next claim).
          * Any other exception → ``mqs.mark_failed`` (normal retry +
            dead-letter).
        """
        from services.case_embedding_resolver import EmbeddingDimensionMismatch
        from services.case_memory_service import index_case
        from services.message_queue_service import MessageQueueService

        payload = item.payload or {}
        origin_kind = payload.get("origin_kind")
        run_id = payload.get("continuous_run_id") or payload.get("flow_run_id")
        wake_event_id = payload.get("wake_event_id")

        if origin_kind not in ("continuous_run", "flow_run") or run_id is None:
            MessageQueueService(db).mark_failed(
                item.id, error="case_index_payload_invalid"
            )
            return {"status": "failed", "reason": "case_index_payload_invalid"}

        try:
            case = index_case(
                db,
                tenant_id=item.tenant_id,
                agent_id=item.agent_id,
                origin_kind=origin_kind,
                run_id=int(run_id),
                wake_event_id=int(wake_event_id) if wake_event_id is not None else None,
            )
        except EmbeddingDimensionMismatch as exc:
            # No retry: bump retry_count to max_retries before marking failed
            # so the next claim moves the row to dead_letter.
            try:
                fresh = db.get(type(item), item.id)
                if fresh is not None:
                    fresh.retry_count = fresh.max_retries or 3
                    db.add(fresh)
                    db.commit()
            except Exception:
                logger.exception(
                    "case_memory: failed to bump retry_count after dim mismatch"
                )
            MessageQueueService(db).mark_failed(
                item.id, error=f"embedding_dimension_mismatch:{exc}"
            )
            return {"status": "failed", "reason": "embedding_dimension_mismatch"}
        except Exception as exc:  # noqa: BLE001 — last-resort error path
            logger.exception(
                "case_memory: case-index handler failed (queue_item=%s)",
                getattr(item, "id", None),
            )
            MessageQueueService(db).mark_failed(item.id, error=str(exc))
            return {"status": "failed", "reason": "indexer_error"}

        result = {
            "status": "completed",
            "case_id": getattr(case, "id", None) if case else None,
            "index_status": getattr(case, "index_status", None) if case else None,
        }
        MessageQueueService(db).mark_completed(item.id, result=result)
        return result


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
    system_addendum: Optional[str] = None,
) -> dict:
    """Invoke ``AgentService.process_message`` for a continuous run.

    Kept as a free function so tests can monkeypatch a stub without having to
    construct a full AgentService graph.

    ``system_addendum`` (v0.7.x Wave 1-A) — optional extra text appended to
    the agent's ``system_prompt`` for this single invocation. Used by the
    Trigger Memory Recap injector when ``inject_position == "system_addendum"``.
    Empty / None → no change to the system prompt.
    """
    from agent.agent_service import AgentService

    base_system_prompt = agent.system_prompt or ""
    if system_addendum:
        effective_system_prompt = (
            f"{base_system_prompt}\n\n---\n\n{system_addendum}"
            if base_system_prompt
            else system_addendum
        )
    else:
        effective_system_prompt = base_system_prompt

    config = {
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "system_prompt": effective_system_prompt,
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
