"""
Migration: Auto-link channel instances to agents + fix contact defaults
Backfills telegram_integration_id and whatsapp_integration_id for agents
that have the channel enabled but are not yet linked to any instance.
Also sets is_dm_trigger=True for all user contacts (new default).

Follows the same pattern as add_agent_channels.py WhatsApp backfill.

Run: python -m migrations.add_telegram_agent_linking
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text


def migrate(db_path: str):
    """Backfill integration IDs for agents with channels enabled."""

    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        try:
            # ---- Telegram auto-linking ----
            print("[Migration] Auto-linking Telegram instances to agents...")

            tenants_with_telegram = conn.execute(text("""
                SELECT tenant_id, MIN(id) as first_instance_id
                FROM telegram_bot_instance
                WHERE status != 'deleted'
                GROUP BY tenant_id
            """)).fetchall()

            if not tenants_with_telegram:
                print("[Migration] No Telegram instances found, skipping Telegram linking")
            else:
                for tenant_id, instance_id in tenants_with_telegram:
                    result = conn.execute(text("""
                        UPDATE agent
                        SET telegram_integration_id = :instance_id
                        WHERE tenant_id = :tenant_id
                        AND telegram_integration_id IS NULL
                        AND is_active = 1
                        AND enabled_channels LIKE '%telegram%'
                    """), {"instance_id": instance_id, "tenant_id": tenant_id})
                    print(f"[Migration] Linked Telegram instance {instance_id} to {result.rowcount} agent(s) in tenant {tenant_id}")

            # ---- WhatsApp auto-linking ----
            print("[Migration] Auto-linking WhatsApp instances to agents...")

            tenants_with_whatsapp = conn.execute(text("""
                SELECT tenant_id, MIN(id) as first_instance_id
                FROM whatsapp_mcp_instance
                WHERE instance_type = 'agent'
                AND status IN ('running', 'starting', 'created')
                GROUP BY tenant_id
            """)).fetchall()

            if not tenants_with_whatsapp:
                print("[Migration] No WhatsApp agent instances found, skipping WhatsApp linking")
            else:
                for tenant_id, instance_id in tenants_with_whatsapp:
                    result = conn.execute(text("""
                        UPDATE agent
                        SET whatsapp_integration_id = :instance_id
                        WHERE tenant_id = :tenant_id
                        AND whatsapp_integration_id IS NULL
                        AND is_active = 1
                        AND enabled_channels LIKE '%whatsapp%'
                    """), {"instance_id": instance_id, "tenant_id": tenant_id})
                    print(f"[Migration] Linked WhatsApp instance {instance_id} to {result.rowcount} agent(s) in tenant {tenant_id}")

                    # Ensure group handler is set
                    existing_handler = conn.execute(text("""
                        SELECT id FROM whatsapp_mcp_instance
                        WHERE tenant_id = :tenant_id AND is_group_handler = 1
                        LIMIT 1
                    """), {"tenant_id": tenant_id}).fetchone()

                    if not existing_handler:
                        conn.execute(text("""
                            UPDATE whatsapp_mcp_instance
                            SET is_group_handler = 1
                            WHERE id = :instance_id
                        """), {"instance_id": instance_id})
                        print(f"[Migration] Set WhatsApp instance {instance_id} as group handler for tenant {tenant_id}")

            # ---- Contact is_dm_trigger backfill ----
            print("[Migration] Setting is_dm_trigger=True for all user contacts...")

            result = conn.execute(text("""
                UPDATE contact
                SET is_dm_trigger = 1
                WHERE role = 'user'
                AND is_dm_trigger = 0
                AND is_active = 1
            """))
            print(f"[Migration] Updated {result.rowcount} user contact(s) to is_dm_trigger=True")

            conn.commit()
            print("[Migration] Channel agent linking migration completed successfully!")
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
