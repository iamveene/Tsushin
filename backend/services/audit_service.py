"""
Audit Service
Phase 7.9: Global Admin Audit Logging + Tenant-Scoped Audit Events (v0.6.0)

Records actions taken by global admins and tenant users for compliance and security.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Generator
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func
import csv
import io
import json
import logging

from models_rbac import GlobalAdminAuditLog, AuditEvent, User

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
            query = query.filter(GlobalAdminAuditLog.action.ilike(f"%{action}%"))
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
            query = query.filter(GlobalAdminAuditLog.action.ilike(f"%{action}%"))
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


# =============================================================================
# Tenant-Scoped Audit Events (v0.6.0)
# =============================================================================

class TenantAuditActions:
    """Standard tenant-scoped audit event action types."""

    # Auth
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_FAILED_LOGIN = "auth.failed_login"
    AUTH_PASSWORD_CHANGE = "auth.password_change"
    AUTH_PASSWORD_RESET = "auth.password_reset"

    # Agents
    AGENT_CREATE = "agent.create"
    AGENT_UPDATE = "agent.update"
    AGENT_DELETE = "agent.delete"
    AGENT_SKILL_CHANGE = "agent.skill_change"

    # Flows
    FLOW_CREATE = "flow.create"
    FLOW_UPDATE = "flow.update"
    FLOW_DELETE = "flow.delete"
    FLOW_EXECUTE = "flow.execute"

    # Contacts
    CONTACT_CREATE = "contact.create"
    CONTACT_UPDATE = "contact.update"
    CONTACT_DELETE = "contact.delete"

    # Settings
    SETTINGS_UPDATE = "settings.update"

    # Security
    SECURITY_SENTINEL_BLOCK = "security.sentinel_block"
    SECURITY_MEMGUARD_BLOCK = "security.memguard_block"
    SECURITY_PERMISSION_DENIED = "security.permission_denied"
    SECURITY_SKILL_SCAN = "security.skill_scan"

    # API Clients
    API_CLIENT_CREATE = "api_client.create"
    API_CLIENT_ROTATE = "api_client.rotate"
    API_CLIENT_REVOKE = "api_client.revoke"

    # Custom Skills
    SKILL_CREATE = "skill.create"
    SKILL_UPDATE = "skill.update"
    SKILL_DELETE = "skill.delete"
    SKILL_DEPLOY = "skill.deploy"

    # MCP Servers
    MCP_CONNECT = "mcp.connect"
    MCP_DISCONNECT = "mcp.disconnect"
    MCP_CREATE = "mcp.create"
    MCP_DELETE = "mcp.delete"

    # Team
    TEAM_INVITE = "team.invite"
    TEAM_REMOVE = "team.remove"
    TEAM_ROLE_CHANGE = "team.role_change"

    # Agent Communication (v0.6.0 Item 15)
    AGENT_COMM_SEND = "agent_comm.send"
    AGENT_COMM_RECEIVE = "agent_comm.receive"
    AGENT_COMM_BLOCKED = "agent_comm.blocked"
    AGENT_COMM_PERMISSION_CREATE = "agent_comm.permission.create"
    AGENT_COMM_PERMISSION_UPDATE = "agent_comm.permission.update"
    AGENT_COMM_PERMISSION_DELETE = "agent_comm.permission.delete"

    # Shell / Beacon
    SHELL_COMMAND_QUEUED = "shell.command_queued"
    SHELL_COMMAND_BLOCKED = "shell.command_blocked"
    SHELL_COMMAND_PENDING_APPROVAL = "shell.command_pending_approval"
    SHELL_APPROVAL_REQUESTED = "shell.approval_requested"
    SHELL_APPROVED = "shell.approved"
    SHELL_REJECTED = "shell.rejected"
    SHELL_EXPIRED = "shell.expired"


class TenantAuditService:
    """Service for tenant-scoped audit event recording and querying."""

    def __init__(self, db: Session):
        self.db = db

    def log_event(
        self,
        tenant_id: str,
        user_id: Optional[int],
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        channel: str = "web",
        severity: str = "info",
    ) -> Optional[AuditEvent]:
        """Create a tenant-scoped audit event."""
        event = AuditEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
            channel=channel,
            severity=severity,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def get_events(
        self,
        tenant_id: str,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        user_id: Optional[int] = None,
        severity: Optional[str] = None,
        channel: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """Query audit events with filters."""
        query = self.db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id)

        if action:
            query = query.filter(AuditEvent.action.ilike(f"%{action}%"))
        if resource_type:
            query = query.filter(AuditEvent.resource_type == resource_type)
        if user_id:
            query = query.filter(AuditEvent.user_id == user_id)
        if severity:
            query = query.filter(AuditEvent.severity == severity)
        if channel:
            query = query.filter(AuditEvent.channel == channel)
        if from_date:
            query = query.filter(AuditEvent.created_at >= from_date)
        if to_date:
            query = query.filter(AuditEvent.created_at <= to_date)

        return query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit).all()

    def get_event_count(
        self,
        tenant_id: str,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        user_id: Optional[int] = None,
        severity: Optional[str] = None,
        channel: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> int:
        """Count audit events matching filters."""
        query = self.db.query(sa_func.count(AuditEvent.id)).filter(AuditEvent.tenant_id == tenant_id)

        if action:
            query = query.filter(AuditEvent.action.ilike(f"%{action}%"))
        if resource_type:
            query = query.filter(AuditEvent.resource_type == resource_type)
        if user_id:
            query = query.filter(AuditEvent.user_id == user_id)
        if severity:
            query = query.filter(AuditEvent.severity == severity)
        if channel:
            query = query.filter(AuditEvent.channel == channel)
        if from_date:
            query = query.filter(AuditEvent.created_at >= from_date)
        if to_date:
            query = query.filter(AuditEvent.created_at <= to_date)

        return query.scalar() or 0

    def get_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get audit event summary statistics."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())

        base = self.db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id)

        events_today = base.filter(AuditEvent.created_at >= today_start).count()
        events_this_week = base.filter(AuditEvent.created_at >= week_start).count()
        critical_count = base.filter(
            AuditEvent.severity == "critical",
            AuditEvent.created_at >= week_start,
        ).count()

        # Top actors (last 7 days)
        top_actors_q = (
            self.db.query(
                AuditEvent.user_id,
                sa_func.count(AuditEvent.id).label("event_count"),
            )
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.created_at >= week_start)
            .group_by(AuditEvent.user_id)
            .order_by(sa_func.count(AuditEvent.id).desc())
            .limit(5)
            .all()
        )

        top_actors = []
        for user_id, count in top_actors_q:
            user = self.db.query(User).filter(User.id == user_id, User.tenant_id == tenant_id).first() if user_id else None
            top_actors.append({
                "user_id": user_id,
                "user_name": user.full_name or user.email if user else "System",
                "event_count": count,
            })

        # Events by category (last 7 days)
        by_category_q = (
            self.db.query(
                sa_func.split_part(AuditEvent.action, '.', 1).label("category"),
                sa_func.count(AuditEvent.id).label("count"),
            )
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.created_at >= week_start)
            .group_by("category")
            .all()
        )
        by_category = {cat: cnt for cat, cnt in by_category_q}

        return {
            "events_today": events_today,
            "events_this_week": events_this_week,
            "critical_count": critical_count,
            "top_actors": top_actors,
            "by_category": by_category,
        }

    def export_events_csv(
        self,
        tenant_id: str,
        **filters,
    ) -> Generator[str, None, None]:
        """Generate CSV rows for audit event export."""
        events = self.get_events(tenant_id, limit=10000, **filters)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Timestamp", "Action", "User ID", "Resource Type", "Resource ID", "Severity", "Channel", "IP Address", "Details"])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for event in events:
            writer.writerow([
                event.id,
                event.created_at.isoformat() if event.created_at else "",
                event.action,
                event.user_id or "",
                event.resource_type or "",
                event.resource_id or "",
                event.severity or "info",
                event.channel or "",
                event.ip_address or "",
                json.dumps(event.details) if event.details else "",
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    def purge_expired(self, tenant_id: str, retention_days: int) -> int:
        """Delete events older than retention period. Returns count deleted.

        audit_event is protected by a BEFORE DELETE trigger (BUG-704). To allow
        legitimate retention purges, we set `app.audit_event_retention_purge`
        on the current transaction. SET LOCAL is automatically reset at COMMIT
        so the bypass cannot leak to subsequent transactions.
        """
        from sqlalchemy import text as sa_text

        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        if self.db.bind.dialect.name == "postgresql":
            self.db.execute(sa_text("SET LOCAL app.audit_event_retention_purge = 'true'"))
        count = (
            self.db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return count


def log_tenant_event(
    db: Session,
    tenant_id: str,
    user_id: Optional[int],
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    request=None,
    channel: str = "web",
    severity: str = "info",
) -> Optional[AuditEvent]:
    """
    Convenience function for logging tenant-scoped audit events.

    Usage in route handlers:
        log_tenant_event(db, ctx.tenant_id, user.id, TenantAuditActions.AGENT_CREATE,
                         "agent", str(agent.id), {"name": agent.name}, request)
    """
    # Global admins have no tenant — skip tenant-scoped audit logging silently.
    if tenant_id is None:
        return None
    try:
        ip_address = None
        user_agent = None
        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent", "")[:500]

        service = TenantAuditService(db)
        event = service.log_event(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
            channel=channel,
            severity=severity,
        )
        db.commit()  # Commit the flushed audit event

        # Syslog forwarding: enqueue event data (non-blocking, fire-and-forget)
        try:
            from services.syslog_forwarder import enqueue_event
            enqueue_event(tenant_id, {
                "id": event.id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "details": details,
                "ip_address": ip_address,
                "channel": channel,
                "severity": severity,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            })
        except Exception:
            pass  # Never let syslog forwarding break audit logging

        return event
    except Exception as e:
        logger.error(f"Failed to log audit event {action}: {e}")
        return None
