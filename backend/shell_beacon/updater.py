"""
Beacon Self-Update Mechanism

Handles:
- Version checking against server
- Downloading new beacon versions
- Verifying checksums
- Applying updates (replacing executable)
"""

import os
import sys
import hashlib
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from datetime import datetime

import requests

from . import __version__

logger = logging.getLogger("tsushin.beacon.updater")


class UpdateError(Exception):
    """Update-related errors."""
    pass


class BeaconUpdater:
    """
    Handles self-update functionality for the beacon.

    Update flow:
    1. Check /beacon/version endpoint for latest version
    2. Compare with current version
    3. If newer version available, download it
    4. Verify checksum
    5. Replace current executable
    6. Signal for restart
    """

    def __init__(
        self,
        server_url: str,
        api_key: str,
        timeout: int = 60
    ):
        """
        Initialize the updater.

        Args:
            server_url: Tsushin server URL
            api_key: Beacon API key
            timeout: HTTP timeout for downloads
        """
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

        # Session for API requests
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"TsushinBeacon/{__version__}",
            "X-API-Key": api_key
        })

    def _parse_version(self, version: str) -> Tuple[int, int, int]:
        """
        Parse version string into tuple for comparison.

        Args:
            version: Version string (e.g., "1.2.3")

        Returns:
            Tuple of (major, minor, patch)
        """
        parts = version.lstrip('v').split('.')
        return tuple(int(p) for p in parts[:3])

    def _is_newer_version(self, remote_version: str) -> bool:
        """
        Check if remote version is newer than current.

        Args:
            remote_version: Version string from server

        Returns:
            True if remote version is newer
        """
        try:
            current = self._parse_version(__version__)
            remote = self._parse_version(remote_version)
            return remote > current
        except (ValueError, TypeError):
            logger.warning(f"Could not parse version: {remote_version}")
            return False

    def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """
        Check server for available updates.

        Returns:
            Update info dict if update available, None otherwise
            Dict contains: version, download_url, checksum, release_notes
        """
        try:
            url = f"{self.server_url}/beacon/version"
            response = self.session.get(url, timeout=30)

            if response.status_code != 200:
                logger.debug(f"Version check returned {response.status_code}")
                return None

            data = response.json()
            remote_version = data.get("version")

            if not remote_version:
                logger.debug("No version in response")
                return None

            if self._is_newer_version(remote_version):
                logger.info(f"Update available: {__version__} -> {remote_version}")
                return {
                    "version": remote_version,
                    "download_url": data.get("download_url"),
                    "checksum": data.get("checksum"),
                    "checksum_algorithm": data.get("checksum_algorithm", "sha256"),
                    "release_notes": data.get("release_notes", ""),
                    "size_bytes": data.get("size_bytes", 0)
                }
            else:
                logger.debug(f"Current version {__version__} is up to date")
                return None

        except requests.exceptions.RequestException as e:
            logger.debug(f"Update check failed: {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error during update check: {e}")
            return None

    def download_update(self, update_info: Dict[str, Any]) -> Optional[Path]:
        """
        Download update to temporary file.

        Args:
            update_info: Update info from check_for_updates()

        Returns:
            Path to downloaded file, or None on error
        """
        download_url = update_info.get("download_url")
        if not download_url:
            logger.error("No download URL in update info")
            return None

        # Resolve relative URLs
        if not download_url.startswith(("http://", "https://")):
            download_url = f"{self.server_url}/{download_url.lstrip('/')}"

        try:
            logger.info(f"Downloading update from {download_url}")

            response = self.session.get(
                download_url,
                timeout=self.timeout,
                stream=True
            )
            response.raise_for_status()

            # Create temp file
            fd, temp_path = tempfile.mkstemp(suffix=".py", prefix="beacon_update_")
            temp_file = Path(temp_path)

            # Download to temp file
            with os.fdopen(fd, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Downloaded to {temp_file}")
            return temp_file

        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            return None

    def verify_checksum(
        self,
        file_path: Path,
        expected_checksum: str,
        algorithm: str = "sha256"
    ) -> bool:
        """
        Verify file checksum.

        Args:
            file_path: Path to file to verify
            expected_checksum: Expected checksum value
            algorithm: Hash algorithm (sha256, sha512, md5)

        Returns:
            True if checksum matches
        """
        if not expected_checksum:
            logger.warning("No checksum provided, skipping verification")
            return True

        try:
            hash_func = getattr(hashlib, algorithm)()

            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_func.update(chunk)

            actual = hash_func.hexdigest()

            # Handle "algorithm:hash" format
            if ':' in expected_checksum:
                expected = expected_checksum.split(':')[1]
            else:
                expected = expected_checksum

            if actual.lower() == expected.lower():
                logger.info("Checksum verified")
                return True
            else:
                logger.error(f"Checksum mismatch: expected {expected}, got {actual}")
                return False

        except Exception as e:
            logger.error(f"Checksum verification error: {e}")
            return False

    def apply_update(self, new_file: Path) -> bool:
        """
        Replace current beacon with new version.

        Args:
            new_file: Path to downloaded update file

        Returns:
            True if update applied successfully
        """
        try:
            # Get path to current script
            current_script = Path(sys.argv[0]).resolve()

            # If we're running from a package, find the beacon.py file
            if current_script.name != 'beacon.py':
                current_script = Path(__file__).resolve()

            logger.info(f"Updating {current_script}")

            # Backup current version
            backup_path = current_script.with_suffix('.py.backup')
            shutil.copy2(current_script, backup_path)
            logger.debug(f"Backup created at {backup_path}")

            # Replace with new version
            shutil.move(str(new_file), str(current_script))

            # Ensure executable
            os.chmod(current_script, 0o755)

            logger.info(f"Update applied successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to apply update: {e}")

            # Try to restore backup
            if backup_path.exists():
                try:
                    shutil.move(str(backup_path), str(current_script))
                    logger.info("Restored from backup")
                except Exception as restore_error:
                    logger.error(f"Failed to restore backup: {restore_error}")

            return False

    def cleanup(self, file_path: Optional[Path]) -> None:
        """
        Clean up temporary files.

        Args:
            file_path: Temp file to remove
        """
        if file_path and file_path.exists():
            try:
                file_path.unlink()
            except Exception as e:
                logger.debug(f"Cleanup failed: {e}")

    def check_and_apply(self) -> bool:
        """
        Full update flow: check, download, verify, apply.

        Returns:
            True if update was applied (beacon should restart)
        """
        # Check for updates
        update_info = self.check_for_updates()
        if not update_info:
            return False

        temp_file = None
        try:
            # Download
            temp_file = self.download_update(update_info)
            if not temp_file:
                return False

            # Verify checksum
            checksum = update_info.get("checksum", "")
            algorithm = update_info.get("checksum_algorithm", "sha256")

            if not self.verify_checksum(temp_file, checksum, algorithm):
                self.cleanup(temp_file)
                return False

            # Apply update
            if self.apply_update(temp_file):
                logger.info(f"Successfully updated to version {update_info['version']}")
                return True

            return False

        except Exception as e:
            logger.error(f"Update failed: {e}")
            self.cleanup(temp_file)
            return False

    def rollback(self) -> bool:
        """
        Rollback to backup version if available.

        Returns:
            True if rollback successful
        """
        try:
            current_script = Path(__file__).resolve()
            backup_path = current_script.with_suffix('.py.backup')

            if not backup_path.exists():
                logger.warning("No backup available for rollback")
                return False

            shutil.copy2(backup_path, current_script)
            logger.info("Rolled back to previous version")
            return True

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False


def get_current_version() -> str:
    """Get the current beacon version."""
    return __version__


def should_check_for_updates(
    last_check: Optional[datetime],
    check_interval_hours: int = 24
) -> bool:
    """
    Determine if we should check for updates.

    Args:
        last_check: Timestamp of last update check
        check_interval_hours: Hours between checks

    Returns:
        True if we should check for updates
    """
    if last_check is None:
        return True

    from datetime import timedelta
    elapsed = datetime.utcnow() - last_check
    return elapsed > timedelta(hours=check_interval_hours)
