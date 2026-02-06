"""
Phase 6.4 Week 4: Scheduler API Routes
Phase 7.9: Added tenant isolation

RESTful API endpoints for managing scheduled events, conversations, and notifications.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from models import ScheduledEvent, ConversationLog
from scheduler.scheduler_service import SchedulerService
from auth_dependencies import (
    get_current_user_required,
    require_permission,
    get_tenant_context,
    TenantContext
)
from models_rbac import User
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])

# Global engine reference (set by main app)
_engine = None

def set_engine(engine):
    """Set the database engine for this router"""
    global _engine
    _engine = engine

# Dependency to get database session
def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================================
# Pydantic Schemas
# ============================================================================

class RecurrenceRuleSchema(BaseModel):
    """Recurrence rule for recurring events"""
    frequency: str = Field(..., description="daily, weekly, or monthly")
    interval: int = Field(1, description="Recurrence interval (e.g., every N days)")
    days_of_week: Optional[List[int]] = Field(None, description="Days for weekly recurrence (1=Monday, 7=Sunday)")
    timezone: Optional[str] = Field(None, description="Timezone (e.g., UTC, America/New_York)")


class EventCreateSchema(BaseModel):
    """Generic event creation"""
    event_type: str = Field(..., description="MESSAGE, TASK, CONVERSATION, or NOTIFICATION")
    scheduled_at: datetime = Field(..., description="When to execute the event")
    payload: Dict[str, Any] = Field(..., description="Event-specific payload")
    recurrence_rule: Optional[RecurrenceRuleSchema] = None


class ConversationCreateSchema(BaseModel):
    """Create conversation event"""
    agent_id: int
    recipient: str = Field(..., description="Phone number or WhatsApp ID")
    objective: str = Field(..., description="Conversation objective")
    scheduled_at: datetime
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)
    max_turns: int = Field(20, description="Maximum conversation turns")
    timeout_hours: int = Field(24, description="Conversation timeout in hours")
    impersonate: Optional[Dict[str, Any]] = None
    persona_id: Optional[int] = Field(None, description="Optional persona to apply to conversation")
    custom_system_prompt: Optional[str] = Field(None, description="Optional custom system prompt")


class NotificationCreateSchema(BaseModel):
    """Create notification event"""
    agent_id: int
    recipient_raw: str = Field(..., description="Contact name, @mention, or phone number")
    reminder_text: str = Field(..., description="Reminder message")
    scheduled_at: datetime
    message_template: Optional[str] = Field(
        "Hi {name}! Reminder: {reminder_text}",
        description="Message template with {name} and {reminder_text} placeholders"
    )
    recurrence_rule: Optional[RecurrenceRuleSchema] = None


class EventUpdateSchema(BaseModel):
    """Update event fields"""
    scheduled_at: Optional[datetime] = None
    payload: Optional[Dict[str, Any]] = None
    recurrence_rule: Optional[RecurrenceRuleSchema] = None


class ConversationGuidanceSchema(BaseModel):
    """Provide guidance to paused conversation"""
    guidance_message: str = Field(..., description="User guidance for the conversation")


class EventResponseSchema(BaseModel):
    """Event response"""
    id: int
    event_type: str
    status: str
    scheduled_at: str  # ISO string with 'Z' suffix
    created_at: str  # ISO string with 'Z' suffix
    creator_type: str
    creator_id: int
    execution_count: int
    last_executed_at: Optional[str]  # ISO string with 'Z' suffix
    next_execution_at: Optional[str]  # ISO string with 'Z' suffix
    completed_at: Optional[str]  # ISO string with 'Z' suffix
    payload: Dict[str, Any]
    recurrence_rule: Optional[Dict[str, Any]]
    conversation_state: Optional[Dict[str, Any]]
    error_message: Optional[str]

    class Config:
        from_attributes = True


class ConversationLogResponseSchema(BaseModel):
    """Conversation log entry"""
    id: int
    event_id: int  # Maps to scheduled_event_id
    turn_number: int  # Maps to conversation_turn
    direction: str  # Maps to message_direction
    recipient: str
    content: str  # Maps to message_content
    timestamp: str  # Maps to message_timestamp - ISO string with 'Z'

    class Config:
        from_attributes = True

    @staticmethod
    def from_orm(log):
        """Custom mapping from ORM model to response schema"""
        # Format timestamp with 'Z' suffix
        timestamp_str = log.message_timestamp.isoformat() + 'Z' if isinstance(log.message_timestamp, datetime) else log.message_timestamp
        if isinstance(timestamp_str, str) and 'T' in timestamp_str and not timestamp_str.endswith('Z') and '+' not in timestamp_str:
            timestamp_str = timestamp_str + 'Z'

        return ConversationLogResponseSchema(
            id=log.id,
            event_id=log.scheduled_event_id,
            turn_number=log.conversation_turn,
            direction=log.message_direction,
            recipient=log.recipient,
            content=log.message_content,
            timestamp=timestamp_str
        )


class StatsResponseSchema(BaseModel):
    """Scheduler statistics"""
    total_events: int
    by_type: Dict[str, int]
    by_status: Dict[str, int]
    active_conversations: int
    pending_executions: int


# ============================================================================
# Helper Functions
# ============================================================================

def event_to_response(event: ScheduledEvent) -> EventResponseSchema:
    """Convert ScheduledEvent to response schema with proper UTC timestamp formatting"""
    payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
    recurrence_rule = json.loads(event.recurrence_rule) if event.recurrence_rule and isinstance(event.recurrence_rule, str) else event.recurrence_rule
    conversation_state = json.loads(event.conversation_state) if event.conversation_state and isinstance(event.conversation_state, str) else event.conversation_state

    def format_datetime(dt):
        """Ensure datetime is serialized as ISO string with 'Z' suffix for UTC"""
        if dt is None:
            return None
        if isinstance(dt, str):
            # Already a string - ensure it has Z suffix if it looks like UTC
            if 'T' in dt and not dt.endswith('Z') and '+' not in dt:
                return dt + 'Z'
            return dt
        # datetime object - convert to ISO with Z (assuming naive UTC from database)
        return dt.isoformat() + 'Z'

    return EventResponseSchema(
        id=event.id,
        event_type=event.event_type,
        status=event.status,
        scheduled_at=format_datetime(event.scheduled_at),
        created_at=format_datetime(event.created_at),
        creator_type=event.creator_type,
        creator_id=event.creator_id,
        execution_count=event.execution_count,
        last_executed_at=format_datetime(event.last_executed_at),
        next_execution_at=format_datetime(event.next_execution_at),
        completed_at=format_datetime(event.completed_at),
        payload=payload,
        recurrence_rule=recurrence_rule,
        conversation_state=conversation_state,
        error_message=event.error_message
    )


# ============================================================================
# Generic Event Endpoints
# ============================================================================

@router.get("/", response_model=List[EventResponseSchema], dependencies=[Depends(require_permission("scheduler.read"))])
def list_events(
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    creator_id: Optional[int] = Query(None, description="Filter by creator ID"),
    recipient: Optional[str] = Query(None, description="Filter by recipient (phone/contact)"),
    tenant_context: TenantContext = Depends(get_tenant_context),
    limit: int = Query(50, le=200, description="Maximum events to return"),
    offset: int = Query(0, description="Pagination offset"),
    db: Session = Depends(get_db)
):
    """
    List scheduled events with optional filters.

    Filters:
    - event_type: MESSAGE, TASK, CONVERSATION, NOTIFICATION
    - status: PENDING, ACTIVE, COMPLETED, FAILED, CANCELLED
    - creator_id: Filter by creator ID (privacy filter)
    - recipient: Filter by recipient phone/contact (privacy filter)
    """
    try:
        scheduler = SchedulerService(db)

        # Build query
        query = db.query(ScheduledEvent)

        # Phase 7.9: Tenant isolation
        query = tenant_context.filter_by_tenant(query, ScheduledEvent.tenant_id)

        if event_type:
            query = query.filter(ScheduledEvent.event_type == event_type.upper())

        if status:
            query = query.filter(ScheduledEvent.status == status.upper())

        if creator_id:
            query = query.filter(ScheduledEvent.creator_id == creator_id)

        # Get all events first, then filter by recipient in Python (since it's in JSON payload)
        if recipient:
            # Need to filter in Python since recipient is in JSON payload
            all_events = query.order_by(ScheduledEvent.id.desc()).offset(offset).limit(limit * 2).all()
            filtered_events = []

            for event in all_events:
                payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload

                # Check if recipient matches in payload
                event_recipient = payload.get('recipient') or payload.get('recipient_raw') or ''

                # Match by phone number or contact name
                if recipient.lower() in event_recipient.lower():
                    filtered_events.append(event)

                    # Stop when we have enough results
                    if len(filtered_events) >= limit:
                        break

            return [event_to_response(event) for event in filtered_events]

        # Order by ID descending (newest first)
        query = query.order_by(ScheduledEvent.id.desc())

        # Pagination
        events = query.offset(offset).limit(limit).all()

        return [event_to_response(event) for event in events]

    except Exception as e:
        logger.error(f"Error listing events: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/", response_model=EventResponseSchema, dependencies=[Depends(require_permission("scheduler.create"))])
def create_event(
    event: EventCreateSchema,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Create a generic scheduled event.

    Use specialized endpoints for conversations and notifications.
    """
    try:
        scheduler = SchedulerService(db)

        recurrence_dict = event.recurrence_rule.dict() if event.recurrence_rule else None

        created_event = scheduler.create_event(
            creator_type='USER',
            creator_id=tenant_context.user_id or 1,  # Phase 7.9: Get from auth context
            event_type=event.event_type.upper(),
            scheduled_at=event.scheduled_at,
            payload=event.payload,
            recurrence_rule=recurrence_dict,
            tenant_id=tenant_context.tenant_id  # Phase 7.9: Multi-tenancy
        )

        return event_to_response(created_event)

    except Exception as e:
        logger.error(f"Error creating event: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{event_id}", response_model=EventResponseSchema, dependencies=[Depends(require_permission("scheduler.read"))])
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get event details by ID"""
    try:
        query = db.query(ScheduledEvent).filter(ScheduledEvent.id == event_id)
        query = tenant_context.filter_by_tenant(query, ScheduledEvent.tenant_id)
        event = query.first()

        if not event:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

        return event_to_response(event)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{event_id}", response_model=EventResponseSchema, dependencies=[Depends(require_permission("scheduler.edit"))])
def update_event(
    event_id: int,
    update: EventUpdateSchema,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Update event fields.

    Can update: scheduled_at, payload, recurrence_rule
    Cannot update: event_type, status (use cancel endpoint)
    """
    try:
        # Phase 7.9: Verify tenant access first
        query = db.query(ScheduledEvent).filter(ScheduledEvent.id == event_id)
        query = tenant_context.filter_by_tenant(query, ScheduledEvent.tenant_id)
        if not query.first():
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

        scheduler = SchedulerService(db)

        updates = {}
        if update.scheduled_at:
            updates['scheduled_at'] = update.scheduled_at
        if update.payload:
            updates['payload'] = update.payload
        if update.recurrence_rule:
            updates['recurrence_rule'] = update.recurrence_rule.dict()

        updated_event = scheduler.update_event(event_id, updates)

        return event_to_response(updated_event)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating event: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{event_id}", dependencies=[Depends(require_permission("scheduler.cancel"))])
def cancel_event(
    event_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Cancel a scheduled event"""
    try:
        # Phase 7.9: Verify tenant access first
        query = db.query(ScheduledEvent).filter(ScheduledEvent.id == event_id)
        query = tenant_context.filter_by_tenant(query, ScheduledEvent.tenant_id)
        if not query.first():
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

        scheduler = SchedulerService(db)
        scheduler.cancel_event(event_id)

        return {"message": f"Event {event_id} cancelled successfully"}

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error cancelling event: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cleanup", dependencies=[Depends(require_permission("scheduler.cancel"))])
def cleanup_events(
    statuses: List[str] = Query(..., description="List of statuses to delete"),
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Permanently delete events with specific statuses.

    This will delete events and their associated conversation logs from the database.
    Use with caution - this action cannot be undone.

    Example: /api/scheduler/cleanup?statuses=CANCELLED&statuses=FAILED&statuses=COMPLETED
    """
    try:
        scheduler = SchedulerService(db)
        deleted_count = scheduler.cleanup_events(statuses)

        return {
            "message": f"Successfully deleted {deleted_count} events",
            "deleted_count": deleted_count,
            "statuses": statuses
        }

    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Conversation-Specific Endpoints
# ============================================================================

@router.post("/conversation", response_model=EventResponseSchema, dependencies=[Depends(require_permission("scheduler.create"))])
def create_conversation(
    conversation: ConversationCreateSchema,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Create a conversation event.

    Conversations are autonomous multi-turn interactions with objectives.
    """
    try:
        scheduler = SchedulerService(db)

        payload = {
            'agent_id': conversation.agent_id,
            'recipient': conversation.recipient,
            'objective': conversation.objective,
            'context': conversation.context or {},
            'max_turns': conversation.max_turns,
            'timeout_hours': conversation.timeout_hours
        }

        if conversation.impersonate:
            payload['impersonate'] = conversation.impersonate

        if conversation.persona_id:
            payload['persona_id'] = conversation.persona_id

        if conversation.custom_system_prompt:
            payload['custom_system_prompt'] = conversation.custom_system_prompt

        event = scheduler.create_event(
            creator_type='USER',
            creator_id=tenant_context.user_id or 1,  # Phase 7.9: Get from auth context
            event_type='CONVERSATION',
            scheduled_at=conversation.scheduled_at,
            payload=payload,
            tenant_id=tenant_context.tenant_id  # Phase 7.9: Multi-tenancy
        )

        return event_to_response(event)

    except Exception as e:
        logger.error(f"Error creating conversation: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/notification", response_model=EventResponseSchema, dependencies=[Depends(require_permission("scheduler.create"))])
def create_notification(
    notification: NotificationCreateSchema,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Create a notification event with contact resolution.

    recipient_raw can be:
    - Contact name (e.g., "Alice")
    - @mention (e.g., "@Alice")
    - Phone number (e.g., "+5500000000001")
    """
    try:
        scheduler = SchedulerService(db)

        payload = {
            'agent_id': notification.agent_id,
            'recipient_raw': notification.recipient_raw,
            'reminder_text': notification.reminder_text,
            'message_template': notification.message_template
        }

        recurrence_dict = notification.recurrence_rule.dict() if notification.recurrence_rule else None

        event = scheduler.create_event(
            creator_type='USER',
            creator_id=tenant_context.user_id or 1,  # Phase 7.9: Get from auth context
            event_type='NOTIFICATION',
            scheduled_at=notification.scheduled_at,
            payload=payload,
            recurrence_rule=recurrence_dict,
            tenant_id=tenant_context.tenant_id  # Phase 7.9: Multi-tenancy
        )

        return event_to_response(event)

    except Exception as e:
        logger.error(f"Error creating notification: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/conversation/{event_id}/logs", response_model=List[ConversationLogResponseSchema], dependencies=[Depends(require_permission("scheduler.read"))])
def get_conversation_logs(
    event_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get all conversation logs for a conversation event"""
    try:
        # Verify event exists, is a conversation, and belongs to tenant (Phase 7.9)
        query = db.query(ScheduledEvent).filter(ScheduledEvent.id == event_id)
        query = tenant_context.filter_by_tenant(query, ScheduledEvent.tenant_id)
        event = query.first()

        if not event:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

        if event.event_type != 'CONVERSATION':
            raise HTTPException(status_code=400, detail="Event is not a conversation")

        # Get logs
        logs = db.query(ConversationLog).filter(
            ConversationLog.scheduled_event_id == event_id
        ).order_by(ConversationLog.message_timestamp.asc()).all()

        return [ConversationLogResponseSchema.from_orm(log) for log in logs]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation logs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversation/{event_id}/guidance", dependencies=[Depends(require_permission("scheduler.edit"))])
def provide_conversation_guidance(
    event_id: int,
    guidance: ConversationGuidanceSchema,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Provide guidance to a paused conversation.

    Used when conversation deviates and needs user intervention.
    """
    try:
        # Phase 7.9: Verify tenant access first
        query = db.query(ScheduledEvent).filter(ScheduledEvent.id == event_id)
        query = tenant_context.filter_by_tenant(query, ScheduledEvent.tenant_id)
        if not query.first():
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

        scheduler = SchedulerService(db)

        result = scheduler.provide_conversation_guidance(
            event_id=event_id,
            guidance_message=guidance.guidance_message
        )

        return {
            "message": "Guidance provided successfully",
            "status": result.get('status'),
            "suggested_reply": result.get('suggested_reply')
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error providing guidance: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/conversation/{event_id}/cancel", dependencies=[Depends(require_permission("scheduler.cancel"))])
def cancel_conversation(
    event_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Cancel an active conversation"""
    try:
        # Phase 7.9: Verify tenant access first
        query = db.query(ScheduledEvent).filter(ScheduledEvent.id == event_id)
        query = tenant_context.filter_by_tenant(query, ScheduledEvent.tenant_id)
        if not query.first():
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

        scheduler = SchedulerService(db)
        scheduler.cancel_event(event_id)

        return {"message": f"Conversation {event_id} cancelled successfully"}

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error cancelling conversation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Statistics & Summary
# ============================================================================

@router.get("/stats/summary", response_model=StatsResponseSchema, dependencies=[Depends(require_permission("scheduler.read"))])
def get_stats(
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get scheduler statistics"""
    try:
        # Phase 7.9: Helper to apply tenant filtering
        def tenant_query():
            q = db.query(ScheduledEvent)
            return tenant_context.filter_by_tenant(q, ScheduledEvent.tenant_id)

        # Total events
        total = tenant_query().count()

        # By type
        by_type = {}
        for event_type in ['MESSAGE', 'TASK', 'CONVERSATION', 'NOTIFICATION']:
            count = tenant_query().filter(
                ScheduledEvent.event_type == event_type
            ).count()
            by_type[event_type.lower()] = count

        # By status
        by_status = {}
        for status in ['PENDING', 'ACTIVE', 'COMPLETED', 'FAILED', 'CANCELLED']:
            count = tenant_query().filter(
                ScheduledEvent.status == status
            ).count()
            by_status[status.lower()] = count

        # Active conversations
        active_conversations = tenant_query().filter(
            ScheduledEvent.event_type == 'CONVERSATION',
            ScheduledEvent.status == 'ACTIVE'
        ).count()

        # Pending executions (PENDING events scheduled in the past)
        pending_executions = tenant_query().filter(
            ScheduledEvent.status == 'PENDING',
            ScheduledEvent.scheduled_at <= datetime.utcnow()
        ).count()

        return StatsResponseSchema(
            total_events=total,
            by_type=by_type,
            by_status=by_status,
            active_conversations=active_conversations,
            pending_executions=pending_executions
        )

    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
