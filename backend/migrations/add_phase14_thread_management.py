"""
Phase 14.1: Add Playground Thread Management Columns

Migration script to add columns to conversation_thread table for playground support.
"""

import sqlite3
import sys
import os
from datetime import datetime

def migrate_db(db_path: str):
    """
    Add Phase 14.1 columns to conversation_thread table.

    New columns:
    - tenant_id
    - user_id
    - thread_type
    - title
    - folder
    - is_archived
    - created_at
    - updated_at
    """
    print(f"🔧 Phase 14.1 Migration: Adding thread management columns to {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(conversation_thread)")
        columns = {row[1] for row in cursor.fetchall()}

        # Add tenant_id if not exists
        if "tenant_id" not in columns:
            print("  ✓ Adding tenant_id column...")
            cursor.execute("""
                ALTER TABLE conversation_thread
                ADD COLUMN tenant_id VARCHAR(50)
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_thread_tenant_id ON conversation_thread(tenant_id)")
        else:
            print("  ⊙ tenant_id column already exists")

        # Add user_id if not exists
        if "user_id" not in columns:
            print("  ✓ Adding user_id column...")
            cursor.execute("""
                ALTER TABLE conversation_thread
                ADD COLUMN user_id INTEGER
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_thread_user_id ON conversation_thread(user_id)")
        else:
            print("  ⊙ user_id column already exists")

        # Add thread_type if not exists
        if "thread_type" not in columns:
            print("  ✓ Adding thread_type column...")
            cursor.execute("""
                ALTER TABLE conversation_thread
                ADD COLUMN thread_type VARCHAR(20) DEFAULT 'flow'
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_thread_type ON conversation_thread(thread_type)")
        else:
            print("  ⊙ thread_type column already exists")

        # Add title if not exists
        if "title" not in columns:
            print("  ✓ Adding title column...")
            cursor.execute("""
                ALTER TABLE conversation_thread
                ADD COLUMN title VARCHAR(200)
            """)
        else:
            print("  ⊙ title column already exists")

        # Add folder if not exists
        if "folder" not in columns:
            print("  ✓ Adding folder column...")
            cursor.execute("""
                ALTER TABLE conversation_thread
                ADD COLUMN folder VARCHAR(100)
            """)
        else:
            print("  ⊙ folder column already exists")

        # Add is_archived if not exists
        if "is_archived" not in columns:
            print("  ✓ Adding is_archived column...")
            cursor.execute("""
                ALTER TABLE conversation_thread
                ADD COLUMN is_archived BOOLEAN DEFAULT 0
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversation_thread_archived ON conversation_thread(is_archived)")
        else:
            print("  ⊙ is_archived column already exists")

        # Add created_at if not exists (SQLite doesn't support CURRENT_TIMESTAMP in ALTER TABLE)
        if "created_at" not in columns:
            print("  ✓ Adding created_at column...")
            cursor.execute("""
                ALTER TABLE conversation_thread
                ADD COLUMN created_at TIMESTAMP
            """)
            # Set existing rows to current time
            cursor.execute("""
                UPDATE conversation_thread
                SET created_at = datetime('now')
                WHERE created_at IS NULL
            """)
        else:
            print("  ⊙ created_at column already exists")

        # Add updated_at if not exists
        if "updated_at" not in columns:
            print("  ✓ Adding updated_at column...")
            cursor.execute("""
                ALTER TABLE conversation_thread
                ADD COLUMN updated_at TIMESTAMP
            """)
            # Set existing rows to current time
            cursor.execute("""
                UPDATE conversation_thread
                SET updated_at = datetime('now')
                WHERE updated_at IS NULL
            """)
        else:
            print("  ⊙ updated_at column already exists")

        # Create composite index for playground threads
        print("  ✓ Creating composite index for playground threads...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conversation_thread_playground
            ON conversation_thread(tenant_id, user_id, agent_id, thread_type)
        """)

        # Make flow_step_run_id nullable (SQLite doesn't support ALTER COLUMN directly)
        # This is handled by the model definition - new rows can have NULL flow_step_run_id
        print("  ⊙ flow_step_run_id is now nullable (handled by model)")

        # Update existing rows to have thread_type = 'flow'
        print("  ✓ Setting thread_type='flow' for existing flow records...")
        cursor.execute("""
            UPDATE conversation_thread
            SET thread_type = 'flow'
            WHERE thread_type IS NULL OR thread_type = ''
        """)

        conn.commit()
        print("✅ Phase 14.1 migration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    # Default to backend/data/agent.db
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent.db")

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    migrate_db(db_path)
