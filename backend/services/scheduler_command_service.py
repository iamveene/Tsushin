"""
Scheduler Command Service

Handles /scheduler slash command operations:
- info: Show provider and account information
- list: List events with date filters
- create: Create events with natural language parsing
- update: Update event details
- delete: Delete events

Supports all scheduler providers (Flows, Google Calendar, Asana).
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import dateparser
import pytz

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Brazil timezone (GMT-3) - consistent with existing scheduler implementation
BRAZIL_TZ = pytz.timezone('America/Sao_Paulo')


class SchedulerCommandService:
    """
    Service for executing scheduler slash commands.

    Features:
    - Multi-provider support (Flows, Google Calendar, Asana)
    - Natural language date parsing
    - Smart event identification (by ID or title)
    - Date filter parsing (today, tomorrow, week, month, specific dates)
    - Permission-aware operations
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    # =========================================================================
    # Command Handlers
    # =========================================================================

    async def execute_info(
        self,
        tenant_id: str,
        agent_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Show scheduler provider and account information.

        Returns provider type, capabilities, and account details.
        """
        try:
            from agent.skills.scheduler.factory import SchedulerProviderFactory

            # Get provider for agent
            provider = SchedulerProviderFactory.get_provider_for_agent(
                agent_id=agent_id,
                db=self.db
            )

            # Get provider info
            provider_type = provider.provider_type.value
            provider_name = provider.provider_name
            capabilities = provider.get_capabilities()
            permissions = provider.get_permissions()

            # Format capabilities
            cap_lines = []
            if capabilities.get('end_time'):
                cap_lines.append("✓ Event start and end times")
            if capabilities.get('location'):
                cap_lines.append("✓ Location support")
            if capabilities.get('attendees'):
                cap_lines.append("✓ Multiple attendees")
            if capabilities.get('recurrence'):
                cap_lines.append("✓ Recurring events")
            if capabilities.get('reminders'):
                cap_lines.append("✓ Reminders")
            if capabilities.get('availability'):
                cap_lines.append("✓ Free/busy checking")

            # Format permissions
            perm_lines = []
            if permissions.get('read'):
                perm_lines.append("✓ Read access")
            else:
                perm_lines.append("✗ No read access")

            if permissions.get('write'):
                perm_lines.append("✓ Write access")
            else:
                perm_lines.append("✗ No write access")

            # Provider-specific details
            details = []

            if provider_type == "google_calendar":
                # Get integration details
                from models import HubIntegration
                if hasattr(provider, 'integration_id') and provider.integration_id:
                    integration = self.db.query(HubIntegration).filter(
                        HubIntegration.id == provider.integration_id
                    ).first()
                    if integration:
                        email = getattr(integration, 'email_address', 'N/A')
                        calendar_id = getattr(integration, 'default_calendar_id', 'primary')
                        details.append(f"📧 **Account:** {email}")
                        details.append(f"📆 **Calendar:** {calendar_id}")

            elif provider_type == "asana":
                # Get Asana workspace details
                from models import HubIntegration
                if hasattr(provider, 'integration_id') and provider.integration_id:
                    integration = self.db.query(HubIntegration).filter(
                        HubIntegration.id == provider.integration_id
                    ).first()
                    if integration:
                        workspace = getattr(integration, 'workspace_name', 'N/A')
                        details.append(f"🏢 **Workspace:** {workspace}")

            # Build message
            message = f"""📅 **Scheduler: {provider_name}**

{chr(10).join(details) if details else ''}

**Capabilities:**
{chr(10).join(cap_lines)}

**Permissions:**
{chr(10).join(perm_lines)}

💡 *Use `/scheduler list` to see upcoming events*"""

            return {
                "status": "success",
                "action": "scheduler_info",
                "provider": {
                    "type": provider_type,
                    "name": provider_name,
                    "capabilities": capabilities,
                    "permissions": permissions
                },
                "message": message
            }

        except Exception as e:
            self.logger.error(f"Error in execute_info: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "scheduler_info",
                "error": str(e),
                "message": f"❌ Failed to get scheduler info: {str(e)}"
            }

    async def execute_list(
        self,
        tenant_id: str,
        agent_id: int,
        date_filter: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        List events with optional date filter.

        Filters: all, today, tomorrow, week, month, or specific dates
        """
        try:
            from agent.skills.scheduler.factory import SchedulerProviderFactory

            # Get provider
            provider = SchedulerProviderFactory.get_provider_for_agent(
                agent_id=agent_id,
                db=self.db
            )

            # Parse date filter
            start, end, filter_label = self._parse_date_filter(date_filter or "week")

            # List events
            events = await provider.list_events(
                start=start,
                end=end,
                max_results=50
            )

            if not events:
                return {
                    "status": "success",
                    "action": "scheduler_list",
                    "events": [],
                    "message": f"📅 **No events {filter_label}**\n\nUse `/scheduler create` to add events."
                }

            # Group events by date
            from collections import defaultdict
            by_date = defaultdict(list)

            for event in events:
                date_key = event.start.strftime("%Y-%m-%d")
                by_date[date_key].append(event)

            # Format message
            lines = [f"📅 **Events {filter_label}**\n"]

            for date_key in sorted(by_date.keys()):
                day_events = by_date[date_key]
                # Format date header
                date_obj = datetime.strptime(date_key, "%Y-%m-%d")
                date_header = date_obj.strftime("%A, %B %d, %Y")
                lines.append(f"**{date_header}**")

                for event in sorted(day_events, key=lambda e: e.start):
                    time_str = event.start.strftime("%I:%M %p")
                    if event.end:
                        end_str = event.end.strftime("%I:%M %p")
                        time_str += f" - {end_str}"

                    # Add status indicator
                    status_icon = "📌" if event.status.value == "scheduled" else "✅"

                    # Format event line
                    event_line = f"  {status_icon} **{event.title}** ({time_str})"
                    if event.description:
                        event_line += f"\n     _{event.description[:50]}{'...' if len(event.description) > 50 else ''}_"
                    event_line += f"\n     ID: `{event.id}`"
                    lines.append(event_line)

                lines.append("")  # Blank line between days

            lines.append(f"💡 *Showing {len(events)} event(s). Use `/scheduler create` to add more.*")

            return {
                "status": "success",
                "action": "scheduler_list",
                "events": [e.to_dict() for e in events],
                "filter": filter_label,
                "message": "\n".join(lines)
            }

        except Exception as e:
            self.logger.error(f"Error in execute_list: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "scheduler_list",
                "error": str(e),
                "message": f"❌ Failed to list events: {str(e)}"
            }

    async def execute_create(
        self,
        tenant_id: str,
        agent_id: int,
        input_text: str,
        sender_key: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create an event from natural language input.

        Examples:
        - "Team meeting tomorrow at 3pm"
        - "Dentist appointment on Jan 15 at 2pm about cleaning"
        - "Buy groceries today at 5pm"
        """
        try:
            from agent.skills.scheduler.factory import SchedulerProviderFactory

            if not input_text or not input_text.strip():
                return {
                    "status": "error",
                    "action": "scheduler_create",
                    "message": "❌ Please provide event details.\n\n**Usage:** `/scheduler create <description>`\n**Example:** `/scheduler create Team meeting tomorrow at 3pm`"
                }

            # Parse natural language input
            parsed = self._parse_create_input(input_text.strip())

            if not parsed.get('title'):
                return {
                    "status": "error",
                    "action": "scheduler_create",
                    "message": "❌ Could not understand event title.\n\n**Usage:** `/scheduler create <description>`\n**Example:** `/scheduler create Team meeting tomorrow at 3pm`"
                }

            if not parsed.get('start'):
                return {
                    "status": "error",
                    "action": "scheduler_create",
                    "message": f"❌ Could not parse date/time from: \"{input_text}\"\n\n**Example:** `/scheduler create Team meeting tomorrow at 3pm`\n\nTry including explicit time like 'tomorrow at 3pm' or 'Jan 15 at 2pm'"
                }

            # Get provider
            provider = SchedulerProviderFactory.get_provider_for_agent(
                agent_id=agent_id,
                db=self.db
            )

            # Log parsed values for debugging
            self.logger.info(f"Creating event with parsed values: title={parsed['title']}, start={parsed['start']}, end={parsed.get('end')}, duration_minutes={parsed.get('duration_minutes')}, recurrence={parsed.get('recurrence')}")

            # Create event with recurrence and duration
            event = await provider.create_event(
                title=parsed['title'],
                start=parsed['start'],
                end=parsed.get('end'),
                description=parsed.get('description'),
                recurrence=parsed.get('recurrence'),
                recipient=sender_key
            )

            # Format success message
            time_str = event.start.strftime("%A, %B %d at %I:%M %p")

            message = f"""✅ **Event created successfully!**

📌 **{event.title}**
🕐 {time_str}"""

            # Add duration info if available
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

                # Show duration if not default 1 hour
                if duration_minutes != 60:
                    message += f"\n⏱️ Duration: {duration_str}"
                    if event.end:
                        end_str = event.end.strftime("%I:%M %p")
                        message += f" (ends at {end_str})"

            # Add recurrence info
            if parsed.get('recurrence'):
                recurrence_str = parsed['recurrence']
                if 'DAILY' in recurrence_str:
                    message += f"\n🔁 Repeats: Daily"
                elif 'WEEKLY' in recurrence_str:
                    if 'BYDAY' in recurrence_str:
                        # Extract day from RRULE
                        day_abbr = recurrence_str.split('BYDAY=')[1][:2]
                        day_names = {'MO': 'Mondays', 'TU': 'Tuesdays', 'WE': 'Wednesdays',
                                   'TH': 'Thursdays', 'FR': 'Fridays', 'SA': 'Saturdays', 'SU': 'Sundays'}
                        message += f"\n🔁 Repeats: Every {day_names.get(day_abbr, 'week')}"
                    else:
                        message += f"\n🔁 Repeats: Weekly"
                elif 'MONTHLY' in recurrence_str:
                    message += f"\n🔁 Repeats: Monthly"

            if event.description:
                message += f"\n📝 {event.description}"

            message += f"\n\n💡 *Event ID: `{event.id}`*"
            message += f"\n*Use `/scheduler list` to see all events*"

            return {
                "status": "success",
                "action": "scheduler_create",
                "event": event.to_dict(),
                "message": message
            }

        except Exception as e:
            self.logger.error(f"Error in execute_create: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "scheduler_create",
                "error": str(e),
                "message": f"❌ Failed to create event: {str(e)}"
            }

    async def execute_update(
        self,
        tenant_id: str,
        agent_id: int,
        event_identifier: str,
        new_name: Optional[str] = None,
        new_description: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update an event's name and/or description.

        Args:
            event_identifier: Event ID or title
            new_name: New title (optional)
            new_description: New description (optional)
        """
        try:
            from agent.skills.scheduler.factory import SchedulerProviderFactory

            if not event_identifier:
                return {
                    "status": "error",
                    "action": "scheduler_update",
                    "message": "❌ Please specify which event to update.\n\n**Usage:** `/scheduler update <event_id_or_name> new_name <name> new_description <desc>`"
                }

            if not new_name and not new_description:
                return {
                    "status": "error",
                    "action": "scheduler_update",
                    "message": "❌ Please specify what to update.\n\n**Usage:** `/scheduler update <event_id_or_name> new_name <name> new_description <desc>`"
                }

            # Get provider
            provider = SchedulerProviderFactory.get_provider_for_agent(
                agent_id=agent_id,
                db=self.db
            )

            # Find event
            event = await self._find_event(provider, event_identifier)

            if not event:
                return {
                    "status": "error",
                    "action": "scheduler_update",
                    "message": f"❌ Event not found: \"{event_identifier}\"\n\nUse `/scheduler list` to see available events."
                }

            if isinstance(event, list):
                # Multiple matches - disambiguation needed
                lines = [f"❌ Multiple events match \"{event_identifier}\":\n"]
                for e in event:
                    time_str = e.start.strftime("%m/%d %I:%M%p")
                    lines.append(f"  • **{e.title}** ({time_str}) - ID: `{e.id}`")
                lines.append(f"\n💡 Use the event ID to update a specific event.")
                return {
                    "status": "error",
                    "action": "scheduler_update",
                    "message": "\n".join(lines)
                }

            # Update event
            updated = await provider.update_event(
                event_id=event.id,
                title=new_name if new_name else None,
                description=new_description if new_description else None
            )

            # Format success message
            message = f"✅ **Event updated successfully!**\n\n"

            if new_name:
                message += f"📌 **Title:** {new_name}\n"
            if new_description:
                message += f"📝 **Description:** {new_description}\n"

            message += f"\n💡 *Event ID: `{updated.id}`*"

            return {
                "status": "success",
                "action": "scheduler_update",
                "event": updated.to_dict(),
                "message": message
            }

        except Exception as e:
            self.logger.error(f"Error in execute_update: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "scheduler_update",
                "error": str(e),
                "message": f"❌ Failed to update event: {str(e)}"
            }

    async def execute_delete(
        self,
        tenant_id: str,
        agent_id: int,
        event_identifier: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Delete an event by ID or title.

        Args:
            event_identifier: Event ID or title
        """
        try:
            from agent.skills.scheduler.factory import SchedulerProviderFactory

            if not event_identifier:
                return {
                    "status": "error",
                    "action": "scheduler_delete",
                    "message": "❌ Please specify which event to delete.\n\n**Usage:** `/scheduler delete <event_id_or_name>`"
                }

            # Get provider
            provider = SchedulerProviderFactory.get_provider_for_agent(
                agent_id=agent_id,
                db=self.db
            )

            # Find event
            event = await self._find_event(provider, event_identifier)

            if not event:
                return {
                    "status": "error",
                    "action": "scheduler_delete",
                    "message": f"❌ Event not found: \"{event_identifier}\"\n\nUse `/scheduler list` to see available events."
                }

            if isinstance(event, list):
                # Multiple matches - disambiguation needed
                lines = [f"❌ Multiple events match \"{event_identifier}\":\n"]
                for e in event:
                    time_str = e.start.strftime("%m/%d %I:%M%p")
                    lines.append(f"  • **{e.title}** ({time_str}) - ID: `{e.id}`")
                lines.append(f"\n💡 Use the event ID to delete a specific event.")
                return {
                    "status": "error",
                    "action": "scheduler_delete",
                    "message": "\n".join(lines)
                }

            # Delete event
            success = await provider.delete_event(event_id=event.id)

            if success:
                time_str = event.start.strftime("%A, %B %d at %I:%M %p")
                message = f"""✅ **Event deleted successfully!**

🗑️ Deleted: **{event.title}**
🕐 Was scheduled for: {time_str}"""

                return {
                    "status": "success",
                    "action": "scheduler_delete",
                    "event_id": event.id,
                    "message": message
                }
            else:
                return {
                    "status": "error",
                    "action": "scheduler_delete",
                    "message": f"❌ Failed to delete event: {event.title}"
                }

        except Exception as e:
            self.logger.error(f"Error in execute_delete: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "scheduler_delete",
                "error": str(e),
                "message": f"❌ Failed to delete event: {str(e)}"
            }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_date_filter(self, filter_str: str) -> Tuple[datetime, datetime, str]:
        """
        Parse date filter into start/end datetime range.

        Returns:
            Tuple of (start, end, human_readable_label)
        """
        now = datetime.now(BRAZIL_TZ)
        filter_str = filter_str.lower().strip()

        if filter_str in ["today", "hoje"]:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            label = "today"

        elif filter_str in ["tomorrow", "amanhã", "amanha"]:
            tomorrow = now + timedelta(days=1)
            start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
            end = tomorrow.replace(hour=23, minute=59, second=59, microsecond=999999)
            label = "tomorrow"

        elif filter_str in ["week", "semana"]:
            start = now
            end = now + timedelta(days=7)
            label = "this week"

        elif filter_str in ["month", "mes", "mês"]:
            start = now
            end = now + timedelta(days=30)
            label = "this month"

        elif filter_str in ["all", "todos"]:
            start = now
            end = now + timedelta(days=90)
            label = "in the next 90 days"

        else:
            # Try parsing as specific date
            parsed = dateparser.parse(
                filter_str,
                settings={
                    'TIMEZONE': 'America/Sao_Paulo',
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'PREFER_DATES_FROM': 'future'
                }
            )

            if parsed:
                start = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
                end = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
                label = f"on {parsed.strftime('%B %d, %Y')}"
            else:
                # Default to week if parsing fails
                start = now
                end = now + timedelta(days=7)
                label = "this week (default)"

        return start, end, label

    def _parse_create_input(self, input_text: str) -> Dict[str, Any]:
        """
        Parse natural language event creation input.

        Extracts:
        - title: Event title
        - start: Start datetime
        - end: End datetime (optional, calculated from duration if provided)
        - description: Event description (optional)
        - recurrence: RRULE string for recurring events (optional)
        - duration_minutes: Event duration in minutes (optional, default 60)

        Examples:
        - "Team meeting tomorrow at 3pm"
        - "Dentist appointment on Jan 15 at 2pm about cleaning"
        - "Buy groceries today at 5pm"
        - "Standup daily at 9am"
        - "Review meeting weekly at 10am 30min"
        - "Monthly sync every 1st at 2pm 1h"
        """
        result = {
            'title': None,
            'start': None,
            'end': None,
            'description': None,
            'recurrence': None,
            'duration_minutes': 60  # Default 1 hour
        }

        original_text = input_text

        # Step 1: Extract duration if present at the END of the string (e.g., "30min", "1h", "2 hours")
        # We search from the end to avoid matching duration numbers in the event title
        duration_patterns = [
            (r'(\d+)\s*min(?:ute)?s?\s*$', 1),   # "30 min", "30 minutes" at end
            (r'(\d+)\s*h(?:our)?s?\s*$', 60),     # "1h", "2 hours" at end
            (r'meia\s+hora\s*$', None),            # "meia hora" at end (Portuguese)
            (r'(\d+)\s*minutos?\s*$', 1),          # "30 minutos" at end
            (r'(\d+)\s*horas?\s*$', 60),           # "1 hora", "2 horas" at end
        ]

        for pattern, multiplier in duration_patterns:
            match = re.search(pattern, input_text, re.IGNORECASE)
            if match:
                if multiplier is None:
                    # Fixed duration (like "meia hora" = 30 minutes)
                    result['duration_minutes'] = 30
                    self.logger.info(f"Parsed fixed duration: 30 minutes")
                else:
                    # Extract number and multiply
                    duration_num = int(match.group(1))
                    result['duration_minutes'] = duration_num * multiplier
                    self.logger.info(f"Parsed duration: {duration_num} * {multiplier} = {result['duration_minutes']} minutes")
                # Remove duration from input
                input_text = input_text[:match.start()].strip()
                break

        # Step 2: Extract recurrence pattern
        recurrence_match = None
        days_of_week_map = {
            'monday': 1, 'mon': 1, 'segunda': 1, 'seg': 1,
            'tuesday': 2, 'tue': 2, 'terca': 2, 'ter': 2,
            'wednesday': 3, 'wed': 3, 'quarta': 3, 'qua': 3,
            'thursday': 4, 'thu': 4, 'quinta': 4, 'qui': 4,
            'friday': 5, 'fri': 5, 'sexta': 5, 'sex': 5,
            'saturday': 6, 'sat': 6, 'sabado': 6, 'sab': 6,
            'sunday': 7, 'sun': 7, 'domingo': 7, 'dom': 7,
        }

        # Check for "every [day/week/month]" or "daily/weekly/monthly"
        # CRITICAL: Only match the recurrence keyword, NOT "at" or time portions
        # Use lookahead to ensure we don't remove the "at" that's needed for time parsing
        recurrence_patterns = [
            # Match recurrence word just before "at" without consuming "at"
            (r'\bevery\s+day\s+(?=at\b)', 'RRULE:FREQ=DAILY;INTERVAL=1'),
            (r'\bdaily\s+(?=at\b)', 'RRULE:FREQ=DAILY;INTERVAL=1'),
            (r'\btodo\s+dia\s+(?=at\b)', 'RRULE:FREQ=DAILY;INTERVAL=1'),
            (r'\bdiariamente\s+(?=at\b)', 'RRULE:FREQ=DAILY;INTERVAL=1'),
            (r'\bevery\s+week\s+(?=at\b)', 'RRULE:FREQ=WEEKLY;INTERVAL=1'),
            (r'\bweekly\s+(?=at\b)', 'RRULE:FREQ=WEEKLY;INTERVAL=1'),
            (r'\btoda\s+semana\s+(?=at\b)', 'RRULE:FREQ=WEEKLY;INTERVAL=1'),
            (r'\bsemanalmente\s+(?=at\b)', 'RRULE:FREQ=WEEKLY;INTERVAL=1'),
            (r'\bevery\s+month\s+(?=at\b)', 'RRULE:FREQ=MONTHLY;INTERVAL=1'),
            (r'\bmonthly\s+(?=at\b)', 'RRULE:FREQ=MONTHLY;INTERVAL=1'),
            # Fallback to standalone (but search from end to avoid title matches)
            (r'\bevery\s+day\b', 'RRULE:FREQ=DAILY;INTERVAL=1'),
            (r'\bdaily\b', 'RRULE:FREQ=DAILY;INTERVAL=1'),
            (r'\btodo\s+dia\b', 'RRULE:FREQ=DAILY;INTERVAL=1'),
            (r'\bdiariamente\b', 'RRULE:FREQ=DAILY;INTERVAL=1'),
            (r'\bevery\s+week\b', 'RRULE:FREQ=WEEKLY;INTERVAL=1'),
            (r'\bweekly\b', 'RRULE:FREQ=WEEKLY;INTERVAL=1'),
            (r'\btoda\s+semana\b', 'RRULE:FREQ=WEEKLY;INTERVAL=1'),
            (r'\bsemanalmente\b', 'RRULE:FREQ=WEEKLY;INTERVAL=1'),
            (r'\bevery\s+month\b', 'RRULE:FREQ=MONTHLY;INTERVAL=1'),
            (r'\bmonthly\b', 'RRULE:FREQ=MONTHLY;INTERVAL=1'),
            (r'\btodo\s+m[eê]s\b', 'RRULE:FREQ=MONTHLY;INTERVAL=1'),
            (r'\bmensalmente\b', 'RRULE:FREQ=MONTHLY;INTERVAL=1'),
        ]

        for pattern, rrule in recurrence_patterns:
            # Find all matches and take the LAST one (more likely to be the recurrence keyword, not title)
            matches = list(re.finditer(pattern, input_text, re.IGNORECASE))
            if matches:
                match = matches[-1]  # Use last match
                result['recurrence'] = rrule
                recurrence_match = match
                self.logger.info(f"Detected recurrence: {rrule} at position {match.start()}-{match.end()}, matched: '{match.group(0)}'")
                # Remove recurrence from input (match only contains the recurrence word, not "at")
                input_text = input_text[:match.start()] + input_text[match.end():]
                input_text = input_text.strip()
                self.logger.info(f"After removing recurrence: '{input_text}'")
                break

        # Check for "every [day of week]" pattern (e.g., "every Monday")
        if not recurrence_match:
            for day_name, day_num in days_of_week_map.items():
                pattern = rf'\bevery\s+{day_name}\b'
                match = re.search(pattern, input_text, re.IGNORECASE)
                if match:
                    result['recurrence'] = f'RRULE:FREQ=WEEKLY;BYDAY={["MO","TU","WE","TH","FR","SA","SU"][day_num-1]}'
                    # Remove from input
                    input_text = input_text[:match.start()] + input_text[match.end():]
                    input_text = input_text.strip()
                    break

        # Step 3: Look for description markers and extract
        desc_markers = ['about', 'regarding', 'for', 're:']
        desc_pattern = r'\b(' + '|'.join(desc_markers) + r')\s+(.+)$'
        desc_match = re.search(desc_pattern, input_text, re.IGNORECASE)

        if desc_match:
            result['description'] = desc_match.group(2).strip()
            # Remove description from input for better title/time parsing
            input_text = input_text[:desc_match.start()].strip()

        self.logger.info(f"After recurrence/duration extraction: '{input_text}'")

        # Identify and extract time/date expressions
        # These patterns help us locate where the title ends and time begins
        time_indicators = [
            r'\b(at)\s+\d{1,2}(:\d{2})?(am|pm)\b',  # "at 9am", "at 2pm", "at 14:00" - am/pm attached
            r'\b(at)\s+\d{1,2}(:\d{2})?\s+(am|pm)\b',  # "at 9 am", "at 2 pm" - am/pm with space
            r'\b(tomorrow|today|tonight)\b',
            r'\b(on)\s+\w+\s+\d{1,2}\b',  # "on Jan 15"
            r'\b(next)\s+\w+\b',  # "next monday"
            r'\b(this)\s+(morning|afternoon|evening|night)\b',
        ]

        # Find where the time expression starts
        time_start_pos = None
        time_indicator_pattern = None
        for pattern in time_indicators:
            match = re.search(pattern, input_text, re.IGNORECASE)
            if match:
                if time_start_pos is None or match.start() < time_start_pos:
                    time_start_pos = match.start()
                    time_indicator_pattern = pattern

        self.logger.info(f"Time indicator found at position {time_start_pos}, pattern: {time_indicator_pattern}")

        # Split into title and time portions
        if time_start_pos is not None:
            # Title is everything before the time indicator
            potential_title = input_text[:time_start_pos].strip()
            time_portion = input_text[time_start_pos:].strip()
            self.logger.info(f"Split -> Title: '{potential_title}', Time portion: '{time_portion}'")
        else:
            # No clear time indicator, assume first 2-3 words are title
            words = input_text.split()
            if len(words) <= 3:
                potential_title = input_text
                time_portion = input_text  # Use whole string for time parsing
            else:
                potential_title = ' '.join(words[:3])
                time_portion = ' '.join(words[3:])
            self.logger.info(f"No time indicator -> Title: '{potential_title}', Time portion: '{time_portion}'")

        # Parse the time portion to get datetime
        self.logger.info(f"Parsing time from: '{time_portion}'")

        # CRITICAL FIX: Preprocess AM/PM format before dateparser
        # Convert "9am" → "09:00", "2pm" → "14:00", etc.
        # This ensures recurring events like "daily at 9am" parse correctly
        def convert_ampm_to_24h(match):
            hour = int(match.group(1))
            ampm = match.group(2).lower()
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            return f"{hour:02d}:00"

        # Apply AM/PM conversion to time portion
        processed_time_portion = re.sub(r'\b(\d{1,2})(am|pm)\b', convert_ampm_to_24h, time_portion, flags=re.IGNORECASE)
        if processed_time_portion != time_portion:
            self.logger.info(f"Converted AM/PM in time portion: '{time_portion}' → '{processed_time_portion}'")

        # CRITICAL FIX: For recurring events without explicit date, add "tomorrow" context
        # This helps dateparser understand "at 09:00" format (recurring events need a reference date)
        parse_text = processed_time_portion
        if result.get('recurrence') and not re.search(r'\b(tomorrow|today|next|on|this)\b', processed_time_portion, re.IGNORECASE):
            # Recurring event without date context - add "tomorrow" to help dateparser
            parse_text = f"tomorrow {processed_time_portion}"
            self.logger.info(f"Added date context for recurring event: '{processed_time_portion}' → '{parse_text}'")

        parsed_datetime = dateparser.parse(
            parse_text,
            settings={
                'TIMEZONE': 'America/Sao_Paulo',
                'RETURN_AS_TIMEZONE_AWARE': True,
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': datetime.now(BRAZIL_TZ)
            }
        )
        self.logger.info(f"Dateparser result for '{parse_text}': {parsed_datetime}")

        # If time parsing failed, try parsing the whole string
        if not parsed_datetime:
            self.logger.info(f"Time parsing failed, trying whole string: '{input_text}'")

            # Apply AM/PM conversion to whole input text as well
            processed_input_text = re.sub(r'\b(\d{1,2})(am|pm)\b', convert_ampm_to_24h, input_text, flags=re.IGNORECASE)
            if processed_input_text != input_text:
                self.logger.info(f"Converted AM/PM in full text: '{input_text}' → '{processed_input_text}'")

            # For recurring events without date context, add "tomorrow"
            parse_full_text = processed_input_text
            if result.get('recurrence') and not re.search(r'\b(tomorrow|today|next|on|this)\b', processed_input_text, re.IGNORECASE):
                parse_full_text = f"tomorrow {processed_input_text}"
                self.logger.info(f"Added date context for recurring event (full): '{processed_input_text}' → '{parse_full_text}'")

            parsed_datetime = dateparser.parse(
                parse_full_text,
                settings={
                    'TIMEZONE': 'America/Sao_Paulo',
                    'RETURN_AS_TIMEZONE_AWARE': True,
                    'PREFER_DATES_FROM': 'future',
                    'RELATIVE_BASE': datetime.now(BRAZIL_TZ)
                }
            )
            self.logger.info(f"Whole string parse result: {parsed_datetime}")

        if parsed_datetime:
            result['start'] = parsed_datetime
            # Calculate end time based on duration
            result['end'] = parsed_datetime + timedelta(minutes=result['duration_minutes'])
            # Use the extracted title
            if potential_title and len(potential_title.strip()) > 0:
                result['title'] = potential_title.strip()
            else:
                # Fallback: use first few words
                result['title'] = ' '.join(original_text.split()[:3])
        else:
            # No datetime could be parsed - use current time and whole text as title
            result['title'] = input_text
            result['start'] = datetime.now(BRAZIL_TZ)
            result['end'] = result['start'] + timedelta(minutes=result['duration_minutes'])

        return result

    async def _find_event(
        self,
        provider,
        identifier: str
    ) -> Any:
        """
        Find event by ID or title.

        Returns:
        - Single SchedulerEvent if found uniquely
        - List of SchedulerEvent if multiple matches (disambiguation needed)
        - None if not found
        """
        # Try as integer ID first
        if identifier.isdigit():
            try:
                event = await provider.get_event(identifier)
                return event
            except:
                pass

        # Search by title (get recent events)
        now = datetime.now(BRAZIL_TZ)
        future = now + timedelta(days=90)

        all_events = await provider.list_events(
            start=now - timedelta(days=30),  # Include past events
            end=future,
            max_results=100
        )

        # Case-insensitive search
        identifier_lower = identifier.lower().strip().strip('"\'')
        matches = []

        for event in all_events:
            if event.id == identifier or str(event.id) == identifier:
                # Exact ID match
                return event

            event_title_lower = event.title.lower()
            if identifier_lower in event_title_lower or event_title_lower in identifier_lower:
                matches.append(event)

        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            return matches  # Return list for disambiguation

        return None
