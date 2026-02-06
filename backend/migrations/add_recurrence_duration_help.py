"""
Migration: Update /scheduler create help text with recurrence and duration examples

This migration updates the /scheduler create command's help text to include
examples of recurring events and custom durations.

Changes:
- Added recurrence patterns (daily, weekly, monthly, every [day])
- Added duration examples (30min, 1h, 2h)
- Updated examples to showcase new features

Run: python backend/migrations/add_recurrence_duration_help.py
"""

import sqlite3
import sys
import os
from datetime import datetime


def run_migration(db_path: str):
    """Update scheduler create command help text"""
    print("=" * 80)
    print("Migration: Update /scheduler create help text with recurrence and duration")
    print("=" * 80)

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
        print("  ⚠ Table 'slash_command' does not exist. Skipping migration.")
        conn.close()
        return

    # Find all scheduler create commands
    cursor.execute("""
        SELECT id, tenant_id, language_code, help_text
        FROM slash_command
        WHERE command_name = 'scheduler create' OR pattern LIKE '%scheduler%create%'
        ORDER BY id
    """)

    scheduler_commands = cursor.fetchall()

    if not scheduler_commands:
        print("  ⚠ No /scheduler create commands found in database.")
        conn.close()
        return

    print(f"  Found {len(scheduler_commands)} /scheduler create command(s) to update")

    # New help text with recurrence and duration examples
    new_help_text = """Usage: /scheduler create <description> [duration] [recurrence]

Examples:
  /scheduler create Team meeting tomorrow at 3pm
  /scheduler create Standup daily at 9am
  /scheduler create 1:1 with John every Monday at 2pm 30min
  /scheduler create Review weekly at 10am 1h
  /scheduler create Monthly sync on Jan 15 at 2pm

Duration: Add '30min', '1h', '2h' etc.
Recurrence: Use 'daily', 'weekly', 'monthly', or 'every Monday/Tuesday/etc.'"""

    updated_count = 0

    for cmd_id, tenant_id, lang_code, old_help in scheduler_commands:
        # Only update English commands
        if lang_code == 'en':
            cursor.execute("""
                UPDATE slash_command
                SET help_text = ?, updated_at = ?
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
    # Determine database path
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Default to backend/data/agent.db (container path)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        backend_dir = os.path.dirname(script_dir)
        db_path = os.path.join(backend_dir, "data", "agent.db")

    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        print("\nUsage: python add_recurrence_duration_help.py [path/to/agent.db]")
        sys.exit(1)

    print(f"Using database: {db_path}\n")
    run_migration(db_path)
