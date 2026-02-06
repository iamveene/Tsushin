"""
Authentication Service
Phase 7.6.3 - Authentication Backend

Handles user authentication, registration, and password management.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models_rbac import User, Tenant, Role, UserRole, PasswordResetToken, UserInvitation
from auth_utils import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    generate_reset_token,
    generate_invitation_token
)


class AuthenticationError(Exception):
    """Custom exception for authentication errors"""
    pass


class AuthService:
    """Service for handling authentication operations"""

    def __init__(self, db: Session):
        self.db = db

    def login(self, email: str, password: str) -> Tuple[User, str]:
        """
        Authenticate user and generate access token

        Args:
            email: User email
            password: Plain text password

        Returns:
            Tuple of (User object, JWT token)

        Raises:
            AuthenticationError: If credentials are invalid
        """
        # Find user by email
        user = self.db.query(User).filter(User.email == email).first()

        if not user:
            raise AuthenticationError("Invalid credentials")

        # Verify password
        if not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")

        # Check if user is active
        if not user.is_active:
            raise AuthenticationError("Account is disabled")

        # Update last login
        user.last_login_at = datetime.utcnow()
        self.db.commit()

        # Get user's role for the token
        user_role = self.db.query(UserRole).filter(UserRole.user_id == user.id).first()
        role_name = None
        if user_role:
            role = self.db.query(Role).filter(Role.id == user_role.role_id).first()
            role_name = role.name if role else None

        # Generate access token
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "tenant_id": user.tenant_id,
            "is_global_admin": user.is_global_admin,
            "role": role_name
        }
        token = create_access_token(token_data)

        return user, token

    def signup(self, email: str, password: str, full_name: str, org_name: str, is_global_admin: bool = False) -> Tuple[User, Tenant, str]:
        """
        Register a new user and create their organization

        Args:
            email: User email
            password: Plain text password
            full_name: User's full name
            org_name: Organization name
            is_global_admin: Whether user should have global admin privileges (default: False)

        Returns:
            Tuple of (User object, Tenant object, JWT token)

        Raises:
            AuthenticationError: If email already exists or validation fails
        """
        # Check if email already exists
        existing_user = self.db.query(User).filter(User.email == email).first()
        if existing_user:
            raise AuthenticationError("Email already registered")

        # Validate password strength (minimum 8 characters)
        if len(password) < 8:
            raise AuthenticationError("Password must be at least 8 characters")

        # Generate tenant ID and slug
        import re
        tenant_id = f"tenant_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        slug = re.sub(r'[^a-z0-9-]', '', org_name.lower().replace(' ', '-'))[:50]

        # Check if slug already exists, append number if needed
        existing_tenant = self.db.query(Tenant).filter(Tenant.slug == slug).first()
        if existing_tenant:
            slug = f"{slug}-{datetime.utcnow().strftime('%H%M%S')}"

        # Create tenant
        tenant = Tenant(
            id=tenant_id,
            name=org_name,
            slug=slug,
            plan='free',  # Default plan
            max_users=5,
            max_agents=5,
            max_monthly_requests=10000,
            is_active=True,
            status='active'
        )
        self.db.add(tenant)
        self.db.flush()  # Get tenant ID

        # Hash password
        hashed_password = hash_password(password)

        # Create user
        user = User(
            email=email,
            password_hash=hashed_password,
            full_name=full_name,
            tenant_id=tenant_id,
            is_global_admin=is_global_admin,
            is_active=True,
            email_verified=False  # Can be verified later
        )
        self.db.add(user)
        self.db.flush()  # Get user ID

        # Assign owner role
        owner_role = self.db.query(Role).filter(Role.name == 'owner').first()
        if owner_role:
            user_role = UserRole(
                user_id=user.id,
                role_id=owner_role.id,
                tenant_id=tenant_id,
                assigned_by=user.id  # Self-assigned on signup
            )
            self.db.add(user_role)

        self.db.commit()

        # Generate access token
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "tenant_id": user.tenant_id,
            "is_global_admin": user.is_global_admin,
            "role": "owner"
        }
        token = create_access_token(token_data)

        return user, tenant, token

    def request_password_reset(self, email: str) -> Optional[str]:
        """
        Generate password reset token for user

        Args:
            email: User email

        Returns:
            Reset token if user exists, None otherwise
        """
        user = self.db.query(User).filter(User.email == email).first()

        if not user:
            # Don't reveal if email exists - return None silently
            return None

        # Generate reset token
        token = generate_reset_token()
        expires_at = datetime.utcnow() + timedelta(hours=24)  # 24 hour expiry

        # Save token
        reset_token = PasswordResetToken(
            user_id=user.id,
            token=token,
            expires_at=expires_at
        )
        self.db.add(reset_token)
        self.db.commit()

        return token

    def reset_password(self, token: str, new_password: str) -> bool:
        """
        Reset user password using reset token

        Args:
            token: Password reset token
            new_password: New plain text password

        Returns:
            True if successful, False otherwise

        Raises:
            AuthenticationError: If token is invalid or expired
        """
        # Find token
        reset_token = self.db.query(PasswordResetToken).filter(
            PasswordResetToken.token == token
        ).first()

        if not reset_token:
            raise AuthenticationError("Invalid reset token")

        # Check if already used
        if reset_token.used_at:
            raise AuthenticationError("Reset token already used")

        # Check if expired
        if reset_token.expires_at < datetime.utcnow():
            raise AuthenticationError("Reset token expired")

        # Validate new password
        if len(new_password) < 8:
            raise AuthenticationError("Password must be at least 8 characters")

        # Get user
        user = self.db.query(User).filter(User.id == reset_token.user_id).first()
        if not user:
            raise AuthenticationError("User not found")

        # Update password
        user.password_hash = hash_password(new_password)

        # Mark token as used
        reset_token.used_at = datetime.utcnow()

        self.db.commit()

        return True

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token

        Args:
            token: JWT access token

        Returns:
            Token payload if valid, None otherwise
        """
        return decode_access_token(token)

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get user by ID

        Args:
            user_id: User ID

        Returns:
            User object if found, None otherwise
        """
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_permissions(self, user_id: int) -> list:
        """
        Get all permissions for a user

        Args:
            user_id: User ID

        Returns:
            List of permission names
        """
        from models_rbac import Permission, RolePermission

        # Get user's role
        user_role = self.db.query(UserRole).filter(UserRole.user_id == user_id).first()

        if not user_role:
            return []

        # Get permissions for the role
        permissions = (
            self.db.query(Permission.name)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .filter(RolePermission.role_id == user_role.role_id)
            .all()
        )

        return [p[0] for p in permissions]
