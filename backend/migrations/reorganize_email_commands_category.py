"""
Database Migration: Reorganize Email Commands Category

Moves email commands from 'tool' category to dedicated 'email' category
for better organization in /help command.

Run: python backend/migrations/reorganize_email_commands_category.py
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_database_path():
    """Get database path from environment or default."""
    return os.getenv("INTERNAL_DB_PATH", "./data/agent.db")


def upgrade(conn):
    """Move email commands to dedicated email category."""
    cursor = conn.cursor()

    print("\n=== Reorganizing Email Commands Category ===")

    # Update all email commands to use 'email' category instead of 'tool'
    cursor.execute("""
        UPDATE slash_command
        SET category = 'email'
        WHERE command_name LIKE 'email %'
        AND category = 'tool'
    """)

    rows_updated = cursor.rowcount
    conn.commit()

    print(f"[OK] Updated {rows_updated} email commands to 'email' category")

    # Verify the changes
    cursor.execute("""
        SELECT command_name, category, language_code
        FROM slash_command
        WHERE command_name LIKE 'email %'
        ORDER BY command_name, language_code
    """)

    print("\nEmail commands now:")
    for row in cursor.fetchall():
        print(f"  - {row[0]} ({row[2]}): category = {row[1]}")


def downgrade(conn):
    """Revert email commands back to tool category."""
    cursor = conn.cursor()

    print("\n=== Reverting Email Commands Category ===")

    cursor.execute("""
        UPDATE slash_command
        SET category = 'tool'
        WHERE command_name LIKE 'email %'
        AND category = 'email'
    """)

    rows_updated = cursor.rowcount
    conn.commit()

    print(f"[OK] Reverted {rows_updated} email commands back to 'tool' category")


def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Reorganize Email Commands Category")
    parser.add_argument("--downgrade", action="store_true", help="Revert to tool category")
    parser.add_argument("--db-path", help="Database path")
    args = parser.parse_args()

    db_path = args.db_path or get_database_path()

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    print(f"Using database: {db_path}")

    conn = sqlite3.connect(db_path)

    try:
        if args.downgrade:
            downgrade(conn)
        else:
            upgrade(conn)

        print("\n[SUCCESS] Migration completed!")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
