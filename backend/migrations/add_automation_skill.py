#!/usr/bin/env python3
"""
Migration: Add Automation Skill and Flows Commands

Adds:
1. Flows commands to slash_command table (/flows run, /flows list)
2. No schema changes needed (AgentSkill table already supports any skill_type)

This migration is safe to run multiple times (idempotent).

Usage:
    python backend/migrations/add_automation_skill.py backend/data/agent.db
"""

import sqlite3
import sys
import json
from datetime import datetime


def run_migration(db_path: str):
    """Run the automation skill migration."""
    print(f"\n{'='*60}")
    print("Migration: Add Automation Skill and Flows Commands")
    print(f"{'='*60}\n")
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # =====================================================================
        # 1. Check if slash_command table exists
        # =====================================================================
        print("1. Checking slash_command table...")
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='slash_command'
        """)

        if not cursor.fetchone():
            print("   ⚠️  slash_command table not found. Run Phase 16 migration first.")
            print("   Skipping command seeding.")
            conn.close()
            return

        print("   ✓ slash_command table exists")

        # =====================================================================
        # 2. Check if flows commands already exist
        # =====================================================================
        print("\n2. Checking for existing flows commands...")
        cursor.execute("""
            SELECT COUNT(*) FROM slash_command
            WHERE tenant_id = '_system'
            AND category = 'flows'
        """)
        existing_count = cursor.fetchone()[0]

        if existing_count > 0:
            print(f"   ⚠️  Found {existing_count} existing flows commands. Skipping seed.")
            conn.close()
            return

        print("   ✓ No existing flows commands found")

        # =====================================================================
        # 3. Insert flows commands
        # =====================================================================
        print("\n3. Inserting flows commands...")

        flows_commands = [
            {
                "tenant_id": "_system",
                "category": "flows",
                "command_name": "flows run",
                "language_code": "en",
                "pattern": r"^/flows\s+run\s+(.+)$",
                "aliases": json.dumps([]),
                "description": "Execute a workflow by name or ID",
                "help_text": (
                    "Usage: /flows run <flow_name_or_id>\n"
                    "Examples:\n"
                    "  /flows run 5 - Run flow with ID 5\n"
                    "  /flows run weekly-report - Run flow by name\n\n"
                    "Requires: Automation skill enabled"
                ),
                "is_enabled": 1,
                "handler_type": "built-in",
                "sort_order": 50
            },
            {
                "tenant_id": "_system",
                "category": "flows",
                "command_name": "flows list",
                "language_code": "en",
                "pattern": r"^/flows\s+list$",
                "aliases": json.dumps([]),
                "description": "List all available workflows",
                "help_text": (
                    "Usage: /flows list\n"
                    "Shows all workflows with name, ID, type, and description.\n\n"
                    "Requires: Automation skill enabled"
                ),
                "is_enabled": 1,
                "handler_type": "built-in",
                "sort_order": 51
            }
        ]

        for cmd in flows_commands:
            cursor.execute("""
                INSERT INTO slash_command
                (tenant_id, category, command_name, language_code, pattern,
                 aliases, description, help_text, is_enabled, handler_type,
                 sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                cmd["tenant_id"],
                cmd["category"],
                cmd["command_name"],
                cmd["language_code"],
                cmd["pattern"],
                cmd["aliases"],
                cmd["description"],
                cmd["help_text"],
                cmd["is_enabled"],
                cmd["handler_type"],
                cmd["sort_order"]
            ))
            print(f"   ✓ Added command: {cmd['command_name']}")

        conn.commit()
        print(f"\n   ✅ Successfully added {len(flows_commands)} flows commands")

        # =====================================================================
        # 4. Summary
        # =====================================================================
        print("\n" + "="*60)
        print("Migration Summary")
        print("="*60)
        print("\n✅ Migration completed successfully!")
        print("\nChanges:")
        print("  • Added 2 flows commands (/flows run, /flows list)")
        print("  • No schema changes needed")
        print("\nNext steps:")
        print("  1. Restart the backend: docker compose restart backend")
        print("  2. Enable Automation skill for agents via API or UI")
        print("  3. Test /flows commands in playground")
        print()

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python add_automation_skill.py <database_path>")
        print("Example: python add_automation_skill.py backend/data/agent.db")
        sys.exit(1)

    db_path = sys.argv[1]
    run_migration(db_path)
