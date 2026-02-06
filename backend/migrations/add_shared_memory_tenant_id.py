"""
Database Migration: Add tenant_id to SharedMemory
Security Fix: CRIT-010 - Add authentication and tenant isolation to shared memory API

This migration:
1. Adds tenant_id column to shared_memory table
2. Creates index on tenant_id for query performance
3. Backfills tenant_id from Agent.tenant_id via shared_by_agent foreign key

Run: python backend/migrations/add_shared_memory_tenant_id.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from pathlib import Path


def run_migration():
    """Add tenant_id column to shared_memory table and backfill from agent relationship."""

    # Database path
    db_path = Path(__file__).parent.parent / "data" / "tsushin.db"

    if not db_path.exists():
        print(f"Database not found at {db_path}")
        return False

    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        # Check if shared_memory table exists
        inspector = inspect(engine)
        if 'shared_memory' not in inspector.get_table_names():
            print("shared_memory table does not exist - nothing to migrate")
            return True

        # Check if tenant_id column already exists
        columns = [col['name'] for col in inspector.get_columns('shared_memory')]

        if 'tenant_id' in columns:
            print("tenant_id column already exists in shared_memory table")
        else:
            # Step 1: Add tenant_id column
            print("Adding tenant_id column to shared_memory table...")
            conn.execute(text("""
                ALTER TABLE shared_memory
                ADD COLUMN tenant_id VARCHAR(50)
            """))
            conn.commit()
            print("  - tenant_id column added")

        # Step 2: Create index if not exists
        # Check existing indexes
        indexes = inspector.get_indexes('shared_memory')
        index_names = [idx['name'] for idx in indexes]

        if 'idx_shared_memory_tenant' not in index_names:
            print("Creating index on tenant_id...")
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_shared_memory_tenant
                ON shared_memory(tenant_id)
            """))
            conn.commit()
            print("  - Index created")
        else:
            print("  - Index already exists")

        # Step 3: Backfill tenant_id from Agent.tenant_id
        print("Backfilling tenant_id from Agent relationship...")

        # Count records needing backfill
        result = conn.execute(text("""
            SELECT COUNT(*) FROM shared_memory WHERE tenant_id IS NULL
        """))
        null_count = result.scalar()

        if null_count > 0:
            print(f"  - Found {null_count} records needing tenant_id backfill")

            # Backfill from agent table
            conn.execute(text("""
                UPDATE shared_memory
                SET tenant_id = (
                    SELECT a.tenant_id
                    FROM agent a
                    WHERE a.id = shared_memory.shared_by_agent
                )
                WHERE tenant_id IS NULL
            """))
            conn.commit()

            # Verify backfill
            result = conn.execute(text("""
                SELECT COUNT(*) FROM shared_memory WHERE tenant_id IS NULL
            """))
            remaining_null = result.scalar()

            if remaining_null > 0:
                print(f"  - WARNING: {remaining_null} records still have NULL tenant_id")
                print("    (These may reference deleted agents)")
            else:
                print(f"  - Successfully backfilled {null_count} records")
        else:
            print("  - No records need backfill")

        # Step 4: Summary
        result = conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(tenant_id) as with_tenant,
                COUNT(DISTINCT tenant_id) as unique_tenants
            FROM shared_memory
        """))
        row = result.fetchone()

        print("\nMigration Summary:")
        print(f"  - Total shared_memory records: {row[0]}")
        print(f"  - Records with tenant_id: {row[1]}")
        print(f"  - Unique tenants: {row[2]}")

        return True


if __name__ == "__main__":
    print("=" * 60)
    print("CRIT-010 Migration: Add tenant_id to SharedMemory")
    print("=" * 60)

    success = run_migration()

    if success:
        print("\nMigration completed successfully!")
    else:
        print("\nMigration failed!")
        sys.exit(1)
