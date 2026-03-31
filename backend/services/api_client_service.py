"""
API Client Service — Public API v1
Handles CRUD operations for API clients, secret management, token generation,
and scope resolution for the OAuth2 client credentials flow.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from auth_utils import hash_password, verify_password, create_access_token
from models import ApiClient, ApiClientToken, ApiRequestLog
from models_rbac import Role, RolePermission, Permission

logger = logging.getLogger(__name__)

# Role-to-permission mapping for predefined API client roles
# These map to subsets of existing RBAC roles, excluding billing/team/user management
API_ROLE_SCOPES = {
    "api_agent_only": [
        "agents.read", "agents.execute",
    ],
    "api_readonly": [
        "agents.read", "contacts.read", "memory.read", "flows.read",
        "knowledge.read", "analytics.read",
        "hub.read",
    ],
    "api_member": [
        "agents.read", "agents.write", "agents.execute",
        "contacts.read", "contacts.write",
        "memory.read", "memory.write",
        "flows.read", "flows.write", "flows.execute",
        "knowledge.read", "knowledge.write",
        "analytics.read",
        "tools.read", "tools.execute",
        "hub.read", "hub.write",
    ],
    "api_admin": [
        "agents.read", "agents.write", "agents.delete", "agents.execute",
        "contacts.read", "contacts.write", "contacts.delete",
        "memory.read", "memory.write", "memory.delete",
        "flows.read", "flows.write", "flows.delete", "flows.execute",
        "knowledge.read", "knowledge.write", "knowledge.delete",
        "analytics.read",
        "tools.read", "tools.manage", "tools.execute",
        "org.settings.read", "org.settings.write",
        "hub.read", "hub.write",
    ],
    "api_owner": [
        "agents.read", "agents.write", "agents.delete", "agents.execute",
        "contacts.read", "contacts.write", "contacts.delete",
        "memory.read", "memory.write", "memory.delete",
        "flows.read", "flows.write", "flows.delete", "flows.execute",
        "knowledge.read", "knowledge.write", "knowledge.delete",
        "analytics.read", "audit.read",
        "tools.read", "tools.manage", "tools.execute",
        "org.settings.read", "org.settings.write",
        "hub.read", "hub.write",
    ],
}

VALID_ROLES = list(API_ROLE_SCOPES.keys()) + ["custom"]


class ApiClientService:

    def __init__(self, db: Session):
        self.db = db

    def create_client(
        self,
        tenant_id: str,
        name: str,
        description: Optional[str],
        role: str,
        rate_limit_rpm: int = 60,
        created_by: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        custom_scopes: Optional[List[str]] = None,
        creator_permissions: Optional[List[str]] = None,
    ) -> Tuple[ApiClient, str]:
        """
        Create a new API client. Returns (client, raw_secret).
        The raw_secret is shown only once and must be saved by the caller.
        """
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role: {role}. Must be one of: {VALID_ROLES}")

        if role == "custom" and not custom_scopes:
            raise ValueError("custom_scopes is required when role is 'custom'")

        # Validate custom scopes against valid permission names
        if custom_scopes:
            valid_perms = {p.name for p in self.db.query(Permission.name).all()}
            invalid = set(custom_scopes) - valid_perms
            if invalid:
                raise ValueError(f"Invalid scopes: {invalid}")

        # BUG-070 FIX: Prevent privilege escalation
        if creator_permissions is not None:
            effective_scopes = custom_scopes if role == "custom" else API_ROLE_SCOPES.get(role, [])
            escalated = set(effective_scopes) - set(creator_permissions)
            if escalated:
                raise ValueError(
                    f"Privilege escalation denied: cannot grant permissions you don't hold: {', '.join(sorted(escalated))}"
                )

        # Generate client_id and secret
        client_id = f"tsn_ci_{secrets.token_urlsafe(16)}"
        raw_secret = f"tsn_cs_{secrets.token_urlsafe(32)}"
        secret_hash = hash_password(raw_secret)
        prefix = raw_secret[:12]

        client = ApiClient(
            tenant_id=tenant_id,
            name=name,
            description=description,
            client_id=client_id,
            client_secret_hash=secret_hash,
            client_secret_prefix=prefix,
            role=role,
            custom_scopes=custom_scopes if role == "custom" else None,
            is_active=True,
            rate_limit_rpm=rate_limit_rpm,
            expires_at=expires_at,
            created_by=created_by,
        )
        self.db.add(client)
        self.db.commit()
        self.db.refresh(client)

        logger.info(f"Created API client '{name}' (id={client.client_id}) for tenant={tenant_id} role={role}")
        return client, raw_secret

    def verify_secret(self, client_id: str, raw_secret: str) -> Optional[ApiClient]:
        """
        Verify client_id + secret combination.
        Returns the ApiClient if valid, None otherwise.
        """
        client = self.db.query(ApiClient).filter(
            ApiClient.client_id == client_id
        ).first()

        if not client:
            return None

        if not client.is_active:
            logger.warning(f"API client '{client_id}' is inactive")
            return None

        if client.expires_at and client.expires_at < datetime.utcnow():
            logger.warning(f"API client '{client_id}' has expired")
            return None

        if not verify_password(raw_secret, client.client_secret_hash):
            return None

        # Update last_used_at
        client.last_used_at = datetime.utcnow()
        self.db.commit()

        return client

    def resolve_by_api_key(self, api_key: str) -> Optional[ApiClient]:
        """
        Resolve an API client from the X-API-Key header (direct auth mode).
        The api_key IS the raw_secret; we find candidates by prefix match.
        """
        prefix = api_key[:12]
        candidates = self.db.query(ApiClient).filter(
            ApiClient.client_secret_prefix == prefix,
            ApiClient.is_active == True,
        ).all()

        for candidate in candidates:
            if candidate.expires_at and candidate.expires_at < datetime.utcnow():
                continue
            if verify_password(api_key, candidate.client_secret_hash):
                candidate.last_used_at = datetime.utcnow()
                self.db.commit()
                return candidate

        return None

    def generate_token(self, client: ApiClient, ip_address: Optional[str] = None) -> dict:
        """
        Generate a JWT access token for an API client.
        Returns {access_token, token_type, expires_in, scope}.
        """
        scopes = self.resolve_scopes(client)
        expires_delta = timedelta(hours=1)

        token = create_access_token(
            data={
                "sub": f"api_client:{client.id}",
                "type": "api_client",
                "tenant_id": client.tenant_id,
                "client_id": client.client_id,
                "scopes": scopes,
                "secret_rotated_at": client.secret_rotated_at.isoformat() if client.secret_rotated_at else None,
            },
            expires_delta=expires_delta,
        )

        # Store token hash for audit/revocation
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        token_record = ApiClientToken(
            api_client_id=client.id,
            token_hash=token_hash,
            scopes=scopes,
            expires_at=datetime.utcnow() + expires_delta,
            ip_address=ip_address,
        )
        self.db.add(token_record)
        self.db.commit()

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 3600,
            "scope": " ".join(scopes),
        }

    def rotate_secret(self, client: ApiClient) -> str:
        """
        Generate a new secret for an API client, invalidating the old one.
        Returns the new raw_secret (shown only once).
        """
        raw_secret = f"tsn_cs_{secrets.token_urlsafe(32)}"
        client.client_secret_hash = hash_password(raw_secret)
        client.client_secret_prefix = raw_secret[:12]
        client.secret_rotated_at = datetime.utcnow()
        client.updated_at = datetime.utcnow()
        self.db.commit()

        logger.info(f"Rotated secret for API client '{client.client_id}'")
        return raw_secret

    def revoke_client(self, client: ApiClient):
        """Deactivate an API client. All issued tokens will fail on next use."""
        client.is_active = False
        client.updated_at = datetime.utcnow()
        self.db.commit()
        logger.info(f"Revoked API client '{client.client_id}'")

    def get_client_by_id(self, client_id: str, tenant_id: Optional[str] = None) -> Optional[ApiClient]:
        """Get an API client by its public client_id, optionally filtered by tenant."""
        query = self.db.query(ApiClient).filter(ApiClient.client_id == client_id)
        if tenant_id:
            query = query.filter(ApiClient.tenant_id == tenant_id)
        return query.first()

    def get_client_by_internal_id(self, internal_id: int) -> Optional[ApiClient]:
        """Get an API client by its internal database ID."""
        return self.db.query(ApiClient).filter(ApiClient.id == internal_id).first()

    def list_clients(self, tenant_id: str) -> List[ApiClient]:
        """List all API clients for a tenant."""
        return self.db.query(ApiClient).filter(
            ApiClient.tenant_id == tenant_id
        ).order_by(ApiClient.created_at.desc()).all()

    def update_client(
        self,
        client: ApiClient,
        name: Optional[str] = None,
        description: Optional[str] = None,
        role: Optional[str] = None,
        rate_limit_rpm: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        custom_scopes: Optional[List[str]] = None,
        updater_permissions: Optional[List[str]] = None,
    ) -> ApiClient:
        """Update API client fields."""
        if name is not None:
            client.name = name
        if description is not None:
            client.description = description
        if role is not None:
            if role not in VALID_ROLES:
                raise ValueError(f"Invalid role: {role}")
            # Privilege escalation guard (same as create_client)
            if updater_permissions is not None:
                new_scopes = custom_scopes if role == "custom" else API_ROLE_SCOPES.get(role, [])
                escalated = set(new_scopes) - set(updater_permissions)
                if escalated:
                    raise ValueError(
                        f"Privilege escalation denied: cannot grant permissions you don't hold: {', '.join(sorted(escalated))}"
                    )
            client.role = role
        if rate_limit_rpm is not None:
            client.rate_limit_rpm = rate_limit_rpm
        if expires_at is not None:
            client.expires_at = expires_at
        if custom_scopes is not None:
            # Privilege escalation guard for custom scopes
            if updater_permissions is not None:
                escalated = set(custom_scopes) - set(updater_permissions)
                if escalated:
                    raise ValueError(
                        f"Privilege escalation denied: cannot grant permissions you don't hold: {', '.join(sorted(escalated))}"
                    )
            client.custom_scopes = custom_scopes

        client.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(client)
        return client

    def resolve_scopes(self, client: ApiClient) -> List[str]:
        """Resolve the effective permissions/scopes for an API client."""
        if client.role == "custom":
            return client.custom_scopes or []

        return API_ROLE_SCOPES.get(client.role, [])

    def get_usage_stats(self, client_id: int) -> dict:
        """Get usage statistics for an API client."""
        from sqlalchemy import func

        total_requests = self.db.query(func.count(ApiRequestLog.id)).filter(
            ApiRequestLog.api_client_id == client_id
        ).scalar() or 0

        error_requests = self.db.query(func.count(ApiRequestLog.id)).filter(
            ApiRequestLog.api_client_id == client_id,
            ApiRequestLog.status_code >= 400,
        ).scalar() or 0

        avg_response_time = self.db.query(func.avg(ApiRequestLog.response_time_ms)).filter(
            ApiRequestLog.api_client_id == client_id,
            ApiRequestLog.response_time_ms.isnot(None),
        ).scalar()

        last_request = self.db.query(ApiRequestLog).filter(
            ApiRequestLog.api_client_id == client_id
        ).order_by(ApiRequestLog.created_at.desc()).first()

        return {
            "total_requests": total_requests,
            "error_requests": error_requests,
            "error_rate": round(error_requests / total_requests * 100, 2) if total_requests > 0 else 0,
            "avg_response_time_ms": round(avg_response_time, 1) if avg_response_time else None,
            "last_request_at": last_request.created_at.isoformat() if last_request else None,
        }

    def log_request(
        self,
        api_client_id: int,
        method: str,
        path: str,
        status_code: int,
        response_time_ms: Optional[int] = None,
        ip_address: Optional[str] = None,
    ):
        """Log an API request for audit trail."""
        log_entry = ApiRequestLog(
            api_client_id=api_client_id,
            method=method,
            path=path,
            status_code=status_code,
            response_time_ms=response_time_ms,
            ip_address=ip_address,
        )
        self.db.add(log_entry)
        self.db.commit()
