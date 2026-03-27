"""
API Client Service — Unit Tests
Tests client creation, secret verification, token generation, rotation, and revocation.
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, ApiClient, ApiClientToken
from auth_utils import verify_password, decode_access_token
from services.api_client_service import ApiClientService, VALID_ROLES


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def service(db):
    return ApiClientService(db)


@pytest.fixture
def tenant_id():
    return "test-tenant-api"


class TestCreateClient:

    def test_create_returns_client_and_secret(self, service, tenant_id):
        client, secret = service.create_client(
            tenant_id=tenant_id, name="Test Client",
            description="For testing", role="api_agent_only",
            rate_limit_rpm=60, created_by=1,
        )
        assert client.id is not None
        assert client.client_id.startswith("tsn_ci_")
        assert secret.startswith("tsn_cs_")
        assert client.name == "Test Client"
        assert client.role == "api_agent_only"
        assert client.is_active is True

    def test_secret_is_hashed(self, service, tenant_id):
        client, secret = service.create_client(
            tenant_id=tenant_id, name="Hash Test",
            description=None, role="api_agent_only",
        )
        # Secret hash should NOT be the raw secret
        assert client.client_secret_hash != secret
        # But should verify correctly
        assert verify_password(secret, client.client_secret_hash) is True

    def test_prefix_stored(self, service, tenant_id):
        client, secret = service.create_client(
            tenant_id=tenant_id, name="Prefix Test",
            description=None, role="api_agent_only",
        )
        assert client.client_secret_prefix == secret[:12]

    def test_invalid_role_raises(self, service, tenant_id):
        with pytest.raises(ValueError, match="Invalid role"):
            service.create_client(
                tenant_id=tenant_id, name="Bad Role",
                description=None, role="invalid_role",
            )

    def test_custom_role_requires_scopes(self, service, tenant_id):
        with pytest.raises(ValueError, match="custom_scopes is required"):
            service.create_client(
                tenant_id=tenant_id, name="Custom No Scopes",
                description=None, role="custom",
            )

    def test_all_valid_roles_accepted(self, service, tenant_id):
        for i, role in enumerate(VALID_ROLES):
            if role == "custom":
                continue  # custom requires seeded permissions in DB
            client, _ = service.create_client(
                tenant_id=tenant_id, name=f"Role Test {i}",
                description=None, role=role,
            )
            assert client.role == role


class TestVerifySecret:

    def test_valid_secret(self, service, tenant_id):
        client, secret = service.create_client(
            tenant_id=tenant_id, name="Verify Test",
            description=None, role="api_agent_only",
        )
        result = service.verify_secret(client.client_id, secret)
        assert result is not None
        assert result.id == client.id

    def test_wrong_secret(self, service, tenant_id):
        client, _ = service.create_client(
            tenant_id=tenant_id, name="Wrong Secret Test",
            description=None, role="api_agent_only",
        )
        result = service.verify_secret(client.client_id, "tsn_cs_wrong_secret")
        assert result is None

    def test_nonexistent_client(self, service):
        result = service.verify_secret("tsn_ci_nonexistent", "tsn_cs_whatever")
        assert result is None

    def test_inactive_client(self, service, tenant_id):
        client, secret = service.create_client(
            tenant_id=tenant_id, name="Inactive Test",
            description=None, role="api_agent_only",
        )
        service.revoke_client(client)
        result = service.verify_secret(client.client_id, secret)
        assert result is None

    def test_expired_client(self, service, tenant_id, db):
        client, secret = service.create_client(
            tenant_id=tenant_id, name="Expired Test",
            description=None, role="api_agent_only",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        result = service.verify_secret(client.client_id, secret)
        assert result is None

    def test_updates_last_used(self, service, tenant_id):
        client, secret = service.create_client(
            tenant_id=tenant_id, name="Last Used Test",
            description=None, role="api_agent_only",
        )
        assert client.last_used_at is None
        service.verify_secret(client.client_id, secret)
        assert client.last_used_at is not None


class TestResolveByApiKey:

    def test_valid_api_key(self, service, tenant_id):
        client, secret = service.create_client(
            tenant_id=tenant_id, name="API Key Test",
            description=None, role="api_agent_only",
        )
        result = service.resolve_by_api_key(secret)
        assert result is not None
        assert result.id == client.id

    def test_invalid_api_key(self, service):
        result = service.resolve_by_api_key("tsn_cs_totally_invalid_key")
        assert result is None


class TestGenerateToken:

    def test_returns_valid_jwt(self, service, tenant_id):
        client, _ = service.create_client(
            tenant_id=tenant_id, name="Token Test",
            description=None, role="api_agent_only",
        )
        token_response = service.generate_token(client)
        assert "access_token" in token_response
        assert token_response["token_type"] == "bearer"
        assert token_response["expires_in"] == 3600

        # Decode and verify claims
        payload = decode_access_token(token_response["access_token"])
        assert payload is not None
        assert payload["type"] == "api_client"
        assert payload["tenant_id"] == tenant_id
        assert payload["client_id"] == client.client_id
        assert "agents.read" in payload["scopes"]
        assert "agents.execute" in payload["scopes"]

    def test_token_stored_in_db(self, service, tenant_id, db):
        client, _ = service.create_client(
            tenant_id=tenant_id, name="Token Store Test",
            description=None, role="api_agent_only",
        )
        service.generate_token(client)
        tokens = db.query(ApiClientToken).filter(
            ApiClientToken.api_client_id == client.id
        ).all()
        assert len(tokens) == 1
        assert tokens[0].token_hash is not None


class TestRotateSecret:

    def test_old_secret_invalid_after_rotation(self, service, tenant_id):
        client, old_secret = service.create_client(
            tenant_id=tenant_id, name="Rotate Test",
            description=None, role="api_agent_only",
        )
        new_secret = service.rotate_secret(client)
        assert new_secret != old_secret
        assert new_secret.startswith("tsn_cs_")

        # Old secret should fail
        assert service.verify_secret(client.client_id, old_secret) is None
        # New secret should work
        assert service.verify_secret(client.client_id, new_secret) is not None


class TestRevokeClient:

    def test_revoke_sets_inactive(self, service, tenant_id):
        client, _ = service.create_client(
            tenant_id=tenant_id, name="Revoke Test",
            description=None, role="api_agent_only",
        )
        assert client.is_active is True
        service.revoke_client(client)
        assert client.is_active is False


class TestResolveScopes:

    def test_api_agent_only_scopes(self, service, tenant_id):
        client, _ = service.create_client(
            tenant_id=tenant_id, name="Scope Test",
            description=None, role="api_agent_only",
        )
        scopes = service.resolve_scopes(client)
        assert "agents.read" in scopes
        assert "agents.execute" in scopes
        assert len(scopes) == 2

    def test_api_owner_scopes(self, service, tenant_id):
        client, _ = service.create_client(
            tenant_id=tenant_id, name="Owner Scope Test",
            description=None, role="api_owner",
        )
        scopes = service.resolve_scopes(client)
        assert "agents.read" in scopes
        assert "agents.write" in scopes
        assert "agents.delete" in scopes
        assert "agents.execute" in scopes
        assert "org.settings.read" in scopes

    def test_custom_scopes(self, service, tenant_id, db):
        """Custom scopes require permissions to exist in DB for validation."""
        from models_rbac import Permission
        # Seed the permissions needed
        for name in ["agents.read", "contacts.read"]:
            db.add(Permission(name=name, resource=name.split(".")[0], action=name.split(".")[1]))
        db.commit()

        client, _ = service.create_client(
            tenant_id=tenant_id, name="Custom Scope Test",
            description=None, role="custom",
            custom_scopes=["agents.read", "contacts.read"],
        )
        scopes = service.resolve_scopes(client)
        assert scopes == ["agents.read", "contacts.read"]
