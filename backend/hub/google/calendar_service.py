"""
Google Calendar Service

Provides Google Calendar API integration through HubIntegrationBase.
Supports creating, listing, updating, and deleting calendar events.

Features:
- Full calendar CRUD operations
- Free/busy availability checking
- Recurring events support
- Multiple calendar support
- Timezone handling

Required Google Calendar API Scopes:
- https://www.googleapis.com/auth/calendar (full access)
- https://www.googleapis.com/auth/calendar.events (events only)
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from hub.base import (
    HubIntegrationBase,
    IntegrationHealthStatus,
    TokenExpiredError,
    RateLimitError,
)
from hub.security import TokenEncryption
from models import CalendarIntegration, OAuthToken, HubIntegration

logger = logging.getLogger(__name__)


class CalendarService(HubIntegrationBase):
    """
    Google Calendar API service.

    Provides calendar management operations for the scheduler provider system.
    Each CalendarService instance is tied to a specific CalendarIntegration.

    Example:
        service = CalendarService(db, integration_id)

        # List events
        events = await service.list_events(
            start=datetime.now(),
            end=datetime.now() + timedelta(days=7)
        )

        # Create event
        event = await service.create_event(
            summary="Team Meeting",
            start=datetime(2025, 1, 15, 14, 0),
            end=datetime(2025, 1, 15, 15, 0)
        )
    """

    # Google Calendar API base URL
    BASE_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(
        self,
        db: Session,
        integration_id: int,
        encryption_key: Optional[str] = None
    ):
        """
        Initialize Calendar service.

        Args:
            db: Database session
            integration_id: CalendarIntegration ID
            encryption_key: Token encryption key (defaults to env var)
        """
        super().__init__(db, integration_id)

        if not encryption_key:
            from services.encryption_key_service import get_google_encryption_key
            encryption_key = get_google_encryption_key(db)

        self._encryption_key = encryption_key
        if not self._encryption_key:
            raise ValueError("GOOGLE_ENCRYPTION_KEY not configured in database or environment")

        self._token_encryption = TokenEncryption(self._encryption_key.encode())
        self._integration: Optional[CalendarIntegration] = None
        self._metrics = {
            "requests_total": 0,
            "requests_failed": 0,
            "requests_duration_seconds": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def _get_integration(self) -> CalendarIntegration:
        """Get the calendar integration."""
        if self._integration is None:
            self._integration = self.db.query(CalendarIntegration).filter(
                CalendarIntegration.id == self.integration_id
            ).first()

            if not self._integration:
                raise ValueError(f"Calendar integration {self.integration_id} not found")

        return self._integration

    async def _get_access_token(self) -> str:
        """
        Get valid access token, refreshing if needed.

        Returns:
            Valid access token

        Raises:
            TokenExpiredError: If token cannot be refreshed
        """
        integration = self._get_integration()

        # Get token from database
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == self.integration_id
        ).order_by(OAuthToken.created_at.desc()).first()

        if not token:
            raise TokenExpiredError(f"No token found for integration {self.integration_id}")

        # Check if expired
        now = datetime.utcnow()
        buffer = timedelta(minutes=5)

        if token.expires_at < now + buffer:
            # Need to refresh
            self._log_info("Token expired, refreshing...")
            success = await self.refresh_tokens()
            if not success:
                raise TokenExpiredError("Token refresh failed")

            # Reload token
            token = self.db.query(OAuthToken).filter(
                OAuthToken.integration_id == self.integration_id
            ).order_by(OAuthToken.created_at.desc()).first()

        # Decrypt and return
        return self._token_encryption.decrypt(
            token.access_token_encrypted,
            integration.email_address
        )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None
    ) -> Dict:
        """
        Make authenticated request to Google Calendar API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint (relative to BASE_URL)
            params: Query parameters
            json_data: JSON body data

        Returns:
            API response as dict

        Raises:
            TokenExpiredError: If authentication fails
            RateLimitError: If rate limited
        """
        import time
        import json as json_lib
        start_time = time.time()
        self._metrics["requests_total"] += 1

        # #region agent log
        try:
            with open('/Users/vinicios/code/tsushin/.cursor/debug.log', 'a') as f:
                f.write(json_lib.dumps({
                    'location': 'calendar_service.py:177',
                    'message': '_make_request ENTRY',
                    'data': {
                        'method': method,
                        'endpoint': endpoint,
                        'has_json_data': json_data is not None,
                        'json_data_keys': list(json_data.keys()) if json_data else None
                    },
                    'timestamp': time.time() * 1000,
                    'sessionId': 'debug-session',
                    'hypothesisId': 'H1,H4'
                }) + '\n')
        except:
            pass
        # #endregion

        try:
            access_token = await self._get_access_token()

            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'calendar_service.py:198',
                        'message': 'Got access token',
                        'data': {
                            'token_length': len(access_token) if access_token else 0,
                            'token_prefix': access_token[:20] if access_token else None
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H2'
                    }) + '\n')
            except:
                pass
            # #endregion

            url = f"{self.BASE_URL}{endpoint}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'calendar_service.py:222',
                        'message': 'About to make HTTP request',
                        'data': {
                            'url': url,
                            'method': method,
                            'json_data': str(json_data)[:500] if json_data else None
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H1,H3,H4'
                    }) + '\n')
            except:
                pass
            # #endregion

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers=headers
                )

                # #region agent log
                try:
                    with open('/app/.cursor/debug.log', 'a') as f:
                        f.write(json_lib.dumps({
                            'location': 'calendar_service.py:244',
                            'message': 'HTTP response received',
                            'data': {
                                'status_code': response.status_code,
                                'response_text': response.text[:1000] if response.text else None,
                                'content_type': response.headers.get('content-type')
                            },
                            'timestamp': time.time() * 1000,
                            'sessionId': 'debug-session',
                            'hypothesisId': 'H1,H2,H4'
                        }) + '\n')
                except:
                    pass
                # #endregion

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    self._metrics["requests_failed"] += 1
                    # #region agent log
                    try:
                        with open('/app/.cursor/debug.log', 'a') as f:
                            f.write(json_lib.dumps({
                                'location': 'calendar_service.py:265',
                                'message': 'Rate limit error',
                                'data': {'retry_after': retry_after},
                                'timestamp': time.time() * 1000,
                                'sessionId': 'debug-session',
                                'hypothesisId': 'H1'
                            }) + '\n')
                    except:
                        pass
                    # #endregion
                    raise RateLimitError(
                        "Google Calendar API rate limit exceeded",
                        retry_after=retry_after
                    )

                # Handle auth errors
                if response.status_code == 401:
                    self._metrics["requests_failed"] += 1
                    # #region agent log
                    try:
                        with open('/app/.cursor/debug.log', 'a') as f:
                            f.write(json_lib.dumps({
                                'location': 'calendar_service.py:285',
                                'message': 'Auth error 401',
                                'data': {'response': response.text[:500]},
                                'timestamp': time.time() * 1000,
                                'sessionId': 'debug-session',
                                'hypothesisId': 'H2'
                            }) + '\n')
                    except:
                        pass
                    # #endregion
                    raise TokenExpiredError("Google Calendar authentication failed")

                response.raise_for_status()

                # Empty response for DELETE
                if response.status_code == 204:
                    return {}

                result = response.json()

                # #region agent log
                try:
                    with open('/app/.cursor/debug.log', 'a') as f:
                        f.write(json_lib.dumps({
                            'location': 'calendar_service.py:309',
                            'message': '_make_request SUCCESS',
                            'data': {
                                'response_keys': list(result.keys()) if isinstance(result, dict) else None,
                                'event_id': result.get('id') if isinstance(result, dict) else None,
                                'response': str(result)[:500]
                            },
                            'timestamp': time.time() * 1000,
                            'sessionId': 'debug-session',
                            'hypothesisId': 'H1,H3'
                        }) + '\n')
                except:
                    pass
                # #endregion

                return result

        except (TokenExpiredError, RateLimitError):
            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'calendar_service.py:333',
                        'message': 'Token or RateLimit exception',
                        'data': {'exception_type': type(e).__name__ if 'e' in locals() else 'unknown'},
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H1,H2'
                    }) + '\n')
            except:
                pass
            # #endregion
            raise
        except Exception as e:
            self._metrics["requests_failed"] += 1
            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'calendar_service.py:349',
                        'message': 'Generic exception in _make_request',
                        'data': {
                            'exception_type': type(e).__name__,
                            'exception_str': str(e)[:500]
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H1,H5'
                    }) + '\n')
            except:
                pass
            # #endregion
            self._log_error(f"API request failed: {e}", exc_info=True)
            raise
        finally:
            duration = time.time() - start_time
            self._metrics["requests_duration_seconds"] += duration

    # ========================================
    # Calendar Events API
    # ========================================

    async def list_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: Optional[str] = None,
        query: Optional[str] = None,
        max_results: int = 50,
        single_events: bool = True
    ) -> List[Dict]:
        """
        List calendar events within a time range.

        Args:
            start: Start of time range (UTC or timezone-aware)
            end: End of time range
            calendar_id: Calendar ID (defaults to integration's default)
            query: Optional search query
            max_results: Maximum events to return
            single_events: If True, expand recurring events

        Returns:
            List of event dicts
        """
        integration = self._get_integration()
        calendar_id = calendar_id or integration.default_calendar_id or "primary"

        params = {
            "timeMin": start.isoformat() + "Z" if not start.tzinfo else start.isoformat(),
            "timeMax": end.isoformat() + "Z" if not end.tzinfo else end.isoformat(),
            "maxResults": max_results,
            "singleEvents": str(single_events).lower(),
            "orderBy": "startTime" if single_events else "updated",
        }

        if query:
            params["q"] = query

        self._log_info(f"Listing events from {calendar_id}: {start} to {end}")

        response = await self._make_request(
            "GET",
            f"/calendars/{calendar_id}/events",
            params=params
        )

        events = response.get("items", [])
        self._log_info(f"Found {len(events)} events")

        return events

    async def get_event(
        self,
        event_id: str,
        calendar_id: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Get a specific event by ID.

        Args:
            event_id: Google Calendar event ID
            calendar_id: Calendar ID

        Returns:
            Event dict or None if not found
        """
        integration = self._get_integration()
        calendar_id = calendar_id or integration.default_calendar_id or "primary"

        try:
            return await self._make_request(
                "GET",
                f"/calendars/{calendar_id}/events/{event_id}"
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def create_event(
        self,
        summary: str,
        start: datetime,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        reminder_minutes: Optional[int] = None,
        recurrence: Optional[List[str]] = None,
        calendar_id: Optional[str] = None,
        timezone: Optional[str] = None,
        all_day: bool = False
    ) -> Dict:
        """
        Create a new calendar event.

        Args:
            summary: Event title
            start: Event start time
            end: Event end time (defaults to start + 1 hour)
            description: Event description
            location: Event location
            attendees: List of attendee emails
            reminder_minutes: Minutes before to remind
            recurrence: RRULE strings for recurring events
            calendar_id: Calendar ID
            timezone: Timezone (defaults to integration's timezone)
            all_day: If True, create all-day event

        Returns:
            Created event dict
        """
        integration = self._get_integration()
        calendar_id = calendar_id or integration.default_calendar_id or "primary"
        timezone = timezone or integration.timezone or "America/Sao_Paulo"

        # DEBUG: Log what we received
        self._log_info(f"create_event called with: start={start}, end={end}, summary={summary}")

        # Build event body
        if all_day:
            event_body = {
                "summary": summary,
                "start": {"date": start.strftime("%Y-%m-%d")},
                "end": {"date": (end or start + timedelta(days=1)).strftime("%Y-%m-%d")},
            }
        else:
            end_provided = end
            end = end or (start + timedelta(hours=1))
            self._log_info(f"Using end time: {end} (was provided: {end_provided is not None})")
            event_body = {
                "summary": summary,
                "start": {
                    "dateTime": start.isoformat(),
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": end.isoformat(),
                    "timeZone": timezone,
                },
            }

        if description:
            event_body["description"] = description

        if location:
            event_body["location"] = location

        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]

        if reminder_minutes is not None:
            event_body["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": reminder_minutes}
                ]
            }

        if recurrence:
            event_body["recurrence"] = recurrence

        self._log_info(f"Creating event '{summary}' at {start}")

        return await self._make_request(
            "POST",
            f"/calendars/{calendar_id}/events",
            json_data=event_body
        )

    async def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        calendar_id: Optional[str] = None,
        timezone: Optional[str] = None
    ) -> Dict:
        """
        Update an existing event.

        Args:
            event_id: Event ID to update
            summary: New title (if changing)
            start: New start time (if changing)
            end: New end time (if changing)
            description: New description (if changing)
            location: New location (if changing)
            attendees: New attendees list (if changing)
            calendar_id: Calendar ID
            timezone: Timezone for datetime fields

        Returns:
            Updated event dict
        """
        integration = self._get_integration()
        calendar_id = calendar_id or integration.default_calendar_id or "primary"
        timezone = timezone or integration.timezone or "America/Sao_Paulo"

        # Get existing event
        existing = await self.get_event(event_id, calendar_id)
        if not existing:
            raise ValueError(f"Event {event_id} not found")

        # Build update body
        event_body = {}

        if summary is not None:
            event_body["summary"] = summary

        if start is not None:
            event_body["start"] = {
                "dateTime": start.isoformat(),
                "timeZone": timezone,
            }

        if end is not None:
            event_body["end"] = {
                "dateTime": end.isoformat(),
                "timeZone": timezone,
            }

        if description is not None:
            event_body["description"] = description

        if location is not None:
            event_body["location"] = location

        if attendees is not None:
            event_body["attendees"] = [{"email": email} for email in attendees]

        self._log_info(f"Updating event {event_id}")

        return await self._make_request(
            "PATCH",
            f"/calendars/{calendar_id}/events/{event_id}",
            json_data=event_body
        )

    async def delete_event(
        self,
        event_id: str,
        calendar_id: Optional[str] = None
    ) -> bool:
        """
        Delete a calendar event.

        Args:
            event_id: Event ID to delete
            calendar_id: Calendar ID

        Returns:
            True if deleted successfully
        """
        integration = self._get_integration()
        calendar_id = calendar_id or integration.default_calendar_id or "primary"

        self._log_info(f"Deleting event {event_id}")

        try:
            await self._make_request(
                "DELETE",
                f"/calendars/{calendar_id}/events/{event_id}"
            )
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                self._log_warning(f"Event {event_id} not found for deletion")
                return False
            raise

    async def check_freebusy(
        self,
        start: datetime,
        end: datetime,
        calendar_ids: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        """
        Check free/busy status for calendars.

        Args:
            start: Start of time range
            end: End of time range
            calendar_ids: List of calendar IDs to check

        Returns:
            Dict mapping calendar ID to list of busy periods:
            {
                "primary": [
                    {"start": "...", "end": "..."},
                    ...
                ]
            }
        """
        integration = self._get_integration()
        calendar_ids = calendar_ids or [integration.default_calendar_id or "primary"]

        request_body = {
            "timeMin": start.isoformat() + "Z" if not start.tzinfo else start.isoformat(),
            "timeMax": end.isoformat() + "Z" if not end.tzinfo else end.isoformat(),
            "items": [{"id": cal_id} for cal_id in calendar_ids],
        }

        self._log_info(f"Checking free/busy: {start} to {end}")

        response = await self._make_request(
            "POST",
            "/freeBusy",
            json_data=request_body
        )

        result = {}
        calendars = response.get("calendars", {})
        for cal_id, data in calendars.items():
            result[cal_id] = data.get("busy", [])

        return result

    async def is_time_available(
        self,
        start: datetime,
        end: datetime,
        calendar_id: Optional[str] = None
    ) -> bool:
        """
        Check if a time slot is available.

        Args:
            start: Start of time slot
            end: End of time slot
            calendar_id: Calendar ID

        Returns:
            True if time slot is free
        """
        integration = self._get_integration()
        calendar_id = calendar_id or integration.default_calendar_id or "primary"

        freebusy = await self.check_freebusy(start, end, [calendar_id])
        busy_periods = freebusy.get(calendar_id, [])

        return len(busy_periods) == 0

    async def list_calendars(self) -> List[Dict]:
        """
        List all calendars accessible to the user.

        Returns:
            List of calendar dicts with id, summary, primary, etc.
        """
        response = await self._make_request("GET", "/users/me/calendarList")
        return response.get("items", [])

    # ========================================
    # HubIntegrationBase Implementation
    # ========================================

    async def check_health(self) -> Dict[str, Any]:
        """Check Calendar API health."""
        try:
            integration = self._get_integration()

            # Try listing calendars as health check
            calendars = await self.list_calendars()

            # Get token expiration
            token = self.db.query(OAuthToken).filter(
                OAuthToken.integration_id == self.integration_id
            ).first()

            token_expires_at = token.expires_at.isoformat() + "Z" if token else None

            return {
                "status": IntegrationHealthStatus.HEALTHY,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {
                    "token_expires_at": token_expires_at,
                    "api_reachable": True,
                    "calendars_accessible": len(calendars),
                    "email": integration.email_address,
                },
                "errors": []
            }

        except TokenExpiredError as e:
            return {
                "status": IntegrationHealthStatus.UNAVAILABLE,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {},
                "errors": [str(e)]
            }
        except Exception as e:
            return {
                "status": IntegrationHealthStatus.DEGRADED,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {},
                "errors": [str(e)]
            }

    async def refresh_tokens(self) -> bool:
        """Refresh OAuth tokens."""
        from hub.google.oauth_handler import get_google_oauth_handler

        try:
            integration = self._get_integration()

            # Get tenant_id from base integration
            base = self.db.query(HubIntegration).filter(
                HubIntegration.id == self.integration_id
            ).first()

            if not base or not base.tenant_id:
                self._log_error("Cannot refresh token: tenant_id not found")
                return False

            handler = get_google_oauth_handler(
                self.db,
                base.tenant_id,
                self._encryption_key
            )

            new_token = await handler.refresh_access_token(
                self.integration_id,
                integration.email_address
            )

            return new_token is not None

        except Exception as e:
            self._log_error(f"Token refresh failed: {e}", exc_info=True)
            return False

    async def revoke_access(self) -> None:
        """Revoke OAuth access."""
        from hub.google.oauth_handler import get_google_oauth_handler

        integration = self._get_integration()
        base = self.db.query(HubIntegration).filter(
            HubIntegration.id == self.integration_id
        ).first()

        if base and base.tenant_id:
            handler = get_google_oauth_handler(
                self.db,
                base.tenant_id,
                self._encryption_key
            )
            await handler.disconnect_integration(self.integration_id)
        else:
            # Just delete tokens and deactivate
            self.db.query(OAuthToken).filter(
                OAuthToken.integration_id == self.integration_id
            ).delete()

            if base:
                base.is_active = False

            self.db.commit()

    def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics."""
        integration = self._get_integration()

        # Get token expiration
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == self.integration_id
        ).first()

        token_expires_in = 0
        if token:
            delta = token.expires_at - datetime.utcnow()
            token_expires_in = max(0, int(delta.total_seconds()))

        return {
            **self._metrics,
            "token_expires_in_seconds": token_expires_in,
            "calendar_id": integration.default_calendar_id,
            "email": integration.email_address,
        }
