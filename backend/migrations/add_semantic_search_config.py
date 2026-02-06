"""
Migration: Add semantic search configuration fields

Adds:
- enable_semantic_search: Boolean toggle for semantic search feature
- semantic_search_results: Number of semantic results to include (default 5)
- semantic_similarity_threshold: Minimum similarity threshold (default 0.3)
"""

import sqlite3
import sys
import os

def migrate():
    # Get database path from environment or use default
    db_path = os.getenv('INTERNAL_DB_PATH', './data/agent.db')

    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(config)")
        columns = [row[1] for row in cursor.fetchall()]

        migrations_applied = []

        # Add enable_semantic_search
        if 'enable_semantic_search' not in columns:
            cursor.execute("""
                ALTER TABLE config ADD COLUMN enable_semantic_search BOOLEAN DEFAULT 0
            """)
            migrations_applied.append("enable_semantic_search")

        # Add semantic_search_results
        if 'semantic_search_results' not in columns:
            cursor.execute("""
                ALTER TABLE config ADD COLUMN semantic_search_results INTEGER DEFAULT 5
            """)
            migrations_applied.append("semantic_search_results")

        # Add semantic_similarity_threshold
        if 'semantic_similarity_threshold' not in columns:
            cursor.execute("""
                ALTER TABLE config ADD COLUMN semantic_similarity_threshold REAL DEFAULT 0.3
            """)
            migrations_applied.append("semantic_similarity_threshold")

        conn.commit()

        if migrations_applied:
            print(f"[OK] Applied migrations: {', '.join(migrations_applied)}")
        else:
            print("[OK] All semantic search columns already exist")

        # Show current config
        cursor.execute("SELECT enable_semantic_search, semantic_search_results, semantic_similarity_threshold FROM config WHERE id = 1")
        row = cursor.fetchone()
        if row:
            print(f"\nCurrent settings:")
            print(f"  enable_semantic_search: {bool(row[0])}")
            print(f"  semantic_search_results: {row[1]}")
            print(f"  semantic_similarity_threshold: {row[2]}")
        else:
            print("\nNo config row found (will be created on first run)")

    except Exception as e:
        print(f"[FAIL] Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
