"""
Database Migration: Add Shell Slash Command (Phase 18.3)

Registers the /shell slash command in the slash_command table
so that it can be detected and routed to the ShellSkill.

Run: python backend/migrations/add_shell_slash_command.py
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

    # Check if shell command already exists
    cursor.execute("""
        SELECT id FROM slash_command
        WHERE command_name = 'shell'
    """)
    if cursor.fetchone():
        print("[INFO] Shell slash command already exists. Skipping.")
        return False

    return True


def upgrade(conn):
    """Add shell slash command to the database."""
    cursor = conn.cursor()

    print("\n=== Adding Shell Slash Command ===")

    # Insert /shell command (English)
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'shell',
            'en',
            '^/shell\\s+(?:([\\w\\-@]+):)?(.+)$',
            '["sh", "cmd", "exec"]',
            'Execute shell commands on remote hosts via beacon agents',
            'Usage: /shell [target:]<command>\n\nExamples:\n  /shell ls -la\n  /shell myserver:df -h\n  /shell @all:uptime\n\nTargets:\n  - default: First available beacon\n  - hostname: Specific beacon by hostname\n  - @all: All beacons (broadcast)\n\nNote: Commands are executed on registered beacon agents. Enable the Shell skill for AI-assisted execution.',
            1,
            'built-in',
            '{"skill_type": "shell"}',
            50
        )
    """)

    # Insert /shell command (Portuguese)
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'shell',
            'pt',
            '^/shell\\s+(?:([\\w\\-@]+):)?(.+)$',
            '["sh", "cmd", "exec"]',
            'Executa comandos shell em hosts remotos via agentes beacon',
            'Uso: /shell [destino:]<comando>\n\nExemplos:\n  /shell ls -la\n  /shell meuservidor:df -h\n  /shell @all:uptime\n\nDestinos:\n  - default: Primeiro beacon disponível\n  - hostname: Beacon específico por hostname\n  - @all: Todos os beacons (broadcast)\n\nNota: Os comandos são executados em agentes beacon registrados. Habilite a skill Shell para execução assistida por IA.',
            1,
            'built-in',
            '{"skill_type": "shell"}',
            50
        )
    """)

    conn.commit()
    print("[OK] Shell slash command added (en, pt)")


def downgrade(conn):
    """Remove shell slash command."""
    cursor = conn.cursor()

    print("\n=== Removing Shell Slash Command ===")

    cursor.execute("""
        DELETE FROM slash_command
        WHERE command_name = 'shell'
    """)

    conn.commit()
    print("[OK] Shell slash command removed")


def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add Shell Slash Command Migration")
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
