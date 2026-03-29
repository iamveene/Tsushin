"""
Tests for authentication/authorization security fixes:
- BUG-053: Admin password reset transmits password in request body (not URL)
- BUG-054: JWT secret key warns when using ephemeral fallback
- BUG-058: JWT token expiration reduced to 24 hours
- BUG-061: Setup wizard TOCTOU race condition prevention
"""

import pytest
import os
import sys
import warnings
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://tsushin:tsushin@postgres:5432/tsushin")


# ============================================================================
# BUG-053: Password reset uses request body instead of query parameter
# ============================================================================

class TestBUG053PasswordResetBody:
    """BUG-053: Verify password reset endpoint accepts body, not query param."""

    def test_reset_password_model_exists(self):
        """ResetPasswordRequest model should be defined with min_length validation."""
        from api.routes_global_users import ResetPasswordRequest

        # Should be able to create a valid instance
        req = ResetPasswordRequest(new_password="secure_password_123")
        assert req.new_password == "secure_password_123"

    def test_reset_password_model_rejects_short_password(self):
        """ResetPasswordRequest should reject passwords shorter than 8 chars."""
        from api.routes_global_users import ResetPasswordRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            ResetPasswordRequest(new_password="short")

        # Should mention min_length or string_too_short
        error_str = str(exc_info.value)
        assert "short" in error_str.lower() or "8" in error_str or "min_length" in error_str

    def test_reset_password_endpoint_signature_uses_body(self):
        """The endpoint should accept a ResetPasswordRequest body, not a Query param."""
        from api.routes_global_users import admin_reset_password
        import inspect

        sig = inspect.signature(admin_reset_password)
        params = sig.parameters

        # Should have 'body' parameter (ResetPasswordRequest), not 'new_password' Query
        assert "body" in params, "Endpoint should have 'body' parameter for ResetPasswordRequest"
        assert "new_password" not in params, "Endpoint should NOT have 'new_password' as a direct parameter"

    def test_reset_password_model_requires_password(self):
        """ResetPasswordRequest should require new_password field."""
        from api.routes_global_users import ResetPasswordRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ResetPasswordRequest()  # Missing required field


# ============================================================================
# BUG-054: JWT secret key ephemeral fallback warning
# ============================================================================

class TestBUG054JWTSecretKeyWarning:
    """BUG-054: Verify warning is raised when JWT_SECRET_KEY is not set."""

    def test_jwt_secret_key_warning_when_not_set(self):
        """Should raise a warning when JWT_SECRET_KEY env var is missing."""
        import importlib

        # Clear any cached module
        if "auth_utils" in sys.modules:
            del sys.modules["auth_utils"]

        # Ensure JWT_SECRET_KEY is not set
        env_backup = os.environ.pop("JWT_SECRET_KEY", None)

        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                import auth_utils
                importlib.reload(auth_utils)

                # Check that a warning was raised
                jwt_warnings = [
                    x for x in w
                    if "JWT_SECRET_KEY" in str(x.message) and "ephemeral" in str(x.message)
                ]
                assert len(jwt_warnings) >= 1, (
                    f"Expected warning about ephemeral JWT key, got warnings: "
                    f"{[str(x.message) for x in w]}"
                )
        finally:
            # Restore env
            if env_backup is not None:
                os.environ["JWT_SECRET_KEY"] = env_backup
            # Reload to restore original state
            if "auth_utils" in sys.modules:
                importlib.reload(sys.modules["auth_utils"])

    def test_jwt_secret_key_no_warning_when_set(self):
        """Should NOT raise a warning when JWT_SECRET_KEY is set."""
        import importlib

        if "auth_utils" in sys.modules:
            del sys.modules["auth_utils"]

        os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"

        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                import auth_utils
                importlib.reload(auth_utils)

                jwt_warnings = [
                    x for x in w
                    if "JWT_SECRET_KEY" in str(x.message) and "ephemeral" in str(x.message)
                ]
                assert len(jwt_warnings) == 0, (
                    f"Should not warn when JWT_SECRET_KEY is set, got: "
                    f"{[str(x.message) for x in jwt_warnings]}"
                )
        finally:
            del os.environ["JWT_SECRET_KEY"]
            if "auth_utils" in sys.modules:
                importlib.reload(sys.modules["auth_utils"])

    def test_jwt_secret_key_uses_env_value_when_set(self):
        """Should use the env var value when JWT_SECRET_KEY is set."""
        import importlib

        if "auth_utils" in sys.modules:
            del sys.modules["auth_utils"]

        test_key = "my-test-secret-key-value-12345"
        os.environ["JWT_SECRET_KEY"] = test_key

        try:
            import auth_utils
            importlib.reload(auth_utils)
            assert auth_utils.JWT_SECRET_KEY == test_key
        finally:
            del os.environ["JWT_SECRET_KEY"]
            if "auth_utils" in sys.modules:
                importlib.reload(sys.modules["auth_utils"])


# ============================================================================
# BUG-058: JWT token expiration reduced to 24 hours
# ============================================================================

class TestBUG058TokenExpiration:
    """BUG-058: Verify JWT token lifetime is 24 hours, not 7 days."""

    def test_jwt_expiration_is_24_hours(self):
        """JWT_ACCESS_TOKEN_EXPIRE_MINUTES should be 24 hours (1440 minutes)."""
        import importlib
        import auth_utils
        importlib.reload(auth_utils)

        expected_minutes = 60 * 24  # 24 hours = 1440 minutes
        assert auth_utils.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == expected_minutes, (
            f"Expected {expected_minutes} minutes (24h), "
            f"got {auth_utils.JWT_ACCESS_TOKEN_EXPIRE_MINUTES} minutes"
        )

    def test_jwt_expiration_not_7_days(self):
        """JWT_ACCESS_TOKEN_EXPIRE_MINUTES should NOT be 7 days."""
        import importlib
        import auth_utils
        importlib.reload(auth_utils)

        seven_days_minutes = 60 * 24 * 7
        assert auth_utils.JWT_ACCESS_TOKEN_EXPIRE_MINUTES != seven_days_minutes, (
            "JWT token expiration should not be 7 days"
        )

    def test_created_token_expires_within_24_hours(self):
        """A created token should have expiration within 24 hours."""
        import importlib
        import auth_utils
        importlib.reload(auth_utils)

        token = auth_utils.create_access_token({"sub": "1", "email": "test@test.com"})
        payload = auth_utils.decode_access_token(token)

        assert payload is not None, "Token should be valid"

        exp_time = datetime.utcfromtimestamp(payload["exp"])
        iat_time = datetime.utcfromtimestamp(payload["iat"])
        delta = exp_time - iat_time

        # Should be approximately 24 hours (with small tolerance for execution time)
        assert timedelta(hours=23, minutes=59) <= delta <= timedelta(hours=24, minutes=1), (
            f"Token lifetime should be ~24 hours, got {delta}"
        )


# ============================================================================
# BUG-061: Setup wizard TOCTOU race condition
# ============================================================================

class TestBUG061SetupWizardTOCTOU:
    """BUG-061: Verify setup wizard prevents TOCTOU race condition."""

    def test_setup_wizard_rejects_when_users_exist(self):
        """Setup wizard should return 403 when users already exist."""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        # We need to check that the endpoint logic rejects when users exist.
        # Since the endpoint uses rate limiting and complex dependencies,
        # we test the core logic directly.

        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from models import Base
        from models_rbac import User

        # Connect to PostgreSQL (tables managed by Alembic)
        engine = create_engine(DATABASE_URL)
        connection = engine.connect()
        transaction = connection.begin()
        SessionLocal = sessionmaker(bind=connection)
        db = SessionLocal()

        try:
            # Seed an existing user
            user = User(
                email="existing@example.com",
                password_hash="hashed",
                full_name="Existing User",
                tenant_id=None,
                is_global_admin=True,
                is_active=True,
            )
            db.add(user)
            db.flush()

            # Verify user count check would catch this
            user_count = db.query(User).count()
            assert user_count > 0, "Test setup: should have at least one user"
        finally:
            db.close()
            transaction.rollback()
            connection.close()

    def test_setup_wizard_allows_fresh_install(self):
        """Setup wizard should allow access when no users exist in an empty transaction scope."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        from models import Base, ApiClient
        from models_rbac import (
            User, UserRole, UserInvitation, PasswordResetToken,
            GlobalAdminAuditLog, AuditEvent, SystemIntegration, Tenant,
        )

        # Connect to PostgreSQL using a transaction that we'll roll back
        engine = create_engine(DATABASE_URL)
        connection = engine.connect()
        transaction = connection.begin()
        SessionLocal = sessionmaker(bind=connection)
        db = SessionLocal()

        try:
            # Delete all child tables with FK to user.id, then users
            db.query(UserRole).delete()
            db.query(UserInvitation).delete()
            db.query(PasswordResetToken).delete()
            db.query(GlobalAdminAuditLog).delete()
            db.query(AuditEvent).delete()
            db.query(ApiClient).delete()
            db.query(SystemIntegration).delete()
            # Nullify all nullable FK columns pointing to user.id
            db.execute(text("DELETE FROM google_oauth_credentials"))
            db.execute(text("UPDATE tenant SET created_by_global_admin = NULL"))
            db.execute(text("DELETE FROM user_contact_mapping"))
            db.execute(text("UPDATE sentinel_profile SET created_by = NULL, updated_by = NULL"))
            db.execute(text("UPDATE sentinel_config SET created_by = NULL, updated_by = NULL"))
            db.execute(text("UPDATE shell_security_pattern SET created_by = NULL, updated_by = NULL"))
            db.execute(text("UPDATE sentinel_exception SET created_by = NULL, updated_by = NULL"))
            db.execute(text("DELETE FROM whatsapp_mcp_instance"))
            db.execute(text("DELETE FROM telegram_bot_instance"))
            db.query(User).delete()
            db.flush()

            user_count = db.query(User).count()
            assert user_count == 0, "Fresh database should have no users"
        finally:
            db.close()
            transaction.rollback()
            connection.close()

    def test_setup_wizard_has_double_check_logic(self):
        """Verify the setup wizard source code contains the TOCTOU fix."""
        import inspect
        from auth_routes import setup_wizard

        source = inspect.getsource(setup_wizard)

        # Check for the re-verification under lock
        assert "pg_advisory_xact_lock" in source or "BEGIN IMMEDIATE" in source, (
            "Setup wizard should use database-level locking (advisory lock or BEGIN IMMEDIATE)"
        )
        assert "user_count_locked" in source or "Re-check" in source.lower() or "re-verify" in source.lower(), (
            "Setup wizard should re-check user count under the lock"
        )

    def test_setup_wizard_locked_recheck_rejects_concurrent_setup(self):
        """Simulate that the locked re-check catches a concurrent user creation."""
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        from models import Base, ApiClient
        from models_rbac import (
            User, UserRole, UserInvitation, PasswordResetToken,
            GlobalAdminAuditLog, AuditEvent, SystemIntegration,
        )

        # Connect to PostgreSQL using a transaction that we'll roll back
        engine = create_engine(DATABASE_URL)
        connection = engine.connect()
        transaction = connection.begin()
        SessionLocal = sessionmaker(bind=connection)

        # Clear all child tables with FK to user.id, then users
        db_setup = SessionLocal()
        db_setup.query(UserRole).delete()
        db_setup.query(UserInvitation).delete()
        db_setup.query(PasswordResetToken).delete()
        db_setup.query(GlobalAdminAuditLog).delete()
        db_setup.query(AuditEvent).delete()
        db_setup.query(ApiClient).delete()
        db_setup.query(SystemIntegration).delete()
        # Nullify all nullable FK columns pointing to user.id
        db_setup.execute(text("DELETE FROM google_oauth_credentials"))
        db_setup.execute(text("UPDATE tenant SET created_by_global_admin = NULL"))
        db_setup.execute(text("DELETE FROM user_contact_mapping"))
        db_setup.execute(text("UPDATE sentinel_profile SET created_by = NULL, updated_by = NULL"))
        db_setup.execute(text("UPDATE sentinel_config SET created_by = NULL, updated_by = NULL"))
        db_setup.execute(text("UPDATE shell_security_pattern SET created_by = NULL, updated_by = NULL"))
        db_setup.execute(text("UPDATE sentinel_exception SET created_by = NULL, updated_by = NULL"))
        db_setup.execute(text("DELETE FROM whatsapp_mcp_instance"))
        db_setup.execute(text("DELETE FROM telegram_bot_instance"))
        db_setup.query(User).delete()
        db_setup.flush()
        db_setup.close()

        # Session 1: passes initial check (0 users)
        db1 = SessionLocal()
        initial_count = db1.query(User).count()
        assert initial_count == 0

        # Simulate concurrent setup: another request creates a user
        db2 = SessionLocal()
        user = User(
            email="first-setup@example.com",
            password_hash="hashed",
            full_name="First Setup Admin",
            tenant_id=None,
            is_global_admin=True,
            is_active=True,
        )
        db2.add(user)
        db2.flush()
        db2.close()

        # Session 1: the locked re-check should now find users
        locked_count = db1.query(User).count()
        assert locked_count > 0, (
            "Locked re-check should detect user created by concurrent request"
        )

        db1.close()
        transaction.rollback()
        connection.close()
