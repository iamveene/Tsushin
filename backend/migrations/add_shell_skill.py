"""
Database Migration: Add Shell Skill (Phase 18)
Remote Command Execution via C2 Architecture

Creates:
- shell_integration (specialized table, FK to hub_integration)
- shell_command (command queue with full audit trail)

Run: python backend/migrations/add_shell_skill.py
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
    backup_path = backup_dir / f"agent_backup_pre_shell_skill_{timestamp}.db"

    print(f"Creating backup: {backup_path}")

    import shutil
    shutil.copy2(db_path, backup_path)

    print(f"[OK] Backup created: {backup_path}")
    return backup_path


def check_prerequisites(conn):
    """
    Verify database state before migration.
    """
    cursor = conn.cursor()

    # Check if hub_integration table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='hub_integration'
    """)
    if not cursor.fetchone():
        raise Exception("hub_integration table not found. Run add_hub_integration.py first.")

    # Check if shell_integration already exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='shell_integration'
    """)
    if cursor.fetchone():
        print("[WARN] Shell integration tables already exist. Skipping migration.")
        return False

    print("[OK] Prerequisites check passed")
    return True


def upgrade(conn):
    """Apply migration: Create shell skill tables."""
    cursor = conn.cursor()

    print("\n=== Upgrading Database: Shell Skill ===")

    # 1. Create shell_integration table (polymorphic child of hub_integration)
    print("Creating shell_integration table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shell_integration (
            id INTEGER PRIMARY KEY,

            -- Authentication (SHA-256 hash of API key)
            api_key_hash VARCHAR(128) NOT NULL,

            -- C2 Configuration
            poll_interval INTEGER DEFAULT 5,
            mode VARCHAR(20) DEFAULT 'beacon',

            -- Security Controls
            allowed_commands JSON DEFAULT '[]',
            allowed_paths JSON DEFAULT '[]',

            -- Host Identification
            hostname VARCHAR(255),
            remote_ip VARCHAR(45),

            -- Registration
            registration_token_hash VARCHAR(128),
            registered_at DATETIME,

            -- Status
            os_info JSON,
            last_checkin DATETIME,

            -- Result retention (NULL = keep forever)
            retention_days INTEGER,

            -- Security: YOLO mode auto-approves high-risk commands (CRIT-005)
            yolo_mode INTEGER DEFAULT 0 NOT NULL,

            FOREIGN KEY (id) REFERENCES hub_integration(id) ON DELETE CASCADE
        )
    """)

    # Create indexes for shell_integration
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_shell_hostname
        ON shell_integration(hostname)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_shell_last_checkin
        ON shell_integration(last_checkin)
    """)

    print("[OK] shell_integration table created")

    # 2. Create shell_command table
    print("Creating shell_command table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shell_command (
            id VARCHAR(36) PRIMARY KEY,
            shell_id INTEGER NOT NULL,
            tenant_id VARCHAR(50) NOT NULL,

            -- Request Details
            commands JSON NOT NULL,
            initiated_by VARCHAR(100) NOT NULL,
            executed_by_agent_id INTEGER,

            -- Status Tracking
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            queued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sent_at DATETIME,
            completed_at DATETIME,

            -- Timeout
            timeout_seconds INTEGER DEFAULT 300,

            -- Approval Workflow (Phase 5 prep)
            approval_required BOOLEAN DEFAULT 0,
            approved_by_user_id INTEGER,
            approved_at DATETIME,
            rejection_reason TEXT,

            -- Execution Results
            exit_code INTEGER,
            stdout TEXT,
            stderr TEXT,
            execution_time_ms INTEGER,
            full_result_json JSON,
            final_working_dir VARCHAR(500),
            error_message TEXT,

            -- Timestamps
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (shell_id) REFERENCES shell_integration(id) ON DELETE CASCADE,
            FOREIGN KEY (executed_by_agent_id) REFERENCES agent(id)
        )
    """)

    # Create indexes for shell_command
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_shell_command_status
        ON shell_command(status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_shell_command_shell_status
        ON shell_command(shell_id, status)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_shell_command_tenant
        ON shell_command(tenant_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_shell_command_queued
        ON shell_command(queued_at)
    """)

    print("[OK] shell_command table created")

    conn.commit()
    print("\n[OK] Migration completed successfully")


def verify_migration(conn):
    """Verify migration was successful."""
    cursor = conn.cursor()

    print("\n=== Verifying Migration ===")

    # Check tables exist
    tables = ['shell_integration', 'shell_command']
    for table in tables:
        cursor.execute(f"""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table,))
        if not cursor.fetchone():
            raise Exception(f"Table {table} was not created")
        print(f"[OK] Table {table} exists")

    # Check indexes exist
    indexes = [
        'idx_shell_hostname',
        'idx_shell_last_checkin',
        'idx_shell_command_status',
        'idx_shell_command_shell_status',
        'idx_shell_command_tenant',
        'idx_shell_command_queued'
    ]
    for idx in indexes:
        cursor.execute(f"""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name=?
        """, (idx,))
        if cursor.fetchone():
            print(f"[OK] Index {idx} exists")
        else:
            print(f"[WARN] Index {idx} not found")

    # Count records
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"[OK] Table {table}: {count} records")

    print("\n[OK] Verification completed successfully")


def downgrade(conn):
    """
    Rollback migration: Remove shell skill tables.
    """
    cursor = conn.cursor()

    print("\n=== Rolling Back Migration ===")

    # Safety check: No active shell integrations
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM shell_integration
        """)
        count = cursor.fetchone()[0]

        if count > 0:
            confirm = input(f"[WARN] {count} shell integrations exist. This will delete all data. Continue? (yes/no): ")
            if confirm.lower() != 'yes':
                print("Rollback cancelled")
                return
    except sqlite3.OperationalError:
        pass  # Table doesn't exist

    # Drop tables in order (respecting foreign keys)
    print("Dropping shell_command table...")
    cursor.execute("DROP TABLE IF EXISTS shell_command")

    print("Dropping shell_integration table...")
    cursor.execute("DROP TABLE IF EXISTS shell_integration")

    # Also remove any hub_integration entries with type='shell'
    print("Removing shell type entries from hub_integration...")
    try:
        cursor.execute("DELETE FROM hub_integration WHERE type = 'shell'")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    print("\n[OK] Rollback completed successfully")


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Shell Skill Migration (Phase 18)")
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
            downgrade(conn)
        else:
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
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
