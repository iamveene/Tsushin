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

from models import Contact, ConversationThread

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
        logger_instance: logging.Logger
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

            # Check if contact already has a WhatsApp ID
            if contact.whatsapp_id:
                logger_instance.debug(
                    f"[AUTO-DISCOVERY] Contact {contact.friendly_name} already has "
                    f"WhatsApp ID: {contact.whatsapp_id}"
                )
                return None

            # SUCCESS! Link the WhatsApp ID to this contact
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

        except Exception as e:
            logger_instance.error(
                f"Error in _try_link_thread_contact for thread {thread.id}: {e}",
                exc_info=True
            )
            db.rollback()
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
