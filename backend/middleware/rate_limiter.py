"""
API Rate Limiter — Public API v1
In-memory sliding window rate limiter for /api/v1/ endpoints.
Per-client rate limiting based on API client configuration.
"""

import time
import uuid
import logging
from collections import defaultdict
from threading import Lock

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


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
        rate_limit = 60  # Default RPM

        # Check X-API-Key header
        api_key = request.headers.get("x-api-key")
        if api_key and api_key.startswith("tsn_cs_"):
            rate_key = f"apikey:{api_key[:12]}"

        # Check Bearer token
        if not rate_key:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # Use first 16 chars of token as rate key (good enough for uniqueness)
                rate_key = f"bearer:{token[:16]}"

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

        # Add standard headers to all /api/v1/ responses
        response.headers["X-Request-Id"] = request_id
        if rate_key:
            remaining = api_rate_limiter.remaining(rate_key, rate_limit)
            response.headers["X-RateLimit-Limit"] = str(rate_limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response
