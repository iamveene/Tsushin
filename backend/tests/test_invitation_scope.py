"""
Tests for invitation scope, auth_provider, Global SSO config, and related
routes introduced by the global-admin invitation/Google-SSO architecture.

Covers:
  - Raw-token round-trip bug fix in routes_team.invitation_to_response
  - Tenant-scoped invite auth_provider validation + accept-flow blocking
  - Global admin invitations (POST/GET/DELETE /api/admin/invitations)
  - Google SSO accept email-match enforcement
  - Global SSO config singleton CRUD (/api/admin/sso-config)
  - Shape CHECK constraints on user_invitation

These tests run against the live PostgreSQL container (the same one used
by the running backend). Each test cleans up any user_invitation rows it
creates via a unique test email suffix so tests stay isolated.
"""

import os
import sys
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ---------------------------------------------------------------------------
# Lazy imports — defer until after sys.path is set so the tests work both
# inside the backend container (where /app is already on PYTHONPATH) and
# from a host-side pytest invocation.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _module_client():
    """Module-scoped TestClient — paid once for the FastAPI lifespan."""
    from fastapi.testclient import TestClient
    from app import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client(_module_client):
    """Per-test client view that clears cookies so prior accept-invite calls
    (which set ``tsushin_session`` httpOnly cookie) don't leak into later
    tests' Authorization-Bearer requests. The auth dependency checks the
    cookie *before* the bearer header, so a stale session cookie would
    resolve to a soft-deleted test user and return ``401 User not found``.
    """
    _module_client.cookies.clear()
    return _module_client


@pytest.fixture(scope="module")
def db_session(_module_client):
    """Direct DB session (bypasses FastAPI) for cleanup + constraint tests.

    Depends on ``_module_client`` so the FastAPI lifespan (which calls
    ``set_global_engine``) has fired before we try to grab a session.
    """
    from db import get_session_factory

    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        try:
            session.rollback()
        except Exception:
            pass
        session.close()


TEST_EMAIL_DOMAIN = "invitescope.example.com"


@pytest.fixture(scope="module", autouse=True)
def purge_orphaned_test_data(db_session):
    """Clean up orphaned invitations/users from prior aborted runs.

    The per-test ``cleanup_emails`` fixture handles the happy path, but a
    crash inside the test (or a failed assertion before cleanup runs) can
    leave stale invitations around. These pile up against the tenant's
    ``max_users`` limit and cause cascading failures on the next run, so we
    wipe anything matching our distinctive test domain at module load.
    """
    from models_rbac import Tenant, User, UserInvitation, UserRole

    try:
        db_session.query(UserInvitation).filter(
            UserInvitation.email.like(f"%@{TEST_EMAIL_DOMAIN}")
        ).delete(synchronize_session=False)

        test_user_ids = [
            uid for (uid,) in db_session.query(User.id)
            .filter(User.email.like(f"%@{TEST_EMAIL_DOMAIN}"))
            .all()
        ]
        if test_user_ids:
            db_session.query(UserRole).filter(UserRole.user_id.in_(test_user_ids)).delete(
                synchronize_session=False
            )
            db_session.query(User).filter(User.id.in_(test_user_ids)).delete(
                synchronize_session=False
            )

        # Ensure max_users is generous enough for the test suite. We restore
        # the original value in teardown so we don't widen production limits.
        tenant = db_session.query(Tenant).first()
        original_max = tenant.max_users if tenant else None
        if tenant and (tenant.max_users or 0) < 50:
            tenant.max_users = 200

        db_session.commit()
    except Exception:
        db_session.rollback()
        original_max = None

    yield

    # Best-effort teardown — leave no trace.
    try:
        db_session.query(UserInvitation).filter(
            UserInvitation.email.like(f"%@{TEST_EMAIL_DOMAIN}")
        ).delete(synchronize_session=False)
        test_user_ids = [
            uid for (uid,) in db_session.query(User.id)
            .filter(User.email.like(f"%@{TEST_EMAIL_DOMAIN}"))
            .all()
        ]
        if test_user_ids:
            db_session.query(UserRole).filter(UserRole.user_id.in_(test_user_ids)).delete(
                synchronize_session=False
            )
            db_session.query(User).filter(User.id.in_(test_user_ids)).delete(
                synchronize_session=False
            )
        if original_max is not None:
            tenant = db_session.query(Tenant).first()
            if tenant is not None:
                tenant.max_users = original_max
        db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture(scope="module")
def tenant_id(db_session):
    from models_rbac import Tenant
    t = db_session.query(Tenant).first()
    assert t is not None, "Expected at least one tenant in the DB (seeded)."
    return t.id


class _UserInfo:
    """Detached snapshot of a seeded user — plain fields, no session binding."""

    __slots__ = ("id", "email", "tenant_id", "is_global_admin")

    def __init__(self, user):
        self.id = user.id
        self.email = user.email
        self.tenant_id = user.tenant_id
        self.is_global_admin = bool(user.is_global_admin)


@pytest.fixture(scope="module")
def tenant_owner(db_session, tenant_id):
    from models_rbac import User
    u = (
        db_session.query(User)
        .filter(User.tenant_id == tenant_id, User.is_global_admin == False)  # noqa: E712
        .filter(User.email == "test@example.com")
        .first()
    )
    assert u is not None, "Expected tenant-owner test@example.com to be seeded."
    return _UserInfo(u)


@pytest.fixture(scope="module")
def global_admin(db_session):
    from models_rbac import User
    u = (
        db_session.query(User)
        .filter(User.is_global_admin == True)  # noqa: E712
        .filter(User.email == "testadmin@example.com")
        .first()
    )
    assert u is not None, "Expected global admin testadmin@example.com to be seeded."
    return _UserInfo(u)


def _bearer_for(user) -> dict:
    from auth_utils import create_access_token
    token = create_access_token(
        {
            "sub": str(user.id),
            "email": user.email,
            "tenant_id": user.tenant_id,
            "is_global_admin": bool(user.is_global_admin),
        }
    )
    return {"Authorization": f"Bearer {token}"}


def _unique_email(prefix: str) -> str:
    # Use an example.com subdomain — EmailStr rejects reserved TLDs like
    # ``.test`` and `.local``. ``example.com`` is the canonical testing
    # domain (RFC 2606) and passes pydantic's EmailStr validator.
    return f"{prefix}-{uuid.uuid4().hex[:10]}@{TEST_EMAIL_DOMAIN}"


@pytest.fixture
def cleanup_emails(db_session):
    """Track emails used by a test and purge matching invitations/users."""
    from models_rbac import User, UserInvitation, UserRole

    used = []
    yield used

    if not used:
        return

    try:
        user_ids = [
            uid for (uid,) in db_session.query(User.id).filter(User.email.in_(used)).all()
        ]
        if user_ids:
            db_session.query(UserRole).filter(UserRole.user_id.in_(user_ids)).delete(
                synchronize_session=False
            )
            db_session.query(User).filter(User.id.in_(user_ids)).delete(
                synchronize_session=False
            )
        db_session.query(UserInvitation).filter(UserInvitation.email.in_(used)).delete(
            synchronize_session=False
        )
        db_session.commit()
    except Exception:
        db_session.rollback()


# ===========================================================================
# 1. Raw-token round-trip (bug fix #2)
# ===========================================================================

def test_copy_invite_link_uses_raw_token(client, tenant_owner, cleanup_emails):
    email = _unique_email("raw-token")
    cleanup_emails.append(email)

    resp = client.post(
        "/api/team/invite",
        headers=_bearer_for(tenant_owner),
        json={"email": email, "role": "member"},
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    link = body.get("invitation_link")
    assert link, f"Expected invitation_link, got body={body!r}"
    assert "/auth/invite/" in link, link

    raw_token = link.split("/auth/invite/")[-1]
    assert raw_token, "Could not extract raw token from link"

    # Accepting with this token must work (proves token is raw, not hashed).
    accept_resp = client.post(
        f"/api/auth/invitation/{raw_token}/accept",
        json={"password": "supersecret12", "full_name": "Invite Accept Test"},
    )
    assert accept_resp.status_code == 200, accept_resp.text
    assert "access_token" in accept_resp.json()


# ===========================================================================
# 2. Google auth_provider invites cannot accept via password flow
# ===========================================================================

def test_tenant_invite_auth_provider_google_blocks_password_accept(
    client, tenant_owner, cleanup_emails
):
    email = _unique_email("google-invite")
    cleanup_emails.append(email)

    resp = client.post(
        "/api/team/invite",
        headers=_bearer_for(tenant_owner),
        json={"email": email, "role": "member", "auth_provider": "google"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["auth_provider"] == "google"
    raw_token = body["invitation_link"].split("/auth/invite/")[-1]

    accept_resp = client.post(
        f"/api/auth/invitation/{raw_token}/accept",
        json={"password": "supersecret12", "full_name": "Should Fail"},
    )
    assert accept_resp.status_code == 400, accept_resp.text
    assert "Google SSO" in accept_resp.json()["detail"]


# ===========================================================================
# 3. auth_provider defaults to 'local' when omitted
# ===========================================================================

def test_tenant_invite_auth_provider_defaults_to_local(
    client, tenant_owner, db_session, cleanup_emails
):
    from models_rbac import UserInvitation

    email = _unique_email("default-local")
    cleanup_emails.append(email)

    resp = client.post(
        "/api/team/invite",
        headers=_bearer_for(tenant_owner),
        json={"email": email, "role": "member"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["auth_provider"] == "local"

    inv = (
        db_session.query(UserInvitation)
        .filter(UserInvitation.email == email)
        .first()
    )
    assert inv is not None
    assert inv.auth_provider == "local"


# ===========================================================================
# 4. Invalid auth_provider rejected at validation layer (422)
# ===========================================================================

def test_invalid_auth_provider_rejected(client, tenant_owner, cleanup_emails):
    email = _unique_email("bad-provider")
    cleanup_emails.append(email)

    resp = client.post(
        "/api/team/invite",
        headers=_bearer_for(tenant_owner),
        json={"email": email, "role": "member", "auth_provider": "github"},
    )
    assert resp.status_code == 422, resp.text


# ===========================================================================
# 5. Global-admin invite → global user on accept (no tenant_id, no UserRole)
# ===========================================================================

def test_global_admin_invite_creates_global_user_on_accept(
    client, global_admin, db_session, cleanup_emails
):
    from models_rbac import User, UserRole

    email = _unique_email("new-global-admin")
    cleanup_emails.append(email)

    resp = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json={
            "email": email,
            "is_global_admin": True,
            "auth_provider": "local",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["is_global_admin"] is True
    assert body["tenant_id"] in (None, "")
    raw_token = body["invitation_link"].split("/auth/invite/")[-1]

    accept_resp = client.post(
        f"/api/auth/invitation/{raw_token}/accept",
        json={"password": "supersecret12", "full_name": "Global Admin Accept"},
    )
    assert accept_resp.status_code == 200, accept_resp.text

    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None
    assert user.is_global_admin is True
    assert user.tenant_id is None
    role_rows = db_session.query(UserRole).filter(UserRole.user_id == user.id).all()
    assert role_rows == []


# ===========================================================================
# 6. Global-admin invite with tenant_id should be rejected
# ===========================================================================

def test_global_admin_invite_with_tenant_id_rejected(
    client, global_admin, tenant_id, cleanup_emails
):
    email = _unique_email("ga-with-tenant")
    cleanup_emails.append(email)

    resp = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json={
            "email": email,
            "is_global_admin": True,
            "tenant_id": tenant_id,
            "auth_provider": "local",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "tenant_id" in resp.json()["detail"] or "Global" in resp.json()["detail"]


# ===========================================================================
# 7. Tenant-scoped admin invite missing role or tenant_id → 400
# ===========================================================================

def test_tenant_scoped_global_invite_requires_role_and_tenant(
    client, global_admin, tenant_id, cleanup_emails
):
    email = _unique_email("needs-role")
    cleanup_emails.append(email)

    # Missing role
    r1 = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json={
            "email": email,
            "is_global_admin": False,
            "tenant_id": tenant_id,
        },
    )
    assert r1.status_code == 400, r1.text

    # Missing tenant_id
    r2 = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json={
            "email": _unique_email("needs-tenant"),
            "is_global_admin": False,
            "role": "member",
        },
    )
    cleanup_emails.append(_unique_email("needs-tenant"))  # best-effort placeholder
    assert r2.status_code == 400, r2.text


# ===========================================================================
# 8. Global admin invites a member into tenant X
# ===========================================================================

def test_global_admin_invite_into_tenant(
    client, global_admin, db_session, tenant_id, cleanup_emails
):
    from models_rbac import Role, User, UserRole

    email = _unique_email("ga-invites-member")
    cleanup_emails.append(email)

    resp = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json={
            "email": email,
            "tenant_id": tenant_id,
            "role": "member",
            "auth_provider": "local",
        },
    )
    assert resp.status_code == 201, resp.text
    raw_token = resp.json()["invitation_link"].split("/auth/invite/")[-1]

    accept_resp = client.post(
        f"/api/auth/invitation/{raw_token}/accept",
        json={"password": "supersecret12", "full_name": "Tenant Member Accept"},
    )
    assert accept_resp.status_code == 200, accept_resp.text

    user = db_session.query(User).filter(User.email == email).first()
    assert user is not None
    assert user.tenant_id == tenant_id
    assert user.is_global_admin is False

    ur = (
        db_session.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.tenant_id == tenant_id)
        .first()
    )
    assert ur is not None
    role = db_session.query(Role).filter(Role.id == ur.role_id).first()
    assert role is not None
    assert role.name == "member"


# ===========================================================================
# 9. Duplicate pending invite rejected (409)
# ===========================================================================

def test_duplicate_pending_invite_rejected(
    client, global_admin, tenant_id, cleanup_emails
):
    email = _unique_email("dup-pending")
    cleanup_emails.append(email)

    payload = {
        "email": email,
        "tenant_id": tenant_id,
        "role": "member",
        "auth_provider": "local",
    }
    r1 = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json=payload,
    )
    assert r1.status_code == 201, r1.text

    r2 = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json=payload,
    )
    assert r2.status_code == 409, r2.text


# ===========================================================================
# 10. Re-invite after accept is allowed (partial-unique-index WHERE accepted_at IS NULL)
# ===========================================================================

def test_reinvite_after_accept_allowed(
    client, global_admin, tenant_id, cleanup_emails
):
    email = _unique_email("reinvite-after-accept")
    cleanup_emails.append(email)

    # Invite #1
    r1 = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json={
            "email": email,
            "tenant_id": tenant_id,
            "role": "member",
            "auth_provider": "local",
        },
    )
    assert r1.status_code == 201, r1.text
    raw_token = r1.json()["invitation_link"].split("/auth/invite/")[-1]

    # Accept
    accept_resp = client.post(
        f"/api/auth/invitation/{raw_token}/accept",
        json={"password": "supersecret12", "full_name": "Reinvite User"},
    )
    assert accept_resp.status_code == 200, accept_resp.text

    # Re-invite to same tenant+email should now succeed (no pending row
    # exists). The admin route rejects if the user already exists in the
    # tenant — so we expect a 400 here with "already a member". That is
    # *different* from the partial-unique-index check. The test proves the
    # DB-level index does not block re-issue; the logical guard does.
    #
    # To isolate the index behavior, delete the user and retry — the index
    # must allow a second row because the first one has accepted_at set.
    from models_rbac import User, UserRole

    # Fetch session from fixture indirectly: reuse client's db via a fresh session
    from db import get_session_factory

    s = get_session_factory()()
    try:
        u = s.query(User).filter(User.email == email).first()
        assert u is not None
        s.query(UserRole).filter(UserRole.user_id == u.id).delete()
        s.delete(u)
        s.commit()
    finally:
        s.close()

    # Clear cookies — the accept flow set a session cookie whose user we
    # just deleted. Subsequent requests must fall back to Bearer auth.
    client.cookies.clear()

    r2 = client.post(
        "/api/admin/invitations/",
        headers=_bearer_for(global_admin),
        json={
            "email": email,
            "tenant_id": tenant_id,
            "role": "member",
            "auth_provider": "local",
        },
    )
    assert r2.status_code == 201, (
        f"Re-invite after accept should succeed (partial-unique-index only "
        f"blocks pending rows). Got: {r2.status_code} {r2.text}"
    )


# ===========================================================================
# 11. CHECK constraint: is_global_admin=True with tenant_id set → IntegrityError
# ===========================================================================

def test_check_constraint_global_admin_shape(global_admin, tenant_id):
    from sqlalchemy.exc import IntegrityError

    from db import get_session_factory
    from models_rbac import UserInvitation

    s = get_session_factory()()
    try:
        bad = UserInvitation(
            tenant_id=tenant_id,  # ← disallowed when is_global_admin=True
            email=_unique_email("ck-constraint"),
            role_id=1,
            invited_by=global_admin.id,
            invitation_token=f"fake-token-{uuid.uuid4().hex}",
            expires_at=datetime.utcnow(),
            is_global_admin=True,
            auth_provider="local",
        )
        s.add(bad)
        with pytest.raises(IntegrityError):
            s.flush()
    finally:
        s.rollback()
        s.close()


# ===========================================================================
# 12. Google SSO accept email mismatch (unit test on find_or_create_user)
# ===========================================================================

def test_google_sso_accept_email_mismatch(
    global_admin, tenant_id, db_session, cleanup_emails
):
    from datetime import timedelta

    from auth_google import GoogleSSOError, GoogleSSOService
    from auth_utils import generate_invitation_token, hash_token
    from models_rbac import UserInvitation

    invitee_email = _unique_email("google-mismatch-invite")
    google_email = _unique_email("google-mismatch-google")
    cleanup_emails.append(invitee_email)
    cleanup_emails.append(google_email)

    raw = generate_invitation_token()
    inv = UserInvitation(
        tenant_id=tenant_id,
        email=invitee_email,
        role_id=3,  # member
        invited_by=global_admin.id,
        invitation_token=hash_token(raw),
        expires_at=datetime.utcnow() + timedelta(days=1),
        is_global_admin=False,
        auth_provider="google",
    )
    db_session.add(inv)
    db_session.commit()
    db_session.refresh(inv)

    service = GoogleSSOService(db_session)
    # Invitation was addressed to invitee_email; Google returned a different
    # email. Google-scoped invites must reject this loudly.
    with pytest.raises(GoogleSSOError) as exc_info:
        service.find_or_create_user(
            google_id=f"gid-{uuid.uuid4().hex}",
            email=google_email,
            full_name="Different Person",
            avatar_url=None,
            tenant_id=tenant_id,
            invitation_token=raw,
        )
    assert "does not match" in str(exc_info.value).lower()


# ===========================================================================
# 13. Global SSO config singleton GET → PUT → GET
# ===========================================================================

def test_global_sso_config_singleton(client, global_admin, db_session):
    from models_rbac import GlobalSSOConfig

    r1 = client.get("/api/admin/sso-config/", headers=_bearer_for(global_admin))
    assert r1.status_code == 200, r1.text
    cfg1 = r1.json()
    assert "id" in cfg1
    original_enabled = cfg1["google_sso_enabled"]

    try:
        put = client.put(
            "/api/admin/sso-config/",
            headers=_bearer_for(global_admin),
            json={
                "google_sso_enabled": not original_enabled,
                "auto_provision_users": False,
            },
        )
        assert put.status_code == 200, put.text
        assert put.json()["google_sso_enabled"] is (not original_enabled)

        r2 = client.get("/api/admin/sso-config/", headers=_bearer_for(global_admin))
        assert r2.status_code == 200
        assert r2.json()["google_sso_enabled"] is (not original_enabled)

        # Singleton: only one row ever exists
        count = db_session.query(GlobalSSOConfig).count()
        assert count == 1
    finally:
        # Restore original state so other tests / the running app are not affected.
        client.put(
            "/api/admin/sso-config/",
            headers=_bearer_for(global_admin),
            json={"google_sso_enabled": original_enabled},
        )


# ===========================================================================
# 14. Global SSO config: regular tenant owner → 403
# ===========================================================================

def test_global_sso_config_requires_global_admin(client, tenant_owner):
    r = client.get("/api/admin/sso-config/", headers=_bearer_for(tenant_owner))
    assert r.status_code == 403, r.text
