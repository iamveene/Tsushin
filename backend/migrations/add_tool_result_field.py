"""
Migration: Add tool_result field to agent_run table

This stores the raw tool response separate from the AI's interpretation
"""

import sqlite3
import sys
from pathlib import Path

def run_migration(db_path: str):
    """Add tool_result column to agent_run table"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print(f"[INFO] Connecting to database: {db_path}")

        # Check if column already exists
        cursor.execute("PRAGMA table_info(agent_run)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'tool_result' in columns:
            print("[WARN] Column 'tool_result' already exists. Skipping.")
            return

        # Add the column
        print("[INFO] Adding 'tool_result' column to agent_run table...")
        cursor.execute("""
            ALTER TABLE agent_run
            ADD COLUMN tool_result TEXT
        """)

        conn.commit()
        print("[OK] Migration completed successfully!")
        print("[OK] Added column: tool_result (TEXT)")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    # Default to project database
    default_db = Path(__file__).parent.parent / "data" / "agent.db"
    db_path = sys.argv[1] if len(sys.argv) > 1 else str(default_db)

    print("\n=== Agent Run - Add Tool Result Field ===\n")
    run_migration(db_path)
    print("\n")
