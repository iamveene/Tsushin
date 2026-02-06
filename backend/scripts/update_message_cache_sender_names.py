#!/usr/bin/env python3
"""
Update existing message_cache entries to use resolved contact names from ContactChannelMappingService.
This retroactively applies the Phase 10.2 fix to historical messages.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import MessageCache
from services.contact_channel_mapping_service import ContactChannelMappingService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_message_cache():
    # Connect to database
    engine = create_engine('sqlite:///data/agent.db')
    Session = sessionmaker(bind=engine)
    db = Session()

    mapping_service = ContactChannelMappingService(db)

    # Get all cached messages
    messages = db.query(MessageCache).all()
    logger.info(f"Found {len(messages)} messages in cache")

    updated_count = 0

    for msg in messages:
        if not msg.sender or not msg.channel:
            continue

        # Determine tenant_id based on message metadata
        # Default to "default" if we can't determine
        tenant_id = "default"

        # Try to resolve contact via channel mapping
        channel_identifier = None
        channel_type = None

        if msg.channel == "telegram":
            # For Telegram, sender is the telegram user ID
            channel_identifier = msg.sender.lstrip("+")
            channel_type = "telegram"
        elif msg.channel == "whatsapp":
            # For WhatsApp, try phone number
            channel_identifier = msg.sender.lstrip("+")
            channel_type = "phone"

        # Try to resolve contact
        if channel_identifier and channel_type:
            try:
                contact = mapping_service.get_contact_by_channel(channel_type, channel_identifier, tenant_id)
                if contact and contact.is_active:
                    old_name = msg.sender_name
                    msg.sender_name = contact.friendly_name
                    updated_count += 1
                    logger.info(f"Updated message {msg.id}: '{old_name}' -> '{contact.friendly_name}' (contact_id: {contact.id}, {channel_type}: {channel_identifier})")
                else:
                    # Try alternate tenant if default didn't work
                    if tenant_id == "default":
                        # Try common tenant patterns
                        for alt_tenant in ["tenant_20251202232822"]:
                            contact = mapping_service.get_contact_by_channel(channel_type, channel_identifier, alt_tenant)
                            if contact and contact.is_active:
                                old_name = msg.sender_name
                                msg.sender_name = contact.friendly_name
                                updated_count += 1
                                logger.info(f"Updated message {msg.id}: '{old_name}' -> '{contact.friendly_name}' (contact_id: {contact.id}, {channel_type}: {channel_identifier}, tenant: {alt_tenant})")
                                break
            except Exception as e:
                logger.warning(f"Failed to resolve sender for message {msg.id}: {e}")

    # Commit all updates
    db.commit()
    logger.info(f"✅ Updated {updated_count} out of {len(messages)} messages")

    db.close()

if __name__ == "__main__":
    update_message_cache()
