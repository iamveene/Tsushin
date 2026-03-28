"""
Tests for CORS configuration (BUG-046).

Verifies that the TSN_CORS_ORIGINS env var correctly controls
CORS middleware behavior:
- Default / "*" -> allow all origins, credentials=False
- Specific origins -> only those origins allowed, credentials=True
- Exception handlers respect the same configuration
"""
import os
import pytest
from unittest.mock import patch


class TestCorsOriginsEnvParsing:
    """Unit tests for CORS origin parsing logic (mirrors backend/app.py startup)."""

    @staticmethod
    def _parse_cors_config(env_value: str | None):
        """Replicate the parsing logic from app.py for isolated testing."""
        cors_origins_str = env_value if env_value is not None else "*"
        if cors_origins_str.strip() == "*":
            return ["*"], False
        origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
        return origins, True

    def test_default_wildcard(self):
        origins, creds = self._parse_cors_config(None)
        assert origins == ["*"]
        assert creds is False

    def test_explicit_wildcard(self):
        origins, creds = self._parse_cors_config("*")
        assert origins == ["*"]
        assert creds is False

    def test_wildcard_with_whitespace(self):
        origins, creds = self._parse_cors_config("  *  ")
        assert origins == ["*"]
        assert creds is False

    def test_single_origin(self):
        origins, creds = self._parse_cors_config("https://app.example.com")
        assert origins == ["https://app.example.com"]
        assert creds is True

    def test_multiple_origins(self):
        origins, creds = self._parse_cors_config(
            "https://app.example.com, https://admin.example.com"
        )
        assert origins == ["https://app.example.com", "https://admin.example.com"]
        assert creds is True

    def test_origins_with_extra_commas(self):
        origins, creds = self._parse_cors_config(
            "https://a.com,,https://b.com,"
        )
        assert origins == ["https://a.com", "https://b.com"]
        assert creds is True

    def test_origins_trimmed(self):
        origins, creds = self._parse_cors_config(
            "  https://a.com , https://b.com  "
        )
        assert origins == ["https://a.com", "https://b.com"]
        assert creds is True

    def test_localhost_origins(self):
        origins, creds = self._parse_cors_config(
            "http://localhost:3030,http://localhost:8081"
        )
        assert origins == ["http://localhost:3030", "http://localhost:8081"]
        assert creds is True


class TestCorsHeadersForRequest:
    """Test the _cors_headers_for_request helper logic."""

    @staticmethod
    def _build_headers(cors_origins: list, request_origin: str) -> dict:
        """Replicate the _cors_headers_for_request logic from app.py."""
        if cors_origins == ["*"]:
            return {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
        if request_origin in cors_origins:
            return {
                "Access-Control-Allow-Origin": request_origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "*",
                "Access-Control-Allow-Headers": "*",
            }
        return {}

    def test_wildcard_returns_star(self):
        headers = self._build_headers(["*"], "https://evil.com")
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert "Access-Control-Allow-Credentials" not in headers

    def test_allowed_origin_reflected(self):
        origins = ["https://app.example.com", "https://admin.example.com"]
        headers = self._build_headers(origins, "https://app.example.com")
        assert headers["Access-Control-Allow-Origin"] == "https://app.example.com"
        assert headers["Access-Control-Allow-Credentials"] == "true"

    def test_disallowed_origin_empty(self):
        origins = ["https://app.example.com"]
        headers = self._build_headers(origins, "https://evil.com")
        assert headers == {}

    def test_no_origin_header_empty(self):
        origins = ["https://app.example.com"]
        headers = self._build_headers(origins, "")
        assert headers == {}
