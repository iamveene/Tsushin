"""
Base classes for persistence managers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class PersistenceStatus(Enum):
    """Status of the persistence mechanism."""
    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class PersistenceResult:
    """Result of a persistence operation."""
    success: bool
    message: str
    status: Optional[PersistenceStatus] = None
    details: Optional[Dict[str, Any]] = field(default_factory=dict)


class BasePersistenceManager(ABC):
    """
    Abstract base class for platform-specific persistence managers.

    Each platform implementation (Linux, macOS, Windows) should inherit
    from this class and implement the abstract methods.
    """

    def __init__(
        self,
        beacon_path: str,
        config_path: str,
        python_path: str,
        server_url: str,
        api_key: str,
        system_level: bool = False
    ):
        """
        Initialize the persistence manager.

        Args:
            beacon_path: Absolute path to the beacon entry point
            config_path: Path to the beacon configuration file
            python_path: Path to the Python interpreter
            server_url: Tsushin server URL
            api_key: Beacon API key
            system_level: If True, use system-level persistence
        """
        self.beacon_path = beacon_path
        self.config_path = config_path
        self.python_path = python_path
        self.server_url = server_url
        self.api_key = api_key
        self.system_level = system_level

    @abstractmethod
    def install(self) -> PersistenceResult:
        """
        Install the persistence mechanism.

        Creates the necessary service files and enables auto-start.

        Returns:
            PersistenceResult with success status and message
        """
        pass

    @abstractmethod
    def uninstall(self) -> PersistenceResult:
        """
        Remove the persistence mechanism.

        Stops the service and removes service files.

        Returns:
            PersistenceResult with success status and message
        """
        pass

    @abstractmethod
    def status(self) -> PersistenceResult:
        """
        Check the persistence status.

        Returns:
            PersistenceResult with current status information
        """
        pass

    @abstractmethod
    def get_service_file_path(self) -> str:
        """
        Get the path where the service file will be/is created.

        Returns:
            Absolute path to the service file
        """
        pass

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """
        Get a human-readable name for this platform's persistence mechanism.

        Returns:
            Platform name string (e.g., "Linux (systemd)", "macOS (LaunchAgent)")
        """
        pass

    def _redact_api_key(self, api_key: str) -> str:
        """Redact API key for display, showing only first and last 4 chars."""
        if len(api_key) <= 12:
            return "***"
        return f"{api_key[:8]}...{api_key[-4:]}"
