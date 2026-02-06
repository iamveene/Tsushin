"""
Phase 10.2: Contact Channel Mapping Migration

Creates the contact_channel_mapping table and migrates existing channel identifiers
from Contact table columns (whatsapp_id, telegram_id, phone_number) to the new table.

This migration maintains backward compatibility by keeping the old columns intact
during the transition period (dual-write strategy).

Run with: python backend/migrations/add_contact_channel_mapping.py
"""

import sys
import os
import logging
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import Base, Contact, ContactChannelMapping

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(db_path: str = "backend/data/agent.db"):
    """
    Run the migration to create contact_channel_mapping table and migrate data.

    Args:
        db_path: Path to the SQLite database file
    """
    logger.info(f"Starting migration: add_contact_channel_mapping")
    logger.info(f"Database: {db_path}")

    # Create engine
    engine = create_engine(f'sqlite:///{db_path}')
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Step 1: Create the new table
        logger.info("Step 1: Creating contact_channel_mapping table...")
        ContactChannelMapping.__table__.create(engine, checkfirst=True)
        logger.info("✓ Table created successfully")

        # Step 2: Migrate existing data
        logger.info("Step 2: Migrating existing channel identifiers...")

        # Get all contacts
        contacts = session.query(Contact).all()
        logger.info(f"Found {len(contacts)} contacts to process")

        migrated_count = {
            'whatsapp': 0,
            'telegram': 0,
            'phone': 0,
            'total': 0
        }

        # Track identifiers we've already processed to avoid duplicates within this migration
        processed_identifiers = set()  # Will store tuples of (channel_type, identifier, tenant_id)

        # Use no_autoflush to avoid premature flushes during queries
        with session.no_autoflush:
            for contact in contacts:
                # Determine tenant_id (use contact's tenant_id or default to 'default')
                tenant_id = contact.tenant_id or 'default'

                # Migrate WhatsApp ID
                if contact.whatsapp_id and contact.whatsapp_id.strip():
                    identifier_key = ('whatsapp', contact.whatsapp_id, tenant_id)

                    # Check if we've already processed this identifier in this migration run
                    if identifier_key in processed_identifiers:
                        logger.warning(f"  Skipping WhatsApp ID {contact.whatsapp_id} for contact {contact.id} - already processed")
                        continue

                    # Check if mapping already exists in the database
                    existing = session.query(ContactChannelMapping).filter(
                        ContactChannelMapping.channel_type == 'whatsapp',
                        ContactChannelMapping.channel_identifier == contact.whatsapp_id,
                        ContactChannelMapping.tenant_id == tenant_id
                    ).first()

                    if not existing:
                        mapping = ContactChannelMapping(
                            contact_id=contact.id,
                            channel_type='whatsapp',
                            channel_identifier=contact.whatsapp_id,
                            tenant_id=tenant_id,
                            created_at=contact.created_at,
                            updated_at=contact.updated_at
                        )
                        session.add(mapping)
                        processed_identifiers.add(identifier_key)
                        migrated_count['whatsapp'] += 1
                        migrated_count['total'] += 1
                        logger.debug(f"  Migrated WhatsApp ID for contact {contact.id}: {contact.whatsapp_id}")
                    else:
                        processed_identifiers.add(identifier_key)
                        logger.warning(f"  Skipping WhatsApp ID {contact.whatsapp_id} for contact {contact.id} - already mapped to contact {existing.contact_id}")

                # Migrate Phone Number
                if contact.phone_number and contact.phone_number.strip():
                    identifier_key = ('phone', contact.phone_number, tenant_id)

                    # Check if we've already processed this identifier in this migration run
                    if identifier_key in processed_identifiers:
                        logger.warning(f"  Skipping phone {contact.phone_number} for contact {contact.id} - already processed")
                        continue

                    # Check if mapping already exists in the database
                    existing = session.query(ContactChannelMapping).filter(
                        ContactChannelMapping.channel_type == 'phone',
                        ContactChannelMapping.channel_identifier == contact.phone_number,
                        ContactChannelMapping.tenant_id == tenant_id
                    ).first()

                    if not existing:
                        mapping = ContactChannelMapping(
                            contact_id=contact.id,
                            channel_type='phone',
                            channel_identifier=contact.phone_number,
                            tenant_id=tenant_id,
                            created_at=contact.created_at,
                            updated_at=contact.updated_at
                        )
                        session.add(mapping)
                        processed_identifiers.add(identifier_key)
                        migrated_count['phone'] += 1
                        migrated_count['total'] += 1
                        logger.debug(f"  Migrated phone number for contact {contact.id}: {contact.phone_number}")
                    else:
                        processed_identifiers.add(identifier_key)
                        logger.warning(f"  Skipping phone {contact.phone_number} for contact {contact.id} - already mapped to contact {existing.contact_id}")

                # Migrate Telegram ID (with username in metadata)
                if contact.telegram_id and contact.telegram_id.strip():
                    identifier_key = ('telegram', contact.telegram_id, tenant_id)

                    # Check if we've already processed this identifier in this migration run
                    if identifier_key in processed_identifiers:
                        logger.warning(f"  Skipping Telegram ID {contact.telegram_id} for contact {contact.id} - already processed")
                        continue

                    # Check if mapping already exists in the database
                    existing = session.query(ContactChannelMapping).filter(
                        ContactChannelMapping.channel_type == 'telegram',
                        ContactChannelMapping.channel_identifier == contact.telegram_id,
                        ContactChannelMapping.tenant_id == tenant_id
                    ).first()

                    if not existing:
                        # Include username in metadata if available
                        channel_metadata = {}
                        if contact.telegram_username:
                            channel_metadata['username'] = contact.telegram_username

                        mapping = ContactChannelMapping(
                            contact_id=contact.id,
                            channel_type='telegram',
                            channel_identifier=contact.telegram_id,
                            channel_metadata=channel_metadata if channel_metadata else None,
                            tenant_id=tenant_id,
                            created_at=contact.created_at,
                            updated_at=contact.updated_at
                        )
                        session.add(mapping)
                        processed_identifiers.add(identifier_key)
                        migrated_count['telegram'] += 1
                        migrated_count['total'] += 1
                        logger.debug(f"  Migrated Telegram ID for contact {contact.id}: {contact.telegram_id}")
                    else:
                        processed_identifiers.add(identifier_key)
                        logger.warning(f"  Skipping Telegram ID {contact.telegram_id} for contact {contact.id} - already mapped to contact {existing.contact_id}")

        # Commit all migrations
        session.commit()

        logger.info(f"✓ Migration completed successfully!")
        logger.info(f"  - WhatsApp mappings: {migrated_count['whatsapp']}")
        logger.info(f"  - Phone mappings: {migrated_count['phone']}")
        logger.info(f"  - Telegram mappings: {migrated_count['telegram']}")
        logger.info(f"  - Total mappings created: {migrated_count['total']}")

        # Step 3: Validation
        logger.info("Step 3: Validating migration...")
        total_mappings = session.query(ContactChannelMapping).count()
        logger.info(f"✓ Total mappings in database: {total_mappings}")

        # Verify no data loss - count should match
        if total_mappings != migrated_count['total']:
            logger.warning(f"⚠️  Mapping count mismatch: expected {migrated_count['total']}, found {total_mappings}")

        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        session.rollback()
        raise
    finally:
        session.close()


def rollback_migration(db_path: str = "backend/data/agent.db"):
    """
    Rollback the migration by dropping the contact_channel_mapping table.

    NOTE: This will delete all channel mapping data!
    Old columns (whatsapp_id, telegram_id, phone_number) on Contact table remain intact.

    Args:
        db_path: Path to the SQLite database file
    """
    logger.info(f"Rolling back migration: add_contact_channel_mapping")
    logger.info(f"Database: {db_path}")

    engine = create_engine(f'sqlite:///{db_path}')

    try:
        logger.info("Dropping contact_channel_mapping table...")
        ContactChannelMapping.__table__.drop(engine, checkfirst=True)
        logger.info("✓ Rollback completed successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Rollback failed: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Contact Channel Mapping Migration')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    parser.add_argument('--db', default='backend/data/agent.db', help='Database path')

    args = parser.parse_args()

    if args.rollback:
        rollback_migration(args.db)
    else:
        run_migration(args.db)
