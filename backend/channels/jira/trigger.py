"""Jira trigger adapter for normalized issue wakeups."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Optional

import httpx
from sqlalchemy.orm import Session

from channels.trigger import Trigger
from channels.jira.utils import jira_issue_link, normalize_jira_site_url
from channels.types import HealthResult, TriggerEvent
from hub.security import TokenEncryption
from models import ContinuousAgent, ContinuousRun, ContinuousSubscription, JiraChannelInstance, WakeEvent
from services.encryption_key_service import get_webhook_encryption_key
from services.jira_notification_service import (
    JIRA_NOTIFICATION_ACTION_TYPE,
    JIRA_NOTIFICATION_EVENT_TYPE,
    send_jira_whatsapp_notification,
)
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService


_JIRA_TZ_RE = re.compile(r"([+-]\d{2})(\d{2})$")
_JIRA_SEARCH_TIMEOUT_SECONDS = 15.0
_DEFAULT_MAX_EVENTS_PER_POLL = 50
_MAX_EVENTS_PER_POLL = 100
_JIRA_SEARCH_FIELDS = [
    "summary",
    "description",
    "status",
    "statusCategory",
    "issuetype",
    "project",
    "priority",
    "reporter",
    "assignee",
    "created",
    "updated",
    "labels",
]


@dataclass(frozen=True)
class JiraPollResult:
    """Summary of one Jira trigger poll."""

    instance_id: int
    tenant_id: str
    status: str
    fetched_count: int = 0
    dispatched_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    processed_count: int = 0
    failed_count: int = 0
    cursor: Optional[str] = None
    reason: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime = field(default_factory=datetime.utcnow)
    dispatch_statuses: list[str] = field(default_factory=list)


def _parse_jira_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value.strip():
        return datetime.utcnow()

    normalized = value.strip().replace("Z", "+00:00")
    normalized = _JIRA_TZ_RE.sub(r"\1:\2", normalized)
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.utcnow()


def _cursor_sort_key(value: Any) -> datetime:
    parsed = _parse_jira_datetime(value)
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def _first_user_identifier(*users: Any) -> Optional[str]:
    for user in users:
        if not isinstance(user, dict):
            continue
        for key in ("accountId", "emailAddress", "displayName", "name"):
            value = user.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


class JiraTrigger(Trigger):
    """Normalize Jira issues and dispatch them to continuous-agent wakeups."""

    channel_type: ClassVar[str] = "jira"
    delivery_mode: ClassVar[str] = "poll"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = False
    text_chunk_limit: ClassVar[int] = 16000

    def __init__(
        self,
        db_session: Session,
        jira_instance_id: int,
        logger: logging.Logger,
        dispatcher: Optional[TriggerDispatchService] = None,
    ) -> None:
        self.db = db_session
        self.jira_instance_id = jira_instance_id
        self.logger = logger
        self.dispatcher = dispatcher or TriggerDispatchService(db_session)

    async def start(self) -> None:
        """No persistent connection is needed for Jira polling."""
        return None

    async def stop(self) -> None:
        """No persistent connection is needed for Jira polling."""
        return None

    def _load_instance(self):
        return self.db.query(JiraChannelInstance).filter_by(id=self.jira_instance_id).first()

    def normalize_issue_payload(self, issue: dict[str, Any]) -> TriggerDispatchInput:
        """Convert a Jira issue payload into the dispatcher contract."""
        instance = self._load_instance()
        if instance is None:
            raise ValueError("Jira trigger instance not found")
        return self._issue_to_dispatch_input(issue, instance)

    def _issue_to_dispatch_input(self, issue: dict[str, Any], instance: Any) -> TriggerDispatchInput:
        if not isinstance(issue, dict):
            raise ValueError("Jira issue payload must be an object")

        issue_id = str(issue.get("id") or "").strip()
        issue_key = str(issue.get("key") or "").strip()
        issue_identity = issue_id or issue_key
        if not issue_identity:
            raise ValueError("Jira issue payload must include id or key")

        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
        updated = str(fields.get("updated") or issue.get("updated") or "").strip()
        dedupe_key = f"jira_issue:{issue_key or issue_identity}"
        occurred_at = _parse_jira_datetime(updated)

        payload = {
            "issue": issue,
            "jira": {
                "site_url": instance.site_url,
                "project_key": instance.project_key,
                "jql": instance.jql,
                "link": jira_issue_link(instance.site_url, issue_key),
            },
        }
        sender_key = _first_user_identifier(fields.get("reporter"), fields.get("assignee"))

        return TriggerDispatchInput(
            trigger_type=self.channel_type,
            instance_id=instance.id,
            event_type=JIRA_NOTIFICATION_EVENT_TYPE,
            dedupe_key=dedupe_key,
            payload=payload,
            occurred_at=occurred_at,
            importance="normal",
            explicit_agent_id=instance.default_agent_id,
            sender_key=sender_key or issue_key or issue_id,
            source_id=issue_key or issue_id,
        )

    async def poll_or_receive(self) -> list[TriggerEvent]:
        """Scheduler-driven polling uses ``poll_active`` and returns audit rows."""
        return []

    @classmethod
    async def poll_active(
        cls,
        db: Session,
        *,
        dispatcher_factory: Optional[type[TriggerDispatchService]] = None,
        force: bool = False,
    ) -> list[JiraPollResult]:
        """Poll every due active Jira trigger."""

        rows = (
            db.query(JiraChannelInstance)
            .filter(
                JiraChannelInstance.is_active == True,  # noqa: E712
                JiraChannelInstance.status == "active",
            )
            .order_by(JiraChannelInstance.id.asc())
            .all()
        )
        results: list[JiraPollResult] = []
        for instance in rows:
            if not force and not cls._is_due(instance):
                results.append(
                    JiraPollResult(
                        instance_id=instance.id,
                        tenant_id=instance.tenant_id,
                        status="skipped",
                        reason="poll_interval_not_elapsed",
                        cursor=instance.last_cursor,
                    )
                )
                continue
            results.append(
                await cls.poll_instance(
                    db,
                    instance,
                    dispatcher_factory=dispatcher_factory,
                    force=True,
                )
            )
        return results

    @classmethod
    async def poll_instance(
        cls,
        db: Session,
        instance: JiraChannelInstance,
        *,
        dispatcher_factory: Optional[type[TriggerDispatchService]] = None,
        force: bool = False,
    ) -> JiraPollResult:
        """Poll one Jira trigger and dispatch every returned issue."""

        if not instance.is_active or instance.status != "active":
            return JiraPollResult(
                instance_id=instance.id,
                tenant_id=instance.tenant_id,
                status="skipped",
                reason="inactive_instance",
                cursor=instance.last_cursor,
            )
        if not force and not cls._is_due(instance):
            return JiraPollResult(
                instance_id=instance.id,
                tenant_id=instance.tenant_id,
                status="skipped",
                reason="poll_interval_not_elapsed",
                cursor=instance.last_cursor,
            )

        poll_started_at = datetime.utcnow()
        try:
            api_token = _decrypt_token(db, instance.tenant_id, instance.api_token_encrypted)
            issues = await cls._fetch_issues(
                site_url=instance.site_url,
                jql=instance.jql,
                auth_email=instance.auth_email,
                api_token=api_token,
                max_results=_max_events_per_poll(instance.trigger_criteria),
            )

            dispatcher = (dispatcher_factory or TriggerDispatchService)(db)
            dispatch_statuses: list[str] = []
            processed_count = 0
            failed_count = 0

            adapter = cls(db, instance.id, logging.getLogger(__name__), dispatcher)
            for issue in issues:
                dispatch_result = dispatcher.dispatch(adapter._issue_to_dispatch_input(issue, instance))
                dispatch_statuses.append(dispatch_result.status)
                outcomes = await cls._process_managed_notification(
                    db=db,
                    instance=instance,
                    dispatch_result=dispatch_result,
                    issue_payload={"issue": issue},
                )
                processed_count += sum(1 for outcome in outcomes if outcome.get("success"))
                failed_count += sum(1 for outcome in outcomes if not outcome.get("success"))

            newest_cursor = _newest_cursor(issues, instance.last_cursor)
            instance.site_url = normalize_jira_site_url(instance.site_url)
            instance.last_health_check = poll_started_at
            instance.health_status = "healthy"
            instance.health_status_reason = None
            if newest_cursor and newest_cursor != instance.last_cursor:
                instance.last_cursor = newest_cursor
            if any(status == "dispatched" for status in dispatch_statuses):
                instance.last_activity_at = poll_started_at
            db.add(instance)
            db.commit()

            return JiraPollResult(
                instance_id=instance.id,
                tenant_id=instance.tenant_id,
                status="ok",
                fetched_count=len(issues),
                dispatched_count=sum(1 for status in dispatch_statuses if status == "dispatched"),
                duplicate_count=sum(1 for status in dispatch_statuses if status == "duplicate"),
                skipped_count=sum(1 for status in dispatch_statuses if status not in {"dispatched", "duplicate"}),
                processed_count=processed_count,
                failed_count=failed_count,
                cursor=instance.last_cursor,
                dispatch_statuses=dispatch_statuses,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning("Jira trigger %s poll failed: %s", instance.id, type(exc).__name__)
            return cls._mark_unhealthy(
                db,
                instance,
                reason=f"jira_poll_failed:{type(exc).__name__}",
                status="error",
            )

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        """Forward an already-normalized TriggerEvent through the dispatcher."""
        dispatch_input = TriggerDispatchInput(
            trigger_type=event.trigger_type,
            instance_id=event.instance_id,
            event_type=event.event_type,
            dedupe_key=event.dedupe_key,
            payload=event.payload,
            occurred_at=event.occurred_at,
            importance=event.importance,
            explicit_agent_id=event.matched_agent_id,
            sender_key=None,
            source_id=None,
        )
        self.dispatcher.dispatch(dispatch_input)

    async def emit_issue_wake_event(self, issue: dict[str, Any]):
        """Normalize and dispatch a Jira issue payload."""
        return self.dispatcher.dispatch(self.normalize_issue_payload(issue))

    async def health_check(self) -> HealthResult:
        instance = self._load_instance()
        if instance is None:
            return HealthResult(healthy=False, status="error", detail="Jira trigger not found")
        if not instance.is_active or instance.status == "paused":
            return HealthResult(healthy=False, status="paused", detail="Jira trigger paused")
        return HealthResult(
            healthy=(instance.health_status == "healthy"),
            status=instance.health_status or "unknown",
            detail=instance.health_status_reason,
        )

    def validate_recipient(self, recipient: str) -> bool:
        """Jira trigger wakeups do not have user-addressable recipients."""
        return True

    @staticmethod
    def _is_due(instance: JiraChannelInstance) -> bool:
        if instance.last_health_check is None:
            return True
        elapsed = (datetime.utcnow() - instance.last_health_check).total_seconds()
        return elapsed >= int(instance.poll_interval_seconds or 300)

    @staticmethod
    async def _fetch_issues(
        *,
        site_url: str,
        jql: str,
        auth_email: Optional[str],
        api_token: Optional[str],
        max_results: int,
    ) -> list[dict[str, Any]]:
        auth = None
        if auth_email or api_token:
            if not auth_email or not api_token:
                raise ValueError("jira_auth_incomplete")
            auth = (auth_email, api_token)

        payload = {
            "jql": _ordered_jql(jql),
            "maxResults": max_results,
            "fields": _JIRA_SEARCH_FIELDS,
        }
        url = f"{normalize_jira_site_url(site_url)}/rest/api/3/search/jql"
        async with httpx.AsyncClient(timeout=_JIRA_SEARCH_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, auth=auth)
        if response.status_code >= 400:
            raise ValueError(f"jira_http_{response.status_code}")
        data = response.json()
        raw_issues = data.get("issues")
        if not isinstance(raw_issues, list):
            return []
        return [issue for issue in raw_issues if isinstance(issue, dict)]

    @staticmethod
    def _mark_unhealthy(
        db: Session,
        instance: JiraChannelInstance,
        *,
        reason: str,
        status: str,
    ) -> JiraPollResult:
        instance.last_health_check = datetime.utcnow()
        instance.health_status = "unhealthy"
        instance.health_status_reason = reason[:500]
        db.add(instance)
        db.commit()
        return JiraPollResult(
            instance_id=instance.id,
            tenant_id=instance.tenant_id,
            status=status,
            reason=reason,
            cursor=instance.last_cursor,
        )

    @classmethod
    async def _process_managed_notification(
        cls,
        *,
        db: Session,
        instance: JiraChannelInstance,
        dispatch_result: Any,
        issue_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Send WhatsApp notifications for system-owned Jira subscriptions."""

        if dispatch_result.status != "dispatched":
            return []
        if not dispatch_result.continuous_subscription_ids or not dispatch_result.continuous_run_ids:
            return []

        outcomes: list[dict[str, Any]] = []
        for subscription_id, run_id in zip(
            dispatch_result.continuous_subscription_ids,
            dispatch_result.continuous_run_ids,
        ):
            subscription = (
                db.query(ContinuousSubscription)
                .filter(
                    ContinuousSubscription.id == subscription_id,
                    ContinuousSubscription.tenant_id == instance.tenant_id,
                    ContinuousSubscription.channel_type == cls.channel_type,
                    ContinuousSubscription.channel_instance_id == instance.id,
                    ContinuousSubscription.event_type == JIRA_NOTIFICATION_EVENT_TYPE,
                    ContinuousSubscription.is_system_owned == True,  # noqa: E712
                )
                .first()
            )
            if subscription is None:
                continue
            action_config = subscription.action_config if isinstance(subscription.action_config, dict) else {}
            if action_config.get("action_type") != JIRA_NOTIFICATION_ACTION_TYPE:
                continue

            continuous_agent = (
                db.query(ContinuousAgent)
                .filter(
                    ContinuousAgent.id == subscription.continuous_agent_id,
                    ContinuousAgent.tenant_id == instance.tenant_id,
                    ContinuousAgent.is_system_owned == True,  # noqa: E712
                )
                .first()
            )
            run = (
                db.query(ContinuousRun)
                .filter(
                    ContinuousRun.id == run_id,
                    ContinuousRun.tenant_id == instance.tenant_id,
                )
                .first()
            )
            wake_event = (
                db.query(WakeEvent)
                .filter(
                    WakeEvent.id == dispatch_result.wake_event_id,
                    WakeEvent.tenant_id == instance.tenant_id,
                )
                .first()
            )
            if continuous_agent is None or run is None:
                continue

            run.status = "running"
            run.started_at = run.started_at or datetime.utcnow()
            if wake_event is not None:
                wake_event.status = "claimed"
                db.add(wake_event)
            db.add(run)
            db.commit()

            try:
                notification_result = await send_jira_whatsapp_notification(
                    db,
                    trigger=instance,
                    continuous_agent=continuous_agent,
                    issue_payload=issue_payload,
                    recipient_phone=str(action_config.get("recipient_phone") or ""),
                )
                success = bool(notification_result.get("success"))
                run.status = "succeeded" if success else "failed"
                run.outcome_state = {"jira_whatsapp_notification": notification_result}
                if wake_event is not None:
                    wake_event.status = "processed" if success else "failed"
                    db.add(wake_event)
                outcomes.append(notification_result)
            except Exception as exc:
                failure = {
                    "success": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "action": JIRA_NOTIFICATION_ACTION_TYPE,
                }
                run.status = "failed"
                run.outcome_state = {"jira_whatsapp_notification": failure}
                if wake_event is not None:
                    wake_event.status = "failed"
                    db.add(wake_event)
                outcomes.append(failure)
            finally:
                run.finished_at = datetime.utcnow()
                db.add(run)
                db.commit()
        return outcomes


def _decrypt_token(db: Session, tenant_id: str, encrypted: Optional[str]) -> Optional[str]:
    if not encrypted:
        return None
    master_key = get_webhook_encryption_key(db)
    if not master_key:
        raise ValueError("missing_jira_encryption_key")
    return TokenEncryption(master_key.encode()).decrypt(encrypted, tenant_id)


def _ordered_jql(jql: str) -> str:
    value = jql.strip()
    if re.search(r"\border\s+by\b", value, flags=re.IGNORECASE):
        return value
    return f"{value} ORDER BY updated ASC, key ASC"


def _max_events_per_poll(criteria: Any) -> int:
    max_events = None
    if isinstance(criteria, dict):
        rate_limit = criteria.get("rate_limit")
        if isinstance(rate_limit, dict):
            max_events = rate_limit.get("max_events_per_poll")
    try:
        value = int(max_events)
    except (TypeError, ValueError):
        value = _DEFAULT_MAX_EVENTS_PER_POLL
    return max(1, min(value, _MAX_EVENTS_PER_POLL))


def _newest_cursor(issues: list[dict[str, Any]], existing_cursor: Optional[str]) -> Optional[str]:
    candidates: list[str] = []
    for issue in issues:
        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
        updated = fields.get("updated")
        if isinstance(updated, str) and updated.strip():
            candidates.append(updated.strip())
    if existing_cursor:
        candidates.append(existing_cursor)
    if not candidates:
        return existing_cursor
    return max(candidates, key=_cursor_sort_key)
