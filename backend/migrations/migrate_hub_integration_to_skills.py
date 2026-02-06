#!/usr/bin/env python3
"""
Data Migration: Hub Integration to Skills System

Migrates agents using hub_integration_id to the new AgentSkillIntegration system.
- Moves Asana integrations to Scheduler skill provider configuration
- Preserves default_asana_assignee_gid in skill config
- Enables flows skill for affected agents
- Clears deprecated hub_integration_id fields
"""

import sys
import os
import sqlite3
import json
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate(db_path: str):
    """
    Migrate hub_integration_id to AgentSkillIntegration system.

    Args:
        db_path: Path to SQLite database
    """
    print("=" * 70)
    print("Data Migration: Hub Integration → Skills System")
    print("=" * 70)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Access columns by name
    cursor = conn.cursor()

    try:
        # Step 1: Find all agents with hub_integration_id
        print("\n[1/5] Finding agents with hub_integration_id...")
        cursor.execute("""
            SELECT
                a.id as agent_id,
                a.hub_integration_id,
                a.default_asana_assignee_gid,
                a.tenant_id,
                h.type as integration_type,
                h.name as integration_name
            FROM agent a
            LEFT JOIN hub_integration h ON a.hub_integration_id = h.id
            WHERE a.hub_integration_id IS NOT NULL
        """)

        agents_to_migrate = cursor.fetchall()

        if not agents_to_migrate:
            print("   ✓ No agents to migrate (none using hub_integration_id)")
            conn.close()
            return

        print(f"   Found {len(agents_to_migrate)} agent(s) with hub integration:")
        for agent in agents_to_migrate:
            print(f"     - Agent {agent['agent_id']}: {agent['integration_type']} "
                  f"(integration_id={agent['hub_integration_id']})")

        # Step 2: Migrate each agent
        print(f"\n[2/5] Migrating agents to AgentSkillIntegration...")

        migrated_count = 0
        skipped_count = 0

        for agent in agents_to_migrate:
            agent_id = agent['agent_id']
            integration_id = agent['hub_integration_id']
            integration_type = agent['integration_type']
            assignee_gid = agent['default_asana_assignee_gid']

            # Only migrate Asana integrations
            if integration_type != 'asana':
                print(f"   ⚠ Agent {agent_id}: Skipping non-Asana integration "
                      f"(type={integration_type})")
                skipped_count += 1
                continue

            # Check if AgentSkillIntegration already exists
            cursor.execute("""
                SELECT id FROM agent_skill_integration
                WHERE agent_id = ? AND skill_type = 'flows'
            """, (agent_id,))

            existing = cursor.fetchone()

            if existing:
                print(f"   ⚠ Agent {agent_id}: AgentSkillIntegration already exists, "
                      f"skipping")
                skipped_count += 1
                continue

            # Build config JSON
            config = {}
            if assignee_gid:
                config['default_asana_assignee_gid'] = assignee_gid

            config_json = json.dumps(config) if config else None

            # Create AgentSkillIntegration record
            cursor.execute("""
                INSERT INTO agent_skill_integration
                (agent_id, skill_type, integration_id, scheduler_provider, config, created_at, updated_at)
                VALUES (?, 'flows', ?, 'asana', ?, ?, ?)
            """, (
                agent_id,
                integration_id,
                config_json,
                datetime.utcnow().isoformat() + "Z",
                datetime.utcnow().isoformat() + "Z"
            ))

            print(f"   ✓ Agent {agent_id}: Created AgentSkillIntegration "
                  f"(scheduler_provider=asana, integration_id={integration_id})")
            migrated_count += 1

        print(f"\n   Summary: {migrated_count} migrated, {skipped_count} skipped")

        # Step 3: Enable flows skill for migrated agents
        print(f"\n[3/5] Enabling flows skill for migrated agents...")

        enabled_count = 0
        already_enabled = 0

        for agent in agents_to_migrate:
            agent_id = agent['agent_id']
            integration_type = agent['integration_type']

            if integration_type != 'asana':
                continue

            # Check if flows skill is already enabled
            cursor.execute("""
                SELECT id, is_enabled FROM agent_skill
                WHERE agent_id = ? AND skill_type = 'flows'
            """, (agent_id,))

            existing_skill = cursor.fetchone()

            if existing_skill:
                if existing_skill['is_enabled']:
                    print(f"   ✓ Agent {agent_id}: flows skill already enabled")
                    already_enabled += 1
                else:
                    # Enable the skill
                    cursor.execute("""
                        UPDATE agent_skill
                        SET is_enabled = 1, updated_at = ?
                        WHERE agent_id = ? AND skill_type = 'flows'
                    """, (datetime.utcnow().isoformat() + "Z", agent_id))
                    print(f"   ✓ Agent {agent_id}: Enabled flows skill")
                    enabled_count += 1
            else:
                # Create new enabled skill
                cursor.execute("""
                    INSERT INTO agent_skill
                    (agent_id, skill_type, is_enabled, config, created_at, updated_at)
                    VALUES (?, 'flows', 1, '{}', ?, ?)
                """, (
                    agent_id,
                    datetime.utcnow().isoformat() + "Z",
                    datetime.utcnow().isoformat() + "Z"
                ))
                print(f"   ✓ Agent {agent_id}: Created and enabled flows skill")
                enabled_count += 1

        print(f"\n   Summary: {enabled_count} enabled, {already_enabled} already enabled")

        # Step 4: Clear hub_integration_id and default_asana_assignee_gid
        print(f"\n[4/5] Clearing deprecated fields...")

        cursor.execute("""
            UPDATE agent
            SET hub_integration_id = NULL,
                default_asana_assignee_gid = NULL
            WHERE hub_integration_id IS NOT NULL
        """)

        cleared_count = cursor.rowcount
        print(f"   ✓ Cleared hub_integration_id and default_asana_assignee_gid "
              f"from {cleared_count} agent(s)")

        # Step 5: Commit changes
        print(f"\n[5/5] Committing changes...")
        conn.commit()
        print("   ✓ All changes committed")

        print("\n" + "=" * 70)
        print("Migration completed successfully!")
        print("=" * 70)
        print(f"\nSummary:")
        print(f"  - Agents migrated: {migrated_count}")
        print(f"  - Skills enabled: {enabled_count}")
        print(f"  - Fields cleared: {cleared_count}")
        print(f"\nNext steps:")
        print(f"  1. Verify agents can use Scheduler skill with Asana provider")
        print(f"  2. Run drop_hub_integration_columns.py to remove deprecated columns")
        print(f"  3. Update frontend to remove Hub Integration UI")

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
        # Check no agents have hub_integration_id set
        cursor.execute("""
            SELECT COUNT(*) as count FROM agent
            WHERE hub_integration_id IS NOT NULL
        """)
        remaining = cursor.fetchone()['count']

        if remaining > 0:
            print(f"   ⚠ Warning: {remaining} agent(s) still have hub_integration_id set")
        else:
            print("   ✓ No agents have hub_integration_id set")

        # Check AgentSkillIntegration records
        cursor.execute("""
            SELECT COUNT(*) as count FROM agent_skill_integration
            WHERE skill_type = 'flows' AND scheduler_provider = 'asana'
        """)
        asana_configs = cursor.fetchone()['count']
        print(f"   ✓ Found {asana_configs} agent(s) with Asana scheduler provider")

        # Check enabled flows skills
        cursor.execute("""
            SELECT COUNT(*) as count FROM agent_skill
            WHERE skill_type = 'flows' AND is_enabled = 1
        """)
        enabled_flows = cursor.fetchone()['count']
        print(f"   ✓ Found {enabled_flows} agent(s) with flows skill enabled")

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
    migrate(db_path)

    # Verify
    verify(db_path)
