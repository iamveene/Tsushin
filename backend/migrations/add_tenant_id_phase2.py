"""
Migration: Add tenant_id to remaining tables for full multi-tenancy support
Phase 7.9.2: Complete Tenant Isolation

Adds tenant_id column to:
- api_key
- persona
- tone_preset
- hub_integration

This enables proper tenant isolation for API keys, personas, tone presets, and hub integrations.
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
    print(f"[Migration] Phase 7.9.2: Adding tenant_id columns to remaining tables...")
    print(f"[Migration] Database path: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Tables to add tenant_id to
    tables = [
        'api_key',
        'persona',
        'tone_preset',
        'hub_integration',
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

    # Special handling for api_key: need to drop unique constraint on 'service' and add composite index
    try:
        # SQLite doesn't support dropping indexes directly if they were created from UNIQUE constraint
        # We'll create a new composite unique index for service+tenant_id if it doesn't exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_api_key_service_tenant'")
        if not cursor.fetchone():
            # Try to create the composite unique index
            try:
                cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_api_key_service_tenant ON api_key(service, tenant_id)")
                print("[OK] Created unique composite index idx_api_key_service_tenant")
            except Exception as e:
                print(f"[WARN] Could not create composite index: {e}")
    except Exception as e:
        print(f"[WARN] Error handling api_key unique constraint: {e}")

    # Note: For existing data, we leave tenant_id as NULL
    # This means existing records are treated as "shared" or "system" resources
    # accessible to all tenants (handled by filter_by_tenant logic)
    print("[INFO] Existing records will have tenant_id=NULL (shared/system resources)")
    print("[INFO] New records created via UI will be assigned to the user's tenant")

    conn.commit()
    conn.close()
    print("[Migration] Phase 7.9.2 tenant_id migration complete")


def downgrade():
    """Remove tenant_id columns (SQLite doesn't support DROP COLUMN easily)"""
    print("[Migration] Downgrade not supported for SQLite - tenant_id columns will remain")
    print("[Migration] To remove, you would need to recreate the tables without tenant_id")


if __name__ == "__main__":
    upgrade()
