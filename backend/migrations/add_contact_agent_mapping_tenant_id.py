"""
Database Migration: Add tenant_id column to contact_agent_mapping (BUG-LOG-012)

Adds tenant_id to ContactAgentMapping for cross-tenant isolation.
Backfills from the agent's tenant_id for existing records.

Supports both PostgreSQL (production) and SQLite (legacy/fallback).

Run: python backend/migrations/add_contact_agent_mapping_tenant_id.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
import settings


def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table using SQLAlchemy inspect."""
    inspector = inspect(engine)
    try:
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def upgrade(engine):
    """Add tenant_id column to contact_agent_mapping and backfill."""
    print("\n=== Upgrading Database: Add tenant_id to contact_agent_mapping ===")

    if not inspect(engine).has_table("contact_agent_mapping"):
        print("[SKIP] contact_agent_mapping table does not exist yet.")
        return

    if check_column_exists(engine, 'contact_agent_mapping', 'tenant_id'):
        print("[OK] tenant_id column already exists. Skipping.")
        return

    print("Adding tenant_id column...")
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE contact_agent_mapping ADD COLUMN tenant_id VARCHAR(100)")
        )

    # Backfill from agent's tenant_id
    print("Backfilling tenant_id from agent table...")
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE contact_agent_mapping
            SET tenant_id = (
                SELECT agent.tenant_id FROM agent WHERE agent.id = contact_agent_mapping.agent_id
            )
            WHERE tenant_id IS NULL
        """))

    # Create index
    print("Creating index on tenant_id...")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_contact_agent_mapping_tenant_id "
            "ON contact_agent_mapping (tenant_id)"
        ))

    print("[OK] tenant_id column added and backfilled successfully")


def verify(engine):
    """Verify the migration."""
    if not check_column_exists(engine, 'contact_agent_mapping', 'tenant_id'):
        print("[ERROR] tenant_id column not found in contact_agent_mapping")
        return False

    print("[OK] tenant_id column exists in contact_agent_mapping")
    with engine.begin() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM contact_agent_mapping")).scalar()
        populated = conn.execute(
            text("SELECT COUNT(*) FROM contact_agent_mapping WHERE tenant_id IS NOT NULL")
        ).scalar()
    print(f"[INFO] contact_agent_mapping rows: {total} total, {populated} with tenant_id set")
    return True


if __name__ == "__main__":
    engine = create_engine(settings.DATABASE_URL)
    upgrade(engine)
    verify(engine)
