"""
BUG-719 regression: 429 events must (a) emit a structured log line and
(b) persist a row to api_request_log when an api_client is identifiable.

We trigger the limit with an X-API-Key burst against an in-memory api_client
configured at rate_limit_rpm=2, then assert both side-effects.
"""

from __future__ import annotations

import json
import logging
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth_utils import hash_password  # noqa: E402
from middleware import rate_limiter as rl  # noqa: E402
from middleware.rate_limiter import ApiV1RateLimitMiddleware  # noqa: E402
from models import ApiClient, ApiRequestLog, Base  # noqa: E402


@pytest.fixture
def isolated_engine(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[ApiClient.__table__, ApiRequestLog.__table__],
    )

    import db as db_module

    monkeypatch.setattr(db_module, "get_global_engine", lambda: engine)
    rl._client_rpm_cache.clear()
    rl._bearer_rpm_cache.clear()
    rl.api_rate_limiter._windows.clear()
    return engine


@pytest.fixture
def low_rpm_apikey_client(isolated_engine):
    """Seed an api_client whose raw secret IS the X-API-Key (direct-mode)."""
    SessionLocal = sessionmaker(bind=isolated_engine)
    session = SessionLocal()
    try:
        # The middleware looks up by client_secret_prefix == api_key[:12].
        raw_key = "tsn_cs_7lbug719testxxxxxxxxxxxxxxxxxxxxxxxx"
        client = ApiClient(
            tenant_id="tenant-rl",
            client_id="tsn_ci_bug719_test",
            client_secret_hash=hash_password(raw_key),
            client_secret_prefix=raw_key[:12],
            name="BUG-719 Client",
            description="429-logged regression",
            role="api_owner",
            rate_limit_rpm=2,
            is_active=True,
        )
        session.add(client)
        session.commit()
        session.refresh(client)
        return raw_key, client.id
    finally:
        session.close()


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ApiV1RateLimitMiddleware)

    @app.get("/api/v1/ping")
    def ping():
        return {"ok": True}

    return app


def test_429_emits_structured_log_and_persists_api_request_log(
    isolated_engine, low_rpm_apikey_client, caplog, monkeypatch
):
    """
    BUG-719: when the limiter triggers, we must see a JSON-formatted
    `rate_limit_exceeded` log line AND an api_request_log row with
    status_code=429.

    NOTE: the X-API-Key middleware path doesn't itself surface
    api_client_id (the cache only stores RPM by prefix). For X-API-Key the
    api_request_log persistence path requires the api_client_id which is
    only present on the Bearer path. We therefore drive the test via the
    Bearer flow which DOES carry api_client_id.
    """
    raw_key, client_internal_id = low_rpm_apikey_client

    # Build a Bearer token for this client so the middleware identifies it
    # by api_client.id (BUG-708 path) — this is the path that records the
    # api_client_id and therefore writes to api_request_log on 429.
    from auth_utils import create_access_token
    from datetime import timedelta

    token = create_access_token(
        data={
            "sub": f"api_client:{client_internal_id}",
            "type": "api_client",
            "tenant_id": "tenant-rl",
            "client_id": "tsn_ci_bug719_test",
            "scopes": [],
            "secret_rotated_at": None,
        },
        expires_delta=timedelta(hours=1),
    )

    app = _build_app()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}

    caplog.set_level(logging.WARNING, logger=rl.logger.name)

    # 2 RPM: 2 succeed, 3rd is 429.
    statuses = [client.get("/api/v1/ping", headers=headers).status_code for _ in range(3)]
    assert statuses == [200, 200, 429], f"Unexpected status sequence: {statuses}"

    # Side-effect 1: structured log line emitted.
    matching = [r for r in caplog.records if "rate_limit_exceeded" in r.getMessage()]
    assert matching, "Expected a rate_limit_exceeded log line on 429"
    parsed = None
    for rec in matching:
        try:
            parsed = json.loads(rec.getMessage())
            break
        except (ValueError, TypeError):
            continue
    assert parsed is not None, "rate_limit_exceeded log line must be JSON-structured"
    assert parsed.get("event") == "rate_limit_exceeded"
    assert parsed.get("rate_limit") == 2
    assert parsed.get("api_client_id") == client_internal_id
    assert parsed.get("path") == "/api/v1/ping"
    assert parsed.get("retry_after") == 60

    # Side-effect 2: api_request_log row persisted with status_code=429.
    SessionLocal = sessionmaker(bind=isolated_engine)
    session = SessionLocal()
    try:
        rows = (
            session.query(ApiRequestLog)
            .filter(ApiRequestLog.status_code == 429)
            .all()
        )
        assert len(rows) >= 1, "Expected at least one api_request_log row at status=429"
        row = rows[0]
        assert row.api_client_id == client_internal_id
        assert row.path == "/api/v1/ping"
        assert row.method == "GET"
    finally:
        session.close()
