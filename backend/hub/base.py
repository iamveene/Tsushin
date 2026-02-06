"""
Hub Integration Base Class

Abstract base class for all Hub integrations (Asana, Slack, Linear, etc.).
Provides common interface for token management, health checks, and metrics.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


class HubIntegrationBase(ABC):
    """
    Abstract base class for all Hub integrations.

    Provides common interface for:
    - Token management (refresh, validation)
    - Health monitoring
    - Metrics collection
    - Error handling

    Subclasses must implement:
    - check_health()
    - refresh_tokens()
    - revoke_access()
    - get_metrics()
    """

    def __init__(self, db: Session, integration_id: int):
        """
        Initialize Hub integration.

        Args:
            db: Database session
            integration_id: HubIntegration table primary key
        """
        self.db = db
        self.integration_id = integration_id
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    async def check_health(self) -> Dict[str, Any]:
        """
        Check health of integration.

        This should verify:
        - Token validity
        - API connectivity
        - Workspace accessibility
        - Rate limit status

        Returns:
            {
                "status": "healthy" | "degraded" | "unavailable",
                "last_check": datetime (ISO format),
                "details": {
                    "token_expires_at": datetime (ISO format),
                    "api_reachable": bool,
                    "workspace_accessible": bool,
                    "rate_limit_remaining": int,
                    ...
                },
                "errors": [str] (if any)
            }

        Example:
            {
                "status": "healthy",
                "last_check": "2025-10-21T15:30:00Z",
                "details": {
                    "token_expires_at": "2025-10-21T16:30:00Z",
                    "api_reachable": True,
                    "workspace_accessible": True,
                    "rate_limit_remaining": 140
                },
                "errors": []
            }
        """
        pass

    @abstractmethod
    async def refresh_tokens(self) -> bool:
        """
        Refresh OAuth tokens if needed.

        Should check token expiration and refresh if necessary.
        Implements automatic retry logic for transient failures.

        Returns:
            True if tokens refreshed successfully or still valid
            False if refresh failed (requires re-authentication)

        Raises:
            Exception: If refresh fails with permanent error
        """
        pass

    @abstractmethod
    async def revoke_access(self) -> None:
        """
        Revoke OAuth access and delete tokens.

        Should:
        1. Call provider's token revocation endpoint (if available)
        2. Delete tokens from database
        3. Mark integration as inactive
        4. Log revocation event

        Raises:
            Exception: If revocation fails
        """
        pass

    @abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get integration metrics for monitoring.

        Metrics should be compatible with Prometheus format.

        Returns:
            {
                "requests_total": int,
                "requests_failed": int,
                "requests_duration_seconds": float,
                "cache_hits": int,
                "cache_misses": int,
                "active_connections": int,
                "token_expires_in_seconds": int,
                ...
            }

        Example:
            {
                "requests_total": 1523,
                "requests_failed": 12,
                "requests_duration_seconds": 1.24,
                "cache_hits": 892,
                "cache_misses": 631,
                "active_connections": 3,
                "token_expires_in_seconds": 3540
            }
        """
        pass

    def _log_error(self, message: str, exc_info: bool = False) -> None:
        """
        Log error with integration context.

        Args:
            message: Error message
            exc_info: Include exception traceback
        """
        self._logger.error(
            f"[Integration {self.integration_id}] {message}",
            exc_info=exc_info
        )

    def _log_info(self, message: str) -> None:
        """
        Log informational message with integration context.

        Args:
            message: Info message
        """
        self._logger.info(f"[Integration {self.integration_id}] {message}")

    def _log_warning(self, message: str) -> None:
        """
        Log warning message with integration context.

        Args:
            message: Warning message
        """
        self._logger.warning(f"[Integration {self.integration_id}] {message}")

    def _log_debug(self, message: str) -> None:
        """
        Log debug message with integration context.

        Args:
            message: Debug message
        """
        self._logger.debug(f"[Integration {self.integration_id}] {message}")


class IntegrationHealthStatus:
    """Health status constants."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class IntegrationError(Exception):
    """Base exception for integration errors."""
    pass


class TokenExpiredError(IntegrationError):
    """Raised when OAuth token is expired and refresh fails."""
    pass


class WorkspaceAccessError(IntegrationError):
    """Raised when workspace is not accessible (permissions revoked)."""
    pass


class RateLimitError(IntegrationError):
    """Raised when API rate limit is exceeded."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after  # Seconds until rate limit resets


class ConnectionError(IntegrationError):
    """Raised when unable to connect to external service."""
    pass
