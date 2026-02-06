"""
Database Migration: Add Hub Integration System
Phase 6.x: Asana, Slack, Linear integrations

Creates:
- hub_integration (base table, polymorphic)
- asana_integration (specialized table)
- oauth_state (CSRF protection)
- oauth_token (encrypted token storage)
- Adds hub_integration_id to agent table

Run: python backend/migrations/add_hub_integration.py
"""

import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from models import Base, HubIntegration, AsanaIntegration, OAuthState, OAuthToken


def get_database_path():
    """Get database path from environment or default."""
    return os.getenv("INTERNAL_DB_PATH", "./data/agent.db")


def backup_database(db_path):
    """Create timestamped backup of database."""
    backup_dir = Path("./data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"agent_backup_pre_hub_migration_{timestamp}.db"

    print(f"Creating backup: {backup_path}")

    # Copy database file
    import shutil
    shutil.copy2(db_path, backup_path)

    print(f"[OK] Backup created: {backup_path}")
    return backup_path


def check_prerequisites(conn):
    """
    Verify database state before migration.

    Checks:
    - No active hub integrations exist (this is new feature)
    - Agent table exists
    - Required columns present
    """
    cursor = conn.cursor()

    # Check if agent table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='agent'
    """)
    if not cursor.fetchone():
        raise Exception("Agent table not found. Database may be corrupted.")

    # Check if hub tables already exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='hub_integration'
    """)
    if cursor.fetchone():
        print("[WARN]  Hub integration tables already exist. Skipping migration.")
        return False

    print("[OK] Prerequisites check passed")
    return True


def upgrade(conn):
    """Apply migration: Create hub integration tables."""
    cursor = conn.cursor()

    print("\n=== Upgrading Database ===")

    # 1. Create hub_integration table (base)
    print("Creating hub_integration table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hub_integration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type VARCHAR(50) NOT NULL,
            name VARCHAR(200) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            last_health_check DATETIME,
            health_status VARCHAR(20) DEFAULT 'unknown'
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_hub_integration_type_active
        ON hub_integration(type, is_active)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_hub_integration_health
        ON hub_integration(health_status)
    """)

    print("[OK] hub_integration table created")

    # 2. Create asana_integration table (specialized)
    print("Creating asana_integration table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asana_integration (
            id INTEGER PRIMARY KEY,
            workspace_gid VARCHAR(50) NOT NULL UNIQUE,
            workspace_name VARCHAR(200) NOT NULL,
            authorized_by_user_gid VARCHAR(50) NOT NULL,
            authorized_at DATETIME NOT NULL,
            FOREIGN KEY (id) REFERENCES hub_integration(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_asana_workspace_gid
        ON asana_integration(workspace_gid)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_asana_user_gid
        ON asana_integration(authorized_by_user_gid)
    """)

    print("[OK] asana_integration table created")

    # 3. Create oauth_state table (CSRF protection)
    print("Creating oauth_state table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oauth_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state_token VARCHAR(64) NOT NULL UNIQUE,
            integration_type VARCHAR(50) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME NOT NULL,
            redirect_url VARCHAR(500)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_oauth_state_token
        ON oauth_state(state_token)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_oauth_state_expires
        ON oauth_state(expires_at)
    """)

    print("[OK] oauth_state table created")

    # 4. Create oauth_token table
    print("Creating oauth_token table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oauth_token (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            integration_id INTEGER NOT NULL,
            access_token_encrypted TEXT NOT NULL,
            refresh_token_encrypted TEXT NOT NULL,
            token_type VARCHAR(20) NOT NULL DEFAULT 'Bearer',
            expires_at DATETIME NOT NULL,
            scope TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME,
            last_refreshed_at DATETIME,
            FOREIGN KEY (integration_id) REFERENCES hub_integration(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_oauth_token_integration
        ON oauth_token(integration_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_oauth_token_expires
        ON oauth_token(expires_at)
    """)

    print("[OK] oauth_token table created")

    # 5. Add hub_integration_id to agent table
    print("Adding hub_integration_id column to agent table...")
    try:
        cursor.execute("""
            ALTER TABLE agent
            ADD COLUMN hub_integration_id INTEGER
            REFERENCES hub_integration(id)
        """)
        print("[OK] hub_integration_id column added to agent table")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("[WARN]  hub_integration_id column already exists")
        else:
            raise

    conn.commit()
    print("\n[OK] Migration completed successfully")


def verify_migration(conn):
    """Verify migration was successful."""
    cursor = conn.cursor()

    print("\n=== Verifying Migration ===")

    # Check all tables exist
    tables = ['hub_integration', 'asana_integration', 'oauth_state', 'oauth_token']
    for table in tables:
        cursor.execute(f"""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table,))
        if not cursor.fetchone():
            raise Exception(f"Table {table} was not created")
        print(f"[OK] Table {table} exists")

    # Check agent table has hub_integration_id
    cursor.execute("PRAGMA table_info(agent)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'hub_integration_id' not in columns:
        raise Exception("hub_integration_id column not found in agent table")
    print("[OK] Agent table has hub_integration_id column")

    # Check foreign keys
    cursor.execute("PRAGMA foreign_keys")
    fk_status = cursor.fetchone()
    if fk_status and fk_status[0] == 0:
        print("[WARN]  Foreign key constraints are disabled. Enable with: PRAGMA foreign_keys = ON")
    else:
        print("[OK] Foreign key constraints enabled")

    # Count records in new tables (should be 0)
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"[OK] Table {table}: {count} records")

    print("\n[OK] Verification completed successfully")


def downgrade(conn):
    """
    Rollback migration: Remove hub integration tables.

    Safety checks:
    - Prevent downgrade if active integrations exist
    - Prevent downgrade if agents use hub integrations
    """
    cursor = conn.cursor()

    print("\n=== Rolling Back Migration ===")

    # Safety check: No active integrations
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM hub_integration
            WHERE is_active = 1
        """)
        active_count = cursor.fetchone()[0]

        if active_count > 0:
            raise Exception(
                f"Cannot downgrade: {active_count} active Hub integrations exist. "
                "Deactivate all integrations first (set is_active = 0)."
            )
    except sqlite3.OperationalError:
        # Table doesn't exist, safe to proceed
        pass

    # Safety check: No agents using integrations
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM agent
            WHERE hub_integration_id IS NOT NULL
        """)
        agent_count = cursor.fetchone()[0]

        if agent_count > 0:
            raise Exception(
                f"Cannot downgrade: {agent_count} agents have Hub integrations assigned. "
                "Remove integration assignments first (set hub_integration_id = NULL)."
            )
    except sqlite3.OperationalError:
        # Column doesn't exist, safe to proceed
        pass

    # Drop tables in reverse order (respecting foreign keys)
    print("Dropping oauth_token table...")
    cursor.execute("DROP TABLE IF EXISTS oauth_token")

    print("Dropping oauth_state table...")
    cursor.execute("DROP TABLE IF EXISTS oauth_state")

    print("Dropping asana_integration table...")
    cursor.execute("DROP TABLE IF EXISTS asana_integration")

    print("Dropping hub_integration table...")
    cursor.execute("DROP TABLE IF EXISTS hub_integration")

    # Remove hub_integration_id column from agent table
    # Note: SQLite doesn't support DROP COLUMN directly
    # We'd need to recreate the table without the column
    # For now, just set all values to NULL
    print("Clearing hub_integration_id from agent table...")
    try:
        cursor.execute("UPDATE agent SET hub_integration_id = NULL")
    except sqlite3.OperationalError:
        pass  # Column doesn't exist

    conn.commit()
    print("\n[OK] Rollback completed successfully")


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Hub Integration Migration")
    parser.add_argument("--downgrade", action="store_true", help="Rollback migration")
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
            verify_migration(conn)
            return

        if args.downgrade:
            # Downgrade
            confirm = input("[WARN]  Are you sure you want to rollback? This will delete all Hub integration data. (yes/no): ")
            if confirm.lower() != 'yes':
                print("Rollback cancelled")
                return

            downgrade(conn)
        else:
            # Upgrade
            # Check prerequisites
            if not check_prerequisites(conn):
                return

            # Create backup
            backup_path = backup_database(db_path)

            # Apply migration
            upgrade(conn)

            # Verify
            verify_migration(conn)

            print(f"\n[SUCCESS] Migration completed successfully!")
            print(f"Backup: {backup_path}")
            print(f"Database: {db_path}")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        print("\nTo restore backup:")
        print(f"  cp {backup_path} {db_path}")
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
