"""
Migration: Add Agent Channel Configuration
Phase 10: Configurable channels for agents

This migration adds:
- Agent.enabled_channels: JSON field for enabled channel types
- Agent.whatsapp_integration_id: FK to specific WhatsApp MCP instance
- Agent.telegram_integration_id: Reserved for future Telegram integration
- WhatsAppMCPInstance.is_group_handler: Flag for group message deduplication

Run: python -m migrations.add_agent_channels
"""

import sys
import os
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text


def migrate(db_path: str):
    """Add channel configuration columns to existing database."""

    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        try:
            print("[Migration] Adding agent channel configuration columns...")

            # Check and add enabled_channels column to agent table
            result = conn.execute(text("PRAGMA table_info(agent)"))
            columns = [row[1] for row in result.fetchall()]

            if "enabled_channels" not in columns:
                conn.execute(text(
                    "ALTER TABLE agent ADD COLUMN enabled_channels TEXT DEFAULT '[\"playground\", \"whatsapp\"]'"
                ))
                print("[Migration] Added agent.enabled_channels column")
            else:
                print("[Migration] agent.enabled_channels already exists")

            if "whatsapp_integration_id" not in columns:
                conn.execute(text(
                    "ALTER TABLE agent ADD COLUMN whatsapp_integration_id INTEGER REFERENCES whatsapp_mcp_instance(id)"
                ))
                print("[Migration] Added agent.whatsapp_integration_id column")
            else:
                print("[Migration] agent.whatsapp_integration_id already exists")

            if "telegram_integration_id" not in columns:
                conn.execute(text(
                    "ALTER TABLE agent ADD COLUMN telegram_integration_id INTEGER"
                ))
                print("[Migration] Added agent.telegram_integration_id column")
            else:
                print("[Migration] agent.telegram_integration_id already exists")

            # Check and add is_group_handler column to whatsapp_mcp_instance table
            result = conn.execute(text("PRAGMA table_info(whatsapp_mcp_instance)"))
            mcp_columns = [row[1] for row in result.fetchall()]

            if "is_group_handler" not in mcp_columns:
                conn.execute(text(
                    "ALTER TABLE whatsapp_mcp_instance ADD COLUMN is_group_handler BOOLEAN DEFAULT 0"
                ))
                print("[Migration] Added whatsapp_mcp_instance.is_group_handler column")
            else:
                print("[Migration] whatsapp_mcp_instance.is_group_handler already exists")

            conn.commit()

            # Backfill data: Assign first MCP instance per tenant to agents
            print("[Migration] Backfilling agent-to-MCP instance mappings...")

            # Get all tenants with their first agent MCP instance
            tenants_with_mcp = conn.execute(text("""
                SELECT tenant_id, MIN(id) as first_mcp_id
                FROM whatsapp_mcp_instance
                WHERE instance_type = 'agent'
                GROUP BY tenant_id
            """)).fetchall()

            for tenant_id, mcp_id in tenants_with_mcp:
                # Update agents without whatsapp_integration_id in this tenant
                conn.execute(text("""
                    UPDATE agent
                    SET whatsapp_integration_id = :mcp_id
                    WHERE tenant_id = :tenant_id
                    AND whatsapp_integration_id IS NULL
                """), {"mcp_id": mcp_id, "tenant_id": tenant_id})
                print(f"[Migration] Assigned MCP instance {mcp_id} to agents in tenant {tenant_id}")

                # Mark first MCP instance as group handler
                conn.execute(text("""
                    UPDATE whatsapp_mcp_instance
                    SET is_group_handler = 1
                    WHERE id = :mcp_id
                """), {"mcp_id": mcp_id})
                print(f"[Migration] Set MCP instance {mcp_id} as group handler for tenant {tenant_id}")

            # Set default enabled_channels for agents that have NULL
            conn.execute(text("""
                UPDATE agent
                SET enabled_channels = '[\"playground\", \"whatsapp\"]'
                WHERE enabled_channels IS NULL
            """))
            print("[Migration] Set default enabled_channels for all agents")

            conn.commit()
            print("[Migration] Agent channel configuration migration completed successfully!")
            return True

        except Exception as e:
            conn.rollback()
            print(f"[Migration] Error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    # Default database path
    db_path = os.environ.get("INTERNAL_DB_PATH", "/app/data/agent.db")

    # Allow override via command line
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print(f"[Migration] Database: {db_path}")
    success = migrate(db_path)
    sys.exit(0 if success else 1)
