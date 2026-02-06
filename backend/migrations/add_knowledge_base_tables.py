"""
Phase 5.0: Knowledge Base System - Database Migration
Adds tables for document-based knowledge base.
"""

import sqlite3
import sys
from pathlib import Path

def migrate():
    """Add knowledge base tables to database."""
    db_path = Path("./data/agent.db")

    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if tables already exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_knowledge'")
        if cursor.fetchone():
            print("Tables already exist. Skipping migration.")
            return

        print("Creating agent_knowledge table...")
        cursor.execute("""
            CREATE TABLE agent_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                document_name VARCHAR(255) NOT NULL,
                document_type VARCHAR(20) NOT NULL,
                file_path VARCHAR(500) NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                num_chunks INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'pending',
                error_message TEXT,
                upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_date DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        print("Creating knowledge_chunk table...")
        cursor.execute("""
            CREATE TABLE knowledge_chunk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                knowledge_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                char_count INTEGER NOT NULL,
                metadata_json TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (knowledge_id) REFERENCES agent_knowledge(id) ON DELETE CASCADE
            )
        """)

        # Create indexes for better performance
        print("Creating indexes...")
        cursor.execute("CREATE INDEX idx_agent_knowledge_agent_id ON agent_knowledge(agent_id)")
        cursor.execute("CREATE INDEX idx_knowledge_chunk_knowledge_id ON knowledge_chunk(knowledge_id)")

        conn.commit()
        print("[OK] Migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
