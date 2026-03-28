"""
API Rate Limiter — Public API v1
In-memory sliding window rate limiter for /api/v1/ endpoints.
Per-client rate limiting based on API client configuration.

BUG-057 FIX: Middleware runs before FastAPI route dependencies, so
request.state.rate_limit_rpm was never set when the middleware checked it.
Now resolves per-client rate_limit_rpm directly from the database via the
API key prefix, with an in-memory cache to avoid per-request DB lookups.
"""

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

# Cache TTL for per-client rate limits (seconds)
_CLIENT_RPM_CACHE_TTL = 300  # 5 minutes


class SlidingWindowRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def allow(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        """Check if a request is allowed within the rate limit."""
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Remove expired entries
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]

            if len(self._windows[key]) >= max_requests:
                return False

            self._windows[key].append(now)
            return True

    def remaining(self, key: str, max_requests: int, window_seconds: int = 60) -> int:
        """Get remaining requests in the current window."""
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            active = [t for t in self._windows.get(key, []) if t > cutoff]
            return max(0, max_requests - len(active))


# Global rate limiter instance
api_rate_limiter = SlidingWindowRateLimiter()

# In-memory cache: api_key_prefix -> (rate_limit_rpm, cached_at)
_client_rpm_cache: dict[str, tuple[int, float]] = {}
_client_rpm_cache_lock = Lock()


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


class ApiV1RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for /api/v1/ endpoints.
    Resolves the API client from headers and checks per-client limits.
    Only applies to /api/v1/ paths (not internal /api/ endpoints).
    """

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit /api/v1/ paths (exclude /api/v1/oauth/token which has its own limits)
        path = request.url.path
        if not path.startswith("/api/v1/") or path == "/api/v1/oauth/token":
            return await call_next(request)

        # Add X-Request-Id header
        request_id = f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = request_id

        # Try to identify the client for rate limiting
        rate_key = None
        rate_limit = DEFAULT_RATE_LIMIT_RPM

        # Check X-API-Key header — resolve per-client rate limit from DB
        api_key = request.headers.get("x-api-key")
        if api_key and api_key.startswith("tsn_cs_"):
            prefix = api_key[:12]
            rate_key = f"apikey:{prefix}"
            client_rpm = _resolve_client_rate_limit(prefix)
            if client_rpm is not None:
                rate_limit = client_rpm

        # Check Bearer token
        if not rate_key:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # Use first 16 chars of token as rate key (good enough for uniqueness)
                rate_key = f"bearer:{token[:16]}"
                # Bearer tokens from UI users get a higher default; exact limit
                # is enforced by the auth layer via request.state.rate_limit_rpm
                # after call_next. For pre-auth gating we use a generous ceiling.
                rate_limit = 120

        # Apply rate limiting if we identified a client
        if rate_key:
            if not api_rate_limiter.allow(rate_key, rate_limit):
                remaining = api_rate_limiter.remaining(rate_key, rate_limit)
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
                    headers={
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(rate_limit),
                        "X-RateLimit-Remaining": str(remaining),
                        "X-Request-Id": request_id,
                    },
                )

        # Process request
        response = await call_next(request)

        # After auth layer runs, check if it set a more specific rate limit
        # (e.g. from JWT-based API client auth or user auth)
        auth_rpm = getattr(request.state, 'rate_limit_rpm', None)
        if auth_rpm is not None:
            rate_limit = auth_rpm

        # Add standard headers to all /api/v1/ responses
        response.headers["X-Request-Id"] = request_id
        if rate_key:
            remaining = api_rate_limiter.remaining(rate_key, rate_limit)
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
