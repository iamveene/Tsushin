"""
Scheduler Provider System

Provides a unified interface for scheduling across multiple backends:
- Built-in Flows (default)
- Google Calendar
- Asana Tasks

Each agent can select which provider to use for scheduling operations.
"""

from .base import (
    SchedulerProviderBase,
    SchedulerEvent,
    SchedulerProviderType,
    SchedulerEventStatus,
    SchedulerProviderError,
    ProviderNotConfiguredError,
    ProviderAuthenticationError,
    ProviderAPIError,
)
from .flows_provider import FlowsProvider
from .factory import SchedulerProviderFactory

# Import calendar provider (optional, may not have dependencies)
try:
    from .calendar_provider import GoogleCalendarProvider
    _has_calendar = True
except ImportError:
    GoogleCalendarProvider = None
    _has_calendar = False

# Import asana provider (optional)
try:
    from .asana_provider import AsanaProvider
    _has_asana = True
except ImportError:
    AsanaProvider = None
    _has_asana = False

__all__ = [
    # Base classes
    "SchedulerProviderBase",
    "SchedulerEvent",
    "SchedulerProviderType",
    "SchedulerEventStatus",
    # Errors
    "SchedulerProviderError",
    "ProviderNotConfiguredError",
    "ProviderAuthenticationError",
    "ProviderAPIError",
    # Factory
    "SchedulerProviderFactory",
    # Providers
    "FlowsProvider",
    "GoogleCalendarProvider",
    "AsanaProvider",
]

# Auto-register providers
if _has_calendar and GoogleCalendarProvider:
    SchedulerProviderFactory.register_provider(
        SchedulerProviderType.GOOGLE_CALENDAR.value,
        GoogleCalendarProvider
    )

if _has_asana and AsanaProvider:
    SchedulerProviderFactory.register_provider(
        SchedulerProviderType.ASANA.value,
        AsanaProvider
    )
