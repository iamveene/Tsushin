"""
Migration: Rename CustomTools to SandboxedTools
Phase 6 of Skills-as-Tools Refactoring

Renames tables and columns for clarity:
- "CustomTools" implies user-created/customized tools
- "SandboxedTools" accurately reflects that these run in isolated Docker containers

Tables renamed:
- custom_tools -> sandboxed_tools
- custom_tool_commands -> sandboxed_tool_commands
- custom_tool_parameters -> sandboxed_tool_parameters
- agent_custom_tool -> agent_sandboxed_tool
- custom_tool_executions -> sandboxed_tool_executions

Note: SQLite doesn't support direct table rename with foreign key updates,
so we use ALTER TABLE RENAME TO which preserves data and indexes.
"""

import sqlite3
import os


def get_db_path():
    """Get database path based on environment"""
    # Check for Docker environment
    if os.path.exists('/app/data/agent.db'):
        return '/app/data/agent.db'
    # Local development
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'agent.db')


def upgrade():
    """Rename CustomTool tables to SandboxedTool"""
    db_path = get_db_path()
    print(f"[Migration] Renaming CustomTool tables to SandboxedTool...")
    print(f"[Migration] Database path: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Table renames: old_name -> new_name
    table_renames = [
        ('custom_tools', 'sandboxed_tools'),
        ('custom_tool_commands', 'sandboxed_tool_commands'),
        ('custom_tool_parameters', 'sandboxed_tool_parameters'),
        ('agent_custom_tool', 'agent_sandboxed_tool'),
        ('custom_tool_executions', 'sandboxed_tool_executions'),
    ]

    for old_name, new_name in table_renames:
        try:
            # Check if old table exists
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{old_name}'")
            if not cursor.fetchone():
                # Check if already renamed
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{new_name}'")
                if cursor.fetchone():
                    print(f"[SKIP] {old_name} already renamed to {new_name}")
                else:
                    print(f"[SKIP] Table {old_name} does not exist")
                continue

            # Rename the table
            cursor.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
            print(f"[OK] Renamed {old_name} -> {new_name}")

        except Exception as e:
            print(f"[ERROR] Failed to rename {old_name}: {e}")

    # Rename indexes to match new table names
    index_renames = [
        ('idx_custom_tools_tenant', 'idx_sandboxed_tools_tenant', 'sandboxed_tools', 'tenant_id'),
        ('idx_custom_tool_commands_tenant', 'idx_sandboxed_tool_commands_tenant', 'sandboxed_tool_commands', 'tenant_id'),
        ('idx_custom_tool_parameters_tenant', 'idx_sandboxed_tool_parameters_tenant', 'sandboxed_tool_parameters', 'tenant_id'),
        ('idx_custom_tool_executions_tenant', 'idx_sandboxed_tool_executions_tenant', 'sandboxed_tool_executions', 'tenant_id'),
    ]

    for old_idx, new_idx, table, column in index_renames:
        try:
            # Drop old index if exists
            cursor.execute(f"DROP INDEX IF EXISTS {old_idx}")
            # Create new index
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {new_idx} ON {table}({column})")
            print(f"[OK] Recreated index {new_idx}")
        except Exception as e:
            print(f"[WARN] Index {old_idx} migration: {e}")

    # Rename columns (SQLite 3.25+ supports ALTER TABLE RENAME COLUMN)
    column_renames = [
        ('agent_sandboxed_tool', 'custom_tool_id', 'sandboxed_tool_id'),
        ('persona', 'enabled_custom_tools', 'enabled_sandboxed_tools'),
        ('project', 'enabled_custom_tools', 'enabled_sandboxed_tools'),
    ]

    for table, old_col, new_col in column_renames:
        try:
            # Check if old column exists
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            if old_col in columns:
                cursor.execute(f"ALTER TABLE {table} RENAME COLUMN {old_col} TO {new_col}")
                print(f"[OK] Renamed column {table}.{old_col} -> {new_col}")
            elif new_col in columns:
                print(f"[SKIP] Column {table}.{new_col} already exists")
            else:
                print(f"[SKIP] Column {table}.{old_col} not found")
        except Exception as e:
            print(f"[ERROR] Failed to rename column {table}.{old_col}: {e}")

    conn.commit()
    conn.close()
    print("[Migration] CustomTool -> SandboxedTool rename complete")


def downgrade():
    """Revert table names from SandboxedTool back to CustomTool"""
    db_path = get_db_path()
    print(f"[Migration] Reverting SandboxedTool tables back to CustomTool...")
    print(f"[Migration] Database path: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Reverse renames: new_name -> old_name
    table_renames = [
        ('sandboxed_tools', 'custom_tools'),
        ('sandboxed_tool_commands', 'custom_tool_commands'),
        ('sandboxed_tool_parameters', 'custom_tool_parameters'),
        ('agent_sandboxed_tool', 'agent_custom_tool'),
        ('sandboxed_tool_executions', 'custom_tool_executions'),
    ]

    for new_name, old_name in table_renames:
        try:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{new_name}'")
            if not cursor.fetchone():
                print(f"[SKIP] Table {new_name} does not exist")
                continue

            cursor.execute(f"ALTER TABLE {new_name} RENAME TO {old_name}")
            print(f"[OK] Reverted {new_name} -> {old_name}")

        except Exception as e:
            print(f"[ERROR] Failed to revert {new_name}: {e}")

    # Recreate old indexes
    index_renames = [
        ('idx_sandboxed_tools_tenant', 'idx_custom_tools_tenant', 'custom_tools', 'tenant_id'),
        ('idx_sandboxed_tool_commands_tenant', 'idx_custom_tool_commands_tenant', 'custom_tool_commands', 'tenant_id'),
        ('idx_sandboxed_tool_parameters_tenant', 'idx_custom_tool_parameters_tenant', 'custom_tool_parameters', 'tenant_id'),
        ('idx_sandboxed_tool_executions_tenant', 'idx_custom_tool_executions_tenant', 'custom_tool_executions', 'tenant_id'),
    ]

    for new_idx, old_idx, table, column in index_renames:
        try:
            cursor.execute(f"DROP INDEX IF EXISTS {new_idx}")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS {old_idx} ON {table}({column})")
            print(f"[OK] Recreated index {old_idx}")
        except Exception as e:
            print(f"[WARN] Index {new_idx} revert: {e}")

    # Revert column renames
    column_renames = [
        ('agent_custom_tool', 'sandboxed_tool_id', 'custom_tool_id'),
        ('persona', 'enabled_sandboxed_tools', 'enabled_custom_tools'),
        ('project', 'enabled_sandboxed_tools', 'enabled_custom_tools'),
    ]

    for table, new_col, old_col in column_renames:
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            if new_col in columns:
                cursor.execute(f"ALTER TABLE {table} RENAME COLUMN {new_col} TO {old_col}")
                print(f"[OK] Reverted column {table}.{new_col} -> {old_col}")
            elif old_col in columns:
                print(f"[SKIP] Column {table}.{old_col} already exists")
            else:
                print(f"[SKIP] Column {table}.{new_col} not found")
        except Exception as e:
            print(f"[ERROR] Failed to revert column {table}.{new_col}: {e}")

    conn.commit()
    conn.close()
    print("[Migration] SandboxedTool -> CustomTool revert complete")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--downgrade':
        downgrade()
    else:
        upgrade()
