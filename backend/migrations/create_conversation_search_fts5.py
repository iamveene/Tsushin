"""
Phase 14.5: Create FTS5 Virtual Table for Conversation Search
Creates SQLite Full-Text Search index for fast conversation search.
"""

import sqlite3
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def upgrade(db_path: str):
    """
    Create FTS5 virtual table and trigger for conversation search.

    Args:
        db_path: Path to SQLite database
    """
    logger.info("[Phase 14.5] Creating FTS5 table for conversation search...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if FTS5 is available
        cursor.execute("PRAGMA compile_options;")
        compile_options = [row[0] for row in cursor.fetchall()]
        has_fts5 = any('FTS5' in opt for opt in compile_options)

        if not has_fts5:
            logger.warning("SQLite FTS5 not available. Skipping FTS5 table creation.")
            logger.warning("Full-text search will fall back to LIKE queries.")
            conn.close()
            return

        # Create FTS5 virtual table for conversation search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS conversation_search_fts USING fts5(
                thread_id,
                message_id,
                role,
                content,
                timestamp,
                tenant_id UNINDEXED,
                user_id UNINDEXED,
                agent_id UNINDEXED,
                tokenize='porter unicode61'
            )
        """)

        # Commit the FTS5 table creation immediately so it's available even if population fails
        conn.commit()
        logger.info("✅ Created conversation_search_fts virtual table")

        # Try to populate FTS table from existing messages (optional - won't fail migration)
        # This only works if the memory table already exists (during server restarts)
        try:
            # Check if memory table exists first
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory';")
            if cursor.fetchone() is None:
                logger.info("Memory table doesn't exist yet - FTS will be populated as messages are added")
            else:
                # Note: Existing messages are stored in messages_json column
                # We'll populate FTS table from the JSON data
                logger.info("Populating FTS table with existing playground messages...")

                cursor.execute("""
                    SELECT m.id, m.agent_id, m.sender_key, m.messages_json,
                           m.tenant_id, m.user_id, ct.id as thread_id
                    FROM memory m
                    LEFT JOIN conversation_thread ct ON (
                        ct.user_id = m.user_id
                        AND ct.agent_id = m.agent_id
                        AND ct.thread_type = 'playground'
                    )
                    WHERE m.sender_key LIKE '%playground%' OR ct.id IS NOT NULL
                """)

                rows = cursor.fetchall()
                messages_inserted = 0

                import json
                for row in rows:
                    memory_id, agent_id, sender_key, messages_json, tenant_id, user_id, thread_id = row

                    # If no thread_id from JOIN, try extracting from sender_key
                    if not thread_id and '_t' in sender_key:
                        thread_id_str = sender_key.split('_t')[-1]
                        try:
                            thread_id = int(thread_id_str)
                        except ValueError:
                            thread_id = None

                    if not thread_id:
                        continue

                    # Parse messages JSON
                    try:
                        messages = json.loads(messages_json) if messages_json else []
                    except:
                        messages = []

                    # Insert each message into FTS table
                    for msg in messages:
                        if isinstance(msg, dict) and 'content' in msg and 'role' in msg:
                            message_id = msg.get('message_id', f"msg_{memory_id}_{messages.index(msg)}")
                            role = msg.get('role', 'user')
                            content = msg.get('content', '')
                            timestamp = msg.get('timestamp', '')

                            if content:
                                cursor.execute("""
                                    INSERT INTO conversation_search_fts(
                                        thread_id, message_id, role, content, timestamp,
                                        tenant_id, user_id, agent_id
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """, (thread_id, message_id, role, content, timestamp, tenant_id, user_id, agent_id))
                                messages_inserted += 1

                logger.info(f"✅ Populated FTS table with {messages_inserted} existing messages from {len(rows)} memory records")
                conn.commit()
        except Exception as pop_error:
            logger.warning(f"Could not populate FTS table from existing messages: {pop_error}")
            logger.info("FTS table created - new messages will be indexed as they are added")

        # Note: Triggers for JSON-based messages would be complex
        # Instead, we'll update FTS from the application layer when messages are added
        # This is more reliable and allows better error handling
        logger.info("✅ FTS table ready (application will manage updates)")
        logger.info("[Phase 14.5] FTS5 migration completed successfully!")

    except Exception as e:
        logger.error(f"Failed to create FTS5 table: {e}")
        raise
    finally:
        conn.close()


def downgrade(db_path: str):
    """
    Remove FTS5 table.

    Args:
        db_path: Path to SQLite database
    """
    logger.info("[Phase 14.5] Rolling back FTS5 migration...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("DROP TABLE IF EXISTS conversation_search_fts")

        conn.commit()
        logger.info("[Phase 14.5] FTS5 rollback completed")

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to rollback FTS5 migration: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        upgrade(db_path)
    else:
        print("Usage: python create_conversation_search_fts5.py <db_path>")
