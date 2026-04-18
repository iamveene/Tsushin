"""
WhatsApp ID Auto-Discovery Service

Automatically discovers and links WhatsApp Business IDs to contacts by analyzing
conversation patterns. This allows users to create flows with contact names or
phone numbers without needing to know the WhatsApp Business ID.

Author: Tsushin AI
Date: 2026-01-07
"""

import logging
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_
import requests

from models import Contact, ConversationThread, WhatsAppMCPInstance
from services.contact_channel_mapping_service import ContactChannelMappingService
from services.mcp_auth_service import get_auth_headers

logger = logging.getLogger(__name__)


class WhatsAppIDDiscovery:
    """
    Auto-discover and link WhatsApp Business IDs to contacts.

    When a WhatsApp Business account replies, it may use a different ID than
    the phone number we sent to. This service automatically discovers and links
    these IDs to contacts based on recent conversation activity.
    """

    def __init__(self, time_window_minutes: int = 60):
        """
        Initialize discovery service.

        Args:
            time_window_minutes: Time window for finding recent threads (default: 60)
        """
        self.time_window_minutes = time_window_minutes

    def auto_link_contact(
        self,
        db: Session,
        sender_whatsapp_id: str,
        logger_instance: logging.Logger,
        tenant_id: Optional[str] = None,
        chat_name: Optional[str] = None,
    ) -> Optional[Contact]:
        """
        Auto-discover contact by analyzing recent conversation threads.

        Strategy:
        1. Find active threads from last N minutes with numeric recipients (phone numbers)
        2. For each thread, check if there's a contact with that phone number
        3. If contact found and doesn't have whatsapp_id yet, link it
        4. Return the linked contact

        Args:
            db: Database session
            sender_whatsapp_id: WhatsApp ID of the sender (e.g., "193853382488108")
            logger_instance: Logger instance for detailed logging

        Returns:
            Contact if discovered and linked, None otherwise
        """
        try:
            # Calculate time threshold
            time_threshold = datetime.utcnow() - timedelta(minutes=self.time_window_minutes)

            logger_instance.debug(
                f"[AUTO-DISCOVERY] Attempting to discover contact for WhatsApp ID: {sender_whatsapp_id}"
            )

            # Find recent active conversation threads
            recent_threads = db.query(ConversationThread).filter(
                ConversationThread.status == 'active',
                ConversationThread.last_activity_at >= time_threshold
            ).order_by(ConversationThread.last_activity_at.desc()).all()

            logger_instance.debug(
                f"[AUTO-DISCOVERY] Found {len(recent_threads)} recent active threads"
            )

            # Try to correlate sender with a contact
            for thread in recent_threads:
                contact = self._try_link_thread_contact(
                    db,
                    thread,
                    sender_whatsapp_id,
                    logger_instance
                )

                if contact:
                    return contact

            contact = self._try_link_via_mcp_contacts(
                db,
                sender_whatsapp_id,
                logger_instance,
                tenant_id=tenant_id,
                chat_name=chat_name,
            )
            if contact:
                return contact

            # No match found
            logger_instance.info(
                f"❌ DISCOVERY FAILED: No recent threads found for WhatsApp ID {sender_whatsapp_id}"
            )
            return None

        except Exception as e:
            logger_instance.error(f"Error in auto_link_contact: {e}", exc_info=True)
            return None

    def _try_link_thread_contact(
        self,
        db: Session,
        thread: ConversationThread,
        sender_whatsapp_id: str,
        logger_instance: logging.Logger
    ) -> Optional[Contact]:
        """
        Try to link a thread's recipient to the sender's WhatsApp ID.

        Args:
            db: Database session
            thread: Conversation thread to analyze
            sender_whatsapp_id: WhatsApp ID to link
            logger_instance: Logger instance

        Returns:
            Contact if successfully linked, None otherwise
        """
        try:
            # Extract clean recipient (remove @ suffixes, + prefixes)
            recipient = thread.recipient
            clean_recipient = recipient.split('@')[0].lstrip('+')

            # Check if recipient looks like a phone number (numeric)
            if not clean_recipient.isdigit():
                logger_instance.debug(
                    f"[AUTO-DISCOVERY] Thread {thread.id} recipient '{recipient}' "
                    "is not numeric (not a phone number)"
                )
                return None

            logger_instance.debug(
                f"[AUTO-DISCOVERY] Thread {thread.id} has numeric recipient: {clean_recipient}"
            )

            # Find contact with this phone number
            contact = db.query(Contact).filter(
                or_(
                    Contact.phone_number == clean_recipient,
                    Contact.phone_number == f"+{clean_recipient}",
                    Contact.phone_number == recipient
                )
            ).first()

            if not contact:
                logger_instance.debug(
                    f"[AUTO-DISCOVERY] No contact found with phone {clean_recipient}"
                )
                return None

            return self._link_contact_alias(db, contact, sender_whatsapp_id, logger_instance)

        except Exception as e:
            logger_instance.error(
                f"Error in _try_link_thread_contact for thread {thread.id}: {e}",
                exc_info=True
            )
            db.rollback()
            return None

    def _link_contact_alias(
        self,
        db: Session,
        contact: Contact,
        sender_whatsapp_id: str,
        logger_instance: logging.Logger
    ) -> Optional[Contact]:
        """Persist a newly observed WhatsApp sender alias for an existing contact."""
        if contact.whatsapp_id:
            if contact.whatsapp_id == sender_whatsapp_id:
                logger_instance.debug(
                    f"[AUTO-DISCOVERY] Contact {contact.friendly_name} already linked "
                    f"to WhatsApp ID {sender_whatsapp_id}"
                )
                return contact

            mapping_service = ContactChannelMappingService(db)
            mapping_service.add_channel_mapping(
                contact_id=contact.id,
                channel_type="whatsapp",
                channel_identifier=sender_whatsapp_id,
                channel_metadata={
                    "discovered_from": "whatsapp_id_discovery",
                    "legacy_whatsapp_id": contact.whatsapp_id,
                },
                tenant_id=contact.tenant_id or "default",
            )
            logger_instance.info(
                f"🔗 AUTO-DISCOVERY: Added WhatsApp alias {sender_whatsapp_id} "
                f"for contact '{contact.friendly_name}'"
            )
            return contact

        logger_instance.info(
            f"🔗 AUTO-DISCOVERY: Linking contact '{contact.friendly_name}' "
            f"(phone: {contact.phone_number}) → WhatsApp ID: {sender_whatsapp_id}"
        )
        contact.whatsapp_id = sender_whatsapp_id
        db.commit()

        logger_instance.info(
            f"✅ AUTO-DISCOVERY SUCCESS: Contact '{contact.friendly_name}' "
            f"linked to WhatsApp ID {sender_whatsapp_id}"
        )
        return contact

    def _try_link_via_mcp_contacts(
        self,
        db: Session,
        sender_whatsapp_id: str,
        logger_instance: logging.Logger,
        tenant_id: Optional[str] = None,
        chat_name: Optional[str] = None,
    ) -> Optional[Contact]:
        """Fallback discovery using the active MCP /contacts endpoint."""
        chat_name = (chat_name or "").strip()
        if not tenant_id or not chat_name:
            return None

        try:
            instance = db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.tenant_id == tenant_id,
                WhatsAppMCPInstance.status.in_(["running", "starting"]),
            ).order_by(WhatsAppMCPInstance.id.asc()).first()
            if not instance:
                return None

            response = requests.get(
                f"{instance.mcp_api_url.rstrip('/')}/contacts",
                params={"q": chat_name, "limit": 10},
                headers=get_auth_headers(instance.api_secret),
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            if not payload.get("success"):
                return None

            for result in payload.get("contacts") or []:
                jid = str(result.get("jid") or "")
                phone = str(result.get("phone") or "")
                name = str(result.get("name") or "")

                if not jid and not phone:
                    continue
                if chat_name.lower() not in name.lower():
                    continue

                identifiers = []
                for candidate in [phone, jid.split("@")[0] if "@" in jid else jid]:
                    candidate = (candidate or "").strip().lstrip("+")
                    if candidate and candidate not in identifiers:
                        identifiers.append(candidate)

                if not identifiers:
                    continue

                contact = db.query(Contact).filter(
                    Contact.tenant_id == tenant_id,
                    Contact.is_active == True,
                    or_(
                        Contact.phone_number.in_(identifiers + [f"+{value}" for value in identifiers]),
                        Contact.whatsapp_id.in_(identifiers),
                    ),
                ).first()
                if contact:
                    logger_instance.info(
                        f"[AUTO-DISCOVERY] MCP contacts resolved '{chat_name}' "
                        f"to contact '{contact.friendly_name}'"
                    )
                    return self._link_contact_alias(db, contact, sender_whatsapp_id, logger_instance)

        except Exception as e:
            logger_instance.debug(f"[AUTO-DISCOVERY] MCP contact lookup skipped: {e}")

        return None

    def find_contact_by_correlation(
        self,
        db: Session,
        sender_id: str,
        logger_instance: logging.Logger
    ) -> Optional[Contact]:
        """
        Find contact by correlating sender ID with recent activity.

        This is a more sophisticated version that looks at patterns beyond
        just recent threads. Can be extended for future use cases.

        Args:
            db: Database session
            sender_id: Sender identifier to correlate
            logger_instance: Logger instance

        Returns:
            Contact if found, None otherwise
        """
        # For now, this delegates to auto_link_contact
        # Can be extended with more sophisticated correlation logic
        return self.auto_link_contact(db, sender_id, logger_instance)
