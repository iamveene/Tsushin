"""
Add emergency_stop column to config table
Bug Fix 2026-01-06: Add global kill switch to prevent message loops

Migration: add_emergency_stop_20260107.py
Date: 2026-01-07
"""

def upgrade(db_path: str):
    """Add emergency_stop column to config table"""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Add emergency_stop column with default False
        cursor.execute("""
            ALTER TABLE config
            ADD COLUMN emergency_stop BOOLEAN DEFAULT 0
        """)

        conn.commit()
        print("✅ Added emergency_stop column to config table")

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("⚠️  emergency_stop column already exists, skipping")
        else:
            raise
    finally:
        conn.close()


def downgrade(db_path: str):
    """Remove emergency_stop column (SQLite doesn't support DROP COLUMN easily)"""
    print("⚠️  Downgrade not supported for SQLite ALTER TABLE DROP COLUMN")
    print("   Manual intervention required if rollback needed")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        upgrade(db_path)
    else:
        print("Usage: python add_emergency_stop_20260107.py <db_path>")
