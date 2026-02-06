"""
Database Migration: Add Host Browser Audit Log (Phase 8)

Creates:
- host_browser_audit_log table for security audit logging

This table logs all host mode browser automation actions for:
- Security compliance and incident investigation
- Tracking actions on authenticated user sessions
- Audit trail for data protection policies

Run: python backend/migrations/add_host_browser_audit.py
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
    backup_path = backup_dir / f"agent_backup_pre_host_browser_audit_{timestamp}.db"

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

    # Check if agent table exists (required for foreign key)
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='agent'
    """)
    if not cursor.fetchone():
        raise Exception("agent table not found. Run core migrations first.")

    # Check if host_browser_audit_log already exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='host_browser_audit_log'
    """)
    if cursor.fetchone():
        print("[WARN] host_browser_audit_log table already exists. Skipping migration.")
        return "table_exists"

    print("[OK] Prerequisites check passed")
    return True


def upgrade(conn):
    """Apply migration: Create host browser audit log table."""
    cursor = conn.cursor()

    print("\n=== Creating Host Browser Audit Log Table ===")

    # Create host_browser_audit_log table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS host_browser_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,

            -- Multi-tenancy and user context
            tenant_id VARCHAR(50) NOT NULL,
            user_key VARCHAR(100) NOT NULL,
            agent_id INTEGER,

            -- Action details
            action VARCHAR(50) NOT NULL,
            url TEXT,
            target_element VARCHAR(255),

            -- MCP details
            mcp_tool VARCHAR(100) NOT NULL,
            mcp_params_hash VARCHAR(64),

            -- Execution result
            success BOOLEAN NOT NULL,
            error_message TEXT,
            duration_ms INTEGER,

            -- Security context
            session_id VARCHAR(100),
            ip_address VARCHAR(45),

            -- Foreign key
            FOREIGN KEY (agent_id) REFERENCES agent(id)
        )
    """)
    print("[OK] Created host_browser_audit_log table")

    # Create indexes for efficient querying
    indexes = [
        ("idx_host_browser_audit_timestamp", "timestamp"),
        ("idx_host_browser_audit_tenant", "tenant_id"),
        ("idx_host_browser_audit_user", "user_key"),
        ("idx_host_browser_audit_action", "action"),
    ]

    for index_name, column in indexes:
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON host_browser_audit_log ({column})
        """)
        print(f"[OK] Created index: {index_name}")

    conn.commit()
    print("\n[OK] Migration completed successfully")


def downgrade(conn):
    """Rollback migration: Drop host browser audit log table."""
    cursor = conn.cursor()

    print("\n=== Rolling back Host Browser Audit Log Migration ===")

    # Drop indexes first
    indexes = [
        "idx_host_browser_audit_timestamp",
        "idx_host_browser_audit_tenant",
        "idx_host_browser_audit_user",
        "idx_host_browser_audit_action",
    ]

    for index_name in indexes:
        cursor.execute(f"DROP INDEX IF EXISTS {index_name}")
        print(f"[OK] Dropped index: {index_name}")

    # Drop table
    cursor.execute("DROP TABLE IF EXISTS host_browser_audit_log")
    print("[OK] Dropped host_browser_audit_log table")

    conn.commit()
    print("\n[OK] Rollback completed successfully")


def main():
    """Run migration."""
    print("=" * 60)
    print("Host Browser Audit Log Migration (Phase 8)")
    print("=" * 60)

    # Get database path
    db_path = get_database_path()

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        print("Please run from the backend directory or set INTERNAL_DB_PATH")
        sys.exit(1)

    print(f"\nDatabase: {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)

    try:
        # Check if rollback requested
        if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
            downgrade(conn)
        else:
            # Check prerequisites
            result = check_prerequisites(conn)
            if result == "table_exists":
                print("\n[SKIP] Migration already applied")
                return

            # Create backup
            backup_database(db_path)

            # Run migration
            upgrade(conn)

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
