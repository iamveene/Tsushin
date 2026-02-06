"""
Migration: Add Phase 8.0 columns to flow_definition table

This adds the new columns needed for the unified flow architecture:
- execution_method
- scheduled_at
- recurrence_rule
- default_agent_id
- flow_type
- last_executed_at
- next_execution_at
- execution_count
"""

import sqlite3
import os
from datetime import datetime


def run_migration(db_path: str):
    """Add Phase 8.0 columns to flow_definition if they don't exist."""
    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(flow_definition)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns: {existing_columns}")

    # Columns to add with their types and defaults
    columns_to_add = [
        ("execution_method", "VARCHAR(20)", "'immediate'"),
        ("scheduled_at", "DATETIME", "NULL"),
        ("recurrence_rule", "TEXT", "NULL"),
        ("default_agent_id", "INTEGER", "NULL"),
        ("flow_type", "VARCHAR(20)", "'workflow'"),
        ("last_executed_at", "DATETIME", "NULL"),
        ("next_execution_at", "DATETIME", "NULL"),
        ("execution_count", "INTEGER", "0"),
        ("initiator_type", "VARCHAR(20)", "'programmatic'"),
        ("initiator_metadata", "TEXT", "'{}'"),
    ]

    for col_name, col_type, default in columns_to_add:
        if col_name not in existing_columns:
            try:
                sql = f"ALTER TABLE flow_definition ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                print(f"Adding column: {col_name}")
                cursor.execute(sql)
                print(f"  ✓ Added {col_name}")
            except sqlite3.OperationalError as e:
                print(f"  ✗ Failed to add {col_name}: {e}")
        else:
            print(f"  - Column {col_name} already exists")

    # Also add new columns to FlowNode table for Phase 8.0
    cursor.execute("PRAGMA table_info(flow_node)")
    existing_node_columns = [row[1] for row in cursor.fetchall()]
    print(f"\nExisting flow_node columns: {existing_node_columns}")

    node_columns_to_add = [
        ("name", "VARCHAR(200)", "NULL"),
        ("step_description", "TEXT", "NULL"),
        ("timeout_seconds", "INTEGER", "300"),
        ("retry_on_failure", "BOOLEAN", "0"),
        ("max_retries", "INTEGER", "0"),
        ("retry_delay_seconds", "INTEGER", "60"),
        ("condition", "TEXT", "NULL"),
        ("on_success", "VARCHAR(20)", "NULL"),
        ("on_failure", "VARCHAR(20)", "NULL"),
        ("allow_multi_turn", "BOOLEAN", "0"),
        ("max_turns", "INTEGER", "20"),
        ("conversation_objective", "TEXT", "NULL"),
        ("agent_id", "INTEGER", "NULL"),
        ("persona_id", "INTEGER", "NULL"),
    ]

    for col_name, col_type, default in node_columns_to_add:
        if col_name not in existing_node_columns:
            try:
                sql = f"ALTER TABLE flow_node ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                print(f"Adding column to flow_node: {col_name}")
                cursor.execute(sql)
                print(f"  ✓ Added {col_name}")
            except sqlite3.OperationalError as e:
                print(f"  ✗ Failed to add {col_name}: {e}")
        else:
            print(f"  - Column {col_name} already exists")

    # Create ConversationThread table if it doesn't exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='conversation_thread'
    """)
    if not cursor.fetchone():
        print("\nCreating conversation_thread table...")
        cursor.execute("""
            CREATE TABLE conversation_thread (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50),
                flow_run_id INTEGER,
                flow_step_run_id INTEGER,
                status VARCHAR(20) DEFAULT 'active',
                current_turn INTEGER DEFAULT 0,
                max_turns INTEGER DEFAULT 20,
                recipient VARCHAR(100) NOT NULL,
                agent_id INTEGER NOT NULL,
                persona_id INTEGER,
                objective TEXT,
                conversation_history TEXT DEFAULT '[]',
                context_data TEXT DEFAULT '{}',
                goal_achieved BOOLEAN DEFAULT 0,
                goal_summary TEXT,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_activity_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                timeout_at DATETIME
            )
        """)
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_thread_recipient ON conversation_thread(recipient)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_thread_status ON conversation_thread(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_thread_agent ON conversation_thread(agent_id)")
        print("  ✓ Created conversation_thread table")
    else:
        print("\n  - conversation_thread table already exists")

    # Add new columns to FlowRun table
    cursor.execute("PRAGMA table_info(flow_run)")
    existing_run_columns = [row[1] for row in cursor.fetchall()]
    print(f"\nExisting flow_run columns: {existing_run_columns}")

    run_columns_to_add = [
        ("tenant_id", "VARCHAR(50)", "NULL"),
        ("trigger_type", "VARCHAR(50)", "'manual'"),
        ("triggered_by", "VARCHAR(100)", "NULL"),
        ("total_steps", "INTEGER", "0"),
        ("completed_steps", "INTEGER", "0"),
        ("failed_steps", "INTEGER", "0"),
    ]

    for col_name, col_type, default in run_columns_to_add:
        if col_name not in existing_run_columns:
            try:
                sql = f"ALTER TABLE flow_run ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                print(f"Adding column to flow_run: {col_name}")
                cursor.execute(sql)
                print(f"  ✓ Added {col_name}")
            except sqlite3.OperationalError as e:
                print(f"  ✗ Failed to add {col_name}: {e}")
        else:
            print(f"  - Column {col_name} already exists")

    # Add new columns to FlowNodeRun table
    cursor.execute("PRAGMA table_info(flow_node_run)")
    existing_node_run_columns = [row[1] for row in cursor.fetchall()]
    print(f"\nExisting flow_node_run columns: {existing_node_run_columns}")

    node_run_columns_to_add = [
        ("retry_count", "INTEGER", "0"),
        ("execution_time_ms", "INTEGER", "NULL"),
        ("token_usage_json", "TEXT", "'{}'"),
        ("tool_used", "VARCHAR(100)", "NULL"),
        ("idempotency_key", "VARCHAR(100)", "NULL"),
    ]

    for col_name, col_type, default in node_run_columns_to_add:
        if col_name not in existing_node_run_columns:
            try:
                sql = f"ALTER TABLE flow_node_run ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                print(f"Adding column to flow_node_run: {col_name}")
                cursor.execute(sql)
                print(f"  ✓ Added {col_name}")
            except sqlite3.OperationalError as e:
                print(f"  ✗ Failed to add {col_name}: {e}")
        else:
            print(f"  - Column {col_name} already exists")

    conn.commit()
    conn.close()
    print("\n✓ Migration completed successfully!")


if __name__ == "__main__":
    # Default database path
    db_path = os.environ.get("DATABASE_PATH", "/app/data/tsushin.db")

    # Also try local path for development
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "tsushin.db")

    if os.path.exists(db_path):
        run_migration(db_path)
    else:
        print(f"Database not found at: {db_path}")
        print("Please provide a valid database path via DATABASE_PATH environment variable")
