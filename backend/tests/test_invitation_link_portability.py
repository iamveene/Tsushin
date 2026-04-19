"""Tests for ``resolve_invitation_base_url`` — the multi-tenant + ingress-
aware helper that composes the public base URL for invitation links.

Covers:
  - Tenant override (``tenant.public_base_url``) wins when set and valid.
  - Falls back to the platform Cloudflare tunnel when tenant has no override.
  - Falls back to the incoming request's origin (honoring ``X-Forwarded-*``
    headers so the named-tunnel hostname survives the proxy chain).
  - Global-admin invites (``tenant=None``) skip the tenant override branch
    but still pick up the platform tunnel / request origin.
  - Trailing slashes are normalized.
  - Returns a safe last-resort string even when nothing is configured, so
    callers never need defensive branching around a None return.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _make_request(scheme: str, host: str, forwarded_proto: str = None, forwarded_host: str = None):
    """Build a tiny Starlette-like Request stand-in for the resolver."""
    headers = {}
    headers["host"] = host
    if forwarded_proto:
        headers["x-forwarded-proto"] = forwarded_proto
    if forwarded_host:
        headers["x-forwarded-host"] = forwarded_host
    url = SimpleNamespace(scheme=scheme, netloc=host)
    return SimpleNamespace(url=url, headers=headers)


def _make_tenant(public_base_url=None):
    return SimpleNamespace(public_base_url=public_base_url)


def test_tenant_override_wins():
    from services.public_ingress_resolver import resolve_invitation_base_url

    tenant = _make_tenant("https://customer-a.tsushin.example")
    req = _make_request("https", "localhost")
    # Even with a tunnel running, the tenant override must win for a
    # tenant-scoped invite so customer-A's link points at customer-A's URL.
    with patch("services.public_ingress_resolver._peek_tunnel_url", return_value="https://tunnel.example.com"):
        assert resolve_invitation_base_url(req, tenant) == "https://customer-a.tsushin.example"


def test_tenant_override_strips_trailing_slash():
    from services.public_ingress_resolver import resolve_invitation_base_url

    tenant = _make_tenant("https://customer-a.tsushin.example/")
    req = _make_request("https", "localhost")
    assert resolve_invitation_base_url(req, tenant) == "https://customer-a.tsushin.example"


def test_falls_back_to_tunnel_when_no_override():
    from services.public_ingress_resolver import resolve_invitation_base_url

    tenant = _make_tenant(None)
    req = _make_request("https", "localhost")
    with patch("services.public_ingress_resolver._peek_tunnel_url", return_value="https://tsushin.archsec.io"):
        assert resolve_invitation_base_url(req, tenant) == "https://tsushin.archsec.io"


def test_global_admin_invite_uses_tunnel():
    """Global-admin invites pass ``tenant=None`` — they must use the platform
    tunnel, never a random tenant's override."""
    from services.public_ingress_resolver import resolve_invitation_base_url

    req = _make_request("https", "localhost")
    with patch("services.public_ingress_resolver._peek_tunnel_url", return_value="https://tsushin.archsec.io"):
        assert resolve_invitation_base_url(req, None) == "https://tsushin.archsec.io"


def test_falls_back_to_request_origin_when_no_tunnel_or_override():
    from services.public_ingress_resolver import resolve_invitation_base_url

    tenant = _make_tenant(None)
    req = _make_request("https", "localhost")
    with patch("services.public_ingress_resolver._peek_tunnel_url", return_value=None):
        assert resolve_invitation_base_url(req, tenant) == "https://localhost"


def test_request_origin_honors_forwarded_headers():
    """When the backend sits behind the compose proxy, ``X-Forwarded-Proto``
    and ``X-Forwarded-Host`` carry the public-facing URL. The resolver must
    honor them so the link doesn't leak the internal ``backend:8081`` host.
    """
    from services.public_ingress_resolver import resolve_invitation_base_url

    tenant = _make_tenant(None)
    req = _make_request(
        scheme="http",
        host="backend:8081",
        forwarded_proto="https",
        forwarded_host="tsushin.archsec.io",
    )
    with patch("services.public_ingress_resolver._peek_tunnel_url", return_value=None):
        assert resolve_invitation_base_url(req, tenant) == "https://tsushin.archsec.io"


def test_request_origin_http_dev_mode():
    """``http://localhost:3030`` dev mode must survive verbatim (scheme+port)."""
    from services.public_ingress_resolver import resolve_invitation_base_url

    tenant = _make_tenant(None)
    req = _make_request("http", "localhost:3030")
    with patch("services.public_ingress_resolver._peek_tunnel_url", return_value=None):
        assert resolve_invitation_base_url(req, tenant) == "http://localhost:3030"


def test_invalid_tenant_override_does_not_crash():
    """An invalid override (bad scheme/shape) should fall through to the
    next source rather than poisoning the link. ``resolve_public_ingress``
    already returns ``url=None`` for invalid shapes; confirm the invitation
    helper treats that as a miss."""
    from services.public_ingress_resolver import resolve_invitation_base_url

    tenant = _make_tenant("not-a-url")
    req = _make_request("https", "localhost")
    with patch("services.public_ingress_resolver._peek_tunnel_url", return_value="https://tunnel.example"):
        # The override is invalid shape → source="override", url=None →
        # we continue to the request-origin branch (tunnel is only
        # consulted for the global-admin / no-tenant path). So the expected
        # result is the request origin, not the tunnel.
        assert resolve_invitation_base_url(req, tenant) == "https://localhost"


def test_last_resort_returns_non_none():
    """With no tenant override, no tunnel, and a request object that yields
    no origin, the helper must still return a non-empty string — callers
    build ``f"{base}/auth/invite/{token}"`` directly and a None would blow
    up with ``TypeError: unsupported operand``."""
    from services.public_ingress_resolver import resolve_invitation_base_url

    tenant = _make_tenant(None)
    # Minimal object that doesn't expose .url or .headers — defensive path.
    req = SimpleNamespace()
    with patch("services.public_ingress_resolver._peek_tunnel_url", return_value=None):
        result = resolve_invitation_base_url(req, tenant)
        assert isinstance(result, str) and result  # non-empty
        assert not result.endswith("/")
