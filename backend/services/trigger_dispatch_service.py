"""Provider-agnostic trigger dispatch for continuous-agent wakeups.

The dispatcher resolves tenant ownership from persisted trigger instance rows
and writes the v0.7.0 continuous-agent audit/queue primitives directly:
ChannelEventDedupe, WakeEvent, and ContinuousRun.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from channels.trigger_criteria import evaluate_payload_criteria
from models import (
    Agent,
    ChannelEventDedupe,
    ContinuousAgent,
    ContinuousRun,
    ContinuousSubscription,
    EmailChannelInstance,
    GitHubChannelInstance,
    JiraChannelInstance,
    ScheduleChannelInstance,
    SentinelConfig,
    WakeEvent,
    WebhookIntegration,
)
from services.default_agent_service import get_default_agent


Importance = Literal["low", "normal", "high"]


class TriggerDispatchStatus(str, Enum):
    """Stable result status names consumed by adapters/tests."""

    DISPATCHED = "dispatched"
    DUPLICATE = "duplicate"
    FILTERED = "filtered"
    BLOCKED_BY_SECURITY = "blocked_by_security"
    INSTANCE_NOT_FOUND = "instance_not_found"
    INACTIVE_INSTANCE = "inactive_instance"
    MISSING_DEFAULT_AGENT = "missing_default_agent"
    CROSS_TENANT_MISMATCH = "cross_tenant_mismatch"
    UNSUPPORTED_TRIGGER_TYPE = "unsupported_trigger_type"


@dataclass(frozen=True)
class TriggerDispatchInput:
    """Normalized trigger event ready for continuous-agent dispatch."""

    trigger_type: str
    instance_id: int
    event_type: str
    dedupe_key: str
    payload: dict[str, Any]
    occurred_at: datetime = field(default_factory=datetime.utcnow)
    importance: Importance = "normal"
    explicit_agent_id: Optional[int] = None
    sender_key: Optional[str] = None
    source_id: Optional[str] = None


@dataclass(frozen=True)
class TriggerDispatchResult:
    """Outcome from a single trigger dispatch attempt."""

    status: str
    reason: Optional[str] = None
    tenant_id: Optional[str] = None
    matched_agent_id: Optional[int] = None
    dedupe_id: Optional[int] = None
    wake_event_id: Optional[int] = None
    continuous_run_ids: list[int] = field(default_factory=list)
    continuous_subscription_ids: list[int] = field(default_factory=list)
    payload_ref: Optional[str] = None


class TriggerDispatchService:
    """Dispatch webhook/email trigger events into continuous-agent work."""

    _INSTANCE_MODELS = {
        "webhook": WebhookIntegration,
        "email": EmailChannelInstance,
        "jira": JiraChannelInstance,
        "schedule": ScheduleChannelInstance,
        "github": GitHubChannelInstance,
    }
    _ACTIVE_STATUS = "active"
    _WAKE_PENDING = "pending"
    _RUN_QUEUED = "queued"
    _OUTCOME_DISPATCHED = "wake_emitted"
    _OUTCOME_FILTERED_OUT = "filtered_out"

    _SENSITIVE_KEY_PARTS = (
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "password",
        "secret",
        "signature",
        "token",
    )

    def __init__(self, db: Session, *, payload_dir: Optional[Path] = None) -> None:
        self.db = db
        backend_root = Path(__file__).resolve().parents[1]
        self._payload_dir = Path(payload_dir) if payload_dir else backend_root / "data" / "wake_events"

    def dispatch(self, event: TriggerDispatchInput) -> TriggerDispatchResult:
        trigger_type = event.trigger_type.strip().lower()
        if trigger_type not in self._INSTANCE_MODELS:
            return TriggerDispatchResult(
                status=TriggerDispatchStatus.UNSUPPORTED_TRIGGER_TYPE.value,
                reason="unsupported_trigger_type",
            )

        instance = self._load_instance(trigger_type, event.instance_id)
        if instance is None:
            return TriggerDispatchResult(
                status=TriggerDispatchStatus.INSTANCE_NOT_FOUND.value,
                reason="instance_not_found",
            )

        tenant_id = instance.tenant_id
        if not self._is_instance_active(instance):
            return self._record_terminal_outcome(
                event=event,
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                status=TriggerDispatchStatus.INACTIVE_INSTANCE,
                outcome=TriggerDispatchStatus.INACTIVE_INSTANCE.value,
                reason="inactive_instance",
            )

        criteria_reason = self._criteria_filter_reason(instance, event)
        if criteria_reason:
            return self._record_terminal_outcome(
                event=event,
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                status=TriggerDispatchStatus.FILTERED,
                outcome=self._OUTCOME_FILTERED_OUT,
                reason=criteria_reason,
            )

        block_reason = self._security_block_reason(event, tenant_id=tenant_id)
        if block_reason:
            return self._record_terminal_outcome(
                event=event,
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                status=TriggerDispatchStatus.BLOCKED_BY_SECURITY,
                outcome=TriggerDispatchStatus.BLOCKED_BY_SECURITY.value,
                reason=block_reason,
            )

        agent_result = self._resolve_agent_id(
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            instance_id=event.instance_id,
            explicit_agent_id=event.explicit_agent_id,
        )
        if isinstance(agent_result, TriggerDispatchResult):
            return self._record_terminal_outcome(
                event=event,
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                status=TriggerDispatchStatus(agent_result.status),
                outcome=agent_result.status,
                reason=agent_result.reason,
            )
        agent_id = agent_result

        subscriptions = self._matching_subscriptions(
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            instance_id=event.instance_id,
            event_type=event.event_type,
            agent_id=agent_id,
        )
        if not subscriptions:
            return self._record_terminal_outcome(
                event=event,
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                status=TriggerDispatchStatus.FILTERED,
                outcome=TriggerDispatchStatus.FILTERED.value,
                reason="no_matching_subscription",
                matched_agent_id=agent_id,
            )

        dedupe = self._claim_dedupe(
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            instance_id=event.instance_id,
            dedupe_key=event.dedupe_key,
            outcome=self._OUTCOME_DISPATCHED,
        )
        if dedupe is None:
            return TriggerDispatchResult(
                status=TriggerDispatchStatus.DUPLICATE.value,
                reason="duplicate_event",
                tenant_id=tenant_id,
                matched_agent_id=agent_id,
            )

        payload_ref = self._write_payload_ref(event, tenant_id=tenant_id, trigger_type=trigger_type)
        wake_event = WakeEvent(
            tenant_id=tenant_id,
            channel_type=trigger_type,
            channel_instance_id=event.instance_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            dedupe_key=event.dedupe_key,
            importance=self._normalize_importance(event.importance),
            payload_ref=payload_ref,
            status=self._WAKE_PENDING,
        )
        if len(subscriptions) == 1:
            wake_event.continuous_agent_id = subscriptions[0].continuous_agent_id
            wake_event.continuous_subscription_id = subscriptions[0].id

        self.db.add(wake_event)
        self.db.flush()

        run_ids: list[int] = []
        runs_to_enqueue: list[tuple[ContinuousRun, ContinuousSubscription, ContinuousAgent]] = []
        for subscription in subscriptions:
            continuous_agent = subscription.continuous_agent
            run = ContinuousRun(
                tenant_id=tenant_id,
                continuous_agent_id=subscription.continuous_agent_id,
                wake_event_ids=[wake_event.id],
                execution_mode=continuous_agent.execution_mode,
                status=self._RUN_QUEUED,
                run_type="continuous",
            )
            self.db.add(run)
            self.db.flush()
            run_ids.append(run.id)
            runs_to_enqueue.append((run, subscription, continuous_agent))

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return TriggerDispatchResult(
                status=TriggerDispatchStatus.DUPLICATE.value,
                reason="duplicate_event",
                tenant_id=tenant_id,
                matched_agent_id=agent_id,
            )

        # BUG-702: Enqueue a ``continuous_task`` MessageQueue row for each
        # tenant-owned subscription so QueueRouter._dispatch_continuous_task
        # can drive the run. System-owned subscriptions (Email triage,
        # Jira-to-WhatsApp, etc.) are dispatched inline by their channel
        # adapter and must NOT be re-enqueued here.
        self._enqueue_continuous_tasks(
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            wake_event=wake_event,
            event=event,
            payload_ref=payload_ref,
            runs=runs_to_enqueue,
        )

        return TriggerDispatchResult(
            status=TriggerDispatchStatus.DISPATCHED.value,
            tenant_id=tenant_id,
            matched_agent_id=agent_id,
            dedupe_id=dedupe.id,
            wake_event_id=wake_event.id,
            continuous_run_ids=run_ids,
            continuous_subscription_ids=[subscription.id for subscription in subscriptions],
            payload_ref=payload_ref,
        )

    def _enqueue_continuous_tasks(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        wake_event: WakeEvent,
        event: TriggerDispatchInput,
        payload_ref: Optional[str],
        runs: list[tuple[ContinuousRun, ContinuousSubscription, ContinuousAgent]],
    ) -> None:
        """BUG-702: enqueue ``continuous_task`` MessageQueue rows for runs.

        System-owned subscriptions are skipped — they are dispatched inline
        by the channel adapter (e.g. ``_process_managed_actions``).
        """
        if not runs:
            return
        try:
            from services.message_queue_service import MessageQueueService

            mqs = MessageQueueService(self.db)
            sender_key = event.sender_key or f"{trigger_type}:{event.instance_id}"
            for run, subscription, continuous_agent in runs:
                if getattr(subscription, "is_system_owned", False):
                    continue
                payload = {
                    "continuous_run_id": run.id,
                    "wake_event_id": wake_event.id,
                    "continuous_agent_id": continuous_agent.id,
                    "continuous_subscription_id": subscription.id,
                    "channel_type": trigger_type,
                    "channel_instance_id": event.instance_id,
                    "event_type": event.event_type,
                    "importance": self._normalize_importance(event.importance),
                    "payload_ref": payload_ref,
                }
                mqs.enqueue(
                    channel="continuous",
                    tenant_id=tenant_id,
                    agent_id=continuous_agent.agent_id,
                    sender_key=sender_key,
                    payload=payload,
                    message_type="continuous_task",
                )
        except Exception:  # pragma: no cover — never abort dispatch on enqueue errors
            # The run row is already persisted; a separate sweep can re-drive
            # the queue if enqueue fails (rare). We deliberately don't raise.
            self.db.rollback()

    def _load_instance(self, trigger_type: str, instance_id: int) -> Any | None:
        model = self._INSTANCE_MODELS[trigger_type]
        return self.db.query(model).filter(model.id == instance_id).first()

    def _is_instance_active(self, instance: Any) -> bool:
        if getattr(instance, "is_active", True) is False:
            return False
        return (getattr(instance, "status", None) or self._ACTIVE_STATUS) == self._ACTIVE_STATUS

    def _security_block_reason(self, event: TriggerDispatchInput, *, tenant_id: Optional[str] = None) -> Optional[str]:
        """Return a security block reason for trigger payloads.

        This is deliberately synchronous because trigger dispatch currently runs
        inside sync request/worker paths. It uses Sentinel's deterministic
        heuristic floor as the MemGuard pre-check and leaves slower LLM
        escalation to the existing Sentinel paths.
        """
        if not tenant_id:
            return None
        try:
            from agent.sentinel.heuristics import evaluate_content

            config = (
                self.db.query(SentinelConfig)
                .filter(SentinelConfig.tenant_id == tenant_id)
                .first()
            )
            if config is None:
                config = (
                    self.db.query(SentinelConfig)
                    .filter(SentinelConfig.tenant_id.is_(None))
                    .first()
                )
            if config is None:
                return None
            if not getattr(config, "is_enabled", True):
                return None
            if (getattr(config, "detection_mode", "block") or "block") != "block":
                return None
            if getattr(config, "block_on_detection", True) is False:
                return None

            enabled_types = set()
            detection_flags = {
                "prompt_injection": "detect_prompt_injection",
                "memory_poisoning": "detect_memory_poisoning",
                "poisoning": "detect_poisoning",
                "agent_takeover": "detect_agent_takeover",
                "continuous_agent_action_approval": "detect_continuous_agent_action_approval",
            }
            for detection_type, flag_name in detection_flags.items():
                if getattr(config, flag_name, True):
                    enabled_types.add(detection_type)
            if not enabled_types:
                return None

            payload_text = json.dumps(
                self._redact(event.payload),
                default=self._json_default,
                ensure_ascii=False,
                sort_keys=True,
            )
            max_chars = max(256, int(getattr(config, "max_input_chars", 5000) or 5000))
            match = evaluate_content(
                payload_text[:max_chars],
                int(getattr(config, "aggressiveness_level", 1) or 1),
                enabled_types,
            )
            if match is None:
                return None
            return f"{match.detection_type}:{match.reason}"
        except Exception:
            # The pre-check must never take down trigger ingestion if Sentinel's
            # optional profile/config tables are unavailable in focused tests.
            return None

    def _criteria_filter_reason(self, instance: Any, event: TriggerDispatchInput) -> Optional[str]:
        criteria = getattr(instance, "trigger_criteria", None)
        if not criteria:
            return None

        # GitHub PR-submitted envelope (criteria_version 1): the dedicated
        # evaluator runs BEFORE the legacy top-level filters fire. If the
        # envelope sets ``event`` to something other than ``pull_request``,
        # log + fall back to the shared payload-criteria evaluator (which
        # honors ``filters.jsonpath_matchers``); the GitHub trigger today only
        # ships the PR-submitted envelope, but this keeps newer envelopes
        # forward-compatible without a dispatcher rev.
        trigger_type = (event.trigger_type or "").strip().lower()
        if trigger_type == "github" and isinstance(criteria, dict):
            envelope_event = str(criteria.get("event") or "").strip().lower()
            if envelope_event == "pull_request":
                return self._github_pr_criteria_reason(event.payload, criteria)
            if envelope_event and envelope_event != "pull_request":
                # Reserved for future envelope shapes; fall through to the
                # shared evaluator (or no-op if the envelope is unstructured).
                import logging

                logging.getLogger(__name__).warning(
                    "GitHub trigger criteria event=%r not yet implemented; falling back to legacy filters",
                    envelope_event,
                )
                return None

        try:
            matched, reason = evaluate_payload_criteria(event.payload, criteria)
        except ValueError as exc:
            return f"invalid_trigger_criteria:{exc}"
        if matched:
            return None
        return f"criteria_no_match:{reason or 'payload'}"

    def _github_pr_criteria_reason(
        self,
        payload: dict[str, Any],
        criteria: dict[str, Any],
    ) -> Optional[str]:
        """Return ``criteria_no_match:<reason>`` if the GitHub PR envelope rejects.

        ``payload`` here is the dispatch envelope built by
        ``channels.github.trigger.build_dispatch_payload`` — the original
        GitHub webhook body lives under ``raw_event``. Pass that to the
        evaluator (which expects ``action`` + ``pull_request`` at the top
        level). Falls back to the wrapper itself if ``raw_event`` is absent
        (defensive for callers that hand us the raw webhook directly, e.g.
        ``test-criteria`` endpoint).
        """
        try:
            from channels.github.criteria import evaluate_pr_criteria
        except ImportError:  # pragma: no cover — channels package is part of the app
            return None
        unwrapped = payload.get("raw_event") if isinstance(payload, dict) else None
        evaluation_target = unwrapped if isinstance(unwrapped, dict) else payload
        try:
            matched, reason = evaluate_pr_criteria(evaluation_target, criteria)
        except ValueError as exc:
            return f"invalid_trigger_criteria:{exc}"
        if matched:
            return None
        return f"criteria_no_match:{reason}"

    def _resolve_agent_id(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        instance_id: int,
        explicit_agent_id: Optional[int],
    ) -> int | TriggerDispatchResult:
        if explicit_agent_id is not None:
            agent = self.db.query(Agent).filter(Agent.id == explicit_agent_id).first()
            if agent is None or agent.tenant_id != tenant_id:
                return TriggerDispatchResult(
                    status=TriggerDispatchStatus.CROSS_TENANT_MISMATCH.value,
                    reason="explicit_agent_not_in_instance_tenant",
                )
            if not agent.is_active:
                return TriggerDispatchResult(
                    status=TriggerDispatchStatus.MISSING_DEFAULT_AGENT.value,
                    reason="explicit_agent_inactive",
                )
            return explicit_agent_id

        agent_id = get_default_agent(
            self.db,
            tenant_id,
            trigger_type,
            instance_id=instance_id,
        )
        if agent_id is None:
            return TriggerDispatchResult(
                status=TriggerDispatchStatus.MISSING_DEFAULT_AGENT.value,
                reason="missing_default_agent",
            )
        return agent_id

    def _matching_subscriptions(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        instance_id: int,
        event_type: str,
        agent_id: int,
    ) -> list[ContinuousSubscription]:
        return (
            self.db.query(ContinuousSubscription)
            .join(ContinuousAgent, ContinuousSubscription.continuous_agent_id == ContinuousAgent.id)
            .filter(
                ContinuousSubscription.tenant_id == tenant_id,
                ContinuousSubscription.channel_type == trigger_type,
                ContinuousSubscription.channel_instance_id == instance_id,
                ContinuousSubscription.status == "active",
                or_(ContinuousSubscription.event_type.is_(None), ContinuousSubscription.event_type == event_type),
                ContinuousAgent.tenant_id == tenant_id,
                ContinuousAgent.agent_id == agent_id,
                ContinuousAgent.status == "active",
            )
            .order_by(ContinuousSubscription.id.asc())
            .all()
        )

    def _record_terminal_outcome(
        self,
        *,
        event: TriggerDispatchInput,
        tenant_id: str,
        trigger_type: str,
        status: TriggerDispatchStatus,
        outcome: str,
        reason: Optional[str],
        matched_agent_id: Optional[int] = None,
    ) -> TriggerDispatchResult:
        dedupe = self._claim_dedupe(
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            instance_id=event.instance_id,
            dedupe_key=event.dedupe_key,
            outcome=outcome,
        )
        if dedupe is None:
            return TriggerDispatchResult(
                status=TriggerDispatchStatus.DUPLICATE.value,
                reason="duplicate_event",
                tenant_id=tenant_id,
                matched_agent_id=matched_agent_id,
            )
        self.db.commit()
        return TriggerDispatchResult(
            status=status.value,
            reason=reason,
            tenant_id=tenant_id,
            matched_agent_id=matched_agent_id,
            dedupe_id=dedupe.id,
        )

    def _claim_dedupe(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        instance_id: int,
        dedupe_key: str,
        outcome: str,
    ) -> Optional[ChannelEventDedupe]:
        existing = (
            self.db.query(ChannelEventDedupe.id)
            .filter(
                ChannelEventDedupe.tenant_id == tenant_id,
                ChannelEventDedupe.channel_type == trigger_type,
                ChannelEventDedupe.instance_id == instance_id,
                ChannelEventDedupe.dedupe_key == dedupe_key,
            )
            .first()
        )
        if existing is not None:
            return None

        dedupe = ChannelEventDedupe(
            tenant_id=tenant_id,
            channel_type=trigger_type,
            instance_id=instance_id,
            dedupe_key=dedupe_key,
            outcome=outcome,
        )
        self.db.add(dedupe)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            return None
        return dedupe

    def _write_payload_ref(self, event: TriggerDispatchInput, *, tenant_id: str, trigger_type: str) -> str:
        digest = hashlib.sha256(
            f"{tenant_id}:{trigger_type}:{event.instance_id}:{event.dedupe_key}".encode("utf-8")
        ).hexdigest()[:24]
        filename = f"{trigger_type}-{event.instance_id}-{digest}.json"
        self._payload_dir.mkdir(parents=True, exist_ok=True)
        payload_path = self._payload_dir / filename
        payload_ref = f"backend/data/wake_events/{filename}"
        document = {
            "trigger_type": trigger_type,
            "instance_id": event.instance_id,
            "event_type": event.event_type,
            "dedupe_key": event.dedupe_key,
            "occurred_at": event.occurred_at.isoformat(),
            "importance": self._normalize_importance(event.importance),
            "explicit_agent_id": event.explicit_agent_id,
            "sender_key": event.sender_key,
            "source_id": event.source_id,
            "payload": self._redact(event.payload),
        }
        payload_path.write_text(
            json.dumps(document, default=self._json_default, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return payload_ref

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            redacted: dict[str, Any] = {}
            for key, child in value.items():
                key_text = str(key)
                if self._is_sensitive_key(key_text):
                    redacted[key_text] = "[REDACTED]"
                else:
                    redacted[key_text] = self._redact(child)
            return redacted
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        if isinstance(value, tuple):
            return [self._redact(item) for item in value]
        if isinstance(value, bytes):
            return f"<{len(value)} bytes>"
        return value

    def _is_sensitive_key(self, key: str) -> bool:
        lowered = key.lower()
        return any(part in lowered for part in self._SENSITIVE_KEY_PARTS)

    def _normalize_importance(self, importance: str) -> Importance:
        if importance in {"low", "normal", "high"}:
            return importance  # type: ignore[return-value]
        return "normal"

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
