#!/usr/bin/env python3
"""
Fix shell skill wait_for_result config for all agents.
Sets wait_for_result=True so /shell returns output directly.
"""
import os
import sys
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def main():
    # Get database URL from environment
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL environment variable is required")
        sys.exit(1)

    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Find all shell skills
        result = session.execute(text("""
            SELECT s.id, s.agent_id, s.config, a.tenant_id
            FROM agent_skill s
            JOIN agent a ON a.id = s.agent_id
            WHERE s.skill_type = 'shell'
        """))

        rows = result.fetchall()
        print(f"Found {len(rows)} shell skill(s)")

        for row in rows:
            skill_id = row[0]
            agent_id = row[1]
            current_config = row[2] or {}
            tenant_id = row[3]

            print(f"\nAgent {agent_id} (tenant: {tenant_id}):")
            print(f"  Current config: {json.dumps(current_config)}")

            # Update config with wait_for_result=True
            new_config = {
                "wait_for_result": True,
                "default_timeout": current_config.get("default_timeout", 60),
                "execution_mode": current_config.get("execution_mode", "programmatic")
            }

            session.execute(text("""
                UPDATE agent_skill
                SET config = :config
                WHERE id = :skill_id
            """), {"config": json.dumps(new_config), "skill_id": skill_id})

            print(f"  Updated config: {json.dumps(new_config)}")

        session.commit()
        print(f"\n✅ Successfully updated {len(rows)} shell skill(s)")

        # Verify
        print("\n--- Verification ---")
        result = session.execute(text("""
            SELECT a.id as agent_id, s.config
            FROM agent_skill s
            JOIN agent a ON a.id = s.agent_id
            WHERE s.skill_type = 'shell'
        """))

        for row in result.fetchall():
            print(f"Agent {row[0]}: {row[1]}")

    except Exception as e:
        print(f"❌ Error: {e}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    main()
