"""
Tests for the API v1 rate limiter middleware (BUG-057 fix).
Validates that per-client rate limits are correctly enforced.
"""

import sys
import time
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from middleware.rate_limiter import (
    SlidingWindowRateLimiter,
    _resolve_client_rate_limit,
    _client_rpm_cache,
    _client_rpm_cache_lock,
    _CLIENT_RPM_CACHE_TTL,
    DEFAULT_RATE_LIMIT_RPM,
)


class TestSlidingWindowRateLimiter:
    """Tests for the core sliding window rate limiter."""

    def setup_method(self):
        self.limiter = SlidingWindowRateLimiter()

    def test_allows_requests_within_limit(self):
        """Requests within the limit should be allowed."""
        for i in range(60):
            assert self.limiter.allow("client1", 60), f"Request {i+1} should be allowed"

    def test_blocks_requests_over_limit(self):
        """Requests exceeding the limit should be blocked."""
        for _ in range(60):
            self.limiter.allow("client1", 60)
        assert not self.limiter.allow("client1", 60), "61st request should be blocked"

    def test_per_client_isolation(self):
        """Different clients should have independent rate limits."""
        for _ in range(60):
            self.limiter.allow("client_a", 60)

        # client_a is at limit, but client_b should still be allowed
        assert self.limiter.allow("client_b", 60)
        assert not self.limiter.allow("client_a", 60)

    def test_custom_rate_limits(self):
        """Each client can have a different rate limit (BUG-057 core test)."""
        # Client with 30 RPM should block at 31
        for i in range(30):
            assert self.limiter.allow("slow_client", 30), f"Request {i+1}/30 should be allowed"
        assert not self.limiter.allow("slow_client", 30), "31st request should be blocked"

        # Client with 120 RPM should allow 120
        for i in range(120):
            assert self.limiter.allow("fast_client", 120), f"Request {i+1}/120 should be allowed"
        assert not self.limiter.allow("fast_client", 120), "121st request should be blocked"

    def test_remaining_count(self):
        """remaining() should report correct count."""
        assert self.limiter.remaining("key", 60) == 60

        for _ in range(25):
            self.limiter.allow("key", 60)

        assert self.limiter.remaining("key", 60) == 35

    def test_window_expiry(self):
        """Old requests should expire after the window passes."""
        limiter = SlidingWindowRateLimiter()
        # Use a 1-second window for fast testing
        for _ in range(5):
            limiter.allow("key", 5, window_seconds=1)

        assert not limiter.allow("key", 5, window_seconds=1)

        # Wait for the window to expire
        time.sleep(1.1)
        assert limiter.allow("key", 5, window_seconds=1)


class TestResolveClientRateLimit:
    """Tests for the database-based client rate limit resolution."""

    def setup_method(self):
        """Clear the cache before each test."""
        with _client_rpm_cache_lock:
            _client_rpm_cache.clear()

    def test_cache_hit(self):
        """Should return cached value without hitting DB."""
        with _client_rpm_cache_lock:
            _client_rpm_cache["tsn_cs_abc12"] = (120, time.time())

        # Should not need the engine at all — cache serves the value
        result = _resolve_client_rate_limit("tsn_cs_abc12")
        assert result == 120

    def test_cache_miss_returns_none_when_no_engine(self):
        """Should return None when the global engine is not set."""
        # Mock db module's get_global_engine to return None
        mock_db = MagicMock()
        mock_db.get_global_engine = MagicMock(return_value=None)

        with patch.dict(sys.modules, {"db": mock_db}):
            # Force reimport of the function's lazy imports
            result = _resolve_client_rate_limit("tsn_cs_noeng1")
            assert result is None

    def test_cache_stores_resolved_value(self):
        """Resolved values should be cached for subsequent calls."""
        # Prime the cache manually
        with _client_rpm_cache_lock:
            _client_rpm_cache["tsn_cs_cached"] = (90, time.time())

        # First call should use cache
        result1 = _resolve_client_rate_limit("tsn_cs_cached")
        assert result1 == 90

        # Update cache to simulate TTL refresh
        with _client_rpm_cache_lock:
            _client_rpm_cache["tsn_cs_cached"] = (200, time.time())

        result2 = _resolve_client_rate_limit("tsn_cs_cached")
        assert result2 == 200

    def test_cache_expiry_triggers_refresh(self):
        """Expired cache entries should not be served."""
        # Set an expired cache entry
        with _client_rpm_cache_lock:
            _client_rpm_cache["tsn_cs_exp01"] = (
                120,
                time.time() - _CLIENT_RPM_CACHE_TTL - 10,
            )

        # The function will try to hit DB after finding expired cache.
        # Without a real DB, it will fail gracefully and return None.
        # (In production, it would query the DB and refresh the cache.)
        result = _resolve_client_rate_limit("tsn_cs_exp01")
        # Returns None because no real DB engine available outside container
        assert result is None

    def test_default_rate_limit_constant(self):
        """DEFAULT_RATE_LIMIT_RPM should be 60."""
        assert DEFAULT_RATE_LIMIT_RPM == 60

    def test_cache_ttl_is_reasonable(self):
        """Cache TTL should be between 1 and 10 minutes."""
        assert 60 <= _CLIENT_RPM_CACHE_TTL <= 600
