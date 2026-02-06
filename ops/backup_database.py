"""
Database Backup Script

Creates timestamped backups of the agent database before any implementation changes.
Usage: python ops/backup_database.py [--message "Description of what will be changed"]
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
import argparse
import json
import sys


def verify_database_integrity(db_path: Path) -> dict:
    """Verify database integrity and collect statistics."""
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check integrity
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]

        # Collect statistics
        stats = {
            "integrity": integrity,
            "tables": {}
        }

        # Get table list
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # Count rows in each table
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                stats["tables"][table] = count
            except Exception as e:
                stats["tables"][table] = f"Error: {e}"

        conn.close()
        return stats
    except Exception as e:
        return {"error": str(e)}


def backup_database(source_path: Path, backup_dir: Path, message: str = None) -> tuple[Path, dict]:
    """
    Create a timestamped backup of the database.

    Returns:
        tuple: (backup_path, pre_backup_stats)
    """
    # Ensure backup directory exists
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Create backup filename
    backup_filename = f"agent_backup_{timestamp}.db"
    backup_path = backup_dir / backup_filename

    # Verify source database before backup
    print(f"Verifying source database integrity...")
    pre_stats = verify_database_integrity(source_path)

    if "error" in pre_stats:
        print(f"[ERROR] Cannot verify source database: {pre_stats['error']}")
        sys.exit(1)

    if pre_stats["integrity"] != "ok":
        print(f"[WARNING] Database integrity check failed: {pre_stats['integrity']}")
        print("Proceeding with backup anyway...")

    # Display statistics
    print(f"\n[STATS] Database Statistics (Pre-Backup):")
    print(f"   Integrity: {pre_stats['integrity']}")
    for table, count in pre_stats.get("tables", {}).items():
        print(f"   - {table}: {count} rows")

    # Copy database file
    print(f"\n[BACKUP] Creating backup: {backup_filename}")
    shutil.copy2(source_path, backup_path)

    # Verify backup
    print(f"Verifying backup integrity...")
    post_stats = verify_database_integrity(backup_path)

    if "error" in post_stats:
        print(f"[ERROR] Backup verification failed: {post_stats['error']}")
        backup_path.unlink()  # Delete failed backup
        sys.exit(1)

    # Compare statistics
    if post_stats != pre_stats:
        print(f"[WARNING] Backup statistics don't match source!")
        print(f"Source: {pre_stats}")
        print(f"Backup: {post_stats}")

    # Create metadata file
    metadata = {
        "timestamp": timestamp,
        "source_path": str(source_path),
        "backup_path": str(backup_path),
        "message": message,
        "pre_backup_stats": pre_stats,
        "post_backup_stats": post_stats,
        "backup_size_bytes": backup_path.stat().st_size
    }

    metadata_path = backup_dir / f"agent_backup_{timestamp}.json"
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    print(f"[SUCCESS] Backup created successfully!")
    print(f"   Location: {backup_path}")
    print(f"   Size: {backup_path.stat().st_size / 1024:.2f} KB")
    print(f"   Metadata: {metadata_path}")

    if message:
        print(f"   Message: {message}")

    return backup_path, pre_stats


def list_backups(backup_dir: Path):
    """List all available backups."""
    if not backup_dir.exists():
        print("No backups found.")
        return

    backups = sorted(backup_dir.glob("agent_backup_*.json"), reverse=True)

    if not backups:
        print("No backups found.")
        return

    print(f"\n[BACKUPS] Available Backups ({len(backups)}):\n")

    for metadata_file in backups:
        try:
            with open(metadata_file, encoding='utf-8') as f:
                metadata = json.load(f)

            timestamp = metadata.get("timestamp", "Unknown")
            message = metadata.get("message", "No description")
            size = metadata.get("backup_size_bytes", 0) / 1024
            tables = metadata.get("pre_backup_stats", {}).get("tables", {})

            print(f"  [{timestamp}]")
            print(f"     Message: {message}")
            print(f"     Size: {size:.2f} KB")
            print(f"     Tables: {len(tables)}")
            print(f"     File: {metadata_file.parent / metadata_file.stem}.db")
            print()
        except Exception as e:
            print(f"  [WARNING] Error reading {metadata_file}: {e}\n")


def restore_backup(backup_path: Path, target_path: Path):
    """Restore a backup to the target location."""
    if not backup_path.exists():
        print(f"[ERROR] Backup file not found: {backup_path}")
        sys.exit(1)

    # Verify backup integrity
    print(f"Verifying backup integrity...")
    stats = verify_database_integrity(backup_path)

    if "error" in stats:
        print(f"[ERROR] Backup is corrupted: {stats['error']}")
        sys.exit(1)

    print(f"[SUCCESS] Backup integrity verified: {stats['integrity']}")

    # Create backup of current database before restore
    if target_path.exists():
        print(f"\n[WARNING] Target database exists. Creating safety backup...")
        safety_backup = target_path.parent / f"{target_path.stem}_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(target_path, safety_backup)
        print(f"Safety backup: {safety_backup}")

    # Restore
    print(f"\n[RESTORE] Restoring backup to {target_path}...")
    shutil.copy2(backup_path, target_path)

    # Verify restored database
    print(f"Verifying restored database...")
    restored_stats = verify_database_integrity(target_path)

    if "error" in restored_stats:
        print(f"[ERROR] Restore verification failed: {restored_stats['error']}")
        sys.exit(1)

    print(f"[SUCCESS] Database restored successfully!")
    print(f"\n[STATS] Restored Database Statistics:")
    print(f"   Integrity: {restored_stats['integrity']}")
    for table, count in restored_stats.get("tables", {}).items():
        print(f"   - {table}: {count} rows")


def main():
    parser = argparse.ArgumentParser(description="Database backup and restore utility")
    parser.add_argument("--message", "-m", help="Description of what will be changed")
    parser.add_argument("--list", "-l", action="store_true", help="List available backups")
    parser.add_argument("--restore", "-r", help="Restore backup by timestamp (YYYYMMDD_HHMMSS)")
    parser.add_argument("--db-path", default="./data/agent.db", help="Path to database file")
    parser.add_argument("--backup-dir", default="./data/backups", help="Backup directory")

    args = parser.parse_args()

    source_path = Path(args.db_path)
    backup_dir = Path(args.backup_dir)

    if args.list:
        list_backups(backup_dir)
    elif args.restore:
        backup_file = backup_dir / f"agent_backup_{args.restore}.db"
        restore_backup(backup_file, source_path)
    else:
        if not source_path.exists():
            print(f"ERROR: Database file not found: {source_path}")
            sys.exit(1)

        backup_database(source_path, backup_dir, args.message)


if __name__ == "__main__":
    main()
