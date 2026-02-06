"""
Add whatsapp_conversation_delay_seconds column to config table
Phase 18: Global WhatsApp conversation debounce configuration
"""

def upgrade(db_path: str):
    """Add whatsapp_conversation_delay_seconds column to config table"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            ALTER TABLE config
            ADD COLUMN whatsapp_conversation_delay_seconds REAL DEFAULT 5.0
        """)

        conn.commit()
        print("✅ Added whatsapp_conversation_delay_seconds column to config table")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("⚠️  whatsapp_conversation_delay_seconds column already exists, skipping")
        else:
            raise
    finally:
        conn.close()


def downgrade(db_path: str):
    """Remove whatsapp_conversation_delay_seconds column (SQLite doesn't support DROP COLUMN easily)"""
    print("⚠️  Downgrade not supported for SQLite ALTER TABLE DROP COLUMN")
    print("   Manual intervention required if rollback needed")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        upgrade(db_path)
    else:
        print("Usage: python add_whatsapp_conversation_delay_config.py <db_path>")
