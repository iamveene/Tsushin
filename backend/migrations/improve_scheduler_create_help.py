"""
Migration: Improve /scheduler create help text with concrete examples

This migration updates the /scheduler create command's help text to provide
clearer, more concrete examples with actual event names and specific formatting.

Changes:
- Replace vague "Team meeting" examples with concrete event names like "Q1-Review"
- Show event name format more clearly (hyphens work well)
- Add note about including both date and time

Run with: python -m migrations.improve_scheduler_create_help
"""

import sqlite3
import os
from datetime import datetime


def run_migration(db_path: str):
    """Run the scheduler create help text improvement migration."""
    print(f"Running scheduler create help text improvement migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # =========================================================================
    # Update /scheduler create command help text
    # =========================================================================
    print("\nUpdating /scheduler create command help text...")

    # Check if slash_command table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='slash_command'
    """)

    if not cursor.fetchone():
        print("  ⚠ slash_command table does not exist. Skipping migration.")
        conn.close()
        return

    # Find scheduler create commands
    cursor.execute("""
        SELECT id, tenant_id, command_name, help_text, language_code
        FROM slash_command
        WHERE command_name = 'scheduler create'
    """)

    scheduler_commands = cursor.fetchall()

    if not scheduler_commands:
        print("  ⚠ No /scheduler create commands found in database.")
        conn.close()
        return

    print(f"  Found {len(scheduler_commands)} /scheduler create command(s) to update")

    # New help text with concrete examples
    new_help_text = """Usage: /scheduler create <event_title> <date/time>

Examples:
  /scheduler create Q1-Review tomorrow at 3pm
  /scheduler create client-call on Jan 15 at 2pm
  /scheduler create deploy-prod today at 5pm
  /scheduler create standup-meeting next Monday at 9am

Note: Hyphens in event names work well. Include both date and time."""

    # Update each scheduler create command
    updated_count = 0
    for cmd_id, tenant_id, cmd_name, old_help_text, lang_code in scheduler_commands:
        if lang_code == "en":
            cursor.execute("""
                UPDATE slash_command
                SET help_text = ?,
                    updated_at = ?
                WHERE id = ?
            """, (new_help_text, datetime.utcnow(), cmd_id))

            updated_count += 1
            print(f"  ✓ Updated /scheduler create help text (ID: {cmd_id}, Tenant: {tenant_id})")
        else:
            print(f"  - Skipped non-English command (ID: {cmd_id}, Lang: {lang_code})")

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
