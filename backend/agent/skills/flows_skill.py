"""
Flows Skill - Unified scheduling and event management

Consolidates SchedulerSkill and SchedulerQuerySkill into a single skill
with granular sub-capabilities for better control and consistency.

Phase 9: Multi-Provider Support
- Built-in Flows (default)
- Google Calendar
- Asana Tasks

Each agent can select which provider to use for scheduling operations.

Sub-capabilities:
- create_notification: Schedule single-message reminders
- create_conversation: Schedule multi-turn AI conversations
- query_events: List and search scheduled events
- update_events: Modify existing events (Phase 2)
- delete_events: Cancel events (Phase 2)
"""

from .base import BaseSkill, InboundMessage, SkillResult
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta

# Import existing skill implementations to reuse logic
from .scheduler_skill import SchedulerSkill
from .scheduler_query_skill import SchedulerQuerySkill

# Import provider system
from .scheduler import (
    SchedulerProviderFactory,
    SchedulerProviderBase,
    SchedulerEvent,
    SchedulerProviderType,
    ProviderNotConfiguredError,
)

logger = logging.getLogger(__name__)


class FlowsSkill(BaseSkill):
    """
    Unified skill for Flow management (scheduling and queries).

    Phase 9: Multi-Provider Support
    Supports multiple scheduling providers:
    - Built-in Flows (default): Internal reminders and conversations
    - Google Calendar: Calendar events and meetings
    - Asana: Tasks with due dates

    Combines scheduling and querying capabilities with granular controls.
    Provider selection is configured per-agent via AgentSkillIntegration.

    Skills-as-Tools (Phase 4):
    - Tool name: manage_reminders (single tool with action parameter)
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    - Actions: create, list, update, delete
    """

    skill_type = "flows"
    skill_name = "Flows"
    skill_description = "Schedule reminders, AI-driven conversations, and manage scheduled events"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    def __init__(self):
        """Initialize with wrapped skills and provider support"""
        super().__init__()
        self._scheduler = SchedulerSkill()
        self._query = SchedulerQuerySkill()
        self._provider: Optional[SchedulerProviderBase] = None

    def set_db_session(self, db):
        """
        Override to also set database session for wrapped skills.

        Phase 7.4: Ensure wrapped scheduler and query skills have database access.
        Phase 9: Also initializes the scheduler provider.
        """
        super().set_db_session(db)
        # Pass database session to wrapped skills
        if hasattr(self._scheduler, 'set_db_session'):
            self._scheduler.set_db_session(db)
        if hasattr(self._query, 'set_db_session'):
            self._query.set_db_session(db)

        # Provider will be initialized lazily when needed
        self._provider = None

    def _get_provider(self, config: Dict[str, Any] = None) -> SchedulerProviderBase:
        """
        Get the scheduler provider for this agent.

        Phase 9: Provider selection based on agent configuration.

        Priority:
        1. Config-specified provider (scheduler_provider + integration_id)
        2. AgentSkillIntegration database configuration
        3. Default FlowsProvider

        Returns:
            Configured SchedulerProviderBase instance
        """
        config = config or getattr(self, '_config', {}) or {}
        agent_id = getattr(self, '_agent_id', None)

        # Check if provider is specified in config
        provider_type = config.get('scheduler_provider', SchedulerProviderType.FLOWS.value)
        integration_id = config.get('integration_id')

        # Get tenant_id from agent
        tenant_id = None
        if agent_id and self._db_session:
            try:
                from models import Agent
                agent = self._db_session.query(Agent).filter(Agent.id == agent_id).first()
                if agent:
                    tenant_id = agent.tenant_id
            except Exception as e:
                logger.warning(f"FlowsSkill: Error getting tenant_id: {e}")

        try:
            # If agent_id is provided and no explicit provider, try to load from DB
            if agent_id and not config.get('scheduler_provider'):
                return SchedulerProviderFactory.get_provider_for_agent(
                    agent_id=agent_id,
                    db=self._db_session
                )

            # Use explicitly configured provider
            return SchedulerProviderFactory.get_provider(
                provider_type=provider_type,
                db=self._db_session,
                tenant_id=tenant_id,
                integration_id=integration_id,
                agent_id=agent_id
            )
        except ProviderNotConfiguredError as e:
            logger.warning(f"FlowsSkill: {e}, falling back to Flows provider")
            from .scheduler import FlowsProvider
            return FlowsProvider(db=self._db_session, tenant_id=tenant_id, agent_id=agent_id)

    def get_provider_info(self, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Get information about the current provider configuration.

        Useful for displaying in UI or debugging.

        Returns:
            Dict with provider info:
            {
                "provider_type": "flows" | "google_calendar" | "asana",
                "provider_name": "Built-in Flows",
                "integration_id": None | int,
                "integration_name": None | str,
                "capabilities": {...}
            }
        """
        provider = self._get_provider(config)

        return {
            "provider_type": provider.provider_type.value,
            "provider_name": provider.provider_name,
            "capabilities": provider.get_capabilities(),
        }

    def _resolve_intent_detection_model(self, config: Dict[str, Any]) -> str:
        """
        Resolve the intent detection model from config.

        Supports:
        - "inherit": Use agent's primary model
        - Specific model name: Use as-is
        - Not set/empty: Use default "gemini-2.5-flash"

        Phase 7.5: Configurable intent detection model.
        Backward compatible with legacy 'ai_model' field.

        Args:
            config: Skill configuration

        Returns:
            Resolved model name (e.g., "gemini-2.5-flash", "gemma2:4b")
        """
        # Phase 7.5: Check new field first, fall back to legacy field, then agent's model
        intent_model = config.get('intent_detection_model') or config.get('ai_model')

        # If no specific intent model configured, use agent's main model
        if not intent_model:
            intent_model = config.get('model_name', 'gemini-2.5-flash')

        # Special case: "inherit" means use agent's model
        if intent_model == "inherit":
            agent_id = getattr(self, '_agent_id', None)
            if agent_id and self._db_session:
                try:
                    from models import Agent
                    agent = self._db_session.query(Agent).filter(Agent.id == agent_id).first()
                    if agent:
                        # Resolve agent's model
                        # For non-Ollama providers, use just model_name
                        if agent.model_provider == "ollama":
                            resolved = agent.model_name  # e.g., "gemma2:4b"
                        else:
                            resolved = agent.model_name  # e.g., "gemini-2.5-flash", "gpt-4"

                        logger.info(f"FlowsSkill: Resolved 'inherit' → agent model: {resolved} (provider: {agent.model_provider})")
                        return resolved
                    else:
                        logger.warning(f"FlowsSkill: Agent {agent_id} not found, using agent config model")
                except Exception as e:
                    logger.error(f"FlowsSkill: Error resolving agent model: {e}", exc_info=True)

            # Fallback to agent's configured model if we can't resolve from database
            logger.warning(f"FlowsSkill: Cannot resolve 'inherit' from database, using agent config model")
            return config.get('model_name', 'gemini-2.5-flash')

        # Return resolved intent model
        return intent_model

    async def _detect_flow_intent(self, text: str, ai_model: str = None) -> str:
        """
        Detect flow operation intent using AI (NO hardcoded keywords).

        Phase 7.1: Uses AI to determine operation type from natural language.
        Phase 7.5: Enhanced provider detection for Ollama models.

        Returns: 'query', 'create', 'update', 'delete', or 'unknown'
        """
        try:
            from agent.ai_client import AIClient

            # Use fallback if no model specified
            if not ai_model:
                ai_model = "gemini-2.5-flash"  # Safe fallback

            # Phase 7.5: Parse model and determine provider
            if ai_model.startswith("gemini"):
                provider = "gemini"
            elif ai_model.startswith("gpt"):
                provider = "openai"
            elif ai_model.startswith("claude"):
                provider = "anthropic"
            elif ":" in ai_model or ai_model.lower() in ["llama", "gemma", "mistral", "deepseek"]:
                # Ollama models typically have format "model:tag" (e.g., "gemma2:4b")
                # Or are common Ollama model names
                provider = "ollama"
            else:
                # Default to gemini for backward compatibility
                provider = "gemini"

            logger.info(f"FlowsSkill: Using provider={provider}, model={ai_model} for intent detection")
            ai_client = AIClient(provider=provider, model_name=ai_model, db=self._db_session)  # Phase 7.4: Pass db for API key loading

            system_prompt = """You are an operation classifier for Flows/Scheduler system.

Determine what operation the user wants to perform.

Operations:
- query: List/show/check scheduled reminders/events/flows
- create: Create/schedule new reminder/event/conversation
- update: Modify/change/edit an existing event (reschedule, change details)
- delete: Delete/remove/cancel an existing event
- unknown: Not requesting any specific operation

Answer with ONLY the operation name (query/create/update/delete/unknown)."""

            user_prompt = f"""Message: "{text}"

What operation is requested?

Answer:"""

            response_dict = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=user_prompt
            )

            intent = response_dict.get("answer", "unknown").strip().lower()

            # Validate response
            valid_intents = ['query', 'create', 'update', 'delete', 'unknown']
            if intent not in valid_intents:
                logger.warning(f"AI returned invalid flow intent: '{intent}', defaulting to 'unknown'")
                return 'unknown'

            logger.info(f"FlowsSkill: AI detected operation intent: {intent}")
            return intent

        except Exception as e:
            logger.error(f"Error detecting flow intent with AI: {e}", exc_info=True)
            return 'unknown'

    async def _process_query_with_provider(
        self,
        provider: SchedulerProviderBase,
        message: InboundMessage
    ) -> SkillResult:
        """
        Process a query request using an external provider.

        Phase 9: External provider support for listing events.

        Args:
            provider: The scheduler provider to use
            message: The inbound message

        Returns:
            SkillResult with formatted event list
        """
        try:
            from datetime import timedelta
            import re

            # Parse user query to determine time range
            message_lower = message.body.lower()
            now = datetime.now()

            # Determine date range based on user query
            if any(kw in message_lower for kw in ['essa semana', 'this week', 'esta semana', 'da semana']):
                # This week: Monday to Sunday
                days_since_monday = now.weekday()  # 0=Monday, 6=Sunday
                start = now - timedelta(days=days_since_monday)
                start = start.replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=7)
            else:
                # Default: next 7 days
                start = now
                end = now + timedelta(days=7)

            events = await provider.list_events(start=start, end=end, max_results=20)

            if not events:
                return SkillResult(
                    success=True,
                    output=f"📅 No events scheduled via {provider.provider_name}.",
                    metadata={'skip_ai': True, 'event_count': 0}
                )

            # Format events for display
            lines = [f"📅 Your events via {provider.provider_name} ({len(events)} found):\n"]
            for event in events:
                # Format event time
                event_time = event.start.strftime('%m/%d/%Y at %H:%M') if event.start else 'No date'
                status_emoji = '✅' if event.status.value == 'completed' else '📌'

                # Extract short ID (last 8 chars after gcal_)
                short_id = event.id.split('_')[-1][:8] if '_' in event.id else event.id[:8]

                lines.append(f"  {status_emoji} **{event.title}**")
                lines.append(f"      📅 {event_time}")

                if event.description:
                    # Strip HTML tags and truncate
                    clean_desc = re.sub(r'<[^>]+>', '', event.description)
                    clean_desc = clean_desc.replace('&nbsp;', ' ').strip()
                    if clean_desc and len(clean_desc) > 3:
                        lines.append(f"      📝 {clean_desc[:80]}{'...' if len(clean_desc) > 80 else ''}")

                lines.append(f"      🔖 ID: {short_id}\n")

            return SkillResult(
                success=True,
                output="\n".join(lines),
                metadata={
                    'skip_ai': True,
                    'event_count': len(events),
                    'provider_type': provider.provider_type.value
                }
            )

        except Exception as e:
            logger.error(f"FlowsSkill: Error querying with provider: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error querying events: {str(e)}",
                metadata={'error': str(e), 'skip_ai': True}
            )

    async def _process_create_with_provider(
        self,
        provider: SchedulerProviderBase,
        message: InboundMessage,
        ai_model: str
    ) -> SkillResult:
        """
        Process a create request using an external provider.

        Phase 9: External provider support for creating events.
        Uses AI to parse natural language into structured event data.

        Args:
            provider: The scheduler provider to use
            message: The inbound message
            ai_model: AI model to use for parsing

        Returns:
            SkillResult with created event confirmation
        """
        try:
            # #region agent log
            import time
            import json as json_lib
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'flows_skill.py:391',
                        'message': '_process_create_with_provider ENTRY',
                        'data': {
                            'message_body': message.body[:200],
                            'provider_type': provider.provider_type.value,
                            'provider_name': provider.provider_name
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H3'
                    }) + '\n')
            except:
                pass
            # #endregion

            # Parse the message to extract event details using AI
            parsed = await self._parse_event_from_message(message.body, ai_model)

            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'flows_skill.py:411',
                        'message': 'Parsed event details',
                        'data': {
                            'parsed_keys': list(parsed.keys()) if parsed else None,
                            'title': parsed.get('title') if parsed else None,
                            'start': parsed.get('start').isoformat() if parsed and parsed.get('start') else None
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H4'
                    }) + '\n')
            except:
                pass
            # #endregion

            if not parsed or not parsed.get('title'):
                return SkillResult(
                    success=False,
                    output="❌ Could not understand the event details. Please specify:\n• What you want to schedule\n• When (date and time)",
                    metadata={'error': 'parse_failed', 'skip_ai': True}
                )

            # Convert recurrence pattern to RRULE format if present
            recurrence_rrule = None
            if parsed.get('recurrence'):
                rec_pattern = parsed['recurrence'].lower()
                if 'daily' in rec_pattern or 'diariamente' in rec_pattern:
                    recurrence_rrule = 'RRULE:FREQ=DAILY;INTERVAL=1'
                elif 'weekly' in rec_pattern or 'semanalmente' in rec_pattern:
                    recurrence_rrule = 'RRULE:FREQ=WEEKLY;INTERVAL=1'
                elif 'monthly' in rec_pattern or 'mensalmente' in rec_pattern:
                    recurrence_rrule = 'RRULE:FREQ=MONTHLY;INTERVAL=1'

            # Create the event via the provider
            event = await provider.create_event(
                title=parsed['title'],
                start=parsed['start'],
                end=parsed.get('end'),
                description=parsed.get('description'),
                location=parsed.get('location'),
                recurrence=recurrence_rrule,
                reminder_minutes=parsed.get('reminder_minutes', 30)
            )

            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'flows_skill.py:463',
                        'message': 'Event created from provider',
                        'data': {
                            'event_id': event.id,
                            'event_title': event.title
                        },
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H5'
                    }) + '\n')
            except:
                pass
            # #endregion

            # Format confirmation message
            event_time = event.start.strftime('%m/%d/%Y at %H:%M') if event.start else 'Not specified'

            confirmation = f"✅ Event created via {provider.provider_name}!\n\n"
            confirmation += f"📌 **{event.title}**\n"
            confirmation += f"📅 {event_time}\n"

            # Show duration if available
            if parsed.get('duration_minutes'):
                duration_minutes = parsed['duration_minutes']
                if duration_minutes == 30:
                    duration_str = "30 minutes"
                elif duration_minutes == 60:
                    duration_str = "1 hour"
                elif duration_minutes < 60:
                    duration_str = f"{duration_minutes} minutes"
                else:
                    hours = duration_minutes // 60
                    mins = duration_minutes % 60
                    if mins == 0:
                        duration_str = f"{hours} hour{'s' if hours > 1 else ''}"
                    else:
                        duration_str = f"{hours}h {mins}min"

                confirmation += f"⏱️ Duration: {duration_str}"
                if event.end:
                    end_time_str = event.end.strftime('%H:%M')
                    confirmation += f" (ends at {end_time_str})"
                confirmation += "\n"

            # Show recurrence if available
            if recurrence_rrule:
                if 'DAILY' in recurrence_rrule:
                    confirmation += f"🔁 Repeats: Daily\n"
                elif 'WEEKLY' in recurrence_rrule:
                    confirmation += f"🔁 Repeats: Weekly\n"
                elif 'MONTHLY' in recurrence_rrule:
                    confirmation += f"🔁 Repeats: Monthly\n"

            if event.description:
                confirmation += f"📝 {event.description}\n"
            if event.location:
                confirmation += f"📍 {event.location}\n"
            confirmation += f"\n🔖 ID: {event.id}"

            return SkillResult(
                success=True,
                output=confirmation,
                metadata={
                    'skip_ai': True,
                    'event_id': event.id,
                    'provider_type': provider.provider_type.value
                }
            )

        except Exception as e:
            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'flows_skill.py:540',
                        'message': 'Exception in _process_create_with_provider',
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
            logger.error(f"FlowsSkill: Error creating with provider: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error creating event: {str(e)}",
                metadata={'error': str(e), 'skip_ai': True}
            )

    async def _process_delete_with_provider(
        self,
        provider: SchedulerProviderBase,
        message: InboundMessage,
        ai_model: str
    ) -> SkillResult:
        """
        Process a delete request using an external provider.

        Uses AI to identify which event to delete from the message.

        Args:
            provider: The scheduler provider to use
            message: The inbound message
            ai_model: AI model to use for parsing

        Returns:
            SkillResult with deletion confirmation
        """
        try:
            # First, try to parse an event ID from the message
            event_id = await self._parse_event_id_from_message(message.body, ai_model, provider)

            if not event_id:
                return SkillResult(
                    success=False,
                    output="❌ Could not identify which event to delete. Try:\n• Mention the event name\n• Use the event ID (e.g., 'delete event gcal_abc123')\n• First list your events with 'what are my events?'",
                    metadata={'error': 'event_not_identified', 'skip_ai': True}
                )

            # Get event details before deleting (for confirmation message)
            event = await provider.get_event(event_id)
            event_title = event.title if event else event_id

            # Delete the event
            success = await provider.delete_event(event_id)

            if success:
                return SkillResult(
                    success=True,
                    output=f"✅ Event deleted via {provider.provider_name}!\n\n📌 **{event_title}** has been removed.",
                    metadata={
                        'skip_ai': True,
                        'event_id': event_id,
                        'provider_type': provider.provider_type.value
                    }
                )
            else:
                return SkillResult(
                    success=False,
                    output=f"❌ Could not delete the event. Please verify the ID is correct: {event_id}",
                    metadata={'error': 'delete_failed', 'skip_ai': True}
                )

        except Exception as e:
            logger.error(f"FlowsSkill: Error deleting with provider: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error deleting event: {str(e)}",
                metadata={'error': str(e), 'skip_ai': True}
            )

    async def _process_update_with_provider(
        self,
        provider: SchedulerProviderBase,
        message: InboundMessage,
        ai_model: str
    ) -> SkillResult:
        """
        Process an update request using an external provider.

        Uses AI to identify which event to update and what changes to make.

        Args:
            provider: The scheduler provider to use
            message: The inbound message
            ai_model: AI model to use for parsing

        Returns:
            SkillResult with update confirmation
        """
        try:
            # Parse event ID and update details from message
            update_info = await self._parse_event_update_from_message(message.body, ai_model, provider)

            if not update_info or not update_info.get('event_id'):
                return SkillResult(
                    success=False,
                    output="❌ Could not identify which event to update. Try:\n• Mention the event name and what you want to change\n• Use the event ID (e.g., 'update event gcal_abc123')\n• First list your events with 'what are my events?'",
                    metadata={'error': 'event_not_identified', 'skip_ai': True}
                )

            event_id = update_info['event_id']

            # Update the event
            event = await provider.update_event(
                event_id=event_id,
                title=update_info.get('title'),
                start=update_info.get('start'),
                end=update_info.get('end'),
                description=update_info.get('description'),
                location=update_info.get('location')
            )

            # Format confirmation message
            event_time = event.start.strftime('%m/%d/%Y at %H:%M') if event.start else 'Not specified'

            confirmation = f"✅ Event updated via {provider.provider_name}!\n\n"
            confirmation += f"📌 **{event.title}**\n"
            confirmation += f"📅 {event_time}\n"
            if event.description:
                confirmation += f"📝 {event.description}\n"
            if event.location:
                confirmation += f"📍 {event.location}\n"

            return SkillResult(
                success=True,
                output=confirmation,
                metadata={
                    'skip_ai': True,
                    'event_id': event.id,
                    'provider_type': provider.provider_type.value
                }
            )

        except Exception as e:
            logger.error(f"FlowsSkill: Error updating with provider: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error updating event: {str(e)}",
                metadata={'error': str(e), 'skip_ai': True}
            )

    async def _parse_event_id_from_message(
        self,
        text: str,
        ai_model: str,
        provider: SchedulerProviderBase
    ) -> Optional[str]:
        """
        Parse event ID from natural language message.

        Tries to identify which event the user wants to delete by:
        1. Looking for explicit event ID in message
        2. Using AI to match event title/description with recent events

        Args:
            text: Natural language message
            ai_model: AI model to use for parsing
            provider: Provider to query events from

        Returns:
            Event ID if found, None otherwise
        """
        try:
            import re
            from agent.ai_client import AIClient
            import json

            # Try to find explicit event ID in message (gcal_xxx, asana_xxx, flows_xxx)
            id_pattern = r'(gcal_[a-zA-Z0-9]+|asana_[a-zA-Z0-9]+|flows_\d+)'
            match = re.search(id_pattern, text)
            if match:
                return match.group(1)

            # Get recent events to help AI identify the target
            now = datetime.now()
            from datetime import timedelta
            events = await provider.list_events(
                start=now - timedelta(days=7),
                end=now + timedelta(days=30),
                max_results=20
            )

            if not events:
                return None

            # Format events for AI context
            events_list = []
            for event in events:
                event_time = event.start.strftime('%Y-%m-%d %H:%M') if event.start else 'No date'
                events_list.append({
                    'id': event.id,
                    'title': event.title,
                    'start': event_time,
                    'description': event.description or ''
                })

            # Use AI to identify which event matches the user's message
            if ai_model.startswith("gemini"):
                ai_provider = "gemini"
            elif ai_model.startswith("gpt"):
                ai_provider = "openai"
            elif ai_model.startswith("claude"):
                ai_provider = "anthropic"
            elif ":" in ai_model:
                ai_provider = "ollama"
            else:
                ai_provider = "gemini"

            ai_client = AIClient(provider=ai_provider, model_name=ai_model, db=self._db_session)

            system_prompt = """You are helping identify which calendar event the user wants to delete.
Given a list of events and the user's message, return the ID of the matching event.

Rules:
- Match by event title, description, or time references
- If message says "this event", "last event", or "the event", choose the most recent event
- Return ONLY the event ID, nothing else
- If no clear match, return "NONE"
"""

            user_prompt = f"""User message: "{text}"

Available events:
{json.dumps(events_list, indent=2)}

Which event ID should be deleted?

Answer:"""

            response_dict = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=user_prompt
            )

            event_id = response_dict.get("answer", "").strip()

            # Validate that the returned ID exists in our events
            if event_id and event_id != "NONE":
                valid_ids = [e.id for e in events]
                if event_id in valid_ids:
                    return event_id

            return None

        except Exception as e:
            logger.error(f"Error parsing event ID from message: {e}", exc_info=True)
            return None

    async def _parse_event_update_from_message(
        self,
        text: str,
        ai_model: str,
        provider: SchedulerProviderBase
    ) -> Optional[Dict[str, Any]]:
        """
        Parse event update details from natural language message.

        Args:
            text: Natural language message
            ai_model: AI model to use for parsing
            provider: Provider to query events from

        Returns:
            Dict with event_id and update fields, or None if parsing fails
        """
        try:
            from agent.ai_client import AIClient
            import json
            import pytz

            # First, identify which event to update (similar to delete)
            event_id = await self._parse_event_id_from_message(text, ai_model, provider)
            if not event_id:
                return None

            # Now parse what changes to make
            if ai_model.startswith("gemini"):
                ai_provider = "gemini"
            elif ai_model.startswith("gpt"):
                ai_provider = "openai"
            elif ai_model.startswith("claude"):
                ai_provider = "anthropic"
            elif ":" in ai_model:
                ai_provider = "ollama"
            else:
                ai_provider = "gemini"

            ai_client = AIClient(provider=ai_provider, model_name=ai_model, db=self._db_session)

            # Get current time context
            brazil_tz = pytz.timezone('America/Sao_Paulo')
            now_brazil = datetime.now(brazil_tz)
            current_time_str = now_brazil.strftime('%Y-%m-%d %H:%M')

            system_prompt = f"""You are parsing event update details from natural language.
Current date/time (Brazil): {current_time_str}

Extract ONLY the fields that should be changed. Return JSON with:
- title: New event title (only if mentioned)
- start: New start datetime in ISO format (only if mentioned)
- end: New end datetime in ISO format (only if mentioned)
- description: New description (only if mentioned)
- location: New location (only if mentioned)

Only include fields that are explicitly being changed. If a field is not mentioned, omit it.

Example: "move the meeting to 3pm tomorrow"
{{
  "start": "2026-01-08T15:00:00"
}}

Example: "change the title to Important Meeting and move to next Monday at 10am"
{{
  "title": "Important Meeting",
  "start": "2026-01-13T10:00:00"
}}
"""

            user_prompt = f"""Message: "{text}"

What fields should be updated?

Answer (JSON only):"""

            response_dict = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=user_prompt
            )

            answer = response_dict.get("answer", "").strip()

            # Parse JSON response
            if answer.startswith('```json'):
                answer = answer[7:]
            if answer.startswith('```'):
                answer = answer[3:]
            if answer.endswith('```'):
                answer = answer[:-3]
            answer = answer.strip()

            updates = json.loads(answer)

            # Convert datetime strings to datetime objects
            if 'start' in updates:
                updates['start'] = datetime.fromisoformat(updates['start'])
            if 'end' in updates:
                updates['end'] = datetime.fromisoformat(updates['end'])

            updates['event_id'] = event_id
            return updates

        except Exception as e:
            logger.error(f"Error parsing event update from message: {e}", exc_info=True)
            return None

    async def _parse_event_from_message(self, text: str, ai_model: str) -> Optional[Dict[str, Any]]:
        """
        Parse event details from natural language using AI.

        Phase 9: AI-powered extraction of event details for external providers.

        Args:
            text: Natural language message
            ai_model: AI model to use for parsing

        Returns:
            Dict with event details: title, start, end, description, location
        """
        try:
            from agent.ai_client import AIClient
            import json
            import pytz

            # Determine provider for AI
            if ai_model.startswith("gemini"):
                ai_provider = "gemini"
            elif ai_model.startswith("gpt"):
                ai_provider = "openai"
            elif ai_model.startswith("claude"):
                ai_provider = "anthropic"
            elif ":" in ai_model:
                ai_provider = "ollama"
            else:
                ai_provider = "gemini"

            ai_client = AIClient(provider=ai_provider, model_name=ai_model, db=self._db_session)

            # Get current time in Brazil timezone for context
            brazil_tz = pytz.timezone('America/Sao_Paulo')
            now_brazil = datetime.now(brazil_tz)
            current_time_str = now_brazil.strftime('%Y-%m-%d %H:%M')
            current_weekday = now_brazil.strftime('%A')

            system_prompt = f"""You are a scheduling assistant that extracts event details from natural language.
Current date/time (Brazil/Sao Paulo): {current_time_str} ({current_weekday})

Extract the following from the user's message:
- title: Brief description of the event (required)
- start_datetime: When the event starts in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)
- end_datetime: When the event ends (optional, if mentioned OR calculated from duration)
- duration_minutes: Event duration in minutes (extract if mentioned: 30min→30, 1h→60, 2h→120, meia hora→30)
- description: Additional details (optional)
- location: Where the event takes place (optional)
- recurrence: Recurrence pattern if mentioned (daily, weekly, monthly, or null)

Return a JSON object with these fields. Use null for missing optional fields.
Always interpret relative times (like "tomorrow", "in 5 minutes", "next Monday") based on the current time provided.
If no specific time is given, assume 09:00 as the default time.
If duration_minutes is specified but end_datetime is not, calculate end_datetime = start_datetime + duration_minutes."""

            user_prompt = f"""Extract event details from this message:
"{text}"

Return ONLY a valid JSON object, no other text."""

            response_dict = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=user_prompt
            )

            answer = response_dict.get("answer", "").strip()

            # Try to parse JSON from the response
            # Handle cases where AI might wrap in code blocks
            if "```json" in answer:
                answer = answer.split("```json")[1].split("```")[0]
            elif "```" in answer:
                answer = answer.split("```")[1].split("```")[0]

            parsed = json.loads(answer)

            # Convert datetime strings to datetime objects
            result = {'title': parsed.get('title')}

            if parsed.get('start_datetime'):
                try:
                    start_dt = datetime.fromisoformat(parsed['start_datetime'].replace('Z', '+00:00'))
                    # If naive, assume Brazil timezone - keep it as naive for Google Calendar
                    # The calendar service will specify the timezone separately
                    # Don't convert to UTC - Google Calendar expects local time with timezone hint
                    if start_dt.tzinfo is not None:
                        # If it has timezone, convert to Brazil time and make naive
                        start_dt = start_dt.astimezone(brazil_tz).replace(tzinfo=None)
                    # Otherwise keep as-is (already in Brazil local time from AI)
                    result['start'] = start_dt
                    logger.info(f"FlowsSkill: Parsed start time as Brazil local: {start_dt}")
                except ValueError:
                    # Fallback to current time + 1 hour (in Brazil local)
                    result['start'] = datetime.now(brazil_tz).replace(tzinfo=None) + timedelta(hours=1)
            else:
                result['start'] = datetime.now(brazil_tz).replace(tzinfo=None) + timedelta(hours=1)

            # Extract duration_minutes if present
            duration_minutes = parsed.get('duration_minutes')
            if duration_minutes:
                try:
                    duration_minutes = int(duration_minutes)
                    result['duration_minutes'] = duration_minutes
                    logger.info(f"FlowsSkill: Extracted duration: {duration_minutes} minutes")

                    # If no end_datetime but duration is specified, calculate it
                    if not parsed.get('end_datetime') and result.get('start'):
                        result['end'] = result['start'] + timedelta(minutes=duration_minutes)
                        logger.info(f"FlowsSkill: Calculated end time from duration: {result['end']}")
                except (ValueError, TypeError):
                    pass

            if parsed.get('end_datetime'):
                try:
                    end_dt = datetime.fromisoformat(parsed['end_datetime'].replace('Z', '+00:00'))
                    if end_dt.tzinfo is not None:
                        end_dt = end_dt.astimezone(brazil_tz).replace(tzinfo=None)
                    result['end'] = end_dt
                except ValueError:
                    pass

            # Extract recurrence if present
            recurrence_pattern = parsed.get('recurrence')
            if recurrence_pattern:
                result['recurrence'] = recurrence_pattern
                logger.info(f"FlowsSkill: Extracted recurrence: {recurrence_pattern}")

            if parsed.get('description'):
                result['description'] = parsed['description']
            if parsed.get('location'):
                result['location'] = parsed['location']

            logger.info(f"FlowsSkill: Parsed event - title: {result.get('title')}, start: {result.get('start')}, end: {result.get('end')}, duration: {result.get('duration_minutes')}")
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"FlowsSkill: Failed to parse AI response as JSON: {e}")
            # Fallback: use the entire message as title
            return {
                'title': text[:100],  # Truncate if too long
                'start': datetime.now() + timedelta(hours=1)
            }
        except Exception as e:
            logger.error(f"FlowsSkill: Error parsing event from message: {e}", exc_info=True)
            return None

    async def _ai_classify(self, message: str, config: Dict[str, Any]) -> bool:
        """
        Override AI classification with Flows-specific examples.

        Phase 7.1.3: Provide specific examples for scheduling/flow operations.
        Phase 7.5: Use configurable intent detection model.
        """
        from agent.skills.ai_classifier import get_classifier

        classifier = get_classifier()
        # Phase 7.5: Resolve intent detection model (supports "inherit")
        ai_model = self._resolve_intent_detection_model(config)

        # Flows-specific examples
        custom_examples = {
            "yes": [
                "Quais são meus lembretes?",
                "Me lembre de comprar pão em 5 minutos",
                "Agende uma reunião para amanhã",
                "What are my scheduled events?",
                "Remind me to call John tomorrow",
                "List my reminders",
                "Mostra meus lembretes agendados",
                "Create a reminder for next Monday",
                "Delete the calendar event tomorrow",
                "Remove my scheduled meeting",
                "Cancel the reminder",
                "Update my calendar event"
            ],
            "no": [
                "What is a reminder?",
                "How do reminders work?",
                "Can reminders be useful?",
                "Tell me about scheduling",
                "I like reminders",
                "I need to delete that email",
                "Remove this message",
                "Check your calendar later",
                "That was a great event yesterday",
                "Delete that file",
                "What's on your calendar?",
                "Create a new document"
            ]
        }

        return await classifier.classify_intent(
            message=message,
            skill_name=self.skill_name,
            skill_description=self.skill_description,
            model=ai_model,
            custom_examples=custom_examples,
            db=self._db_session  # Phase 7.4: Pass database session for API key loading
        )

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Determine if this message should be handled by Flows skill.

        Phase 7.1.3: Uses configurable keywords + AI fallback approach.
        """
        # Get agent-specific config
        config = getattr(self, '_config', {}) or {}
        capabilities = config.get('capabilities', {})
        body_lower = message.body.lower()

        # Phase 6.11.4: Removed special handling for Agendador agent
        # Asana operations are now handled through scheduler provider configuration

        # Phase 7.1.3: Get configurable keywords (simple array)
        keywords = config.get('keywords', self.get_default_config()['keywords'])

        # Step 1: Keyword pre-filter with category-based matching to reduce false positives
        # Categorize keywords to require meaningful combinations
        primary_keywords = ['lembrete', 'lembrar', 'lembre', 'lembra', 'reminder', 'remind', 'flows', 'flow']
        secondary_keywords = ['calendar', 'calendario', 'calendário', 'agenda', 'event', 'events', 'evento',
                             'eventos', 'meeting', 'meetings', 'reunião', 'reuniões']
        action_keywords = ['delete', 'deletar', 'remover', 'cancelar', 'cancel', 'remove',
                          'update', 'atualizar', 'modificar', 'alterar', 'mudar',
                          'create', 'criar', 'crie', 'cria', 'schedule', 'agendar', 'agendamento', 'agenda',
                          'list', 'listar', 'show', 'mostrar', 'ver', 'quais', 'qual', 'what', 'which',
                          # Natural query patterns for checking calendar/events
                          'have', 'tenho', 'any', 'algum', 'alguma', 'check', 'checar', 'verificar',
                          'today', 'hoje', 'tomorrow', 'amanhã', 'amanha', 'week', 'semana',
                          'month', 'mês', 'mes', 'next', 'próximo', 'proximo']

        # Check matches across categories
        primary_match = any(kw in body_lower for kw in primary_keywords)
        secondary_match = any(kw in body_lower for kw in secondary_keywords)
        action_match = any(kw in body_lower for kw in action_keywords)

        # #region agent log
        import time
        import json as json_lib
        try:
            with open('/app/.cursor/debug.log', 'a') as f:
                f.write(json_lib.dumps({
                    'location': 'flows_skill.py:1133',
                    'message': 'FlowsSkill can_handle keyword check',
                    'data': {
                        'body': message.body,
                        'primary_match': primary_match,
                        'secondary_match': secondary_match,
                        'action_match': action_match
                    },
                    'timestamp': time.time() * 1000,
                    'sessionId': 'debug-session',
                    'hypothesisId': 'H6'
                }) + '\n')
        except:
            pass
        # #endregion

        # Count how many categories matched
        category_matches = sum([primary_match, secondary_match, action_match])

        # Require at least 2 keyword categories OR a strong primary keyword
        if category_matches < 2 and not primary_match:
            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'flows_skill.py:1157',
                        'message': 'FlowsSkill REJECTED: insufficient keywords',
                        'data': {'category_matches': category_matches},
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H6'
                    }) + '\n')
            except:
                pass
            # #endregion
            logger.debug(f"FlowsSkill: Insufficient keyword matches ({category_matches} categories) in '{message.body[:50]}...'")
            return False

        logger.info(f"FlowsSkill: Keywords matched ({category_matches} categories) in '{message.body[:50]}...'")

        # Step 2: Check capabilities and use AI to determine specific intent
        # (The AI classification will determine if it's query/create/delete/update)

        # For now, check if ANY capability is enabled
        has_enabled_capability = False
        for cap_name, cap_config in capabilities.items():
            cap_enabled = cap_config.get('enabled', True) if isinstance(cap_config, dict) else True
            if cap_enabled:
                has_enabled_capability = True
                break

        # #region agent log
        try:
            with open('/app/.cursor/debug.log', 'a') as f:
                f.write(json_lib.dumps({
                    'location': 'flows_skill.py:1191',
                    'message': 'FlowsSkill capability check',
                    'data': {
                        'has_enabled_capability': has_enabled_capability,
                        'capabilities': capabilities
                    },
                    'timestamp': time.time() * 1000,
                    'sessionId': 'debug-session',
                    'hypothesisId': 'H6'
                }) + '\n')
        except:
            pass
        # #endregion

        if not has_enabled_capability:
            logger.info(f"FlowsSkill: All capabilities disabled")
            return False

        # Use AI fallback if enabled
        use_ai = config.get('use_ai_fallback', True)
        # #region agent log
        try:
            with open('/app/.cursor/debug.log', 'a') as f:
                f.write(json_lib.dumps({
                    'location': 'flows_skill.py:1215',
                    'message': 'FlowsSkill before AI classify',
                    'data': {'use_ai': use_ai},
                    'timestamp': time.time() * 1000,
                    'sessionId': 'debug-session',
                    'hypothesisId': 'H6'
                }) + '\n')
        except:
            pass
        # #endregion
        if use_ai:
            result = await self._ai_classify(message.body, config)
            # #region agent log
            try:
                with open('/app/.cursor/debug.log', 'a') as f:
                    f.write(json_lib.dumps({
                        'location': 'flows_skill.py:1230',
                        'message': 'FlowsSkill AI classify result',
                        'data': {'result': result, 'body': message.body},
                        'timestamp': time.time() * 1000,
                        'sessionId': 'debug-session',
                        'hypothesisId': 'H6'
                    }) + '\n')
            except:
                pass
            # #endregion
            logger.info(f"FlowsSkill: AI classification result={result}")
            return result

        # Keywords matched, no AI verification needed
        logger.info(f"FlowsSkill: Keywords matched, AI disabled, handling message")
        return True

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process the message using appropriate handler.

        Phase 7.1: Uses AI to detect operation type (NO hardcoded keywords).
        Phase 7.5: Use configurable intent detection model.
        Phase 9: Multi-provider support - routes based on configured provider.

        Provider Integration:
        - FlowsProvider (default): Uses existing SchedulerSkill for AI parsing
        - GoogleCalendarProvider: Uses provider's event methods (needs structured data)
        - AsanaProvider: Uses provider's task methods (needs structured data)
        """
        try:
            # Merge capabilities with defaults (default config has enabled=True for all)
            logger.info(f"FlowsSkill: config = {config}")
            default_capabilities = self.get_default_config().get('capabilities', {})
            config_capabilities = config.get('capabilities', {})
            logger.info(f"FlowsSkill: default_capabilities keys = {list(default_capabilities.keys())}")
            logger.info(f"FlowsSkill: config_capabilities = {config_capabilities}")
            # Deep merge: for each capability, merge the config with the default
            capabilities = {}
            for cap_name, cap_default in default_capabilities.items():
                if cap_name in config_capabilities:
                    # Merge config with default
                    capabilities[cap_name] = {**cap_default, **config_capabilities[cap_name]}
                else:
                    # Use default
                    capabilities[cap_name] = cap_default
            # Add any capabilities in config that aren't in defaults
            for cap_name, cap_config in config_capabilities.items():
                if cap_name not in capabilities:
                    capabilities[cap_name] = cap_config

            logger.info(f"FlowsSkill: Final merged capabilities = {capabilities}")

            # Phase 9: Get the configured provider
            provider = self._get_provider(config)
            provider_type = provider.provider_type.value if hasattr(provider.provider_type, 'value') else str(provider.provider_type)
            provider_name = provider.provider_name
            logger.info(f"FlowsSkill: Using provider '{provider_name}' ({provider_type})")

            # Phase 7.5: Resolve intent detection model (supports "inherit")
            resolved_model = self._resolve_intent_detection_model(config)

            # Use AI to detect operation type (query vs create)
            intent = await self._detect_flow_intent(message.body, resolved_model)
            logger.info(f"FlowsSkill: AI detected operation: {intent}")

            if intent == 'query':
                # Verify query capability is enabled
                query_cap = capabilities.get('query_events', {})
                query_enabled = query_cap.get('enabled', True) if isinstance(query_cap, dict) else True

                if not query_enabled:
                    logger.warning(f"FlowsSkill: Query requested but capability disabled")
                    return SkillResult(
                        success=True,
                        output="I don't have permission to query scheduled events.",
                        processed_content="I don't have permission to query scheduled events.",
                        metadata={'capability_disabled': 'query_events', 'skip_ai': True}
                    )

                # Phase 9: Use provider for query if external, otherwise use existing flow
                if provider_type == 'flows':
                    # Use existing query skill for built-in Flows (handles AI parsing)
                    logger.info(f"FlowsSkill: Routing to built-in query handler")
                    result = await self._query.process(message, {})
                else:
                    # External provider - use provider's list_events method
                    logger.info(f"FlowsSkill: Routing query to {provider_name} provider")
                    result = await self._process_query_with_provider(provider, message)

                # Add provider info to metadata
                if result.metadata:
                    result.metadata['provider_type'] = provider_type
                    result.metadata['provider_name'] = provider_name
                return result

            elif intent == 'create':
                # For now, default to notification (scheduler handles conversation detection internally)
                notif_cap = capabilities.get('create_notification', {})
                notif_enabled = notif_cap.get('enabled', True) if isinstance(notif_cap, dict) else True

                conv_cap = capabilities.get('create_conversation', {})
                conv_enabled = conv_cap.get('enabled', True) if isinstance(conv_cap, dict) else True

                if not notif_enabled and not conv_enabled:
                    logger.warning(f"FlowsSkill: Create requested but all create capabilities disabled")
                    return SkillResult(
                        success=True,
                        output="I don't have permission to create reminders or conversations.",
                        processed_content="I don't have permission to create reminders or conversations.",
                        metadata={'capability_disabled': 'create', 'skip_ai': True}
                    )

                # Phase 9: Use provider for create if external, otherwise use existing flow
                if provider_type == 'flows':
                    # Use existing scheduler skill for built-in Flows (handles AI parsing)
                    logger.info(f"FlowsSkill: Routing to built-in scheduler handler")
                    result = await self._scheduler.process(message, {})
                else:
                    # External provider - use provider's create_event method
                    logger.info(f"FlowsSkill: Routing create to {provider_name} provider")
                    result = await self._process_create_with_provider(provider, message, resolved_model)

                # Add provider info to metadata
                if result.metadata:
                    result.metadata['provider_type'] = provider_type
                    result.metadata['provider_name'] = provider_name
                return result

            elif intent == 'delete':
                # Verify delete capability is enabled
                delete_cap = capabilities.get('delete_events', {})
                delete_enabled = delete_cap.get('enabled', True) if isinstance(delete_cap, dict) else True

                if not delete_enabled:
                    logger.warning(f"FlowsSkill: Delete requested but capability disabled")
                    return SkillResult(
                        success=True,
                        output="I don't have permission to delete events.",
                        processed_content="I don't have permission to delete events.",
                        metadata={'capability_disabled': 'delete_events', 'skip_ai': True}
                    )

                # Delete operation requires provider (no built-in Flows delete from NL)
                logger.info(f"FlowsSkill: Routing delete to {provider_name} provider")
                result = await self._process_delete_with_provider(provider, message, resolved_model)

                # Add provider info to metadata
                if result.metadata:
                    result.metadata['provider_type'] = provider_type
                    result.metadata['provider_name'] = provider_name
                return result

            elif intent == 'update':
                # Verify update capability is enabled
                update_cap = capabilities.get('update_events', {})
                update_enabled = update_cap.get('enabled', True) if isinstance(update_cap, dict) else True

                if not update_enabled:
                    logger.warning(f"FlowsSkill: Update requested but capability disabled")
                    return SkillResult(
                        success=True,
                        output="I don't have permission to update events.",
                        processed_content="I don't have permission to update events.",
                        metadata={'capability_disabled': 'update_events', 'skip_ai': True}
                    )

                # Update operation requires provider (no built-in Flows update from NL)
                logger.info(f"FlowsSkill: Routing update to {provider_name} provider")
                result = await self._process_update_with_provider(provider, message, resolved_model)

                # Add provider info to metadata
                if result.metadata:
                    result.metadata['provider_type'] = provider_type
                    result.metadata['provider_name'] = provider_name
                return result

            else:
                # Unknown intent
                return SkillResult(
                    success=False,
                    output="❌ Could not understand the operation. Try:\n• 'What are my reminders?'\n• 'Remind me to X'\n• 'Delete event X'\n• 'Update event Y'",
                    metadata={'error': 'unknown_intent', 'skip_ai': True, 'provider_type': provider_type}
                )

        except Exception as e:
            logger.error(f"FlowsSkill: Error processing message: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error processing flow request: {str(e)}",
                processed_content=f"Error processing flow request: {str(e)}",
                metadata={'error': str(e), 'skip_ai': False}
            )

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration with all capabilities and configurable keywords.

        Phase 7.1.3: Added multi-category keyword configuration.
        Phase 7.5: Added configurable intent detection model.
        Phase 9: Added scheduler provider configuration.
        """
        return {
            # Phase 7.1.3: Minimal keywords with verb forms for grammatical coverage
            "keywords": [
                # Portuguese - noun + verb conjugations
                "lembrete", "lembrar", "lembre", "lembra",
                # English - noun + verb forms
                "reminder", "remind",
                # System name
                "flows", "flow",
                # Calendar keywords (for Google Calendar provider)
                "calendar", "meeting", "reunião", "evento",
                "schedule", "agendar", "agenda",
                # Delete/Update keywords
                "delete", "deletar", "remover", "cancelar", "cancel",
                "update", "atualizar", "modificar", "alterar", "mudar"
            ],
            "use_ai_fallback": True,
            "ai_model": "gemini-2.5-flash",  # DEPRECATED: Use intent_detection_model instead
            # Phase 7.5: Configurable intent detection model
            "intent_detection_model": "gemini-2.5-flash",  # Can be "inherit", specific model, or default
            # Phase 9: Scheduler provider configuration
            "scheduler_provider": "flows",  # "flows" (default), "google_calendar", "asana"
            "integration_id": None,  # Hub integration ID (required for external providers)
            "capabilities": {
                "create_notification": {
                    "enabled": True,
                    "label": "Create Notifications (Reminders)",
                    "description": "Schedule single-message reminders"
                },
                "create_conversation": {
                    "enabled": True,
                    "label": "Create Conversations",
                    "description": "Schedule multi-turn AI conversations"
                },
                "query_events": {
                    "enabled": True,
                    "label": "Query Events",
                    "description": "List and search scheduled events"
                },
                "update_events": {
                    "enabled": True,
                    "label": "Update Events",
                    "description": "Modify existing scheduled events"
                },
                "delete_events": {
                    "enabled": True,
                    "label": "Delete Events",
                    "description": "Cancel scheduled events"
                }
            }
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for configuration UI.

        Phase 7.1.3: Merges base schema (keywords, AI fallback) with Flows-specific capabilities.
        Phase 7.5: Added intent_detection_model configuration, deprecated ai_model.
        Phase 9: Added scheduler provider selection.
        """
        # Get base schema (includes keywords, use_ai_fallback, ai_model)
        base_schema = super().get_config_schema()

        # Phase 7.5: Hide the legacy ai_model field (use intent_detection_model instead)
        if "ai_model" in base_schema["properties"]:
            del base_schema["properties"]["ai_model"]

        # Phase 7.5: Add intent_detection_model field
        base_schema["properties"]["intent_detection_model"] = {
            "type": "string",
            "title": "Intent Detection Model",
            "description": "AI model for intent classification. Use 'inherit' to use agent's primary model, or specify a model name (e.g., 'gemini-2.5-flash', 'gemma2:4b')",
            "default": "gemini-2.5-flash",
            "enum": [
                "inherit",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gpt-3.5-turbo",
                "gpt-4",
                "claude-haiku"
            ]
        }

        # Phase 9: Add scheduler provider configuration
        base_schema["properties"]["scheduler_provider"] = {
            "type": "string",
            "title": "Scheduler Provider",
            "description": "Which scheduling system to use. Built-in Flows (default), Google Calendar, or Asana.",
            "default": "flows",
            "enum": ["flows", "google_calendar", "asana"],
            "enumNames": ["Built-in Flows", "Google Calendar", "Asana Tasks"]
        }

        base_schema["properties"]["integration_id"] = {
            "type": ["integer", "null"],
            "title": "Integration",
            "description": "Select which integration to use (required for Google Calendar and Asana providers)",
            "default": None
        }

        # Add Flows-specific capabilities
        base_schema["properties"]["capabilities"] = {
                    "type": "object",
                    "title": "Flow Capabilities",
                    "description": "Control what the agent can do with Flows",
                    "properties": {
                        "create_notification": {
                            "type": "object",
                            "title": "Create Notifications",
                            "description": "Enable scheduling single-message reminders",
                            "properties": {
                                "enabled": {
                                    "type": "boolean",
                                    "default": True,
                                    "title": "Enabled"
                                }
                            }
                        },
                        "create_conversation": {
                            "type": "object",
                            "title": "Create Conversations",
                            "description": "Enable scheduling multi-turn AI conversations",
                            "properties": {
                                "enabled": {
                                    "type": "boolean",
                                    "default": True,
                                    "title": "Enabled"
                                }
                            }
                        },
                        "query_events": {
                            "type": "object",
                            "title": "Query Events",
                            "description": "Enable listing and searching scheduled events",
                            "properties": {
                                "enabled": {
                                    "type": "boolean",
                                    "default": True,
                                    "title": "Enabled"
                                }
                            }
                        },
                        "update_events": {
                            "type": "object",
                            "title": "Update Events (Coming Soon)",
                            "description": "Enable modifying existing scheduled events",
                            "properties": {
                                "enabled": {
                                    "type": "boolean",
                                    "default": False,
                                    "title": "Enabled"
                                }
                            }
                        },
                        "delete_events": {
                            "type": "object",
                            "title": "Delete Events (Coming Soon)",
                            "description": "Enable canceling scheduled events",
                            "properties": {
                                "enabled": {
                                    "type": "boolean",
                                    "default": False,
                                    "title": "Enabled"
                                }
                            }
                        }
                    }
                }

        return base_schema

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION (Phase 4)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        Return MCP-compliant tool definition for reminder/event management.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools

        Uses single tool with action parameter (like GmailSkill pattern)
        to handle create/list/update/delete operations.
        """
        return {
            "name": "manage_reminders",
            "title": "Reminder Management",
            "description": (
                "Create, list, update, or delete reminders and scheduled events. "
                "Use when user wants to schedule reminders, check their calendar, "
                "modify existing events, or cancel scheduled items."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create", "list", "update", "delete"],
                        "description": "Action to perform: 'create' (new reminder), 'list' (show reminders), 'update' (modify), 'delete' (cancel)"
                    },
                    "title": {
                        "type": "string",
                        "description": "Title/description of the reminder (required for create)"
                    },
                    "datetime": {
                        "type": "string",
                        "description": "When the reminder should trigger. Accepts ISO 8601 format (2026-02-03T14:30:00) or natural language ('tomorrow at 3pm', 'in 5 minutes')"
                    },
                    "reminder_id": {
                        "type": "string",
                        "description": "ID of the reminder (required for update/delete). Get IDs from 'list' action."
                    },
                    "recurrence": {
                        "type": "string",
                        "enum": ["none", "daily", "weekly", "monthly"],
                        "description": "Recurrence pattern for recurring reminders",
                        "default": "none"
                    },
                    "days_ahead": {
                        "type": "integer",
                        "description": "For 'list' action: how many days ahead to show (default: 7)",
                        "default": 7
                    },
                    "description": {
                        "type": "string",
                        "description": "Additional details or notes for the reminder"
                    },
                    "location": {
                        "type": "string",
                        "description": "Location for the event (if applicable)"
                    }
                },
                "required": ["action"]
            },
            "annotations": {
                "destructive": True,  # Can create/delete events
                "idempotent": False,
                "audience": ["user", "assistant"]
            }
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Reminder operations are generally safe but should still be monitored.
        """
        return {
            "expected_intents": [
                "Create a new reminder or scheduled event",
                "List existing reminders and events",
                "Update or modify scheduled events",
                "Delete or cancel reminders"
            ],
            "expected_patterns": [
                "reminder", "remind", "schedule", "calendar", "event",
                "lembrete", "lembrar", "agendar", "agenda", "evento"
            ],
            "risk_notes": "Monitor for suspicious patterns like bulk deletions or unusual scheduling patterns."
        }

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute reminder management as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - action: 'create', 'list', 'update', or 'delete' (required)
                - title: Reminder title (for create)
                - datetime: When to trigger (for create/update)
                - reminder_id: Event ID (for update/delete)
                - recurrence: Recurrence pattern
                - days_ahead: Days to show (for list)
                - description: Additional notes
                - location: Event location
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with operation result
        """
        action = arguments.get("action")

        if not action:
            return SkillResult(
                success=False,
                output="Action is required. Use 'create', 'list', 'update', or 'delete'.",
                metadata={"error": "missing_action", "skip_ai": True}
            )

        # Merge capabilities with defaults
        default_capabilities = self.get_default_config().get('capabilities', {})
        config_capabilities = config.get('capabilities', {})
        capabilities = {}
        for cap_name, cap_default in default_capabilities.items():
            if cap_name in config_capabilities:
                capabilities[cap_name] = {**cap_default, **config_capabilities[cap_name]}
            else:
                capabilities[cap_name] = cap_default

        # Get provider
        provider = self._get_provider(config)
        provider_type = provider.provider_type.value if hasattr(provider.provider_type, 'value') else str(provider.provider_type)
        provider_name = provider.provider_name
        logger.info(f"FlowsSkill.execute_tool: action={action}, provider={provider_name}")

        try:
            if action == "create":
                return await self._execute_tool_create(arguments, message, config, capabilities, provider)
            elif action == "list":
                return await self._execute_tool_list(arguments, config, capabilities, provider)
            elif action == "update":
                return await self._execute_tool_update(arguments, message, config, capabilities, provider)
            elif action == "delete":
                return await self._execute_tool_delete(arguments, message, config, capabilities, provider)
            else:
                return SkillResult(
                    success=False,
                    output=f"Unknown action: {action}. Use 'create', 'list', 'update', or 'delete'.",
                    metadata={"error": "invalid_action", "skip_ai": True}
                )

        except Exception as e:
            logger.error(f"FlowsSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error executing reminder operation: {str(e)}",
                metadata={"error": str(e), "skip_ai": True}
            )

    async def _execute_tool_create(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any],
        capabilities: Dict[str, Any],
        provider: SchedulerProviderBase
    ) -> SkillResult:
        """Execute create reminder action for tool mode."""
        # Check capability
        notif_cap = capabilities.get('create_notification', {})
        notif_enabled = notif_cap.get('enabled', True) if isinstance(notif_cap, dict) else True

        if not notif_enabled:
            return SkillResult(
                success=False,
                output="Creating reminders is not enabled for this agent.",
                metadata={"capability_disabled": "create_notification", "skip_ai": True}
            )

        title = arguments.get("title")
        datetime_str = arguments.get("datetime")

        if not title:
            return SkillResult(
                success=False,
                output="Title is required for creating a reminder.",
                metadata={"error": "missing_title", "skip_ai": True}
            )

        if not datetime_str:
            return SkillResult(
                success=False,
                output="Date/time is required for creating a reminder. Specify when the reminder should trigger.",
                metadata={"error": "missing_datetime", "skip_ai": True}
            )

        # Parse datetime
        import pytz
        from datetime import timedelta

        brazil_tz = pytz.timezone('America/Sao_Paulo')
        now = datetime.now(brazil_tz)

        try:
            # Try ISO format first
            start_dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            if start_dt.tzinfo is not None:
                start_dt = start_dt.astimezone(brazil_tz).replace(tzinfo=None)
        except ValueError:
            # Natural language - use AI to parse
            resolved_model = self._resolve_intent_detection_model(config)
            parsed = await self._parse_event_from_message(f"Remind me to {title} {datetime_str}", resolved_model)
            if parsed and parsed.get('start'):
                start_dt = parsed['start']
            else:
                return SkillResult(
                    success=False,
                    output=f"Could not understand the date/time: '{datetime_str}'. Please use ISO format (2026-02-03T14:30:00) or natural language.",
                    metadata={"error": "datetime_parse_failed", "skip_ai": True}
                )

        # Parse recurrence
        recurrence_rrule = None
        recurrence = arguments.get("recurrence", "none")
        if recurrence and recurrence != "none":
            if recurrence == "daily":
                recurrence_rrule = 'RRULE:FREQ=DAILY;INTERVAL=1'
            elif recurrence == "weekly":
                recurrence_rrule = 'RRULE:FREQ=WEEKLY;INTERVAL=1'
            elif recurrence == "monthly":
                recurrence_rrule = 'RRULE:FREQ=MONTHLY;INTERVAL=1'

        # Create event via provider
        provider_type = provider.provider_type.value
        provider_name = provider.provider_name

        event = await provider.create_event(
            title=title,
            start=start_dt,
            end=None,
            description=arguments.get("description"),
            location=arguments.get("location"),
            recurrence=recurrence_rrule,
            reminder_minutes=30
        )

        # Format confirmation
        event_time = event.start.strftime('%m/%d/%Y at %H:%M') if event.start else 'Not specified'

        confirmation = f"✅ Reminder created via {provider_name}!\n\n"
        confirmation += f"📌 **{event.title}**\n"
        confirmation += f"📅 {event_time}\n"

        if recurrence_rrule:
            if 'DAILY' in recurrence_rrule:
                confirmation += f"🔁 Repeats: Daily\n"
            elif 'WEEKLY' in recurrence_rrule:
                confirmation += f"🔁 Repeats: Weekly\n"
            elif 'MONTHLY' in recurrence_rrule:
                confirmation += f"🔁 Repeats: Monthly\n"

        if event.description:
            confirmation += f"📝 {event.description}\n"
        if event.location:
            confirmation += f"📍 {event.location}\n"
        confirmation += f"\n🔖 ID: {event.id}"

        return SkillResult(
            success=True,
            output=confirmation,
            metadata={
                "skip_ai": True,
                "event_id": event.id,
                "provider_type": provider_type,
                "action": "create"
            }
        )

    async def _execute_tool_list(
        self,
        arguments: Dict[str, Any],
        config: Dict[str, Any],
        capabilities: Dict[str, Any],
        provider: SchedulerProviderBase
    ) -> SkillResult:
        """Execute list reminders action for tool mode."""
        # Check capability
        query_cap = capabilities.get('query_events', {})
        query_enabled = query_cap.get('enabled', True) if isinstance(query_cap, dict) else True

        if not query_enabled:
            return SkillResult(
                success=False,
                output="Listing reminders is not enabled for this agent.",
                metadata={"capability_disabled": "query_events", "skip_ai": True}
            )

        days_ahead = arguments.get("days_ahead", 7)
        now = datetime.now()
        end = now + timedelta(days=days_ahead)

        provider_name = provider.provider_name
        provider_type = provider.provider_type.value

        events = await provider.list_events(start=now, end=end, max_results=20)

        if not events:
            return SkillResult(
                success=True,
                output=f"📅 No upcoming reminders via {provider_name} in the next {days_ahead} days.",
                metadata={"skip_ai": True, "event_count": 0, "provider_type": provider_type}
            )

        # Format events
        import re
        lines = [f"📅 Your reminders via {provider_name} ({len(events)} found):\n"]
        for event in events:
            event_time = event.start.strftime('%m/%d/%Y at %H:%M') if event.start else 'No date'
            status_emoji = '✅' if event.status.value == 'completed' else '📌'

            short_id = event.id.split('_')[-1][:8] if '_' in event.id else event.id[:8]

            lines.append(f"  {status_emoji} **{event.title}**")
            lines.append(f"      📅 {event_time}")

            if event.description:
                clean_desc = re.sub(r'<[^>]+>', '', event.description)
                clean_desc = clean_desc.replace('&nbsp;', ' ').strip()
                if clean_desc and len(clean_desc) > 3:
                    lines.append(f"      📝 {clean_desc[:80]}{'...' if len(clean_desc) > 80 else ''}")

            lines.append(f"      🔖 ID: {event.id}\n")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={
                "skip_ai": True,
                "event_count": len(events),
                "provider_type": provider_type,
                "action": "list"
            }
        )

    async def _execute_tool_update(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any],
        capabilities: Dict[str, Any],
        provider: SchedulerProviderBase
    ) -> SkillResult:
        """Execute update reminder action for tool mode."""
        # Check capability
        update_cap = capabilities.get('update_events', {})
        update_enabled = update_cap.get('enabled', True) if isinstance(update_cap, dict) else True

        if not update_enabled:
            return SkillResult(
                success=False,
                output="Updating reminders is not enabled for this agent.",
                metadata={"capability_disabled": "update_events", "skip_ai": True}
            )

        reminder_id = arguments.get("reminder_id")
        if not reminder_id:
            return SkillResult(
                success=False,
                output="Reminder ID is required for update. Use 'list' action first to get the ID.",
                metadata={"error": "missing_reminder_id", "skip_ai": True}
            )

        # Parse datetime if provided
        import pytz
        new_start = None
        datetime_str = arguments.get("datetime")
        if datetime_str:
            brazil_tz = pytz.timezone('America/Sao_Paulo')
            try:
                new_start = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                if new_start.tzinfo is not None:
                    new_start = new_start.astimezone(brazil_tz).replace(tzinfo=None)
            except ValueError:
                resolved_model = self._resolve_intent_detection_model(config)
                parsed = await self._parse_event_from_message(f"Update to {datetime_str}", resolved_model)
                if parsed and parsed.get('start'):
                    new_start = parsed['start']

        provider_name = provider.provider_name
        provider_type = provider.provider_type.value

        # Update event
        event = await provider.update_event(
            event_id=reminder_id,
            title=arguments.get("title"),
            start=new_start,
            end=None,
            description=arguments.get("description"),
            location=arguments.get("location")
        )

        event_time = event.start.strftime('%m/%d/%Y at %H:%M') if event.start else 'Not specified'

        confirmation = f"✅ Reminder updated via {provider_name}!\n\n"
        confirmation += f"📌 **{event.title}**\n"
        confirmation += f"📅 {event_time}\n"
        if event.description:
            confirmation += f"📝 {event.description}\n"
        if event.location:
            confirmation += f"📍 {event.location}\n"

        return SkillResult(
            success=True,
            output=confirmation,
            metadata={
                "skip_ai": True,
                "event_id": event.id,
                "provider_type": provider_type,
                "action": "update"
            }
        )

    async def _execute_tool_delete(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any],
        capabilities: Dict[str, Any],
        provider: SchedulerProviderBase
    ) -> SkillResult:
        """Execute delete reminder action for tool mode."""
        # Check capability
        delete_cap = capabilities.get('delete_events', {})
        delete_enabled = delete_cap.get('enabled', True) if isinstance(delete_cap, dict) else True

        if not delete_enabled:
            return SkillResult(
                success=False,
                output="Deleting reminders is not enabled for this agent.",
                metadata={"capability_disabled": "delete_events", "skip_ai": True}
            )

        reminder_id = arguments.get("reminder_id")
        if not reminder_id:
            return SkillResult(
                success=False,
                output="Reminder ID is required for delete. Use 'list' action first to get the ID.",
                metadata={"error": "missing_reminder_id", "skip_ai": True}
            )

        provider_name = provider.provider_name
        provider_type = provider.provider_type.value

        # Get event details before deleting
        event = await provider.get_event(reminder_id)
        event_title = event.title if event else reminder_id

        # Delete event
        success = await provider.delete_event(reminder_id)

        if success:
            return SkillResult(
                success=True,
                output=f"✅ Reminder deleted via {provider_name}!\n\n📌 **{event_title}** has been removed.",
                metadata={
                    "skip_ai": True,
                    "event_id": reminder_id,
                    "provider_type": provider_type,
                    "action": "delete"
                }
            )
        else:
            return SkillResult(
                success=False,
                output=f"❌ Could not delete the reminder. Please verify the ID is correct: {reminder_id}",
                metadata={"error": "delete_failed", "skip_ai": True}
            )
