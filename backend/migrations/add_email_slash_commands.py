"""
Database Migration: Add Email Slash Commands

Registers /email slash commands for programmatic email access:
- /email inbox [count]     - List recent emails
- /email search "query"    - Search emails
- /email unread            - Show unread emails

These commands use EmailCommandService for direct execution (zero AI tokens).

Run: python backend/migrations/add_email_slash_commands.py
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

    # Check if email inbox command already exists
    cursor.execute("""
        SELECT id FROM slash_command
        WHERE command_name = 'email inbox'
    """)
    if cursor.fetchone():
        print("[INFO] Email slash commands already exist. Skipping.")
        return False

    return True


def upgrade(conn):
    """Add email slash commands to the database."""
    cursor = conn.cursor()

    print("\n=== Adding Email Slash Commands ===")

    # /email inbox - English
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email inbox',
            'en',
            '^/email\\s+inbox(?:\\s+(\\d+))?$',
            '["mail inbox", "inbox"]',
            'List recent emails from inbox',
            'Usage: /email inbox [count]\n\nExamples:\n  /email inbox        - Show last 10 emails\n  /email inbox 20     - Show last 20 emails\n\nNote: Requires Gmail skill to be enabled and a Gmail account connected.',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            60
        )
    """)

    # /email inbox - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email inbox',
            'pt',
            '^/email\\s+inbox(?:\\s+(\\d+))?$',
            '["mail inbox", "inbox", "caixa de entrada"]',
            'Listar emails recentes da caixa de entrada',
            'Uso: /email inbox [quantidade]\n\nExemplos:\n  /email inbox        - Mostrar últimos 10 emails\n  /email inbox 20     - Mostrar últimos 20 emails\n\nNota: Requer skill Gmail habilitada e conta Gmail conectada.',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            60
        )
    """)

    # /email search - English
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email search',
            'en',
            '^/email\\s+search\\s+"?([^"]+)"?$',
            '["mail search", "buscar email"]',
            'Search emails with Gmail query syntax',
            'Usage: /email search "query"\n\nExamples:\n  /email search "from:john@example.com"\n  /email search "subject:meeting"\n  /email search "has:attachment"\n  /email search "newer_than:7d"\n\nSupports Gmail search operators.',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            61
        )
    """)

    # /email search - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email search',
            'pt',
            '^/email\\s+search\\s+"?([^"]+)"?$',
            '["mail search", "buscar email", "procurar email"]',
            'Buscar emails com sintaxe Gmail',
            'Uso: /email search "consulta"\n\nExemplos:\n  /email search "from:joao@exemplo.com"\n  /email search "subject:reuniao"\n  /email search "has:attachment"\n  /email search "newer_than:7d"\n\nSuporta operadores de busca do Gmail.',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            61
        )
    """)

    # /email unread - English
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email unread',
            'en',
            '^/email\\s+unread$',
            '["mail unread", "unread"]',
            'Show unread emails',
            'Usage: /email unread\n\nShows all unread emails in your inbox.',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            62
        )
    """)

    # /email unread - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email unread',
            'pt',
            '^/email\\s+unread$',
            '["mail unread", "nao lidos", "emails nao lidos"]',
            'Mostrar emails nao lidos',
            'Uso: /email unread\n\nMostra todos os emails nao lidos da caixa de entrada.',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            62
        )
    """)

    conn.commit()
    print("[OK] Email slash commands added (inbox, search, unread - en, pt)")


def downgrade(conn):
    """Remove email slash commands."""
    cursor = conn.cursor()

    print("\n=== Removing Email Slash Commands ===")

    cursor.execute("""
        DELETE FROM slash_command
        WHERE command_name IN ('email inbox', 'email search', 'email unread')
    """)

    conn.commit()
    print("[OK] Email slash commands removed")


def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add Email Slash Commands Migration")
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
