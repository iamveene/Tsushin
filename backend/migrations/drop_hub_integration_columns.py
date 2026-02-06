#!/usr/bin/env python3
"""
Database Schema Migration: Drop Hub Integration Columns

Removes deprecated columns from agent table:
- hub_integration_id (replaced by AgentSkillIntegration)
- default_asana_assignee_gid (moved to AgentSkillIntegration.config)

Note: SQLite doesn't support DROP COLUMN directly, so we must:
1. Create new table without deprecated columns
2. Copy data from old table
3. Drop old table and rename new table
4. Recreate indexes and foreign keys
"""

import sys
import os
import sqlite3
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate(db_path: str):
    """
    Drop hub_integration_id and default_asana_assignee_gid from agent table.

    Args:
        db_path: Path to SQLite database
    """
    print("=" * 70)
    print("Database Schema Migration: Drop Hub Integration Columns")
    print("=" * 70)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Step 1: Verify prerequisites
        print("\n[1/6] Verifying prerequisites...")

        # Check if data migration was run
        cursor.execute("""
            SELECT COUNT(*) as count FROM agent
            WHERE hub_integration_id IS NOT NULL
        """)
        remaining = cursor.fetchone()['count']

        if remaining > 0:
            print(f"   ❌ ERROR: {remaining} agent(s) still have hub_integration_id set")
            print("   Please run migrate_hub_integration_to_skills.py first")
            conn.close()
            return False

        print("   ✓ No agents have hub_integration_id set")

        # Check if columns exist
        cursor.execute("PRAGMA table_info(agent)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'hub_integration_id' not in columns and 'default_asana_assignee_gid' not in columns:
            print("   ✓ Columns already removed, migration not needed")
            conn.close()
            return True

        print("   ✓ Prerequisites verified")

        # Step 2: Get current agent table schema
        print("\n[2/6] Analyzing current schema...")

        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='agent'")
        original_schema = cursor.fetchone()['sql']
        print(f"   Found agent table with {len(columns)} columns")

        # Step 3: Create new agent table without deprecated columns
        print("\n[3/6] Creating new agent table...")

        cursor.execute("""
            CREATE TABLE agent_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                system_prompt TEXT NOT NULL,
                tone_preset_id INTEGER,
                custom_tone TEXT,
                keywords JSON,
                enabled_tools JSON,
                model_provider VARCHAR(20),
                model_name VARCHAR(100),
                is_active BOOLEAN,
                is_default BOOLEAN,
                created_at DATETIME,
                updated_at DATETIME,
                response_template TEXT DEFAULT '@{agent_name}: {response}',
                persona_id INTEGER,
                memory_size INTEGER,
                trigger_dm_enabled BOOLEAN,
                trigger_group_filters JSON,
                trigger_number_filters JSON,
                context_message_count INTEGER,
                context_char_limit INTEGER,
                memory_isolation_mode TEXT DEFAULT 'isolated',
                enable_semantic_search BOOLEAN DEFAULT 1,
                semantic_search_results INTEGER DEFAULT 10,
                semantic_similarity_threshold REAL DEFAULT 0.5,
                chroma_db_path TEXT,
                tenant_id TEXT,
                user_id INTEGER,
                enabled_channels TEXT DEFAULT '["playground", "whatsapp"]',
                whatsapp_integration_id INTEGER,
                telegram_integration_id INTEGER,
                FOREIGN KEY (contact_id) REFERENCES contact(id),
                FOREIGN KEY (tone_preset_id) REFERENCES tone_preset(id),
                FOREIGN KEY (persona_id) REFERENCES persona(id),
                FOREIGN KEY (whatsapp_integration_id) REFERENCES whatsapp_mcp_instance(id)
            )
        """)

        print("   ✓ Created agent_new table")

        # Step 4: Copy data from old table to new table
        print("\n[4/6] Copying data...")

        # Get all columns except the ones we're dropping
        copy_columns = [col for col in columns if col not in ('hub_integration_id', 'default_asana_assignee_gid')]
        columns_str = ', '.join(copy_columns)

        cursor.execute(f"""
            INSERT INTO agent_new ({columns_str})
            SELECT {columns_str}
            FROM agent
        """)

        copied_count = cursor.rowcount
        print(f"   ✓ Copied {copied_count} agent record(s)")

        # Step 5: Replace old table with new table
        print("\n[5/6] Replacing old table...")

        cursor.execute("DROP TABLE agent")
        cursor.execute("ALTER TABLE agent_new RENAME TO agent")

        print("   ✓ Replaced agent table")

        # Step 6: Recreate indexes
        print("\n[6/6] Recreating indexes...")

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_contact
            ON agent(contact_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_persona
            ON agent(persona_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_tenant
            ON agent(tenant_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_user
            ON agent(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_active
            ON agent(is_active)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_default
            ON agent(is_default)
        """)

        print("   ✓ Recreated 6 indexes")

        # Commit changes
        conn.commit()

        print("\n" + "=" * 70)
        print("Migration completed successfully!")
        print("=" * 70)
        print(f"\nChanges:")
        print(f"  - Removed: hub_integration_id column")
        print(f"  - Removed: default_asana_assignee_gid column")
        print(f"  - Migrated: {copied_count} agent records")
        print(f"\nNext steps:")
        print(f"  1. Update Agent model in models.py")
        print(f"  2. Restart backend containers")
        print(f"  3. Test agent configuration in Studio")

        return True

    except Exception as e:
        print(f"\n❌ Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path: str):
    """
    Verify migration was successful.

    Args:
        db_path: Path to SQLite database
    """
    print("\n" + "=" * 70)
    print("Verification")
    print("=" * 70)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check columns
        cursor.execute("PRAGMA table_info(agent)")
        columns = {row['name'] for row in cursor.fetchall()}

        if 'hub_integration_id' in columns:
            print("   ❌ hub_integration_id column still exists!")
        else:
            print("   ✓ hub_integration_id column removed")

        if 'default_asana_assignee_gid' in columns:
            print("   ❌ default_asana_assignee_gid column still exists!")
        else:
            print("   ✓ default_asana_assignee_gid column removed")

        # Check data integrity
        cursor.execute("SELECT COUNT(*) as count FROM agent")
        agent_count = cursor.fetchone()['count']
        print(f"   ✓ Found {agent_count} agent(s)")

        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='agent'")
        indexes = [row['name'] for row in cursor.fetchall()]
        print(f"   ✓ Found {len(indexes)} index(es): {', '.join(indexes)}")

        print("\n" + "=" * 70)

    finally:
        conn.close()


if __name__ == "__main__":
    # Default to backend/data/agent.db (container path)
    db_path = os.getenv("DB_PATH", "backend/data/agent.db")

    # Allow override from command line
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    # Make path absolute if relative and doesn't already exist
    if not os.path.isabs(db_path) and not os.path.exists(db_path):
        # Go up to project root from backend/migrations
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        db_path = os.path.join(project_root, db_path)

    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    print(f"Database: {db_path}\n")

    # Run migration
    success = migrate(db_path)

    if success:
        # Verify
        verify(db_path)
    else:
        print("\nMigration failed or was skipped")
        sys.exit(1)
