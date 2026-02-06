#!/usr/bin/env python3
"""
Fact Memory Cleanup Script
--------------------------
Cleans up garbage/test facts from the semantic_knowledge table.

Features:
- Creates automatic backup before cleanup
- Removes test artifacts and repetition loops
- Trims overly long fact values (>200 chars)
- Removes duplicate facts
- Validates fact quality
- Provides detailed cleanup report

Usage:
    python backend/maintenance/cleanup_fact_memory.py [--dry-run] [--backup-dir PATH]

    OR inside container:
    docker compose exec backend python /app/maintenance/cleanup_fact_memory.py [--dry-run]
"""

import sqlite3
import sys
import os
from datetime import datetime
from pathlib import Path
import argparse
import json

DB_PATH = "/app/data/agent.db" if os.path.exists("/app/data") else "backend/data/agent.db"
DEFAULT_BACKUP_DIR = "/app/data/backups/fact_memory" if os.path.exists("/app/data") else "backups/fact_memory"


class FactMemoryCleanup:
    """Comprehensive fact memory cleanup with backup and validation."""

    def __init__(self, db_path: str, dry_run: bool = False):
        self.db_path = db_path
        self.dry_run = dry_run
        self.conn = None
        self.stats = {
            'total_before': 0,
            'test_artifacts_removed': 0,
            'long_values_trimmed': 0,
            'duplicates_removed': 0,
            'invalid_removed': 0,
            'total_after': 0,
            'backup_path': None
        }

    def connect(self):
        """Connect to database."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        print(f"✅ Connected to database: {self.db_path}")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("✅ Database connection closed")

    def create_backup(self, backup_dir: str) -> str:
        """Create backup of semantic_knowledge table."""
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"semantic_knowledge_backup_{timestamp}.json")

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM semantic_knowledge")
        rows = cursor.fetchall()

        # Convert to JSON
        backup_data = []
        for row in rows:
            backup_data.append({
                'id': row['id'],
                'agent_id': row['agent_id'],
                'user_id': row['user_id'],
                'topic': row['topic'],
                'key': row['key'],
                'value': row['value'],
                'confidence': row['confidence'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at']
            })

        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)

        self.stats['backup_path'] = backup_path
        print(f"✅ Backup created: {backup_path} ({len(backup_data)} facts)")
        return backup_path

    def get_initial_count(self) -> int:
        """Get initial fact count."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM semantic_knowledge")
        count = cursor.fetchone()['count']
        self.stats['total_before'] = count
        print(f"📊 Initial fact count: {count}")
        return count

    def remove_test_artifacts(self):
        """Remove obvious test artifacts and garbage facts."""
        print("\n🧹 Removing test artifacts...")

        patterns_to_remove = [
            # Repetition/mirroring test artifacts
            ("key LIKE '%repetition%'", "repetition patterns"),
            ("key LIKE '%mirroring%' OR key LIKE '%mirror%'", "mirroring patterns"),
            ("key LIKE '%echo%'", "echo patterns"),
            ("value LIKE '%repetition game%'", "repetition games"),
            ("value LIKE '%copies the assistant%'", "assistant copying"),
            ("value LIKE '%mimics%' OR value LIKE '%mimick%'", "mimicry"),

            # Test behavior markers
            ("value LIKE '%consecutive times%' AND LENGTH(value) > 150", "consecutive test markers"),
            ("value LIKE '%iteration of%' AND LENGTH(value) > 150", "iteration markers"),
            ("key LIKE '%_loop' OR key LIKE '%_game'", "loop/game artifacts"),

            # Overly meta facts about conversation itself
            ("topic = 'inside_jokes' AND (value LIKE '%testing%' OR value LIKE '%repeatedly%')", "test inside jokes"),
            ("topic = 'communication_style' AND value LIKE '%echoes%'", "echo communication style"),
            ("value LIKE '%iteration counter%' OR value LIKE '%consecutive repetition%'", "counter artifacts"),
        ]

        total_removed = 0
        for pattern, description in patterns_to_remove:
            cursor = self.conn.cursor()
            cursor.execute(f"SELECT COUNT(*) as count FROM semantic_knowledge WHERE {pattern}")
            count = cursor.fetchone()['count']

            if count > 0:
                print(f"  • Removing {count} facts: {description}")
                if not self.dry_run:
                    cursor.execute(f"DELETE FROM semantic_knowledge WHERE {pattern}")
                total_removed += count

        self.stats['test_artifacts_removed'] = total_removed
        if not self.dry_run:
            self.conn.commit()
        print(f"✅ Removed {total_removed} test artifact facts")

    def trim_long_values(self, max_length: int = 200):
        """Trim overly long fact values."""
        print(f"\n✂️  Trimming values longer than {max_length} chars...")

        cursor = self.conn.cursor()
        cursor.execute(f"SELECT COUNT(*) as count FROM semantic_knowledge WHERE LENGTH(value) > {max_length}")
        count = cursor.fetchone()['count']

        if count > 0:
            print(f"  • Found {count} facts with long values")

            # Show some examples
            cursor.execute(f"""
                SELECT agent_id, user_id, topic, key, LENGTH(value) as len, SUBSTR(value, 1, 100) as preview
                FROM semantic_knowledge
                WHERE LENGTH(value) > {max_length}
                ORDER BY LENGTH(value) DESC
                LIMIT 5
            """)
            examples = cursor.fetchall()
            print(f"\n  Examples of long facts:")
            for ex in examples:
                print(f"    - [{ex['topic']}] {ex['key']} ({ex['len']} chars): {ex['preview']}...")

            if not self.dry_run:
                cursor.execute(f"""
                    UPDATE semantic_knowledge
                    SET value = SUBSTR(value, 1, {max_length}) || '...',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE LENGTH(value) > {max_length}
                """)
                self.conn.commit()

        self.stats['long_values_trimmed'] = count
        print(f"✅ Trimmed {count} long fact values")

    def remove_duplicates(self):
        """Remove duplicate facts (same agent, user, topic, key but different IDs)."""
        print("\n🔄 Removing duplicate facts...")

        cursor = self.conn.cursor()

        # Find duplicates (keep the most recent one)
        duplicates_query = """
            SELECT agent_id, user_id, topic, key, COUNT(*) as count
            FROM semantic_knowledge
            GROUP BY agent_id, user_id, topic, key
            HAVING COUNT(*) > 1
        """
        cursor.execute(duplicates_query)
        duplicates = cursor.fetchall()

        if duplicates:
            print(f"  • Found {len(duplicates)} sets of duplicate facts")

            removed = 0
            for dup in duplicates:
                # Keep the most recent, delete older ones
                if not self.dry_run:
                    cursor.execute("""
                        DELETE FROM semantic_knowledge
                        WHERE agent_id = ? AND user_id = ? AND topic = ? AND key = ?
                        AND id NOT IN (
                            SELECT id FROM semantic_knowledge
                            WHERE agent_id = ? AND user_id = ? AND topic = ? AND key = ?
                            ORDER BY updated_at DESC
                            LIMIT 1
                        )
                    """, (dup['agent_id'], dup['user_id'], dup['topic'], dup['key'],
                          dup['agent_id'], dup['user_id'], dup['topic'], dup['key']))
                    removed += cursor.rowcount

            if not self.dry_run:
                self.conn.commit()
        else:
            removed = 0

        self.stats['duplicates_removed'] = removed
        print(f"✅ Removed {removed} duplicate facts")

    def remove_invalid_facts(self):
        """Remove facts with invalid/empty values or keys."""
        print("\n🚫 Removing invalid facts...")

        cursor = self.conn.cursor()

        invalid_conditions = [
            ("value IS NULL OR value = ''", "empty values"),
            ("key IS NULL OR key = ''", "empty keys"),
            ("topic IS NULL OR topic = ''", "empty topics"),
            ("LENGTH(TRIM(value)) = 0", "whitespace-only values"),
            ("confidence < 0 OR confidence > 1", "invalid confidence"),
        ]

        total_removed = 0
        for condition, description in invalid_conditions:
            cursor.execute(f"SELECT COUNT(*) as count FROM semantic_knowledge WHERE {condition}")
            count = cursor.fetchone()['count']

            if count > 0:
                print(f"  • Removing {count} facts with {description}")
                if not self.dry_run:
                    cursor.execute(f"DELETE FROM semantic_knowledge WHERE {condition}")
                total_removed += count

        if not self.dry_run:
            self.conn.commit()

        self.stats['invalid_removed'] = total_removed
        print(f"✅ Removed {total_removed} invalid facts")

    def optimize_database(self):
        """Optimize database after cleanup."""
        if not self.dry_run:
            print("\n🔧 Optimizing database...")
            cursor = self.conn.cursor()
            cursor.execute("VACUUM")
            cursor.execute("ANALYZE semantic_knowledge")
            self.conn.commit()
            print("✅ Database optimized")

    def get_final_stats(self):
        """Get final statistics after cleanup."""
        cursor = self.conn.cursor()

        # Total count
        cursor.execute("SELECT COUNT(*) as count FROM semantic_knowledge")
        self.stats['total_after'] = cursor.fetchone()['count']

        # Facts by agent
        cursor.execute("""
            SELECT agent_id, COUNT(*) as count
            FROM semantic_knowledge
            GROUP BY agent_id
            ORDER BY count DESC
        """)
        agent_counts = cursor.fetchall()

        # Facts by topic
        cursor.execute("""
            SELECT topic, COUNT(*) as count
            FROM semantic_knowledge
            GROUP BY topic
            ORDER BY count DESC
        """)
        topic_counts = cursor.fetchall()

        return agent_counts, topic_counts

    def print_report(self, agent_counts, topic_counts):
        """Print detailed cleanup report."""
        print("\n" + "="*60)
        print("📋 CLEANUP REPORT")
        print("="*60)

        if self.dry_run:
            print("⚠️  DRY RUN MODE - No changes were made")

        print(f"\n📊 Summary:")
        print(f"  Total facts before:        {self.stats['total_before']}")
        print(f"  Test artifacts removed:    {self.stats['test_artifacts_removed']}")
        print(f"  Long values trimmed:       {self.stats['long_values_trimmed']}")
        print(f"  Duplicates removed:        {self.stats['duplicates_removed']}")
        print(f"  Invalid facts removed:     {self.stats['invalid_removed']}")
        print(f"  ─────────────────────────")
        total_removed = (self.stats['test_artifacts_removed'] +
                        self.stats['duplicates_removed'] +
                        self.stats['invalid_removed'])
        print(f"  Total removed:             {total_removed}")
        print(f"  Total facts after:         {self.stats['total_after']}")
        print(f"  Net change:                {self.stats['total_after'] - self.stats['total_before']}")

        if self.stats['backup_path']:
            print(f"\n💾 Backup: {self.stats['backup_path']}")

        print(f"\n📈 Facts by Agent:")
        for agent in agent_counts[:10]:
            print(f"  • Agent {agent['agent_id']}: {agent['count']} facts")

        print(f"\n🏷️  Facts by Topic:")
        for topic in topic_counts:
            print(f"  • {topic['topic']}: {topic['count']} facts")

        print("\n" + "="*60)

    def run(self, backup_dir: str):
        """Run complete cleanup process."""
        try:
            self.connect()

            # Get initial count
            self.get_initial_count()

            # Create backup
            if not self.dry_run:
                self.create_backup(backup_dir)
            else:
                print("⚠️  DRY RUN: Skipping backup")

            # Run cleanup steps
            self.remove_test_artifacts()
            self.trim_long_values(max_length=200)
            self.remove_duplicates()
            self.remove_invalid_facts()

            # Optimize database
            self.optimize_database()

            # Get final stats
            agent_counts, topic_counts = self.get_final_stats()

            # Print report
            self.print_report(agent_counts, topic_counts)

            print("\n✅ Cleanup complete!")

        except Exception as e:
            print(f"\n❌ Error during cleanup: {e}")
            import traceback
            traceback.print_exc()
            if self.conn:
                self.conn.rollback()
            raise
        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(
        description='Clean up garbage facts from semantic_knowledge table',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (preview changes without applying)
  python backend/maintenance/cleanup_fact_memory.py --dry-run

  # Run cleanup with default backup location
  python backend/maintenance/cleanup_fact_memory.py

  # Run cleanup with custom backup directory
  python backend/maintenance/cleanup_fact_memory.py --backup-dir /path/to/backups

  # Inside Docker container
  docker compose exec backend python /app/maintenance/cleanup_fact_memory.py --dry-run
        """
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying them'
    )

    parser.add_argument(
        '--backup-dir',
        default=DEFAULT_BACKUP_DIR,
        help=f'Backup directory (default: {DEFAULT_BACKUP_DIR})'
    )

    parser.add_argument(
        '--db-path',
        default=DB_PATH,
        help=f'Database path (default: {DB_PATH})'
    )

    args = parser.parse_args()

    # Verify database exists
    if not os.path.exists(args.db_path):
        print(f"❌ Database not found: {args.db_path}")
        sys.exit(1)

    print("🧹 Fact Memory Cleanup Tool")
    print("="*60)

    if args.dry_run:
        print("⚠️  DRY RUN MODE - No changes will be made")
        print("="*60)

    # Run cleanup
    cleanup = FactMemoryCleanup(args.db_path, dry_run=args.dry_run)
    cleanup.run(args.backup_dir)


if __name__ == "__main__":
    main()
