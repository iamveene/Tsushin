"""
Authentication API Routes
Phase 7.6.3 - Authentication Endpoints

Provides REST API endpoints for authentication operations.
Includes Google SSO support.

MED-004 FIX: Rate limiting added to prevent brute force attacks.
MED-009 FIX: One-time code exchange for SSO callback (removes JWT from URL).
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import logging
import os
import secrets

# MED-004 FIX: Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address

from db import get_db
from auth_service import AuthService, AuthenticationError
from models_rbac import User, UserInvitation, UserRole, Role, Tenant, TenantSSOConfig
from models import GoogleOAuthCredentials, OAuthState
from auth_utils import hash_password, verify_password, hash_token, create_access_token
from auth_dependencies import get_current_user_required
from auth_google import GoogleSSOService, GoogleSSOError, get_google_sso_service
from services.audit_service import log_tenant_event, TenantAuditActions
import settings


def get_encryption_key(db: Session) -> Optional[str]:
    """Get encryption key from database or environment for decrypting OAuth secrets."""
    from services.encryption_key_service import get_google_encryption_key
    return get_google_encryption_key(db)


def _set_session_cookie(response: JSONResponse, token: str) -> None:
    """
    SEC-005: Set the httpOnly session cookie on the response.
    Secure flag: controlled by TSN_SSL_MODE env var (defaults to True for HTTPS installs).
    SameSite=lax: sent on top-level navigations, protects against CSRF.
    max_age=86400: matches JWT 24-hour expiry.
    """
    import os
    ssl_mode = os.environ.get("TSN_SSL_MODE", "").lower()
    use_secure = ssl_mode not in ("", "off", "none", "disabled")
    response.set_cookie(
        key="tsushin_session",
        value=token,
        httponly=True,
        secure=use_secure,
        samesite="lax",
        max_age=86400,  # 24 h — matches JWT expiry
        path="/",
    )


logger = logging.getLogger(__name__)

# MED-004 FIX: Rate limiter for auth endpoints (uses app.state.limiter from app.py)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# Request/Response Models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    org_name: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class MessageResponse(BaseModel):
    message: str


# MED-009 FIX: One-time code exchange models
class SSOCodeExchangeRequest(BaseModel):
    """Request to exchange one-time SSO code for JWT token."""
    code: str


class SSOCodeExchangeResponse(BaseModel):
    """Response with JWT token after code exchange."""
    access_token: str
    token_type: str = "bearer"
    redirect_after: Optional[str] = None


class SetupWizardRequest(BaseModel):
    tenant_name: str
    # Tenant admin fields
    admin_email: EmailStr
    admin_password: str
    admin_full_name: str
    # Global admin fields (optional - will be auto-generated if not provided)
    global_admin_email: Optional[EmailStr] = None
    global_admin_password: Optional[str] = None
    global_admin_full_name: Optional[str] = None
    # API keys
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    create_default_agents: bool = True


# BUG-140 FIX: Removed local get_current_user function that bypassed JWT invalidation
# (password_changed_at vs token iat check). All endpoints now use
# get_current_user_required from auth_dependencies.py instead.


# ============================================================================
# MED-009 FIX: SSO Callback Code Helpers
# ============================================================================
# Instead of transmitting JWT in URL query string (exposed in logs, history, referrer),
# we generate a short-lived one-time code that can be exchanged for the JWT.

def _generate_sso_callback_code(
    db: Session,
    jwt_token: str,
    redirect_after: Optional[str] = None,
    expires_in_seconds: int = 60
) -> str:
    """
    Generate a one-time code for SSO callback and store JWT temporarily.

    Args:
        db: Database session
        jwt_token: The JWT token to store
        redirect_after: Optional redirect URL after login
        expires_in_seconds: Code expiration (default 60 seconds)

    Returns:
        One-time code to be used in URL
    """
    import json

    code = secrets.token_urlsafe(32)  # 256-bit random code
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

    # Store JWT in metadata_json (encrypted at rest by DB-level encryption if configured)
    metadata = {
        "jwt_token": jwt_token,
        "redirect_after": redirect_after
    }

    oauth_state = OAuthState(
        state_token=code,
        integration_type="sso_callback_code",  # Distinct type for SSO callbacks
        expires_at=expires_at,
        redirect_url=redirect_after,
        metadata_json=json.dumps(metadata)
    )

    db.add(oauth_state)
    db.commit()

    logger.debug(f"Generated SSO callback code: {code[:8]}...")
    return code


def _exchange_sso_callback_code(db: Session, code: str) -> tuple[str, Optional[str]]:
    """
    Exchange one-time SSO callback code for JWT token.

    Args:
        db: Database session
        code: One-time code from SSO callback URL

    Returns:
        Tuple of (jwt_token, redirect_after)

    Raises:
        ValueError: If code is invalid, expired, or already used
    """
    import json

    oauth_state = db.query(OAuthState).filter(
        OAuthState.state_token == code,
        OAuthState.integration_type == "sso_callback_code",
        OAuthState.expires_at > datetime.utcnow()
    ).first()

    if not oauth_state:
        logger.warning(f"Invalid or expired SSO callback code: {code[:8]}...")
        raise ValueError("Invalid or expired authentication code")

    # Parse metadata to get JWT
    try:
        metadata = json.loads(oauth_state.metadata_json) if oauth_state.metadata_json else {}
    except json.JSONDecodeError:
        logger.error(f"Failed to parse metadata for SSO code: {code[:8]}...")
        raise ValueError("Invalid authentication data")

    jwt_token = metadata.get("jwt_token")
    redirect_after = metadata.get("redirect_after")

    if not jwt_token:
        logger.error(f"No JWT token in SSO code metadata: {code[:8]}...")
        raise ValueError("Invalid authentication data")

    # Delete code after use (one-time token)
    db.delete(oauth_state)
    db.commit()

    logger.info(f"SSO callback code exchanged successfully: {code[:8]}...")
    return jwt_token, redirect_after


# Authentication Endpoints

@router.post("/login", response_model=AuthResponse)
@limiter.limit("5/minute")  # MED-004 FIX: Prevent brute force attacks
async def login(request: Request, login_request: LoginRequest, db: Session = Depends(get_db)):
    """
    Login endpoint

    Authenticates user with email and password, returns JWT access token.
    Rate limited to 5 requests per minute per IP.
    """
    auth_service = AuthService(db)

    try:
        user, token = auth_service.login(login_request.email, login_request.password)

        # Audit: successful login
        log_tenant_event(db, user.tenant_id, user.id, TenantAuditActions.AUTH_LOGIN, "user", str(user.id), {"email": user.email}, request)

        # Get user permissions for frontend
        permissions = auth_service.get_user_permissions(user.id)

        # SEC-005: Return token in JSON body (for WebSocket/backwards compat) AND
        # set it as an httpOnly cookie so the browser never touches it via JS.
        response = JSONResponse(content={
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "tenant_id": user.tenant_id,
                "is_global_admin": user.is_global_admin,
                "permissions": permissions,
            },
        })
        _set_session_cookie(response, token)
        return response
    except AuthenticationError as e:
        # Audit: failed login (only if user exists — password mismatch)
        failed_user = db.query(User).filter(User.email == login_request.email, User.deleted_at.is_(None)).first()
        if failed_user and failed_user.tenant_id:
            log_tenant_event(db, failed_user.tenant_id, None, TenantAuditActions.AUTH_FAILED_LOGIN, "user", None, {"email": login_request.email}, request, severity="warning")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")  # MED-004 FIX: Prevent spam account creation
async def signup(request: Request, signup_request: SignupRequest, db: Session = Depends(get_db)):
    """
    Signup endpoint

    Registers new user and creates their organization. Returns JWT access token.
    """
    auth_service = AuthService(db)

    try:
        user, tenant, token = auth_service.signup(
            email=signup_request.email,
            password=signup_request.password,
            full_name=signup_request.full_name,
            org_name=signup_request.org_name
        )

        # Get user permissions for frontend
        permissions = auth_service.get_user_permissions(user.id)

        # SEC-005: Set httpOnly session cookie on signup
        response = JSONResponse(status_code=201, content={
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "tenant_id": user.tenant_id,
                "is_global_admin": user.is_global_admin,
                "permissions": permissions,
            },
        })
        _set_session_cookie(response, token)
        return response
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/setup-wizard", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/hour")  # MED-004 FIX: Prevent abuse
async def setup_wizard(
    request: Request,
    setup_request: SetupWizardRequest,
    db: Session = Depends(get_db)
):
    """
    Setup Wizard Endpoint (Installation Only)

    Creates initial tenant, admin user, and optionally seeds default agents.
    This endpoint should only be used during first-time installation.

    Security: Only accessible if database is empty (no users exist)

    Args:
        tenant_name: Organization name
        admin_email: Admin user email
        admin_password: Admin user password
        admin_full_name: Admin user full name
        gemini_api_key: Optional Gemini API key
        openai_api_key: Optional OpenAI API key
        anthropic_api_key: Optional Anthropic API key
        create_default_agents: Whether to create default system agents
        db: Database session

    Returns:
        {
            "success": true,
            "tenant_id": "uuid",
            "user_id": 123,
            "access_token": "jwt_token",
            "agents_created": ["Tsushin", "Kokoro", ...]
        }
    """
    # Security check: Only allow if no users exist (first-time setup)
    existing_users_count = db.query(User).count()
    if existing_users_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup wizard can only be run on a fresh installation. Users already exist."
        )

    # BUG-061 FIX: TOCTOU race condition — re-verify under a serialized transaction.
    # For SQLite: BEGIN IMMEDIATE acquires a reserved lock, preventing concurrent writes.
    # For PostgreSQL: pg_advisory_xact_lock provides an exclusive advisory lock.
    from sqlalchemy import text
    db_dialect = db.bind.dialect.name if db.bind else "sqlite"
    if db_dialect == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(1)"))
    else:
        # SQLite: BEGIN IMMEDIATE ensures only one writer at a time
        db.execute(text("BEGIN IMMEDIATE"))

    # Re-check user count under the lock to prevent race condition
    user_count_locked = db.query(User).count()
    if user_count_locked > 0:
        if db_dialect != "postgresql":
            db.execute(text("ROLLBACK"))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed"
        )

    auth_service = AuthService(db)

    try:
        # Step 1: Create tenant and tenant owner (reuse signup logic)
        tenant_owner, tenant, tenant_owner_token = auth_service.signup(
            email=setup_request.admin_email,
            password=setup_request.admin_password,
            full_name=setup_request.admin_full_name,
            org_name=setup_request.tenant_name
        )

        logger.info(f"Setup wizard: Created tenant '{tenant.name}' and tenant admin '{tenant_owner.email}'")

        # Step 2: Create global admin user (no tenant affiliation)
        from auth_utils import hash_password
        import secrets

        # Auto-generate global admin credentials if not provided
        global_admin_email = setup_request.global_admin_email or f"globaladmin@{tenant.slug}.local"
        global_admin_password = setup_request.global_admin_password or secrets.token_urlsafe(16)
        global_admin_full_name = setup_request.global_admin_full_name or "Global Administrator"

        # Check if global admin email already exists
        existing_global_admin = db.query(User).filter(
            User.email == global_admin_email
        ).first()

        if existing_global_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Global admin email already exists"
            )

        # Validate that global admin email is different from tenant admin
        if global_admin_email == setup_request.admin_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Global admin and tenant admin must use different email addresses"
            )

        # Hash password
        global_admin_password_hash = hash_password(global_admin_password)

        # Create global admin (no tenant affiliation)
        global_admin = User(
            email=global_admin_email,
            password_hash=global_admin_password_hash,
            full_name=global_admin_full_name,
            tenant_id=None,  # No tenant for pure global admin
            is_global_admin=True,  # Global admin flag
            is_active=True,
            email_verified=True
        )
        db.add(global_admin)
        db.commit()
        db.refresh(global_admin)

        logger.info(f"Setup wizard: Created global admin '{global_admin.email}'")

        # Step 3: Store API keys if provided
        from services.api_key_service import store_api_key

        api_keys_stored = []
        if setup_request.gemini_api_key:
            store_api_key("gemini", setup_request.gemini_api_key, tenant.id, db)
            api_keys_stored.append("gemini")
            logger.info(f"Setup wizard: Stored Gemini API key for tenant {tenant.id}")

        if setup_request.openai_api_key:
            store_api_key("openai", setup_request.openai_api_key, tenant.id, db)
            api_keys_stored.append("openai")
            logger.info(f"Setup wizard: Stored OpenAI API key for tenant {tenant.id}")

        if setup_request.anthropic_api_key:
            store_api_key("anthropic", setup_request.anthropic_api_key, tenant.id, db)
            api_keys_stored.append("anthropic")
            logger.info(f"Setup wizard: Stored Anthropic API key for tenant {tenant.id}")

        # Step 4: Create default agents if requested
        agents_created = []
        if setup_request.create_default_agents:
            from services.agent_seeding import seed_default_agents

            # Determine model provider based on available API keys
            if "gemini" in api_keys_stored:
                model_provider = "gemini"
                model_name = "gemini-2.5-flash"
            elif "openai" in api_keys_stored:
                model_provider = "openai"
                model_name = "gpt-4o-mini"
            elif "anthropic" in api_keys_stored:
                model_provider = "anthropic"
                model_name = "claude-3-5-haiku-20241022"
            else:
                # Fallback to gemini (will fail later if no key, but allows user to add later)
                model_provider = "gemini"
                model_name = "gemini-2.5-flash"

            agents = seed_default_agents(
                tenant_id=tenant.id,
                user_id=tenant_owner.id,
                db=db,
                model_provider=model_provider,
                model_name=model_name
            )
            agents_created = [agent["name"] for agent in agents]
            logger.info(f"Setup wizard: Created {len(agents_created)} default agents")

        # Step 5: Seed default sandboxed tools
        tools_created = []
        try:
            from services.sandboxed_tool_seeding import seed_sandboxed_tools

            tools = seed_sandboxed_tools(
                tenant_id=tenant.id,
                db=db
            )
            tools_created = [tool["name"] for tool in tools]
            logger.info(f"Setup wizard: Created {len(tools_created)} default sandboxed tools")
        except Exception as e:
            # Don't fail the whole setup if tools seeding fails
            logger.warning(f"Setup wizard: Failed to seed sandboxed tools: {e}")

        # Get tenant admin permissions for frontend
        tenant_admin_permissions = auth_service.get_user_permissions(tenant_owner.id)

        return {
            "success": True,
            "tenant_id": tenant.id,
            "tenant_admin_user_id": tenant_owner.id,
            "global_admin_user_id": global_admin.id,
            "tenant_name": tenant.name,
            "access_token": tenant_owner_token,
            "user": {
                "id": tenant_owner.id,
                "email": tenant_owner.email,
                "full_name": tenant_owner.full_name,
                "tenant_id": tenant_owner.tenant_id,
                "is_global_admin": tenant_owner.is_global_admin,
                "permissions": tenant_admin_permissions,
            },
            "api_keys_stored": api_keys_stored,
            "agents_created": agents_created,
            "tools_created": tools_created,
            "message": f"Setup complete! Tenant '{tenant.name}' created with {len(agents_created)} agents and {len(tools_created)} sandboxed tools."
        }

    except Exception as e:
        logger.error(f"Setup wizard failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Setup failed. Check server logs for details."
        )


@router.post("/password-reset/request", response_model=MessageResponse)
@limiter.limit("3/hour")  # MED-004 FIX: Prevent email enumeration/flooding
async def request_password_reset(request: Request, reset_request: PasswordResetRequest, db: Session = Depends(get_db)):
    """
    Request password reset endpoint

    Sends password reset email to user. Always returns success for security.
    Rate limited to 3 requests per hour per IP.
    """
    auth_service = AuthService(db)

    # Generate reset token
    token = auth_service.request_password_reset(reset_request.email)

    if token:
        masked_email = reset_request.email[:3] + "***" + reset_request.email[reset_request.email.index("@"):] if "@" in reset_request.email else "***"
        logger.debug(f"DEV: Password reset token for {masked_email}: {token}")

    # BUG-131 FIX: Always return uniform message — never reveal whether the email exists
    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post("/password-reset/confirm", response_model=MessageResponse)
@limiter.limit("5/minute")  # MED-004 FIX: Prevent token brute-force
async def confirm_password_reset(request: Request, confirm_request: PasswordResetConfirm, db: Session = Depends(get_db)):
    """
    Confirm password reset endpoint

    Resets user password using reset token.
    Rate limited to 5 requests per minute per IP.
    """
    auth_service = AuthService(db)

    try:
        auth_service.reset_password(confirm_request.token, confirm_request.new_password)

        # Resolve user from token for audit logging
        from auth_utils import hash_token
        from models_rbac import PasswordResetToken
        reset_record = db.query(PasswordResetToken).filter(
            PasswordResetToken.token == hash_token(confirm_request.token)
        ).first()
        if reset_record:
            reset_user = db.query(User).filter(User.id == reset_record.user_id).first()
            if reset_user and reset_user.tenant_id:
                log_tenant_event(db, reset_user.tenant_id, reset_user.id, TenantAuditActions.AUTH_PASSWORD_RESET, "user", str(reset_user.id), {"email": reset_user.email}, request)

        return MessageResponse(
            message="Password has been reset successfully. You can now log in with your new password."
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """
    Get current user information

    Returns details about the currently authenticated user.
    """
    auth_service = AuthService(db)
    permissions = auth_service.get_user_permissions(current_user.id)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "tenant_id": current_user.tenant_id,
        "is_global_admin": current_user.is_global_admin,
        "is_active": current_user.is_active,
        "email_verified": current_user.email_verified,
        "permissions": permissions,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
    }


class ProfileUpdateRequest(BaseModel):
    full_name: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.put("/me")
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Update current user's profile (full_name)."""
    current_user.full_name = payload.full_name
    db.commit()
    db.refresh(current_user)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "message": "Profile updated successfully",
    }


@router.post("/change-password")
async def change_password(
    request: Request,
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Change the current user's password."""
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change not available for SSO-only accounts",
        )

    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters",
        )

    current_user.password_hash = hash_password(payload.new_password)
    # BUG-134 FIX: Track password change time to invalidate existing JWTs
    current_user.password_changed_at = datetime.utcnow()
    db.commit()
    if current_user.tenant_id:
        log_tenant_event(db, current_user.tenant_id, current_user.id, TenantAuditActions.AUTH_PASSWORD_CHANGE, "user", str(current_user.id), {"email": current_user.email}, request)
    return MessageResponse(message="Password changed successfully")


@router.post("/logout")
async def logout(request: Request, current_user: User = Depends(get_current_user_required), db: Session = Depends(get_db)):
    """
    Logout endpoint

    In JWT implementation, logout is handled client-side by deleting the token.
    This endpoint exists for compatibility and can be extended for token blacklisting.
    """
    if current_user.tenant_id:
        log_tenant_event(db, current_user.tenant_id, current_user.id, TenantAuditActions.AUTH_LOGOUT, "user", str(current_user.id), {"email": current_user.email}, request)
    # SEC-005: Clear the httpOnly session cookie
    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(key="tsushin_session", path="/")
    return response


# Invitation Endpoints

class InvitationAcceptRequest(BaseModel):
    password: str
    full_name: str


class InvitationInfoResponse(BaseModel):
    email: str
    tenant_name: str
    role: str
    role_display_name: str
    inviter_name: str
    expires_at: str
    is_valid: bool


@router.get("/invitation/{token}", response_model=InvitationInfoResponse)
async def get_invitation_info(token: str, db: Session = Depends(get_db)):
    """
    Get invitation details by token.

    Returns information about the invitation for display on the accept page.
    Does not require authentication.
    """
    # BUG-071 FIX: Hash token for lookup (stored as SHA-256)
    invitation = db.query(UserInvitation).filter(
        UserInvitation.invitation_token == hash_token(token)
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    # Check if already accepted
    if invitation.accepted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted"
        )

    # Check if expired
    is_valid = invitation.expires_at > datetime.utcnow()

    # Get related data
    tenant = db.query(Tenant).filter(Tenant.id == invitation.tenant_id).first()
    role = db.query(Role).filter(Role.id == invitation.role_id).first()
    inviter = db.query(User).filter(User.id == invitation.invited_by).first()

    return InvitationInfoResponse(
        email=invitation.email,
        tenant_name=tenant.name if tenant else "Unknown Organization",
        role=role.name if role else "member",
        role_display_name=role.display_name if role else "Member",
        inviter_name=inviter.full_name if inviter else "Unknown",
        expires_at=invitation.expires_at.isoformat(),
        is_valid=is_valid,
    )


@router.post("/invitation/{token}/accept", response_model=AuthResponse)
async def accept_invitation(
    token: str,
    request: InvitationAcceptRequest,
    db: Session = Depends(get_db)
):
    """
    Accept invitation and create user account.

    Creates a new user account with the invitation's role and tenant.
    Returns JWT access token for immediate login.
    """
    # BUG-071 FIX: Hash token for lookup (stored as SHA-256)
    invitation = db.query(UserInvitation).filter(
        UserInvitation.invitation_token == hash_token(token)
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    # Check if already accepted
    if invitation.accepted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been accepted"
        )

    # Check if expired
    if invitation.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired"
        )

    # Check if email already registered
    existing_user = db.query(User).filter(User.email == invitation.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )

    # Validate password
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters"
        )

    # Create user
    user = User(
        tenant_id=invitation.tenant_id,
        email=invitation.email,
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        is_global_admin=False,
        is_active=True,
        email_verified=True,  # Accepted via invitation
    )
    db.add(user)
    db.flush()

    # Assign role
    user_role = UserRole(
        user_id=user.id,
        role_id=invitation.role_id,
        tenant_id=invitation.tenant_id,
        assigned_by=invitation.invited_by,
    )
    db.add(user_role)

    # Mark invitation as accepted
    invitation.accepted_at = datetime.utcnow()

    db.commit()
    db.refresh(user)

    # Get role name for token
    role = db.query(Role).filter(Role.id == invitation.role_id).first()
    role_name = role.name if role else "member"

    # Generate access token
    pwd_ts = None
    if user.password_changed_at:
        pwd_ts = int(user.password_changed_at.timestamp())
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "tenant_id": user.tenant_id,
        "is_global_admin": user.is_global_admin,
        "role": role_name,
        "pwd_ts": pwd_ts,
    }
    access_token = create_access_token(token_data)

    # Get user permissions for frontend
    auth_service = AuthService(db)
    permissions = auth_service.get_user_permissions(user.id)

    # SEC-005: Set httpOnly session cookie on invitation accept
    response = JSONResponse(content={
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "tenant_id": user.tenant_id,
            "is_global_admin": user.is_global_admin,
            "permissions": permissions,
        },
    })
    _set_session_cookie(response, access_token)
    return response


# ========================================================================
# Google SSO Endpoints
# ========================================================================

class GoogleAuthURLResponse(BaseModel):
    auth_url: str


class GoogleSSOStatusResponse(BaseModel):
    enabled: bool
    platform_configured: bool
    tenant_configured: bool
    tenant_slug: Optional[str] = None


@router.get("/google/status", response_model=GoogleSSOStatusResponse)
async def get_google_sso_status(
    tenant_slug: Optional[str] = Query(None, description="Tenant slug to check SSO status for"),
    db: Session = Depends(get_db)
):
    """
    Check if Google SSO is available.

    Returns status of Google SSO configuration for both platform and tenant.
    When no tenant_slug is provided, checks if ANY tenant has SSO configured.
    """
    platform_configured = bool(settings.GOOGLE_SSO_CLIENT_ID and settings.GOOGLE_SSO_CLIENT_SECRET)
    tenant_configured = False

    if tenant_slug:
        # Check specific tenant
        tenant = db.query(Tenant).filter(
            Tenant.slug == tenant_slug,
            Tenant.deleted_at.is_(None)
        ).first()

        if tenant:
            # Check if tenant has SSO enabled in TenantSSOConfig
            config = db.query(TenantSSOConfig).filter(
                TenantSSOConfig.tenant_id == tenant.id
            ).first()

            if config and config.google_sso_enabled:
                tenant_configured = True

            # Also check if tenant has Google OAuth credentials configured
            if not tenant_configured:
                credentials = db.query(GoogleOAuthCredentials).filter(
                    GoogleOAuthCredentials.tenant_id == tenant.id
                ).first()
                if credentials and credentials.client_id:
                    # Tenant has credentials, check if SSO is enabled
                    if config and config.google_sso_enabled:
                        tenant_configured = True
    else:
        # No tenant specified - check if ANY tenant has SSO enabled with credentials
        # This allows showing the Google SSO button on the login page
        any_tenant_with_sso = db.query(TenantSSOConfig).filter(
            TenantSSOConfig.google_sso_enabled == True
        ).first()

        if any_tenant_with_sso:
            # Check if that tenant also has Google OAuth credentials
            credentials = db.query(GoogleOAuthCredentials).filter(
                GoogleOAuthCredentials.tenant_id == any_tenant_with_sso.tenant_id
            ).first()
            if credentials and credentials.client_id:
                tenant_configured = True

    return GoogleSSOStatusResponse(
        enabled=platform_configured or tenant_configured,
        platform_configured=platform_configured,
        tenant_configured=tenant_configured,
        tenant_slug=tenant_slug,
    )


@router.get("/google/authorize", response_model=GoogleAuthURLResponse)
async def get_google_auth_url(
    tenant_slug: Optional[str] = Query(None, description="Tenant slug for tenant-specific auth"),
    redirect_after: str = Query("/", description="URL to redirect to after authentication"),
    invitation_token: Optional[str] = Query(None, description="Invitation token if accepting an invite"),
    db: Session = Depends(get_db)
):
    """
    Get Google OAuth authorization URL.

    Start the OAuth flow by redirecting users to this URL.
    """
    # BUG-137 + BUG-141 FIX: Whitelist approach — only allow relative paths starting with /
    # This blocks javascript:, data:, http://, https://, //, and any other scheme
    if redirect_after:
        stripped = redirect_after.strip()
        if not stripped.startswith('/') or stripped.startswith('//'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="redirect_after must be a relative path starting with /"
            )

    try:
        sso_service = get_google_sso_service(db, get_encryption_key(db))
        auth_url = sso_service.generate_authorization_url(
            tenant_slug=tenant_slug,
            redirect_after=redirect_after,
            invitation_token=invitation_token,
        )
        return GoogleAuthURLResponse(auth_url=auth_url)
    except GoogleSSOError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/google/callback")
async def google_sso_callback(
    code: Optional[str] = Query(None, description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State token"),
    error: Optional[str] = Query(None, description="Error from Google"),
    error_description: Optional[str] = Query(None, description="Error description from Google"),
    db: Session = Depends(get_db)
):
    """
    Google OAuth callback endpoint.

    Handles the redirect from Google after user authentication.
    Exchanges code for tokens and creates/updates user.

    MED-009 Security Fix: Redirects to frontend with one-time code instead of JWT.
    The frontend exchanges the code for JWT via /api/auth/sso-exchange endpoint.
    This prevents JWT exposure in browser history, server logs, and referrer headers.
    """
    # Handle errors from Google
    if error:
        logger.error(f"Google OAuth error: {error} - {error_description}")
        error_msg = error_description or error
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/login?error={error_msg}",
            status_code=302
        )

    if not code or not state:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/login?error=Missing+authorization+code",
            status_code=302
        )

    try:
        sso_service = get_google_sso_service(db, get_encryption_key(db))
        user, jwt_token, redirect_after = await sso_service.authenticate(code, state)

        # MED-009 Security Fix: Generate one-time code instead of putting JWT in URL
        # Code expires in 60 seconds and can only be used once
        callback_code = _generate_sso_callback_code(db, jwt_token, redirect_after)

        # Redirect to frontend with code (not JWT)
        # Frontend will call /api/auth/sso-exchange to get the actual JWT
        redirect_url = f"{settings.FRONTEND_URL}/auth/sso-callback?code={callback_code}"

        logger.info(f"Google SSO successful for user: {user.email}")
        return RedirectResponse(url=redirect_url, status_code=302)

    except GoogleSSOError as e:
        logger.error(f"Google SSO authentication failed: {e}")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/login?error={str(e)}",
            status_code=302
        )
    except Exception as e:
        logger.exception(f"Unexpected error during Google SSO: {e}")
        import urllib.parse
        error_detail = urllib.parse.quote(str(e) or "Authentication failed")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/auth/login?error={error_detail}",
            status_code=302
        )


@router.post("/sso-exchange", response_model=SSOCodeExchangeResponse)
@limiter.limit("10/minute")  # Rate limit to prevent code guessing attacks
async def exchange_sso_code(
    request: Request,
    exchange_request: SSOCodeExchangeRequest,
    db: Session = Depends(get_db)
):
    """
    Exchange one-time SSO callback code for JWT token.

    MED-009 Security Fix: This endpoint receives the one-time code from
    the SSO callback URL and returns the actual JWT token. The code is
    invalidated after use and expires after 60 seconds.

    This prevents JWT tokens from appearing in:
    - Browser history
    - Server access logs
    - Referrer headers
    """
    try:
        jwt_token, redirect_after = _exchange_sso_callback_code(db, exchange_request.code)

        # SEC-005: Set httpOnly session cookie on SSO code exchange
        response = JSONResponse(content={
            "access_token": jwt_token,
            "token_type": "bearer",
            "redirect_after": redirect_after,
        })
        _set_session_cookie(response, jwt_token)
        return response

    except ValueError as e:
        logger.warning(f"SSO code exchange failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Unexpected error during SSO code exchange: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )


@router.post("/google/link")
async def link_google_account(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    Start the process to link Google account to existing user.

    Returns authorization URL for linking.
    """
    if current_user.google_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google account is already linked"
        )

    try:
        sso_service = get_google_sso_service(db)

        # Get tenant slug if user has a tenant
        tenant_slug = None
        if current_user.tenant_id:
            tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
            if tenant:
                tenant_slug = tenant.slug

        auth_url = sso_service.generate_authorization_url(
            tenant_slug=tenant_slug,
            redirect_after="/settings/security",
        )
        return GoogleAuthURLResponse(auth_url=auth_url)
    except GoogleSSOError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/google/unlink")
async def unlink_google_account(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    Unlink Google account from user.

    User must have a password set to unlink Google.
    """
    if not current_user.google_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Google account is linked"
        )

    # Ensure user has a password set
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set a password before unlinking Google. Use password reset to set one."
        )

    # Unlink
    current_user.google_id = None
    current_user.auth_provider = "local"
    db.commit()

    return MessageResponse(message="Google account unlinked successfully")
