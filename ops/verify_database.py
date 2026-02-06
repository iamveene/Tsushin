"""
Database Verification Script

Verifies database integrity and critical data after implementations.
Usage: python ops/verify_database.py
"""

import sqlite3
import sys
from pathlib import Path


def verify_database(db_path: Path) -> dict:
    """
    Comprehensive database verification.

    Returns:
        dict with verification results
    """
    results = {
        "success": True,
        "errors": [],
        "warnings": [],
        "info": {}
    }

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # 1. Check integrity
        print("[CHECK] Database integrity...")
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]
        results["info"]["integrity"] = integrity
        if integrity != "ok":
            results["errors"].append(f"Integrity check failed: {integrity}")
            results["success"] = False
        else:
            print("  [OK] Database integrity verified")

        # 2. Check critical tables exist
        print("\n[CHECK] Critical tables...")
        required_tables = [
            "config", "agent", "contact", "api_key",
            "agent_skill", "memory", "message_cache",
            "agent_run", "agent_knowledge", "knowledge_chunk"
        ]
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]
        results["info"]["tables"] = existing_tables

        for table in required_tables:
            if table not in existing_tables:
                results["errors"].append(f"Missing critical table: {table}")
                results["success"] = False
            else:
                print(f"  [OK] Table '{table}' exists")

        # 3. Check API Keys
        print("\n[CHECK] API Keys...")
        cursor.execute("SELECT service, is_active FROM api_key WHERE is_active = 1")
        api_keys = cursor.fetchall()
        results["info"]["api_keys"] = [{"service": row[0], "active": row[1]} for row in api_keys]

        required_keys = ["openai", "gemini"]  # Add more as needed
        found_keys = [key[0] for key in api_keys]

        for key in required_keys:
            if key in found_keys:
                print(f"  [OK] API key for '{key}' is active")
            else:
                results["warnings"].append(f"Missing or inactive API key: {key}")
                print(f"  [WARNING] API key for '{key}' not found or inactive")

        # 4. Check Agents
        print("\n[CHECK] Agents...")
        cursor.execute("SELECT COUNT(*) FROM agent WHERE is_active = 1")
        agent_count = cursor.fetchone()[0]
        results["info"]["active_agents"] = agent_count

        if agent_count == 0:
            results["errors"].append("No active agents found")
            results["success"] = False
        else:
            print(f"  [OK] {agent_count} active agent(s)")

            # Check agent skills
            cursor.execute("""
                SELECT a.id, c.friendly_name, COUNT(s.id) as skill_count
                FROM agent a
                LEFT JOIN contact c ON a.contact_id = c.id
                LEFT JOIN agent_skill s ON a.id = s.agent_id AND s.is_enabled = 1
                WHERE a.is_active = 1
                GROUP BY a.id
            """)
            for agent_id, agent_name, skill_count in cursor.fetchall():
                print(f"  [INFO] Agent '{agent_name}' (ID: {agent_id}) has {skill_count} enabled skill(s)")

                # Check for audio_transcript skill
                cursor.execute("""
                    SELECT skill_type FROM agent_skill
                    WHERE agent_id = ? AND skill_type = 'audio_transcript' AND is_enabled = 1
                """, (agent_id,))
                if cursor.fetchone():
                    print(f"    [OK] audio_transcript enabled")
                else:
                    results["warnings"].append(f"Agent '{agent_name}' does not have audio_transcript enabled")

        # 5. Check Contacts
        print("\n[CHECK] Contacts...")
        cursor.execute("SELECT COUNT(*) FROM contact WHERE is_active = 1")
        contact_count = cursor.fetchone()[0]
        results["info"]["active_contacts"] = contact_count

        if contact_count == 0:
            results["warnings"].append("No active contacts found")
        else:
            print(f"  [OK] {contact_count} active contact(s)")

        # 6. Check Memory/Message Data
        print("\n[CHECK] Memory & Messages...")
        cursor.execute("SELECT COUNT(*) FROM memory")
        memory_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM message_cache")
        message_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM agent_run")
        run_count = cursor.fetchone()[0]

        results["info"]["memory_records"] = memory_count
        results["info"]["cached_messages"] = message_count
        results["info"]["agent_runs"] = run_count

        print(f"  [INFO] Memory records: {memory_count}")
        print(f"  [INFO] Cached messages: {message_count}")
        print(f"  [INFO] Agent runs: {run_count}")

        # 7. Check Knowledge Base
        print("\n[CHECK] Knowledge Base...")
        cursor.execute("SELECT COUNT(*) FROM agent_knowledge WHERE status = 'processed'")
        knowledge_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM knowledge_chunk")
        chunk_count = cursor.fetchone()[0]

        results["info"]["knowledge_documents"] = knowledge_count
        results["info"]["knowledge_chunks"] = chunk_count

        print(f"  [INFO] Processed knowledge documents: {knowledge_count}")
        print(f"  [INFO] Knowledge chunks: {chunk_count}")

        conn.close()

    except Exception as e:
        results["success"] = False
        results["errors"].append(f"Verification failed: {str(e)}")
        print(f"\n[ERROR] Verification failed: {e}")

    return results


def main():
    db_path = Path("./data/agent.db")

    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    print("=" * 60)
    print("DATABASE VERIFICATION")
    print("=" * 60)
    print(f"Database: {db_path}\n")

    results = verify_database(db_path)

    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    if results["success"]:
        print("[SUCCESS] All critical checks passed!")
    else:
        print("[FAILED] Some critical checks failed!")

    if results["errors"]:
        print(f"\n[ERRORS] ({len(results['errors'])})")
        for error in results["errors"]:
            print(f"  - {error}")

    if results["warnings"]:
        print(f"\n[WARNINGS] ({len(results['warnings'])})")
        for warning in results["warnings"]:
            print(f"  - {warning}")

    print("\n[INFO] Database Statistics:")
    info = results["info"]
    print(f"  - Integrity: {info.get('integrity', 'N/A')}")
    print(f"  - Tables: {len(info.get('tables', []))}")
    print(f"  - Active Agents: {info.get('active_agents', 0)}")
    print(f"  - Active Contacts: {info.get('active_contacts', 0)}")
    print(f"  - API Keys: {len(info.get('api_keys', []))}")
    print(f"  - Memory Records: {info.get('memory_records', 0)}")
    print(f"  - Cached Messages: {info.get('cached_messages', 0)}")
    print(f"  - Agent Runs: {info.get('agent_runs', 0)}")
    print(f"  - Knowledge Docs: {info.get('knowledge_documents', 0)}")

    sys.exit(0 if results["success"] and not results["errors"] else 1)


if __name__ == "__main__":
    main()
