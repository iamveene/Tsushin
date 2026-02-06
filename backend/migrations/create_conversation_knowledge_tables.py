"""
Phase 14.6: Create Knowledge Extraction Tables
Creates tables for storing AI-generated tags, insights, and conversation links.
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def upgrade(db_path: str):
    """
    Create knowledge extraction tables.

    Args:
        db_path: Path to SQLite database
    """
    logger.info("[Phase 14.6] Creating knowledge extraction tables...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Tags table (AI-generated or user-defined)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_tag (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                tag VARCHAR(100) NOT NULL,
                source VARCHAR(10) DEFAULT 'ai' CHECK(source IN ('ai', 'user')),
                color VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tenant_id VARCHAR(50) NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES conversation_thread(id) ON DELETE CASCADE
            )
        """)
        logger.info("✅ Created conversation_tag table")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_tag_thread
            ON conversation_tag(thread_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_tag_tenant_user
            ON conversation_tag(tenant_id, user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_tag_tag
            ON conversation_tag(tag)
        """)

        logger.info("✅ Created conversation_tag indexes")

        # Insights table (AI-extracted key learnings)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_insight (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                insight_text TEXT NOT NULL,
                insight_type VARCHAR(50) DEFAULT 'fact'
                    CHECK(insight_type IN ('fact', 'conclusion', 'decision', 'action_item', 'question')),
                confidence FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tenant_id VARCHAR(50) NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES conversation_thread(id) ON DELETE CASCADE
            )
        """)
        logger.info("✅ Created conversation_insight table")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_insight_thread
            ON conversation_insight(thread_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_insight_type
            ON conversation_insight(insight_type)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_insight_tenant_user
            ON conversation_insight(tenant_id, user_id)
        """)

        logger.info("✅ Created conversation_insight indexes")

        # Related conversations (AI-suggested links)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversation_link (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_thread_id INTEGER NOT NULL,
                target_thread_id INTEGER NOT NULL,
                relationship_type VARCHAR(50) DEFAULT 'related',
                confidence FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                tenant_id VARCHAR(50) NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (source_thread_id) REFERENCES conversation_thread(id) ON DELETE CASCADE,
                FOREIGN KEY (target_thread_id) REFERENCES conversation_thread(id) ON DELETE CASCADE
            )
        """)
        logger.info("✅ Created conversation_link table")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_link_source
            ON conversation_link(source_thread_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_link_target
            ON conversation_link(target_thread_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_link_tenant_user
            ON conversation_link(tenant_id, user_id)
        """)

        logger.info("✅ Created conversation_link indexes")

        conn.commit()
        logger.info("[Phase 14.6] Knowledge tables migration completed successfully!")

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to create knowledge tables: {e}")
        raise
    finally:
        conn.close()


def downgrade(db_path: str):
    """
    Remove knowledge extraction tables.

    Args:
        db_path: Path to SQLite database
    """
    logger.info("[Phase 14.6] Rolling back knowledge tables migration...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("DROP TABLE IF EXISTS conversation_link")
        cursor.execute("DROP TABLE IF EXISTS conversation_insight")
        cursor.execute("DROP TABLE IF EXISTS conversation_tag")

        conn.commit()
        logger.info("[Phase 14.6] Knowledge tables rollback completed")

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to rollback knowledge tables migration: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        upgrade(db_path)
    else:
        print("Usage: python create_conversation_knowledge_tables.py <db_path>")
