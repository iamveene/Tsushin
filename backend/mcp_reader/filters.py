from typing import Dict, Optional
import re
import json
import logging

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
        db_session = None,  # Phase 6.4 Week 3: For checking active conversations
        tenant_id: str = None,  # v0.7.3: Per-tenant emergency stop check
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
        self.tenant_id = tenant_id
        self.logger = logging.getLogger(__name__)

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
        # Emergency Stop Check (highest priority).
        # v0.7.3: Check BOTH the global kill switch (Config.emergency_stop) and
        # the per-tenant flag (Tenant.emergency_stop) for this watcher's tenant.
        # Either flag true → block. DB errors fail-open so a transient outage
        # does not silently halt the bot.
        if self.db_session:
            try:
                from models import Config
                config = self.db_session.query(Config).first()
                if config and getattr(config, 'emergency_stop', False):
                    return None  # Global emergency stop — block every channel
                if self.tenant_id:
                    from models_rbac import Tenant
                    tenant = self.db_session.query(Tenant).filter(Tenant.id == self.tenant_id).first()
                    if tenant and getattr(tenant, 'emergency_stop', False):
                        return None  # Tenant-scoped emergency stop
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
            contact = self._resolve_direct_message_contact(message)
            if contact:
                # If contact exists, respect their is_dm_trigger setting
                # This MUST be checked before dm_auto_mode to prevent bypassing contact settings
                if contact.is_dm_trigger:
                    return "contact_trigger"
                else:
                    # Contact exists but has is_dm_trigger=False → DO NOT TRIGGER
                    # This overrides both dm_auto_mode AND legacy number_filters
                    self.logger.info(
                        f"🚫 TRIGGER BLOCKED: Contact {contact.friendly_name} "
                        f"(is_dm_trigger=False) | Sender: {sender}"
                    )
                    return None

                # If not a known contact, fall through to global dm_auto_mode and number_filters

            # Global dm_auto_mode check - only applies to unknown contacts (not in database)
            if self.dm_auto_mode:
                return "auto"  # Auto-reply mode for unknown senders

            # Fallback: Check legacy number_filters for backward compatibility
            # This only applies to senders NOT in the contact database
            for filter_num in self.number_filters:
                filter_normalized = filter_num.lstrip("+")
                if (
                    sender_normalized == filter_normalized or
                    sender_normalized.endswith(filter_normalized) or
                    filter_normalized.endswith(sender_normalized)
                ):
                    return "number"

        return None

    def _resolve_direct_message_contact(self, message: Dict):
        """Resolve DM senders using WhatsApp metadata fallbacks in addition to raw sender IDs."""
        sender = message.get("sender", "")
        sender_normalized = sender.split("@")[0].lstrip("+")

        if self.contact_service:
            contact = self.contact_service.identify_sender(sender)
            if contact:
                return contact

            chat_id = message.get("chat_id", "")
            if chat_id and chat_id != sender:
                contact = self.contact_service.identify_sender(chat_id)
                if contact:
                    return contact

        if not self.db_session:
            return None

        from models import Contact

        tenant_id = getattr(self.contact_service, "tenant_id", None)
        names_to_try = []
        for candidate in [message.get("chat_name"), message.get("sender_name")]:
            candidate = (candidate or "").strip()
            if candidate and candidate not in names_to_try and not candidate.isdigit():
                names_to_try.append(candidate)

        for candidate in names_to_try:
            base_query = self.db_session.query(Contact).filter(Contact.is_active == True)
            if tenant_id:
                base_query = base_query.filter(Contact.tenant_id == tenant_id)

            exact_matches = base_query.filter(Contact.friendly_name.ilike(candidate)).all()
            if len(exact_matches) == 1:
                self.logger.info(
                    f"[DM RESOLUTION] Resolved sender {sender or message.get('chat_id')} "
                    f"to contact '{exact_matches[0].friendly_name}' via exact chat metadata '{candidate}'"
                )
                return exact_matches[0]

            candidate_lower = candidate.lower()
            partial_matches = [
                contact for contact in base_query.all()
                if contact.friendly_name and contact.friendly_name.lower() in candidate_lower
            ]
            if len(partial_matches) == 1:
                self.logger.info(
                    f"[DM RESOLUTION] Resolved sender {sender or message.get('chat_id')} "
                    f"to contact '{partial_matches[0].friendly_name}' via partial chat metadata '{candidate}'"
                )
                return partial_matches[0]

        try:
            from services.whatsapp_id_discovery import WhatsAppIDDiscovery
            discovery = WhatsAppIDDiscovery(time_window_minutes=60)
            return discovery.auto_link_contact(
                self.db_session,
                sender_normalized,
                self.logger,
                tenant_id=tenant_id,
                chat_name=message.get("chat_name") or message.get("sender_name"),
            )
        except Exception:
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
