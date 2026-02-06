"""
SQLAlchemy Models for RBAC & Multi-Tenancy
Phase 7.6.3 - Authentication Backend

These models correspond to the database schema created in migration 001.
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from models import Base


class Tenant(Base):
    """Organization/Tenant model"""
    __tablename__ = "tenant"

    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    plan = Column(String(50), default='free')  # Legacy: plan name string
    plan_id = Column(Integer, ForeignKey('subscription_plan.id'), nullable=True)  # New: FK to subscription_plan
    max_users = Column(Integer, default=1)
    max_agents = Column(Integer, default=1)
    max_monthly_requests = Column(Integer, default=1000)
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default='active')  # active, suspended, trial
    created_by_global_admin = Column(Integer, ForeignKey('user.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    users = relationship("User", back_populates="tenant", foreign_keys="User.tenant_id")
    user_roles = relationship("UserRole", back_populates="tenant")
    subscription_plan = relationship("SubscriptionPlan", back_populates="tenants", foreign_keys=[plan_id])
    sso_config = relationship("TenantSSOConfig", back_populates="tenant", uselist=False)


class User(Base):
    """User account model"""
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=True)  # Nullable for global admins
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for SSO-only users
    full_name = Column(String(255), nullable=True)
    is_global_admin = Column(Boolean, default=False, index=True)
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    # SSO / Authentication fields
    auth_provider = Column(String(20), default='local', index=True)  # local, google
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    avatar_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="users", foreign_keys=[tenant_id])
    user_roles = relationship("UserRole", back_populates="user", foreign_keys="UserRole.user_id")
    sent_invitations = relationship("UserInvitation", back_populates="inviter", foreign_keys="UserInvitation.invited_by")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user")


class Role(Base):
    """Role definition model"""
    __tablename__ = "role"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_system_role = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    role_permissions = relationship("RolePermission", back_populates="role")
    user_roles = relationship("UserRole", back_populates="role")


class Permission(Base):
    """Permission model"""
    __tablename__ = "permission"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    resource = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    role_permissions = relationship("RolePermission", back_populates="permission")


class RolePermission(Base):
    """Role-Permission mapping"""
    __tablename__ = "role_permission"

    id = Column(Integer, primary_key=True, autoincrement=True)
    role_id = Column(Integer, ForeignKey('role.id'), nullable=False)
    permission_id = Column(Integer, ForeignKey('permission.id'), nullable=False)

    # Relationships
    role = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")

    # Unique constraint
    __table_args__ = (
        Index('uq_role_permission', 'role_id', 'permission_id', unique=True),
    )


class UserRole(Base):
    """User-Role-Tenant mapping"""
    __tablename__ = "user_role"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False, index=True)
    role_id = Column(Integer, ForeignKey('role.id'), nullable=False)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=False, index=True)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    assigned_by = Column(Integer, ForeignKey('user.id'), nullable=True)

    # Relationships
    user = relationship("User", back_populates="user_roles", foreign_keys=[user_id], overlaps="sent_invitations")
    role = relationship("Role", back_populates="user_roles")
    tenant = relationship("Tenant", back_populates="user_roles")
    assigner = relationship("User", foreign_keys=[assigned_by], overlaps="user_roles,user")

    # Unique constraint: one role per user per tenant
    __table_args__ = (
        Index('uq_user_tenant', 'user_id', 'tenant_id', unique=True),
    )


class UserInvitation(Base):
    """User invitation model"""
    __tablename__ = "user_invitation"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=False)
    email = Column(String(255), nullable=False)
    role_id = Column(Integer, ForeignKey('role.id'), nullable=False)
    invited_by = Column(Integer, ForeignKey('user.id'), nullable=False)
    invitation_token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    inviter = relationship("User", back_populates="sent_invitations", foreign_keys=[invited_by])

    # Unique constraint
    __table_args__ = (
        Index('uq_tenant_email', 'tenant_id', 'email', unique=True),
    )


class PasswordResetToken(Base):
    """Password reset token model"""
    __tablename__ = "password_reset_token"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="password_reset_tokens")


class SystemIntegration(Base):
    """System-wide integration managed by global admins"""
    __tablename__ = "system_integration"

    id = Column(Integer, primary_key=True, autoincrement=True)
    service_type = Column(String(50), nullable=False, index=True)  # ai_provider, tool_api, infrastructure
    service_name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    api_key = Column(Text, nullable=True)  # Encrypted
    config_json = Column(Text, nullable=True)  # JSON string
    is_active = Column(Boolean, default=True, index=True)
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)
    configured_by_global_admin = Column(Integer, ForeignKey('user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TenantSystemIntegrationUsage(Base):
    """Track tenant usage of system integrations"""
    __tablename__ = "tenant_system_integration_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), nullable=False)
    system_integration_id = Column(Integer, ForeignKey('system_integration.id'), nullable=False)
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, nullable=True)

    # Unique constraint
    __table_args__ = (
        Index('uq_tenant_integration', 'tenant_id', 'system_integration_id', unique=True),
    )


class GlobalAdminAuditLog(Base):
    """Audit log for global admin actions"""
    __tablename__ = "global_admin_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    global_admin_id = Column(Integer, ForeignKey('user.id'), nullable=False, index=True)
    action = Column(String(100), nullable=False, index=True)
    target_tenant_id = Column(String(50), nullable=True, index=True)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    details_json = Column(Text, nullable=True)  # JSON string
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SubscriptionPlan(Base):
    """
    Subscription plan definition.
    Database-driven plans management for multi-tenant SaaS.
    """
    __tablename__ = "subscription_plan"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)  # free, pro, team, enterprise
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price_monthly = Column(Integer, default=0)  # Price in cents
    price_yearly = Column(Integer, default=0)   # Price in cents (annual)
    max_users = Column(Integer, default=1)
    max_agents = Column(Integer, default=1)
    max_monthly_requests = Column(Integer, default=1000)
    max_knowledge_docs = Column(Integer, default=10)
    max_flows = Column(Integer, default=5)
    max_mcp_instances = Column(Integer, default=1)
    features_json = Column(Text, nullable=True)  # JSON array of feature flags
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)  # Show in pricing page
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenants = relationship("Tenant", back_populates="subscription_plan", foreign_keys="Tenant.plan_id")


class TenantSSOConfig(Base):
    """
    Per-tenant SSO configuration.
    Allows tenants to enable/configure Google SSO authentication.
    """
    __tablename__ = "tenant_sso_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(50), ForeignKey('tenant.id'), unique=True, nullable=False)
    google_sso_enabled = Column(Boolean, default=False)
    google_client_id = Column(String(255), nullable=True)      # Optional BYOT (Bring Your Own Token)
    google_client_secret_encrypted = Column(Text, nullable=True)  # MED-007 Security Fix: Fernet encrypted
    allowed_domains = Column(Text, nullable=True)               # JSON array, e.g. ["company.com"]
    auto_provision_users = Column(Boolean, default=False)       # Auto-create users on first login
    default_role_id = Column(Integer, ForeignKey('role.id'), nullable=True)  # Role for auto-provisioned users
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", back_populates="sso_config")
    default_role = relationship("Role")
