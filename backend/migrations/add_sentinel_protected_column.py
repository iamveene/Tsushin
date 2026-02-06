"""
Database Migration: Add sentinel_protected column to shell_integration (Phase 20)

This migration adds the missing sentinel_protected column that was added to the
ShellIntegration model but not migrated to existing databases.

Run: python backend/migrations/add_sentinel_protected_column.py
"""

import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_database_path():
    """Get database path from environment or default."""
    return os.getenv("INTERNAL_DB_PATH", "./data/agent.db")


def check_column_exists(conn, table_name, column_name):
    """Check if a column exists in a table."""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cursor.fetchall()}
    return column_name in columns


def upgrade(conn):
    """Add sentinel_protected column to shell_integration table."""
    cursor = conn.cursor()

    print("\n=== Upgrading Database: Add sentinel_protected column ===")

    # Check if column already exists
    if check_column_exists(conn, 'shell_integration', 'sentinel_protected'):
        print("[OK] sentinel_protected column already exists. Skipping.")
        return True

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='shell_integration'
    """)
    if not cursor.fetchone():
        print("[WARN] shell_integration table does not exist. Skipping migration.")
        return False

    # Add the column with default value
    print("Adding sentinel_protected column...")
    cursor.execute("""
        ALTER TABLE shell_integration
        ADD COLUMN sentinel_protected INTEGER NOT NULL DEFAULT 1
    """)

    conn.commit()
    print("[OK] sentinel_protected column added successfully")
    return True


def upgrade_from_engine(engine):
    """
    Run migration using SQLAlchemy engine.
    Called from init_database in db.py.
    """
    db_path = engine.url.database
    if not db_path or not os.path.exists(db_path):
        print(f"[WARN] Database not found for migration: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        upgrade(conn)
    finally:
        conn.close()


def verify_migration(conn):
    """Verify migration was successful."""
    print("\n=== Verifying Migration ===")

    if check_column_exists(conn, 'shell_integration', 'sentinel_protected'):
        print("[OK] sentinel_protected column exists")

        # Check default value
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sentinel_protected FROM shell_integration LIMIT 1
        """)
        row = cursor.fetchone()
        if row:
            print(f"[OK] Existing records have sentinel_protected = {row[0]}")
        else:
            print("[INFO] No existing shell_integration records")

        return True
    else:
        print("[ERROR] sentinel_protected column not found")
        return False


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Add sentinel_protected column (Phase 20)")
    parser.add_argument("--verify-only", action="store_true", help="Only verify migration")
    parser.add_argument("--db-path", help="Database path (default: from env or ./data/agent.db)")
    args = parser.parse_args()

    # Get database path
    db_path = args.db_path or get_database_path()

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    print(f"Using database: {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)

    try:
        if args.verify_only:
            if verify_migration(conn):
                print("\n[OK] Migration verified successfully")
            else:
                sys.exit(1)
        else:
            upgrade(conn)
            verify_migration(conn)
            print("\n[SUCCESS] Migration completed!")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
