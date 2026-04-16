"""
Migration: Fix duplicate sandboxed tool commands and parameters (BUG-044).

Problem:
  - nuclei tool has two 'severity_scan' commands (one with params, one empty)
  - The command with params has duplicate 'url' and 'severity' entries
  - Root cause: no uniqueness constraints on (tool_id, command_name) or
    (command_id, parameter_name), and update logic used .first() instead
    of detecting duplicates

Fix:
  1. Delete duplicate commands (keep the one with most params, lowest ID tiebreak)
  2. Delete duplicate parameters (keep lowest ID)
  3. Add UNIQUE constraints to prevent recurrence

Run with:
  docker compose exec backend python migrations/fix_duplicate_tool_commands.py
"""

import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text


def run_migration():
    """Apply the duplicate tool commands fix migration."""
    db_url = os.environ.get("DATABASE_URL", "sqlite:///data/agent.db")
    engine = create_engine(db_url)
    is_postgres = "postgresql" in db_url

    with engine.connect() as conn:
        # Detect table names (could be old custom_* or new sandboxed_*)
        if is_postgres:
            tables_result = conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ))
        else:
            tables_result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ))
        all_tables = {row[0] for row in tables_result}

        # Determine correct table names
        if "sandboxed_tool_commands" in all_tables:
            cmd_table = "sandboxed_tool_commands"
            param_table = "sandboxed_tool_parameters"
        elif "custom_tool_commands" in all_tables:
            cmd_table = "custom_tool_commands"
            param_table = "custom_tool_parameters"
        else:
            print("No tool commands table found - nothing to migrate")
            return

        print(f"Using tables: {cmd_table}, {param_table}")

        # --- Phase 1: Find and remove duplicate commands ---
        # Find (tool_id, command_name) pairs with duplicates
        dup_cmds = conn.execute(text(f"""
            SELECT tool_id, command_name, COUNT(*) as cnt
            FROM {cmd_table}
            GROUP BY tool_id, command_name
            HAVING COUNT(*) > 1
        """)).fetchall()

        total_cmds_deleted = 0
        total_params_deleted = 0

        for tool_id, cmd_name, cnt in dup_cmds:
            print(f"\nDuplicate command: tool_id={tool_id}, command_name='{cmd_name}', count={cnt}")

            # Get all duplicates with their parameter counts
            rows = conn.execute(text(f"""
                SELECT c.id,
                       (SELECT COUNT(*) FROM {param_table} p WHERE p.command_id = c.id) as param_count
                FROM {cmd_table} c
                WHERE c.tool_id = :tool_id AND c.command_name = :cmd_name
                ORDER BY param_count DESC, c.id ASC
            """), {"tool_id": tool_id, "cmd_name": cmd_name}).fetchall()

            # Keep the first (most params, lowest ID), delete the rest
            keeper_id = rows[0][0]
            keeper_params = rows[0][1]
            print(f"  Keeping command ID {keeper_id} ({keeper_params} params)")

            for cmd_id, param_count in rows[1:]:
                # Delete parameters of the duplicate
                result = conn.execute(text(f"""
                    DELETE FROM {param_table} WHERE command_id = :cmd_id
                """), {"cmd_id": cmd_id})
                params_removed = result.rowcount
                total_params_deleted += params_removed

                # Delete the duplicate command
                conn.execute(text(f"""
                    DELETE FROM {cmd_table} WHERE id = :cmd_id
                """), {"cmd_id": cmd_id})
                total_cmds_deleted += 1
                print(f"  Deleted duplicate command ID {cmd_id} ({param_count} params removed)")

        # --- Phase 2: Find and remove duplicate parameters ---
        dup_params = conn.execute(text(f"""
            SELECT command_id, parameter_name, COUNT(*) as cnt
            FROM {param_table}
            GROUP BY command_id, parameter_name
            HAVING COUNT(*) > 1
        """)).fetchall()

        for command_id, param_name, cnt in dup_params:
            print(f"\nDuplicate param: command_id={command_id}, parameter_name='{param_name}', count={cnt}")

            # Get all duplicate param IDs, keep the lowest
            param_rows = conn.execute(text(f"""
                SELECT id FROM {param_table}
                WHERE command_id = :command_id AND parameter_name = :param_name
                ORDER BY id ASC
            """), {"command_id": command_id, "param_name": param_name}).fetchall()

            keeper_id = param_rows[0][0]
            print(f"  Keeping param ID {keeper_id}")

            for row in param_rows[1:]:
                conn.execute(text(f"""
                    DELETE FROM {param_table} WHERE id = :param_id
                """), {"param_id": row[0]})
                total_params_deleted += 1
                print(f"  Deleted duplicate param ID {row[0]}")

        # --- Phase 3: Add unique constraints ---
        print("\nAdding unique constraints...")

        if is_postgres:
            # PostgreSQL: use ADD CONSTRAINT IF NOT EXISTS pattern
            try:
                conn.execute(text(f"""
                    ALTER TABLE {cmd_table}
                    ADD CONSTRAINT uq_sandboxed_tool_command_name
                    UNIQUE (tool_id, command_name)
                """))
                print(f"  Added UNIQUE(tool_id, command_name) on {cmd_table}")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"  UNIQUE constraint on {cmd_table} already exists")
                else:
                    raise

            try:
                conn.execute(text(f"""
                    ALTER TABLE {param_table}
                    ADD CONSTRAINT uq_sandboxed_tool_param_name
                    UNIQUE (command_id, parameter_name)
                """))
                print(f"  Added UNIQUE(command_id, parameter_name) on {param_table}")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"  UNIQUE constraint on {param_table} already exists")
                else:
                    raise
        else:
            # SQLite: cannot ADD CONSTRAINT, use CREATE UNIQUE INDEX IF NOT EXISTS
            conn.execute(text(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sandboxed_tool_command_name
                ON {cmd_table}(tool_id, command_name)
            """))
            print(f"  Added UNIQUE INDEX on {cmd_table}(tool_id, command_name)")

            conn.execute(text(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS uq_sandboxed_tool_param_name
                ON {param_table}(command_id, parameter_name)
            """))
            print(f"  Added UNIQUE INDEX on {param_table}(command_id, parameter_name)")

        conn.commit()

        print(f"\nMigration complete:")
        print(f"  Duplicate commands deleted: {total_cmds_deleted}")
        print(f"  Duplicate parameters deleted: {total_params_deleted}")
        print(f"  Unique constraints: added")


if __name__ == "__main__":
    run_migration()
