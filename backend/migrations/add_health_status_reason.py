"""
Migration: Add health_status_reason column to hub_integration table

Stores the reason why an integration became unavailable (e.g., "invalid_grant",
"Token revoked by user"). This enables better debugging and user-facing error
messages when OAuth tokens expire or are revoked.

Run: python backend/migrations/add_health_status_reason.py
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_db_path():
    """Get database path based on environment"""
    if os.path.exists('/app/data/agent.db'):
        return '/app/data/agent.db'
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'agent.db')


def upgrade():
    """Add health_status_reason column to hub_integration table"""
    db_path = get_db_path()
    print(f"[Migration] Adding health_status_reason to hub_integration...")
    print(f"[Migration] Database path: {db_path}")

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found at {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hub_integration'")
        if not cursor.fetchone():
            print("[SKIP] hub_integration table does not exist yet (will be created by SQLAlchemy)")
            return True

        cursor.execute("PRAGMA table_info(hub_integration)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'health_status_reason' in columns:
            print("[SKIP] health_status_reason column already exists")
            return True

        cursor.execute("ALTER TABLE hub_integration ADD COLUMN health_status_reason VARCHAR(500)")
        print("[OK] Added health_status_reason column to hub_integration")

        conn.commit()
        print("[Migration] Complete")
        return True

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    success = upgrade()
    sys.exit(0 if success else 1)
