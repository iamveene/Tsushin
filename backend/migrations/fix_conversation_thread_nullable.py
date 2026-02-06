"""
Fix conversation_thread table to make flow_step_run_id nullable for playground support.
SQLite doesn't support ALTER COLUMN, so we need to recreate the table.
"""

import sqlite3
import sys
import os

def migrate_db(db_path: str):
    """Make flow_step_run_id nullable in conversation_thread table."""

    print(f"🔧 Fixing conversation_thread.flow_step_run_id constraint in {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: Create new table with nullable flow_step_run_id
        print("  1. Creating new table schema...")
        cursor.execute("""
            CREATE TABLE conversation_thread_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                flow_step_run_id INTEGER,  -- Made nullable
                status VARCHAR(20),
                current_turn INTEGER,
                max_turns INTEGER,
                recipient VARCHAR(100) NOT NULL,
                agent_id INTEGER NOT NULL,
                persona_id INTEGER,
                objective TEXT,
                conversation_history JSON,
                context_data JSON,
                goal_achieved BOOLEAN,
                goal_summary TEXT,
                started_at DATETIME,
                last_activity_at DATETIME,
                completed_at DATETIME,
                timeout_at DATETIME,
                tenant_id VARCHAR(50),
                user_id INTEGER,
                thread_type VARCHAR(20) DEFAULT 'flow',
                title VARCHAR(200),
                folder VARCHAR(100),
                is_archived BOOLEAN DEFAULT 0,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                FOREIGN KEY(flow_step_run_id) REFERENCES flow_node_run (id)
            )
        """)

        # Step 2: Copy data from old table
        print("  2. Copying existing data...")
        cursor.execute("""
            INSERT INTO conversation_thread_new
            SELECT * FROM conversation_thread
        """)

        # Step 3: Drop old table
        print("  3. Dropping old table...")
        cursor.execute("DROP TABLE conversation_thread")

        # Step 4: Rename new table
        print("  4. Renaming new table...")
        cursor.execute("ALTER TABLE conversation_thread_new RENAME TO conversation_thread")

        # Step 5: Recreate indexes
        print("  5. Recreating indexes...")
        cursor.execute("CREATE INDEX idx_conversation_thread_status ON conversation_thread (status)")
        cursor.execute("CREATE INDEX idx_conversation_thread_active ON conversation_thread (status, recipient)")
        cursor.execute("CREATE INDEX idx_conversation_thread_recipient ON conversation_thread (recipient)")
        cursor.execute("CREATE INDEX idx_conversation_thread_tenant_id ON conversation_thread(tenant_id)")
        cursor.execute("CREATE INDEX idx_conversation_thread_user_id ON conversation_thread(user_id)")
        cursor.execute("CREATE INDEX idx_conversation_thread_type ON conversation_thread(thread_type)")
        cursor.execute("CREATE INDEX idx_conversation_thread_archived ON conversation_thread(is_archived)")
        cursor.execute("""
            CREATE INDEX idx_conversation_thread_playground
            ON conversation_thread(tenant_id, user_id, agent_id, thread_type)
        """)
        cursor.execute("CREATE INDEX ix_conversation_thread_flow_step_run_id ON conversation_thread (flow_step_run_id)")

        conn.commit()
        print("✅ Migration completed successfully! flow_step_run_id is now nullable.")

    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent.db")

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    migrate_db(db_path)
