"""
Phase 6.4 Week 5: Scheduler Skill

Allows agents to schedule events via natural language.
Supports scheduling reminders (NOTIFICATION) and AI-driven conversations (CONVERSATION).

For scheduled messages and tool execution, use the Flows feature.

Enhanced with:
- Portuguese natural language date parsing (dateparser)
- GMT-3 timezone handling (Brazil/São Paulo timezone)
- Robust date/time extraction
- Contact resolution for @mentions and names
"""

from .base import BaseSkill, InboundMessage, SkillResult
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import re
import json
import logging
import dateparser
import pytz

logger = logging.getLogger(__name__)

# Brazil timezone (GMT-3)
BRAZIL_TZ = pytz.timezone('America/Sao_Paulo')


class SchedulerSkill(BaseSkill):
    """
    Skill for scheduling events via natural language.

    Detects scheduling intent and creates scheduled events.
    Supports NOTIFICATION (reminders) and CONVERSATION (AI-driven conversations).
    For scheduled messages and tool execution, use the Flows feature.
    """

    skill_type = "scheduler"
    skill_name = "Scheduler"
    skill_description = "Schedule reminders and AI-driven conversations via natural language"
    execution_mode = "hybrid"  # Supports both keywords and AI tool calls

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        MCP-compliant tool definition for scheduling events.

        Works with multiple providers: Flows (built-in), Google Calendar, Asana.
        """
        return {
            "name": "schedule_event",
            "title": "Event Scheduler",
            "description": (
                "Schedule reminders, notifications, and events. "
                "Supports natural language time expressions like 'tomorrow at 3pm' or 'in 2 hours'. "
                "Can create new events or list existing ones. "
                "Works with Flows (built-in), Google Calendar, or Asana depending on configuration."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list"],
                        "description": "Action to perform: 'create' a new event or 'list' existing events"
                    },
                    "event_type": {
                        "type": "string",
                        "enum": ["NOTIFICATION", "CONVERSATION"],
                        "description": (
                            "For create action: "
                            "NOTIFICATION = one-time reminder message, "
                            "CONVERSATION = multi-turn AI conversation with objective"
                        )
                    },
                    "title": {
                        "type": "string",
                        "description": "For create: What to remind about or conversation objective"
                    },
                    "time_expression": {
                        "type": "string",
                        "description": (
                            "When to schedule. Accepts: "
                            "natural language ('tomorrow at 3pm', 'in 2 hours', 'next Monday'), "
                            "ISO 8601 ('2024-03-15T14:00:00'), "
                            "or relative ('in 30 minutes')"
                        )
                    },
                    "recipient": {
                        "type": "string",
                        "description": (
                            "For create: Who receives the notification/conversation. "
                            "Can be phone number, contact name, or 'me' for self-reminders."
                        )
                    },
                    "recurrence": {
                        "type": "string",
                        "enum": ["none", "daily", "weekly", "monthly"],
                        "description": "Recurrence pattern (default: none)"
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "For list action: Show events up to N days ahead (default: 7)",
                        "default": 7
                    }
                },
                "required": ["action"]
            },
            "annotations": {
                "destructive": False,
                "idempotent": False
            }
        }

    # Intent detection keywords (Phase 6.11.3: Made more specific to reduce false positives)
    # TODO: Replace with @mention-based triggering via dedicated scheduler agent
    SCHEDULE_KEYWORDS = [
        # Portuguese - More specific phrases to avoid false positives
        "me lembre de",      # Instead of just "lembre"
        "me lembra de",      # Common variation
        "me avise",          # Alternative to "notifique"
        "agende uma",        # Instead of just "agendar"
        "agende um",         # Masculine variation
        "marque uma",        # Alternative scheduling verb
        "crie um lembrete",  # Full phrase
        "crie uma conversa", # Full phrase

        # English - More specific phrases
        "remind me to",      # Instead of just "remind"
        "remind me about",   # Variation
        "schedule a",        # Instead of just "schedule"
        "set a reminder",    # Already specific
        "create a reminder", # Already specific
        "notify me",         # Instead of just "notify"

        # Multi-word patterns (more specific)
        "conversation with", # Already specific
        "conversa com",      # Already specific
        "fale com",          # Conversation starter
        "pergunte para"      # Question starter for conversations
    ]

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Detect if message contains scheduling intent.

        Returns True if:
        - Message is routed to Agendador agent (ID 7) - ALL messages to @agendador are scheduling requests
        - Message contains scheduling keywords (for other agents)
        """
        body_lower = message.body.lower()

        # Phase 6.11.4: Removed special handling for Agendador agent
        # Asana operations are now handled through scheduler provider configuration

        # Defer to SchedulerQuerySkill if query keywords present
        agent_id = getattr(self, '_agent_id', None)
        if agent_id == 7:  # Agendador agent ID
            query_keywords = ['quais', 'meus lembretes', 'meus agendamentos', 'o que']
            if any(keyword in message.body.lower() for keyword in query_keywords):
                logger.info(f"SchedulerSkill: Query keywords detected, deferring to SchedulerQuerySkill")
                return False

            # Default: handle all other scheduling/reminder messages
            logger.info(f"SchedulerSkill: Agendador agent detected, handling message as reminder/flow")
            return True

        # Check for scheduling keywords (for other agents)
        for keyword in self.SCHEDULE_KEYWORDS:
            if keyword in body_lower:
                logger.info(f"SchedulerSkill: Detected keyword '{keyword}' in message")
                return True

        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process scheduling request.

        Handles two types of requests:
        1. CREATE: Schedule new events (conversations, notifications)
        2. LIST: Show existing scheduled events

        Routes based on AI-detected intent.
        """
        try:
            logger.info(f"SchedulerSkill: Processing message: {message.body}")

            # Detect intent using AI (CREATE vs LIST)
            intent = await self._detect_intent(message.body, config)
            logger.info(f"SchedulerSkill: Detected intent={intent}")

            if intent == 'LIST':
                return await self._handle_list_request(message, config)
            elif intent == 'CREATE':
                return await self._handle_create_request(message, config)
            else:
                return SkillResult(
                    success=False,
                    output="❌ Não entendi. Tente:\n• 'Me lembre de X em Y'\n• 'Quais são meus lembretes?'",
                    metadata={'error': 'unknown_intent', 'skip_ai': True}
                )

        except Exception as e:
            logger.error(f"SchedulerSkill: Error processing: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Sorry, I couldn't process that. Error: {str(e)}",
                metadata={'error': str(e)}
            )

    async def _detect_intent(self, text: str, config: Dict[str, Any]) -> str:
        """
        Use AI to detect user intent: CREATE or LIST.

        This avoids hardcoded keywords and handles natural language variations.
        """
        from agent.ai_client import AIClient

        # Get agent config
        agent_id = config.get('agent_id', 1)

        # Get AI model config from database
        from models import Agent
        from sqlalchemy.orm import sessionmaker
        from db import get_engine
        import os

        engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        try:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return 'UNKNOWN'

            provider = agent.model_provider
            model = agent.model_name
        finally:
            db.close()

        # Create AI client (Phase 7.4: Pass db for API key loading)
        ai_client = AIClient(provider=provider, model_name=model, db=self._db_session)

        # Intent detection prompt
        prompt = f"""Analyze this user request and determine their intent.

User request: "{text}"

Intent options:
1. **CREATE** - User wants to schedule/create a new reminder, notification, or conversation
   Examples:
   - "Me lembre de comprar pão em 2 horas"
   - "Agende uma conversa com João amanhã"
   - "Notifique Maria sobre a reunião"
   - "Remind me to call mom tomorrow"
   - "Set a reminder for 3pm"

2. **LIST** - User wants to see/view/list existing scheduled events
   Examples:
   - "Quais são meus lembretes?"
   - "Mostre meus agendamentos"
   - "Ver lembretes"
   - "Lista de eventos"
   - "Show my reminders"
   - "What do I have scheduled?"
   - "List my events"

Respond ONLY with: CREATE or LIST (no explanation, no punctuation)"""

        result = await ai_client.generate(
            system_prompt="You are an intent classifier. Respond with exactly one word: CREATE or LIST",
            user_message=prompt
        )

        intent_text = result.get('answer', 'UNKNOWN').strip().upper()

        # Extract just the intent word (in case AI adds extra text)
        if 'CREATE' in intent_text:
            return 'CREATE'
        elif 'LIST' in intent_text:
            return 'LIST'
        else:
            return 'UNKNOWN'

    async def _handle_create_request(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Handle CREATE intent: Schedule a new event.

        This is the original process() logic.
        """
        try:
            # Parse scheduling request
            parsed = await self._parse_scheduling_request(message.body, config, message.sender)

            if not parsed['success']:
                return SkillResult(
                    success=False,
                    output=parsed['error'],
                    metadata={'error': parsed['error']}
                )

            # Create simple scheduled event (NOT multi-step flow)
            from scheduler.scheduler_service import SchedulerService
            from sqlalchemy.orm import sessionmaker
            from db import get_engine
            import os

            engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
            SessionLocal = sessionmaker(bind=engine)
            db = SessionLocal()

            try:
                scheduler_service = SchedulerService(db)

                # Create scheduled event in scheduled_events table
                event = scheduler_service.create_event(
                    creator_type='AGENT',
                    creator_id=parsed['agent_id'],
                    event_type=parsed['event_type'],
                    scheduled_at=parsed['scheduled_at'],
                    payload=parsed['payload'],
                    recurrence_rule=parsed.get('recurrence_rule')
                )

                # Format confirmation message using the skill's _format_confirmation method
                confirmation = self._format_confirmation(event, parsed)

                return SkillResult(
                    success=True,
                    output=confirmation,
                    metadata={
                        'event_id': event.id,
                        'event_type': event.event_type,
                        'scheduled_at': parsed['scheduled_at'].isoformat(),
                        'skip_ai': True  # Send confirmation directly without AI processing
                    }
                )

            finally:
                db.close()

        except Exception as e:
            logger.error(f"SchedulerSkill: Error creating event: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Sorry, I couldn't schedule that. Error: {str(e)}",
                metadata={'error': str(e)}
            )

    async def _handle_list_request(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Handle LIST intent: Show existing scheduled events.
        """
        from scheduler.scheduler_service import SchedulerService
        from sqlalchemy.orm import sessionmaker
        from db import get_engine
        from models import ScheduledEvent
        import os
        import pytz

        engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()

        try:
            # Get all PENDING/ACTIVE events
            events = db.query(ScheduledEvent).filter(
                ScheduledEvent.status.in_(['PENDING', 'ACTIVE'])
            ).order_by(ScheduledEvent.scheduled_at.asc()).limit(20).all()

            if not events:
                logger.info("No scheduled events found")
                return SkillResult(
                    success=True,
                    output="Você não tem lembretes agendados no momento.",
                    metadata={'skip_ai': True, 'event_count': 0}
                )

            # Format list with Brazil timezone
            logger.info(f"Found {len(events)} scheduled events")
            lines = [f"Você tem {len(events)} lembrete(s) agendado(s):\n"]

            for event in events:
                payload = json.loads(event.payload) if isinstance(event.payload, str) else event.payload

                # Convert UTC to Brazil time
                utc_time = event.scheduled_at.replace(tzinfo=pytz.UTC)
                brazil_time = utc_time.astimezone(BRAZIL_TZ)
                time_str = brazil_time.strftime('%d/%m às %H:%M')

                # Format based on event type
                if event.event_type == 'NOTIFICATION':
                    reminder = payload.get('reminder_text', 'Lembrete')
                    recipient = payload.get('recipient_raw')
                    line = f"- [{event.id}] {reminder}"
                    if recipient:
                        line += f" (para {recipient})"
                    line += f" - {time_str}"

                elif event.event_type == 'CONVERSATION':
                    objective = payload.get('objective', 'Conversa')
                    recipient = payload.get('recipient', 'contato')
                    line = f"- [{event.id}] Conversa com {recipient}: {objective} - {time_str}"

                else:
                    line = f"- [{event.id}] {event.event_type} - {time_str}"

                lines.append(line)

            output = "\n".join(lines)
            output += "\n\nPara cancelar um lembrete, vá em: http://localhost:3030/flows"

            logger.info(f"Returning list of {len(events)} events to user")
            return SkillResult(
                success=True,
                output=output,
                metadata={'skip_ai': True, 'event_count': len(events)}
            )

        except Exception as e:
            logger.error(f"SchedulerSkill: Error listing events: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Erro ao listar lembretes: {str(e)}",
                metadata={'error': str(e)}
            )

        finally:
            db.close()

    def _parse_natural_language_datetime(self, text: str) -> Optional[datetime]:
        """
        Parse natural language date/time using dateparser with Portuguese support.

        Handles patterns like:
        - "amanhã às 14h" → tomorrow at 2pm
        - "segunda-feira" → next Monday
        - "daqui a 2 horas" → 2 hours from now
        - "15/10 às 9h30" → Oct 15 at 9:30am
        - "em 1 minuto" → 1 minute from now
        - "em 5 minutos" → 5 minutes from now

        Returns datetime in UTC (converts from GMT-3).
        """
        try:
            # Get current time in Brazil timezone
            now_brazil = datetime.now(BRAZIL_TZ)

            # Pre-process common Portuguese patterns that dateparser might miss
            # Pattern: "em X minuto(s)" or "em X segundo(s)" or "em X hora(s)"
            relative_match = re.search(r'em\s+(\d+)\s+(minuto|segundo|hora|dia)(s)?', text.lower())
            if relative_match:
                amount = int(relative_match.group(1))
                unit = relative_match.group(2)

                if unit == 'minuto':
                    parsed = now_brazil + timedelta(minutes=amount)
                elif unit == 'segundo':
                    parsed = now_brazil + timedelta(seconds=amount)
                elif unit == 'hora':
                    parsed = now_brazil + timedelta(hours=amount)
                elif unit == 'dia':
                    parsed = now_brazil + timedelta(days=amount)

                utc_time = parsed.astimezone(pytz.UTC).replace(tzinfo=None)
                logger.info(f"Parsed Portuguese relative time '{text}' → Brazil: {parsed.strftime('%Y-%m-%d %H:%M %Z')} → UTC: {utc_time}")
                return utc_time

            # Pre-process Portuguese date/time formats that dateparser struggles with
            processed_text = text

            # FIRST: Convert AM/PM to 24-hour format (before any other pattern matching)
            # Pattern: "8am" → "08:00", "8pm" → "20:00", "11am" → "11:00"
            def convert_ampm_to_24h(match):
                hour = int(match.group(1))
                ampm = match.group(2).lower()
                if ampm == 'pm' and hour < 12:
                    hour += 12
                elif ampm == 'am' and hour == 12:
                    hour = 0
                return f"{hour:02d}:00"

            # Replace all AM/PM occurrences
            processed_text = re.sub(r'\b(\d{1,2})(am|pm)\b', convert_ampm_to_24h, processed_text, flags=re.IGNORECASE)
            if processed_text != text:
                logger.info(f"Converted AM/PM: '{text}' → '{processed_text}'")

            # Pattern: "HH:MM do dia DD/MM/YYYY" or "às HH:MM do dia DD/MM/YYYY" → "DD/MM/YYYY HH:MM"
            # This must come BEFORE time-only check
            datetime_swap = re.search(r'(?:[aà]s?\s+)?(\d{1,2}):(\d{2})\s+do\s+dia\s+(\d{1,2}/\d{1,2}/\d{4})', processed_text, re.IGNORECASE)
            if datetime_swap:
                time_part = f"{datetime_swap.group(1)}:{datetime_swap.group(2)}"
                date_part = datetime_swap.group(3)
                processed_text = f"{date_part} {time_part}"
                logger.info(f"Reordered datetime: '{text}' → '{processed_text}'")

            # Pattern: "dia DD/MM as HH:MM" or "dia DD/MM/YYYY as HH:MM" (with or without "no")
            # Also handles: "dia DD/MM as HH" (without minutes)
            # Handles: "dia 02/12 as 9:00", "dia 02/12/2025 as 9:00", "dia 02/12 às 9"
            # Handles: "no dia 02/12 as 9:00" (backward compatible)
            # Manual parsing to avoid DD/MM vs MM/DD ambiguity
            dia_pattern = re.search(r'(?:no\s+)?dia\s+(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\s+[aà]s?\s+(\d{1,2})(?::(\d{2}))?', processed_text, re.IGNORECASE)
            if dia_pattern:
                day = int(dia_pattern.group(1))
                month = int(dia_pattern.group(2))
                year = int(dia_pattern.group(3)) if dia_pattern.group(3) else now_brazil.year
                hour = int(dia_pattern.group(4))
                minute = int(dia_pattern.group(5)) if dia_pattern.group(5) else 0

                # Create datetime in Brazil timezone (DD/MM/YYYY format)
                try:
                    target_time = now_brazil.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)

                    # If the date is in the past and no year was specified, try next year
                    if not dia_pattern.group(3) and target_time <= now_brazil:
                        target_time = target_time.replace(year=now_brazil.year + 1)

                    # Convert to UTC
                    utc_time = target_time.astimezone(pytz.UTC).replace(tzinfo=None)
                    logger.info(f"Parsed 'dia' format: '{text}' → Brazil: {target_time.strftime('%Y-%m-%d %H:%M %Z')} → UTC: {utc_time}")
                    return utc_time
                except ValueError as e:
                    logger.warning(f"Invalid date components in 'dia' pattern: day={day}, month={month}, year={year}, error={e}")

            # Pattern: "às HH:MM da próxima X-feira" → Don't treat as time-only
            # Check for weekday keywords before applying time-only logic
            weekday_keywords = ['segunda', 'terça', 'terca', 'quarta', 'quinta', 'sexta', 'sábado', 'sabado', 'domingo', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            has_weekday = any(day in processed_text.lower() for day in weekday_keywords)

            # Pattern: "HH hrs" or "HH horas" (hour-only format without minutes)
            # Examples: "19 hrs", "14 horas", "9 hrs"
            # Convert to "HH:00" format for consistent parsing
            hour_only_match = re.search(r'\b(\d{1,2})\s*(hrs?|horas?)\b', processed_text, re.IGNORECASE)
            if hour_only_match:
                hour = int(hour_only_match.group(1))
                # Replace "HH hrs" with "HH:00" for standard parsing
                processed_text = re.sub(r'\b(\d{1,2})\s*(hrs?|horas?)\b', r'\1:00', processed_text, flags=re.IGNORECASE)
                logger.info(f"Converted hour-only format: '{text}' → '{processed_text}'")

            # Pattern: "às HH:MM" or "as HH:MM" (time only, use today's date)
            # Only apply if NO date format AND NO weekday reference
            time_only_match = re.search(r'[aà]s?\s+(\d{1,2}):(\d{2})', processed_text, re.IGNORECASE)
            if time_only_match and not re.search(r'\d{1,2}/\d{1,2}', processed_text) and not has_weekday:
                hour = int(time_only_match.group(1))
                minute = int(time_only_match.group(2))
                target_time = now_brazil.replace(hour=hour, minute=minute, second=0, microsecond=0)

                # If time is in the past today, use tomorrow
                if target_time <= now_brazil:
                    target_time = target_time + timedelta(days=1)

                utc_time = target_time.astimezone(pytz.UTC).replace(tzinfo=None)
                logger.info(f"Parsed time-only '{text}' → Brazil: {target_time.strftime('%Y-%m-%d %H:%M %Z')} → UTC: {utc_time}")
                return utc_time

            # Pattern: "às HH:MM da próxima X-feira" → Manual parsing for weekdays
            # MUST come BEFORE removing "às" (needs it for pattern matching)
            weekday_with_time = re.search(r'[aà]s?\s+(\d{1,2}):(\d{2})\s+da\s+pr[oó]xim[ao]\s+(segunda|terça|terca|quarta|quinta|sexta|s[aá]bado|domingo)[\s-]?feira?', processed_text, re.IGNORECASE)
            if weekday_with_time:
                hour = int(weekday_with_time.group(1))
                minute = int(weekday_with_time.group(2))
                weekday_pt = weekday_with_time.group(3).lower()

                # Map to weekday number (0=Monday)
                weekday_num_map = {
                    'segunda': 0,
                    'terca': 1, 'terça': 1,
                    'quarta': 2,
                    'quinta': 3,
                    'sexta': 4,
                    'sabado': 5, 'sábado': 5,
                    'domingo': 6
                }
                target_weekday = weekday_num_map.get(weekday_pt)

                if target_weekday is not None:
                    # Calculate next occurrence of this weekday
                    current_weekday = now_brazil.weekday()
                    days_ahead = target_weekday - current_weekday
                    if days_ahead <= 0:  # Target day already passed this week
                        days_ahead += 7

                    target_date = now_brazil + timedelta(days=days_ahead)
                    target_time = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

                    utc_time = target_time.astimezone(pytz.UTC).replace(tzinfo=None)
                    logger.info(f"Parsed weekday+time '{text}' → Brazil: {target_time.strftime('%Y-%m-%d %H:%M %Z')} → UTC: {utc_time}")
                    return utc_time

            # Pattern: "DD/MM/YYYY às HH:MM" or "DD/MM/YYYY as HH:MM"
            # Convert "DD/MM/YYYY às HH:MM" to "DD/MM/YYYY HH:MM" (remove "às")
            processed_text = re.sub(r'\s+[aà]s\s+', ' ', processed_text)

            # Pattern: "próxima segunda-feira" (without specific time) - for dateparser fallback
            # Convert to "next monday" which dateparser understands better
            weekday_map = {
                'segunda-feira': 'monday',
                'segunda feira': 'monday',
                'terça-feira': 'tuesday',
                'terca-feira': 'tuesday',
                'quarta-feira': 'wednesday',
                'quinta-feira': 'thursday',
                'sexta-feira': 'friday',
                'sábado': 'saturday',
                'sabado': 'saturday',
                'domingo': 'sunday'
            }
            for pt_day, en_day in weekday_map.items():
                if f'próxima {pt_day}' in processed_text.lower() or f'proxima {pt_day}' in processed_text.lower():
                    # Replace entire phrase
                    pattern = r'pr[oó]xim[ao]\s+' + pt_day.replace('-', r'[-\s]?')
                    processed_text = re.sub(pattern, f'next {en_day}', processed_text, flags=re.IGNORECASE)
                    logger.info(f"Translated weekday: '{text}' → '{processed_text}'")
                    break

            # Try dateparser with preprocessed text
            parsed = dateparser.parse(
                processed_text,
                languages=['pt', 'en'],
                settings={
                    'TIMEZONE': 'America/Sao_Paulo',
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': now_brazil,
                    'PREFER_DAY_OF_MONTH': 'first',
                    'STRICT_PARSING': False
                }
            )

            if parsed:
                # Ensure it's in the future
                if parsed <= now_brazil:
                    # If parsed date is in the past, try adding appropriate time
                    # (e.g., if user says "segunda-feira 9h30" and it's already Monday, use next Monday)
                    if 'semana' not in text.lower() and 'week' not in text.lower():
                        # Add 1 week if it's a weekday and already passed
                        parsed = parsed + timedelta(days=7)

                # Convert to UTC for storage
                utc_time = parsed.astimezone(pytz.UTC).replace(tzinfo=None)
                logger.info(f"Parsed '{text}' → Brazil: {parsed.strftime('%Y-%m-%d %H:%M %Z')} → UTC: {utc_time}")
                return utc_time

            return None
        except Exception as e:
            logger.warning(f"Failed to parse datetime '{text}': {e}")
            return None

    async def _ai_parse_datetime(self, text: str, config: Dict[str, Any]) -> Optional[datetime]:
        """
        Use AI to parse date/time when traditional parsing fails.

        This is a fallback method that uses the AI model to understand
        complex date/time expressions that dateparser might struggle with.

        Returns datetime in UTC, or None if AI also can't parse it.
        """
        try:
            from agent.ai_client import AIClient

            # Get agent config
            agent_id = config.get('agent_id', 1)

            # Get AI model config from database
            from models import Agent
            from sqlalchemy.orm import sessionmaker
            from db import get_engine
            import os

            engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
            SessionLocal = sessionmaker(bind=engine)
            db = SessionLocal()

            try:
                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                if not agent:
                    return None

                provider = agent.model_provider
                model = agent.model_name
            finally:
                db.close()

            # Create AI client
            ai_client = AIClient(provider=provider, model_name=model, db=self._db_session)

            # Get current time in Brazil timezone for context
            now_brazil = datetime.now(BRAZIL_TZ)
            now_str = now_brazil.strftime('%Y-%m-%d %H:%M')

            # Prompt for AI date parsing
            prompt = f"""Parse the date and time from this text and convert it to a specific datetime.

Text: "{text}"

Current datetime (Brazil GMT-3): {now_str}
Current day: {now_brazil.strftime('%A')} ({now_brazil.strftime('%d/%m/%Y')})

Extract the date and time mentioned in the text. Consider:
- Portuguese date formats: "dia 17/12" means December 17th, "dia 17/12/2026" includes the year
- Time formats: "8am" = 08:00, "8pm" = 20:00, "14h" = 14:00
- Relative dates: "amanhã" = tomorrow, "segunda-feira" = next Monday
- If no year is specified and the date is in the past, use next year

Respond with ONLY a JSON object (no markdown, no explanation):
{{
  "year": {now_brazil.year},
  "month": {now_brazil.month},
  "day": {now_brazil.day},
  "hour": 8,
  "minute": 0
}}

If you cannot determine the date/time, respond with: {{"error": "cannot parse"}}"""

            result = await ai_client.generate(
                system_prompt="You are a date/time parser. Extract date and time from text and return as JSON.",
                user_message=prompt
            )

            # Parse JSON response
            response_text = result.get('answer', '{}')

            # Strip markdown code blocks if present
            if '```' in response_text:
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
                else:
                    response_text = response_text.replace('```json', '').replace('```', '').strip()

            parsed_data = json.loads(response_text)

            # Check for error
            if 'error' in parsed_data:
                logger.warning(f"AI could not parse datetime: {parsed_data['error']}")
                return None

            # Extract components
            year = int(parsed_data.get('year', now_brazil.year))
            month = int(parsed_data.get('month', 1))
            day = int(parsed_data.get('day', 1))
            hour = int(parsed_data.get('hour', 0))
            minute = int(parsed_data.get('minute', 0))

            # Create datetime in Brazil timezone
            target_time = now_brazil.replace(year=year, month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)

            # Convert to UTC
            utc_time = target_time.astimezone(pytz.UTC).replace(tzinfo=None)
            logger.info(f"AI parsed '{text}' → Brazil: {target_time.strftime('%Y-%m-%d %H:%M %Z')} → UTC: {utc_time}")
            return utc_time

        except Exception as e:
            logger.error(f"Error in AI date parsing: {e}", exc_info=True)
            return None

    async def _parse_scheduling_request(self, text: str, config: Dict[str, Any], sender: str) -> Dict[str, Any]:
        """
        Parse natural language scheduling request using AI + dateparser.

        Args:
            text: The scheduling request text
            config: Skill configuration
            sender: Phone number of the requester (for fallback recipient)

        Returns dict with:
        - success: bool
        - event_type: str (CONVERSATION or NOTIFICATION)
        - scheduled_at: datetime (UTC)
        - payload: dict
        - recurrence_rule: dict or None
        - agent_id: int
        - error: str (if success=False)

        Note: MESSAGE and TASK types are not supported. Use Flows instead.
        """
        try:
            # Use AI to parse the request
            from agent.ai_client import AIClient

            # Get agent config (default to agent 1 for now)
            agent_id = config.get('agent_id', 1)

            # Get AI model config from database
            from models import Agent
            from sqlalchemy.orm import sessionmaker
            from db import get_engine
            import os

            engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
            SessionLocal = sessionmaker(bind=engine)
            db = SessionLocal()

            try:
                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                if not agent:
                    return {'success': False, 'error': 'Agent not found'}

                provider = agent.model_provider
                model = agent.model_name

            finally:
                db.close()

            # Create AI client (Phase 7.4: Pass db for API key loading)
            ai_client = AIClient(provider=provider, model_name=model, db=self._db_session)

            # Get current time in Brazil timezone for context
            now_brazil = datetime.now(BRAZIL_TZ)
            now_str = now_brazil.strftime('%Y-%m-%d %H:%M')

            # Prompt for parsing
            prompt = f"""Parse this Portuguese/English scheduling request and extract structured data.

Request: "{text}"

Current time (Brazil GMT-3): {now_str}
Current day: {now_brazil.strftime('%A')} ({now_brazil.strftime('%d/%m/%Y')})

Extract these fields:

1. **event_type**:
   - NOTIFICATION: For single-turn actions (send and complete):
     * Reminders: "Me lembre...", "Notifique..."
     * Simple messages: "Envie uma mensagem para...", "Mande um beijo para...", "Send a message to..."
     * Any request that doesn't require a response or back-and-forth
   - CONVERSATION: ONLY for multi-turn back-and-forth interactions:
     * "Agende uma conversa com...", "Fale com X para confirmar..."
     * "Pergunte para X se...", "Ask X if..."
     * Requires responses and continuing dialogue until objective achieved
   - NOTE: Scheduled messages and tool executions should use the Flows feature, not scheduler

2. **recipient**: WHO should receive the notification/conversation
   - For NOTIFICATION (reminders to self): null
     * "Me lembre de comprar pão" → recipient: null (reminder goes to requester)
     * "Me lembre de mandar beijo pra @Alice" → recipient: null (reminder goes to requester, @Alice is in content)
   - For NOTIFICATION (direct messages to others): extract recipient
     * "Envie uma mensagem para @Bob" → recipient: "@Bob"
     * "Notifique @Alice sobre a reunião" → recipient: "@Alice"
     * "Send a message to @John" → recipient: "@John"
   - For CONVERSATION: Always extract the recipient
     * "Fale com @Bob para confirmar" → recipient: "@Bob"
   - IMPORTANT: If the request says "me lembre" (remind ME), recipient is ALWAYS null

3. **time_expression**: Extract the EXACT time phrase from the original request
   - Portuguese relative: "em 1 minuto", "em 3 minutos", "daqui a 2 horas", "em 5 segundos"
   - Portuguese absolute: "amanhã às 14h", "segunda-feira às 9h", "15/10 às 9h30"
   - English: "in 1 minute", "tomorrow at 2pm", "next Monday"
   - IMPORTANT: Copy the time phrase EXACTLY as written, do not translate or modify
   - If no time specified: null

4. **objective_or_content**: What the reminder is about or the conversation objective
   - For NOTIFICATION: What to be reminded about
     - "Me lembre de mandar uma mensagem para minha mãe" → "mandar uma mensagem para minha mãe"
     - "Me lembre de tomar remédio" → "tomar remédio"
   - For CONVERSATION: The objective of the conversation
     - "Fale com @Bob para confirmar presença" → "confirmar presença na reunião"
   - Be specific and clear, include ALL details

5. **recurrence**: null unless explicitly mentions "todo dia", "toda semana", "daily", "weekly"

6. **duration_minutes**: Event duration in minutes (optional)
   - Extract if mentions: "30 min", "30 minutos", "meia hora" → 30
   - Extract if mentions: "1 hora", "1 hour", "1h" → 60
   - Extract if mentions: "2 horas", "2 hours", "2h" → 120
   - If not specified: null (will use default 60 minutes)

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "event_type": "NOTIFICATION or CONVERSATION",
  "recipient": "name/@mention/phone or null",
  "time_expression": "exact phrase or null",
  "objective_or_content": "clear description",
  "recurrence": null,
  "duration_minutes": null,
  "notes": ""
}}"""

            result = await ai_client.generate(
                system_prompt="You are a scheduling assistant. Parse natural language into structured JSON.",
                user_message=prompt
            )

            # Parse JSON response (AIClient returns 'answer' key, not 'response')
            response_text = result.get('answer', '{}')
            logger.info(f"SchedulerSkill AI response: {response_text[:200]}...")  # Log first 200 chars

            # Strip markdown code blocks if present
            if '```' in response_text:
                # Extract JSON from markdown code block
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
                if json_match:
                    response_text = json_match.group(1)
                else:
                    # Try without code blocks
                    response_text = response_text.replace('```json', '').replace('```', '').strip()

            parsed_data = json.loads(response_text)
            logger.info(f"Parsed data: time_expression='{parsed_data.get('time_expression')}', content='{parsed_data.get('objective_or_content')}'")

            # Build payload based on event type
            event_type = parsed_data.get('event_type', 'NOTIFICATION').upper()
            recipient = parsed_data.get('recipient', '')
            time_expression = parsed_data.get('time_expression', '')
            content = parsed_data.get('objective_or_content', '')
            recurrence_data = parsed_data.get('recurrence')

            # Parse time expression using dateparser
            scheduled_at = None
            if time_expression:
                scheduled_at = self._parse_natural_language_datetime(time_expression)

            # Fallback if parsing failed
            if not scheduled_at:
                # Try parsing the entire text
                scheduled_at = self._parse_natural_language_datetime(text)

            # AI Fallback: Use AI to parse the date if traditional parsing failed
            if not scheduled_at:
                logger.warning(f"Traditional parsing failed for '{time_expression}' or '{text}', trying AI fallback...")
                scheduled_at = await self._ai_parse_datetime(text, config)

            # Final fallback: 1 hour from now (in Brazil timezone, then convert to UTC)
            if not scheduled_at:
                now_brazil = datetime.now(BRAZIL_TZ)
                fallback_brazil = now_brazil + timedelta(hours=1)
                scheduled_at = fallback_brazil.astimezone(pytz.UTC).replace(tzinfo=None)
                logger.warning(f"Could not parse time from '{time_expression}' or '{text}', using 1 hour from now (Brazil time)")

            # Extract duration
            duration_minutes = parsed_data.get('duration_minutes')
            if duration_minutes:
                try:
                    duration_minutes = int(duration_minutes)
                    logger.info(f"SchedulerSkill: Extracted duration from AI: {duration_minutes} minutes")
                except (ValueError, TypeError):
                    duration_minutes = None

            # Build payload
            payload = {}

            if event_type == 'CONVERSATION':
                payload = {
                    'agent_id': agent_id,
                    'recipient': recipient,
                    'objective': content,
                    'context': {'created_by': 'scheduler_skill'},
                    'max_turns': config.get('default_max_turns', 20),
                    'timeout_hours': config.get('default_timeout_hours', 24)
                }

            elif event_type == 'NOTIFICATION':
                payload = {
                    'agent_id': agent_id,
                    'recipient_raw': recipient,
                    'reminder_text': content,
                    'message_template': config.get('notification_template', 'Hi {name}! Reminder: {reminder_text}'),
                    'sender_key': sender  # Requester's phone number for fallback recipient
                }
            else:
                return {
                    'success': False,
                    'error': f"Unsupported event type: {event_type}. Use NOTIFICATION for reminders or CONVERSATION for AI-driven conversations. For scheduled messages or tool execution, please use the Flows feature."
                }

            # Build recurrence rule if specified
            recurrence_rule = None
            if recurrence_data and isinstance(recurrence_data, dict):
                recurrence_rule = {
                    'frequency': recurrence_data.get('frequency', 'daily'),
                    'interval': recurrence_data.get('interval', 1)
                }

            return {
                'success': True,
                'event_type': event_type,
                'scheduled_at': scheduled_at,
                'payload': payload,
                'recurrence_rule': recurrence_rule,
                'duration_minutes': duration_minutes,
                'agent_id': agent_id,
                'parsed_data': parsed_data
            }

        except Exception as e:
            logger.error(f"Error parsing scheduling request: {e}", exc_info=True)
            return {
                'success': False,
                'error': f"I couldn't understand the scheduling request. Please be more specific about what, when, and who."
            }

    def _format_confirmation(self, event, parsed: Dict[str, Any]) -> str:
        """Format confirmation message with Brazil timezone display"""
        event_type_name = event.event_type.lower()

        # Convert UTC scheduled_at to Brazil timezone for display
        utc_time = event.scheduled_at.replace(tzinfo=pytz.UTC)
        brazil_time = utc_time.astimezone(BRAZIL_TZ)
        scheduled_time = brazil_time.strftime('%d/%m/%Y às %H:%M GMT-3')

        payload = parsed['payload']

        if event.event_type == 'CONVERSATION':
            recipient = payload.get('recipient', 'recipient')
            objective = payload.get('objective', 'objective')
            msg = f"✅ Conversa agendada com {recipient}\n"
            msg += f"   Objetivo: {objective}\n"
            msg += f"   Data/Hora: {scheduled_time}\n"
            msg += f"   ID do evento: {event.id}"

        elif event.event_type == 'NOTIFICATION':
            recipient = payload.get('recipient_raw', 'você')
            reminder = payload.get('reminder_text', 'lembrete')
            msg = f"✅ Lembrete agendado\n"
            if recipient and recipient != 'você':
                msg += f"   Para: {recipient}\n"
            msg += f"   Mensagem: {reminder}\n"
            msg += f"   Data/Hora: {scheduled_time}\n"
            msg += f"   ID do evento: {event.id}"

            if event.recurrence_rule:
                freq = json.loads(event.recurrence_rule).get('frequency', 'daily')
                freq_pt = {'daily': 'diariamente', 'weekly': 'semanalmente', 'monthly': 'mensalmente'}.get(freq, freq)
                msg += f"\n   Recorrência: {freq_pt}"

        else:
            # Generic confirmation for unsupported types (shouldn't reach here)
            msg = f"✅ Evento agendado: {event_type_name}\n"
            msg += f"   Data/Hora: {scheduled_time}\n"
            msg += f"   ID do evento: {event.id}"

        return msg

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """Default configuration"""
        return {
            'agent_id': 1,
            'default_max_turns': 20,
            'default_timeout_hours': 24,
            'notification_template': 'Hi {name}! Reminder: {reminder_text}'
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Configuration schema"""
        return {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "integer",
                    "description": "Default agent ID for scheduled events",
                    "default": 1
                },
                "default_max_turns": {
                    "type": "integer",
                    "description": "Default max turns for conversations",
                    "default": 20
                },
                "default_timeout_hours": {
                    "type": "integer",
                    "description": "Default timeout for conversations in hours",
                    "default": 24
                },
                "notification_template": {
                    "type": "string",
                    "description": "Default notification message template",
                    "default": "Hi {name}! Reminder: {reminder_text}"
                }
            },
            "required": []
        }

    # =========================================================================
    # SKILLS-AS-TOOLS: EXECUTE_TOOL METHODS
    # =========================================================================

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute scheduler as a tool call.

        Routes to create or list based on action argument.
        Uses SchedulerProviderFactory for provider-agnostic execution.
        """
        action = arguments.get("action", "create")

        try:
            if action == "list":
                return await self._execute_list_action(arguments, message, config)
            elif action == "create":
                return await self._execute_create_action(arguments, message, config)
            else:
                return SkillResult(
                    success=False,
                    response=f"Unknown action: {action}. Use 'create' or 'list'.",
                    data={"error": "unknown_action"}
                )
        except Exception as e:
            logger.error(f"SchedulerSkill execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                response=f"Error executing scheduler: {str(e)}",
                data={"error": str(e)}
            )

    async def _execute_list_action(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """Handle list action - retrieve scheduled events via provider."""
        from agent.skills.scheduler.factory import SchedulerProviderFactory

        days_ahead = arguments.get("days_ahead", 7)
        agent_id = config.get('agent_id')

        try:
            # Get provider for this agent
            provider = SchedulerProviderFactory.get_provider_for_agent(
                agent_id=agent_id,
                db=self._db_session,
                skill_type="scheduler"
            )

            # Query events
            now = datetime.now(BRAZIL_TZ)
            end_date = now + timedelta(days=days_ahead)

            events = await provider.list_events(
                start=now,
                end=end_date,
                max_results=50
            )

            if not events:
                return SkillResult(
                    success=True,
                    response=f"📅 No scheduled events found in the next {days_ahead} days.",
                    data={"events": [], "count": 0}
                )

            # Format events for display
            lines = [f"📅 **Scheduled Events** (next {days_ahead} days):\n"]
            for event in events:
                time_str = event.start.strftime("%Y-%m-%d %H:%M")
                status = event.status.value if hasattr(event.status, 'value') else event.status
                provider_tag = f"[{event.provider}]" if event.provider != "flows" else ""
                lines.append(f"• **{event.title}** - {time_str} ({status}) {provider_tag}")

            return SkillResult(
                success=True,
                response="\n".join(lines),
                data={
                    "events": [e.to_dict() for e in events],
                    "count": len(events)
                }
            )

        except Exception as e:
            logger.error(f"Failed to list events: {e}", exc_info=True)
            return SkillResult(
                success=False,
                response=f"Failed to list events: {str(e)}",
                data={"error": str(e)}
            )

    async def _execute_create_action(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """Handle create action - schedule new event via provider."""
        from agent.skills.scheduler.factory import SchedulerProviderFactory

        # Extract arguments
        event_type = arguments.get("event_type", "NOTIFICATION")
        title = arguments.get("title", "")
        time_expr = arguments.get("time_expression", "")
        recipient = arguments.get("recipient", "")
        recurrence = arguments.get("recurrence", "none")
        agent_id = config.get('agent_id')

        # Validate required fields
        if not title:
            return SkillResult(
                success=False,
                response="Missing required field: 'title' is required to create an event.",
                data={"error": "missing_title"}
            )

        if not time_expr:
            return SkillResult(
                success=False,
                response="Missing required field: 'time_expression' is required (e.g., 'tomorrow at 3pm').",
                data={"error": "missing_time"}
            )

        # Parse time expression using existing logic
        scheduled_at = self._parse_natural_language_datetime(time_expr)

        if not scheduled_at:
            # Try AI parsing as fallback
            scheduled_at = await self._ai_parse_datetime(time_expr, config)

        if not scheduled_at:
            return SkillResult(
                success=False,
                response=f"Could not understand the time '{time_expr}'. Try formats like 'tomorrow at 3pm' or '2024-03-15 14:00'.",
                data={"error": "invalid_time"}
            )

        # Determine recipient
        if not recipient or recipient.lower() in ('me', 'myself', 'self'):
            recipient = message.sender

        # Convert recurrence to RRULE format
        recurrence_rule = None
        if recurrence and recurrence != "none":
            recurrence_map = {
                "daily": "RRULE:FREQ=DAILY;INTERVAL=1",
                "weekly": "RRULE:FREQ=WEEKLY;INTERVAL=1",
                "monthly": "RRULE:FREQ=MONTHLY;INTERVAL=1"
            }
            recurrence_rule = recurrence_map.get(recurrence)

        try:
            # Get provider for this agent (Flows, Google Calendar, or Asana)
            provider = SchedulerProviderFactory.get_provider_for_agent(
                agent_id=agent_id,
                db=self._db_session,
                skill_type="scheduler"
            )

            # Create event via provider's unified interface
            # Note: event_type and recipient are Flows-specific kwargs
            event = await provider.create_event(
                title=title,
                start=scheduled_at,
                recurrence=recurrence_rule,
                event_type=event_type,  # Flows-specific: NOTIFICATION or CONVERSATION
                recipient=recipient,    # Flows-specific: who receives the reminder
                agent_id=agent_id       # Flows-specific: agent context
            )

            # Format response
            time_str = scheduled_at.strftime("%Y-%m-%d %H:%M")
            recurrence_str = f" (repeating {recurrence})" if recurrence != "none" else ""
            provider_name = provider.provider_name

            return SkillResult(
                success=True,
                response=f"✅ Scheduled via {provider_name}: '{title}' for {time_str}{recurrence_str}",
                data={
                    "event_id": event.id,
                    "provider": event.provider,
                    "event_type": event_type,
                    "scheduled_at": time_str,
                    "title": title,
                    "recipient": recipient,
                    "recurrence": recurrence
                }
            )

        except Exception as e:
            logger.error(f"Failed to create event: {e}", exc_info=True)
            return SkillResult(
                success=False,
                response=f"Failed to schedule event: {str(e)}",
                data={"error": str(e)}
            )
