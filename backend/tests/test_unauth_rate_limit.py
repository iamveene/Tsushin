"""
BUG-718 regression: unauthenticated /api/v1/* requests must be throttled
per-IP, with a tighter bucket on /api/v1/oauth/token.

Tested at the middleware layer using a stub /api/v1/* route that does NOT
require auth (the rate-limiter runs first regardless of route auth, so
unauth requests with no X-API-Key/Bearer header still go through it).
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from middleware import rate_limiter as rl  # noqa: E402
from middleware.rate_limiter import (  # noqa: E402
    ApiV1RateLimitMiddleware,
    OAUTH_TOKEN_RPM_PER_IP,
    UNAUTH_RPM_PER_IP,
)


@pytest.fixture(autouse=True)
def reset_buckets():
    rl.api_rate_limiter._windows.clear()
    rl._client_rpm_cache.clear()
    rl._bearer_rpm_cache.clear()


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ApiV1RateLimitMiddleware)

    @app.get("/api/v1/anywhere")
    def anywhere():
        return {"ok": True}

    @app.post("/api/v1/oauth/token")
    def fake_token():
        return {"ok": True}

    return app


def test_unauth_burst_is_eventually_throttled_with_retry_after():
    """
    BUG-718: unauthenticated burst against /api/v1/anywhere must hit 429
    after UNAUTH_RPM_PER_IP requests, and the 429 must carry a Retry-After
    header so callers can back off.
    """
    app = _build_app()
    client = TestClient(app)

    # Drive enough requests to definitely exceed the per-IP budget.
    burst = UNAUTH_RPM_PER_IP + 5
    statuses = []
    for _ in range(burst):
        resp = client.get("/api/v1/anywhere")
        statuses.append((resp.status_code, resp.headers.get("Retry-After")))

    # All requests under the limit must NOT be 429 (they may be 401/403/404
    # depending on auth; in this stub they're 200).
    success_count = sum(1 for s, _ in statuses[:UNAUTH_RPM_PER_IP] if s != 429)
    assert success_count == UNAUTH_RPM_PER_IP, f"Pre-limit requests should not 429: {statuses}"

    # At least one of the over-limit requests must be 429 with Retry-After.
    over = statuses[UNAUTH_RPM_PER_IP:]
    assert any(code == 429 for code, _ in over), f"Expected at least one 429, got: {over}"
    for code, retry_after in over:
        if code == 429:
            assert retry_after == "60", "Retry-After must be 60s on 429"


def test_oauth_token_has_tighter_per_ip_bucket():
    """
    BUG-718: /api/v1/oauth/token has its own (tighter) per-IP bucket.
    We assert that exactly OAUTH_TOKEN_RPM_PER_IP requests succeed (200) and
    the next request is 429.
    """
    assert OAUTH_TOKEN_RPM_PER_IP < UNAUTH_RPM_PER_IP, (
        "OAuth-token bucket must be tighter than the generic unauth bucket"
    )

    app = _build_app()
    client = TestClient(app)

    statuses = []
    for _ in range(OAUTH_TOKEN_RPM_PER_IP + 1):
        resp = client.post("/api/v1/oauth/token", data={"grant_type": "client_credentials"})
        statuses.append(resp.status_code)

    # First N must succeed.
    assert all(s == 200 for s in statuses[:-1]), (
        f"First {OAUTH_TOKEN_RPM_PER_IP} should succeed, got: {statuses}"
    )
    # Last (N+1th) must be 429.
    assert statuses[-1] == 429, f"Expected 429 on over-limit, got: {statuses}"
