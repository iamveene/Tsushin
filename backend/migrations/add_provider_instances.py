"""
Database Migration: Add Provider Instance Tables
Phase 21: OpenAI URL Rebase & Multi-Instance Providers

Creates:
- provider_instance (per-tenant LLM provider endpoints)
- provider_url_policy (URL allowlist/blocklist)
- provider_connection_audit (connection event log)
- Adds provider_instance_id FK to agent table

Run: python backend/migrations/add_provider_instances.py
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


def backup_database(db_path):
    """Create timestamped backup of database."""
    backup_dir = Path("./data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"agent_backup_pre_provider_instances_{timestamp}.db"

    print(f"Creating backup: {backup_path}")

    import shutil
    shutil.copy2(db_path, backup_path)

    print(f"[OK] Backup created: {backup_path}")
    return backup_path


def check_prerequisites(conn):
    """
    Verify database state before migration.

    Checks:
    - Agent table exists
    - Reports if provider tables already exist
    """
    cursor = conn.cursor()

    # Check if agent table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='agent'
    """)
    if not cursor.fetchone():
        raise Exception("Agent table not found. Database may be corrupted.")

    # Check if provider tables already exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='provider_instance'
    """)
    if cursor.fetchone():
        print("[WARN]  Provider instance tables already exist. Checking for missing pieces...")
        return True  # Continue to handle partial migrations

    print("[OK] Prerequisites check passed")
    return True


def upgrade(conn):
    """Apply migration: Create provider instance tables."""
    cursor = conn.cursor()

    print("\n=== Upgrading Database ===")

    # 1. Create provider_instance table
    print("Creating provider_instance table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS provider_instance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id VARCHAR(50) NOT NULL,
            vendor VARCHAR(30) NOT NULL,
            instance_name VARCHAR(100) NOT NULL,
            base_url VARCHAR(500),
            api_key_encrypted TEXT,
            available_models JSON DEFAULT '[]',
            is_default BOOLEAN NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            health_status VARCHAR(20) DEFAULT 'unknown',
            health_status_reason VARCHAR(500),
            last_health_check DATETIME,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_provider_instance_tenant_id
        ON provider_instance(tenant_id)
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_instance_tenant_name
        ON provider_instance(tenant_id, instance_name)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_pi_tenant_vendor
        ON provider_instance(tenant_id, vendor)
    """)

    print("[OK] provider_instance table created")

    # 2. Create provider_url_policy table
    print("Creating provider_url_policy table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS provider_url_policy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope VARCHAR(10) NOT NULL,
            tenant_id VARCHAR(50),
            policy_type VARCHAR(10) NOT NULL,
            url_pattern VARCHAR(500) NOT NULL,
            description VARCHAR(255),
            created_by INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("[OK] provider_url_policy table created")

    # 3. Create provider_connection_audit table
    print("Creating provider_connection_audit table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS provider_connection_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id VARCHAR(50) NOT NULL,
            user_id INTEGER,
            provider_instance_id INTEGER NOT NULL,
            action VARCHAR(30) NOT NULL,
            resolved_ip VARCHAR(45),
            base_url VARCHAR(500),
            success BOOLEAN NOT NULL,
            error_message TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("[OK] provider_connection_audit table created")

    # 4. Add provider_instance_id to agent table
    print("Adding provider_instance_id column to agent table...")
    cursor.execute("PRAGMA table_info(agent)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'provider_instance_id' not in columns:
        try:
            cursor.execute("""
                ALTER TABLE agent
                ADD COLUMN provider_instance_id INTEGER
                REFERENCES provider_instance(id) ON DELETE SET NULL
            """)
            print("[OK] provider_instance_id column added to agent table")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("[WARN]  provider_instance_id column already exists")
            else:
                raise
    else:
        print("[WARN]  provider_instance_id column already exists in agent table")

    conn.commit()
    print("\n[OK] Migration completed successfully")


def verify_migration(conn):
    """Verify migration was successful."""
    cursor = conn.cursor()

    print("\n=== Verifying Migration ===")

    # Check all tables exist
    tables = ['provider_instance', 'provider_url_policy', 'provider_connection_audit']
    for table in tables:
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table,))
        if not cursor.fetchone():
            raise Exception(f"Table {table} was not created")
        print(f"[OK] Table {table} exists")

    # Check agent table has provider_instance_id
    cursor.execute("PRAGMA table_info(agent)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'provider_instance_id' not in columns:
        raise Exception("provider_instance_id column not found in agent table")
    print("[OK] Agent table has provider_instance_id column")

    # Check indexes exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name='uq_provider_instance_tenant_name'
    """)
    if cursor.fetchone():
        print("[OK] Unique index uq_provider_instance_tenant_name exists")
    else:
        print("[WARN]  Unique index uq_provider_instance_tenant_name missing")

    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index' AND name='idx_pi_tenant_vendor'
    """)
    if cursor.fetchone():
        print("[OK] Index idx_pi_tenant_vendor exists")
    else:
        print("[WARN]  Index idx_pi_tenant_vendor missing")

    # Count records in new tables (should be 0)
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"[OK] Table {table}: {count} records")

    print("\n[OK] Verification completed successfully")


def downgrade(conn):
    """
    Rollback migration: Remove provider instance tables.

    Safety checks:
    - Prevent downgrade if active provider instances exist
    - Prevent downgrade if agents reference provider instances
    """
    cursor = conn.cursor()

    print("\n=== Rolling Back Migration ===")

    # Safety check: No active provider instances
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM provider_instance
            WHERE is_active = 1
        """)
        active_count = cursor.fetchone()[0]

        if active_count > 0:
            raise Exception(
                f"Cannot downgrade: {active_count} active provider instances exist. "
                "Deactivate all instances first (set is_active = 0)."
            )
    except sqlite3.OperationalError:
        pass  # Table doesn't exist, safe to proceed

    # Safety check: No agents using provider instances
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM agent
            WHERE provider_instance_id IS NOT NULL
        """)
        agent_count = cursor.fetchone()[0]

        if agent_count > 0:
            raise Exception(
                f"Cannot downgrade: {agent_count} agents have provider instances assigned. "
                "Remove provider instance assignments first (set provider_instance_id = NULL)."
            )
    except sqlite3.OperationalError:
        pass  # Column doesn't exist, safe to proceed

    # Drop tables in reverse order
    print("Dropping provider_connection_audit table...")
    cursor.execute("DROP TABLE IF EXISTS provider_connection_audit")

    print("Dropping provider_url_policy table...")
    cursor.execute("DROP TABLE IF EXISTS provider_url_policy")

    print("Dropping provider_instance table...")
    cursor.execute("DROP TABLE IF EXISTS provider_instance")

    # Clear provider_instance_id from agent table
    # Note: SQLite doesn't support DROP COLUMN in older versions
    print("Clearing provider_instance_id from agent table...")
    try:
        cursor.execute("UPDATE agent SET provider_instance_id = NULL")
    except sqlite3.OperationalError:
        pass  # Column doesn't exist

    conn.commit()
    print("\n[OK] Rollback completed successfully")


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Provider Instances Migration")
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
            confirm = input("[WARN]  Are you sure you want to rollback? This will delete all provider instance data. (yes/no): ")
            if confirm.lower() != 'yes':
                print("Rollback cancelled")
                return

            downgrade(conn)
        else:
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
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
