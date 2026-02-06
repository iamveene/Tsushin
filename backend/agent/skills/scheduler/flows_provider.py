"""
Flows Provider - Built-in Scheduler Provider

Wraps the existing Flows/Scheduler system to provide a consistent interface
for the unified scheduler skill. This is the default provider.

Features:
- Single-message reminders (NOTIFICATION)
- AI-driven multi-turn conversations (CONVERSATION)
- Recurrence support (daily, weekly, monthly)
- Contact resolution (@mentions, names)
- Brazil timezone handling (GMT-3)
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json
import logging
import pytz

from sqlalchemy.orm import Session

from .base import (
    SchedulerProviderBase,
    SchedulerEvent,
    SchedulerProviderType,
    SchedulerEventStatus,
    SchedulerProviderError,
)

logger = logging.getLogger(__name__)

# Brazil timezone (GMT-3)
BRAZIL_TZ = pytz.timezone('America/Sao_Paulo')


class FlowsProvider(SchedulerProviderBase):
    """
    Built-in Flows scheduler provider.

    Uses the existing SchedulerService and ScheduledEvent model to manage
    reminders, notifications, and AI-driven conversations.

    This is the default provider and requires no external integration setup.

    Supported event types:
        - NOTIFICATION: Single-message reminders sent to a recipient
        - CONVERSATION: Multi-turn AI conversations with objectives

    Features:
        - Natural language date/time parsing (Portuguese + English)
        - Contact resolution from @mentions and names
        - Recurrence rules (daily, weekly, monthly)
        - Brazil timezone (GMT-3) handling

    Example:
        provider = FlowsProvider(db, tenant_id="tenant_123")

        # Create a reminder
        event = await provider.create_event(
            title="Buy groceries",
            start=datetime(2025, 1, 15, 14, 0),
            description="Remember to buy milk and bread"
        )

        # List upcoming events
        events = await provider.list_events(
            start=datetime.now(),
            end=datetime.now() + timedelta(days=7)
        )
    """

    provider_type = SchedulerProviderType.FLOWS
    provider_name = "Built-in Flows"
    provider_description = "Built-in scheduling system for reminders and AI conversations"

    # Feature flags
    supports_end_time = False  # Flows uses scheduled_at only
    supports_location = False
    supports_attendees = False
    supports_recurrence = True
    supports_reminders = True
    supports_availability = False

    def __init__(self, db: Session, tenant_id: Optional[str] = None, agent_id: Optional[int] = None, config: Optional[Dict] = None):
        """
        Initialize Flows provider.

        Args:
            db: SQLAlchemy database session
            tenant_id: Tenant ID for multi-tenant isolation
            agent_id: Agent ID for event creation (optional)
            config: Optional configuration including permissions
        """
        super().__init__(db, tenant_id, config)
        self.agent_id = agent_id
        self._scheduler_service = None

    def _get_scheduler_service(self):
        """Lazy-load SchedulerService to avoid circular imports."""
        if self._scheduler_service is None:
            from scheduler.scheduler_service import SchedulerService
            self._scheduler_service = SchedulerService(self.db)
        return self._scheduler_service

    def _scheduled_event_to_scheduler_event(self, event) -> SchedulerEvent:
        """
        Convert a ScheduledEvent model to a SchedulerEvent dataclass.

        Args:
            event: ScheduledEvent model instance

        Returns:
            SchedulerEvent with mapped fields
        """
        # Parse payload
        payload = {}
        if event.payload:
            try:
                payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
            except json.JSONDecodeError:
                payload = {}

        # Map status
        status_map = {
            'PENDING': SchedulerEventStatus.SCHEDULED,
            'ACTIVE': SchedulerEventStatus.IN_PROGRESS,
            'COMPLETED': SchedulerEventStatus.COMPLETED,
            'CANCELLED': SchedulerEventStatus.CANCELLED,
            'FAILED': SchedulerEventStatus.FAILED,
        }
        status = status_map.get(event.status, SchedulerEventStatus.SCHEDULED)

        # Build title from payload
        if event.event_type == 'NOTIFICATION':
            title = payload.get('reminder_text', 'Reminder')
        elif event.event_type == 'CONVERSATION':
            title = payload.get('objective', 'Conversation')
        else:
            title = f"{event.event_type} Event"

        # Parse recurrence
        recurrence = None
        if event.recurrence_rule:
            try:
                recurrence_data = json.loads(event.recurrence_rule) if isinstance(event.recurrence_rule, str) else event.recurrence_rule
                freq = recurrence_data.get('frequency', 'daily').upper()
                interval = recurrence_data.get('interval', 1)
                recurrence = f"RRULE:FREQ={freq};INTERVAL={interval}"
            except:
                pass

        return SchedulerEvent(
            id=f"flows_{event.id}",
            provider=self.provider_type.value,
            title=title,
            start=event.scheduled_at,
            end=None,  # Flows doesn't have end times
            description=payload.get('reminder_text') or payload.get('objective'),
            status=status,
            recurrence=recurrence,
            raw_data={
                'event_type': event.event_type,
                'creator_type': event.creator_type,
                'creator_id': event.creator_id,
                'payload': payload,
            },
            metadata={
                'event_type': event.event_type,
                'recipient': payload.get('recipient_raw') or payload.get('recipient'),
                'agent_id': payload.get('agent_id'),
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
        event_type: str = 'NOTIFICATION',
        recipient: Optional[str] = None,
        **kwargs
    ) -> SchedulerEvent:
        """
        Create a new scheduled event in Flows.

        Args:
            title: Event title (used as reminder_text or objective)
            start: When to execute the event
            end: Ignored for Flows (no end times)
            description: Additional description (combined with title)
            location: Ignored for Flows
            reminder_minutes: Ignored for Flows (uses start time directly)
            recurrence: RRULE string for recurring events
            attendees: Ignored for Flows
            event_type: 'NOTIFICATION' or 'CONVERSATION' (default: NOTIFICATION)
            recipient: Who to send to (optional, for notifications)
            **kwargs: Additional provider-specific args

        Returns:
            SchedulerEvent representing the created event
        """
        self._log_info(f"Creating {event_type} event: {title}")

        scheduler_service = self._get_scheduler_service()

        # Determine agent_id
        agent_id = kwargs.get('agent_id') or self.agent_id or 1

        # Build payload based on event type
        if event_type.upper() == 'CONVERSATION':
            payload = {
                'agent_id': agent_id,
                'recipient': recipient,
                'objective': title,
                'context': {'created_by': 'scheduler_provider'},
                'max_turns': kwargs.get('max_turns', 20),
                'timeout_hours': kwargs.get('timeout_hours', 24),
            }
            if description:
                payload['context']['description'] = description
        else:
            # Default to NOTIFICATION
            event_type = 'NOTIFICATION'
            payload = {
                'agent_id': agent_id,
                'recipient_raw': recipient,
                'reminder_text': title,
                'message_template': kwargs.get('message_template', 'Reminder: {reminder_text}'),
            }
            if description:
                payload['reminder_text'] = f"{title} - {description}"

        # Parse recurrence rule from RRULE format
        recurrence_rule = None
        execution_method = 'immediate'  # Default
        start_time = None
        days_of_week = None

        if recurrence:
            # Parse RRULE format (e.g., "RRULE:FREQ=DAILY;INTERVAL=1" or "RRULE:FREQ=WEEKLY;BYDAY=MO")
            freq_match = recurrence.upper()

            if 'DAILY' in freq_match:
                recurrence_rule = {'frequency': 'daily', 'interval': 1, 'timezone': 'America/Sao_Paulo'}
                execution_method = 'recurring'
            elif 'WEEKLY' in freq_match:
                recurrence_rule = {'frequency': 'weekly', 'interval': 1, 'timezone': 'America/Sao_Paulo'}
                execution_method = 'recurring'

                # Extract BYDAY if present (e.g., BYDAY=MO)
                if 'BYDAY=' in freq_match:
                    day_abbr = freq_match.split('BYDAY=')[1].split(';')[0][:2]
                    day_map = {'MO': 1, 'TU': 2, 'WE': 3, 'TH': 4, 'FR': 5, 'SA': 6, 'SU': 7}
                    if day_abbr in day_map:
                        days_of_week = [day_map[day_abbr]]
                        recurrence_rule['days_of_week'] = days_of_week

            elif 'MONTHLY' in freq_match:
                recurrence_rule = {'frequency': 'monthly', 'interval': 1, 'timezone': 'America/Sao_Paulo'}
                execution_method = 'recurring'

            # Extract start time from scheduled_at for recurring events
            if start:
                start_time = start.strftime('%H:%M')
                recurrence_rule['start_time'] = start_time

        # For recurring events, create as FlowDefinition instead of ScheduledEvent
        # This allows the ScheduledFlowExecutor to handle the recurrence properly
        if execution_method == 'recurring':
            try:
                from models import FlowDefinition, FlowNode
                from flows.flow_creator_service import FlowCreatorService

                # Create a flow for recurring execution
                flow_name = f"{event_type.title()}: {title}"
                flow = FlowDefinition(
                    tenant_id=self.tenant_id,
                    name=flow_name,
                    description=description or title,
                    execution_method='recurring',
                    scheduled_at=start,
                    recurrence_rule=recurrence_rule,
                    flow_type=event_type.lower() if event_type in ['NOTIFICATION', 'CONVERSATION'] else 'notification',
                    default_agent_id=agent_id,
                    initiator_type='agentic',
                    is_active=True,
                    next_execution_at=start
                )
                self.db.add(flow)
                self.db.flush()

                # Create the notification/conversation step
                step_config = payload.copy()
                step = FlowNode(
                    flow_definition_id=flow.id,
                    name=title,
                    step_description=description,
                    type=event_type.lower(),
                    position=1,
                    config_json=json.dumps(step_config),
                    agent_id=agent_id
                )
                self.db.add(step)
                self.db.commit()

                self._log_info(f"Created recurring flow ID: {flow.id}")

                # Return as SchedulerEvent for consistent interface
                return SchedulerEvent(
                    id=f"flows_recurring_{flow.id}",
                    provider=self.provider_type.value,
                    title=title,
                    start=start,
                    end=end,
                    description=description,
                    status=SchedulerEventStatus.SCHEDULED,
                    recurrence=recurrence,
                    raw_data={
                        'flow_id': flow.id,
                        'event_type': event_type,
                        'execution_method': 'recurring',
                        'recurrence_rule': recurrence_rule,
                    },
                    metadata={
                        'event_type': event_type,
                        'recipient': recipient,
                        'agent_id': agent_id,
                        'is_recurring': True,
                    }
                )
            except Exception as e:
                self._log_error(f"Failed to create recurring flow: {e}", exc_info=True)
                raise SchedulerProviderError(f"Failed to create recurring flow: {e}")

        # For one-time events, use the existing ScheduledEvent system
        try:
            created_event = scheduler_service.create_event(
                creator_type='AGENT',
                creator_id=agent_id,
                event_type=event_type.upper(),
                scheduled_at=start,
                payload=payload,
                recurrence_rule=recurrence_rule if not execution_method == 'recurring' else None,
                tenant_id=self.tenant_id,
            )

            self._log_info(f"Created event ID: {created_event.id}")
            return self._scheduled_event_to_scheduler_event(created_event)

        except Exception as e:
            self._log_error(f"Failed to create event: {e}", exc_info=True)
            raise SchedulerProviderError(f"Failed to create Flows event: {e}")

    async def list_events(
        self,
        start: datetime,
        end: datetime,
        query: Optional[str] = None,
        max_results: int = 50,
        include_completed: bool = False,
        **kwargs
    ) -> List[SchedulerEvent]:
        """
        List events within a time range.

        Args:
            start: Start of time range
            end: End of time range
            query: Optional search query (searches reminder_text/objective)
            max_results: Maximum events to return
            include_completed: Include completed events (default: False)
            **kwargs: Additional filter args

        Returns:
            List of SchedulerEvent objects
        """
        from models import ScheduledEvent

        self._log_info(f"Listing events from {start} to {end}")

        # Build query
        db_query = self.db.query(ScheduledEvent).filter(
            ScheduledEvent.scheduled_at >= start,
            ScheduledEvent.scheduled_at <= end,
        )

        # Filter by tenant
        if self.tenant_id:
            db_query = db_query.filter(ScheduledEvent.tenant_id == self.tenant_id)

        # Filter by status
        if include_completed:
            statuses = ['PENDING', 'ACTIVE', 'COMPLETED']
        else:
            statuses = ['PENDING', 'ACTIVE']
        db_query = db_query.filter(ScheduledEvent.status.in_(statuses))

        # Order and limit
        db_query = db_query.order_by(ScheduledEvent.scheduled_at.asc())
        db_query = db_query.limit(max_results)

        events = db_query.all()

        # Convert to SchedulerEvent
        result = []
        for event in events:
            scheduler_event = self._scheduled_event_to_scheduler_event(event)

            # Filter by query if provided
            if query:
                query_lower = query.lower()
                if query_lower not in scheduler_event.title.lower():
                    if scheduler_event.description and query_lower not in scheduler_event.description.lower():
                        continue

            result.append(scheduler_event)

        self._log_info(f"Found {len(result)} events")
        return result

    async def get_event(self, event_id: str) -> Optional[SchedulerEvent]:
        """
        Get a specific event by ID.

        Args:
            event_id: Event ID (format: "flows_123")

        Returns:
            SchedulerEvent if found, None otherwise
        """
        from models import ScheduledEvent

        # Extract numeric ID
        if event_id.startswith('flows_'):
            numeric_id = int(event_id.replace('flows_', ''))
        else:
            try:
                numeric_id = int(event_id)
            except ValueError:
                self._log_warning(f"Invalid event ID format: {event_id}")
                return None

        # Query
        query = self.db.query(ScheduledEvent).filter(ScheduledEvent.id == numeric_id)

        if self.tenant_id:
            query = query.filter(ScheduledEvent.tenant_id == self.tenant_id)

        event = query.first()

        if event:
            return self._scheduled_event_to_scheduler_event(event)
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
        Update an existing event.

        Args:
            event_id: Event ID (format: "flows_123")
            title: New title
            start: New start time
            end: Ignored for Flows
            description: New description
            location: Ignored for Flows
            status: New status
            **kwargs: Additional args

        Returns:
            Updated SchedulerEvent
        """
        from models import ScheduledEvent

        # Extract numeric ID
        if event_id.startswith('flows_'):
            numeric_id = int(event_id.replace('flows_', ''))
        else:
            numeric_id = int(event_id)

        # Get event
        query = self.db.query(ScheduledEvent).filter(ScheduledEvent.id == numeric_id)
        if self.tenant_id:
            query = query.filter(ScheduledEvent.tenant_id == self.tenant_id)

        event = query.first()
        if not event:
            raise ValueError(f"Event not found: {event_id}")

        # Update fields
        if start:
            event.scheduled_at = start
            event.next_execution_at = start

        if title or description:
            payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload

            if event.event_type == 'NOTIFICATION':
                if title:
                    payload['reminder_text'] = title
                if description:
                    payload['reminder_text'] = f"{title or payload.get('reminder_text', '')} - {description}"
            elif event.event_type == 'CONVERSATION':
                if title:
                    payload['objective'] = title

            event.payload = json.dumps(payload)

        if status:
            status_map = {
                SchedulerEventStatus.SCHEDULED: 'PENDING',
                SchedulerEventStatus.IN_PROGRESS: 'ACTIVE',
                SchedulerEventStatus.COMPLETED: 'COMPLETED',
                SchedulerEventStatus.CANCELLED: 'CANCELLED',
                SchedulerEventStatus.FAILED: 'FAILED',
            }
            event.status = status_map.get(status, 'PENDING')

        self.db.commit()
        self._log_info(f"Updated event {event_id}")

        return self._scheduled_event_to_scheduler_event(event)

    async def delete_event(self, event_id: str) -> bool:
        """
        Delete/cancel an event.

        Args:
            event_id: Event ID (format: "flows_123")

        Returns:
            True if deleted/cancelled successfully
        """
        from models import ScheduledEvent

        # Extract numeric ID
        if event_id.startswith('flows_'):
            numeric_id = int(event_id.replace('flows_', ''))
        else:
            numeric_id = int(event_id)

        # Get event
        query = self.db.query(ScheduledEvent).filter(ScheduledEvent.id == numeric_id)
        if self.tenant_id:
            query = query.filter(ScheduledEvent.tenant_id == self.tenant_id)

        event = query.first()
        if not event:
            self._log_warning(f"Event not found for deletion: {event_id}")
            return False

        # Cancel instead of delete (preserve history)
        event.status = 'CANCELLED'
        self.db.commit()

        self._log_info(f"Cancelled event {event_id}")
        return True

    async def check_health(self) -> Dict[str, Any]:
        """
        Check Flows provider health.

        Returns:
            Health status dict
        """
        from models import ScheduledEvent

        try:
            # Test database connection
            count = self.db.query(ScheduledEvent).filter(
                ScheduledEvent.status.in_(['PENDING', 'ACTIVE'])
            ).count()

            return {
                'status': 'healthy',
                'provider': self.provider_type.value,
                'provider_name': self.provider_name,
                'last_check': datetime.utcnow().isoformat() + 'Z',
                'details': {
                    'pending_events': count,
                    'database_connected': True,
                }
            }
        except Exception as e:
            return {
                'status': 'unavailable',
                'provider': self.provider_type.value,
                'provider_name': self.provider_name,
                'last_check': datetime.utcnow().isoformat() + 'Z',
                'errors': [str(e)]
            }
