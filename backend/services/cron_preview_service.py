"""Cron expression validation + next-fire preview.

Extracted from the now-removed Schedule trigger so the Flow wizard's
scheduled-kind step can reuse it. Pure utility functions; no DB access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CronUnavailableError(RuntimeError):
    """Raised when croniter is not installed in the runtime."""


def _croniter_cls():
    try:
        from croniter import croniter
    except ImportError as exc:
        raise CronUnavailableError(
            "croniter is required for cron validation and preview"
        ) from exc
    return croniter


def normalize_utc_naive(value: Optional[datetime] = None) -> datetime:
    dt = value or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


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
