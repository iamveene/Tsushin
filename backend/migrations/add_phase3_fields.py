"""
Database migration script to add Phase 3 fields to the config table.
Run this script to update the database schema without losing existing data.
"""
import sqlite3
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def migrate_database(db_path: str):
    """Add Phase 3 fields to config table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print(f"Migrating database: {db_path}")

    # Get existing columns
    cursor.execute("PRAGMA table_info(config)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"Existing columns: {len(existing_columns)}")

    migrations = []

    # Maintenance Mode fields
    if 'maintenance_mode' not in existing_columns:
        migrations.append(("maintenance_mode", "ALTER TABLE config ADD COLUMN maintenance_mode BOOLEAN DEFAULT 0"))

    if 'maintenance_message' not in existing_columns:
        migrations.append(("maintenance_message",
                          "ALTER TABLE config ADD COLUMN maintenance_message TEXT DEFAULT '🔧 The bot is currently under maintenance. Please try again later.'"))

    # Group Message Context fields
    if 'context_message_count' not in existing_columns:
        migrations.append(("context_message_count", "ALTER TABLE config ADD COLUMN context_message_count INTEGER DEFAULT 5"))

    if 'context_char_limit' not in existing_columns:
        migrations.append(("context_char_limit", "ALTER TABLE config ADD COLUMN context_char_limit INTEGER DEFAULT 1000"))

    # Enhanced Trigger System fields
    if 'dm_auto_mode' not in existing_columns:
        migrations.append(("dm_auto_mode", "ALTER TABLE config ADD COLUMN dm_auto_mode BOOLEAN DEFAULT 0"))

    if 'agent_phone_number' not in existing_columns:
        migrations.append(("agent_phone_number", "ALTER TABLE config ADD COLUMN agent_phone_number TEXT DEFAULT '175909696979085'"))

    if 'agent_name' not in existing_columns:
        migrations.append(("agent_name", "ALTER TABLE config ADD COLUMN agent_name TEXT DEFAULT 'Assistant'"))

    if 'group_keywords' not in existing_columns:
        migrations.append(("group_keywords", "ALTER TABLE config ADD COLUMN group_keywords TEXT DEFAULT '[]'"))

    # Tool Management field
    if 'enabled_tools' not in existing_columns:
        migrations.append(("enabled_tools", 'ALTER TABLE config ADD COLUMN enabled_tools TEXT DEFAULT \'["google_search"]\''))

    # Execute migrations
    if not migrations:
        print("[OK] Database already up to date!")
        conn.close()
        return

    print(f"\n[MIGRATING] Applying {len(migrations)} migrations:")
    for field_name, sql in migrations:
        try:
            cursor.execute(sql)
            print(f"  [OK] Added column: {field_name}")
        except Exception as e:
            print(f"  [WARN] Error adding {field_name}: {e}")

    conn.commit()
    print(f"\n[OK] Migration completed successfully!")

    # Verify new columns
    cursor.execute("PRAGMA table_info(config)")
    new_columns = {row[1] for row in cursor.fetchall()}
    print(f"Total columns after migration: {len(new_columns)}")

    conn.close()

if __name__ == "__main__":
    # Get database path from arguments, environment, or use default
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = os.getenv("INTERNAL_DB_PATH", "D:\\code\\whatsbot\\backend\\data\\agent.db")

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found at: {db_path}")
        print("Usage: python add_phase3_fields.py [database_path]")
        print("Or set INTERNAL_DB_PATH environment variable")
        sys.exit(1)

    migrate_database(db_path)
