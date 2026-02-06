"""
Contact Resolver Service

Resolves message senders to contact IDs for contact-based memory isolation.
Enables consistent memory across channels (DM, groups, other platforms).

Phase: Item 10 - Contact-Based Memory
Phase 10.2: Updated to use ContactChannelMappingService for scalable channel support.
"""

import logging
from typing import Optional
from sqlalchemy.orm import Session

from services.contact_channel_mapping_service import ContactChannelMappingService


class ContactResolver:
    """
    Resolves sender identifiers (phone, WhatsApp ID) to contact IDs.
    Supports multi-channel identity mapping for unified memory.
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def resolve_contact_id(
        self,
        sender: str,
        whatsapp_id: Optional[str] = None,
        telegram_id: Optional[str] = None,  # Phase 10.1.1: Telegram support
        telegram_username: Optional[str] = None,  # Phase 10.1.1: Username fallback
        tenant_id: str = "default"  # Phase 10.2: Tenant-aware resolution
    ) -> Optional[int]:
        """
        Resolve sender to contact ID.

        Phase 10.2: Uses ContactChannelMappingService for resolution.
        Falls back to legacy columns if mapping not found.

        Args:
            sender: Phone number or WhatsApp ID from message
            whatsapp_id: Explicit WhatsApp ID if available
            telegram_id: Telegram user ID if available (Phase 10.1.1)
            telegram_username: Telegram @username if available (Phase 10.1.1)
            tenant_id: Tenant ID for multi-tenant resolution

        Returns:
            Contact ID if found, None otherwise
        """
        try:
            from models import Contact

            mapping_service = ContactChannelMappingService(self.db)

            self.logger.info(f"[RESOLVER] resolve_contact_id called: sender={sender}, whatsapp={whatsapp_id}, telegram={telegram_id}, tenant={tenant_id}")

            # Phase 10.2: Try channel mappings first (NEW)

            # Try Telegram ID (most reliable for Telegram)
            if telegram_id:
                self.logger.info(f"[RESOLVER] Trying telegram channel mapping for {telegram_id}")
                contact = mapping_service.get_contact_by_channel('telegram', telegram_id, tenant_id)
                if contact and contact.is_active:
                    self.logger.info(f"[RESOLVER] ✅ Resolved contact ID {contact.id} ({contact.friendly_name}) via Telegram ID {telegram_id}")
                    return contact.id
                else:
                    self.logger.warning(f"[RESOLVER] Telegram mapping lookup returned: {contact}")

            # Try WhatsApp ID
            if whatsapp_id:
                normalized_whatsapp_id = whatsapp_id.lstrip("+")
                contact = mapping_service.get_contact_by_channel('whatsapp', normalized_whatsapp_id, tenant_id)
                if contact and contact.is_active:
                    self.logger.debug(f"Resolved contact ID {contact.id} via WhatsApp ID {whatsapp_id}")
                    return contact.id

            # Try phone number
            normalized_sender = sender.lstrip("+")
            contact = mapping_service.get_contact_by_channel('phone', normalized_sender, tenant_id)
            if contact and contact.is_active:
                self.logger.debug(f"Resolved contact ID {contact.id} via phone {sender}")
                return contact.id

            # Phase 10.2: Fallback to legacy columns for backward compatibility

            # Try Telegram ID (legacy)
            if telegram_id:
                contact = self.db.query(Contact).filter(
                    Contact.telegram_id == telegram_id,
                    Contact.is_active == True
                ).first()
                if contact:
                    self.logger.debug(f"Resolved contact ID {contact.id} via legacy Telegram ID {telegram_id}")
                    return contact.id

            # Try Telegram username (legacy)
            if telegram_username:
                username = telegram_username.lstrip('@')
                contact = self.db.query(Contact).filter(
                    Contact.telegram_username == username,
                    Contact.is_active == True
                ).first()
                if contact:
                    self.logger.debug(f"Resolved contact ID {contact.id} via legacy Telegram username @{username}")
                    return contact.id

            # Try WhatsApp ID (legacy)
            if whatsapp_id:
                normalized_whatsapp_id = whatsapp_id.lstrip("+")
                contact = self.db.query(Contact).filter(
                    Contact.whatsapp_id == normalized_whatsapp_id,
                    Contact.is_active == True
                ).first()
                if contact:
                    self.logger.debug(f"Resolved contact ID {contact.id} via legacy WhatsApp ID {whatsapp_id}")
                    return contact.id

            # Try phone number (legacy)
            contact = self.db.query(Contact).filter(
                Contact.phone_number == normalized_sender,
                Contact.is_active == True
            ).first()
            if contact:
                self.logger.debug(f"Resolved contact ID {contact.id} via legacy phone {sender}")
                return contact.id

            # Try whatsapp_id field with sender value (legacy)
            contact = self.db.query(Contact).filter(
                Contact.whatsapp_id == normalized_sender,
                Contact.is_active == True
            ).first()
            if contact:
                self.logger.debug(f"Resolved contact ID {contact.id} via legacy WhatsApp ID field {sender}")
                return contact.id

            self.logger.debug(f"No contact found for sender {sender}")
            return None

        except Exception as e:
            self.logger.error(f"Error resolving contact ID for sender {sender}: {e}")
            return None

    def get_or_create_anonymous_contact(
        self,
        sender: str,
        whatsapp_id: Optional[str] = None,
        telegram_id: Optional[str] = None,  # Phase 10.1.1: Telegram support
        telegram_username: Optional[str] = None  # Phase 10.1.1: Username fallback
    ) -> int:
        """
        Get existing contact or create anonymous contact for unknown senders.

        Args:
            sender: Phone number or WhatsApp ID
            whatsapp_id: Explicit WhatsApp ID if available
            telegram_id: Telegram user ID if available (Phase 10.1.1)
            telegram_username: Telegram @username if available (Phase 10.1.1)

        Returns:
            Contact ID (existing or newly created)
        """
        try:
            from models import Contact

            # Try to resolve existing contact
            contact_id = self.resolve_contact_id(sender, whatsapp_id, telegram_id, telegram_username)
            if contact_id:
                return contact_id

            # Create anonymous contact
            normalized_sender = sender.lstrip("+")
            friendly_name = f"Unknown_{normalized_sender[:8]}"

            # Check if anonymous contact already exists
            contact = self.db.query(Contact).filter(
                Contact.friendly_name == friendly_name
            ).first()

            if contact:
                return contact.id

            # Create new anonymous contact
            contact = Contact(
                friendly_name=friendly_name,
                phone_number=normalized_sender if sender.isdigit() else None,
                whatsapp_id=whatsapp_id or (normalized_sender if not sender.isdigit() else None),
                telegram_id=telegram_id,  # Phase 10.1.1
                role="user",
                is_active=True,
                is_dm_trigger=True,
                notes="Auto-created anonymous contact"
            )
            self.db.add(contact)
            self.db.commit()
            self.db.refresh(contact)

            self.logger.info(f"Created anonymous contact ID {contact.id} for sender {sender}")
            return contact.id

        except Exception as e:
            self.logger.error(f"Error creating anonymous contact for sender {sender}: {e}")
            # Fallback: return a hash-based ID
            return hash(sender) % 1000000

    def get_memory_key(
        self,
        agent_id: int,
        sender: str,
        whatsapp_id: Optional[str] = None,
        telegram_id: Optional[str] = None,  # Phase 10.1.1: Telegram support
        telegram_username: Optional[str] = None,  # Phase 10.1.1: Username fallback
        use_contact_mapping: bool = True,
        tenant_id: str = "default"  # Phase 10.2: Tenant-aware resolution
    ) -> str:
        """
        Generate memory key for agent-sender pair.

        Args:
            agent_id: Agent ID
            sender: Sender identifier (phone/WhatsApp ID)
            whatsapp_id: Explicit WhatsApp ID if available
            telegram_id: Telegram user ID if available (Phase 10.1.1)
            telegram_username: Telegram @username if available (Phase 10.1.1)
            use_contact_mapping: If True, use contact-based keys; if False, use sender-based keys
            tenant_id: Tenant ID for multi-tenant resolution

        Returns:
            Memory key in format "agent_{id}:contact_{contact_id}" or "agent_{id}:sender_{sender}"
        """
        if use_contact_mapping:
            contact_id = self.resolve_contact_id(sender, whatsapp_id, telegram_id, telegram_username, tenant_id)
            if contact_id:
                return f"agent_{agent_id}:contact_{contact_id}"

        # Fallback to sender-based key (backward compatibility)
        normalized_sender = sender.lstrip("+")
        return f"agent_{agent_id}:sender_{normalized_sender}"
