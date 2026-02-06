"""
Migration: Add Ollama configuration fields to Config table
Phase 5.2.1: Configurable Ollama base URL and optional API key

Run with: python backend/migrations/add_ollama_config.py
"""

import sqlite3
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, create_engine

def migrate():
    """Add Ollama configuration fields to Config table"""
    db_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent.db")
    db_path = os.path.abspath(db_path)
    print(f"Database: {db_path}")

    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        try:
            # Check if columns already exist
            result = conn.execute(text("PRAGMA table_info(config)"))
            columns = [row[1] for row in result.fetchall()]

            if 'ollama_base_url' not in columns:
                print("Adding ollama_base_url column...")
                conn.execute(text("""
                    ALTER TABLE config
                    ADD COLUMN ollama_base_url VARCHAR(255) DEFAULT 'http://host.docker.internal:11434'
                """))
                conn.commit()
                print("[OK] Added ollama_base_url column")
            else:
                print("[OK] ollama_base_url column already exists")

            if 'ollama_api_key' not in columns:
                print("Adding ollama_api_key column...")
                conn.execute(text("""
                    ALTER TABLE config
                    ADD COLUMN ollama_api_key VARCHAR(500) DEFAULT NULL
                """))
                conn.commit()
                print("[OK] Added ollama_api_key column")
            else:
                print("[OK] ollama_api_key column already exists")

            print("\n[SUCCESS] Migration completed successfully")
            print("   - ollama_base_url: http://host.docker.internal:11434 (default)")
            print("   - ollama_api_key: NULL (optional)")

        except Exception as e:
            print(f"\n[ERROR] Migration failed: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    print("=" * 50)
    print("Ollama Configuration Migration")
    print("=" * 50)
    migrate()
