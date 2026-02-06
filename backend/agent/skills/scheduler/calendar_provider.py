"""
Google Calendar Provider

Scheduler provider implementation for Google Calendar.
Converts between the unified SchedulerEvent model and Google Calendar API format.

Features:
- Create calendar events
- List events with filtering
- Update events
- Delete events
- Free/busy availability checking
- Recurring events support
- Multiple attendees support
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
import os

from sqlalchemy.orm import Session

from .base import (
    SchedulerProviderBase,
    SchedulerEvent,
    SchedulerProviderType,
    SchedulerEventStatus,
    SchedulerProviderError,
    ProviderAuthenticationError,
    ProviderAPIError,
    PermissionDeniedError,
)

logger = logging.getLogger(__name__)


class GoogleCalendarProvider(SchedulerProviderBase):
    """
    Google Calendar scheduler provider.

    Uses CalendarService to interact with Google Calendar API and
    converts between the unified SchedulerEvent model and Google's format.

    Features:
        - Full calendar event CRUD
        - Free/busy availability checking
        - Recurring events
        - Attendee management
        - Location support
        - Timezone handling

    Example:
        provider = GoogleCalendarProvider(
            db=db_session,
            tenant_id="tenant_123",
            integration_id=5
        )

        # Create an event
        event = await provider.create_event(
            title="Team Meeting",
            start=datetime(2025, 1, 15, 14, 0),
            end=datetime(2025, 1, 15, 15, 0),
            location="Conference Room A",
            attendees=["john@example.com"]
        )
    """

    provider_type = SchedulerProviderType.GOOGLE_CALENDAR
    provider_name = "Google Calendar"
    provider_description = "Google Calendar events and meetings"

    # Feature flags
    supports_end_time = True
    supports_location = True
    supports_attendees = True
    supports_recurrence = True
    supports_reminders = True
    supports_availability = True

    def __init__(
        self,
        db: Session,
        tenant_id: Optional[str] = None,
        integration_id: Optional[int] = None,
        config: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Initialize Google Calendar provider.

        Args:
            db: Database session
            tenant_id: Tenant ID for multi-tenant isolation
            integration_id: CalendarIntegration ID (required)
            config: Optional configuration including permissions
        """
        super().__init__(db, tenant_id, config)

        if not integration_id:
            raise ValueError("GoogleCalendarProvider requires integration_id")

        self.integration_id = integration_id
        self._service = None

    def _get_service(self):
        """Lazy-load CalendarService."""
        if self._service is None:
            from hub.google.calendar_service import CalendarService
            self._service = CalendarService(self.db, self.integration_id)
        return self._service

    def _google_event_to_scheduler_event(self, google_event: Dict) -> SchedulerEvent:
        """
        Convert Google Calendar event to SchedulerEvent.

        Args:
            google_event: Event dict from Google Calendar API

        Returns:
            SchedulerEvent with mapped fields
        """
        # Parse start/end times
        start_data = google_event.get("start", {})
        end_data = google_event.get("end", {})

        # Handle all-day vs timed events
        is_all_day = "date" in start_data

        if is_all_day:
            start = datetime.strptime(start_data["date"], "%Y-%m-%d")
            end = datetime.strptime(end_data["date"], "%Y-%m-%d") if end_data.get("date") else None
        else:
            # Parse dateTime (can include timezone)
            start_str = start_data.get("dateTime", "")
            end_str = end_data.get("dateTime", "")

            # Remove timezone suffix for parsing
            if start_str:
                if "+" in start_str:
                    start_str = start_str.rsplit("+", 1)[0]
                elif start_str.endswith("Z"):
                    start_str = start_str[:-1]
                start = datetime.fromisoformat(start_str)
            else:
                start = datetime.utcnow()

            if end_str:
                if "+" in end_str:
                    end_str = end_str.rsplit("+", 1)[0]
                elif end_str.endswith("Z"):
                    end_str = end_str[:-1]
                end = datetime.fromisoformat(end_str)
            else:
                end = None

        # Map status
        google_status = google_event.get("status", "confirmed")
        status_map = {
            "confirmed": SchedulerEventStatus.SCHEDULED,
            "tentative": SchedulerEventStatus.SCHEDULED,
            "cancelled": SchedulerEventStatus.CANCELLED,
        }
        status = status_map.get(google_status, SchedulerEventStatus.SCHEDULED)

        # Extract attendees
        attendees = [
            a.get("email")
            for a in google_event.get("attendees", [])
            if a.get("email")
        ]

        # Extract reminder
        reminders = google_event.get("reminders", {})
        reminder_minutes = None
        if not reminders.get("useDefault", True):
            overrides = reminders.get("overrides", [])
            if overrides:
                reminder_minutes = overrides[0].get("minutes")

        # Build recurrence string
        recurrence = None
        recurrence_rules = google_event.get("recurrence", [])
        if recurrence_rules:
            recurrence = recurrence_rules[0]  # Take first RRULE

        return SchedulerEvent(
            id=f"gcal_{google_event['id']}",
            provider=self.provider_type.value,
            title=google_event.get("summary", "Untitled"),
            start=start,
            end=end,
            description=google_event.get("description"),
            location=google_event.get("location"),
            is_all_day=is_all_day,
            status=status,
            recurrence=recurrence,
            reminder_minutes=reminder_minutes,
            attendees=attendees,
            raw_data=google_event,
            metadata={
                "calendar_id": google_event.get("calendarId"),
                "html_link": google_event.get("htmlLink"),
                "creator": google_event.get("creator", {}).get("email"),
                "organizer": google_event.get("organizer", {}).get("email"),
            }
        )

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
        Create a Google Calendar event.

        Args:
            title: Event title
            start: Event start time
            end: Event end time (defaults to start + 1 hour)
            description: Event description
            location: Event location
            reminder_minutes: Minutes before to remind
            recurrence: RRULE string for recurring events
            attendees: List of attendee emails

        Returns:
            SchedulerEvent representing the created event

        Raises:
            PermissionDeniedError: If write permission is not granted
        """
        # Check write permission
        self._check_permission("write")

        self._log_info(f"Creating Google Calendar event: {title}")

        # #region agent log
        import time
        import json as json_lib
        try:
            with open('/app/.cursor/debug.log', 'a') as f:
                f.write(json_lib.dumps({
                    'location': 'calendar_provider.py:247',
                    'message': 'GoogleCalendarProvider.create_event ENTRY',
                    'data': {
                        'title': title,
                        'start': start.isoformat(),
                        'end': end.isoformat() if end else None,
                        'recurrence': recurrence
                    },
                    'timestamp': time.time() * 1000,
                    'sessionId': 'debug-session',
                    'hypothesisId': 'H3,H4'
                }) + '\n')
        except:
            pass
        # #endregion

        try:
            service = self._get_service()

            # Convert RRULE string to list
            recurrence_list = [recurrence] if recurrence else None

            google_event = await service.create_event(
                summary=title,
                start=start,
                end=end,
                description=description,
                location=location,
                attendees=attendees,
                reminder_minutes=reminder_minutes,
                recurrence=recurrence_list
            )

            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'calendar_provider.py:281',
                        'message': 'Got google_event from service',
                        'data': {
                            'google_event_type': type(google_event).__name__,
                            'google_event_keys': list(google_event.keys()) if isinstance(google_event, dict) else None,
                            'google_event_id': google_event.get('id') if isinstance(google_event, dict) else None,
                            'google_event': str(google_event)[:500]
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H1,H3'
                    }) + '\n')
            except:
                pass
            # #endregion

            event = self._google_event_to_scheduler_event(google_event)

            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'calendar_provider.py:301',
                        'message': 'Converted to SchedulerEvent',
                        'data': {
                            'event_id': event.id,
                            'event_title': event.title,
                            'event_start': event.start.isoformat(),
                            'event_metadata': event.metadata
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H1,H3'
                    }) + '\n')
            except:
                pass
            # #endregion

            self._log_info(f"Created event: {event.id}")

            return event

        except Exception as e:
            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'calendar_provider.py:324',
                        'message': 'Exception in create_event',
                        'data': {
                            'exception_type': type(e).__name__,
                            'exception_str': str(e)[:500]
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H5'
                    }) + '\n')
            except:
                pass
            # #endregion
            self._log_error(f"Failed to create event: {e}", exc_info=True)
            raise ProviderAPIError(
                self.provider_type.value,
                f"Failed to create calendar event: {e}"
            )

    async def list_events(
        self,
        start: datetime,
        end: datetime,
        query: Optional[str] = None,
        max_results: int = 50,
        **kwargs
    ) -> List[SchedulerEvent]:
        """
        List Google Calendar events within a time range.

        Args:
            start: Start of time range
            end: End of time range
            query: Optional search query
            max_results: Maximum events to return

        Returns:
            List of SchedulerEvent objects

        Raises:
            PermissionDeniedError: If read permission is not granted
        """
        # Check read permission
        self._check_permission("read")

        self._log_info(f"Listing events from {start} to {end}")

        try:
            service = self._get_service()

            google_events = await service.list_events(
                start=start,
                end=end,
                query=query,
                max_results=max_results
            )

            events = [
                self._google_event_to_scheduler_event(e)
                for e in google_events
            ]

            self._log_info(f"Found {len(events)} events")
            return events

        except Exception as e:
            self._log_error(f"Failed to list events: {e}", exc_info=True)
            raise ProviderAPIError(
                self.provider_type.value,
                f"Failed to list calendar events: {e}"
            )

    async def get_event(self, event_id: str) -> Optional[SchedulerEvent]:
        """
        Get a specific event by ID.

        Args:
            event_id: Event ID (format: "gcal_xxx" or just "xxx")

        Returns:
            SchedulerEvent if found, None otherwise

        Raises:
            PermissionDeniedError: If read permission is not granted
        """
        # Check read permission
        self._check_permission("read")

        # Extract Google event ID
        if event_id.startswith("gcal_"):
            google_id = event_id[5:]
        else:
            google_id = event_id

        try:
            service = self._get_service()
            google_event = await service.get_event(google_id)

            if google_event:
                return self._google_event_to_scheduler_event(google_event)
            return None

        except Exception as e:
            self._log_error(f"Failed to get event {event_id}: {e}", exc_info=True)
            return None

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
        Update a Google Calendar event.

        Args:
            event_id: Event ID to update
            title: New title
            start: New start time
            end: New end time
            description: New description
            location: New location
            status: New status (cancelled = delete)

        Returns:
            Updated SchedulerEvent

        Raises:
            PermissionDeniedError: If write permission is not granted
        """
        # Check write permission
        self._check_permission("write")

        # Extract Google event ID
        if event_id.startswith("gcal_"):
            google_id = event_id[5:]
        else:
            google_id = event_id

        self._log_info(f"Updating event {google_id}")

        try:
            service = self._get_service()

            # Handle cancellation as delete
            if status == SchedulerEventStatus.CANCELLED:
                await service.delete_event(google_id)
                # Return a cancelled event
                return SchedulerEvent(
                    id=event_id,
                    provider=self.provider_type.value,
                    title=title or "Cancelled",
                    start=start or datetime.utcnow(),
                    status=SchedulerEventStatus.CANCELLED
                )

            # Regular update
            google_event = await service.update_event(
                event_id=google_id,
                summary=title,
                start=start,
                end=end,
                description=description,
                location=location,
                attendees=kwargs.get("attendees")
            )

            return self._google_event_to_scheduler_event(google_event)

        except Exception as e:
            self._log_error(f"Failed to update event: {e}", exc_info=True)
            raise ProviderAPIError(
                self.provider_type.value,
                f"Failed to update calendar event: {e}"
            )

    async def delete_event(self, event_id: str) -> bool:
        """
        Delete a Google Calendar event.

        Args:
            event_id: Event ID to delete

        Returns:
            True if deleted successfully

        Raises:
            PermissionDeniedError: If write permission is not granted
        """
        # Check write permission
        self._check_permission("write")

        # Extract Google event ID
        if event_id.startswith("gcal_"):
            google_id = event_id[5:]
        else:
            google_id = event_id

        self._log_info(f"Deleting event {google_id}")

        try:
            service = self._get_service()
            return await service.delete_event(google_id)
        except Exception as e:
            self._log_error(f"Failed to delete event: {e}", exc_info=True)
            return False

    async def check_availability(
        self,
        start: datetime,
        end: datetime,
        emails: Optional[List[str]] = None
    ) -> bool:
        """
        Check if a time slot is available.

        Args:
            start: Start of time slot
            end: End of time slot
            emails: Optional list of attendee emails to check

        Returns:
            True if time slot is available
        """
        try:
            service = self._get_service()
            return await service.is_time_available(start, end)
        except Exception as e:
            self._log_error(f"Failed to check availability: {e}", exc_info=True)
            # Default to available on error
            return True

    async def check_health(self) -> Dict[str, Any]:
        """
        Check Google Calendar provider health.

        Returns:
            Health status dict
        """
        try:
            service = self._get_service()
            health = await service.check_health()

            return {
                "status": health["status"],
                "provider": self.provider_type.value,
                "provider_name": self.provider_name,
                "last_check": health["last_check"],
                "details": health.get("details", {}),
                "errors": health.get("errors", [])
            }
        except Exception as e:
            return {
                "status": "unavailable",
                "provider": self.provider_type.value,
                "provider_name": self.provider_name,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "errors": [str(e)]
            }
