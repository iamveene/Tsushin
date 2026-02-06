"""
Migration: Add encryption key fields to config table

This adds encryption key columns to the config table to enable SaaS-ready configuration:
- google_encryption_key (nullable String)
- asana_encryption_key (nullable String)

These keys were previously only stored in .env files, which prevents dynamic
per-tenant configuration in a multi-tenant SaaS environment.
"""

import sqlite3
import os
from datetime import datetime


def run_migration(db_path: str):
    """Add encryption key columns to config table if they don't exist."""
    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if config table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='config'
    """)
    if not cursor.fetchone():
        print("  ✗ Config table does not exist. Skipping migration.")
        conn.close()
        return

    # Get existing columns
    cursor.execute("PRAGMA table_info(config)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns: {existing_columns}")

    # Columns to add with their types and defaults
    columns_to_add = [
        ("google_encryption_key", "VARCHAR(500)", "NULL"),
        ("asana_encryption_key", "VARCHAR(500)", "NULL"),
    ]

    for col_name, col_type, default in columns_to_add:
        if col_name not in existing_columns:
            try:
                sql = f"ALTER TABLE config ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                print(f"Adding column: {col_name}")
                cursor.execute(sql)
                print(f"  ✓ Added {col_name}")
            except sqlite3.OperationalError as e:
                print(f"  ✗ Failed to add {col_name}: {e}")
        else:
            print(f"  - Column {col_name} already exists")

    conn.commit()
    conn.close()
    print("\n✅ Migration completed successfully!")


if __name__ == "__main__":
    # Default database path
    db_path = os.environ.get("DATABASE_PATH", "/app/data/agent.db")

    if not os.path.exists(db_path):
        # Try local path for development
        db_path = "data/agent.db"

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        print("Please provide a valid database path via DATABASE_PATH environment variable")
    else:
        run_migration(db_path)
