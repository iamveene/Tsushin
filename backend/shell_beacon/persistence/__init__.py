"""
Persistence module for Tsushin Shell Beacon.

Provides cross-platform auto-start persistence (systemd, LaunchAgent, Task Scheduler).
"""

import platform
import sys
import os
from pathlib import Path
from typing import Optional

from .base import BasePersistenceManager, PersistenceResult, PersistenceStatus


def get_persistence_manager(
    beacon_path: str,
    config_path: str,
    python_path: str,
    server_url: str,
    api_key: str,
    system_level: bool = False
) -> BasePersistenceManager:
    """
    Factory function to get the appropriate persistence manager for the current OS.

    Args:
        beacon_path: Absolute path to the beacon entry point
        config_path: Path to the beacon configuration file
        python_path: Path to the Python interpreter
        server_url: Tsushin server URL
        api_key: Beacon API key
        system_level: If True, use system-level persistence (requires admin/root)

    Returns:
        Platform-specific persistence manager instance

    Raises:
        RuntimeError: If the current platform is not supported
    """
    system = platform.system()

    if system == "Linux":
        from .linux import LinuxPersistenceManager
        return LinuxPersistenceManager(
            beacon_path=beacon_path,
            config_path=config_path,
            python_path=python_path,
            server_url=server_url,
            api_key=api_key,
            system_level=system_level
        )
    elif system == "Darwin":
        from .macos import MacOSPersistenceManager
        return MacOSPersistenceManager(
            beacon_path=beacon_path,
            config_path=config_path,
            python_path=python_path,
            server_url=server_url,
            api_key=api_key,
            system_level=system_level
        )
    elif system == "Windows":
        from .windows import WindowsPersistenceManager
        return WindowsPersistenceManager(
            beacon_path=beacon_path,
            config_path=config_path,
            python_path=python_path,
            server_url=server_url,
            api_key=api_key,
            system_level=system_level
        )
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


def _detect_beacon_path() -> str:
    """
    Detect the absolute path to the beacon entry point.

    Handles different execution contexts:
    - Running as module: python -m shell_beacon
    - Running run.py directly
    - Running beacon.py directly
    """
    # Get the shell_beacon package directory
    package_dir = Path(__file__).parent.parent

    # Prefer run.py as the entry point (most portable)
    run_py = package_dir / "run.py"
    if run_py.exists():
        return str(run_py.resolve())

    # Fallback to beacon.py
    beacon_py = package_dir / "beacon.py"
    if beacon_py.exists():
        return str(beacon_py.resolve())

    # Last resort: use the package as module
    return str(package_dir.resolve())


def _get_default_config_path() -> str:
    """Get the default configuration file path."""
    return str(Path.home() / ".tsushin" / "beacon.yaml")


def handle_persistence_command(
    action: str,
    config,  # BeaconConfig
    system_level: bool = False
) -> int:
    """
    Handle persistence subcommand and return exit code.

    Args:
        action: One of 'install', 'uninstall', 'status'
        config: BeaconConfig instance
        system_level: If True, use system-level persistence

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Detect paths
        beacon_path = _detect_beacon_path()
        python_path = sys.executable

        # Get config path
        config_path = getattr(config, 'config_file_path', None)
        if not config_path:
            config_path = _get_default_config_path()

        # Get server config
        server_url = config.server.url if hasattr(config, 'server') and config.server.url else ""
        api_key = config.server.api_key if hasattr(config, 'server') and config.server.api_key else ""

        # For install, we need valid config
        if action == "install":
            if not server_url:
                print("Error: Server URL is required for persistence install.", file=sys.stderr)
                print("Provide --server URL or set TSUSHIN_SERVER_URL environment variable.", file=sys.stderr)
                return 1
            if not api_key:
                print("Error: API key is required for persistence install.", file=sys.stderr)
                print("Provide --api-key KEY or set TSUSHIN_API_KEY environment variable.", file=sys.stderr)
                return 1

        # Get the persistence manager for this platform
        manager = get_persistence_manager(
            beacon_path=beacon_path,
            config_path=config_path,
            python_path=python_path,
            server_url=server_url,
            api_key=api_key,
            system_level=system_level
        )

        # Execute the requested action
        if action == "install":
            result = manager.install()
        elif action == "uninstall":
            result = manager.uninstall()
        elif action == "status":
            result = manager.status()
        else:
            print(f"Unknown persistence action: {action}", file=sys.stderr)
            return 1

        # Print result message
        print(result.message)

        # Print additional details if present
        if result.details:
            for key, value in result.details.items():
                print(f"  {key}: {value}")

        return 0 if result.success else 1

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1


__all__ = [
    "BasePersistenceManager",
    "PersistenceResult",
    "PersistenceStatus",
    "get_persistence_manager",
    "handle_persistence_command",
]
