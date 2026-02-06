"""
Database Migration: Add tenant_id to MessageCache
Security Fix: HIGH-012 - Add tenant isolation to MessageCache for multi-tenant data separation

This migration:
1. Adds tenant_id column to message_cache table
2. Creates index on tenant_id for query performance
3. Backfills tenant_id from related message channel instances where possible

Run: python backend/migrations/add_message_cache_tenant_id.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from pathlib import Path


def run_migration():
    """Add tenant_id column to message_cache table and backfill where possible."""

    # Database path
    db_path = Path(__file__).parent.parent / "data" / "agent.db"
    print(f"Database path: {db_path}")
    print(f"Database exists: {db_path.exists()}")

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    engine = create_engine(f"sqlite:///{db_path}")

    # Check if message_cache table exists
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Found {len(tables)} tables in database")
    print(f"Looking for message_cache... ", end="")

    if 'message_cache' not in tables:
        print("NOT FOUND")
        print(f"Available tables (first 10): {tables[:10]}")
        print("message_cache table does not exist - nothing to migrate")
        return True

    print("FOUND")

    with engine.connect() as conn:

        # Check if tenant_id column already exists
        columns = [col['name'] for col in inspector.get_columns('message_cache')]

        if 'tenant_id' in columns:
            print("tenant_id column already exists in message_cache table")
        else:
            # Step 1: Add tenant_id column
            print("Adding tenant_id column to message_cache table...")
            conn.execute(text("""
                ALTER TABLE message_cache
                ADD COLUMN tenant_id VARCHAR(50)
            """))
            conn.commit()
            print("  - tenant_id column added")

        # Step 2: Create index if not exists
        # Check existing indexes
        indexes = inspector.get_indexes('message_cache')
        index_names = [idx['name'] for idx in indexes]

        if 'idx_message_cache_tenant' not in index_names:
            print("Creating index on tenant_id...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_message_cache_tenant
                ON message_cache(tenant_id)
            """))
            conn.commit()
            print("  - Index created")
        else:
            print("  - Index already exists")

        # Step 3: Backfill tenant_id
        # For message_cache, we cannot easily backfill from related tables
        # because chat_id doesn't directly map to instances.
        # We'll set existing records to 'default' tenant as a safe default.
        print("Backfilling tenant_id for existing records...")

        # Count records needing backfill
        result = conn.execute(text("""
            SELECT COUNT(*) FROM message_cache WHERE tenant_id IS NULL
        """))
        null_count = result.scalar()

        if null_count > 0:
            print(f"  - Found {null_count} records needing tenant_id backfill")

            # Set to 'default' tenant for existing records
            # In a real multi-tenant deployment, you may want to:
            # 1. Match by channel and attempt to correlate with instances
            # 2. Or leave NULL and filter them out
            conn.execute(text("""
                UPDATE message_cache
                SET tenant_id = 'default'
                WHERE tenant_id IS NULL
            """))
            conn.commit()

            print(f"  - Set {null_count} records to 'default' tenant")
        else:
            print("  - No records need backfill")

        # Step 4: Summary
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(tenant_id) as with_tenant,
                COUNT(DISTINCT tenant_id) as unique_tenants
            FROM message_cache
        """))
        row = result.fetchone()

        print("\nMigration Summary:")
        print(f"  - Total message_cache records: {row[0]}")
        print(f"  - Records with tenant_id: {row[1]}")
        print(f"  - Unique tenants: {row[2]}")

        return True


if __name__ == "__main__":
    print("=" * 60)
    print("HIGH-012 Migration: Add tenant_id to MessageCache")
    print("=" * 60)

    success = run_migration()

    if success:
        print("\nMigration completed successfully!")
    else:
        print("\nMigration failed!")
        sys.exit(1)
