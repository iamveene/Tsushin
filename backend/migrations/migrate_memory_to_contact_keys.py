#!/usr/bin/env python3
"""
Migration Script: Convert Phone-Based Memory Keys to Contact-Based Keys

This script migrates legacy memory entries that use phone numbers as sender_key
to the new contact-based format (contact_X) for cross-platform memory consistency.

Features:
- Backs up tables before migration
- Supports --dry-run mode to preview changes
- Merges duplicate entries when both phone-based and contact-based exist
- Logs all changes for audit

Usage:
    python migrate_memory_to_contact_keys.py --dry-run  # Preview changes
    python migrate_memory_to_contact_keys.py            # Run migration
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_path() -> str:
    """Get database path from environment or use default."""
    return os.environ.get("DATABASE_PATH", "/app/data/agent.db")


def create_backup(engine, table_name: str, backup_suffix: str) -> bool:
    """Create a backup of a table before migration."""
    backup_table = f"{table_name}_backup_{backup_suffix}"
    try:
        with engine.connect() as conn:
            # Check if backup already exists
            result = conn.execute(text(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{backup_table}'"
            )).fetchone()

            if result:
                logger.warning(f"Backup table {backup_table} already exists, skipping backup")
                return True

            # Create backup
            conn.execute(text(f"CREATE TABLE {backup_table} AS SELECT * FROM {table_name}"))
            conn.commit()
            logger.info(f"Created backup: {backup_table}")
            return True
    except Exception as e:
        logger.error(f"Failed to create backup of {table_name}: {e}")
        return False


def get_contacts_with_identifiers(engine) -> Dict[str, int]:
    """
    Build a mapping of phone numbers and WhatsApp IDs to contact IDs.

    Returns:
        Dict mapping phone/whatsapp_id to contact_id
    """
    mapping = {}
    try:
        with engine.connect() as conn:
            contacts = conn.execute(text("""
                SELECT id, phone_number, whatsapp_id
                FROM contact
                WHERE phone_number IS NOT NULL OR whatsapp_id IS NOT NULL
            """)).fetchall()

            for contact in contacts:
                contact_id, phone, whatsapp_id = contact
                if phone:
                    # Normalize phone (remove + prefix)
                    normalized_phone = phone.lstrip('+')
                    mapping[normalized_phone] = contact_id
                    mapping[phone] = contact_id
                if whatsapp_id:
                    mapping[whatsapp_id] = contact_id

            logger.info(f"Loaded {len(contacts)} contacts with {len(mapping)} identifier mappings")
    except Exception as e:
        logger.error(f"Failed to load contacts: {e}")

    return mapping


def get_user_contact_mappings(engine) -> Dict[int, int]:
    """
    Get UserContactMapping entries (user_id -> contact_id).

    Returns:
        Dict mapping user_id to contact_id
    """
    mapping = {}
    try:
        with engine.connect() as conn:
            mappings = conn.execute(text("""
                SELECT user_id, contact_id
                FROM user_contact_mapping
            """)).fetchall()

            for m in mappings:
                mapping[m[0]] = m[1]

            logger.info(f"Loaded {len(mapping)} user-contact mappings")
    except Exception as e:
        logger.error(f"Failed to load user-contact mappings: {e}")

    return mapping


def identify_legacy_memory_entries(engine, contact_mapping: Dict[str, int],
                                    user_contact_mapping: Dict[int, int]) -> List[Dict]:
    """
    Identify memory entries that need migration.

    Returns:
        List of entries to migrate with their target contact_id
    """
    entries_to_migrate = []

    try:
        with engine.connect() as conn:
            # Get all memory entries
            memories = conn.execute(text("""
                SELECT id, agent_id, sender_key, messages_json, updated_at
                FROM memory
            """)).fetchall()

            for memory in memories:
                mem_id, agent_id, sender_key, messages_json, updated_at = memory
                target_contact_id = None
                migration_reason = None

                # Skip if already contact-based
                if sender_key.startswith('contact_'):
                    continue

                # Skip shared memory
                if sender_key == 'shared':
                    continue

                # Skip group chats (contain @g.us)
                if '@g.us' in sender_key:
                    continue

                # Check if phone number maps to a contact
                if sender_key in contact_mapping:
                    target_contact_id = contact_mapping[sender_key]
                    migration_reason = f"phone_to_contact"

                # Check if it's an old playground user format
                elif sender_key.startswith('sender_playground_user_'):
                    try:
                        user_id = int(sender_key.replace('sender_playground_user_', ''))
                        if user_id in user_contact_mapping:
                            target_contact_id = user_contact_mapping[user_id]
                            migration_reason = f"playground_user_to_contact"
                    except ValueError:
                        pass

                # Check if it's a plain phone number (digits only)
                elif sender_key.isdigit() and len(sender_key) >= 10:
                    # Try to find in contact mapping
                    if sender_key in contact_mapping:
                        target_contact_id = contact_mapping[sender_key]
                        migration_reason = f"phone_to_contact"

                if target_contact_id:
                    entries_to_migrate.append({
                        'id': mem_id,
                        'agent_id': agent_id,
                        'sender_key': sender_key,
                        'target_key': f"contact_{target_contact_id}",
                        'target_contact_id': target_contact_id,
                        'messages_json': messages_json,
                        'updated_at': updated_at,
                        'reason': migration_reason
                    })

            logger.info(f"Found {len(entries_to_migrate)} memory entries to migrate")
    except Exception as e:
        logger.error(f"Failed to identify legacy entries: {e}")

    return entries_to_migrate


def identify_legacy_semantic_knowledge(engine, contact_mapping: Dict[str, int],
                                        user_contact_mapping: Dict[int, int]) -> List[Dict]:
    """
    Identify semantic_knowledge entries that need migration.

    Returns:
        List of entries to migrate with their target contact_id
    """
    entries_to_migrate = []

    try:
        with engine.connect() as conn:
            # Check if table exists
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_knowledge'"
            )).fetchone()

            if not result:
                logger.info("semantic_knowledge table does not exist, skipping")
                return []

            # Get all semantic_knowledge entries
            knowledge = conn.execute(text("""
                SELECT id, agent_id, user_id, topic, key, value
                FROM semantic_knowledge
            """)).fetchall()

            for k in knowledge:
                k_id, agent_id, user_id, topic, key, value = k
                target_contact_id = None
                migration_reason = None

                # Skip if already contact-based
                if user_id.startswith('contact_'):
                    continue

                # Check if phone number maps to a contact
                if user_id in contact_mapping:
                    target_contact_id = contact_mapping[user_id]
                    migration_reason = f"phone_to_contact"

                # Check if it's an old playground user format
                elif user_id.startswith('sender_playground_user_'):
                    try:
                        uid = int(user_id.replace('sender_playground_user_', ''))
                        if uid in user_contact_mapping:
                            target_contact_id = user_contact_mapping[uid]
                            migration_reason = f"playground_user_to_contact"
                    except ValueError:
                        pass

                if target_contact_id:
                    entries_to_migrate.append({
                        'id': k_id,
                        'agent_id': agent_id,
                        'user_id': user_id,
                        'target_key': f"contact_{target_contact_id}",
                        'target_contact_id': target_contact_id,
                        'reason': migration_reason
                    })

            logger.info(f"Found {len(entries_to_migrate)} semantic_knowledge entries to migrate")
    except Exception as e:
        logger.error(f"Failed to identify legacy semantic_knowledge: {e}")

    return entries_to_migrate


def merge_messages(existing_messages: List[Dict], new_messages: List[Dict]) -> List[Dict]:
    """
    Merge two lists of messages, deduplicating and sorting by timestamp.

    Args:
        existing_messages: Messages from existing contact-based entry
        new_messages: Messages from legacy entry to merge

    Returns:
        Merged and deduplicated message list
    """
    # Combine all messages
    all_messages = existing_messages + new_messages

    # Deduplicate by content + timestamp
    seen = set()
    unique_messages = []
    for msg in all_messages:
        # Create a key for deduplication
        key = (msg.get('role', ''), msg.get('content', '')[:100], msg.get('timestamp', ''))
        if key not in seen:
            seen.add(key)
            unique_messages.append(msg)

    # Sort by timestamp
    def get_timestamp(msg):
        ts = msg.get('timestamp', '')
        if ts:
            try:
                return datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                pass
        return datetime.min

    unique_messages.sort(key=get_timestamp)

    return unique_messages


def migrate_memory_entries(engine, entries: List[Dict], dry_run: bool = True) -> Tuple[int, int]:
    """
    Migrate memory entries to contact-based keys.

    Returns:
        Tuple of (migrated_count, merged_count)
    """
    migrated = 0
    merged = 0

    try:
        with engine.connect() as conn:
            for entry in entries:
                target_key = entry['target_key']
                agent_id = entry['agent_id']

                # Check if target entry already exists
                existing = conn.execute(text("""
                    SELECT id, messages_json
                    FROM memory
                    WHERE agent_id = :agent_id AND sender_key = :sender_key
                """), {'agent_id': agent_id, 'sender_key': target_key}).fetchone()

                if existing:
                    # Merge messages
                    existing_id, existing_messages_json = existing
                    existing_messages = json.loads(existing_messages_json) if existing_messages_json else []
                    new_messages = json.loads(entry['messages_json']) if entry['messages_json'] else []

                    merged_messages = merge_messages(existing_messages, new_messages)

                    logger.info(f"{'[DRY-RUN] ' if dry_run else ''}MERGE: "
                               f"id={entry['id']} ({entry['sender_key']}) -> {target_key} "
                               f"({len(existing_messages)} + {len(new_messages)} = {len(merged_messages)} messages)")

                    if not dry_run:
                        # Update existing entry with merged messages
                        conn.execute(text("""
                            UPDATE memory
                            SET messages_json = :messages, updated_at = :updated_at
                            WHERE id = :id
                        """), {
                            'messages': json.dumps(merged_messages),
                            'updated_at': datetime.utcnow(),
                            'id': existing_id
                        })

                        # Delete the old entry
                        conn.execute(text("DELETE FROM memory WHERE id = :id"), {'id': entry['id']})

                    merged += 1
                else:
                    # Simple key update
                    logger.info(f"{'[DRY-RUN] ' if dry_run else ''}MIGRATE: "
                               f"id={entry['id']} ({entry['sender_key']}) -> {target_key}")

                    if not dry_run:
                        conn.execute(text("""
                            UPDATE memory
                            SET sender_key = :new_key, updated_at = :updated_at
                            WHERE id = :id
                        """), {
                            'new_key': target_key,
                            'updated_at': datetime.utcnow(),
                            'id': entry['id']
                        })

                    migrated += 1

            if not dry_run:
                conn.commit()

    except Exception as e:
        logger.error(f"Failed to migrate memory entries: {e}")
        raise

    return migrated, merged


def migrate_semantic_knowledge(engine, entries: List[Dict], dry_run: bool = True) -> Tuple[int, int]:
    """
    Migrate semantic_knowledge entries to contact-based keys.
    Handles duplicate key conflicts by keeping the newer entry.

    Returns:
        Tuple of (migrated_count, deleted_duplicates_count)
    """
    migrated = 0
    deleted = 0

    try:
        with engine.connect() as conn:
            for entry in entries:
                target_key = entry['target_key']
                agent_id = entry['agent_id']

                # Get the current entry's details
                current = conn.execute(text("""
                    SELECT topic, key, value, updated_at
                    FROM semantic_knowledge
                    WHERE id = :id
                """), {'id': entry['id']}).fetchone()

                if not current:
                    continue

                topic, key, value, updated_at = current

                # Check if target entry already exists
                existing = conn.execute(text("""
                    SELECT id, value, updated_at
                    FROM semantic_knowledge
                    WHERE agent_id = :agent_id
                      AND user_id = :user_id
                      AND topic = :topic
                      AND key = :key
                """), {
                    'agent_id': agent_id,
                    'user_id': target_key,
                    'topic': topic,
                    'key': key
                }).fetchone()

                if existing:
                    # Duplicate exists - delete the old entry (keep the newer contact-based one)
                    logger.info(f"{'[DRY-RUN] ' if dry_run else ''}DELETE DUPLICATE KNOWLEDGE: "
                               f"id={entry['id']} ({entry['user_id']}) - target already exists at id={existing[0]}")

                    if not dry_run:
                        conn.execute(text("DELETE FROM semantic_knowledge WHERE id = :id"),
                                    {'id': entry['id']})
                    deleted += 1
                else:
                    # No duplicate - safe to update
                    logger.info(f"{'[DRY-RUN] ' if dry_run else ''}MIGRATE KNOWLEDGE: "
                               f"id={entry['id']} ({entry['user_id']}) -> {target_key}")

                    if not dry_run:
                        conn.execute(text("""
                            UPDATE semantic_knowledge
                            SET user_id = :new_key, updated_at = :updated_at
                            WHERE id = :id
                        """), {
                            'new_key': target_key,
                            'updated_at': datetime.utcnow(),
                            'id': entry['id']
                        })
                    migrated += 1

            if not dry_run:
                conn.commit()

    except Exception as e:
        logger.error(f"Failed to migrate semantic_knowledge entries: {e}")
        raise

    return migrated, deleted


def main():
    parser = argparse.ArgumentParser(
        description='Migrate memory keys from phone-based to contact-based format'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without making them'
    )
    parser.add_argument(
        '--database',
        type=str,
        default=None,
        help='Path to database file (default: from DATABASE_PATH env or /app/data/agent.db)'
    )
    parser.add_argument(
        '--skip-backup',
        action='store_true',
        help='Skip creating backup tables'
    )

    args = parser.parse_args()

    # Get database path
    db_path = args.database or get_database_path()
    logger.info(f"Using database: {db_path}")

    # Create engine
    engine = create_engine(f"sqlite:///{db_path}")

    # Create backups if not dry-run and not skipped
    backup_suffix = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    if not args.dry_run and not args.skip_backup:
        logger.info("Creating backups...")
        if not create_backup(engine, 'memory', backup_suffix):
            logger.error("Failed to create memory backup, aborting")
            return 1
        create_backup(engine, 'semantic_knowledge', backup_suffix)  # May not exist

    # Load mappings
    logger.info("Loading contact mappings...")
    contact_mapping = get_contacts_with_identifiers(engine)
    user_contact_mapping = get_user_contact_mappings(engine)

    # Identify entries to migrate
    logger.info("Identifying entries to migrate...")
    memory_entries = identify_legacy_memory_entries(engine, contact_mapping, user_contact_mapping)
    knowledge_entries = identify_legacy_semantic_knowledge(engine, contact_mapping, user_contact_mapping)

    if not memory_entries and not knowledge_entries:
        logger.info("No entries need migration!")
        return 0

    # Migrate memory entries
    if memory_entries:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"MIGRATING MEMORY TABLE ({len(memory_entries)} entries)")
        logger.info('=' * 50)
        migrated, merged = migrate_memory_entries(engine, memory_entries, args.dry_run)
        logger.info(f"Memory: {migrated} migrated, {merged} merged")

    # Migrate semantic_knowledge entries
    if knowledge_entries:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"MIGRATING SEMANTIC_KNOWLEDGE TABLE ({len(knowledge_entries)} entries)")
        logger.info('=' * 50)
        sk_migrated, sk_deleted = migrate_semantic_knowledge(engine, knowledge_entries, args.dry_run)
        logger.info(f"Semantic Knowledge: {sk_migrated} migrated, {sk_deleted} duplicates deleted")

    # Summary
    logger.info(f"\n{'=' * 50}")
    logger.info("MIGRATION SUMMARY")
    logger.info('=' * 50)
    if args.dry_run:
        logger.info("[DRY-RUN MODE] No changes were made")
        logger.info(f"Would migrate {len(memory_entries)} memory entries")
        logger.info(f"Would migrate {len(knowledge_entries)} semantic_knowledge entries")
        logger.info("\nRun without --dry-run to apply changes")
    else:
        logger.info(f"Successfully migrated {len(memory_entries)} memory entries")
        logger.info(f"Successfully migrated {len(knowledge_entries)} semantic_knowledge entries")
        logger.info(f"Backup tables created with suffix: {backup_suffix}")

    return 0


if __name__ == '__main__':
    sys.exit(main())
