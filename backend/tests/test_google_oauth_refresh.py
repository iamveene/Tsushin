import asyncio
from datetime import datetime, timedelta

import httpx
import pytest
from cryptography.fernet import Fernet

from hub.google.oauth_handler import GoogleOAuthHandler
from hub.security import TokenEncryption
from models import GoogleOAuthCredentials, CalendarIntegration, OAuthToken
from models_rbac import Tenant


class DummyResponse:
    status_code = 400
    text = "invalid_grant"

    def json(self):
        return {
            "error": "invalid_grant",
            "error_description": "Token has been expired or revoked."
        }


class DummyAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        return self._response


@pytest.mark.asyncio
async def test_refresh_access_token_invalid_grant_marks_unavailable(test_db, monkeypatch):
    tenant = Tenant(id="tenant_test", name="Test Tenant", slug="test-tenant")
    test_db.add(tenant)

    key = Fernet.generate_key().decode()
    token_encryption = TokenEncryption(key.encode())

    credentials = GoogleOAuthCredentials(
        tenant_id=tenant.id,
        client_id="client_id",
        client_secret_encrypted=token_encryption.encrypt("client_secret", tenant.id)
    )
    test_db.add(credentials)

    integration = CalendarIntegration(
        type="calendar",
        name="Calendar - user@example.com",
        display_name="Calendar",
        tenant_id=tenant.id,
        is_active=True,
        health_status="healthy",
        email_address="user@example.com",
        authorized_at=datetime.utcnow()
    )
    test_db.add(integration)
    test_db.flush()

    token = OAuthToken(
        integration_id=integration.id,
        access_token_encrypted=token_encryption.encrypt("access_token", integration.email_address),
        refresh_token_encrypted=token_encryption.encrypt("refresh_token", integration.email_address),
        expires_at=datetime.utcnow() - timedelta(minutes=1)
    )
    test_db.add(token)
    test_db.commit()

    dummy_client = DummyAsyncClient(DummyResponse())
    monkeypatch.setattr(httpx, "AsyncClient", lambda *args, **kwargs: dummy_client)

    handler = GoogleOAuthHandler(test_db, key, tenant.id)
    result = await handler.refresh_access_token(integration.id, integration.email_address)

    assert result is None

    updated = test_db.query(CalendarIntegration).filter(
        CalendarIntegration.id == integration.id
    ).first()
    assert updated is not None
    assert updated.is_active is False
    assert updated.health_status == "unavailable"
    assert updated.last_health_check is not None
