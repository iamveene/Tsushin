"""
Audit Service
Phase 7.9: Global Admin Audit Logging

Records actions taken by global admins for compliance and security.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
import json
import logging

from models_rbac import GlobalAdminAuditLog, User

logger = logging.getLogger(__name__)


class AuditService:
    """Service for recording audit logs."""

    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        admin: User,
        action: str,
        target_tenant_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> GlobalAdminAuditLog:
        """
        Log a global admin action.

        Args:
            admin: The global admin performing the action
            action: Action being performed (e.g., "tenant.create", "user.suspend")
            target_tenant_id: ID of the tenant being affected (if any)
            resource_type: Type of resource (e.g., "tenant", "user", "integration")
            resource_id: ID of the specific resource
            details: Additional details about the action
            ip_address: IP address of the request
            user_agent: User agent of the request

        Returns:
            The created audit log entry
        """
        if not admin.is_global_admin:
            logger.warning(f"Attempted to log action for non-admin user {admin.id}")
            return None

        log_entry = GlobalAdminAuditLog(
            global_admin_id=admin.id,
            action=action,
            target_tenant_id=target_tenant_id,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details_json=json.dumps(details) if details else None,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.add(log_entry)
        self.db.commit()
        self.db.refresh(log_entry)

        logger.info(
            f"Audit log: Admin {admin.email} performed {action} "
            f"on {resource_type}/{resource_id}"
        )

        return log_entry

    def get_logs(
        self,
        admin_id: Optional[int] = None,
        action: Optional[str] = None,
        target_tenant_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        """
        Query audit logs with filters.

        Args:
            admin_id: Filter by admin user ID
            action: Filter by action type
            target_tenant_id: Filter by target tenant
            resource_type: Filter by resource type
            from_date: Filter logs from this date
            to_date: Filter logs until this date
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of audit log entries
        """
        query = self.db.query(GlobalAdminAuditLog)

        if admin_id:
            query = query.filter(GlobalAdminAuditLog.global_admin_id == admin_id)
        if action:
            query = query.filter(GlobalAdminAuditLog.action == action)
        if target_tenant_id:
            query = query.filter(GlobalAdminAuditLog.target_tenant_id == target_tenant_id)
        if resource_type:
            query = query.filter(GlobalAdminAuditLog.resource_type == resource_type)
        if from_date:
            query = query.filter(GlobalAdminAuditLog.created_at >= from_date)
        if to_date:
            query = query.filter(GlobalAdminAuditLog.created_at <= to_date)

        return (
            query.order_by(GlobalAdminAuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_log_count(
        self,
        admin_id: Optional[int] = None,
        action: Optional[str] = None,
        target_tenant_id: Optional[str] = None,
    ) -> int:
        """Get total count of audit logs matching filters."""
        query = self.db.query(GlobalAdminAuditLog)

        if admin_id:
            query = query.filter(GlobalAdminAuditLog.global_admin_id == admin_id)
        if action:
            query = query.filter(GlobalAdminAuditLog.action == action)
        if target_tenant_id:
            query = query.filter(GlobalAdminAuditLog.target_tenant_id == target_tenant_id)

        return query.count()


# Predefined action types for consistency
class AuditActions:
    """Standard audit action types."""

    # Tenant actions
    TENANT_CREATE = "tenant.create"
    TENANT_UPDATE = "tenant.update"
    TENANT_DELETE = "tenant.delete"
    TENANT_SUSPEND = "tenant.suspend"
    TENANT_REACTIVATE = "tenant.reactivate"

    # User actions
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_SUSPEND = "user.suspend"
    USER_ROLE_CHANGE = "user.role_change"

    # Integration actions
    INTEGRATION_CREATE = "integration.create"
    INTEGRATION_UPDATE = "integration.update"
    INTEGRATION_DELETE = "integration.delete"
    INTEGRATION_ACTIVATE = "integration.activate"
    INTEGRATION_DEACTIVATE = "integration.deactivate"

    # Plan actions
    PLAN_CREATE = "plan.create"
    PLAN_UPDATE = "plan.update"
    PLAN_DELETE = "plan.delete"
    PLAN_DUPLICATE = "plan.duplicate"

    # SSO actions
    SSO_CONFIG_UPDATE = "sso.config_update"
    SSO_CONFIG_DELETE = "sso.config_delete"

    # System actions
    SYSTEM_CONFIG_UPDATE = "system.config_update"
    SYSTEM_MAINTENANCE = "system.maintenance"


def log_admin_action(
    db: Session,
    admin: User,
    action: str,
    target_tenant_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request=None,
) -> Optional[GlobalAdminAuditLog]:
    """
    Convenience function for logging admin actions.

    Can be used as a quick one-liner in route handlers:
        log_admin_action(db, current_user, AuditActions.TENANT_CREATE, tenant.id)
    """
    ip_address = None
    user_agent = None

    if request:
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

    service = AuditService(db)
    return service.log_action(
        admin=admin,
        action=action,
        target_tenant_id=target_tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )
