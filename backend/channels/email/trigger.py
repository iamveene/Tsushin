"""Gmail-backed email trigger runtime."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
import logging
from typing import Any, Callable, ClassVar, Optional, Protocol

from sqlalchemy.orm import Session

from channels.trigger import Trigger
from channels.types import HealthResult, TriggerEvent
from hub.google.gmail_service import GmailService
from models import ContinuousAgent, ContinuousRun, ContinuousSubscription, EmailChannelInstance, GmailIntegration
from services.email_triage_service import create_triage_draft
from services.trigger_dispatch_service import (
    TriggerDispatchInput,
    TriggerDispatchResult,
    TriggerDispatchService,
)


EMAIL_EVENT_TYPE = "email.message.received"
DEFAULT_MAX_RESULTS = 20
EMAIL_TEXT_LIMIT = 16000


class GmailPollService(Protocol):
    """Small protocol for the GmailService methods used by the trigger."""

    async def list_messages(self, max_results: int = 20, **kwargs: Any) -> list[dict[str, Any]]:
        ...

    async def search_messages(self, query: str, max_results: int = 20, **kwargs: Any) -> list[dict[str, Any]]:
        ...

    async def get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        ...


GmailServiceFactory = Callable[[Session, int], GmailPollService]
DispatcherFactory = Callable[[Session], TriggerDispatchService]


@dataclass(frozen=True)
class EmailPollResult:
    """Outcome from polling one email trigger row."""

    instance_id: int
    tenant_id: Optional[str]
    status: str
    fetched_count: int = 0
    dispatched_count: int = 0
    skipped_count: int = 0
    duplicate_count: int = 0
    cursor: Optional[str] = None
    reason: Optional[str] = None
    dispatch_statuses: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NormalizedGmailMessage:
    """Normalized Gmail message data used for cursoring and dispatch."""

    message_id: str
    cursor: str
    occurred_at: datetime
    payload: dict[str, Any]
    sender_key: str


def _default_gmail_service_factory(db: Session, integration_id: int) -> GmailPollService:
    return GmailService(db, integration_id)


def _default_dispatcher_factory(db: Session) -> TriggerDispatchService:
    return TriggerDispatchService(db)


def _now_utc_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _cursor(internal_ms: int, message_id: str) -> str:
    return f"{max(internal_ms, 0):013d}:{message_id}"


def _parse_cursor(value: Optional[str]) -> tuple[int, str]:
    if not value:
        return (-1, "")
    raw = str(value)
    if ":" not in raw:
        return (0, raw)
    prefix, message_id = raw.split(":", 1)
    try:
        return (int(prefix), message_id)
    except ValueError:
        return (0, message_id or raw)


def _cursor_after(candidate: str, previous: Optional[str]) -> bool:
    return _parse_cursor(candidate) > _parse_cursor(previous)


def _parse_internal_date_ms(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _datetime_from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)


def _poll_interval_seconds(instance: EmailChannelInstance) -> int:
    try:
        interval = int(instance.poll_interval_seconds or 60)
    except (TypeError, ValueError):
        interval = 60
    return max(30, min(interval, 3600))


def _poll_due(instance: EmailChannelInstance, now: datetime) -> bool:
    if instance.last_health_check is None:
        return True
    return (now - instance.last_health_check).total_seconds() >= _poll_interval_seconds(instance)


def _parse_header_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _utc_naive(parsedate_to_datetime(value))
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _truncate_text(value: Any, limit: int = EMAIL_TEXT_LIMIT) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _header_map(message: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
    for header in payload.get("headers") or []:
        if not isinstance(header, dict):
            continue
        name = str(header.get("name") or "").lower()
        if name:
            headers[name] = str(header.get("value") or "")
    return headers


def _decode_body_data(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        return base64.urlsafe_b64decode(value.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_message_parts(message: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    body_text = ""
    body_html = ""
    attachments: list[dict[str, Any]] = []

    def extract_part(part: dict[str, Any]) -> None:
        nonlocal body_text, body_html
        mime_type = str(part.get("mimeType") or "")
        body = part.get("body") if isinstance(part.get("body"), dict) else {}

        nested_parts = part.get("parts")
        if isinstance(nested_parts, list):
            for nested in nested_parts:
                if isinstance(nested, dict):
                    extract_part(nested)
            return

        if mime_type == "text/plain":
            decoded = _decode_body_data(body.get("data"))
            if decoded and not body_text:
                body_text = decoded
        elif mime_type == "text/html":
            decoded = _decode_body_data(body.get("data"))
            if decoded and not body_html:
                body_html = decoded
        elif body.get("attachmentId"):
            attachments.append(
                {
                    "filename": part.get("filename") or "attachment",
                    "mimeType": mime_type,
                    "size": body.get("size") or 0,
                    "attachmentId": body.get("attachmentId"),
                }
            )

    payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
    if isinstance(payload.get("parts"), list):
        for part in payload["parts"]:
            if isinstance(part, dict):
                extract_part(part)
    else:
        mime_type = str(payload.get("mimeType") or "text/plain")
        decoded = _decode_body_data((payload.get("body") or {}).get("data"))
        if mime_type == "text/html":
            body_html = decoded
        else:
            body_text = decoded

    return _truncate_text(body_text), _truncate_text(body_html), attachments


def _sender_key(from_header: str, message_id: str) -> str:
    parsed = getaddresses([from_header or ""])
    if parsed:
        _, address = parsed[0]
        if address:
            return address.lower()[:255]
    return f"gmail:{message_id}"[:255]


def normalize_gmail_message(
    *,
    instance: EmailChannelInstance,
    integration: GmailIntegration,
    message: dict[str, Any],
) -> NormalizedGmailMessage:
    """Normalize a Gmail API message into the dispatcher contract."""

    message_id = str(message.get("id") or "").strip()
    if not message_id:
        raise ValueError("Gmail message is missing id")

    headers = _header_map(message)
    internal_ms = _parse_internal_date_ms(message.get("internalDate"))
    occurred_at = _datetime_from_ms(internal_ms) if internal_ms is not None else None
    if occurred_at is None:
        occurred_at = _parse_header_datetime(headers.get("date")) or _now_utc_naive()
        internal_ms = int(occurred_at.replace(tzinfo=timezone.utc).timestamp() * 1000)

    cursor = _cursor(internal_ms, message_id)
    body_text, body_html, attachments = _extract_message_parts(message)

    payload = {
        "email_trigger_id": instance.id,
        "provider": "gmail",
        "gmail_integration_id": integration.id,
        "gmail_account_email": integration.email_address,
        "message": {
            "id": message_id,
            "threadId": message.get("threadId"),
            "historyId": message.get("historyId"),
            "internalDate": message.get("internalDate"),
            "cursor": cursor,
            "subject": headers.get("subject") or "(No Subject)",
            "from": headers.get("from") or "",
            "to": headers.get("to") or "",
            "cc": headers.get("cc") or "",
            "bcc": headers.get("bcc") or "",
            "date": headers.get("date") or "",
            "snippet": message.get("snippet") or "",
            "body_text": body_text,
            "body_html": body_html,
            "attachments": attachments,
            "labels": list(message.get("labelIds") or []),
        },
        "raw_event": {
            "id": message_id,
            "threadId": message.get("threadId"),
            "historyId": message.get("historyId"),
            "internalDate": message.get("internalDate"),
            "labelIds": list(message.get("labelIds") or []),
        },
    }

    return NormalizedGmailMessage(
        message_id=message_id,
        cursor=cursor,
        occurred_at=occurred_at,
        payload=payload,
        sender_key=_sender_key(headers.get("from") or "", message_id),
    )


class EmailTrigger(Trigger):
    """Poll Gmail-backed email trigger rows and dispatch wake events."""

    channel_type: ClassVar[str] = "email"
    delivery_mode: ClassVar[str] = "poll"
    supports_threads: ClassVar[bool] = True
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = True
    supports_media: ClassVar[bool] = True
    text_chunk_limit: ClassVar[int] = EMAIL_TEXT_LIMIT

    def __init__(
        self,
        db_session: Session,
        email_instance_id: int,
        logger: logging.Logger,
        *,
        gmail_service_factory: GmailServiceFactory = _default_gmail_service_factory,
        dispatcher_factory: DispatcherFactory = _default_dispatcher_factory,
        max_results: int = DEFAULT_MAX_RESULTS,
    ) -> None:
        self.db = db_session
        self.email_instance_id = email_instance_id
        self.logger = logger
        self.gmail_service_factory = gmail_service_factory
        self.dispatcher_factory = dispatcher_factory
        self.max_results = max_results

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def poll_or_receive(self) -> list[TriggerEvent]:
        """Poll this trigger instance and dispatch matching Gmail messages."""

        instance = self._load_instance()
        if instance is None:
            self.logger.warning("Email trigger %s not found", self.email_instance_id)
            return []

        await self._poll_instance(
            db=self.db,
            instance=instance,
            logger=self.logger,
            gmail_service_factory=self.gmail_service_factory,
            dispatcher_factory=self.dispatcher_factory,
            max_results=self.max_results,
        )
        return []

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
        self.dispatcher_factory(self.db).dispatch(dispatch_input)

    async def health_check(self) -> HealthResult:
        instance = self._load_instance()
        if instance is None:
            return HealthResult(healthy=False, status="error", detail="Email trigger not found")
        if not instance.is_active or instance.status != "active":
            return HealthResult(healthy=False, status="paused", detail="Email trigger paused")
        return HealthResult(
            healthy=(instance.health_status == "healthy"),
            status=instance.health_status or "unknown",
            detail=instance.health_status_reason,
        )

    def validate_recipient(self, recipient: str) -> bool:
        return bool(recipient)

    def _load_instance(self) -> Optional[EmailChannelInstance]:
        return self.db.query(EmailChannelInstance).filter(
            EmailChannelInstance.id == self.email_instance_id,
        ).first()

    @classmethod
    async def poll_active(
        cls,
        db: Session,
        *,
        logger: Optional[logging.Logger] = None,
        gmail_service_factory: GmailServiceFactory = _default_gmail_service_factory,
        dispatcher_factory: DispatcherFactory = _default_dispatcher_factory,
        max_results: int = DEFAULT_MAX_RESULTS,
        force: bool = False,
    ) -> list[EmailPollResult]:
        """Poll all active Gmail email trigger rows."""

        active_rows = (
            db.query(EmailChannelInstance)
            .filter(
                EmailChannelInstance.provider == "gmail",
                EmailChannelInstance.is_active == True,  # noqa: E712
                EmailChannelInstance.status == "active",
            )
            .order_by(EmailChannelInstance.id.asc())
            .all()
        )
        runtime_logger = logger or logging.getLogger(__name__)

        results: list[EmailPollResult] = []
        for instance in active_rows:
            results.append(
                await cls._poll_instance(
                    db=db,
                    instance=instance,
                    logger=runtime_logger,
                    gmail_service_factory=gmail_service_factory,
                    dispatcher_factory=dispatcher_factory,
                    max_results=max_results,
                    force=force,
                )
            )
        return results

    @classmethod
    async def _poll_instance(
        cls,
        *,
        db: Session,
        instance: EmailChannelInstance,
        logger: logging.Logger,
        gmail_service_factory: GmailServiceFactory,
        dispatcher_factory: DispatcherFactory,
        max_results: int,
        force: bool = False,
    ) -> EmailPollResult:
        if not instance.tenant_id:
            return cls._mark_unhealthy(
                db,
                instance,
                reason="missing_tenant_context",
                status="skipped",
            )
        if not instance.is_active or instance.status != "active":
            return EmailPollResult(
                instance_id=instance.id,
                tenant_id=instance.tenant_id,
                status="skipped",
                reason="inactive_instance",
                cursor=instance.last_cursor,
            )
        if instance.provider != "gmail":
            return cls._mark_unhealthy(
                db,
                instance,
                reason="unsupported_email_provider",
                status="error",
            )
        if not instance.gmail_integration_id:
            return cls._mark_unhealthy(
                db,
                instance,
                reason="missing_gmail_integration",
                status="error",
            )

        integration = db.query(GmailIntegration).filter(
            GmailIntegration.id == instance.gmail_integration_id,
        ).first()
        if integration is None:
            return cls._mark_unhealthy(
                db,
                instance,
                reason="gmail_integration_not_found",
                status="error",
            )
        if integration.tenant_id != instance.tenant_id:
            return cls._mark_unhealthy(
                db,
                instance,
                reason="gmail_integration_tenant_mismatch",
                status="error",
            )
        if not integration.is_active or integration.health_status == "disconnected":
            return cls._mark_unhealthy(
                db,
                instance,
                reason="gmail_integration_inactive",
                status="error",
            )

        poll_started_at = _now_utc_naive()
        if not force and not _poll_due(instance, poll_started_at):
            return EmailPollResult(
                instance_id=instance.id,
                tenant_id=instance.tenant_id,
                status="skipped",
                reason="poll_interval_not_elapsed",
                cursor=instance.last_cursor,
            )

        try:
            gmail = gmail_service_factory(db, integration.id)
            if instance.search_query:
                message_refs = await gmail.search_messages(
                    instance.search_query,
                    max_results=max(1, max_results),
                )
            else:
                message_refs = await gmail.list_messages(max_results=max(1, max_results))

            normalized_messages = await cls._fetch_and_normalize_messages(
                gmail=gmail,
                instance=instance,
                integration=integration,
                message_refs=message_refs,
                logger=logger,
            )
            new_messages = [
                message
                for message in normalized_messages
                if _cursor_after(message.cursor, instance.last_cursor)
            ]
            new_messages.sort(key=lambda message: _parse_cursor(message.cursor))

            dispatcher = dispatcher_factory(db)
            dispatch_results: list[TriggerDispatchResult] = []
            for message in new_messages:
                dispatch_result = dispatcher.dispatch(
                    TriggerDispatchInput(
                        trigger_type=cls.channel_type,
                        instance_id=instance.id,
                        event_type=EMAIL_EVENT_TYPE,
                        dedupe_key=f"gmail:{message.message_id}",
                        occurred_at=message.occurred_at,
                        payload=message.payload,
                        explicit_agent_id=instance.default_agent_id,
                        sender_key=message.sender_key,
                        source_id=message.message_id,
                    )
                )
                dispatch_results.append(dispatch_result)
                await cls._process_managed_triage(
                    db=db,
                    instance=instance,
                    dispatch_result=dispatch_result,
                    email_payload=message.payload,
                    sender_key=message.sender_key,
                )

            newest_cursor = instance.last_cursor
            if normalized_messages:
                newest_cursor = max(
                    [message.cursor for message in normalized_messages] + ([instance.last_cursor] if instance.last_cursor else []),
                    key=_parse_cursor,
                )

            instance.last_health_check = poll_started_at
            instance.health_status = "healthy"
            instance.health_status_reason = None
            if newest_cursor and newest_cursor != instance.last_cursor:
                instance.last_cursor = newest_cursor
            if new_messages:
                instance.last_activity_at = poll_started_at
            db.add(instance)
            db.commit()

            statuses = [result.status for result in dispatch_results]
            return EmailPollResult(
                instance_id=instance.id,
                tenant_id=instance.tenant_id,
                status="ok",
                fetched_count=len(normalized_messages),
                dispatched_count=sum(1 for status in statuses if status == "dispatched"),
                skipped_count=max(0, len(normalized_messages) - len(new_messages)),
                duplicate_count=sum(1 for status in statuses if status == "duplicate"),
                cursor=instance.last_cursor,
                dispatch_statuses=statuses,
            )
        except Exception as exc:
            logger.warning("Email trigger %s Gmail poll failed: %s", instance.id, exc)
            return cls._mark_unhealthy(
                db,
                instance,
                reason=f"gmail_poll_failed:{type(exc).__name__}",
                status="error",
            )

    @staticmethod
    async def _fetch_and_normalize_messages(
        *,
        gmail: GmailPollService,
        instance: EmailChannelInstance,
        integration: GmailIntegration,
        message_refs: list[dict[str, Any]],
        logger: logging.Logger,
    ) -> list[NormalizedGmailMessage]:
        normalized_messages: list[NormalizedGmailMessage] = []
        seen_ids: set[str] = set()

        for message_ref in message_refs:
            message_id = str((message_ref or {}).get("id") or "").strip()
            if not message_id or message_id in seen_ids:
                continue
            seen_ids.add(message_id)
            try:
                message = await gmail.get_message(message_id, format="full")
                normalized_messages.append(
                    normalize_gmail_message(
                        instance=instance,
                        integration=integration,
                        message=message,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Email trigger %s skipped Gmail message %s: %s",
                    instance.id,
                    message_id,
                    exc,
                )
        return normalized_messages

    @staticmethod
    def _mark_unhealthy(
        db: Session,
        instance: EmailChannelInstance,
        *,
        reason: str,
        status: str,
    ) -> EmailPollResult:
        instance.last_health_check = _now_utc_naive()
        instance.health_status = "unhealthy"
        instance.health_status_reason = reason[:500]
        db.add(instance)
        db.commit()
        return EmailPollResult(
            instance_id=instance.id,
            tenant_id=instance.tenant_id,
            status=status,
            reason=reason,
            cursor=instance.last_cursor,
        )

    @classmethod
    async def _process_managed_triage(
        cls,
        *,
        db: Session,
        instance: EmailChannelInstance,
        dispatch_result: TriggerDispatchResult,
        email_payload: dict[str, Any],
        sender_key: str,
    ) -> None:
        """Create drafts for system-owned Email triage subscriptions."""

        if dispatch_result.status != "dispatched":
            return
        if not dispatch_result.continuous_subscription_ids or not dispatch_result.continuous_run_ids:
            return

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
                    ContinuousSubscription.event_type == EMAIL_EVENT_TYPE,
                    ContinuousSubscription.is_system_owned == True,  # noqa: E712
                )
                .first()
            )
            if subscription is None:
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
            if continuous_agent is None or run is None:
                continue

            run.status = "running"
            run.started_at = run.started_at or _now_utc_naive()
            db.add(run)
            db.commit()

            try:
                draft_result = await create_triage_draft(
                    db,
                    trigger=instance,
                    continuous_agent=continuous_agent,
                    email_payload=email_payload,
                    sender_key=sender_key,
                )
                run.status = "succeeded" if draft_result.get("success") else "failed"
                run.outcome_state = {"triage_draft": draft_result}
            except Exception as exc:
                run.status = "failed"
                run.outcome_state = {
                    "triage_draft": {
                        "success": False,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                }
            finally:
                run.finished_at = _now_utc_naive()
                db.add(run)
                db.commit()
