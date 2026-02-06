"""
Database Migration: Add Email Read Slash Command

Registers /email read command:
- /email read <identifier>  - Read full email content by ID or list index

Run: python backend/migrations/add_email_read_command.py
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

    # Check if email read command already exists
    cursor.execute("""
        SELECT id FROM slash_command
        WHERE command_name = 'email read'
    """)
    if cursor.fetchone():
        print("[INFO] Email read command already exists. Skipping.")
        return False

    return True


def upgrade(conn):
    """Add email read slash command to the database."""
    cursor = conn.cursor()

    print("\n=== Adding Email Read Slash Command ===")

    # /email read - English
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email read',
            'en',
            '^/email\\s+read\\s+(.+)$',
            '["mail read", "read email", "ler email"]',
            'Read full email content by ID or list index',
            'Usage: /email read <identifier>

Read the full content of an email.

Examples:
  /email read 3           - Read email #3 from last list
  /email read abc123xyz   - Read email by message ID

Tip: Use /email list first, then /email read <number>',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            57
        )
    """)

    # /email read - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'email read',
            'pt',
            '^/email\\s+read\\s+(.+)$',
            '["mail read", "ler email", "email ler"]',
            'Ler conteudo completo do email por ID ou indice',
            'Uso: /email read <identificador>

Le o conteudo completo de um email.

Exemplos:
  /email read 3           - Ler email #3 da ultima lista
  /email read abc123xyz   - Ler email pelo ID

Dica: Use /email list primeiro, depois /email read <numero>',
            1,
            'built-in',
            '{"skill_type": "gmail"}',
            57
        )
    """)

    conn.commit()
    print("[OK] Email read slash command added (en, pt)")


def downgrade(conn):
    """Remove email read slash command."""
    cursor = conn.cursor()

    print("\n=== Removing Email Read Slash Command ===")

    cursor.execute("""
        DELETE FROM slash_command
        WHERE command_name = 'email read'
    """)

    conn.commit()
    print("[OK] Email read slash command removed")


def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add Email Read Command Migration")
    parser.add_argument("--downgrade", action="store_true", help="Remove the command")
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
