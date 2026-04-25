"""
API Rate Limiter — Public API v1
In-memory sliding window rate limiter for /api/v1/ endpoints.
Per-client rate limiting based on API client configuration.

BUG-057 FIX: Middleware runs before FastAPI route dependencies, so
request.state.rate_limit_rpm was never set when the middleware checked it.
Now resolves per-client rate_limit_rpm directly from the database via the
API key prefix, with an in-memory cache to avoid per-request DB lookups.

BUG-708 FIX (v0.7.0): Bearer-token requests no longer use a hard-coded
120 RPM ceiling. The middleware now decodes the JWT, resolves the issuing
``api_client.id`` and uses that client's ``rate_limit_rpm`` for bucket
selection, so OAuth2 Bearer requests honour the same per-client budget as
``X-API-Key`` requests.

BUG-718 FIX (v0.7.0): Unauthenticated requests are now throttled per-IP.
Default budget is configurable via ``TSN_UNAUTH_RPM_PER_IP`` (default 60).
``/api/v1/oauth/token`` has its own tightest bucket configurable via
``TSN_OAUTH_TOKEN_RPM_PER_IP`` (default 10).

BUG-719 FIX (v0.7.0): Whenever the limiter triggers a 429 it now emits a
structured ``rate_limit_exceeded`` log line and persists a row to
``api_request_log`` (when an api_client is identifiable) so operators can
audit rate-limit events.
"""

import json
import os
import time
import uuid
import logging
from collections import defaultdict
from threading import Lock
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Default rate limit when client cannot be resolved
DEFAULT_RATE_LIMIT_RPM = 60

# BUG-718: per-IP throttle for unauthenticated /api/v1/* requests.
# Configurable so operators can tune for forensic / red-team / staging
# environments. Defaults are conservative.
def _int_env(key: str, default: int) -> int:
    try:
        v = int(os.environ.get(key, str(default)))
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


UNAUTH_RPM_PER_IP = _int_env("TSN_UNAUTH_RPM_PER_IP", 60)
OAUTH_TOKEN_RPM_PER_IP = _int_env("TSN_OAUTH_TOKEN_RPM_PER_IP", 10)

# Cache TTL for per-client rate limits (seconds)
_CLIENT_RPM_CACHE_TTL = 300  # 5 minutes


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    @staticmethod
    def _scoped_key(key: str, budget_kind: Optional[str] = None) -> str:
        if not budget_kind:
            return key
        return f"{key}:budget:{budget_kind}"

    def allow(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
        budget_kind: Optional[str] = None,
    ) -> bool:
        """Check if a request is allowed within the rate limit."""
        key = self._scoped_key(key, budget_kind)
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Remove expired entries
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]

            if len(self._windows[key]) >= max_requests:
                return False

            self._windows[key].append(now)
            return True

    def remaining(
        self,
        key: str,
        max_requests: int,
        window_seconds: int = 60,
        budget_kind: Optional[str] = None,
    ) -> int:
        """Get remaining requests in the current window."""
        key = self._scoped_key(key, budget_kind)
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            if key in self._windows:
                self._windows[key] = [t for t in self._windows[key] if t > cutoff]
                # Evict empty keys to prevent unbounded dict growth
                if not self._windows[key]:
                    del self._windows[key]
                    return max_requests
                return max(0, max_requests - len(self._windows[key]))
            return max_requests

    def reset_time(
        self,
        key: str,
        window_seconds: int = 60,
        budget_kind: Optional[str] = None,
    ) -> int:
        """Get the UTC epoch timestamp when the oldest request in the window expires."""
        key = self._scoped_key(key, budget_kind)
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            if key in self._windows:
                active = [t for t in self._windows[key] if t > cutoff]
                if active:
                    # The oldest request expires at its timestamp + window_seconds
                    return int(min(active) + window_seconds)
            # No active requests — reset is a full window from now
            return int(now + window_seconds)


# Global rate limiter instance
api_rate_limiter = SlidingWindowRateLimiter()

# In-memory cache: api_key_prefix -> (rate_limit_rpm, cached_at)
_client_rpm_cache: dict[str, tuple[int, float]] = {}
_client_rpm_cache_lock = Lock()

# BUG-708: in-memory cache for Bearer token -> (api_client_id, rate_limit_rpm, cached_at).
# Keyed by sha256(token) to avoid storing raw tokens in process memory.
_bearer_rpm_cache: dict[str, tuple[int, int, float]] = {}
_bearer_rpm_cache_lock = Lock()


def _resolve_client_rate_limit(api_key_prefix: str) -> Optional[int]:
    """
    Look up the per-client rate_limit_rpm from the database by API key prefix.
    Uses an in-memory cache with TTL to avoid per-request DB queries.
    Returns None if the client cannot be resolved (auth layer will reject later).
    """
    now = time.time()

    # Check cache first
    with _client_rpm_cache_lock:
        cached = _client_rpm_cache.get(api_key_prefix)
        if cached and (now - cached[1]) < _CLIENT_RPM_CACHE_TTL:
            return cached[0]

    # Cache miss — query the database
    try:
        from db import get_global_engine
        from sqlalchemy.orm import Session as SaSession
        from models import ApiClient

        engine = get_global_engine()
        if not engine:
            return None

        with SaSession(engine) as db:
            client = db.query(ApiClient.rate_limit_rpm).filter(
                ApiClient.client_secret_prefix == api_key_prefix,
                ApiClient.is_active == True,
            ).first()

            if client:
                rpm = client.rate_limit_rpm or DEFAULT_RATE_LIMIT_RPM
                with _client_rpm_cache_lock:
                    _client_rpm_cache[api_key_prefix] = (rpm, now)
                return rpm

    except Exception as exc:
        logger.debug(f"Could not resolve client rate limit for prefix {api_key_prefix}: {exc}")

    return None


def _resolve_bearer_rate_limit(token: str) -> Optional[tuple[int, int]]:
    """
    BUG-708: Decode a Bearer JWT and look up the issuing api_client's rate_limit_rpm.

    Returns (api_client_internal_id, rate_limit_rpm) or None if the token cannot
    be resolved. We cache by sha256(token) so the cost is paid once per token,
    not per request. Cache entry TTL matches the regular client RPM cache.
    """
    import hashlib

    if not token:
        return None

    cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.time()

    with _bearer_rpm_cache_lock:
        cached = _bearer_rpm_cache.get(cache_key)
        if cached and (now - cached[2]) < _CLIENT_RPM_CACHE_TTL:
            return cached[0], cached[1]

    try:
        from auth_utils import decode_access_token

        payload = decode_access_token(token)
        if not payload:
            return None

        # Only api_client tokens have a rate_limit_rpm to resolve.
        if payload.get("type") != "api_client":
            return None

        client_id_str = payload.get("client_id")
        if not client_id_str:
            return None

        from db import get_global_engine
        from sqlalchemy.orm import Session as SaSession
        from models import ApiClient

        engine = get_global_engine()
        if not engine:
            return None

        with SaSession(engine) as db:
            client = db.query(ApiClient.id, ApiClient.rate_limit_rpm).filter(
                ApiClient.client_id == client_id_str,
                ApiClient.is_active == True,
            ).first()
            if not client:
                return None
            rpm = client.rate_limit_rpm or DEFAULT_RATE_LIMIT_RPM
            with _bearer_rpm_cache_lock:
                _bearer_rpm_cache[cache_key] = (client.id, rpm, now)
            return client.id, rpm

    except Exception as exc:
        logger.debug(f"Could not resolve Bearer rate limit: {exc}")
        return None


def _persist_429_to_request_log(
    *,
    api_client_id: Optional[int],
    method: str,
    path: str,
    ip_address: Optional[str],
) -> None:
    """
    BUG-719: Persist a 429 row to api_request_log for operability.
    Only persists when we can attribute the request to an api_client (FK NOT NULL).
    Failures are swallowed so a logging hiccup never escalates a 429 to a 500.
    """
    if not api_client_id:
        return
    try:
        from db import get_global_engine
        from sqlalchemy.orm import Session as SaSession
        from models import ApiRequestLog

        engine = get_global_engine()
        if not engine:
            return

        with SaSession(engine) as db:
            row = ApiRequestLog(
                api_client_id=api_client_id,
                method=method[:10],
                path=path[:500],
                status_code=429,
                response_time_ms=0,
                ip_address=ip_address,
            )
            db.add(row)
            db.commit()
    except Exception as exc:
        logger.debug(f"Could not persist 429 to api_request_log: {exc}")


def _client_ip(request: Request) -> str:
    """Best-effort client IP for unauth bucket keying."""
    if request.client and request.client.host:
        return request.client.host
    # Fallback: use the X-Forwarded-For only if ProxyHeadersMiddleware ran.
    # request.client.host is already the trusted value.
    return ""


def _build_429_response(
    *,
    rate_limit: int,
    rate_key: str,
    request_id: str,
    extra_headers: Optional[dict] = None,
) -> JSONResponse:
    remaining = api_rate_limiter.remaining(rate_key, rate_limit)
    headers = {
        "Retry-After": "60",
        "X-RateLimit-Limit": str(rate_limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(api_rate_limiter.reset_time(rate_key)),
        "X-Request-Id": request_id,
    }
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limit_exceeded",
                "message": f"Rate limit exceeded. Maximum {rate_limit} requests per minute.",
                "status": 429,
            },
            "request_id": request_id,
        },
        headers=headers,
    )


class ApiV1RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for /api/v1/ endpoints.
    Resolves the API client from headers and checks per-client limits.
    Only applies to /api/v1/ paths (not internal /api/ endpoints).

    v0.7.0 (BUG-708 / BUG-718 / BUG-719):
      • Bearer tokens now route through ``_resolve_bearer_rate_limit`` to get
        the issuing client's per-client RPM instead of a hard-coded 120 ceiling.
      • Unauthenticated requests are throttled per-IP. ``/api/v1/oauth/token``
        has its own tightest bucket.
      • 429 events are emitted as structured log lines AND persisted to
        ``api_request_log`` (when attributable to an api_client).
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Only /api/v1/* is in scope. The legacy /api/* surface is unchanged.
        if not path.startswith("/api/v1/"):
            return await call_next(request)

        # Add X-Request-Id header — used by the structured 429 log line and
        # propagated to the response for cross-system correlation.
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id

        # Identify the caller. Order: X-API-Key > Bearer JWT > unauth-by-IP.
        rate_key: Optional[str] = None
        rate_limit: int = DEFAULT_RATE_LIMIT_RPM
        api_client_id: Optional[int] = None
        bucket_kind = "client"  # 'client' | 'unauth-ip' | 'oauth-token-ip'

        # Check X-API-Key header — resolve per-client rate limit from DB
        api_key = request.headers.get("x-api-key")
        if api_key and api_key.startswith("tsn_cs_"):
            prefix = api_key[:12]
            rate_key = f"apikey:{prefix}"
            client_rpm = _resolve_client_rate_limit(prefix)
            if client_rpm is not None:
                rate_limit = client_rpm

        # Check Bearer token — BUG-708: resolve issuing client's rate_limit_rpm
        if not rate_key:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                resolved = _resolve_bearer_rate_limit(token)
                if resolved is not None:
                    api_client_id, rate_limit = resolved
                    # Bucket on api_client.id so all tokens issued for the
                    # same client share one budget — closes the loophole
                    # where rotating tokens reset the budget to 0.
                    rate_key = f"apiclient:{api_client_id}"
                else:
                    # User JWT or unresolvable token — fall back to short-prefix bucket.
                    # We still apply DEFAULT_RATE_LIMIT_RPM here; the auth layer
                    # may bump this later via request.state.rate_limit_rpm
                    # for UI sessions.
                    rate_key = f"bearer:{token[:16]}"
                    rate_limit = DEFAULT_RATE_LIMIT_RPM

        # BUG-718: unauth path → per-IP throttle. Tightest budget on /oauth/token.
        if not rate_key:
            client_ip = _client_ip(request) or "unknown"
            if path == "/api/v1/oauth/token":
                rate_key = f"unauth-oauth-ip:{client_ip}"
                rate_limit = OAUTH_TOKEN_RPM_PER_IP
                bucket_kind = "oauth-token-ip"
            else:
                rate_key = f"unauth-ip:{client_ip}"
                rate_limit = UNAUTH_RPM_PER_IP
                bucket_kind = "unauth-ip"

        # Apply rate limiting
        if not api_rate_limiter.allow(rate_key, rate_limit):
            client_ip = _client_ip(request)
            # BUG-719: structured log line so spikes are visible to operators.
            try:
                logger.warning(
                    json.dumps(
                        {
                            "event": "rate_limit_exceeded",
                            "request_id": request_id,
                            "bucket": bucket_kind,
                            "rate_key": rate_key,
                            "rate_limit": rate_limit,
                            "method": request.method,
                            "path": path,
                            "ip": client_ip or None,
                            "api_client_id": api_client_id,
                            "retry_after": 60,
                        }
                    )
                )
            except Exception:
                # Logging must never escalate to 500 from a 429.
                pass

            # BUG-719: persist to api_request_log when attributable.
            _persist_429_to_request_log(
                api_client_id=api_client_id,
                method=request.method,
                path=path,
                ip_address=client_ip or None,
            )

            return _build_429_response(
                rate_limit=rate_limit,
                rate_key=rate_key,
                request_id=request_id,
            )

        # Process request
        response = await call_next(request)

        # After auth layer runs, check if it set a more specific rate limit
        # (e.g. from JWT-based API client auth or user auth). Used to surface
        # the correct X-RateLimit-* headers on the response.
        auth_rpm = getattr(request.state, 'rate_limit_rpm', None)
        if auth_rpm is not None:
            rate_limit = auth_rpm

        # Add standard headers to all /api/v1/ responses
        response.headers["X-Request-Id"] = request_id
        response.headers["X-API-Version"] = "v1"
        if rate_key:
            remaining = api_rate_limiter.remaining(rate_key, rate_limit)
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(api_rate_limiter.reset_time(rate_key))

        return response
