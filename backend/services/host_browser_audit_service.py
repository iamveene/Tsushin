"""
Host Browser Audit Service
Phase 8: Browser Automation - Security audit logging for host mode operations.

All host mode browser actions MUST be logged for:
- Security compliance and incident investigation
- Tracking actions on authenticated user sessions
- Audit trail for data protection policies

Note: Container mode actions are NOT logged (isolated environment).
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models import HostBrowserAuditLog

logger = logging.getLogger(__name__)


# Sensitive query parameters to redact from URLs
SENSITIVE_URL_PARAMS = {
    'token', 'key', 'password', 'auth', 'session', 'secret', 'api_key',
    'apikey', 'access_token', 'refresh_token', 'bearer', 'credential',
    'pwd', 'pass', 'passwd', 'private', 'signature', 'sig', 'hash',
}


class HostBrowserAuditService:
    """
    Audit logging service for host browser automation operations.

    All host mode browser actions MUST be logged before execution.
    This service handles:
    - Creating audit log entries
    - Sanitizing URLs (removing sensitive query params)
    - Hashing parameters for privacy
    - Querying audit logs for compliance reporting
    """

    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        tenant_id: str,
        user_key: str,
        action: str,
        mcp_tool: str,
        url: Optional[str] = None,
        target_element: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        agent_id: Optional[int] = None,
    ) -> HostBrowserAuditLog:
        """
        Log a host browser action BEFORE execution.

        Creates an audit log entry with success=False initially.
        The caller should update the entry after execution with update_result().

        Args:
            tenant_id: Tenant ID for multi-tenancy
            user_key: User identifier (WhatsApp number, email, etc.)
            action: Browser action type (navigate, click, fill, etc.)
            mcp_tool: Full MCP tool name used
            url: URL being accessed (will be sanitized)
            target_element: CSS selector or element reference
            params: MCP call parameters (will be hashed for privacy)
            session_id: Browser session identifier
            ip_address: Client IP address
            agent_id: ID of the agent performing the action

        Returns:
            The created HostBrowserAuditLog entry
        """
        # Hash params to avoid storing sensitive data
        params_hash = None
        if params:
            try:
                params_hash = hashlib.sha256(
                    json.dumps(params, sort_keys=True, default=str).encode()
                ).hexdigest()
            except Exception as e:
                logger.warning(f"Failed to hash params: {e}")

        # Sanitize URL
        sanitized_url = self._sanitize_url(url)

        entry = HostBrowserAuditLog(
            tenant_id=tenant_id,
            user_key=user_key,
            agent_id=agent_id,
            action=action,
            url=sanitized_url,
            target_element=target_element,
            mcp_tool=mcp_tool,
            mcp_params_hash=params_hash,
            success=False,  # Updated after execution
            session_id=session_id,
            ip_address=ip_address,
        )

        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)

        logger.info(
            f"Host browser audit: {action} by {user_key} on {sanitized_url or 'N/A'} "
            f"(tenant={tenant_id}, agent={agent_id})"
        )

        return entry

    def update_result(
        self,
        log_entry: HostBrowserAuditLog,
        success: bool,
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> HostBrowserAuditLog:
        """
        Update audit log entry with execution result.

        Call this after the browser action completes.

        Args:
            log_entry: The audit log entry to update
            success: Whether the action succeeded
            duration_ms: Execution duration in milliseconds
            error_message: Error message if action failed

        Returns:
            The updated log entry
        """
        log_entry.success = success
        log_entry.duration_ms = duration_ms
        log_entry.error_message = error_message

        self.db.commit()
        self.db.refresh(log_entry)

        if not success:
            logger.warning(
                f"Host browser action failed: {log_entry.action} - {error_message}"
            )

        return log_entry

    def _sanitize_url(self, url: Optional[str]) -> Optional[str]:
        """
        Sanitize URL for logging - remove sensitive query parameters.

        Removes parameters like: token, key, password, auth, session, secret, etc.

        Args:
            url: The URL to sanitize

        Returns:
            Sanitized URL with sensitive params redacted
        """
        if not url:
            return None

        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query, keep_blank_values=True)

            # Redact sensitive parameters
            for param in list(params.keys()):
                param_lower = param.lower()
                if any(s in param_lower for s in SENSITIVE_URL_PARAMS):
                    params[param] = ['[REDACTED]']

            # Rebuild URL (use quote_via to prevent encoding of brackets)
            from urllib.parse import quote
            sanitized_query = urlencode(params, doseq=True, quote_via=lambda s, *_: s)
            sanitized = parsed._replace(query=sanitized_query)
            return urlunparse(sanitized)
        except Exception as e:
            logger.warning(f"Failed to sanitize URL: {e}")
            # Return URL without query string as fallback
            try:
                parsed = urlparse(url)
                return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            except Exception:
                return "[INVALID_URL]"

    def get_logs(
        self,
        tenant_id: Optional[str] = None,
        user_key: Optional[str] = None,
        action: Optional[str] = None,
        agent_id: Optional[int] = None,
        success: Optional[bool] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[HostBrowserAuditLog]:
        """
        Query audit logs with filters.

        Args:
            tenant_id: Filter by tenant ID
            user_key: Filter by user identifier
            action: Filter by action type
            agent_id: Filter by agent ID
            success: Filter by success status
            from_date: Filter logs from this date
            to_date: Filter logs until this date
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of audit log entries
        """
        query = self.db.query(HostBrowserAuditLog)

        if tenant_id:
            query = query.filter(HostBrowserAuditLog.tenant_id == tenant_id)
        if user_key:
            query = query.filter(HostBrowserAuditLog.user_key == user_key)
        if action:
            query = query.filter(HostBrowserAuditLog.action == action)
        if agent_id:
            query = query.filter(HostBrowserAuditLog.agent_id == agent_id)
        if success is not None:
            query = query.filter(HostBrowserAuditLog.success == success)
        if from_date:
            query = query.filter(HostBrowserAuditLog.timestamp >= from_date)
        if to_date:
            query = query.filter(HostBrowserAuditLog.timestamp <= to_date)

        return (
            query.order_by(desc(HostBrowserAuditLog.timestamp))
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_log_count(
        self,
        tenant_id: Optional[str] = None,
        user_key: Optional[str] = None,
        action: Optional[str] = None,
        success: Optional[bool] = None,
    ) -> int:
        """Get total count of audit logs matching filters."""
        query = self.db.query(HostBrowserAuditLog)

        if tenant_id:
            query = query.filter(HostBrowserAuditLog.tenant_id == tenant_id)
        if user_key:
            query = query.filter(HostBrowserAuditLog.user_key == user_key)
        if action:
            query = query.filter(HostBrowserAuditLog.action == action)
        if success is not None:
            query = query.filter(HostBrowserAuditLog.success == success)

        return query.count()

    def get_recent_logs_for_user(
        self,
        tenant_id: str,
        user_key: str,
        limit: int = 10,
    ) -> List[HostBrowserAuditLog]:
        """
        Get recent audit logs for a specific user.

        Useful for showing user their recent browser automation activity.
        """
        return self.get_logs(
            tenant_id=tenant_id,
            user_key=user_key,
            limit=limit,
        )

    def get_failed_actions(
        self,
        tenant_id: Optional[str] = None,
        from_date: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[HostBrowserAuditLog]:
        """
        Get failed browser actions for investigation.

        Useful for monitoring and debugging.
        """
        return self.get_logs(
            tenant_id=tenant_id,
            success=False,
            from_date=from_date,
            limit=limit,
        )


# Predefined action types for consistency
class HostBrowserAuditActions:
    """Standard host browser audit action types."""

    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    EXTRACT = "extract"
    SCREENSHOT = "screenshot"
    EXECUTE_SCRIPT = "execute_script"

    # Security events
    SENSITIVE_DOMAIN_BLOCKED = "sensitive_domain_blocked"
    UNAUTHORIZED_ACCESS_ATTEMPT = "unauthorized_access_attempt"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"


def log_host_browser_action(
    db: Session,
    tenant_id: str,
    user_key: str,
    action: str,
    mcp_tool: str,
    url: Optional[str] = None,
    target_element: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    agent_id: Optional[int] = None,
) -> HostBrowserAuditLog:
    """
    Convenience function for logging host browser actions.

    Can be used as a quick one-liner:
        entry = log_host_browser_action(
            db, tenant_id, user_key, "navigate", "browser_navigate",
            url="https://example.com"
        )
    """
    service = HostBrowserAuditService(db)
    return service.log_action(
        tenant_id=tenant_id,
        user_key=user_key,
        action=action,
        mcp_tool=mcp_tool,
        url=url,
        target_element=target_element,
        params=params,
        session_id=session_id,
        ip_address=ip_address,
        agent_id=agent_id,
    )
