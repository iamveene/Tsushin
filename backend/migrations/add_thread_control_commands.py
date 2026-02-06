"""
Migration: Add Thread Control Slash Commands
Date: 2026-01-11
Author: AI Assistant

Adds /thread commands to manually control active conversation threads:
- /thread end: End the current active thread
- /thread list: List active threads for the user
- /thread status: Show current thread status
"""

import sqlite3
import json
from datetime import datetime


# Thread control commands to add
THREAD_COMMANDS = [
    {
        "tenant_id": "_system",
        "category": "thread",
        "command_name": "thread end",
        "language_code": "en",
        "pattern": r"^/thread\s+end$",
        "aliases": json.dumps(["thread stop", "thread cancel"]),
        "description": "End the current active conversation thread",
        "help_text": "Usage: /thread end\n\nEnds any active conversation thread you're currently in. Use this if a conversation is hijacking your messages.",
        "handler_type": "built-in",
        "sort_order": 70
    },
    {
        "tenant_id": "_system",
        "category": "thread",
        "command_name": "thread list",
        "language_code": "en",
        "pattern": r"^/thread\s+list$",
        "aliases": json.dumps(["threads"]),
        "description": "List your active conversation threads",
        "help_text": "Usage: /thread list\n\nShows all active conversation threads you're currently participating in.",
        "handler_type": "built-in",
        "sort_order": 71
    },
    {
        "tenant_id": "_system",
        "category": "thread",
        "command_name": "thread status",
        "language_code": "en",
        "pattern": r"^/thread\s+status$",
        "aliases": json.dumps([]),
        "description": "Show current thread status",
        "help_text": "Usage: /thread status\n\nShows details about your current active conversation thread, if any.",
        "handler_type": "built-in",
        "sort_order": 72
    },
    {
        "tenant_id": "_system",
        "category": "thread",
        "command_name": "thread encerrar",
        "language_code": "pt",
        "pattern": r"^/thread\s+encerrar$",
        "aliases": json.dumps(["thread parar", "thread cancelar"]),
        "description": "Encerrar a conversa ativa atual",
        "help_text": "Uso: /thread encerrar\n\nEncerra qualquer conversa ativa em andamento. Use isso se uma conversa estiver capturando suas mensagens.",
        "handler_type": "built-in",
        "sort_order": 73
    },
]


def run_migration(db_path: str):
    """Run the thread control commands migration."""
    print(f"\n{'='*60}")
    print("Migration: Add Thread Control Commands")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if slash_command table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='slash_command'
        """)
        if not cursor.fetchone():
            print("❌ Error: slash_command table does not exist")
            print("   Run phase 16 migrations first")
            return

        print("1. Adding thread control commands...")

        added_count = 0
        skipped_count = 0

        for cmd in THREAD_COMMANDS:
            # Check if command already exists
            cursor.execute("""
                SELECT id FROM slash_command
                WHERE tenant_id = ? AND command_name = ? AND language_code = ?
            """, (cmd["tenant_id"], cmd["command_name"], cmd["language_code"]))

            if cursor.fetchone():
                print(f"   ⏭️  Skipping '{cmd['command_name']}' (already exists)")
                skipped_count += 1
                continue

            # Insert command
            cursor.execute("""
                INSERT INTO slash_command (
                    tenant_id, category, command_name, language_code,
                    pattern, aliases, description, help_text,
                    handler_type, sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cmd["tenant_id"],
                cmd["category"],
                cmd["command_name"],
                cmd["language_code"],
                cmd["pattern"],
                cmd["aliases"],
                cmd["description"],
                cmd["help_text"],
                cmd["handler_type"],
                cmd["sort_order"],
                datetime.utcnow().isoformat() + "Z",
                datetime.utcnow().isoformat() + "Z"
            ))

            print(f"   ✓ Added '{cmd['command_name']}'")
            added_count += 1

        conn.commit()

        print(f"\n✅ Migration completed successfully!")
        print(f"   Added: {added_count} commands")
        print(f"   Skipped: {skipped_count} commands (already exist)")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python add_thread_control_commands.py <db_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    run_migration(db_path)
