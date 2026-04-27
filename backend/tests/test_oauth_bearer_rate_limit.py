"""
BUG-708 regression: OAuth2 Bearer tokens must honour the issuing client's
``rate_limit_rpm`` instead of a hard-coded 120.

Tested at the middleware layer by:
  • Building a real api_client row with rate_limit_rpm=10 in an in-memory DB.
  • Issuing a real JWT via the production token-creation helper.
  • Pointing the middleware's ``get_global_engine`` at the in-memory DB.
  • Driving a TestClient burst of Bearer requests through a stub /api/v1/* route.

If the fix is in place, the 11th request returns 429.
If the fix is missing (hard-coded 120), all 11 succeed.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_utils import create_access_token, hash_password  # noqa: E402
from middleware import rate_limiter as rl  # noqa: E402
from middleware.rate_limiter import (  # noqa: E402
    ApiV1RateLimitMiddleware,
    SlidingWindowRateLimiter,
)
from models import ApiClient, ApiRequestLog, Base  # noqa: E402
# Importing models_rbac registers Tenant and User tables on Base.metadata so
# that FKs from api_client (tenant_id, created_by) resolve during create_all.
from models_rbac import Tenant as _RBACTenant, User as _RBACUser  # noqa: E402, F401


@pytest.fixture
def isolated_engine(monkeypatch):
    """Create an isolated in-memory engine and pin it as the global engine.

    Uses StaticPool so that all sessions opened anywhere (including the
    middleware's lazy-imported get_global_engine() session) share the SAME
    underlying SQLite connection — without this, each new session would see
    a separate empty :memory: database.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            _RBACTenant.__table__,
            _RBACUser.__table__,
            ApiClient.__table__,
            ApiRequestLog.__table__,
        ],
    )

    def _engine_getter():
        return engine

    # Patch both the lazy-imported db.get_global_engine and the cached caches.
    import db as db_module

    monkeypatch.setattr(db_module, "get_global_engine", _engine_getter)
    rl._client_rpm_cache.clear()
    rl._bearer_rpm_cache.clear()
    rl.api_rate_limiter._windows.clear()
    return engine


@pytest.fixture
def low_rpm_client(isolated_engine):
    """Seed an active api_client with rate_limit_rpm=10 and return its JWT."""
    SessionLocal = sessionmaker(bind=isolated_engine)
    session = SessionLocal()
    try:
        client = ApiClient(
            tenant_id="tenant-rl",
            client_id="tsn_ci_lowrpm_test",
            client_secret_hash=hash_password("tsn_cs_dummy_secret_value_for_test_only"),
            client_secret_prefix="tsn_cs_dumm",
            name="Low-RPM Test Client",
            description="BUG-708 regression",
            role="api_owner",
            rate_limit_rpm=10,
            is_active=True,
        )
        session.add(client)
        session.commit()
        session.refresh(client)
        client_id_str = client.client_id

        # Issue a real JWT exactly like ApiClientService.generate_token does.
        token = create_access_token(
            data={
                "sub": f"api_client:{client.id}",
                "type": "api_client",
                "tenant_id": client.tenant_id,
                "client_id": client_id_str,
                "scopes": [],
                "secret_rotated_at": None,
            },
            expires_delta=timedelta(hours=1),
        )
        return token, client_id_str
    finally:
        session.close()


def _build_app() -> FastAPI:
    """Minimal app with the middleware and a stub /api/v1/* route."""
    app = FastAPI()
    app.add_middleware(ApiV1RateLimitMiddleware)

    @app.get("/api/v1/ping")
    def ping():
        return {"ok": True}

    return app


def test_bearer_burst_honors_per_client_rpm(low_rpm_client):
    """
    BUG-708: a 10-RPM client's 11th Bearer request must be 429, NOT 200.
    """
    token, _ = low_rpm_client
    app = _build_app()
    client = TestClient(app)

    headers = {"Authorization": f"Bearer {token}"}
    statuses = []
    for _ in range(11):
        resp = client.get("/api/v1/ping", headers=headers)
        statuses.append(resp.status_code)

    # First 10 must succeed, 11th must be throttled.
    assert statuses.count(200) == 10, f"Expected 10×200, got: {statuses}"
    assert statuses[-1] == 429, f"Expected 11th to be 429, got: {statuses}"

    # 429 carries Retry-After + per-bucket headers.
    last_resp = client.get("/api/v1/ping", headers=headers)
    assert last_resp.status_code == 429
    assert last_resp.headers.get("Retry-After") == "60"
    assert last_resp.headers.get("X-RateLimit-Limit") == "10"
