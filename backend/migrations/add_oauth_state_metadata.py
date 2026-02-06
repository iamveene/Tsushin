"""
Migration: Add metadata_json column to oauth_state table
Security Fix: HIGH-004 - OAuth State Tokens Stored In-Memory

This enables GoogleSSOService to store additional SSO-specific data
(tenant_slug, invitation_token) in the database-backed OAuth state,
ensuring state persists across server restarts and works in multi-instance deployments.

Phase SEC-004: Security hardening - persistent OAuth state storage
"""

import sqlite3
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_db_path():
    """Get database path based on environment"""
    # Docker container path
    if os.path.exists('/app/data/agent.db'):
        return '/app/data/agent.db'
    # Local development path
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'agent.db')


def upgrade():
    """Add metadata_json column to oauth_state table"""
    db_path = get_db_path()
    print(f"[Migration] HIGH-004: Adding metadata_json to oauth_state...")
    print(f"[Migration] Database path: {db_path}")

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found at {db_path}")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if oauth_state table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='oauth_state'")
        if not cursor.fetchone():
            print("[SKIP] oauth_state table does not exist yet (will be created by SQLAlchemy)")
            return True

        # Check if column already exists
        cursor.execute("PRAGMA table_info(oauth_state)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'metadata_json' in columns:
            print("[SKIP] metadata_json column already exists")
            return True

        # Add metadata_json column (TEXT to store JSON, default empty object)
        cursor.execute("ALTER TABLE oauth_state ADD COLUMN metadata_json TEXT DEFAULT '{}'")
        print("[OK] Added metadata_json column to oauth_state")

        conn.commit()
        print("[Migration] HIGH-004 migration complete")
        return True

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def downgrade():
    """
    Remove metadata_json column.
    Note: SQLite doesn't support DROP COLUMN easily, so we just document the process.
    """
    print("[Migration] Downgrade: To remove metadata_json column, recreate oauth_state table:")
    print("""
    -- Backup existing data
    CREATE TABLE oauth_state_backup AS SELECT
        id, state_token, integration_type, tenant_id, created_at, expires_at, redirect_url
    FROM oauth_state;

    -- Drop and recreate
    DROP TABLE oauth_state;
    CREATE TABLE oauth_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        state_token VARCHAR(64) NOT NULL UNIQUE,
        integration_type VARCHAR(50) NOT NULL,
        tenant_id VARCHAR(50),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        expires_at DATETIME NOT NULL,
        redirect_url VARCHAR(500)
    );
    CREATE INDEX idx_oauth_state_token ON oauth_state(state_token);
    CREATE INDEX idx_oauth_state_expires ON oauth_state(expires_at);

    -- Restore data
    INSERT INTO oauth_state SELECT * FROM oauth_state_backup;
    DROP TABLE oauth_state_backup;
    """)


if __name__ == "__main__":
    success = upgrade()
    sys.exit(0 if success else 1)
