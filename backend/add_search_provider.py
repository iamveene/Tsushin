#!/usr/bin/env python
"""Add search_provider column to config table"""
import sqlite3
import sys
import os

DB_PATH = r"D:\code\tsushin\backend\data\agent.db"

def add_search_provider_column():
    """Add search_provider column if it doesn't exist"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if column already exists
        cursor.execute("PRAGMA table_info(config)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'search_provider' in columns:
            print("✓ Column 'search_provider' already exists")
        else:
            # Add the column
            cursor.execute("ALTER TABLE config ADD COLUMN search_provider VARCHAR(20) DEFAULT 'brave'")
            conn.commit()
            print("✓ Added column 'search_provider' with default value 'brave'")

        conn.close()
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    print("Adding search_provider column to database...")
    success = add_search_provider_column()
    sys.exit(0 if success else 1)
