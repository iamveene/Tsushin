"""
Migration: Fix /help Command Pattern for Multi-word Commands

This migration updates the /help command's regex pattern to support
multi-word commands like "/help scheduler create" and "/help project enter".

Changes:
1. Updates pattern from r"^/help\s*(\w*)$" to r"^/help\s*(.*)$"
2. Updates help_text to include better examples
3. Applies to all tenants (both _system and tenant-specific)

Run with: python -m migrations.fix_help_command_pattern
"""

import sqlite3
import os
from datetime import datetime


def run_migration(db_path: str):
    """Run the help command pattern fix migration."""
    print(f"Running help command pattern fix migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # =========================================================================
    # Update /help command pattern to support multi-word commands
    # =========================================================================
    print("\nUpdating /help command pattern...")

    # Check if slash_command table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='slash_command'
    """)

    if not cursor.fetchone():
        print("  ⚠ slash_command table does not exist. Skipping migration.")
        conn.close()
        return

    # Find all help commands (could be in multiple languages or tenants)
    cursor.execute("""
        SELECT id, tenant_id, command_name, pattern, help_text, language_code
        FROM slash_command
        WHERE command_name = 'help'
    """)

    help_commands = cursor.fetchall()

    if not help_commands:
        print("  ⚠ No /help commands found in database.")
        conn.close()
        return

    print(f"  Found {len(help_commands)} /help command(s) to update")

    # Update each help command
    updated_count = 0
    for cmd_id, tenant_id, cmd_name, pattern, help_text, lang_code in help_commands:
        # Update pattern to support multi-word commands
        new_pattern = r"^/help\s*(.*)$"

        # Update help_text with better examples
        if lang_code == "en":
            new_help_text = "Usage: /help [command]\nExamples: /help scheduler create, /help project enter"
        else:
            # Keep original help text for other languages or update as needed
            new_help_text = help_text

        cursor.execute("""
            UPDATE slash_command
            SET pattern = ?,
                help_text = ?,
                updated_at = ?
            WHERE id = ?
        """, (new_pattern, new_help_text, datetime.utcnow(), cmd_id))

        updated_count += 1
        print(f"  ✓ Updated /help command (ID: {cmd_id}, Tenant: {tenant_id}, Lang: {lang_code})")

    conn.commit()
    conn.close()

    print(f"\n✓ Migration completed successfully! Updated {updated_count} command(s).")


if __name__ == "__main__":
    # Default database path for Docker container
    db_path = os.environ.get("DATABASE_PATH", "/app/data/agent.db")

    # Also try local path for development
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent.db")

    if os.path.exists(db_path):
        run_migration(db_path)
    else:
        print(f"Database not found at: {db_path}")
        print("Please provide a valid database path via DATABASE_PATH environment variable")
