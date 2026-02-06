"""
Contact Auto-Population Service
Phase 10.1.1 / Phase 10.2

Automatically creates/updates contacts from incoming messages.
Enables seamless cross-channel memory without manual contact creation.

Phase 10.2: Updated to use ContactChannelMappingService for scalable channel support.
Implements dual-write strategy for backward compatibility during migration.
"""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session

from models import Contact
from services.contact_channel_mapping_service import ContactChannelMappingService

logger = logging.getLogger(__name__)


class ContactAutoPopulateService:
    """Automatically populate contact information from incoming messages."""

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    async def ensure_contact_from_telegram(
        self,
        telegram_id: str,
        sender_name: str,
        telegram_username: Optional[str],
        tenant_id: str,
        user_id: int = 1
    ) -> Contact:
        """
        Create or update contact from Telegram message metadata.

        Phase 10.2: Uses ContactChannelMappingService for resolution.
        Maintains dual-write to legacy columns for backward compatibility.

        Args:
            telegram_id: Telegram user ID (numeric)
            sender_name: Display name from Telegram
            telegram_username: @username (without @)
            tenant_id: Tenant ID
            user_id: System user ID for auto-created contacts

        Returns:
            Contact instance (existing or newly created)
        """
        mapping_service = ContactChannelMappingService(self.db)

        # Phase 10.2: Check for contact via channel mapping (NEW)
        contact = mapping_service.get_contact_by_channel(
            channel_type='telegram',
            channel_identifier=telegram_id,
            tenant_id=tenant_id
        )

        if contact:
            # Update username metadata if changed
            mappings = mapping_service.get_channel_mappings(contact.id, 'telegram')
            if mappings:
                telegram_mapping = mappings[0]
                current_username = (telegram_mapping.channel_metadata or {}).get('username') if telegram_mapping.channel_metadata else None
                if telegram_username and current_username != telegram_username:
                    self.logger.info(
                        f"Updating Telegram username for {contact.friendly_name}: "
                        f"{current_username} → @{telegram_username}"
                    )
                    telegram_mapping.channel_metadata = {'username': telegram_username}
                    telegram_mapping.updated_at = datetime.utcnow()

                    # Dual-write: Also update legacy column
                    contact.telegram_username = telegram_username
                    contact.updated_at = datetime.utcnow()

                    self.db.commit()
                    self.db.refresh(contact)

            return contact

        # Create new contact
        friendly_name = sender_name or f"Telegram User {telegram_id}"
        if telegram_username:
            friendly_name = f"@{telegram_username}"

        self.logger.info(
            f"Auto-creating contact: {friendly_name} "
            f"(telegram_id={telegram_id}, username=@{telegram_username})"
        )

        # Dual-write: Create contact with legacy columns
        contact = Contact(
            friendly_name=friendly_name,
            telegram_id=telegram_id,  # LEGACY: Keep for backward compatibility
            telegram_username=telegram_username,  # LEGACY: Keep for backward compatibility
            role="user",
            is_active=True,
            is_dm_trigger=True,
            tenant_id=tenant_id,
            user_id=user_id
        )

        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)

        # Phase 10.2: Add channel mapping (NEW)
        metadata = {}
        if telegram_username:
            metadata['username'] = telegram_username

        mapping_service.add_channel_mapping(
            contact_id=contact.id,
            channel_type='telegram',
            channel_identifier=telegram_id,
            channel_metadata=metadata if metadata else None,
            tenant_id=tenant_id
        )

        self.logger.info(f"Created Telegram channel mapping for contact {contact.id}")

        return contact

    async def ensure_contact_from_whatsapp(
        self,
        whatsapp_id: str,
        phone_number: Optional[str],
        sender_name: str,
        tenant_id: str,
        user_id: int = 1
    ) -> Contact:
        """
        Create or update contact from WhatsApp message metadata.

        Phase 10.2: Uses ContactChannelMappingService for resolution.
        Maintains dual-write to legacy columns for backward compatibility.

        Args:
            whatsapp_id: WhatsApp ID
            phone_number: Phone number if available
            sender_name: Display name from WhatsApp
            tenant_id: Tenant ID
            user_id: System user ID for auto-created contacts

        Returns:
            Contact instance (existing or newly created)
        """
        mapping_service = ContactChannelMappingService(self.db)

        # Phase 10.2: Check for contact via channel mapping (NEW)
        contact = mapping_service.get_contact_by_channel(
            channel_type='whatsapp',
            channel_identifier=whatsapp_id,
            tenant_id=tenant_id
        )

        if contact:
            # Update phone number if changed and provided
            updated = False
            if phone_number:
                # Check if phone mapping exists
                phone_mappings = [m for m in mapping_service.get_channel_mappings(contact.id) if m.channel_type == 'phone']

                if not phone_mappings:
                    # Add phone mapping if it doesn't exist
                    mapping_service.add_channel_mapping(
                        contact_id=contact.id,
                        channel_type='phone',
                        channel_identifier=phone_number,
                        tenant_id=tenant_id
                    )
                    # Dual-write to legacy column
                    contact.phone_number = phone_number
                    updated = True
                elif phone_mappings[0].channel_identifier != phone_number:
                    # Update if changed
                    self.logger.info(
                        f"Updating phone number for {contact.friendly_name}: "
                        f"{phone_mappings[0].channel_identifier} → {phone_number}"
                    )
                    # Remove old and add new (phone numbers can be reassigned)
                    mapping_service.remove_channel_mapping_by_id(phone_mappings[0].id)
                    mapping_service.add_channel_mapping(
                        contact_id=contact.id,
                        channel_type='phone',
                        channel_identifier=phone_number,
                        tenant_id=tenant_id
                    )
                    # Dual-write to legacy column
                    contact.phone_number = phone_number
                    updated = True

            if updated:
                contact.updated_at = datetime.utcnow()
                self.db.commit()
                self.db.refresh(contact)

            return contact

        # Create new contact
        friendly_name = sender_name or f"WhatsApp User {whatsapp_id}"

        self.logger.info(
            f"Auto-creating contact: {friendly_name} "
            f"(whatsapp_id={whatsapp_id}, phone={phone_number})"
        )

        # Dual-write: Create contact with legacy columns
        contact = Contact(
            friendly_name=friendly_name,
            whatsapp_id=whatsapp_id,  # LEGACY: Keep for backward compatibility
            phone_number=phone_number,  # LEGACY: Keep for backward compatibility
            role="user",
            is_active=True,
            is_dm_trigger=True,
            tenant_id=tenant_id,
            user_id=user_id
        )

        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)

        # Phase 10.2: Add channel mappings (NEW)
        mapping_service.add_channel_mapping(
            contact_id=contact.id,
            channel_type='whatsapp',
            channel_identifier=whatsapp_id,
            tenant_id=tenant_id
        )

        if phone_number:
            mapping_service.add_channel_mapping(
                contact_id=contact.id,
                channel_type='phone',
                channel_identifier=phone_number,
                tenant_id=tenant_id
            )

        self.logger.info(f"Created WhatsApp channel mappings for contact {contact.id}")

        return contact
