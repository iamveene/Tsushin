"""Remote Access (Cloudflare Tunnel) config service — v0.6.0.

Thin service layer around the RemoteAccessConfig single-row table. Handles:
- Read/write with optimistic concurrency (expected_updated_at check).
- Token encryption on write via TokenEncryption + remote_access key.
- Audit emission for every config change.
- Per-tenant entitlement toggling with dual-stream audit
  (GlobalAdminAuditLog + tenant AuditEvent).
- Computing the Google OAuth callback URIs the admin must whitelist for a
  given hostname.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import Config, RemoteAccessConfig
from models_rbac import Tenant, User, AuditEvent
from services.audit_service import (
    log_admin_action,
    log_tenant_event,
    AuditActions,
)
from services.encryption_key_service import get_remote_access_encryption_key

logger = logging.getLogger(__name__)

WORKSPACE_ID = "remote_access_system"


class ConfigConflictError(Exception):
    """Raised when the expected_updated_at in a PUT does not match the DB row."""


def get_or_create_config(db: Session) -> RemoteAccessConfig:
    row = db.query(RemoteAccessConfig).filter(RemoteAccessConfig.id == 1).first()
    if row is None:
        row = RemoteAccessConfig(id=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def serialize_config(db: Session, row: RemoteAccessConfig) -> Dict[str, Any]:
    """Return the PUBLIC shape of the config row (token NEVER included)."""
    updated_by_email: Optional[str] = None
    if row.updated_by:
        user = db.query(User).filter(User.id == row.updated_by).first()
        if user:
            updated_by_email = user.email

    return {
        "enabled": bool(row.enabled),
        "mode": row.mode or "quick",
        "autostart": bool(row.autostart),
        "protocol": row.protocol or "auto",
        "tunnel_hostname": row.tunnel_hostname,
        "tunnel_dns_target": row.tunnel_dns_target,
        "target_url": row.target_url or "http://frontend:3030",
        "tunnel_token_configured": bool(row.tunnel_token_encrypted),
        "last_started_at": row.last_started_at.isoformat() if row.last_started_at else None,
        "last_stopped_at": row.last_stopped_at.isoformat() if row.last_stopped_at else None,
        "last_error": row.last_error,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by_email": updated_by_email,
    }


def update_config(
    db: Session,
    admin: User,
    payload: Dict[str, Any],
    expected_updated_at: Optional[datetime],
    request=None,
) -> RemoteAccessConfig:
    """Apply a partial update to the remote_access_config row.

    Raises ConfigConflictError if `expected_updated_at` is provided and does
    not match the row's current `updated_at`.
    """
    row = get_or_create_config(db)

    if expected_updated_at is not None and row.updated_at is not None:
        # Compare at second precision + strip timezone to dodge microsecond and
        # tz-aware/naive serialization drift. The frontend sends the string it
        # received in a previous GET, which may have microseconds; our SQLAlchemy
        # DateTime column stores naive UTC. Normalize both sides before comparing.
        def _normalize(dt):
            if dt is None:
                return None
            if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt.replace(microsecond=0)

        if _normalize(row.updated_at) != _normalize(expected_updated_at):
            raise ConfigConflictError(
                "Config was modified by another administrator. Reload and try again."
            )

    # Track which fields changed (for the audit event; token redacted)
    diff: Dict[str, Any] = {}

    # Nullable fields may be explicitly cleared (frontend sends null),
    # non-nullable fields cannot. The route layer already passes
    # model_dump(exclude_unset=True), so anything in the payload dict was
    # intentionally sent by the caller — we must not silently drop null values.
    nullable_fields = ("tunnel_hostname", "tunnel_dns_target")
    non_nullable_fields = ("enabled", "mode", "autostart", "protocol", "target_url")

    for field_name in non_nullable_fields:
        if field_name in payload and payload[field_name] is not None:
            new_value = payload[field_name]
            current = getattr(row, field_name)
            if new_value != current:
                diff[field_name] = new_value
                setattr(row, field_name, new_value)

    for field_name in nullable_fields:
        if field_name in payload:  # explicit set, including None
            new_value = payload[field_name]
            current = getattr(row, field_name)
            if new_value != current:
                diff[field_name] = new_value
                setattr(row, field_name, new_value)

    # Token handling — write-only, never read back, never audited plaintext
    if payload.get("clear_tunnel_token"):
        if row.tunnel_token_encrypted is not None:
            row.tunnel_token_encrypted = None
            diff["tunnel_token"] = "cleared"
    elif payload.get("tunnel_token"):
        plaintext = payload["tunnel_token"]
        key = get_remote_access_encryption_key(db)
        if not key:
            raise RuntimeError("Remote access encryption key unavailable")
        encryption = TokenEncryption(key.encode())
        row.tunnel_token_encrypted = encryption.encrypt(plaintext, WORKSPACE_ID)
        diff["tunnel_token"] = "updated"

    row.updated_by = admin.id if admin else None
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    if diff:
        log_admin_action(
            db=db,
            admin=admin,
            action="remote_access.config.updated",
            resource_type="remote_access_config",
            resource_id="1",
            details={"changed_fields": sorted(diff.keys()), "changes": diff},
            request=request,
        )

    return row


def compute_callbacks(hostname: Optional[str]) -> Dict[str, Any]:
    """Return the Google OAuth callback URIs that must be whitelisted in GCP
    when the tunnel is exposed on the given hostname."""
    if not hostname:
        return {"hostname": None, "callbacks": []}
    base = f"https://{hostname.strip().rstrip('/').lower()}"
    return {
        "hostname": hostname,
        "callbacks": [
            {
                "label": "Google SSO callback",
                "uri": f"{base}/api/auth/google/callback",
                "purpose": "google_sso",
            },
            {
                "label": "Google Hub OAuth callback (Gmail/Calendar)",
                "uri": f"{base}/api/hub/google/oauth/callback",
                "purpose": "hub_oauth",
            },
        ],
    }


def list_tenants_with_entitlement(db: Session) -> List[Dict[str, Any]]:
    """Return every tenant with its remote_access_enabled flag + user count
    + who last toggled it (best-effort via GlobalAdminAuditLog)."""
    from models_rbac import GlobalAdminAuditLog
    import json

    tenants = db.query(Tenant).order_by(Tenant.name).all()
    rows: List[Dict[str, Any]] = []
    for t in tenants:
        user_count = db.query(User).filter(
            User.tenant_id == t.id,
            User.deleted_at.is_(None),
        ).count()

        last = (
            db.query(GlobalAdminAuditLog)
            .filter(
                GlobalAdminAuditLog.target_tenant_id == t.id,
                GlobalAdminAuditLog.action.in_([
                    "remote_access.tenant.enabled",
                    "remote_access.tenant.disabled",
                ]),
            )
            .order_by(GlobalAdminAuditLog.created_at.desc())
            .first()
        )

        last_changed_at = last.created_at.isoformat() if last else None
        last_changed_by_email: Optional[str] = None
        if last:
            admin_user = db.query(User).filter(User.id == last.global_admin_id).first()
            if admin_user:
                last_changed_by_email = admin_user.email

        rows.append({
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "user_count": user_count,
            "remote_access_enabled": bool(t.remote_access_enabled),
            "last_changed_at": last_changed_at,
            "last_changed_by_email": last_changed_by_email,
        })
    return rows


def set_tenant_entitlement(
    db: Session,
    admin: User,
    tenant_id: str,
    enabled: bool,
    reason: Optional[str],
    request=None,
) -> Dict[str, Any]:
    """Toggle Tenant.remote_access_enabled and emit both audit streams."""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise ValueError(f"Tenant {tenant_id} not found")

    previous = bool(tenant.remote_access_enabled)
    tenant.remote_access_enabled = bool(enabled)
    tenant.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(tenant)

    action = "remote_access.tenant.enabled" if enabled else "remote_access.tenant.disabled"
    details: Dict[str, Any] = {
        "previous": previous,
        "new": enabled,
    }
    if reason:
        details["reason"] = reason

    # Global admin stream
    log_admin_action(
        db=db,
        admin=admin,
        action=action,
        target_tenant_id=tenant.id,
        resource_type="tenant",
        resource_id=tenant.id,
        details=details,
        request=request,
    )
    # Tenant-scoped stream (so the tenant owner sees it in their audit log)
    log_tenant_event(
        db=db,
        tenant_id=tenant.id,
        user_id=admin.id if admin else None,
        action=action,
        resource_type="tenant",
        resource_id=tenant.id,
        details=details,
        request=request,
        severity="info",
    )

    # Reuse the list helper for a single row, so the returned shape matches
    for row in list_tenants_with_entitlement(db):
        if row["id"] == tenant.id:
            return row
    # Fallback (shouldn't happen)
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "user_count": 0,
        "remote_access_enabled": bool(tenant.remote_access_enabled),
        "last_changed_at": None,
        "last_changed_by_email": None,
    }
