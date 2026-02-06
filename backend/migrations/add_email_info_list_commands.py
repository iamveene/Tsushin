"""
Database Migration: Add Email Info/List Slash Commands

Registers additional /email slash commands:
- /email info          - Show Gmail configuration
- /email list [filter] - List emails with filters (unread, today, <number>)

Run: python backend/migrations/add_email_info_list_commands.py
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

    # Check if email info command already exists
    cursor.execute("""
        SELECT id FROM slash_command
        WHERE command_name = 'email info'
    """)
    if cursor.fetchone():
        print("[INFO] Email info/list commands already exist. Skipping.")
        return False

    return True


def upgrade(conn):
    """Add email info/list slash commands to the database."""
    cursor = conn.cursor()

    print("\n=== Adding Email Info/List Slash Commands ===")

    # /email info - English
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email info',
            'en',
            '^/email\\s+info$',
            '["mail info", "gmail info"]',
            'Show Gmail configuration and connection status',
            'Usage: /email info

Displays Gmail integration status, connected email address, authorization date, and available capabilities.',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            59
        )
    """)

    # /email info - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email info',
            'pt',
            '^/email\\s+info$',
            '["mail info", "gmail info", "email configuracao"]',
            'Mostrar configuracao e status do Gmail',
            'Uso: /email info

Exibe status da integracao Gmail, email conectado, data de autorizacao e capacidades disponiveis.',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            59
        )
    """)

    # /email list - English
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email list',
            'en',
            '^/email\\s+list(?:\\s+(\\d+|unread|today))?$',
            '["mail list", "listar emails"]',
            'List emails with optional filter',
            'Usage: /email list [filter]

Filters:
  (none)   - Show last 10 emails
  unread   - Show unread emails only
  today    - Show today''s emails
  <number> - Show last N emails (e.g., /email list 20)

Examples:
  /email list
  /email list unread
  /email list today
  /email list 25',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            58
        )
    """)

    # /email list - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email list',
            'pt',
            '^/email\\s+list(?:\\s+(\\d+|unread|today|nao_lidos|hoje))?$',
            '["mail list", "listar emails", "emails lista"]',
            'Listar emails com filtro opcional',
            'Uso: /email list [filtro]

Filtros:
  (nenhum) - Mostrar ultimos 10 emails
  unread   - Mostrar apenas nao lidos
  hoje/today - Mostrar emails de hoje
  <numero> - Mostrar ultimos N emails (ex: /email list 20)

Exemplos:
  /email list
  /email list unread
  /email list hoje
  /email list 25',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            58
        )
    """)

    conn.commit()
    print("[OK] Email info/list slash commands added (en, pt)")


def downgrade(conn):
    """Remove email info/list slash commands."""
    cursor = conn.cursor()

    print("\n=== Removing Email Info/List Slash Commands ===")

    cursor.execute("""
        DELETE FROM slash_command
        WHERE command_name IN ('email info', 'email list')
    """)

    conn.commit()
    print("[OK] Email info/list slash commands removed")


def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add Email Info/List Commands Migration")
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
