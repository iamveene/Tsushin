"""
Scheduler Provider Base Classes

Defines the abstract interface for all scheduler providers and the unified event model.
This allows the FlowsSkill to work with different scheduling backends (Flows, Google Calendar, Asana)
through a consistent API.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class SchedulerProviderType(str, Enum):
    """Supported scheduler provider types."""
    FLOWS = "flows"
    GOOGLE_CALENDAR = "google_calendar"
    ASANA = "asana"


class SchedulerEventStatus(str, Enum):
    """Event status across all providers."""
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class SchedulerEvent:
    """
    Provider-agnostic event representation.

    This unified model represents events from any scheduling backend,
    allowing the FlowsSkill to work with different providers seamlessly.

    Attributes:
        id: Provider-specific event ID
        provider: Which provider owns this event (flows, google_calendar, asana)
        title: Event title/name
        start: Event start time
        end: Event end time (optional for reminders/tasks)
        description: Optional event description
        location: Optional event location (Calendar only)
        is_all_day: Whether this is an all-day event
        status: Current event status
        recurrence: Recurrence rule (optional)
        reminder_minutes: Minutes before to remind (optional)
        attendees: List of attendee emails (Calendar only)
        raw_data: Original provider response for debugging
        metadata: Additional provider-specific data

    Example:
        # From Flows
        SchedulerEvent(
            id="flow_123",
            provider="flows",
            title="Buy bread",
            start=datetime(2025, 1, 15, 14, 0),
            status=SchedulerEventStatus.SCHEDULED
        )

        # From Google Calendar
        SchedulerEvent(
            id="gcal_abc123",
            provider="google_calendar",
            title="Team Meeting",
            start=datetime(2025, 1, 15, 14, 0),
            end=datetime(2025, 1, 15, 15, 0),
            location="Conference Room A",
            attendees=["john@example.com"],
            status=SchedulerEventStatus.SCHEDULED
        )

        # From Asana
        SchedulerEvent(
            id="asana_456",
            provider="asana",
            title="Review PR #42",
            start=datetime(2025, 1, 15, 23, 59),  # Due date as start
            status=SchedulerEventStatus.SCHEDULED,
            metadata={"project_gid": "123", "assignee_gid": "456"}
        )
    """
    id: str
    provider: str  # SchedulerProviderType value
    title: str
    start: datetime
    end: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    is_all_day: bool = False
    status: SchedulerEventStatus = SchedulerEventStatus.SCHEDULED
    recurrence: Optional[str] = None
    reminder_minutes: Optional[int] = None
    attendees: List[str] = field(default_factory=list)
    raw_data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "provider": self.provider,
            "title": self.title,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "description": self.description,
            "location": self.location,
            "is_all_day": self.is_all_day,
            "status": self.status.value if isinstance(self.status, SchedulerEventStatus) else self.status,
            "recurrence": self.recurrence,
            "reminder_minutes": self.reminder_minutes,
            "attendees": self.attendees,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SchedulerEvent":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            provider=data["provider"],
            title=data["title"],
            start=datetime.fromisoformat(data["start"]) if data.get("start") else datetime.now(),
            end=datetime.fromisoformat(data["end"]) if data.get("end") else None,
            description=data.get("description"),
            location=data.get("location"),
            is_all_day=data.get("is_all_day", False),
            status=SchedulerEventStatus(data.get("status", "scheduled")),
            recurrence=data.get("recurrence"),
            reminder_minutes=data.get("reminder_minutes"),
            attendees=data.get("attendees", []),
            raw_data=data.get("raw_data"),
            metadata=data.get("metadata", {}),
        )


class SchedulerProviderBase(ABC):
    """
    Abstract base class for all scheduler providers.

    Provides a unified interface for scheduling operations across different backends.
    Each provider must implement these methods to integrate with the FlowsSkill.

    Providers:
        - FlowsProvider: Built-in Flows system (reminders, AI conversations)
        - GoogleCalendarProvider: Google Calendar API
        - AsanaProvider: Asana tasks with due dates

    Usage:
        provider = SchedulerProviderFactory.get_provider(
            provider_type="google_calendar",
            integration_id=123,
            db=db_session
        )

        # Create an event
        event = await provider.create_event(
            title="Team Meeting",
            start=datetime(2025, 1, 15, 14, 0),
            end=datetime(2025, 1, 15, 15, 0)
        )

        # List events
        events = await provider.list_events(
            start=datetime(2025, 1, 15, 0, 0),
            end=datetime(2025, 1, 16, 0, 0)
        )
    """

    # Class attributes - must be overridden by subclasses
    provider_type: SchedulerProviderType = SchedulerProviderType.FLOWS
    provider_name: str = "Base Provider"
    provider_description: str = "Base scheduler provider"

    # Feature flags - override in subclasses to indicate supported features
    supports_end_time: bool = True  # Whether provider supports event end times
    supports_location: bool = False  # Whether provider supports locations
    supports_attendees: bool = False  # Whether provider supports attendees
    supports_recurrence: bool = False  # Whether provider supports recurring events
    supports_reminders: bool = True  # Whether provider supports reminders
    supports_availability: bool = False  # Whether provider supports free/busy queries

    def __init__(self, db, tenant_id: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the provider.

        Args:
            db: SQLAlchemy database session
            tenant_id: Tenant ID for multi-tenant isolation
            config: Optional provider configuration including permissions

        Config structure:
            {
                "permissions": {
                    "read": bool,   # View/list events
                    "write": bool   # Create/update/delete events
                },
                ... other provider-specific settings
            }
        """
        self.db = db
        self.tenant_id = tenant_id
        self.config = config or {}

        # Initialize permissions from config
        # Default: full access (backward compatibility)
        permissions_config = self.config.get("permissions", {})
        self._permissions = {
            "read": permissions_config.get("read", True),
            "write": permissions_config.get("write", True),
        }

        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def create_event(
        self,
        title: str,
        start: datetime,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        reminder_minutes: Optional[int] = None,
        recurrence: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        **kwargs
    ) -> SchedulerEvent:
        """
        Create a new scheduled event.

        Args:
            title: Event title/name
            start: Event start time
            end: Event end time (optional, provider-dependent)
            description: Event description
            location: Event location (Calendar only)
            reminder_minutes: Minutes before to send reminder
            recurrence: Recurrence rule (e.g., "RRULE:FREQ=DAILY")
            attendees: List of attendee emails (Calendar only)
            **kwargs: Provider-specific arguments

        Returns:
            SchedulerEvent representing the created event

        Raises:
            ValueError: If required fields are missing
            ProviderError: If provider API fails
        """
        pass

    @abstractmethod
    async def list_events(
        self,
        start: datetime,
        end: datetime,
        query: Optional[str] = None,
        max_results: int = 50,
        **kwargs
    ) -> List[SchedulerEvent]:
        """
        List events within a time range.

        Args:
            start: Start of time range
            end: End of time range
            query: Optional search query
            max_results: Maximum number of events to return
            **kwargs: Provider-specific arguments

        Returns:
            List of SchedulerEvent objects
        """
        pass

    @abstractmethod
    async def get_event(self, event_id: str) -> Optional[SchedulerEvent]:
        """
        Get a specific event by ID.

        Args:
            event_id: Provider-specific event ID

        Returns:
            SchedulerEvent if found, None otherwise
        """
        pass

    @abstractmethod
    async def update_event(
        self,
        event_id: str,
        title: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        status: Optional[SchedulerEventStatus] = None,
        **kwargs
    ) -> SchedulerEvent:
        """
        Update an existing event.

        Args:
            event_id: Provider-specific event ID
            title: New title (if changing)
            start: New start time (if changing)
            end: New end time (if changing)
            description: New description (if changing)
            location: New location (if changing)
            status: New status (if changing)
            **kwargs: Provider-specific arguments

        Returns:
            Updated SchedulerEvent

        Raises:
            ValueError: If event not found
            ProviderError: If provider API fails
        """
        pass

    @abstractmethod
    async def delete_event(self, event_id: str) -> bool:
        """
        Delete/cancel an event.

        Args:
            event_id: Provider-specific event ID

        Returns:
            True if deleted successfully, False otherwise
        """
        pass

    async def check_availability(
        self,
        start: datetime,
        end: datetime,
        emails: Optional[List[str]] = None
    ) -> bool:
        """
        Check if a time slot is available.

        Default implementation returns True (available).
        Override in providers that support free/busy queries.

        Args:
            start: Start of time slot
            end: End of time slot
            emails: Optional list of emails to check (Calendar only)

        Returns:
            True if time slot is available
        """
        if not self.supports_availability:
            self._logger.warning(
                f"{self.provider_name} does not support availability checking, assuming available"
            )
            return True
        return True

    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """
        Check provider health and connectivity.

        Returns:
            Dict with health status:
            {
                "status": "healthy" | "degraded" | "unavailable",
                "provider": provider_type,
                "details": {...provider-specific details...},
                "last_check": datetime (ISO format)
            }
        """
        pass

    def get_capabilities(self) -> Dict[str, bool]:
        """
        Get provider capabilities.

        Returns:
            Dict of feature flags indicating what the provider supports
        """
        return {
            "end_time": self.supports_end_time,
            "location": self.supports_location,
            "attendees": self.supports_attendees,
            "recurrence": self.supports_recurrence,
            "reminders": self.supports_reminders,
            "availability": self.supports_availability,
        }

    def get_permissions(self) -> Dict[str, bool]:
        """
        Get current permission configuration for this provider.

        Returns:
            Dict with permission flags:
            {
                "read": bool,   # Can view/list events
                "write": bool   # Can create/update/delete events
            }
        """
        return self._permissions.copy()

    def _check_permission(self, operation: str) -> None:
        """
        Check if current configuration allows the requested operation.

        Args:
            operation: Operation type - 'read' or 'write'

        Raises:
            PermissionDeniedError: If permission is not granted

        Permission Model:
            - READ: list_events, get_event
            - WRITE: create_event, update_event, delete_event
        """
        if operation not in ["read", "write"]:
            raise ValueError(f"Invalid operation type: {operation}. Must be 'read' or 'write'")

        if not self._permissions.get(operation, False):
            operation_descriptions = {
                "read": "view calendar events",
                "write": "create, update, or delete calendar events"
            }
            raise PermissionDeniedError(
                provider_type=self.provider_type.value,
                operation=operation,
                message=f"Permission denied: This agent does not have permission to {operation_descriptions[operation]}. "
                        f"Please contact your administrator to enable {operation} access."
            )

    def _log_info(self, message: str) -> None:
        """Log info message with provider context."""
        self._logger.info(f"[{self.provider_type.value}] {message}")

    def _log_error(self, message: str, exc_info: bool = False) -> None:
        """Log error message with provider context."""
        self._logger.error(f"[{self.provider_type.value}] {message}", exc_info=exc_info)

    def _log_warning(self, message: str) -> None:
        """Log warning message with provider context."""
        self._logger.warning(f"[{self.provider_type.value}] {message}")

    def _log_debug(self, message: str) -> None:
        """Log debug message with provider context."""
        self._logger.debug(f"[{self.provider_type.value}] {message}")


class SchedulerProviderError(Exception):
    """Base exception for scheduler provider errors."""
    pass


class ProviderNotConfiguredError(SchedulerProviderError):
    """Raised when a provider is requested but not configured."""
    def __init__(self, provider_type: str, message: str = None):
        self.provider_type = provider_type
        super().__init__(message or f"Provider '{provider_type}' is not configured")


class ProviderAuthenticationError(SchedulerProviderError):
    """Raised when provider authentication fails."""
    pass


class ProviderAPIError(SchedulerProviderError):
    """Raised when provider API returns an error."""
    def __init__(self, provider_type: str, message: str, status_code: Optional[int] = None):
        self.provider_type = provider_type
        self.status_code = status_code
        super().__init__(f"[{provider_type}] API Error: {message}")


class PermissionDeniedError(SchedulerProviderError):
    """
    Raised when an operation is attempted without proper permissions.

    Used for granular permission control (e.g., read-only vs full access).
    """
    def __init__(self, provider_type: str, operation: str, message: str = None):
        self.provider_type = provider_type
        self.operation = operation
        default_message = f"Permission denied for operation '{operation}' on provider '{provider_type}'"
        super().__init__(message or default_message)
