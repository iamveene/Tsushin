"""
Database Migration: Add secret_rotated_at column to api_client (BUG-SEC-010)

This migration adds the secret_rotated_at column used to invalidate existing JWTs
when an API client's secret is rotated — preventing stale tokens from remaining
valid for up to 1h after rotation.

Supports both PostgreSQL (production) and SQLite (legacy/fallback).

Run: python backend/migrations/add_api_client_secret_rotated_at.py
"""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text, inspect
import settings


def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table using SQLAlchemy inspect."""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def check_table_exists(engine, table_name):
    """Check if a table exists using SQLAlchemy inspect."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def upgrade(engine):
    """Add secret_rotated_at column to api_client table."""
    print("\n=== Upgrading Database: Add secret_rotated_at column to api_client ===")

    if not check_table_exists(engine, 'api_client'):
        print("[WARN] api_client table does not exist. Skipping migration.")
        return False

    if check_column_exists(engine, 'api_client', 'secret_rotated_at'):
        print("[OK] secret_rotated_at column already exists. Skipping.")
        return True

    print("Adding secret_rotated_at column...")
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE api_client ADD COLUMN secret_rotated_at TIMESTAMP"
        ))

    print("[OK] secret_rotated_at column added successfully")
    return True


def verify_migration(engine):
    """Verify migration was successful."""
    print("\n=== Verifying Migration ===")

    if not check_column_exists(engine, 'api_client', 'secret_rotated_at'):
        print("[ERROR] secret_rotated_at column not found in api_client")
        return False

    print("[OK] secret_rotated_at column exists in api_client")

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM api_client")).scalar()
        populated = conn.execute(
            text("SELECT COUNT(*) FROM api_client WHERE secret_rotated_at IS NOT NULL")
        ).scalar()
    print(f"[INFO] api_client rows: {total} total, {populated} with secret_rotated_at set")
    return True


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Add secret_rotated_at to api_client (BUG-SEC-010)")
    parser.add_argument("--verify-only", action="store_true", help="Only verify migration")
    args = parser.parse_args()

    db_url = settings.DATABASE_URL
    print(f"Using database: {db_url.split('@')[-1] if '@' in db_url else db_url}")

    engine = create_engine(db_url)

    try:
        if args.verify_only:
            if verify_migration(engine):
                print("\n[OK] Migration verified successfully")
            else:
                sys.exit(1)
        else:
            upgrade(engine)
            verify_migration(engine)
            print("\n[SUCCESS] Migration completed!")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
