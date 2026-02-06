"""
Migration: Add ai_summary column to persona table
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
import settings

def migrate():
    engine = create_engine(f"sqlite:///{settings.INTERNAL_DB_PATH}")

    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("PRAGMA table_info(persona)"))
        columns = [row[1] for row in result]

        if 'ai_summary' not in columns:
            print("Adding ai_summary column to persona table...")
            conn.execute(text("ALTER TABLE persona ADD COLUMN ai_summary TEXT"))
            conn.commit()
            print("✅ Migration completed successfully")
        else:
            print("⚠️ Column ai_summary already exists, skipping migration")

if __name__ == "__main__":
    migrate()
