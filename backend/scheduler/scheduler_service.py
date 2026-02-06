"""
Phase 6.4: Enhanced Scheduler Service

Core service for managing scheduled events including:
- Notifications (smart reminders with contact resolution)
- Conversations (autonomous multi-turn AI-driven conversations)

Note: Scheduled messages and tool executions are handled by the Flows feature.
"""

import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_
from mcp_sender import MCPSender

try:
    import pytz
except ImportError:
    pytz = None
    logging.warning("pytz not installed - timezone support disabled")

from models import ScheduledEvent, ConversationLog, Agent, Contact, Persona
from agent.contact_service import ContactService

logger = logging.getLogger(__name__)

# Conversation completion phrases (English and Portuguese)
COMPLETION_PHRASES = [
    # English
    "have a productive day", "have a great day", "have a good day", "have an excellent day",
    "you're welcome", "you are welcome", "take care", "goodbye",
    "talk to you later", "speak soon", "that's all", "all set",
    "we're done", "bye", "see you", "catch you later",
    # Portuguese - flexible day wishes
    "tenha um", "ótimo dia", "excelente dia", "bom dia", "produtivo dia",
    "de nada", "disponha", "até logo", "tchau", "até mais",
    "falamos depois", "falo com você depois", "qualquer coisa é só chamar",
    "se precisar é só chamar", "boas reuniões", "boa sorte", "fico feliz em ajudar"
]


class SchedulerService:
    """Service for managing scheduled events with conversation support."""

    def __init__(self, db: Session, memory_manager=None):
        """
        Initialize SchedulerService.

        Args:
            db: Database session
            memory_manager: Optional MultiAgentMemoryManager for semantic memory integration (Item 11)
        """
        self.db = db
        self.contact_service = ContactService(db)
        self.memory_manager = memory_manager  # Item 11: For semantic memory in conversations

    def _sanitize_ai_reply(self, agent_id: int, reply: str) -> str:
        if not reply:
            return ""

        from agent.contamination_detector import get_contamination_detector

        detector = get_contamination_detector(db_session=self.db, agent_id=agent_id)
        contamination_pattern = detector.check(reply)
        if contamination_pattern:
            logger.error(
                f"[CONVERSATION] Contamination detected in AI reply (agent {agent_id}): {contamination_pattern}"
            )
            return ""

        return detector.clean_response(reply).strip()

    def _resolve_mcp_api_url(self, agent_id: int) -> str:
        """
        Phase 8: Resolve MCP API URL for an agent based on tenant_id

        Looks up the active WhatsApp MCP instance for the agent's tenant.
        Falls back to default URL if no instance found (backward compatibility).

        Args:
            agent_id: Agent ID

        Returns:
            MCP API URL (e.g., http://127.0.0.1:8080/api)
        """
        from models import WhatsAppMCPInstance

        try:
            # Get agent's tenant_id
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                logger.warning(f"Agent {agent_id} not found, using default MCP URL")
                return "http://127.0.0.1:8080/api"

            # If agent has no tenant_id, fall back to default (backward compatibility)
            if not agent.tenant_id:
                logger.debug(f"Agent {agent_id} has no tenant_id, using default MCP URL")
                return "http://127.0.0.1:8080/api"

            # Find active AGENT MCP instance for tenant (NOT tester!)
            # CRITICAL: Must filter by instance_type="agent" to prevent sending via tester phone
            instance = self.db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.tenant_id == agent.tenant_id,
                WhatsAppMCPInstance.instance_type == "agent",  # CRITICAL: Only use agent instances!
                WhatsAppMCPInstance.status.in_(["running", "starting"])
            ).first()

            if instance:
                logger.debug(f"Resolved MCP URL for agent {agent_id}: {instance.mcp_api_url}")
                return instance.mcp_api_url
            else:
                logger.warning(f"No active MCP instance for tenant {agent.tenant_id}, using default URL")
                return "http://127.0.0.1:8080/api"

        except Exception as e:
            logger.error(f"Error resolving MCP URL for agent {agent_id}: {e}", exc_info=True)
            return "http://127.0.0.1:8080/api"

    def create_event(
        self,
        creator_type: str,
        creator_id: int,
        event_type: str,
        scheduled_at: datetime,
        payload: Dict,
        recurrence_rule: Optional[Dict] = None,
        tenant_id: Optional[str] = None  # Phase 7.9: Multi-tenancy
    ) -> ScheduledEvent:
        """
        Create a new scheduled event.

        Args:
            creator_type: 'USER' or 'AGENT'
            creator_id: ID of user or agent creating the event
            event_type: 'NOTIFICATION' or 'CONVERSATION'
            scheduled_at: When to execute the event
            payload: Event-specific data (JSON)
            recurrence_rule: Optional recurrence configuration (JSON)
            tenant_id: Tenant ID for multi-tenancy (Phase 7.9)

        Returns:
            Created ScheduledEvent

        Note: For scheduled messages and tool execution, use the Flows feature.
        """
        # Validate and enrich payload based on event type
        if event_type == 'NOTIFICATION':
            payload = self._enrich_notification_payload(payload)
        elif event_type == 'CONVERSATION':
            payload = self._validate_conversation_payload(payload)

        event = ScheduledEvent(
            tenant_id=tenant_id,  # Phase 7.9: Multi-tenancy
            creator_type=creator_type,
            creator_id=creator_id,
            event_type=event_type,
            scheduled_at=scheduled_at,
            payload=json.dumps(payload),
            recurrence_rule=json.dumps(recurrence_rule) if recurrence_rule else None,
            next_execution_at=scheduled_at,
            status='PENDING'
        )

        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        logger.info(f"Created {event_type} event {event.id} scheduled for {scheduled_at}")
        return event

    def _enrich_notification_payload(self, payload: Dict) -> Dict:
        """
        Resolve contact identifiers for notifications.

        CRITICAL: Always resolves to phone numbers, never WhatsApp IDs.
        WhatsApp MCP API only accepts phone numbers for sending messages.
        """
        recipient_raw = payload.get('recipient_raw', '')
        sender_key = payload.get('sender_key', '')  # Requester's identifier (may be WhatsApp ID or phone)

        # Try to resolve contact by name, phone, or @mention
        contact = self.contact_service.resolve_identifier(recipient_raw)

        if contact:
            # Contact found - use their phone number ONLY
            if not contact.phone_number:
                raise ValueError(f"Contact '{recipient_raw}' has no phone number - cannot send notification")

            payload['recipient_resolved'] = contact.phone_number
            payload['recipient_contact_id'] = contact.id

            # Personalize message template
            message_template = payload.get('message_template', '{reminder_text}')
            payload['message_content'] = message_template.format(
                name=contact.friendly_name,
                reminder_text=payload.get('reminder_text', '')
            )
        else:
            # Fallback: if recipient_raw is empty or not resolved, send to requester (sender_key)
            if not recipient_raw or not recipient_raw.strip():
                # CRITICAL FIX: Resolve sender_key to phone number via Contact database
                # For group messages, sender_key is WhatsApp ID, not phone number
                sender_contact = self.contact_service.resolve_identifier(sender_key)

                if sender_contact and sender_contact.phone_number:
                    payload['recipient_resolved'] = sender_contact.phone_number
                    logger.info(f"No recipient specified - resolved sender '{sender_key}' to phone: {sender_contact.phone_number}")
                else:
                    # Assume sender_key is already a phone number (for backward compatibility with DMs)
                    payload['recipient_resolved'] = sender_key
                    logger.warning(f"Could not resolve sender '{sender_key}' to contact - using as-is (may fail if not a phone number)")
            else:
                # Recipient specified but couldn't resolve - still try to use it as phone number
                payload['recipient_resolved'] = recipient_raw
                logger.warning(f"Could not resolve contact for '{recipient_raw}', using as-is")

            # Always create message_content even if contact not resolved
            reminder_text = payload.get('reminder_text', 'Reminder')
            payload['message_content'] = f"⏰ Reminder: {reminder_text}"

        return payload

    def _validate_conversation_payload(self, payload: Dict) -> Dict:
        """Validate and enrich conversation event payload."""
        required = ['agent_id', 'recipient', 'objective', 'context']
        missing = [field for field in required if field not in payload]

        if missing:
            raise ValueError(f"Missing required conversation fields: {missing}")

        # Resolve recipient contact (@Alice, Alice, or phone number)
        recipient_raw = payload.get('recipient', '')
        contact = self.contact_service.resolve_identifier(recipient_raw)

        if contact:
            # Use resolved phone number
            payload['recipient'] = contact.phone_number or contact.whatsapp_id
            payload['recipient_contact_id'] = contact.id
            payload['recipient_name'] = contact.friendly_name
            logger.info(f"Resolved conversation recipient '{recipient_raw}' to {payload['recipient']}")
        else:
            # Keep as-is (assume it's already a phone number)
            logger.warning(f"Could not resolve conversation recipient '{recipient_raw}', using as-is")

        # Set defaults
        payload.setdefault('max_turns', 20)
        payload.setdefault('timeout_hours', 24)
        payload.setdefault('notify_on_deviation', True)
        payload.setdefault('auto_pause_on_deviation', True)
        payload.setdefault('deviation_threshold', 3)
        payload.setdefault('impersonate', {'enabled': False})

        return payload

    def get_due_events(self) -> List[ScheduledEvent]:
        """Get all events that are due for execution."""
        now = datetime.utcnow()

        # SQLAlchemy will handle the datetime comparison correctly
        # The database stores ISO strings but SQLAlchemy converts them to datetime objects
        events = self.db.query(ScheduledEvent).filter(
            and_(
                ScheduledEvent.status.in_(['PENDING', 'ACTIVE']),
                ScheduledEvent.next_execution_at <= now
            )
        ).all()

        return events

    def execute_event(self, event: ScheduledEvent):
        """Execute a scheduled event."""
        logger.info(f"Executing {event.event_type} event {event.id}")

        try:
            payload = json.loads(event.payload)

            # Update execution tracking BEFORE execution to prevent race conditions
            event.execution_count += 1
            event.last_executed_at = datetime.utcnow()
            # Commit immediately to prevent duplicate executions
            self.db.commit()

            if event.event_type == 'NOTIFICATION':
                self._execute_notification_event(event, payload)
            elif event.event_type == 'CONVERSATION':
                self._execute_conversation_event(event, payload)
            else:
                raise ValueError(f"Unsupported event type: {event.event_type}. Only NOTIFICATION and CONVERSATION are supported. Use Flows for scheduled messages and tool execution.")

            # Handle recurrence (not applicable to CONVERSATION which stays ACTIVE)
            if event.event_type != 'CONVERSATION' and event.recurrence_rule:
                next_time = self._calculate_next_execution(event)
                if next_time and (not event.max_executions or
                                 event.execution_count < event.max_executions):
                    event.next_execution_at = next_time
                    event.status = 'PENDING'
                else:
                    event.status = 'COMPLETED'
                    event.completed_at = datetime.utcnow()
            elif event.event_type != 'CONVERSATION':
                # One-time event completed
                event.status = 'COMPLETED'
                event.completed_at = datetime.utcnow()

            event.error_message = None

        except Exception as e:
            logger.error(f"Error executing event {event.id}: {e}", exc_info=True)
            event.status = 'FAILED'
            event.error_message = str(e)
            if event.event_type != 'CONVERSATION':
                event.completed_at = datetime.utcnow()

        self.db.commit()

    def _execute_notification_event(self, event: ScheduledEvent, payload: Dict):
        """Execute a notification event."""
        recipient = payload.get('recipient_resolved')
        content = payload.get('message_content')
        platform = payload.get('platform', 'whatsapp')
        agent_id = payload.get('agent_id')

        if not recipient:
            raise ValueError("Could not resolve recipient for notification")

        if not content:
            raise ValueError("Notification missing content")

        if not agent_id:
            raise ValueError("Notification missing agent_id")

        # CRITICAL: Validate recipient is a phone number (not WhatsApp ID)
        # WhatsApp MCP API only accepts phone numbers for sending
        import re
        # Phone numbers are typically 10-15 digits (international format, optional + prefix)
        if not re.match(r'^\+?\d{10,15}$', recipient):
            logger.error(f"Invalid recipient format: {recipient} (not a phone number)")
            raise ValueError(f"Invalid recipient: {recipient} - must be a phone number (10-15 digits), not WhatsApp ID")

        logger.info(f"[NOTIFICATION] To: {recipient}, Content: {content}")

        # Send via WhatsApp MCP
        if platform == 'whatsapp':
            logger.info(f"Preparing to send WhatsApp message to {recipient}")

            # Phase 8: Resolve MCP API URL for the agent's tenant
            mcp_api_url = self._resolve_mcp_api_url(agent_id)
            logger.info(f"Resolved MCP URL for agent {agent_id}: {mcp_api_url}")

            mcp_sender = MCPSender()
            whatsapp_id = f"{recipient}@s.whatsapp.net"

            # Send message asynchronously using new event loop
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    success = loop.run_until_complete(mcp_sender.send_message(whatsapp_id, content, api_url=mcp_api_url))
                    logger.info(f"MCPSender returned success={success}")
                finally:
                    loop.close()

                if not success:
                    raise Exception(f"Failed to send notification to {recipient}")

                logger.info(f"Successfully sent WhatsApp message to {recipient}")
            except Exception as e:
                logger.error(f"Error sending WhatsApp message: {e}", exc_info=True)
                raise

    def _execute_conversation_event(self, event: ScheduledEvent, payload: Dict):
        """
        Execute a conversation event (initial execution only).
        Conversations remain ACTIVE and are driven by incoming messages.
        """
        # First execution: send initial message (execution_count was incremented before this)
        if event.execution_count == 1:
            # Set status and next_execution BEFORE starting conversation (prevents race condition)
            event.status = 'ACTIVE'  # Keep active for continuation
            event.next_execution_at = None  # Driven by incoming messages
            # CRITICAL: Commit immediately BEFORE _start_conversation() to prevent race condition
            # _start_conversation() is SLOW (AI generation + WhatsApp send + logging)
            self.db.commit()

            # Now start the conversation (this takes 2-5 seconds)
            self._start_conversation(event, payload)
        else:
            # This should not happen - conversations are driven by incoming messages
            logger.warning(f"Conversation event {event.id} executed multiple times (execution_count={event.execution_count})")

    def _ensure_single_active_conversation(self, agent_id: int, recipient: str, exclude_event_id: int = None):
        """
        Ensure only one active conversation per (agent, recipient) pair.
        Auto-completes any existing active conversations.

        Args:
            agent_id: The agent ID
            recipient: The recipient phone number
            exclude_event_id: Event ID to exclude from check (for updates)
        """
        query = self.db.query(ScheduledEvent).filter(
            ScheduledEvent.event_type == 'CONVERSATION',
            ScheduledEvent.status == 'ACTIVE',
            ScheduledEvent.creator_id == agent_id
        )

        if exclude_event_id:
            query = query.filter(ScheduledEvent.id != exclude_event_id)

        # Find active conversations for this agent-recipient pair
        active_conversations = query.all()

        for conv in active_conversations:
            conv_payload = json.loads(conv.payload)
            conv_recipient = conv_payload.get('recipient')

            if conv_recipient == recipient:
                logger.info(
                    f"Auto-completing existing conversation Event {conv.id} "
                    f"(agent {agent_id} -> {recipient}) to enforce single-conversation rule"
                )
                conv.status = 'COMPLETED'
                conv.completed_at = datetime.utcnow()

        self.db.commit()

    def _start_conversation(self, event: ScheduledEvent, payload: Dict):
        """Start an autonomous conversation."""
        agent_id = payload['agent_id']
        recipient = payload['recipient']
        objective = payload['objective']
        context = payload['context']
        impersonate = payload.get('impersonate', {'enabled': False})

        # Enforce single active conversation per (agent, recipient)
        self._ensure_single_active_conversation(agent_id, recipient, exclude_event_id=event.id)

        # Get agent
        agent = self.db.query(Agent).get(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Get agent's contact name
        agent_contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
        agent_name = agent_contact.friendly_name if agent_contact else 'the assistant'

        # Build initial message using AI
        user_name = context.get('user_name', agent_name)
        tone = context.get('tone', 'professional')

        # Generate initial message using AI (run in event loop)
        # For single-turn flows: complete the ENTIRE objective in one message
        # For multi-turn flows: generate conversational opening to START working towards objective
        max_turns = payload.get('max_turns', 20)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            initial_message = loop.run_until_complete(self._generate_opening_message(
                agent=agent,
                objective=objective,
                context=context,
                impersonate=impersonate,
                payload=payload,
                is_single_turn=(max_turns == 1)  # Pass flag to change behavior
            ))
        finally:
            loop.close()

        # Send initial message via WhatsApp
        logger.info(f"[CONVERSATION START] Event: {event.id}, To: {recipient}, Message: {initial_message[:100]}...")

        # Send via WhatsApp MCP
        try:
            # Phase 8: Resolve MCP API URL for the agent's tenant
            mcp_api_url = self._resolve_mcp_api_url(agent_id)
            logger.info(f"Resolved MCP URL for agent {agent_id}: {mcp_api_url}")

            mcp_sender = MCPSender()
            whatsapp_id = f"{recipient}@s.whatsapp.net"

            # Send message asynchronously using new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success = loop.run_until_complete(mcp_sender.send_message(whatsapp_id, initial_message, api_url=mcp_api_url))
                logger.info(f"Conversation start message sent: success={success}")
            finally:
                loop.close()

            if not success:
                raise Exception(f"Failed to send conversation start message to {recipient}")

        except Exception as e:
            logger.error(f"Error sending conversation start message: {e}", exc_info=True)
            raise

        # Log conversation message
        self._log_conversation_message(
            event_id=event.id,
            agent_id=agent_id,
            recipient=recipient,
            direction='SENT',
            content=initial_message,
            turn=1,
            is_impersonating=impersonate.get('enabled', False),
            impersonation_identity=impersonate.get('identity')
        )

        # Initialize conversation state
        state = {
            'current_turn': 1,
            'last_activity': datetime.utcnow().isoformat() + "Z",
            'conversation_history': [{
                'turn': 1,
                'sender': 'agent',
                'message': initial_message,
                'timestamp': datetime.utcnow().isoformat() + "Z"
            }],
            'objective_progress': {
                'achieved': False,
                'confidence': 0.0,
                'notes': 'Conversation started'
            },
            'deviations': []
        }

        event.conversation_state = json.dumps(state)

        # CRITICAL: For single-turn flows (max_turns=1), complete immediately
        # Single-turn means: send message and DONE, no waiting for response
        max_turns = payload.get('max_turns', 20)
        if max_turns == 1:
            event.status = 'COMPLETED'
            event.completed_at = datetime.utcnow()
            state['objective_progress']['notes'] = 'Single-turn flow: message sent, completed immediately'
            event.conversation_state = json.dumps(state)
            logger.info(f"Single-turn flow {event.id} completed immediately after sending message (max_turns=1)")

        self.db.commit()

        logger.info(f"Started conversation for event {event.id} with {recipient}")

    def _log_conversation_message(
        self,
        event_id: int,
        agent_id: int,
        recipient: str,
        direction: str,
        content: str,
        turn: int,
        is_impersonating: bool = False,
        impersonation_identity: str = None
    ):
        """Log a conversation message."""
        log = ConversationLog(
            scheduled_event_id=event_id,
            agent_id=agent_id,
            recipient=recipient,
            message_direction=direction,
            message_content=content,
            conversation_turn=turn,
            is_impersonating=is_impersonating,
            impersonation_identity=impersonation_identity
        )
        self.db.add(log)
        self.db.commit()

    def _calculate_next_execution(self, event: ScheduledEvent) -> Optional[datetime]:
        """Calculate next execution time based on recurrence rule."""
        if not event.recurrence_rule:
            return None

        rule = json.loads(event.recurrence_rule)
        frequency = rule.get('frequency')
        interval = rule.get('interval', 1)

        # Timezone support (optional if pytz is available)
        timezone = None
        if pytz:
            timezone_str = rule.get('timezone', 'UTC')
            try:
                timezone = pytz.timezone(timezone_str)
            except:
                timezone = pytz.UTC

        current = event.next_execution_at
        if not current:
            current = event.scheduled_at

        if frequency == 'once':
            return None

        elif frequency == 'daily':
            next_time = current + timedelta(days=interval)

        elif frequency == 'weekly':
            days_of_week = rule.get('days_of_week', [])
            if days_of_week:
                # Find next matching day of week
                next_time = current + timedelta(days=1)
                max_days = 14  # Safety limit
                days_checked = 0
                while next_time.isoweekday() not in days_of_week and days_checked < max_days:
                    next_time += timedelta(days=1)
                    days_checked += 1
            else:
                next_time = current + timedelta(weeks=interval)

        elif frequency == 'monthly':
            # Add interval months
            month = current.month + interval
            year = current.year
            while month > 12:
                month -= 12
                year += 1

            # Handle day overflow (e.g., Jan 31 -> Feb 28)
            day = current.day
            try:
                next_time = current.replace(year=year, month=month, day=day)
            except ValueError:
                # Day doesn't exist in target month, use last day
                import calendar
                last_day = calendar.monthrange(year, month)[1]
                next_time = current.replace(year=year, month=month, day=last_day)

        else:
            raise ValueError(f"Unknown frequency: {frequency}")

        # Apply timezone if available
        if timezone and pytz:
            if next_time.tzinfo is None:
                next_time = timezone.localize(next_time)
            next_time = next_time.astimezone(pytz.UTC).replace(tzinfo=None)

        return next_time

    def cancel_event(self, event_id: int):
        """Cancel a scheduled event."""
        event = self.db.query(ScheduledEvent).get(event_id)
        if not event:
            raise ValueError(f"Event {event_id} not found")

        event.status = 'CANCELLED'
        event.completed_at = datetime.utcnow()
        self.db.commit()

        logger.info(f"Cancelled scheduled event {event_id}")

    def delete_event(self, event_id: int):
        """Permanently delete a scheduled event and its conversation logs."""
        event = self.db.query(ScheduledEvent).get(event_id)
        if not event:
            raise ValueError(f"Event {event_id} not found")

        # Delete associated conversation logs if any
        if event.event_type == 'CONVERSATION':
            self.db.query(ConversationLog).filter(
                ConversationLog.scheduled_event_id == event_id
            ).delete()

        # Delete the event
        self.db.delete(event)
        self.db.commit()

        logger.info(f"Permanently deleted event {event_id}")

    def cleanup_events(self, statuses: list[str]) -> int:
        """
        Permanently delete events with specific statuses.

        Args:
            statuses: List of statuses to delete (e.g., ['CANCELLED', 'FAILED', 'COMPLETED'])

        Returns:
            Number of events deleted
        """
        count = 0
        events = self.db.query(ScheduledEvent).filter(
            ScheduledEvent.status.in_(statuses)
        ).all()

        for event in events:
            # Delete associated conversation logs
            if event.event_type == 'CONVERSATION':
                self.db.query(ConversationLog).filter(
                    ConversationLog.scheduled_event_id == event.id
                ).delete()

            # Delete the event
            self.db.delete(event)
            count += 1

        self.db.commit()
        logger.info(f"Cleanup: deleted {count} events with statuses {statuses}")

        return count

    def update_event(self, event_id: int, update_data: Dict) -> ScheduledEvent:
        """Update a scheduled event."""
        event = self.db.query(ScheduledEvent).get(event_id)
        if not event:
            raise ValueError(f"Event {event_id} not found")

        if event.status not in ['PENDING', 'ACTIVE', 'PAUSED']:
            raise ValueError(f"Cannot update event with status {event.status}")

        # Update allowed fields
        allowed_fields = ['scheduled_at', 'payload', 'recurrence_rule', 'next_execution_at']

        for key, value in update_data.items():
            if key in allowed_fields:
                if key in ['payload', 'recurrence_rule']:
                    value = json.dumps(value) if value else None
                setattr(event, key, value)

        # If scheduled_at is updated but next_execution_at is not provided, sync them
        if 'scheduled_at' in update_data and 'next_execution_at' not in update_data:
            event.next_execution_at = event.scheduled_at

        event.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(event)

        logger.info(f"Updated event {event_id}")
        return event

    def get_event(self, event_id: int) -> Optional[ScheduledEvent]:
        """Get a scheduled event by ID."""
        return self.db.query(ScheduledEvent).get(event_id)

    def list_events(
        self,
        creator_type: Optional[str] = None,
        creator_id: Optional[int] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[ScheduledEvent]:
        """List scheduled events with optional filters."""
        query = self.db.query(ScheduledEvent)

        if creator_type:
            query = query.filter(ScheduledEvent.creator_type == creator_type)

        if creator_id:
            query = query.filter(ScheduledEvent.creator_id == creator_id)

        if event_type:
            query = query.filter(ScheduledEvent.event_type == event_type)

        if status:
            query = query.filter(ScheduledEvent.status == status)

        query = query.order_by(ScheduledEvent.scheduled_at.desc())
        query = query.limit(limit)

        return query.all()

    # ============================================================================
    # Week 2: Conversation Management Methods
    # ============================================================================

    def _check_conversation_completion(
        self,
        event: ScheduledEvent,
        state: Dict,
        last_agent_message: str
    ) -> bool:
        """
        Check if conversation should be marked as completed.

        Completion criteria:
        1. Agent uses explicit completion signal "Obrigado!!" (2+ exclamation marks) (PRIMARY)
        2. Agent uses closing phrases (goodbye, take care, etc.)
        3. Conversation appears naturally concluded

        Args:
            event: The scheduled event
            state: Current conversation state
            last_agent_message: Most recent agent message

        Returns:
            bool: True if conversation should be completed
        """
        # PRIMARY: Check for explicit completion signal (case-insensitive, 2 or more exclamation marks)
        import re
        if re.search(r'obrigado!!+', last_agent_message.lower()):
            logger.info(f"Event {event.id}: Detected explicit completion signal 'Obrigado!!' (2+ marks)")
            return True

        # SECONDARY: Check for closing phrases in agent's last message
        last_msg_lower = last_agent_message.lower()
        if any(phrase in last_msg_lower for phrase in COMPLETION_PHRASES):
            logger.info(f"Event {event.id}: Detected closing phrase in agent message")
            return True

        # TERTIARY: Check if objective appears achieved based on conversation flow
        # If agent says things like "that's it", "all done", "we're set"
        completion_indicators = [
            "that's it", "that's all", "all done", "all set",
            "we're set", "we're done", "that should do it"
        ]
        if any(indicator in last_msg_lower for indicator in completion_indicators):
            logger.info(f"Event {event.id}: Detected completion indicator in agent message")
            return True

        return False

    async def process_conversation_reply(
        self,
        event_id: int,
        sender: str,
        message_content: str
    ) -> Dict[str, Any]:
        """
        Process an incoming reply to an active conversation.

        Args:
            event_id: ID of the conversation event
            sender: Phone number/WhatsApp ID of the sender
            message_content: Content of the incoming message

        Returns:
            Dict with 'should_reply', 'reply_content', 'status' keys
        """
        event = self.get_event(event_id)

        if not event or event.event_type != 'CONVERSATION':
            raise ValueError(f"Event {event_id} is not a conversation")

        if event.status not in ['ACTIVE', 'PAUSED']:
            logger.warning(f"Conversation {event_id} is {event.status}, ignoring reply")
            return {'should_reply': False, 'status': event.status}

        # Load conversation state
        state = json.loads(event.conversation_state) if event.conversation_state else {}
        payload = json.loads(event.payload)

        # Verify sender matches expected recipient
        if sender != payload['recipient']:
            logger.warning(f"Reply from {sender} doesn't match recipient {payload['recipient']}")
            return {'should_reply': False, 'status': 'wrong_sender'}

        # Increment turn counter
        current_turn = state.get('current_turn', 1) + 1
        max_turns = payload.get('max_turns', 20)

        # Log incoming message
        self._log_conversation_message(
            event_id=event_id,
            agent_id=payload['agent_id'],
            recipient=sender,
            direction='RECEIVED',
            content=message_content,
            turn=current_turn
        )

        # Update conversation history
        if 'conversation_history' not in state:
            state['conversation_history'] = []

        state['conversation_history'].append({
            'turn': current_turn,
            'sender': 'user',
            'message': message_content,
            'timestamp': datetime.utcnow().isoformat() + "Z"
        })

        # Analyze conversation progress
        analysis = await self._analyze_conversation_progress(event, message_content, state)

        # Update state with analysis
        state['objective_progress'] = analysis['objective_progress']
        state['current_turn'] = current_turn
        state['last_activity'] = datetime.utcnow().isoformat() + "Z"

        # Check for deviations
        if analysis.get('deviation_detected'):
            state.setdefault('deviations', []).append({
                'turn': current_turn,
                'severity': analysis['deviation_severity'],
                'reason': analysis['deviation_reason'],
                'timestamp': datetime.utcnow().isoformat() + "Z"
            })

            # Handle deviation
            deviation_count = len(state['deviations'])
            deviation_threshold = payload.get('deviation_threshold', 3)

            if deviation_count >= deviation_threshold:
                if payload.get('auto_pause_on_deviation', True):
                    event.status = 'PAUSED'
                    event.requires_intervention = True
                    event.intervention_message = f"Conversation deviated {deviation_count} times. Paused for review."

                if payload.get('notify_on_deviation', True):
                    self._notify_user_intervention_needed(event, state, analysis)

                # Save state and return
                event.conversation_state = json.dumps(state)
                self.db.commit()

                return {
                    'should_reply': False,
                    'status': 'paused_deviation',
                    'deviation_count': deviation_count
                }

        # CRITICAL: Check if max turns reached BEFORE generating any reply
        # For single-turn flows (max_turns=1), we don't want ANY response after the initial message
        if current_turn > max_turns:
            # Max turns exceeded - complete WITHOUT sending any reply
            logger.info(f"Event {event_id}: Max turns ({max_turns}) exceeded (current_turn={current_turn}). Completing without reply.")

            event.status = 'COMPLETED'
            event.completed_at = datetime.utcnow()
            state['current_turn'] = current_turn
            event.conversation_state = json.dumps(state)
            self.db.commit()

            return {
                'should_reply': False,  # Don't send any reply
                'status': 'completed_max_turns'
            }

        # Check if objective achieved
        if analysis['objective_progress']['achieved']:
            # Generate closing message
            closing_message = await self._generate_closing_message(event, state)

            # Log closing message
            self._log_conversation_message(
                event_id=event_id,
                agent_id=payload['agent_id'],
                recipient=sender,
                direction='SENT',
                content=closing_message,
                turn=current_turn + 1,
                is_impersonating=payload.get('impersonate', {}).get('enabled', False),
                impersonation_identity=payload.get('impersonate', {}).get('identity')
            )

            # Mark conversation as completed
            event.status = 'COMPLETED'
            event.completed_at = datetime.utcnow()

            # Final state update
            state['conversation_history'].append({
                'turn': current_turn + 1,
                'sender': 'agent',
                'message': closing_message,
                'timestamp': datetime.utcnow().isoformat() + "Z"
            })
            state['current_turn'] = current_turn + 1

            event.conversation_state = json.dumps(state)
            self.db.commit()

            return {
                'should_reply': True,
                'reply_content': closing_message,
                'status': 'completed'
            }

        # Check if we're at max turns (will send final reply and complete)
        if current_turn == max_turns:
            # This is the last turn - send closing message
            closing_message = await self._generate_closing_message(
                event,
                state,
                reason="Maximum conversation turns reached"
            )

            self._log_conversation_message(
                event_id=event_id,
                agent_id=payload['agent_id'],
                recipient=sender,
                direction='SENT',
                content=closing_message,
                turn=current_turn + 1,
                is_impersonating=payload.get('impersonate', {}).get('enabled', False),
                impersonation_identity=payload.get('impersonate', {}).get('identity')
            )

            event.status = 'COMPLETED'
            event.completed_at = datetime.utcnow()

            state['conversation_history'].append({
                'turn': current_turn + 1,
                'sender': 'agent',
                'message': closing_message,
                'timestamp': datetime.utcnow().isoformat() + "Z"
            })
            state['current_turn'] = current_turn + 1

            event.conversation_state = json.dumps(state)
            self.db.commit()

            return {
                'should_reply': True,
                'reply_content': closing_message,
                'status': 'completed_max_turns'
            }

        # Generate agent reply (AWAIT the async method)
        agent_reply = await self._generate_agent_reply(event, message_content, state)
        if not agent_reply:
            event.status = 'PAUSED'
            event.requires_intervention = True
            event.intervention_message = "Contamination detected in AI response; conversation paused."
            event.conversation_state = json.dumps(state)
            self.db.commit()
            return {
                'should_reply': False,
                'status': 'contamination_detected'
            }

        # Log agent reply
        self._log_conversation_message(
            event_id=event_id,
            agent_id=payload['agent_id'],
            recipient=sender,
            direction='SENT',
            content=agent_reply,
            turn=current_turn + 1,
            is_impersonating=payload.get('impersonate', {}).get('enabled', False),
            impersonation_identity=payload.get('impersonate', {}).get('identity')
        )

        # Update conversation history with agent reply
        state['conversation_history'].append({
            'turn': current_turn + 1,
            'sender': 'agent',
            'message': agent_reply,
            'timestamp': datetime.utcnow().isoformat() + "Z"
        })
        state['current_turn'] = current_turn + 1

        # Check if conversation should be completed
        should_complete = self._check_conversation_completion(
            event=event,
            state=state,
            last_agent_message=agent_reply
        )

        if should_complete:
            event.status = 'COMPLETED'
            event.completed_at = datetime.utcnow()
            logger.info(f"Auto-completing conversation Event {event_id} - completion criteria met")

        # Save updated state
        event.conversation_state = json.dumps(state)
        self.db.commit()

        return {
            'should_reply': True,
            'reply_content': agent_reply,
            'status': 'completed' if should_complete else 'active'
        }

    async def _analyze_conversation_progress(
        self,
        event: ScheduledEvent,
        last_message: str,
        state: Dict
    ) -> Dict[str, Any]:
        """
        Analyze conversation progress using AI.

        Returns:
            Dict with objective_progress, deviation_detected, etc.
        """
        from agent.ai_client import AIClient

        payload = json.loads(event.payload)
        objective = payload['objective']
        context = payload.get('context', {})
        conversation_history = state.get('conversation_history', [])

        # Build analysis prompt
        history_text = "\n".join([
            f"Turn {msg['turn']} ({msg['sender']}): {msg['message']}"
            for msg in conversation_history[-10:]  # Last 10 messages
        ])

        prompt = f"""You are analyzing an autonomous conversation.

**Objective**: {objective}

**Context**: {json.dumps(context)}

**Conversation History**:
{history_text}

**Latest Message from User**: {last_message}

Analyze the conversation and respond with JSON:
{{
  "objective_progress": {{
    "achieved": true/false,
    "confidence": 0-100,
    "notes": "explanation of progress"
  }},
  "deviation_detected": true/false,
  "deviation_severity": "low/medium/high",
  "deviation_reason": "why conversation deviated from objective",
  "suggested_next_action": "what agent should do next"
}}

Important:
- objective_progress.achieved should be true ONLY if the objective is fully completed
- deviation_detected should be true if conversation went off-topic
- Be realistic about confidence scores"""

        try:
            # Get agent's AI configuration
            agent = self.db.query(Agent).get(payload['agent_id'])
            if not agent:
                raise ValueError(f"Agent {payload['agent_id']} not found")

            # Create AI client
            ai_client = AIClient(
                provider=agent.model_provider,
                model_name=agent.model_name,
                db=self.db
            )

            # Get analysis (AWAIT the async method)
            response = await ai_client.generate(
                system_prompt="You are a conversation analysis assistant. Always respond with valid JSON.",
                user_message=prompt
            )

            # Parse JSON response - response is a dict with 'answer' key
            answer = response.get('answer', '{}')
            analysis = json.loads(answer)

            return analysis

        except Exception as e:
            logger.error(f"Error analyzing conversation: {e}", exc_info=True)

            # Fallback analysis
            return {
                'objective_progress': {
                    'achieved': False,
                    'confidence': 0.0,
                    'notes': f"Analysis failed: {str(e)}"
                },
                'deviation_detected': False,
                'deviation_severity': 'low',
                'deviation_reason': None,
                'suggested_next_action': 'Continue conversation normally'
            }

    async def _generate_agent_reply(
        self,
        event: ScheduledEvent,
        user_message: str,
        state: Dict
    ) -> str:
        """
        Generate agent's reply using AI.

        Args:
            event: Conversation event
            user_message: Latest user message
            state: Conversation state

        Returns:
            Agent's reply message
        """
        from agent.ai_client import AIClient

        payload = json.loads(event.payload)
        objective = payload['objective']
        context = payload.get('context', {})
        impersonate = payload.get('impersonate', {'enabled': False})
        conversation_history = state.get('conversation_history', [])

        # Load persona if specified (CRITICAL: same logic as opening message)
        persona_text = ""
        if payload.get('persona_id'):
            persona = self.db.query(Persona).get(payload['persona_id'])
            if persona:
                # Build comprehensive persona profile
                profile_parts = []

                # Use AI summary if available, otherwise use description
                if persona.ai_summary:
                    profile_parts.append(persona.ai_summary)
                elif persona.description:
                    profile_parts.append(persona.description)

                # Add role and role description if available
                if persona.role:
                    profile_parts.append(f"\nRole: {persona.role}")
                if persona.role_description:
                    profile_parts.append(f"\n{persona.role_description}")

                # Add personality traits if available
                if persona.personality_traits:
                    profile_parts.append(f"\nPersonality: {persona.personality_traits}")

                # Add guardrails if available
                if persona.guardrails:
                    profile_parts.append(f"\nGuidelines: {persona.guardrails}")

                persona_text = f"\n\nPERSONA PROFILE:\n{chr(10).join(profile_parts)}\n"

        # Item 11.1-11.3: Retrieve semantic memory context if memory_manager available
        semantic_context_text = ""
        if self.memory_manager and payload.get('use_semantic_memory', True):
            try:
                agent_id = payload['agent_id']
                recipient = payload['recipient']

                # Item 11.3: Get semantic context including learned facts
                semantic_context = await self.memory_manager.get_context(
                    agent_id=agent_id,
                    sender_key=recipient,
                    current_message=user_message,
                    max_semantic_results=payload.get('semantic_max_results', 5),
                    similarity_threshold=payload.get('semantic_threshold', 0.3),
                    include_knowledge=True,  # Item 11.3: Include learned facts
                    include_shared=payload.get('include_shared_memory', False),
                    whatsapp_id=recipient,  # For contact resolution
                    use_contact_mapping=True
                )

                # Format semantic context for the prompt
                if semantic_context:
                    agent_memory = self.memory_manager.get_agent_memory(agent_id)
                    semantic_context_text = agent_memory.format_context_for_prompt(semantic_context)

                    logger.info(f"[CONVERSATION] Semantic memory retrieved: {len(semantic_context_text)} chars")

                    # Item 11.5: Track memory usage in state
                    if 'memory_usage' not in state:
                        state['memory_usage'] = []
                    state['memory_usage'].append({
                        'turn': len(conversation_history) + 1,
                        'semantic_results': len(semantic_context.get('semantic_results', [])),
                        'facts_count': len(semantic_context.get('learned_facts', [])),
                        'context_size': len(semantic_context_text)
                    })
            except Exception as e:
                logger.warning(f"[CONVERSATION] Failed to retrieve semantic memory: {e}")
                semantic_context_text = ""

        # Build conversation context with clear role labels
        # Include ALL conversation history so AI has full context
        history_text = "\n".join([
            f"{'You (in previous turn)' if msg['sender'] == 'agent' else 'User'}: {msg['message']}"
            for msg in conversation_history  # All messages for consistency
        ])

        # Build system prompt
        if payload.get('custom_system_prompt'):
            # Use custom prompt if provided
            system_prompt = payload['custom_system_prompt']
            if persona_text:
                system_prompt = system_prompt + persona_text
            # Add completion signal instruction
            system_prompt += "\n\nIMPORTANT: When the conversation objective is fully achieved and you're closing the conversation, end your message with EXACTLY: 'Obrigado!!!'"
        elif persona_text:
            # If persona provided, use persona-focused prompt
            system_prompt = f"""You are conducting a conversation to achieve this objective: {objective}

Context: {json.dumps(context)}
{persona_text}

CRITICAL RULES FOR THIS CONVERSATION:
1. Use ONLY the exact information from your PERSONA PROFILE above (names, email, CPF, etc.)
2. DO NOT make up, change, or hallucinate ANY data - use EXACT values from the persona
3. Review your previous responses to maintain consistency throughout the conversation
4. If you already provided information in an earlier turn, use THE SAME VALUES
5. Be authentic and natural while staying consistent
6. Work towards the objective conversationally

CRITICAL - Conversation Completion:
When the conversation objective is fully achieved and you're closing the conversation, end your message with EXACTLY: 'Obrigado!!!'"""
        elif impersonate.get('enabled'):
            identity = impersonate.get('identity', 'myself')
            system_prompt = f"""You are {identity}. You are conducting a conversation to achieve this objective: {objective}

Context: {json.dumps(context)}

Important:
- Stay in character as {identity}
- Keep responses natural and conversational
- Work towards the objective without being too direct
- If objective is achieved, acknowledge it naturally

CRITICAL - Conversation Completion:
When the conversation objective is fully achieved and you're closing the conversation, end your message with EXACTLY: 'Obrigado!!!'"""
        else:
            user_name = context.get('user_name', 'my client')
            system_prompt = f"""You are an assistant messaging on behalf of {user_name}. Your objective: {objective}

Context: {json.dumps(context)}

Important:
- Be professional and helpful
- Work towards the objective
- Keep responses concise
- If objective is achieved, acknowledge it naturally

CRITICAL - Conversation Completion:
When the conversation objective is fully achieved and you're closing the conversation, end your message with EXACTLY: 'Obrigado!!!'"""

        # Item 11.2: Build prompt with semantic context merged with conversation history
        prompt_parts = []

        # Add semantic context first (broader historical context)
        if semantic_context_text and semantic_context_text != "[No previous context]":
            prompt_parts.append(f"SEMANTIC MEMORY (Past interactions and learned facts):\n{semantic_context_text}\n")

        # Add recent conversation history (immediate context)
        prompt_parts.append(f"Previous conversation:\n{history_text}\n")

        # Add current message
        prompt_parts.append(f"User's latest message: {user_message}\n")

        # Add instructions
        prompt_parts.append("""
CRITICAL INSTRUCTIONS:
1. Review YOUR previous responses above (marked as "You (in previous turn)")
2. Maintain consistency with ALL information you already provided (names, email, CPF, etc.)
3. NEVER contradict or change information you already gave
4. If you already provided a name/email/CPF, use THE SAME VALUES
5. Use information from semantic memory to enhance your responses with past knowledge
6. Continue the conversation naturally based on what you've already said

Generate your reply to continue working towards the objective.""")

        prompt = "\n".join(prompt_parts)

        try:
            # Get agent's AI configuration
            agent = self.db.query(Agent).get(payload['agent_id'])
            if not agent:
                raise ValueError(f"Agent {payload['agent_id']} not found")

            # Create AI client
            ai_client = AIClient(
                provider=agent.model_provider,
                model_name=agent.model_name,
                db=self.db
            )

            # Generate reply (AWAIT and use correct parameters)
            response = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=prompt
            )

            # Extract the text (AIClient returns {'answer': ..., 'token_usage': ..., 'error': ...})
            if isinstance(response, dict) and 'answer' in response:
                reply = response['answer']
            else:
                reply = str(response)

            return self._sanitize_ai_reply(payload['agent_id'], reply)

        except Exception as e:
            logger.error(f"Error generating agent reply: {e}", exc_info=True)

            # Fallback reply
            return f"I understand. Let me check on that and get back to you."

    async def _generate_opening_message(
        self,
        agent: Agent,
        objective: str,
        context: Dict,
        impersonate: Dict,
        payload: Dict = None,
        is_single_turn: bool = False
    ) -> str:
        """
        Generate opening message using AI.

        For single-turn flows (is_single_turn=True):
            - COMPLETE the entire objective in ONE message
            - Don't just introduce, actually DO the task
            - Example: If objective is "tell a joke", message should contain the actual joke

        For multi-turn flows (is_single_turn=False):
            - Generate conversational opening to START working towards objective
            - Natural conversation starter
            - Work towards objective over multiple turns

        Args:
            agent: Agent model
            objective: Conversation objective (internal instruction)
            context: Context information
            impersonate: Impersonation settings
            payload: Full payload with persona_id and custom_system_prompt
            is_single_turn: True if max_turns=1 (complete objective in this message)

        Returns:
            Opening message (completes objective if single-turn)
        """
        from agent.ai_client import AIClient

        # Get agent's contact name
        agent_contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
        agent_name = agent_contact.friendly_name if agent_contact else 'the assistant'

        user_name = context.get('user_name', agent_name)
        tone = context.get('tone', 'professional')

        # Load persona if specified
        persona_text = ""
        if payload and payload.get('persona_id'):
            persona = self.db.query(Persona).get(payload['persona_id'])
            if persona:
                # Build comprehensive persona profile
                profile_parts = []

                # Use AI summary if available, otherwise use description
                if persona.ai_summary:
                    profile_parts.append(persona.ai_summary)
                elif persona.description:
                    profile_parts.append(persona.description)

                # Add role and role description if available
                if persona.role:
                    profile_parts.append(f"\nRole: {persona.role}")
                if persona.role_description:
                    profile_parts.append(f"\n{persona.role_description}")

                # Add personality traits if available
                if persona.personality_traits:
                    profile_parts.append(f"\nPersonality: {persona.personality_traits}")

                # Add guardrails if available
                if persona.guardrails:
                    profile_parts.append(f"\nGuidelines: {persona.guardrails}")

                persona_text = f"\n\nPERSONA PROFILE:\n{chr(10).join(profile_parts)}\n"

        # Check for custom system prompt
        custom_prompt = payload.get('custom_system_prompt') if payload else None

        # Build system prompt based on single-turn vs multi-turn
        if is_single_turn:
            # SINGLE-TURN: Complete the entire objective in ONE message
            if custom_prompt:
                system_prompt = custom_prompt
                if persona_text:
                    system_prompt = system_prompt + persona_text
            elif persona_text:
                system_prompt = f"""SINGLE-TURN MESSAGE: Complete this entire task in ONE message: {objective}

Context: {json.dumps(context)}
{persona_text}

CRITICAL:
- This is a single-turn flow - you will NOT get another chance to respond
- COMPLETE the full objective in this ONE message
- If objective is "tell a joke", include the actual joke NOW
- If objective is "ask a question", ask it NOW
- Don't just introduce - actually DO the task completely
- Use a {tone} tone"""
            elif impersonate.get('enabled'):
                identity = impersonate.get('identity', user_name)
                system_prompt = f"""You are {identity}. SINGLE-TURN MESSAGE: Complete this task in ONE message: {objective}

CRITICAL:
- This is your ONLY message - complete the full objective NOW
- If objective is "tell a joke", include the actual joke
- Don't just introduce - actually DO it
- Use a {tone} tone"""
            else:
                system_prompt = f"""You are messaging on behalf of {user_name}. SINGLE-TURN MESSAGE: Complete this task in ONE message: {objective}

CRITICAL:
- This is your ONLY message - complete the full objective NOW
- If objective is "tell a joke", include the actual joke in this message
- If objective is "ask a question", ask it NOW
- Don't just introduce or hint - actually DO the task completely
- Use a {tone} tone"""
        else:
            # MULTI-TURN: Generate conversational opening to START working towards objective
            if custom_prompt:
                # Use custom prompt but still inject persona if provided
                system_prompt = custom_prompt
                if persona_text:
                    system_prompt = system_prompt + persona_text
            elif persona_text:
                # If persona is provided (but no custom prompt), use persona-focused prompt
                system_prompt = f"""Generate a natural, conversational opening message to start this interaction.

Requirements:
- Be authentic and natural
- DO NOT reveal the full objective/instruction
- Start the conversation naturally to achieve: {objective}
- Use a {tone} tone
- Keep it brief (1-2 sentences)
- Be conversational, not robotic

IMPORTANT - Conversation Completion:
When the conversation objective is fully achieved, end your message with one of these keywords:
- "completo"
- "finalizado"
- "concluído"
- "objetivo atingido"
This signals the system that the conversation can be marked as complete.{persona_text}"""
            elif impersonate.get('enabled'):
                identity = impersonate.get('identity', user_name)
                system_prompt = f"""You are {identity}. Generate a natural, conversational opening message.

Requirements:
- Be authentic and natural as {identity}
- DO NOT reveal the full objective/instruction
- Start the conversation naturally to achieve: {objective}
- Use a {tone} tone
- Keep it brief (1-2 sentences)
- Be conversational, not robotic

IMPORTANT - Conversation Completion:
When the conversation objective is fully achieved, end your message with one of these keywords:
- "completo"
- "finalizado"
- "concluído"
- "objetivo atingido"
This signals the system that the conversation can be marked as complete."""
            else:
                system_prompt = f"""You are messaging on behalf of {user_name}. Generate a natural, professional opening message.

Requirements:
- Be professional and friendly
- DO NOT reveal the full objective/instruction
- Start the conversation naturally to achieve: {objective}
- Use a {tone} tone
- Keep it brief (1-2 sentences)

IMPORTANT - Conversation Completion:
When the conversation objective is fully achieved, end your message with one of these keywords:
- "completo"
- "finalizado"
- "concluído"
- "objetivo atingido"
This signals the system that the conversation can be marked as complete."""

        # Build user prompt
        if is_single_turn:
            prompt = f"""COMPLETE THIS TASK ENTIRELY IN YOUR RESPONSE: {objective}

Context: {json.dumps(context)}

IMPORTANT: This is a single-turn message. You will NOT get another chance to respond.
- If the task is "tell a joke", your message MUST contain the actual joke
- If the task is "ask a question", your message MUST contain the question
- COMPLETE the objective fully in this ONE message

Generate ONLY the message text - no quotes, no explanations."""
        else:
            prompt = f"""Generate a natural opening message to start this conversation.

Internal objective (DO NOT copy verbatim): {objective}

Context: {json.dumps(context)}

Generate ONLY the message text - no quotes, no explanations."""

        try:
            # Create AI client
            ai_client = AIClient(
                provider=agent.model_provider,
                model_name=agent.model_name,
                db=self.db
            )

            # Generate opening (AWAIT the coroutine)
            response = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=prompt
            )

            # Extract the text response (AIClient returns {'answer': ..., 'token_usage': ..., 'error': ...})
            if isinstance(response, dict) and 'answer' in response:
                opening = response['answer']
            else:
                opening = str(response)

            return self._sanitize_ai_reply(agent.id, opening)

        except Exception as e:
            logger.error(f"Error generating opening message: {e}", exc_info=True)

            # Fallback: Still better than raw objective
            if impersonate.get('enabled'):
                identity = impersonate.get('identity', user_name)
                return f"Hey! Quick question for you."
            else:
                return f"Hi! I have a quick question on behalf of {user_name}."

    async def _generate_closing_message(
        self,
        event: ScheduledEvent,
        state: Dict,
        reason: str = None
    ) -> str:
        """
        Generate closing message for conversation completion.

        Args:
            event: Conversation event
            state: Conversation state
            reason: Optional reason for closing (e.g., "max turns reached")

        Returns:
            Closing message
        """
        from agent.ai_client import AIClient

        payload = json.loads(event.payload)
        objective = payload['objective']
        context = payload.get('context', {})
        impersonate = payload.get('impersonate', {'enabled': False})
        conversation_history = state.get('conversation_history', [])

        # Build history
        history_text = "\n".join([
            f"{msg['sender']}: {msg['message']}"
            for msg in conversation_history[-5:]  # Last 5 messages
        ])

        # Build prompt
        if reason:
            prompt_context = f"The conversation is ending because: {reason}"
        else:
            prompt_context = "The objective has been achieved."

        if impersonate.get('enabled'):
            identity = impersonate.get('identity', 'myself')
            prompt = f"""You are {identity}. {prompt_context}

Recent conversation:
{history_text}

Generate a brief, natural closing message. Thank them and wrap up the conversation."""
        else:
            user_name = context.get('user_name', 'my client')
            prompt = f"""You are messaging on behalf of {user_name}. {prompt_context}

Recent conversation:
{history_text}

Generate a brief, professional closing message. Thank them and confirm completion if objective was achieved."""

        try:
            # Get agent configuration
            agent = self.db.query(Agent).get(payload['agent_id'])
            if not agent:
                raise ValueError(f"Agent {payload['agent_id']} not found")

            # Create AI client
            ai_client = AIClient(
                provider=agent.model_provider,
                model_name=agent.model_name,
                db=self.db
            )

            # Generate closing (AWAIT the async method)
            response = await ai_client.generate(
                system_prompt="You are a helpful assistant. Generate brief, natural closing messages.",
                user_message=prompt
            )

            # Extract the answer from the response dict
            closing = response.get('answer', '')
            return self._sanitize_ai_reply(payload['agent_id'], closing)

        except Exception as e:
            logger.error(f"Error generating closing message: {e}", exc_info=True)

            # Fallback closing
            if impersonate.get('enabled'):
                return "Thanks for your time! Talk soon."
            else:
                return "Thank you for your time. We'll be in touch if needed."

    def _notify_user_intervention_needed(
        self,
        event: ScheduledEvent,
        state: Dict,
        analysis: Dict
    ):
        """
        Notify user that conversation needs intervention.

        Args:
            event: Conversation event
            state: Conversation state
            analysis: Analysis results with deviation info
        """
        payload = json.loads(event.payload)

        # Build notification message
        notification = f"""🚨 Conversation Intervention Needed

Conversation ID: {event.id}
Recipient: {payload['recipient']}
Objective: {payload['objective']}

Deviation Detected: {analysis.get('deviation_severity', 'unknown')} severity
Reason: {analysis.get('deviation_reason', 'Unknown')}

Deviation Count: {len(state.get('deviations', []))}

Current Turn: {state.get('current_turn', 0)}

The conversation has been PAUSED. Please review and provide guidance."""

        # TODO: When MCP sender is available, send notification to creator
        # For now, log it
        logger.warning(f"Intervention needed for conversation {event.id}")
        logger.warning(notification)

        # Store notification in event
        event.intervention_message = notification

    async def provide_conversation_guidance(
        self,
        event_id: int,
        guidance_message: str
    ) -> Dict[str, Any]:
        """
        Provide user guidance to a paused conversation.

        Args:
            event_id: Conversation event ID
            guidance_message: User's guidance/instructions

        Returns:
            Dict with status and next suggested reply
        """
        event = self.get_event(event_id)

        if not event or event.event_type != 'CONVERSATION':
            raise ValueError(f"Event {event_id} is not a conversation")

        if event.status != 'PAUSED':
            raise ValueError(f"Conversation {event_id} is not paused")

        # Load state
        state = json.loads(event.conversation_state) if event.conversation_state else {}
        payload = json.loads(event.payload)

        # Add guidance to state
        if 'user_guidance' not in state:
            state['user_guidance'] = []

        state['user_guidance'].append({
            'turn': state.get('current_turn', 0),
            'guidance': guidance_message,
            'timestamp': datetime.utcnow().isoformat() + "Z"
        })

        # Generate suggested reply incorporating guidance
        from agent.ai_client import AIClient

        conversation_history = state.get('conversation_history', [])
        history_text = "\n".join([
            f"{msg['sender']}: {msg['message']}"
            for msg in conversation_history[-5:]
        ])

        prompt = f"""The conversation was paused due to deviation from objective.

Objective: {payload['objective']}

Recent conversation:
{history_text}

User guidance: {guidance_message}

Generate a message to get the conversation back on track towards the objective, incorporating the user's guidance."""

        try:
            agent = self.db.query(Agent).get(payload['agent_id'])
            ai_client = AIClient(
                provider=agent.model_provider,
                model_name=agent.model_name,
                db=self.db
            )

            response = await ai_client.generate(
                system_prompt="Generate a helpful message to redirect conversation towards the objective.",
                user_message=prompt
            )

            suggested_reply = self._sanitize_ai_reply(payload['agent_id'], response.get('answer', ''))
            if not suggested_reply:
                return {
                    'status': 'error',
                    'message': 'Contamination detected in guidance reply'
                }

            # Resume conversation
            event.status = 'ACTIVE'
            event.requires_intervention = False
            event.conversation_state = json.dumps(state)
            self.db.commit()

            return {
                'status': 'resumed',
                'suggested_reply': suggested_reply,
                'message': 'Conversation resumed with guidance applied'
            }

        except Exception as e:
            logger.error(f"Error providing guidance: {e}", exc_info=True)

            return {
                'status': 'error',
                'message': str(e)
            }
