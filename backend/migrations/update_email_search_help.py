"""
Database Migration: Update Email Search Help Text

Updates /email search help text to clarify Gmail syntax capabilities:
- Plain keyword searches all fields
- subject: prefix for subject-only search
- from: prefix for sender search
- etc.

Run: python backend/migrations/update_email_search_help.py
"""

import sys
import os
import sqlite3
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_database_path():
    """Get database path from environment or default."""
    return os.getenv("INTERNAL_DB_PATH", "./data/agent.db")


def upgrade(conn):
    """Update email search help text."""
    cursor = conn.cursor()

    print("\n=== Updating Email Search Help Text ===")

    # Update English help text
    new_help_en = '''Usage: /email search "query"

Search emails using Gmail syntax.

Examples:
  /email search "meeting"              - Search all fields
  /email search "subject:invoice"      - Search subject only
  /email search "from:boss@company.com" - Search by sender
  /email search "has:attachment"       - With attachments
  /email search "newer_than:7d"        - Last 7 days
  /email search "is:unread important"  - Unread and important

Tip: For simple keyword search, just use the keyword without prefix.
Gmail will search subject, body, and sender.'''

    cursor.execute("""
        UPDATE slash_command
        SET help_text = ?
        WHERE command_name = 'email search' AND language_code = 'en'
    """, (new_help_en,))

    # Update Portuguese help text
    new_help_pt = '''Uso: /email search "consulta"

Busca emails usando sintaxe Gmail.

Exemplos:
  /email search "reuniao"              - Busca em todos os campos
  /email search "subject:fatura"       - Busca so no assunto
  /email search "from:chefe@empresa.com" - Busca por remetente
  /email search "has:attachment"       - Com anexos
  /email search "newer_than:7d"        - Ultimos 7 dias
  /email search "is:unread important"  - Nao lidos e importantes

Dica: Para busca simples, use a palavra-chave sem prefixo.
Gmail buscara no assunto, corpo e remetente.'''

    cursor.execute("""
        UPDATE slash_command
        SET help_text = ?
        WHERE command_name = 'email search' AND language_code = 'pt'
    """, (new_help_pt,))

    conn.commit()

    # Check how many rows were updated
    cursor.execute("""
        SELECT COUNT(*) FROM slash_command
        WHERE command_name = 'email search'
    """)
    count = cursor.fetchone()[0]

    print(f"[OK] Updated help text for {count} email search command entries")


def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Update Email Search Help Text Migration")
    parser.add_argument("--db-path", help="Database path")
    args = parser.parse_args()

    db_path = args.db_path or get_database_path()

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    print(f"Using database: {db_path}")

    conn = sqlite3.connect(db_path)

    try:
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
