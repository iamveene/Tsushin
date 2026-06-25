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
import logging
from pathlib import Path
from typing import Any, Literal, Optional

logger = logging.getLogger(__name__)

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from channels.trigger_criteria import evaluate_payload_criteria
from config.feature_flags import flows_trigger_binding_enabled
from models import (
    Agent,
    AgentTeam,
    AgentTeamRun,
    AgentTeamTrigger,
    ChannelEventDedupe,
    ContinuousAgent,
    ContinuousRun,
    ContinuousSubscription,
    EmailChannelInstance,
    FlowTriggerBinding,
    GitHubChannelInstance,
    GitHubCommitsChannelInstance,
    GitHubProjectsChannelInstance,
    GitLabChannelInstance,
    JiraChannelInstance,
    SentinelConfig,
    TeamRunStatus,
    TeamStatus,
    WakeEvent,
    WebhookIntegration,
)
from services.default_agent_service import get_default_agent
from services.flow_binding_service import (
    has_active_suppress_default_binding,
    list_active_bindings_for_trigger,
)


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
    ENQUEUE_FAILED = "enqueue_failed"


class TeamRunQueueEnqueueError(RuntimeError):
    """Raised when a matched team run cannot be inserted into message_queue."""


def _emit_team_run_failed_event(
    *,
    tenant_id: str,
    team_run_id: int,
    team_id: int,
    team_name: Optional[str],
    error_json: dict[str, Any],
) -> None:
    try:
        from services.watcher_activity_service import emit_team_run_async

        emit_team_run_async(
            tenant_id=tenant_id,
            team_run_id=team_run_id,
            team_id=team_id,
            status=TeamRunStatus.FAILED.value,
            event="failed",
            team_name=team_name,
            error_json=error_json,
        )
    except Exception:
        logger.debug("Watcher team_run queue failure event emission skipped", exc_info=True)


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
    team_run_ids: list[int] = field(default_factory=list)
    skipped_team_reasons: list[str] = field(default_factory=list)
    payload_ref: Optional[str] = None


class TriggerDispatchService:
    """Dispatch webhook/email trigger events into continuous-agent work."""

    _INSTANCE_MODELS = {
        "webhook": WebhookIntegration,
        "email": EmailChannelInstance,
        "jira": JiraChannelInstance,
        "github": GitHubChannelInstance,
        "github_projects": GitHubProjectsChannelInstance,
        "github_commits": GitHubCommitsChannelInstance,
        "gitlab": GitLabChannelInstance,
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

        team_matches, skipped_team_reasons = self._matching_team_triggers(
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            instance_id=event.instance_id,
            event_type=event.event_type,
            payload=event.payload,
        )

        agent_id: Optional[int] = None
        bindings: list[FlowTriggerBinding] = []
        subscriptions: list[ContinuousSubscription] = []
        agent_result = self._resolve_agent_id(
            tenant_id=tenant_id,
            trigger_type=trigger_type,
            instance_id=event.instance_id,
            explicit_agent_id=event.explicit_agent_id,
        )
        if isinstance(agent_result, TriggerDispatchResult):
            if not team_matches:
                return self._record_terminal_outcome(
                    event=event,
                    tenant_id=tenant_id,
                    trigger_type=trigger_type,
                    status=TriggerDispatchStatus(agent_result.status),
                    outcome=agent_result.status,
                    reason=agent_result.reason,
                    skipped_team_reasons=skipped_team_reasons,
                )
        else:
            agent_id = agent_result
            subscriptions = self._matching_subscriptions(
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                instance_id=event.instance_id,
                event_type=event.event_type,
                agent_id=agent_id,
            )

        # v0.7.0 Wave 3 — Triggers↔Flows Unification.
        # If any active flow_trigger_binding for this (kind, instance) has
        # ``suppress_default_agent=True``, the bound flow takes over fully
        # for this dispatch — drop subscriptions so no ContinuousRun is
        # created. We still proceed to ``_enqueue_bound_flows`` below to
        # produce FlowRuns. Gated by TSN_FLOWS_TRIGGER_BINDING_ENABLED.
        if agent_id is not None and flows_trigger_binding_enabled():
            bindings = list_active_bindings_for_trigger(
                self.db,
                tenant_id=tenant_id,
                trigger_kind=trigger_type,
                trigger_instance_id=event.instance_id,
            )
            if subscriptions and any(b.suppress_default_agent for b in bindings):
                logger.info(
                    "Suppressing legacy ContinuousRun path for %s/%s — bound flow has suppress_default_agent=True",
                    trigger_type,
                    event.instance_id,
                )
                subscriptions = []

        if not subscriptions and not bindings and not team_matches:
            return self._record_terminal_outcome(
                event=event,
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                status=TriggerDispatchStatus.FILTERED,
                outcome=TriggerDispatchStatus.FILTERED.value,
                reason="no_matching_subscription",
                matched_agent_id=agent_id,
                skipped_team_reasons=skipped_team_reasons,
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
                skipped_team_reasons=skipped_team_reasons,
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

        team_run_ids: list[int] = []
        team_runs_to_enqueue: list[tuple[AgentTeamRun, AgentTeam]] = []
        for team_trigger in team_matches:
            team = team_trigger.team
            team_run = AgentTeamRun(
                tenant_id=tenant_id,
                team_id=team.id,
                status=TeamRunStatus.PENDING.value,
                trigger_event_id=wake_event.id,
                goal_text_snapshot=team.goal_text,
                topology_snapshot=team.topology,
                total_steps=0,
                completed_steps=0,
                failed_steps=0,
            )
            self.db.add(team_run)
            self.db.flush()
            team_run_ids.append(team_run.id)
            team_runs_to_enqueue.append((team_run, team))

        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return TriggerDispatchResult(
                status=TriggerDispatchStatus.DUPLICATE.value,
                reason="duplicate_event",
                tenant_id=tenant_id,
                matched_agent_id=agent_id,
                skipped_team_reasons=skipped_team_reasons,
            )

        # v0.7.x Wave 1-A — Trigger Memory Recap (default-off behind
        # ``TSN_CASE_MEMORY_ENABLED``). Build the recap once, then attach
        # it to BOTH the continuous_task queue payload AND the
        # flow_run_triggered ``trigger_context.source.memory_recap``. The
        # recap is best-effort — any failure swallows + logs and yields
        # ``None`` (recap omitted, dispatch proceeds normally).
        recap: Optional[dict] = None
        try:
            recap_agent_id = self._resolve_recap_agent_id(
                runs_to_enqueue=runs_to_enqueue,
                bindings=bindings,
                fallback_agent_id=agent_id,
            )
            if recap_agent_id is not None:
                payload_doc = self._read_payload_ref(payload_ref) or {}
                if not payload_doc:
                    # Last-resort fallback — _read_payload_ref returns None
                    # only on missing file / parse error. We still want
                    # the recap to render against the in-memory event for
                    # tests + dev ergonomics; this branch is never hit on
                    # the prod path because _write_payload_ref ran above.
                    payload_doc = {
                        "trigger_type": trigger_type,
                        "instance_id": event.instance_id,
                        "event_type": event.event_type,
                        "dedupe_key": event.dedupe_key,
                        "payload": event.payload,
                    }
                from services import trigger_recap_service

                recap = trigger_recap_service.build_memory_recap(
                    db=self.db,
                    tenant_id=tenant_id,
                    agent_id=recap_agent_id,
                    trigger_kind=trigger_type,
                    trigger_instance_id=event.instance_id,
                    payload_doc=payload_doc,
                )
        except Exception:  # noqa: BLE001 — recap NEVER aborts dispatch
            logger.exception(
                "trigger_dispatch: recap build failed (non-fatal) for %s/%s",
                trigger_type,
                event.instance_id,
            )
            recap = None

        # v0.7.0 Wave 3 — fan out to bound Flows alongside the legacy path.
        # Reads ``flow_trigger_binding`` for (kind, instance), enqueues one
        # ``flow_run_triggered`` MessageQueue item per active binding. The
        # bindings list was loaded above; we re-use it here. Failures in the
        # bound-flow fan-out NEVER abort dispatch — the ContinuousRun path
        # is the source of truth for backward compatibility.
        bound_flow_run_ids: list[int] = []
        if bindings and agent_id is not None:
            try:
                bound_flow_run_ids = self._enqueue_bound_flows(
                    tenant_id=tenant_id,
                    trigger_type=trigger_type,
                    instance_id=event.instance_id,
                    wake_event=wake_event,
                    event=event,
                    payload_ref=payload_ref,
                    bindings=bindings,
                    agent_id=agent_id,  # v0.7.0 fix: required for the
                    # message_queue.agent_id NOT NULL column. Caught by
                    # release-finishing dispatch E2E test.
                    memory_recap=recap,
                )
            except Exception:  # pragma: no cover — never abort dispatch on fan-out errors
                logger.exception(
                    "Bound-flow fan-out failed for %s/%s wake_event=%s",
                    trigger_type,
                    event.instance_id,
                    wake_event.id,
                )

        # BUG #26: emit continuous_run activity events to the Watcher Graph
        # View WS so the agent node + run banner glow when a trigger fires.
        # The legacy create_continuous_run() helper at
        # services/continuous_agent_service.py emits this, but the dispatcher
        # builds ContinuousRun rows directly via the ORM so that emit never ran.
        try:
            from services.watcher_activity_service import emit_continuous_run_async

            for run, subscription, _continuous_agent in runs_to_enqueue:
                emit_continuous_run_async(
                    tenant_id=tenant_id,
                    continuous_run_id=run.id,
                    continuous_agent_id=subscription.continuous_agent_id,
                    status=run.status,
                    wake_event_ids=run.wake_event_ids or [],
                    channel_type=trigger_type,
                )
        except Exception:
            pass

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
            memory_recap=recap,
        )

        try:
            self._enqueue_team_runs(
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                wake_event=wake_event,
                event=event,
                payload_ref=payload_ref,
                runs=team_runs_to_enqueue,
            )
        except TeamRunQueueEnqueueError:
            reason = "team_run_queue_enqueue_failed"
            self._mark_team_enqueue_failed(
                tenant_id=tenant_id,
                wake_event_id=wake_event.id,
                team_run_ids=team_run_ids,
                dedupe_id=dedupe.id,
                reason=reason,
                preserve_wake_for_other_work=bool(run_ids or bound_flow_run_ids),
            )
            return TriggerDispatchResult(
                status=TriggerDispatchStatus.ENQUEUE_FAILED.value,
                reason=reason,
                tenant_id=tenant_id,
                matched_agent_id=agent_id,
                dedupe_id=dedupe.id,
                wake_event_id=wake_event.id,
                continuous_run_ids=run_ids,
                continuous_subscription_ids=[subscription.id for subscription in subscriptions],
                team_run_ids=team_run_ids,
                skipped_team_reasons=skipped_team_reasons,
                payload_ref=payload_ref,
            )

        return TriggerDispatchResult(
            status=TriggerDispatchStatus.DISPATCHED.value,
            tenant_id=tenant_id,
            matched_agent_id=agent_id,
            dedupe_id=dedupe.id,
            wake_event_id=wake_event.id,
            continuous_run_ids=run_ids,
            continuous_subscription_ids=[subscription.id for subscription in subscriptions],
            team_run_ids=team_run_ids,
            skipped_team_reasons=skipped_team_reasons,
            payload_ref=payload_ref,
        )

    def _matching_team_triggers(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        instance_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> tuple[list[AgentTeamTrigger], list[str]]:
        """Return active tenant-owned Agent Team triggers matching this event.

        Team trigger config is intentionally fail-closed: each row must carry a
        config_json.trigger_instance_id that matches the dispatch instance.
        Optional event_types and filters then narrow the match.
        """
        if trigger_type not in {"webhook", "github", "gitlab", "jira", "email"}:
            return [], []

        # AgentTeamTrigger.trigger_kind stores "gmail" for the Gmail/email
        # channel, while the dispatch trigger_type is "email". Translate so the
        # query matches the persisted enum value.
        team_trigger_kind = "gmail" if trigger_type == "email" else trigger_type

        try:
            rows = (
                self.db.query(AgentTeamTrigger)
                .join(
                    AgentTeam,
                    (AgentTeamTrigger.tenant_id == AgentTeam.tenant_id)
                    & (AgentTeamTrigger.team_id == AgentTeam.id),
                )
                .filter(
                    AgentTeamTrigger.tenant_id == tenant_id,
                    AgentTeamTrigger.trigger_kind == team_trigger_kind,
                    AgentTeamTrigger.is_enabled.is_(True),
                    AgentTeam.tenant_id == tenant_id,
                )
                .order_by(AgentTeamTrigger.id.asc())
                .all()
            )
        except OperationalError as exc:
            message = str(getattr(exc, "orig", exc)).lower()
            if "no such table" in message and (
                "agent_team_trigger" in message or "agent_team" in message
            ):
                self.db.rollback()
                logger.warning(
                    "Team trigger lookup skipped because team trigger tables are unavailable"
                )
                return [], ["team_trigger_schema_unavailable"]
            raise

        matched: list[AgentTeamTrigger] = []
        skipped: list[str] = []
        for row in rows:
            config = row.config_json if isinstance(row.config_json, dict) else {}
            configured_instance_id = config.get("trigger_instance_id")
            if configured_instance_id is None:
                skipped.append(f"team_trigger:{row.id}:missing_trigger_instance_id")
                continue
            try:
                if int(configured_instance_id) != int(instance_id):
                    skipped.append(f"team_trigger:{row.id}:trigger_instance_mismatch")
                    continue
            except (TypeError, ValueError):
                skipped.append(f"team_trigger:{row.id}:invalid_trigger_instance_id")
                continue

            team = row.team
            if team is None or team.tenant_id != tenant_id:
                skipped.append(f"team_trigger:{row.id}:tenant_mismatch")
                continue
            if team.status != TeamStatus.ACTIVE.value:
                skipped.append(f"team:{team.id}:inactive")
                continue

            event_types = config.get("event_types")
            if event_types:
                if isinstance(event_types, str):
                    allowed_event_types = {event_types}
                elif isinstance(event_types, list):
                    allowed_event_types = {str(item) for item in event_types}
                else:
                    skipped.append(f"team_trigger:{row.id}:invalid_event_types")
                    continue
                if "*" not in allowed_event_types and event_type not in allowed_event_types:
                    skipped.append(f"team_trigger:{row.id}:event_type_mismatch")
                    continue

            filter_config = config.get("filters")
            if filter_config:
                criteria = (
                    filter_config
                    if isinstance(filter_config, dict) and "filters" in filter_config
                    else {
                        "criteria_version": 1,
                        "filters": filter_config,
                        "window": {"mode": "since_cursor"},
                        "ordering": "oldest_first",
                    }
                )
                try:
                    filter_matched, filter_reason = evaluate_payload_criteria(payload, criteria)
                except ValueError as exc:
                    skipped.append(f"team_trigger:{row.id}:invalid_filters:{exc}")
                    continue
                if not filter_matched:
                    skipped.append(f"team_trigger:{row.id}:filter_mismatch:{filter_reason or 'payload'}")
                    continue

            matched.append(row)

        return matched, skipped

    def _enqueue_team_runs(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        wake_event: WakeEvent,
        event: TriggerDispatchInput,
        payload_ref: Optional[str],
        runs: list[tuple[AgentTeamRun, AgentTeam]],
    ) -> None:
        if not runs:
            return
        from services.message_queue_service import MessageQueueService

        mqs = MessageQueueService(self.db)
        sender_key_root = event.sender_key or f"{trigger_type}:{event.instance_id}"
        for team_run, team in runs:
            try:
                mqs.enqueue(
                    channel="team",
                    tenant_id=tenant_id,
                    agent_id=None,
                    sender_key=f"{sender_key_root}:team:{team.id}:run:{team_run.id}",
                    payload={
                        "team_run_id": team_run.id,
                        "team_id": team.id,
                        "trigger_event_id": wake_event.id,
                        "wake_event_id": wake_event.id,
                        "trigger_kind": trigger_type,
                        "trigger_instance_id": event.instance_id,
                        "event_type": event.event_type,
                        "dedupe_key": event.dedupe_key,
                        "occurred_at": event.occurred_at.isoformat() + "Z",
                        "importance": self._normalize_importance(event.importance),
                        "payload_ref": payload_ref,
                    },
                    team_id=team.id,
                    team_run_id=team_run.id,
                    message_type="team_run",
                    commit=False,
                )
            except Exception as exc:
                logger.exception(
                    "Team-run queue enqueue failed for %s/%s wake_event=%s team_run=%s",
                    trigger_type,
                    event.instance_id,
                    wake_event.id,
                    team_run.id,
                )
                self.db.rollback()
                raise TeamRunQueueEnqueueError("team_run_queue_enqueue_failed") from exc
        self.db.commit()

    def _mark_team_enqueue_failed(
        self,
        *,
        tenant_id: str,
        wake_event_id: int,
        team_run_ids: list[int],
        dedupe_id: int,
        reason: str,
        preserve_wake_for_other_work: bool,
    ) -> None:
        now = datetime.utcnow()
        failed_events: list[dict[str, Any]] = []
        if team_run_ids:
            for team_run in (
                self.db.query(AgentTeamRun)
                .filter(
                    AgentTeamRun.tenant_id == tenant_id,
                    AgentTeamRun.id.in_(team_run_ids),
                )
                .all()
            ):
                team_run.status = TeamRunStatus.FAILED.value
                team_run.completed_at = now
                team_run.error_json = {"reason": reason}
                self.db.add(team_run)
                failed_events.append(
                    {
                        "tenant_id": team_run.tenant_id,
                        "team_run_id": team_run.id,
                        "team_id": team_run.team_id,
                        "team_name": team_run.team.name if team_run.team is not None else None,
                        "error_json": team_run.error_json,
                    }
                )

        wake_event = (
            self.db.query(WakeEvent)
            .filter(WakeEvent.tenant_id == tenant_id, WakeEvent.id == wake_event_id)
            .first()
        )
        if wake_event is not None and not preserve_wake_for_other_work:
            wake_event.status = "failed"
            self.db.add(wake_event)

        dedupe = (
            self.db.query(ChannelEventDedupe)
            .filter(ChannelEventDedupe.id == dedupe_id, ChannelEventDedupe.tenant_id == tenant_id)
            .first()
        )
        if dedupe is not None:
            dedupe.outcome = reason
            self.db.add(dedupe)

        self.db.commit()
        for event in failed_events:
            _emit_team_run_failed_event(**event)

    def _enqueue_continuous_tasks(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        wake_event: WakeEvent,
        event: TriggerDispatchInput,
        payload_ref: Optional[str],
        runs: list[tuple[ContinuousRun, ContinuousSubscription, ContinuousAgent]],
        memory_recap: Optional[dict] = None,
    ) -> None:
        """BUG-702: enqueue ``continuous_task`` MessageQueue rows for runs.

        System-owned subscriptions are skipped — they are dispatched inline
        by the channel adapter (e.g. ``_process_managed_actions``).

        ``memory_recap`` (v0.7.x Wave 1-A) — optional pre-built recap dict
        produced by ``trigger_recap_service.build_memory_recap``. When
        present, it is attached to the queue payload under the
        ``memory_recap`` key so ``QueueRouter._dispatch_continuous_task``
        can inject it into the agent's first-turn user message.
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
                if isinstance(memory_recap, dict) and memory_recap.get("rendered_text"):
                    payload["memory_recap"] = memory_recap
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

    def _enqueue_bound_flows(
        self,
        *,
        tenant_id: str,
        trigger_type: str,
        instance_id: int,
        wake_event: WakeEvent,
        event: TriggerDispatchInput,
        payload_ref: Optional[str],
        bindings: list[FlowTriggerBinding],
        agent_id: int,
        memory_recap: Optional[dict] = None,
    ) -> list[int]:
        """v0.7.0 Wave 3 — fan a wake event out to every bound Flow.

        For each ``flow_trigger_binding`` row pointing at this trigger,
        enqueue ONE ``flow_run_triggered`` MessageQueue item that the
        QueueRouter consumes by calling ``FlowEngine.run_flow`` with the
        wake event payload nested under ``trigger_context["source"]``.

        Returns the list of binding IDs that were enqueued (audit only;
        the actual FlowRun rows are created by the worker, not here).

        Failures NEVER abort dispatch — the legacy ContinuousRun path is
        the source of truth for backward compatibility. Caller wraps
        this in a try/except.
        """
        if not bindings:
            return []

        from services.message_queue_service import MessageQueueService

        # Read the redacted payload once and reuse for all bindings. The Flow
        # source contract exposes the original trigger payload under
        # source.payload, not the wake-event document wrapper.
        payload_document = self._read_payload_ref(payload_ref)
        if isinstance(payload_document, dict) and isinstance(payload_document.get("payload"), dict):
            source_payload = payload_document["payload"]
        else:
            logger.warning(
                "Falling back to in-memory redacted payload for %s trigger %s; payload_ref=%s",
                trigger_type,
                instance_id,
                payload_ref,
            )
            source_payload = self._redact(event.payload)

        mqs = MessageQueueService(self.db)
        sender_key_root = event.sender_key or f"{trigger_type}:{instance_id}"
        enqueued_binding_ids: list[int] = []

        for binding in bindings:
            source_block: dict[str, Any] = {
                "trigger_kind": trigger_type,
                "instance_id": instance_id,
                "event_type": event.event_type,
                "dedupe_key": event.dedupe_key,
                "occurred_at": event.occurred_at.isoformat() + "Z",
                "wake_event_id": wake_event.id,
                "binding_id": binding.id,
                "payload": source_payload,
            }
            # v0.7.x Wave 1-A — Trigger Memory Recap rides under
            # source.memory_recap so flow Source steps can reference
            # {{source.memory_recap.rendered_text}} for free (FlowEngine
            # already exposes nested {{source.*}} variables).
            if isinstance(memory_recap, dict) and memory_recap.get("rendered_text"):
                source_block["memory_recap"] = memory_recap
            queue_payload = {
                "flow_definition_id": binding.flow_definition_id,
                "binding_id": binding.id,
                "trigger_event_id": wake_event.id,
                "tenant_id": tenant_id,
                "trigger_kind": trigger_type,
                "trigger_instance_id": instance_id,
                # Nested under "source" so SourceStepHandler + the variable
                # resolver can expose {{source.payload.*}}, {{source.trigger_kind}},
                # etc. Schema must match what flow_engine.SourceStepHandler reads.
                "trigger_context": {"source": source_block},
            }
            mqs.enqueue(
                channel="flow",
                tenant_id=tenant_id,
                # v0.7.0 fix: message_queue.agent_id is NOT NULL (FK to
                # agent.id). Pass the resolved trigger agent_id so the
                # row inserts cleanly. The actual flow execution uses
                # flow_definition_id from the payload — agent_id here is
                # bookkeeping for the queue layer (lets per-agent rate
                # limiters and watcher dashboards group queue items).
                agent_id=agent_id,
                sender_key=f"{sender_key_root}:flow:{binding.flow_definition_id}",
                payload=queue_payload,
                message_type="flow_run_triggered",
            )
            enqueued_binding_ids.append(binding.id)
            logger.info(
                "Enqueued bound flow run: flow=%s binding=%s wake_event=%s",
                binding.flow_definition_id,
                binding.id,
                wake_event.id,
            )

        return enqueued_binding_ids

    def _resolve_recap_agent_id(
        self,
        *,
        runs_to_enqueue: list[
            tuple[ContinuousRun, ContinuousSubscription, ContinuousAgent]
        ],
        bindings: list[FlowTriggerBinding],
        fallback_agent_id: Optional[int],
    ) -> Optional[int]:
        """Pick an agent_id to scope the recap's vector search.

        The recap config is per-trigger (tenant + kind + instance_id), but
        ``case_memory_service.search_similar_cases`` needs an agent_id to
        resolve the vector store. We pick:

          1. The first matched continuous_agent.agent_id when at least
             one ContinuousRun was created — the recap will be injected
             into that subscription's queue payload.
          2. Otherwise, the resolved trigger agent_id (fallback) — used
             for bound flows that don't go through ContinuousRun.
          3. ``None`` when neither is available — caller skips recap.
        """
        for _run, _subscription, continuous_agent in runs_to_enqueue:
            agent_id_attr = getattr(continuous_agent, "agent_id", None)
            if isinstance(agent_id_attr, int):
                return agent_id_attr
        if isinstance(fallback_agent_id, int):
            return fallback_agent_id
        # bindings don't carry an agent_id directly — they reference
        # FlowDefinition. Without a fallback agent_id we can't scope the
        # search, so skip recap entirely.
        if bindings:
            return None
        return None

    def _read_payload_ref(self, payload_ref: Optional[str]) -> Optional[dict]:
        """Read the redacted payload JSON written to disk by ``_write_payload_ref``.

        Returns None on missing file / parse error so callers can use a
        redacted in-memory fallback. ``_write_payload_ref`` stores a stable
        repo-relative ref (``backend/data/wake_events/<file>.json``), while
        tests and deployments can configure ``payload_dir`` to a different
        root, so we normalize legacy and current refs back to that directory.
        """
        if not payload_ref:
            return None
        try:
            path = self._resolve_payload_ref_path(payload_ref)
            if path is None or not path.exists():
                return None
            payload_root = self._payload_dir.resolve()
            try:
                path.resolve().relative_to(payload_root)
            except ValueError:
                logger.warning("Ignoring payload_ref outside payload_dir: %s", payload_ref)
                return None
            with path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            logger.exception("Failed to re-read payload_ref %s", payload_ref)
            return None

    def _resolve_payload_ref_path(self, payload_ref: str) -> Optional[Path]:
        path = Path(payload_ref)
        if path.is_absolute():
            return path

        parts = path.parts
        if len(parts) >= 4 and parts[-4:-1] == ("backend", "data", "wake_events"):
            return self._payload_dir / path.name
        if len(parts) >= 3 and parts[-3:-1] == ("data", "wake_events"):
            return self._payload_dir / path.name
        if len(parts) == 1:
            return self._payload_dir / path.name

        return Path.cwd() / path

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
        if trigger_type in {"github", "gitlab"} and isinstance(criteria, dict):
            envelope_event = str(criteria.get("event") or "").strip().lower()
            if trigger_type == "github" and envelope_event == "pull_request":
                return self._github_pr_criteria_reason(event.payload, criteria)
            if envelope_event:
                return self._repository_criteria_reason(
                    event.payload,
                    criteria,
                    provider=trigger_type,
                    provider_event=event.payload.get("provider_event") if isinstance(event.payload, dict) else None,
                )
        try:
            matched, reason = evaluate_payload_criteria(event.payload, criteria)
        except ValueError as exc:
            return f"invalid_trigger_criteria:{exc}"
        if matched:
            return None
        return f"criteria_no_match:{reason or 'payload'}"

    def _repository_criteria_reason(
        self,
        payload: dict[str, Any],
        criteria: dict[str, Any],
        *,
        provider: str,
        provider_event: Optional[str] = None,
    ) -> Optional[str]:
        try:
            from channels.repository.criteria import evaluate_repository_criteria

            matched, reason = evaluate_repository_criteria(
                payload,
                criteria,
                provider=provider,
                provider_event=provider_event,
            )
        except ValueError as exc:
            return f"invalid_trigger_criteria:{exc}"
        if matched:
            return None
        return f"criteria_no_match:{reason}"

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
        skipped_team_reasons: Optional[list[str]] = None,
    ) -> TriggerDispatchResult:
        skipped_team_reasons = skipped_team_reasons or []
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
                skipped_team_reasons=skipped_team_reasons,
            )
        self.db.commit()
        return TriggerDispatchResult(
            status=status.value,
            reason=reason,
            tenant_id=tenant_id,
            matched_agent_id=matched_agent_id,
            dedupe_id=dedupe.id,
            skipped_team_reasons=skipped_team_reasons,
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
