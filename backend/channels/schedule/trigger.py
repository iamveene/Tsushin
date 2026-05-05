"""Schedule trigger implementation backed by persisted cron rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, ClassVar, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from channels.trigger import Trigger
from channels.types import HealthResult, TriggerEvent
from models import ScheduleChannelInstance
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService

logger = logging.getLogger(__name__)

SCHEDULE_EVENT_TYPE = "schedule.fire"


class CronUnavailableError(RuntimeError):
    """Raised when croniter is not installed in the runtime."""


@dataclass(frozen=True)
class SchedulePollResult:
    """Result from polling one due schedule trigger row."""

    instance_id: int
    tenant_id: str
    scheduled_at: datetime
    next_fire_at: Optional[datetime]
    dispatch_status: str
    dispatch_reason: Optional[str] = None


def _croniter_cls():
    try:
        from croniter import croniter
    except ImportError as exc:
        raise CronUnavailableError(
            "croniter is required for schedule trigger cron validation and preview"
        ) from exc
    return croniter


def normalize_utc_naive(value: Optional[datetime] = None) -> datetime:
    """Return a naive UTC datetime for DB storage and comparisons."""

    dt = value or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_iso(value: datetime) -> str:
    return normalize_utc_naive(value).isoformat(timespec="seconds") + "Z"


def _timezone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid timezone: {timezone_name}") from exc


def _local_base(base: Optional[datetime], timezone_name: str) -> datetime:
    tz = _timezone(timezone_name)
    utc_base = normalize_utc_naive(base).replace(tzinfo=timezone.utc)
    return utc_base.astimezone(tz)


def validate_cron_expression(cron_expression: str) -> str:
    """Validate and normalize a cron expression using croniter."""

    expression = (cron_expression or "").strip()
    if not expression:
        raise ValueError("cron_expression must not be empty")

    croniter = _croniter_cls()
    try:
        is_valid = croniter.is_valid(expression)
    except Exception as exc:
        raise ValueError(f"Invalid cron expression: {exc}") from exc
    if not is_valid:
        raise ValueError("Invalid cron expression")
    return expression


def calculate_next_fire_times(
    cron_expression: str,
    timezone_name: str,
    *,
    base: Optional[datetime] = None,
    count: int = 5,
) -> list[datetime]:
    """Return the next cron fire times as naive UTC datetimes."""

    if count < 1:
        return []
    expression = validate_cron_expression(cron_expression)
    local_base = _local_base(base, timezone_name)
    croniter = _croniter_cls()

    iterator = croniter(expression, local_base)
    results: list[datetime] = []
    tz = _timezone(timezone_name)
    for _ in range(count):
        local_next = iterator.get_next(datetime)
        if local_next.tzinfo is None:
            local_next = local_next.replace(tzinfo=tz)
        results.append(local_next.astimezone(timezone.utc).replace(tzinfo=None))
    return results


class ScheduleTrigger(Trigger):
    """Cron-backed trigger that emits due schedule wake events."""

    channel_type: ClassVar[str] = "schedule"
    delivery_mode: ClassVar[str] = "poll"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = False

    def __init__(self, db_session: Session, schedule_instance_id: int, logger_: logging.Logger):
        self.db = db_session
        self.schedule_instance_id = schedule_instance_id
        self.logger = logger_

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def poll_or_receive(self) -> list[TriggerEvent]:
        return []

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        return None

    async def health_check(self) -> HealthResult:
        instance = self.db.query(ScheduleChannelInstance).filter(
            ScheduleChannelInstance.id == self.schedule_instance_id,
        ).first()
        if instance is None:
            return HealthResult(healthy=False, status="error", detail="Schedule trigger not found")
        if not instance.is_active or instance.status != "active":
            return HealthResult(healthy=False, status="paused", detail="Schedule trigger paused")
        return HealthResult(
            healthy=(instance.health_status == "healthy"),
            status=instance.health_status or "unknown",
            detail=instance.health_status_reason,
        )

    def validate_recipient(self, recipient: str) -> bool:
        return True

    @classmethod
    def poll_due(cls, db: Session, now: Optional[datetime] = None) -> list[SchedulePollResult]:
        """Dispatch due active schedule trigger rows.

        This intentionally reads only ScheduleChannelInstance and never uses
        legacy ScheduledEvent rows.
        """

        now_utc = normalize_utc_naive(now)
        due_rows = (
            db.query(ScheduleChannelInstance)
            .filter(
                ScheduleChannelInstance.is_active == True,  # noqa: E712
                ScheduleChannelInstance.status == "active",
                ScheduleChannelInstance.next_fire_at.isnot(None),
                ScheduleChannelInstance.next_fire_at <= now_utc,
            )
            .order_by(ScheduleChannelInstance.next_fire_at.asc(), ScheduleChannelInstance.id.asc())
            .all()
        )

        results: list[SchedulePollResult] = []
        for row in due_rows:
            scheduled_at = normalize_utc_naive(row.next_fire_at)
            scheduled_iso = _utc_iso(scheduled_at)
            fired_iso = _utc_iso(now_utc)
            payload = cls._build_payload(row, scheduled_iso=scheduled_iso, fired_iso=fired_iso)

            dispatch_input = TriggerDispatchInput(
                trigger_type=cls.channel_type,
                instance_id=row.id,
                event_type=SCHEDULE_EVENT_TYPE,
                dedupe_key=f"schedule:{row.id}:{scheduled_iso}",
                occurred_at=scheduled_at,
                payload=payload,
                explicit_agent_id=row.default_agent_id,
                sender_key=f"schedule:{row.id}",
                source_id=scheduled_iso,
            )
            dispatch_result = TriggerDispatchService(db).dispatch(dispatch_input)

            next_fire_at = cls._next_fire_after(row, now_utc)
            row.last_fire_at = scheduled_at
            row.last_activity_at = now_utc
            row.last_cursor = scheduled_iso
            row.next_fire_at = next_fire_at
            if next_fire_at is not None:
                row.health_status = "healthy"
                row.health_status_reason = None
            db.add(row)
            db.commit()

            results.append(
                SchedulePollResult(
                    instance_id=row.id,
                    tenant_id=row.tenant_id,
                    scheduled_at=scheduled_at,
                    next_fire_at=next_fire_at,
                    dispatch_status=dispatch_result.status,
                    dispatch_reason=dispatch_result.reason,
                )
            )
        return results

    @staticmethod
    def _build_payload(row: ScheduleChannelInstance, *, scheduled_iso: str, fired_iso: str) -> dict[str, Any]:
        template = row.payload_template if isinstance(row.payload_template, dict) else {}
        payload = dict(template)
        payload.setdefault(
            "schedule",
            {
                "id": row.id,
                "integration_name": row.integration_name,
                "cron_expression": row.cron_expression,
                "timezone": row.timezone,
                "scheduled_at": scheduled_iso,
                "fired_at": fired_iso,
            },
        )
        return payload

    @staticmethod
    def _next_fire_after(row: ScheduleChannelInstance, now_utc: datetime) -> Optional[datetime]:
        try:
            return calculate_next_fire_times(
                row.cron_expression,
                row.timezone,
                base=now_utc,
                count=1,
            )[0]
        except Exception as exc:
            row.health_status = "unhealthy"
            row.health_status_reason = str(exc)[:500]
            logger.warning(
                "Failed to calculate next schedule fire for trigger %s: %s",
                row.id,
                exc,
            )
            return None
