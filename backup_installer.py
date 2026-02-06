#!/usr/bin/env python3
"""
Tsushin Backup & Restore Utility
Phase 0: Safety Infrastructure

Provides backup and restore functionality for Tsushin installations.
Use this before making any risky changes to the system.

Usage:
    python backup_installer.py create [backup_name]
    python backup_installer.py restore <backup_dir>
    python backup_installer.py list
"""

import os
import sys
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from platform_utils import detect_docker_compose_cmd


class TsushinBackup:
    def __init__(self):
        self.root_dir = Path(__file__).parent
        self.backup_base_dir = self.root_dir / "backups"
        self.backup_base_dir.mkdir(exist_ok=True)
        self.docker_compose_cmd = detect_docker_compose_cmd() or ["docker-compose"]

    def create_backup(self, backup_name: str = None) -> str:
        """
        Create timestamped backup of current installation

        Args:
            backup_name: Optional custom backup name

        Returns:
            Path to created backup directory
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = backup_name or f"tsushin_backup_{timestamp}"
        backup_dir = self.backup_base_dir / backup_name

        print(f"\n🗄️  Creating backup: {backup_name}")
        print("=" * 60)

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Backup .env file
            if (self.root_dir / ".env").exists():
                shutil.copy(self.root_dir / ".env", backup_dir / ".env")
                print("✅ Backed up .env file")
            else:
                print("⚠️  No .env file found (skipping)")

            # Backup backend data directory
            backend_data_dir = self.root_dir / "backend" / "data"
            if backend_data_dir.exists():
                shutil.copytree(backend_data_dir, backup_dir / "data")
                print(f"✅ Backed up backend data ({self._get_dir_size(backend_data_dir)})")
            else:
                print("⚠️  No backend/data directory found (skipping)")

            # Export docker-compose configuration
            try:
                result = subprocess.run(
                    self.docker_compose_cmd + ["config"],
                    cwd=self.root_dir,
                    capture_output=True,
                    text=True,
                    check=True
                )
                with open(backup_dir / "docker-compose.yml", 'w') as f:
                    f.write(result.stdout)
                print("✅ Backed up docker-compose configuration")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("⚠️  Could not export docker-compose config (Docker Compose not available)")

            # Create backup manifest
            manifest = {
                "backup_name": backup_name,
                "timestamp": timestamp,
                "created_at": datetime.now().isoformat(),
                "root_dir": str(self.root_dir),
                "files_backed_up": []
            }

            for item in backup_dir.iterdir():
                if item.is_file():
                    manifest["files_backed_up"].append(item.name)
                elif item.is_dir():
                    manifest["files_backed_up"].append(f"{item.name}/ (directory)")

            with open(backup_dir / "MANIFEST.txt", 'w') as f:
                f.write(f"Tsushin Backup Manifest\n")
                f.write(f"=" * 60 + "\n")
                f.write(f"Backup Name: {manifest['backup_name']}\n")
                f.write(f"Created At: {manifest['created_at']}\n")
                f.write(f"Root Directory: {manifest['root_dir']}\n")
                f.write(f"\nBackup Contents:\n")
                for item in manifest["files_backed_up"]:
                    f.write(f"  - {item}\n")

            print(f"\n✅ Backup created successfully!")
            print(f"📁 Location: {backup_dir}")
            print(f"💾 Size: {self._get_dir_size(backup_dir)}")
            print(f"\n💡 To restore: python backup_installer.py restore {backup_dir}")

            return str(backup_dir)

        except Exception as e:
            print(f"\n❌ Backup failed: {e}")
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            raise

    def restore_backup(self, backup_dir: str) -> None:
        """
        Restore from backup

        Args:
            backup_dir: Path to backup directory
        """
        backup_path = Path(backup_dir)

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_dir}")

        print(f"\n♻️  Restoring from backup: {backup_path.name}")
        print("=" * 60)

        # Read manifest
        manifest_file = backup_path / "MANIFEST.txt"
        if manifest_file.exists():
            print("\n📋 Backup Manifest:")
            with open(manifest_file, 'r') as f:
                print(f.read())

        # Confirm restoration
        confirm = input("\n⚠️  This will REPLACE current installation. Continue? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("❌ Restore cancelled")
            return

        try:
            # Stop running containers
            print("\n🛑 Stopping containers...")
            try:
                subprocess.run(
                    self.docker_compose_cmd + ["down"],
                    cwd=self.root_dir,
                    check=True
                )
                print("✅ Containers stopped")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("⚠️  Could not stop containers (Docker Compose not available)")

            # Restore .env file
            backup_env = backup_path / ".env"
            if backup_env.exists():
                shutil.copy(backup_env, self.root_dir / ".env")
                print("✅ Restored .env file")

            # Restore backend data
            backup_data_dir = backup_path / "data"
            backend_data_dir = self.root_dir / "backend" / "data"

            if backup_data_dir.exists():
                if backend_data_dir.exists():
                    print("🗑️  Removing current backend/data...")
                    shutil.rmtree(backend_data_dir)

                print("📦 Restoring backend/data...")
                shutil.copytree(backup_data_dir, backend_data_dir)
                print(f"✅ Restored backend data ({self._get_dir_size(backend_data_dir)})")

            # Restart containers
            print("\n🚀 Restarting containers...")
            try:
                subprocess.run(
                    self.docker_compose_cmd + ["up", "-d"],
                    cwd=self.root_dir,
                    check=True
                )
                print("✅ Containers restarted")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("⚠️  Could not restart containers (please run 'docker compose up -d' manually)")

            print(f"\n✅ Restore completed successfully!")
            print(f"🎉 Your Tsushin instance has been restored from {backup_path.name}")

        except Exception as e:
            print(f"\n❌ Restore failed: {e}")
            print("⚠️  Your installation may be in an inconsistent state")
            print("💡 Try restoring again or contact support")
            raise

    def list_backups(self) -> None:
        """List all available backups"""
        print(f"\n📋 Available Backups")
        print("=" * 60)

        if not self.backup_base_dir.exists() or not any(self.backup_base_dir.iterdir()):
            print("No backups found")
            return

        backups = sorted(self.backup_base_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)

        for idx, backup in enumerate(backups, 1):
            if backup.is_dir():
                manifest_file = backup / "MANIFEST.txt"
                created_at = "Unknown"

                if manifest_file.exists():
                    with open(manifest_file, 'r') as f:
                        for line in f:
                            if line.startswith("Created At:"):
                                created_at = line.split(":", 1)[1].strip()
                                break

                size = self._get_dir_size(backup)
                print(f"{idx}. {backup.name}")
                print(f"   📅 Created: {created_at}")
                print(f"   💾 Size: {size}")
                print(f"   📁 Path: {backup}")
                print()

    def _get_dir_size(self, path: Path) -> str:
        """Get human-readable directory size"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = Path(dirpath) / filename
                if filepath.exists():
                    total_size += filepath.stat().st_size

        # Convert to human-readable format
        for unit in ['B', 'KB', 'MB', 'GB']:
            if total_size < 1024.0:
                return f"{total_size:.1f} {unit}"
            total_size /= 1024.0
        return f"{total_size:.1f} TB"


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python backup_installer.py create [backup_name]")
        print("  python backup_installer.py restore <backup_dir>")
        print("  python backup_installer.py list")
        sys.exit(1)

    backup_tool = TsushinBackup()
    command = sys.argv[1]

    try:
        if command == "create":
            backup_name = sys.argv[2] if len(sys.argv) > 2 else None
            backup_tool.create_backup(backup_name)
        elif command == "restore":
            if len(sys.argv) < 3:
                print("Error: backup directory required")
                print("Usage: python backup_installer.py restore <backup_dir>")
                sys.exit(1)
            backup_dir = sys.argv[2]
            backup_tool.restore_backup(backup_dir)
        elif command == "list":
            backup_tool.list_backups()
        else:
            print(f"Unknown command: {command}")
            print("Available commands: create, restore, list")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
