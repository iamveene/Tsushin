"""
Migration: Add message filtering columns to WhatsAppMCPInstance

Phase 17: Instance-Level Message Filtering
Moves WhatsApp-specific filtering from global Config to per-instance configuration.

New columns:
- group_filters (JSON): WhatsApp group names to monitor
- number_filters (JSON): Phone numbers for DM allowlist
- group_keywords (JSON): Keywords that trigger responses
- dm_auto_mode (BOOLEAN): Auto-reply to unknown DMs
"""

import sqlite3
import json
import os


def migrate():
    """Add instance-level filtering columns to whatsapp_mcp_instance table"""

    # Try to get DB path from settings first
    try:
        import settings
        db_path = settings.INTERNAL_DB_PATH
    except:
        db_path = os.environ.get("DATABASE_URL", "./data/agent.db")
        if db_path.startswith("sqlite:///"):
            db_path = db_path.replace("sqlite:///", "")

    print(f"Running migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check existing columns
        cursor.execute("PRAGMA table_info(whatsapp_mcp_instance)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        print(f"Existing columns: {existing_columns}")

        # Add new columns if they don't exist
        new_columns = [
            ("group_filters", "JSON"),
            ("number_filters", "JSON"),
            ("group_keywords", "JSON"),
            ("dm_auto_mode", "BOOLEAN DEFAULT 0"),
        ]

        for col_name, col_type in new_columns:
            if col_name not in existing_columns:
                sql = f"ALTER TABLE whatsapp_mcp_instance ADD COLUMN {col_name} {col_type}"
                print(f"Adding column: {col_name}")
                cursor.execute(sql)
            else:
                print(f"Column {col_name} already exists, skipping")

        conn.commit()
        print("Migration completed successfully!")

        # Optionally copy global config to instances (one-time migration)
        cursor.execute("SELECT group_filters, number_filters, group_keywords, dm_auto_mode FROM config WHERE id = 1")
        global_config = cursor.fetchone()

        if global_config:
            group_filters, number_filters, group_keywords, dm_auto_mode = global_config

            # Parse JSON if stored as string
            if isinstance(group_filters, str):
                group_filters = json.loads(group_filters) if group_filters else []
            if isinstance(number_filters, str):
                number_filters = json.loads(number_filters) if number_filters else []
            if isinstance(group_keywords, str):
                group_keywords = json.loads(group_keywords) if group_keywords else []

            # Check if any instances need defaults
            cursor.execute("""
                SELECT id FROM whatsapp_mcp_instance
                WHERE group_filters IS NULL AND number_filters IS NULL
            """)
            instances_to_update = cursor.fetchall()

            if instances_to_update and (group_filters or number_filters or group_keywords):
                print(f"\nCopying global config to {len(instances_to_update)} instance(s)...")
                for (instance_id,) in instances_to_update:
                    cursor.execute("""
                        UPDATE whatsapp_mcp_instance
                        SET group_filters = ?, number_filters = ?, group_keywords = ?, dm_auto_mode = ?
                        WHERE id = ?
                    """, (
                        json.dumps(group_filters) if group_filters else None,
                        json.dumps(number_filters) if number_filters else None,
                        json.dumps(group_keywords) if group_keywords else None,
                        dm_auto_mode or False,
                        instance_id
                    ))
                    print(f"  Updated instance {instance_id}")

                conn.commit()
                print("Global config copied to instances!")

    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
