"""Timezone helpers for agent-local clocks and scheduler boundaries.

Database scheduler timestamps are stored as naive UTC.  Natural-language and
calendar inputs, on the other hand, are usually naive local wall-clock values.
Keeping those two representations explicit prevents the host/container timezone
from leaking into reminder execution and lets ``zoneinfo`` apply historical DST
offsets for the date being scheduled.
"""

from datetime import datetime, timezone
from typing import Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from constants.agent_config import DEFAULT_AGENT_TIMEZONE


TimezoneValue = Optional[Union[str, ZoneInfo]]


def resolve_timezone_name(value: TimezoneValue = None) -> str:
    """Return a valid IANA timezone name, falling back to the platform default."""
    if isinstance(value, ZoneInfo):
        return value.key
    if value is not None and not isinstance(value, str):
        return DEFAULT_AGENT_TIMEZONE

    candidate = (value or DEFAULT_AGENT_TIMEZONE).strip()
    try:
        ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return DEFAULT_AGENT_TIMEZONE
    return candidate


def resolve_timezone(value: TimezoneValue = None) -> ZoneInfo:
    """Resolve an IANA timezone using the configured platform fallback."""
    return ZoneInfo(resolve_timezone_name(value))


def localize_wall_time(value: datetime, timezone_value: TimezoneValue = None) -> datetime:
    """Interpret a naive datetime as local wall time in ``timezone_value``.

    Aware inputs are converted normally.  For naive inputs, a UTC round-trip is
    used to reject nonexistent local times during a spring-forward transition.
    Ambiguous fall-back times use ``fold=0`` (the first occurrence), matching
    Python's documented default while remaining deterministic.
    """
    zone = resolve_timezone(timezone_value)
    if value.tzinfo is not None:
        return value.astimezone(zone)

    candidate = value.replace(tzinfo=zone, fold=0)
    round_tripped = candidate.astimezone(timezone.utc).astimezone(zone)
    if round_tripped.replace(tzinfo=None) != value:
        raise ValueError(
            f"Local time {value.isoformat()} does not exist in {zone.key} because of a DST transition"
        )
    return candidate


def to_utc_naive(value: datetime, timezone_value: TimezoneValue = None) -> datetime:
    """Convert an aware instant or local naive wall time to database-style UTC."""
    aware = localize_wall_time(value, timezone_value)
    return aware.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(value: datetime, timezone_value: TimezoneValue = None) -> datetime:
    """Convert a database-style naive UTC (or any aware instant) to agent local time."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(resolve_timezone(timezone_value))


def to_local_naive(value: datetime, timezone_value: TimezoneValue = None) -> datetime:
    """Return a provider-friendly naive local wall-clock datetime."""
    if value.tzinfo is None:
        # Validate DST gaps while preserving the provider's naive-local contract.
        localize_wall_time(value, timezone_value)
        return value
    return value.astimezone(resolve_timezone(timezone_value)).replace(tzinfo=None)
