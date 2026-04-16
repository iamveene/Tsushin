"""
Migration: Add Agent Avatar
Adds avatar column to agent table for visual agent identification.

Run: python -m migrations.add_agent_avatar
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text


def migrate(db_path: str):
    """Add avatar column to agent table."""

    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        try:
            print("[Migration] Adding agent avatar column...")

            result = conn.execute(text("PRAGMA table_info(agent)"))
            columns = [row[1] for row in result.fetchall()]

            if "avatar" not in columns:
                conn.execute(text(
                    "ALTER TABLE agent ADD COLUMN avatar TEXT DEFAULT NULL"
                ))
                print("[Migration] Added agent.avatar column")
            else:
                print("[Migration] agent.avatar already exists")

            conn.commit()
            print("[Migration] Agent avatar migration completed successfully!")
            return True

        except Exception as e:
            conn.rollback()
            print(f"[Migration] Error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    db_path = os.environ.get("INTERNAL_DB_PATH", "/app/data/agent.db")

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print(f"[Migration] Database: {db_path}")
    success = migrate(db_path)
    sys.exit(0 if success else 1)
