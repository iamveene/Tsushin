"""
Contact Channel Mapping Service
Phase 10.2

Service for managing contact channel mappings across all communication platforms.
Provides CRUD operations for the ContactChannelMapping table.
"""

import logging
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import Contact, ContactChannelMapping

logger = logging.getLogger(__name__)


class ContactChannelMappingService:
    """
    Service for managing contact channel mappings.

    Handles creation, retrieval, update, and deletion of channel identifiers
    for contacts across multiple communication platforms (WhatsApp, Telegram, Discord, etc.).
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def add_channel_mapping(
        self,
        contact_id: int,
        channel_type: str,
        channel_identifier: str,
        channel_metadata: Optional[dict] = None,
        tenant_id: str = "default"
    ) -> ContactChannelMapping:
        """
        Add a new channel mapping for a contact.

        Args:
            contact_id: Contact ID
            channel_type: Channel type ('whatsapp', 'telegram', 'phone', 'discord', 'email', etc.)
            channel_identifier: The channel-specific identifier (user_id, phone, email, etc.)
            channel_metadata: Optional metadata (e.g., {'username': '@johndoe'})
            tenant_id: Tenant ID

        Returns:
            ContactChannelMapping instance (existing or newly created)

        Raises:
            IntegrityError: If identifier is already mapped to a different contact in the same tenant
        """
        try:
            # Check if this exact mapping already exists
            existing = self.db.query(ContactChannelMapping).filter(
                ContactChannelMapping.contact_id == contact_id,
                ContactChannelMapping.channel_type == channel_type,
                ContactChannelMapping.channel_identifier == channel_identifier,
                ContactChannelMapping.tenant_id == tenant_id
            ).first()

            if existing:
                # Update metadata if provided and different
                if channel_metadata and existing.channel_metadata != channel_metadata:
                    self.logger.info(
                        f"Updating metadata for {channel_type} mapping {channel_identifier} "
                        f"(contact {contact_id})"
                    )
                    existing.channel_metadata = channel_metadata
                    existing.updated_at = datetime.utcnow()
                    self.db.commit()
                    self.db.refresh(existing)
                return existing

            # Create new mapping
            mapping = ContactChannelMapping(
                contact_id=contact_id,
                channel_type=channel_type,
                channel_identifier=channel_identifier,
                channel_metadata=channel_metadata or {},
                tenant_id=tenant_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(mapping)
            self.db.commit()
            self.db.refresh(mapping)

            self.logger.info(
                f"Created {channel_type} mapping for contact {contact_id}: {channel_identifier}"
            )
            return mapping

        except IntegrityError as e:
            self.db.rollback()
            self.logger.error(
                f"Failed to add {channel_type} mapping {channel_identifier}: {e}"
            )
            raise

    def get_contact_by_channel(
        self,
        channel_type: str,
        channel_identifier: str,
        tenant_id: str
    ) -> Optional[Contact]:
        """
        Find contact by channel identifier.

        Args:
            channel_type: Channel type ('whatsapp', 'telegram', etc.)
            channel_identifier: The channel-specific identifier
            tenant_id: Tenant ID

        Returns:
            Contact instance if found, None otherwise
        """
        mapping = self.db.query(ContactChannelMapping).filter(
            ContactChannelMapping.channel_type == channel_type,
            ContactChannelMapping.channel_identifier == channel_identifier,
            ContactChannelMapping.tenant_id == tenant_id
        ).first()

        if mapping:
            contact = self.db.query(Contact).get(mapping.contact_id)
            self.logger.debug(
                f"Resolved contact {contact.id} ({contact.friendly_name}) "
                f"via {channel_type}: {channel_identifier}"
            )
            return contact

        self.logger.debug(
            f"No contact found for {channel_type}: {channel_identifier} (tenant: {tenant_id})"
        )
        return None

    def get_channel_mappings(
        self,
        contact_id: int,
        channel_type: Optional[str] = None
    ) -> List[ContactChannelMapping]:
        """
        Get all channel mappings for a contact.

        Args:
            contact_id: Contact ID
            channel_type: Optional channel type filter

        Returns:
            List of ContactChannelMapping instances
        """
        query = self.db.query(ContactChannelMapping).filter(
            ContactChannelMapping.contact_id == contact_id
        )

        if channel_type:
            query = query.filter(ContactChannelMapping.channel_type == channel_type)

        mappings = query.all()
        self.logger.debug(f"Found {len(mappings)} channel mappings for contact {contact_id}")
        return mappings

    def remove_channel_mapping(
        self,
        contact_id: int,
        channel_type: str,
        channel_identifier: str
    ) -> bool:
        """
        Remove a specific channel mapping.

        Args:
            contact_id: Contact ID
            channel_type: Channel type
            channel_identifier: Channel identifier

        Returns:
            True if removed, False if not found
        """
        mapping = self.db.query(ContactChannelMapping).filter(
            ContactChannelMapping.contact_id == contact_id,
            ContactChannelMapping.channel_type == channel_type,
            ContactChannelMapping.channel_identifier == channel_identifier
        ).first()

        if mapping:
            self.db.delete(mapping)
            self.db.commit()
            self.logger.info(
                f"Removed {channel_type} mapping for contact {contact_id}: {channel_identifier}"
            )
            return True

        self.logger.warning(
            f"No mapping found to remove: contact {contact_id}, {channel_type}: {channel_identifier}"
        )
        return False

    def remove_channel_mapping_by_id(self, mapping_id: int) -> bool:
        """
        Remove a channel mapping by its ID.

        Args:
            mapping_id: ContactChannelMapping ID

        Returns:
            True if removed, False if not found
        """
        mapping = self.db.query(ContactChannelMapping).get(mapping_id)

        if mapping:
            self.db.delete(mapping)
            self.db.commit()
            self.logger.info(f"Removed channel mapping ID {mapping_id}")
            return True

        self.logger.warning(f"No mapping found with ID {mapping_id}")
        return False

    def update_channel_metadata(
        self,
        mapping_id: int,
        channel_metadata: dict
    ) -> Optional[ContactChannelMapping]:
        """
        Update metadata for a channel mapping.

        Args:
            mapping_id: ContactChannelMapping ID
            channel_metadata: New metadata dictionary

        Returns:
            Updated ContactChannelMapping instance if found, None otherwise
        """
        mapping = self.db.query(ContactChannelMapping).get(mapping_id)

        if mapping:
            mapping.channel_metadata = channel_metadata
            mapping.updated_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(mapping)
            self.logger.info(f"Updated metadata for channel mapping ID {mapping_id}")
            return mapping

        self.logger.warning(f"No mapping found with ID {mapping_id}")
        return None

    def get_mapping_by_id(self, mapping_id: int) -> Optional[ContactChannelMapping]:
        """
        Get a channel mapping by its ID.

        Args:
            mapping_id: ContactChannelMapping ID

        Returns:
            ContactChannelMapping instance if found, None otherwise
        """
        mapping = self.db.query(ContactChannelMapping).get(mapping_id)
        return mapping
