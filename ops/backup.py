"""
Backup Script - Create timestamped backups before implementation changes

Usage:
    python ops/backup.py                    # Backup everything
    python ops/backup.py --backend-only     # Backup only backend
    python ops/backup.py --frontend-only    # Backup only frontend
    python ops/backup.py --db-only          # Backup only database
"""

import os
import shutil
import argparse
from datetime import datetime
from pathlib import Path


def create_backup(backup_root: Path, source: Path, backup_name: str):
    """Create a timestamped backup of a directory or file"""
    if not source.exists():
        print(f"[WARN] Source not found: {source}")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_root / f"{backup_name}_{timestamp}"

    try:
        if source.is_dir():
            # Exclude common directories
            exclude_dirs = {'.git', 'node_modules', '__pycache__', '.next', 'dist', 'build', 'venv', 'env'}

            def ignore_patterns(dir, files):
                return [f for f in files if f in exclude_dirs]

            shutil.copytree(source, backup_dir, ignore=ignore_patterns)
            print(f"[OK] Backed up directory: {source} -> {backup_dir}")
        else:
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup_dir / source.name)
            print(f"[OK] Backed up file: {source} -> {backup_dir}")

        return backup_dir

    except Exception as e:
        print(f"[ERROR] Failed to backup {source}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Backup WhatsBot project")
    parser.add_argument("--backend-only", action="store_true", help="Backup only backend")
    parser.add_argument("--frontend-only", action="store_true", help="Backup only frontend")
    parser.add_argument("--db-only", action="store_true", help="Backup only database")
    args = parser.parse_args()

    # Project root is parent of ops/
    project_root = Path(__file__).parent.parent
    backup_root = project_root / "backups"
    backup_root.mkdir(exist_ok=True)

    print(f"\n=== WhatsBot Backup ===")
    print(f"Project: {project_root}")
    print(f"Backup location: {backup_root}\n")

    # Determine what to backup
    backup_all = not (args.backend_only or args.frontend_only or args.db_only)

    if backup_all or args.backend_only:
        create_backup(backup_root, project_root / "backend", "backend")

    if backup_all or args.frontend_only:
        create_backup(backup_root, project_root / "frontend", "frontend")

    if backup_all or args.db_only:
        # Backup the internal database
        db_path = project_root / "backend" / "data" / "agent.db"
        create_backup(backup_root, db_path, "agent_db")

    print(f"\n[OK] Backup complete: {backup_root}\n")

    # Show backup size
    total_size = sum(f.stat().st_size for f in backup_root.rglob('*') if f.is_file())
    print(f"Total backup size: {total_size / (1024*1024):.2f} MB")


if __name__ == "__main__":
    main()
