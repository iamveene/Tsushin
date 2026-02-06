"""
Phase 6.4 Week 5: Scheduler Query Skill

Allows agents to query scheduled events via natural language.
Supports listing, filtering, and summarizing scheduled events.
"""

from .base import BaseSkill, InboundMessage, SkillResult
from typing import Dict, Any, List
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class SchedulerQuerySkill(BaseSkill):
    """
    Skill for querying scheduled events via natural language.

    Detects query intent and retrieves scheduled events with formatting.
    """

    skill_type = "scheduler_query"
    skill_name = "Scheduler Query"
    skill_description = "Query and list scheduled events via natural language"
    execution_mode = "legacy"  # Query functionality merged into SchedulerSkill's list action

    # Query detection keywords
    QUERY_KEYWORDS = [
        "list", "show", "what", "which", "tell me about",
        "listar", "mostrar", "quais", "qual",
        "scheduled", "agendado", "agendados",
        "upcoming", "próximo", "próximos",
        "my events", "meus eventos",
        "my reminders", "meus lembretes",
        "my conversations", "minhas conversas",
        "what's scheduled", "o que está agendado"
    ]

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Detect if message contains query intent.

        Returns True if message contains query keywords AND scheduler-related terms.
        """
        body_lower = message.body.lower()

        # Must contain both a query keyword and a scheduler term
        has_query = any(keyword in body_lower for keyword in self.QUERY_KEYWORDS)
        has_scheduler_term = any(term in body_lower for term in [
            'schedule', 'agendar', 'event', 'evento',
            'reminder', 'lembrete', 'notification', 'notific',
            'conversation', 'conversa', 'message', 'mensagem'
        ])

        if has_query and has_scheduler_term:
            logger.info(f"SchedulerQuerySkill: Detected query intent in message")
            return True

        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process query request.

        Extracts filter criteria and retrieves matching events.
        """
        try:
            logger.info(f"SchedulerQuerySkill: Processing query: {message.body}")

            # Parse query intent
            filters = await self._parse_query(message.body, config)

            # Query events
            from scheduler.scheduler_service import SchedulerService
            from models import ScheduledEvent
            from sqlalchemy.orm import sessionmaker
            from db import get_engine
            import os

            engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
            SessionLocal = sessionmaker(bind=engine)
            db = SessionLocal()

            try:
                # Build query
                query = db.query(ScheduledEvent)

                # Apply filters
                if filters.get('event_type'):
                    query = query.filter(ScheduledEvent.event_type == filters['event_type'].upper())

                if filters.get('status'):
                    query = query.filter(ScheduledEvent.status == filters['status'].upper())
                elif filters.get('upcoming_only', True):
                    # Default to showing upcoming events (PENDING or ACTIVE)
                    query = query.filter(ScheduledEvent.status.in_(['PENDING', 'ACTIVE']))

                # Sort by scheduled time
                query = query.order_by(ScheduledEvent.scheduled_at.asc())

                # Limit
                limit = filters.get('limit', 10)
                events = query.limit(limit).all()

                # Format response
                formatted_response = self._format_events(events, filters)

                return SkillResult(
                    success=True,
                    output=formatted_response,
                    metadata={
                        'event_count': len(events),
                        'filters': filters
                    },
                    processed_content=formatted_response
                )

            finally:
                db.close()

        except Exception as e:
            logger.error(f"SchedulerQuerySkill: Error processing: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Sorry, I couldn't retrieve the scheduled events. Error: {str(e)}",
                metadata={'error': str(e)}
            )

    async def _parse_query(self, text: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse query intent to extract filter criteria.

        Returns dict with:
        - event_type: str or None (CONVERSATION, NOTIFICATION, MESSAGE, TASK)
        - status: str or None (PENDING, ACTIVE, COMPLETED, etc.)
        - upcoming_only: bool
        - limit: int
        """
        text_lower = text.lower()

        filters = {
            'event_type': None,
            'status': None,
            'upcoming_only': True,
            'limit': 10
        }

        # Detect event type
        if any(word in text_lower for word in ['conversation', 'conversa']):
            filters['event_type'] = 'CONVERSATION'
        elif any(word in text_lower for word in ['notification', 'notific', 'reminder', 'lembrete']):
            filters['event_type'] = 'NOTIFICATION'
        elif any(word in text_lower for word in ['message', 'mensagem']):
            filters['event_type'] = 'MESSAGE'
        elif any(word in text_lower for word in ['task', 'tarefa']):
            filters['event_type'] = 'TASK'

        # Detect status
        if any(word in text_lower for word in ['active', 'ativo', 'ongoing', 'em andamento']):
            filters['status'] = 'ACTIVE'
        elif any(word in text_lower for word in ['pending', 'pendente', 'upcoming', 'próximo']):
            filters['status'] = 'PENDING'
        elif any(word in text_lower for word in ['completed', 'concluído', 'done', 'feito']):
            filters['status'] = 'COMPLETED'
            filters['upcoming_only'] = False
        elif any(word in text_lower for word in ['all', 'todos', 'everything', 'tudo']):
            filters['upcoming_only'] = False

        # Detect limit
        import re
        limit_match = re.search(r'(\d+)\s*(?:event|evento|item|reminder)', text_lower)
        if limit_match:
            filters['limit'] = min(int(limit_match.group(1)), 50)  # Cap at 50

        return filters

    def _format_events(self, events: List, filters: Dict[str, Any]) -> str:
        """Format events as human-readable text"""
        if not events:
            filter_desc = ""
            if filters.get('event_type'):
                filter_desc = f" {filters['event_type'].lower()}"
            return f"📅 No{filter_desc} events found."

        # Build response
        lines = []

        # Header
        event_type_desc = f" {filters['event_type'].lower()}" if filters.get('event_type') else ""
        lines.append(f"📅 Found {len(events)}{event_type_desc} event(s):\n")

        # List events
        for i, event in enumerate(events, 1):
            lines.append(self._format_single_event(i, event))

        return "\n".join(lines)

    def _format_single_event(self, number: int, event) -> str:
        """Format a single event"""
        # Parse payload
        try:
            payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
        except:
            payload = {}

        # Format time
        scheduled_time = event.scheduled_at.strftime('%Y-%m-%d %I:%M %p')

        # Build description
        lines = [f"{number}. {event.event_type} #{event.id} - {event.status}"]

        if event.event_type == 'CONVERSATION':
            recipient = payload.get('recipient', 'Unknown')
            objective = payload.get('objective', 'No objective')
            lines.append(f"   To: {recipient}")
            lines.append(f"   Objective: {objective}")
            lines.append(f"   Scheduled: {scheduled_time}")

            # Add conversation progress if ACTIVE
            if event.status == 'ACTIVE' and event.conversation_state:
                try:
                    state = json.loads(event.conversation_state) if isinstance(event.conversation_state, str) else event.conversation_state
                    turn = state.get('current_turn', 0)
                    progress = state.get('objective_progress', {})
                    confidence = progress.get('confidence', 0)
                    lines.append(f"   Progress: Turn {turn}, {confidence}% confident")
                except:
                    pass

        elif event.event_type == 'NOTIFICATION':
            recipient = payload.get('recipient_raw', 'Unknown')
            reminder = payload.get('reminder_text', 'No reminder')
            lines.append(f"   To: {recipient}")
            lines.append(f"   Reminder: {reminder}")
            lines.append(f"   Scheduled: {scheduled_time}")

            # Check for recurrence
            if event.recurrence_rule:
                try:
                    recurrence = json.loads(event.recurrence_rule) if isinstance(event.recurrence_rule, str) else event.recurrence_rule
                    freq = recurrence.get('frequency', 'daily')
                    lines.append(f"   Recurs: {freq}")
                except:
                    pass

        elif event.event_type == 'MESSAGE':
            recipient = payload.get('recipient', 'Unknown')
            content = payload.get('content', '')[:50]  # Truncate
            lines.append(f"   To: {recipient}")
            if content:
                lines.append(f"   Content: {content}...")
            lines.append(f"   Scheduled: {scheduled_time}")

        else:  # TASK or other
            lines.append(f"   Scheduled: {scheduled_time}")

        return "\n".join(lines)

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """Default configuration"""
        return {
            'default_limit': 10
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Configuration schema"""
        return {
            "type": "object",
            "properties": {
                "default_limit": {
                    "type": "integer",
                    "description": "Default number of events to return",
                    "default": 10
                }
            },
            "required": []
        }
