"""
Database Migration: Add sentinel_fail_behavior column to config (BUG-LOG-020)

Adds configurable Sentinel fail behavior: "open" (allow on error) or "closed" (block on error).

Run: python backend/migrations/add_sentinel_fail_behavior.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
import settings


def check_column_exists(engine, table_name, column_name):
    inspector = inspect(engine)
    try:
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def upgrade(engine):
    print("\n=== Upgrading Database: Add sentinel_fail_behavior to config ===")

    if check_column_exists(engine, 'config', 'sentinel_fail_behavior'):
        print("[OK] sentinel_fail_behavior column already exists. Skipping.")
        return

    print("Adding sentinel_fail_behavior column...")
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE config ADD COLUMN sentinel_fail_behavior VARCHAR(10) DEFAULT 'open'")
        )
    print("[OK] sentinel_fail_behavior column added successfully")


def verify(engine):
    if not check_column_exists(engine, 'config', 'sentinel_fail_behavior'):
        print("[ERROR] sentinel_fail_behavior column not found in config")
        return False
    print("[OK] sentinel_fail_behavior column exists in config")
    return True


if __name__ == "__main__":
    engine = create_engine(settings.DATABASE_URL)
    upgrade(engine)
    verify(engine)
