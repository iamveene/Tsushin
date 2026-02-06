"""
Database Migration: Add Search Slash Commands

Registers /search slash command for programmatic web search:
- /search "query"     - Search the web

Uses SearchCommandService for direct execution (zero AI tokens).

Run: python backend/migrations/add_search_slash_commands.py
"""

import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_database_path():
    """Get database path from environment or default."""
    return os.getenv("INTERNAL_DB_PATH", "./data/agent.db")


def check_prerequisites(conn):
    """Verify database state before migration."""
    cursor = conn.cursor()

    # Check if slash_command table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='slash_command'
    """)
    if not cursor.fetchone():
        raise Exception("slash_command table not found.")

    # Check if search command already exists
    cursor.execute("""
        SELECT id FROM slash_command
        WHERE command_name = 'search'
    """)
    if cursor.fetchone():
        print("[INFO] Search slash command already exists. Skipping.")
        return False

    return True


def upgrade(conn):
    """Add search slash commands to the database."""
    cursor = conn.cursor()

    print("\n=== Adding Search Slash Commands ===")

    # /search "query" - English
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'search',
            'en',
            '^/search\\s+"?([^"]+)"?$',
            '["buscar", "pesquisar", "google"]',
            'Search the web',
            'Usage: /search "query"\n\nExamples:\n  /search "best python libraries 2024"\n  /search "weather API documentation"\n  /search "latest AI news"\n\nUses configured search provider (Brave Search by default).',
            1,
            'built-in',
            '{"skill_type": "web_search"}',
            72
        )
    """)

    # /search "query" - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'search',
            'pt',
            '^/search\\s+"?([^"]+)"?$',
            '["buscar", "pesquisar", "google"]',
            'Pesquisar na web',
            'Uso: /search "consulta"\n\nExemplos:\n  /search "melhores bibliotecas python 2024"\n  /search "documentacao API de clima"\n  /search "ultimas noticias IA"\n\nUsa o provedor de busca configurado (Brave Search por padrao).',
            1,
            'built-in',
            '{"skill_type": "web_search"}',
            72
        )
    """)

    conn.commit()
    print("[OK] Search slash command added (en, pt)")


def downgrade(conn):
    """Remove search slash commands."""
    cursor = conn.cursor()

    print("\n=== Removing Search Slash Commands ===")

    cursor.execute("""
        DELETE FROM slash_command
        WHERE command_name = 'search'
    """)

    conn.commit()
    print("[OK] Search slash command removed")


def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add Search Slash Commands Migration")
    parser.add_argument("--downgrade", action="store_true", help="Remove the commands")
    parser.add_argument("--db-path", help="Database path")
    args = parser.parse_args()

    db_path = args.db_path or get_database_path()

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    print(f"Using database: {db_path}")

    conn = sqlite3.connect(db_path)

    try:
        if args.downgrade:
            downgrade(conn)
        else:
            if check_prerequisites(conn):
                upgrade(conn)

        print("[SUCCESS] Migration completed!")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
