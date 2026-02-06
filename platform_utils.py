"""
Tsushin Platform Utilities
Cross-platform helpers for installer scripts (Linux, macOS, Windows).

Used by install.py and backup_installer.py to handle OS-specific differences
while keeping the main logic clean.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List


def is_windows() -> bool:
    return sys.platform == "win32"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_root() -> bool:
    """Check if running as root/admin. Safe on all platforms."""
    if is_windows():
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    return os.geteuid() == 0


def set_directory_permissions(path, mode=0o777):
    """Set directory permissions. No-op on Windows (Docker Desktop handles it)."""
    if is_windows():
        return
    os.chmod(path, mode)


def set_directory_ownership(path, uid: int, gid: int):
    """Set directory ownership. No-op on Windows."""
    if is_windows():
        return
    os.chown(path, uid, gid)


def get_real_user_info() -> Optional[Tuple[int, int, str]]:
    """
    Get the non-root user info when running via sudo.
    Returns (uid, gid, username) or None.
    Only relevant on Linux/macOS.
    """
    if is_windows():
        return None
    real_user = os.environ.get("SUDO_USER")
    if not real_user:
        return None
    try:
        import pwd
        user_info = pwd.getpwnam(real_user)
        return (user_info.pw_uid, user_info.pw_gid, real_user)
    except Exception:
        return None


def detect_docker_compose_cmd() -> Optional[List[str]]:
    """
    Detect whether to use 'docker-compose' or 'docker compose'.
    Returns the command as a list, or None if neither is available.
    """
    try:
        subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True, text=True, check=True
        )
        return ["docker-compose"]
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, text=True, check=True
        )
        return ["docker", "compose"]
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    return None


def enable_ansi_colors():
    """Enable ANSI color support on Windows 10+."""
    if is_windows():
        os.system("")  # Triggers VT100 processing on Windows 10+
