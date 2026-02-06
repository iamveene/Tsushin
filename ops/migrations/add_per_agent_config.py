"""
Migration: Add Per-Agent Configuration Columns

Adds columns to the agent table for per-agent configuration:
- memory_size: Ring buffer size per sender
- trigger_dm_enabled: Enable DM auto-response
- trigger_group_filters: Group names to monitor
- trigger_number_filters: Phone numbers to monitor
- context_message_count: Messages to fetch for context
- context_char_limit: Character limit for context

All columns are nullable (NULL = use system default from config table)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from datetime import datetime


def run_migration(db_path: str = "./data/agent.db"):
    """
    Run the migration to add per-agent configuration columns.

    Args:
        db_path: Path to the database file (relative to backend directory)
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting migration: add_per_agent_config")
    print(f"Database: {db_path}")

    # Create engine
    engine = create_engine(f'sqlite:///{db_path}')

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("PRAGMA table_info(agent)"))
        existing_columns = {row[1] for row in result.fetchall()}

        columns_to_add = [
            ("memory_size", "INTEGER"),
            ("trigger_dm_enabled", "BOOLEAN"),
            ("trigger_group_filters", "JSON"),
            ("trigger_number_filters", "JSON"),
            ("context_message_count", "INTEGER"),
            ("context_char_limit", "INTEGER"),
        ]

        added_columns = []
        skipped_columns = []

        for column_name, column_type in columns_to_add:
            if column_name in existing_columns:
                print(f"  [SKIP] Column '{column_name}' already exists, skipping")
                skipped_columns.append(column_name)
                continue

            try:
                # Add column (SQLite doesn't support multiple columns in one statement)
                sql = f"ALTER TABLE agent ADD COLUMN {column_name} {column_type}"
                conn.execute(text(sql))
                conn.commit()
                print(f"  [OK] Added column: {column_name} ({column_type})")
                added_columns.append(column_name)
            except Exception as e:
                print(f"  [ERROR] Error adding column '{column_name}': {e}")
                raise

        # Verify all columns exist
        result = conn.execute(text("PRAGMA table_info(agent)"))
        final_columns = {row[1] for row in result.fetchall()}

        print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Migration completed successfully")
        print(f"  Added: {len(added_columns)} columns")
        print(f"  Skipped: {len(skipped_columns)} columns (already exist)")

        if added_columns:
            print(f"  New columns: {', '.join(added_columns)}")

        # Show current agents and their default config state
        result = conn.execute(text("SELECT id, is_active FROM agent"))
        agents = result.fetchall()

        if agents:
            print(f"\n  Current agents ({len(agents)}):")
            for agent_id, is_active in agents:
                status = "active" if is_active else "inactive"
                print(f"    Agent {agent_id}: {status} (will use system defaults)")
        else:
            print("\n  No agents found in database")

        print(f"\n  [INFO] All agents will use system-level config until you override per-agent settings")
        print(f"  [INFO] NULL values = use system default from config table")


def rollback_migration(db_path: str = "./data/agent.db"):
    """
    Rollback the migration (SQLite doesn't support DROP COLUMN, requires table recreation).

    Args:
        db_path: Path to the database file
    """
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] WARNING: SQLite does not support DROP COLUMN")
    print("To rollback, you need to:")
    print("1. Restore from backup, OR")
    print("2. Manually recreate the agent table without the new columns")
    print("\nRecommended: Use database backup/restore instead of rollback")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Add per-agent configuration columns to agent table")
    parser.add_argument("--db", default="./data/agent.db", help="Path to database file")
    parser.add_argument("--rollback", action="store_true", help="Rollback migration (shows instructions)")

    args = parser.parse_args()

    # Change to backend directory
    backend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "backend")
    os.chdir(backend_dir)

    if args.rollback:
        rollback_migration(args.db)
    else:
        run_migration(args.db)
