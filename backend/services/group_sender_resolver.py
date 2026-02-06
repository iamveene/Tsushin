"""
Group Sender Auto-Resolution Service
Phase 10.2 - Option B Implementation

Automatically resolves WhatsApp group message senders to existing contacts.
When a group message arrives, if the sender's phone number matches an existing
contact, we add a WhatsApp channel mapping for that contact.

This is the CONSERVATIVE approach (Option B):
- Only adds mappings to EXISTING contacts
- Never creates new contacts automatically
- Matches by phone number (Contact.phone_number field)

Author: Tsushin AI
Date: 2026-01-29
"""

import logging
import re
from typing import Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_

from models import Contact, ContactChannelMapping

logger = logging.getLogger(__name__)


class GroupSenderResolver:
    """
    Auto-resolve group message senders to existing contacts.

    When a WhatsApp group message arrives:
    1. Extract sender's phone number from the message
    2. Look for existing Contact with matching phone_number
    3. If found, add a 'whatsapp' channel mapping for the sender's JID

    This allows the system to recognize users across both DM and group contexts.
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def auto_resolve_group_sender(
        self,
        sender: str,
        sender_name: Optional[str] = None,
        tenant_id: str = "default",
        chat_id: Optional[str] = None
    ) -> Optional[Contact]:
        """
        Attempt to resolve a group message sender to an existing contact.

        Strategy (Option B - Conservative):
        1. Extract phone number from sender (e.g., "5500000000001@s.whatsapp.net" -> "5500000000001")
        2. Search for existing Contact with this phone_number
        3. If found, add WhatsApp channel mapping with the sender's JID
        4. Return the matched contact

        Args:
            sender: Sender identifier from WhatsApp (JID format)
            sender_name: Optional sender display name for logging
            tenant_id: Tenant ID for multi-tenant support
            chat_id: Optional group chat ID (for metadata)

        Returns:
            Contact if successfully resolved, None otherwise
        """
        try:
            # Step 1: Extract phone number from sender JID
            phone_number = self._extract_phone_from_jid(sender)

            if not phone_number:
                self.logger.debug(
                    f"[GROUP_RESOLVER] Could not extract phone from sender: {sender}"
                )
                return None

            self.logger.debug(
                f"[GROUP_RESOLVER] Extracted phone number: {phone_number} from {sender}"
            )

            # Step 2: Search for existing contact by phone number
            contact = self._find_contact_by_phone(phone_number, tenant_id)

            if not contact:
                self.logger.debug(
                    f"[GROUP_RESOLVER] No existing contact found for phone: {phone_number}"
                )
                return None

            # Step 3: Check if this WhatsApp mapping already exists
            sender_normalized = sender.split('@')[0]  # Remove @s.whatsapp.net suffix

            existing_mapping = self.db.query(ContactChannelMapping).filter(
                ContactChannelMapping.contact_id == contact.id,
                ContactChannelMapping.channel_type == "whatsapp",
                ContactChannelMapping.channel_identifier == sender_normalized,
                ContactChannelMapping.tenant_id == tenant_id
            ).first()

            if existing_mapping:
                self.logger.debug(
                    f"[GROUP_RESOLVER] WhatsApp mapping already exists for contact "
                    f"'{contact.friendly_name}' (ID: {contact.id})"
                )
                return contact

            # Step 4: Add new WhatsApp channel mapping
            metadata = {
                "source": "group_auto_discovery",
                "discovered_at": datetime.utcnow().isoformat() + "Z",
                "sender_name": sender_name
            }

            if chat_id:
                metadata["discovered_in_group"] = chat_id

            mapping = ContactChannelMapping(
                contact_id=contact.id,
                channel_type="whatsapp",
                channel_identifier=sender_normalized,
                channel_metadata=metadata,
                tenant_id=tenant_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            self.db.add(mapping)
            self.db.commit()
            self.db.refresh(mapping)

            self.logger.info(
                f"🔗 [GROUP_RESOLVER] Auto-linked WhatsApp ID '{sender_normalized}' "
                f"to contact '{contact.friendly_name}' (phone: {contact.phone_number})"
            )

            # Also update Contact.whatsapp_id if not already set
            if not contact.whatsapp_id:
                contact.whatsapp_id = sender_normalized
                self.db.commit()
                self.logger.info(
                    f"✅ [GROUP_RESOLVER] Updated contact.whatsapp_id for '{contact.friendly_name}'"
                )

            return contact

        except Exception as e:
            self.logger.error(
                f"[GROUP_RESOLVER] Error auto-resolving sender {sender}: {e}",
                exc_info=True
            )
            self.db.rollback()
            return None

    def _extract_phone_from_jid(self, jid: str) -> Optional[str]:
        """
        Extract phone number from WhatsApp JID.

        Handles formats:
        - "5500000000001@s.whatsapp.net" -> "5500000000001"
        - "5500000000001@lid" -> "5500000000001"
        - "+5500000000001" -> "5500000000001"
        - "5500000000001" -> "5500000000001"

        Args:
            jid: WhatsApp JID or phone number

        Returns:
            Normalized phone number (digits only) or None if invalid
        """
        if not jid:
            return None

        # Remove @ suffix (e.g., @s.whatsapp.net, @lid)
        clean = jid.split('@')[0]

        # Remove + prefix
        clean = clean.lstrip('+')

        # Validate: should be all digits and reasonable length (10-15 digits)
        if not clean.isdigit():
            return None

        if len(clean) < 10 or len(clean) > 15:
            return None

        return clean

    def _find_contact_by_phone(
        self,
        phone_number: str,
        tenant_id: str
    ) -> Optional[Contact]:
        """
        Find contact by phone number with flexible matching.

        Matches against:
        - Exact phone number
        - Phone number with + prefix
        - Phone number without + prefix

        Args:
            phone_number: Normalized phone number (digits only)
            tenant_id: Tenant ID for filtering

        Returns:
            Contact if found, None otherwise
        """
        # Try multiple formats
        possible_formats = [
            phone_number,
            f"+{phone_number}",
        ]

        # Also handle partial matches for country codes
        # e.g., phone_number might be missing country code prefix

        contact = self.db.query(Contact).filter(
            Contact.is_active == True,
            or_(
                Contact.phone_number.in_(possible_formats),
                # Also check if stored phone ends with the number
                Contact.phone_number.endswith(phone_number)
            )
        ).first()

        if contact:
            self.logger.debug(
                f"[GROUP_RESOLVER] Found contact '{contact.friendly_name}' "
                f"(ID: {contact.id}) for phone {phone_number}"
            )

        return contact


def get_group_sender_resolver(db: Session) -> GroupSenderResolver:
    """
    Factory function to get a GroupSenderResolver instance.

    Args:
        db: Database session

    Returns:
        GroupSenderResolver instance
    """
    return GroupSenderResolver(db)
