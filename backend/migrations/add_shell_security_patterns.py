"""
Database Migration: Add Shell Security Patterns (Phase 19)
Customizable security patterns for shell command validation

Creates:
- shell_security_pattern (tenant-aware security pattern storage)

Run: python backend/migrations/add_shell_security_patterns.py
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
    backup_path = backup_dir / f"agent_backup_pre_security_patterns_{timestamp}.db"

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

    # Check if user table exists (for foreign key)
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='user'
    """)
    if not cursor.fetchone():
        raise Exception("user table not found. Database not properly initialized.")

    # Check if shell_security_pattern already exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='shell_security_pattern'
    """)
    if cursor.fetchone():
        print("[WARN] shell_security_pattern table already exists. Skipping migration.")
        return False

    print("[OK] Prerequisites check passed")
    return True


def upgrade(conn):
    """Apply migration: Create shell security pattern table."""
    cursor = conn.cursor()

    print("\n=== Upgrading Database: Shell Security Patterns ===")

    # Create shell_security_pattern table
    print("Creating shell_security_pattern table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shell_security_pattern (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id VARCHAR(50),

            -- Pattern Definition
            pattern VARCHAR(500) NOT NULL,
            pattern_type VARCHAR(20) NOT NULL,
            risk_level VARCHAR(20),
            description VARCHAR(255) NOT NULL,

            -- Categorization
            category VARCHAR(50),

            -- Flags
            is_system_default INTEGER DEFAULT 0 NOT NULL,
            is_active INTEGER DEFAULT 1 NOT NULL,

            -- Audit
            created_by INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (created_by) REFERENCES user(id),
            FOREIGN KEY (updated_by) REFERENCES user(id)
        )
    """)

    print("[OK] shell_security_pattern table created")

    # Create indexes
    print("Creating indexes...")

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_security_pattern_tenant_active
        ON shell_security_pattern(tenant_id, is_active)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_security_pattern_type
        ON shell_security_pattern(pattern_type, is_active)
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_security_pattern_unique
        ON shell_security_pattern(tenant_id, pattern)
    """)

    print("[OK] Indexes created")

    conn.commit()
    print("\n[OK] Migration completed successfully")


def verify_migration(conn):
    """Verify migration was successful."""
    cursor = conn.cursor()

    print("\n=== Verifying Migration ===")

    # Check table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='shell_security_pattern'
    """)
    if not cursor.fetchone():
        raise Exception("Table shell_security_pattern was not created")
    print("[OK] Table shell_security_pattern exists")

    # Check columns
    cursor.execute("PRAGMA table_info(shell_security_pattern)")
    columns = {row[1] for row in cursor.fetchall()}
    expected = {
        'id', 'tenant_id', 'pattern', 'pattern_type', 'risk_level',
        'description', 'category', 'is_system_default', 'is_active',
        'created_by', 'created_at', 'updated_by', 'updated_at'
    }
    missing = expected - columns
    if missing:
        raise Exception(f"Missing columns: {missing}")
    print(f"[OK] All {len(expected)} columns present")

    # Check indexes
    indexes = [
        'idx_security_pattern_tenant_active',
        'idx_security_pattern_type',
        'idx_security_pattern_unique'
    ]
    for idx in indexes:
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name=?
        """, (idx,))
        if cursor.fetchone():
            print(f"[OK] Index {idx} exists")
        else:
            print(f"[WARN] Index {idx} not found")

    # Count records
    cursor.execute("SELECT COUNT(*) FROM shell_security_pattern")
    count = cursor.fetchone()[0]
    print(f"[OK] Table shell_security_pattern: {count} records")

    print("\n[OK] Verification completed successfully")


def downgrade(conn):
    """
    Rollback migration: Remove shell security pattern table.
    """
    cursor = conn.cursor()

    print("\n=== Rolling Back Migration ===")

    # Safety check: Custom patterns exist
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM shell_security_pattern
            WHERE is_system_default = 0
        """)
        custom_count = cursor.fetchone()[0]

        if custom_count > 0:
            confirm = input(f"[WARN] {custom_count} custom patterns exist. This will delete all data. Continue? (yes/no): ")
            if confirm.lower() != 'yes':
                print("Rollback cancelled")
                return
    except sqlite3.OperationalError:
        pass  # Table doesn't exist

    # Drop indexes first
    print("Dropping indexes...")
    cursor.execute("DROP INDEX IF EXISTS idx_security_pattern_tenant_active")
    cursor.execute("DROP INDEX IF EXISTS idx_security_pattern_type")
    cursor.execute("DROP INDEX IF EXISTS idx_security_pattern_unique")

    # Drop table
    print("Dropping shell_security_pattern table...")
    cursor.execute("DROP TABLE IF EXISTS shell_security_pattern")

    conn.commit()
    print("\n[OK] Rollback completed successfully")


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Shell Security Patterns Migration (Phase 19)")
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
