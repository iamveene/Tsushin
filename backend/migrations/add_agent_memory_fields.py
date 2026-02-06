"""
Migration: Add per-agent memory configuration and fix Memory model

Phase 4.8: Per-agent memory system requires:
1. Agent table: Add semantic search configuration fields
2. Memory table: Add agent_id for per-agent memory isolation
3. SemanticKnowledge table: Ensure agent_id exists

This migration ensures all agents have their own memory configuration and storage.
"""

import sqlite3
import sys
import os
from pathlib import Path

def migrate():
    # Get database path from environment or use default
    db_path = os.getenv('INTERNAL_DB_PATH', './data/agent.db')

    print(f"Migrating database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        migrations_applied = []

        # ============================================================
        # PART 1: Add semantic search fields to Agent table
        # ============================================================
        print("\n[1/3] Checking Agent table...")
        cursor.execute("PRAGMA table_info(agent)")
        agent_columns = [row[1] for row in cursor.fetchall()]

        # Add enable_semantic_search to agent
        if 'enable_semantic_search' not in agent_columns:
            cursor.execute("""
                ALTER TABLE agent ADD COLUMN enable_semantic_search BOOLEAN DEFAULT 1
            """)
            migrations_applied.append("agent.enable_semantic_search")
            print("  [OK] Added enable_semantic_search")

        # Add semantic_search_results to agent
        if 'semantic_search_results' not in agent_columns:
            cursor.execute("""
                ALTER TABLE agent ADD COLUMN semantic_search_results INTEGER DEFAULT 10
            """)
            migrations_applied.append("agent.semantic_search_results")
            print("  [OK] Added semantic_search_results")

        # Add semantic_similarity_threshold to agent
        if 'semantic_similarity_threshold' not in agent_columns:
            cursor.execute("""
                ALTER TABLE agent ADD COLUMN semantic_similarity_threshold REAL DEFAULT 0.5
            """)
            migrations_applied.append("agent.semantic_similarity_threshold")
            print("  [OK] Added semantic_similarity_threshold")

        # Add chroma_db_path to agent
        if 'chroma_db_path' not in agent_columns:
            cursor.execute("""
                ALTER TABLE agent ADD COLUMN chroma_db_path TEXT
            """)
            migrations_applied.append("agent.chroma_db_path")
            print("  [OK] Added chroma_db_path")

        # ============================================================
        # PART 2: Add agent_id to Memory table
        # ============================================================
        print("\n[2/3] Checking Memory table...")
        cursor.execute("PRAGMA table_info(memory)")
        memory_columns = [row[1] for row in cursor.fetchall()]

        if 'agent_id' not in memory_columns:
            # SQLite doesn't support adding NOT NULL columns to existing tables easily
            # We need to recreate the table
            print("  ! Memory table needs restructuring to add agent_id")

            # Step 1: Create new table with agent_id
            cursor.execute("""
                CREATE TABLE memory_new (
                    id INTEGER PRIMARY KEY,
                    agent_id INTEGER NOT NULL,
                    sender_key TEXT NOT NULL,
                    messages_json TEXT DEFAULT '[]',
                    updated_at TEXT,
                    UNIQUE(agent_id, sender_key)
                )
            """)

            # Step 2: Get default agent ID (should be 1 for the first agent)
            cursor.execute("SELECT id FROM agent ORDER BY id LIMIT 1")
            default_agent_id = cursor.fetchone()
            if default_agent_id:
                default_agent_id = default_agent_id[0]
                print(f"  ! Using default agent_id={default_agent_id} for existing memories")

                # Step 3: Copy existing data with default agent_id
                cursor.execute(f"""
                    INSERT INTO memory_new (id, agent_id, sender_key, messages_json, updated_at)
                    SELECT id, {default_agent_id}, sender_key, messages_json, updated_at
                    FROM memory
                """)
            else:
                print("  ! No agents found, skipping data migration")

            # Step 4: Drop old table and rename new one
            cursor.execute("DROP TABLE memory")
            cursor.execute("ALTER TABLE memory_new RENAME TO memory")

            # Step 5: Create index
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_memory_sender_key ON memory(sender_key)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_memory_agent_id ON memory(agent_id)")

            migrations_applied.append("memory.agent_id")
            print("  [OK] Added agent_id to Memory table")
        else:
            print("  [OK] agent_id already exists")

        # ============================================================
        # PART 3: Ensure SemanticKnowledge has agent_id
        # ============================================================
        print("\n[3/3] Checking SemanticKnowledge table...")
        try:
            cursor.execute("PRAGMA table_info(semantic_knowledge)")
            semantic_columns = [row[1] for row in cursor.fetchall()]

            if 'agent_id' not in semantic_columns:
                print("  ! SemanticKnowledge table needs agent_id")
                cursor.execute("""
                    ALTER TABLE semantic_knowledge ADD COLUMN agent_id INTEGER
                """)
                # Set default agent_id for existing records
                cursor.execute("SELECT id FROM agent ORDER BY id LIMIT 1")
                default_agent_id = cursor.fetchone()
                if default_agent_id:
                    cursor.execute(f"""
                        UPDATE semantic_knowledge SET agent_id = {default_agent_id[0]} WHERE agent_id IS NULL
                    """)
                migrations_applied.append("semantic_knowledge.agent_id")
                print("  [OK] Added agent_id to SemanticKnowledge")
            else:
                print("  [OK] agent_id already exists")
        except sqlite3.OperationalError:
            print("  ! SemanticKnowledge table doesn't exist yet (will be created on first use)")

        # ============================================================
        # PART 4: Set default ChromaDB paths for existing agents
        # ============================================================
        print("\n[4/4] Setting default ChromaDB paths...")
        cursor.execute("SELECT id, contact_id FROM agent WHERE chroma_db_path IS NULL")
        agents_without_path = cursor.fetchall()

        for agent_id, contact_id in agents_without_path:
            # Get contact name for path
            cursor.execute("SELECT friendly_name FROM contact WHERE id = ?", (contact_id,))
            contact_name = cursor.fetchone()
            if contact_name:
                contact_name = contact_name[0].lower().replace(" ", "_")
                chroma_path = f"./data/chroma/{contact_name}_agent_{agent_id}"
                cursor.execute("UPDATE agent SET chroma_db_path = ? WHERE id = ?", (chroma_path, agent_id))
                print(f"  [OK] Set ChromaDB path for agent {agent_id}: {chroma_path}")

        conn.commit()

        if migrations_applied:
            print(f"\n[OK] Applied migrations: {', '.join(migrations_applied)}")
        else:
            print("\n[OK] All fields already exist")

        # Show current agent configurations
        print("\n=== Agent Configurations ===")
        cursor.execute("""
            SELECT
                a.id,
                c.friendly_name,
                a.memory_size,
                a.enable_semantic_search,
                a.semantic_search_results,
                a.semantic_similarity_threshold,
                a.chroma_db_path
            FROM agent a
            JOIN contact c ON a.contact_id = c.id
        """)
        agents = cursor.fetchall()
        for agent in agents:
            print(f"\nAgent ID: {agent[0]} ({agent[1]})")
            print(f"  Memory Size: {agent[2]}")
            print(f"  Semantic Search: {'Enabled' if agent[3] else 'Disabled'}")
            print(f"  Semantic Results: {agent[4]}")
            print(f"  Similarity Threshold: {agent[5]}")
            print(f"  ChromaDB Path: {agent[6]}")

    except Exception as e:
        print(f"\n[FAIL] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
