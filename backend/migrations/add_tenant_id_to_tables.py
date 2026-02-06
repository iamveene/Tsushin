"""
Migration: Add tenant_id to tables for multi-tenancy support
Phase 7.9: Tenant Isolation

Adds tenant_id column to:
- flow_definition
- scheduled_events
- custom_tools
- custom_tool_commands
- custom_tool_parameters
- custom_tool_executions

This enables proper tenant isolation for these resources.
"""

import sqlite3
import os
from datetime import datetime


def get_db_path():
    """Get database path based on environment"""
    # Check for Docker environment
    if os.path.exists('/app/data/agent.db'):
        return '/app/data/agent.db'
    # Local development
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'agent.db')


def upgrade():
    """Add tenant_id columns to tables"""
    db_path = get_db_path()
    print(f"[Migration] Adding tenant_id columns to tables...")
    print(f"[Migration] Database path: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Tables to add tenant_id to
    tables = [
        'flow_definition',
        'scheduled_events',
        'custom_tools',
        'custom_tool_commands',
        'custom_tool_parameters',
        'custom_tool_executions',
    ]

    for table in tables:
        try:
            # Check if table exists
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if not cursor.fetchone():
                print(f"[SKIP] Table {table} does not exist")
                continue

            # Check if column already exists
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]

            if 'tenant_id' in columns:
                print(f"[SKIP] {table}.tenant_id already exists")
                continue

            # Add tenant_id column
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id VARCHAR(50)")
            print(f"[OK] Added tenant_id to {table}")

            # Create index for tenant_id
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_tenant ON {table}(tenant_id)")
            print(f"[OK] Created index idx_{table}_tenant")

        except Exception as e:
            print(f"[ERROR] Failed to modify {table}: {e}")

    # Get default tenant to assign to existing records
    cursor.execute("SELECT id FROM tenant LIMIT 1")
    default_tenant = cursor.fetchone()

    if default_tenant:
        default_tenant_id = default_tenant[0]
        print(f"[Migration] Assigning existing records to tenant: {default_tenant_id}")

        for table in tables:
            try:
                cursor.execute(f"UPDATE {table} SET tenant_id = ? WHERE tenant_id IS NULL", (default_tenant_id,))
                updated = cursor.rowcount
                if updated > 0:
                    print(f"[OK] Updated {updated} records in {table}")
            except Exception as e:
                print(f"[WARN] Could not update {table}: {e}")

    conn.commit()
    conn.close()
    print("[Migration] tenant_id migration complete")


def downgrade():
    """Remove tenant_id columns (SQLite doesn't support DROP COLUMN easily)"""
    print("[Migration] Downgrade not supported for SQLite - tenant_id columns will remain")
    print("[Migration] To remove, you would need to recreate the tables without tenant_id")


if __name__ == "__main__":
    upgrade()
