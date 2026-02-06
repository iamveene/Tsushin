from typing import Dict, Optional
import re
import json

class MessageFilter:
    def __init__(
        self,
        group_filters: list,
        number_filters: list,
        agent_number: str = None,
        dm_auto_mode: bool = False,
        agent_phone_number: str = None,
        agent_name: str = None,
        group_keywords: list = None,
        contact_service = None,  # Phase 4.2: ContactService for mention detection
        db_session = None  # Phase 6.4 Week 3: For checking active conversations
    ):
        self.group_filters = set(group_filters)
        self.number_filters = set(number_filters)
        self.agent_number = agent_number.lstrip("+") if agent_number else None
        self.dm_auto_mode = dm_auto_mode
        self.agent_phone_number = agent_phone_number.lstrip("+") if agent_phone_number else None
        self.agent_name = agent_name.lower() if agent_name else None
        self.group_keywords = [kw.lower() for kw in (group_keywords or [])]
        self.contact_service = contact_service
        self.db_session = db_session

    def should_trigger(self, message: Dict) -> Optional[str]:
        """
        Check if message matches filter criteria.
        Returns trigger type: "group", "number", "auto", "contact_trigger", or None

        Priority order:
        0. Emergency stop check (Bug Fix 2026-01-06)
        1. Group mentions/keywords
        2. DM auto-mode or contact triggers

        For groups: Trigger if:
          - Group is in group_filters AND
          - (Message contains @agent_phone_number OR @agent_name OR any keyword from group_keywords)

        For direct messages: Trigger if:
          - dm_auto_mode is True (reply to all DMs), OR
          - sender is a contact with is_dm_trigger enabled, OR
          - sender matches number_filters (legacy)
        """
        # Bug Fix 2026-01-06: Emergency Stop Check - Highest Priority
        if self.db_session:
            try:
                from models import Config
                config = self.db_session.query(Config).first()
                if config and hasattr(config, 'emergency_stop') and config.emergency_stop:
                    return None  # Emergency stop is active - block all messages
            except Exception:
                pass  # If check fails, continue normal processing

        is_group = bool(message.get("is_group", 0))

        if is_group:
            chat_name = message.get("chat_name", "")
            if chat_name in self.group_filters:
                # Multi-Agent Fix: Pass ALL messages from allowed groups to router
                # The router will determine which agent (if any) should handle the message
                # based on agent-specific keywords configured in the agent table
                return "group"
        else:
            # Direct message handling
            sender = message.get("sender", "")
            sender_normalized = sender.split("@")[0].lstrip("+")

            # Phase 6.4 Week 3: HIGHEST PRIORITY - Check for active conversations FIRST
            # Conversation replies must ALWAYS trigger, regardless of is_dm_trigger setting
            if self.db_session and self._has_active_conversation(sender_normalized):
                return "conversation"  # Active conversation found - MUST trigger

            # CRITICAL FIX 2026-01-08: Check contact's is_dm_trigger setting BEFORE dm_auto_mode
            # Contact-level settings MUST override global dm_auto_mode to prevent trigger hijacking
            if self.contact_service:
                # First, check if sender is a known contact
                contact = self.contact_service.identify_sender(sender)

                if contact:
                    # If contact exists, respect their is_dm_trigger setting
                    # This MUST be checked before dm_auto_mode to prevent bypassing contact settings
                    if contact.is_dm_trigger:
                        return "contact_trigger"
                    else:
                        # Contact exists but has is_dm_trigger=False → DO NOT TRIGGER
                        # This overrides both dm_auto_mode AND legacy number_filters
                        # ABSOLUTE: No trigger for this contact, regardless of other settings
                        # MONITORING 2026-01-08: Log blocked triggers for audit
                        try:
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.info(f"🚫 TRIGGER BLOCKED: Contact {contact.friendly_name} (is_dm_trigger=False) | Sender: {sender}")
                        except:
                            pass
                        return None

                # If not a known contact, fall through to global dm_auto_mode and number_filters

            # Global dm_auto_mode check - only applies to unknown contacts (not in database)
            if self.dm_auto_mode:
                return "auto"  # Auto-reply mode for unknown senders

            # Fallback: Check legacy number_filters for backward compatibility
            # This only applies to senders NOT in the contact database
            for filter_num in self.number_filters:
                filter_normalized = filter_num.lstrip("+")
                if sender_normalized == filter_normalized:
                    return "number"

        return None

    def _has_active_conversation(self, sender_normalized: str) -> bool:
        """
        Phase 6.4 Week 3 + Bug Fix 2026-01-07: Check if sender has an active conversation.
        This ensures conversation replies always trigger, regardless of other settings.

        CRITICAL: Checks BOTH ConversationThread (Phase 8.0) and ScheduledEvent (legacy)
        to prevent hijack by is_dm_trigger when flow conversations are active.

        Args:
            sender_normalized: Phone number without '+' prefix

        Returns:
            True if sender has an active conversation
        """
        if not self.db_session:
            return False

        try:
            from models import ScheduledEvent, ConversationThread

            # PRIORITY 1: Check ConversationThread (Phase 8.0 - modern flows)
            # Build possible recipient formats to match against
            possible_recipients = [
                sender_normalized,
                f"+{sender_normalized}",
                f"{sender_normalized}@s.whatsapp.net",
                f"{sender_normalized}@lid"  # WhatsApp Business format
            ]

            # Bug Fix 2026-01-07: Check if sender is a WhatsApp Business ID that maps to a contact's phone
            # This handles case where thread recipient is phone number but bot replies from WhatsApp ID
            try:
                from models import Contact

                # CHECK 1: If sender is WhatsApp ID → add phone number formats
                contact = self.db_session.query(Contact).filter(
                    Contact.whatsapp_id == sender_normalized
                ).first()

                if contact and contact.phone_number:
                    # Add contact's phone number to possible recipients
                    contact_phone = contact.phone_number.lstrip('+')
                    additional_formats = [
                        contact.phone_number,
                        contact_phone,
                        f"+{contact_phone}",
                        f"{contact_phone}@s.whatsapp.net",
                        f"{contact_phone}@lid"
                    ]
                    possible_recipients.extend(additional_formats)

                # CRITICAL FIX 2026-01-08: CHECK 2: If sender is phone number → add WhatsApp ID formats
                # This handles when user sends from phone but thread was created with WhatsApp ID
                contact_by_phone = self.db_session.query(Contact).filter(
                    Contact.phone_number == sender_normalized
                ).first()

                if contact_by_phone and contact_by_phone.whatsapp_id:
                    # Add contact's WhatsApp ID to possible recipients
                    whatsapp_id = contact_by_phone.whatsapp_id
                    additional_formats = [
                        whatsapp_id,
                        f"+{whatsapp_id}",
                        f"{whatsapp_id}@s.whatsapp.net",
                        f"{whatsapp_id}@lid"
                    ]
                    possible_recipients.extend(additional_formats)

            except Exception:
                pass  # Silently fail - continue with original matching

            # Check for active conversation threads
            active_thread = self.db_session.query(ConversationThread).filter(
                ConversationThread.recipient.in_(possible_recipients),
                ConversationThread.status == 'active'
            ).first()

            if active_thread:
                return True

            # PRIORITY 2: Check ScheduledEvent (legacy conversations - backward compat)
            active_conversations = self.db_session.query(ScheduledEvent).filter(
                ScheduledEvent.event_type == 'CONVERSATION',
                ScheduledEvent.status == 'ACTIVE'
            ).all()

            # Check if any conversation matches this sender
            for conversation in active_conversations:
                try:
                    payload = json.loads(conversation.payload)
                    recipient = payload.get('recipient', '')
                    recipient_normalized = recipient.lstrip('+')

                    if recipient_normalized == sender_normalized:
                        return True
                except (json.JSONDecodeError, KeyError):
                    continue

            return False

        except Exception as e:
            # If check fails, don't block the message
            return False

    def update_filters(
        self,
        group_filters: list,
        number_filters: list,
        agent_number: str = None,
        dm_auto_mode: bool = False,
        agent_phone_number: str = None,
        agent_name: str = None,
        group_keywords: list = None
    ):
        """Update filter configuration"""
        self.group_filters = set(group_filters)
        self.number_filters = set(number_filters)
        if agent_number:
            self.agent_number = agent_number.lstrip("+")
        self.dm_auto_mode = dm_auto_mode
        if agent_phone_number:
            self.agent_phone_number = agent_phone_number.lstrip("+")
        if agent_name:
            self.agent_name = agent_name.lower()
        if group_keywords is not None:
            self.group_keywords = [kw.lower() for kw in group_keywords]
