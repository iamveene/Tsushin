"""
Migration: Add /inject list and /inject clear subcommands

This migration adds the hierarchical subcommands for /inject to enable
autocomplete suggestions in the frontend.

Run with: python -m migrations.add_inject_subcommands
"""

import sqlite3
import os
import json
from datetime import datetime


# New inject subcommands
INJECT_SUBCOMMANDS = [
    {
        "category": "tool",
        "command_name": "inject list",
        "language_code": "en",
        "pattern": r"^/inject\s+list$",
        "aliases": [],
        "description": "List available tool executions for injection",
        "help_text": "Usage: /inject list\nShows all tool executions that can be injected into conversation.",
        "sort_order": 49
    },
    {
        "category": "tool",
        "command_name": "inject clear",
        "language_code": "en",
        "pattern": r"^/inject\s+clear$",
        "aliases": [],
        "description": "Clear all injected tool outputs",
        "help_text": "Usage: /inject clear\nRemoves all tool outputs from the injection buffer.",
        "sort_order": 50
    },
]


def run_migration(db_path: str):
    """Run the inject subcommands migration."""
    print(f"Running inject subcommands migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if slash_command table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='slash_command'
    """)
    if not cursor.fetchone():
        print("ERROR: slash_command table does not exist. Run add_phase16_memory_commands.py first.")
        conn.close()
        return

    print("\nAdding inject subcommands...")

    added_count = 0
    skipped_count = 0

    for cmd in INJECT_SUBCOMMANDS:
        # Check if command already exists
        cursor.execute("""
            SELECT id FROM slash_command
            WHERE tenant_id = '_system'
            AND command_name = ?
            AND language_code = ?
        """, (cmd["command_name"], cmd["language_code"]))

        if cursor.fetchone():
            print(f"  - Command '{cmd['command_name']}' already exists, skipping")
            skipped_count += 1
            continue

        # Insert new command
        cursor.execute("""
            INSERT INTO slash_command
            (tenant_id, category, command_name, language_code, pattern, aliases,
             description, help_text, is_enabled, handler_type, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'built-in', ?)
        """, (
            "_system",
            cmd["category"],
            cmd["command_name"],
            cmd["language_code"],
            cmd["pattern"],
            json.dumps(cmd.get("aliases", [])),
            cmd.get("description", ""),
            cmd.get("help_text", ""),
            cmd.get("sort_order", 0)
        ))
        print(f"  ✓ Added command '{cmd['command_name']}'")
        added_count += 1

    # Update sort_order for subsequent commands (shift by 2)
    cursor.execute("""
        UPDATE slash_command
        SET sort_order = sort_order + 2
        WHERE tenant_id = '_system'
        AND sort_order >= 49
        AND command_name NOT IN ('inject list', 'inject clear', 'inject', 'injetar')
    """)

    conn.commit()
    conn.close()

    print(f"\n✓ Migration completed!")
    print(f"  - Added: {added_count} commands")
    print(f"  - Skipped: {skipped_count} commands")


if __name__ == "__main__":
    # Default database path for container
    db_path = os.environ.get("DATABASE_PATH", "/app/data/agent.db")

    # Also try local path for development
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent.db")

    if os.path.exists(db_path):
        run_migration(db_path)
    else:
        print(f"Database not found at: {db_path}")
        print("Please provide a valid database path via DATABASE_PATH environment variable")
