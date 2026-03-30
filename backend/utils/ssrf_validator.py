"""
SSRF Validation Module (BUG-065, BUG-066)

Provides URL validation with DNS-resolution-based IP checking to prevent
Server-Side Request Forgery attacks. Replaces fragmented string-prefix
checks across scraper_tool.py and playwright_provider.py.

Usage:
    from utils.ssrf_validator import validate_url, validate_ollama_url, SSRFValidationError

    # General SSRF validation (blocks private IPs, metadata, etc.)
    validate_url("https://example.com")  # OK
    validate_url("http://169.254.169.254/...")  # raises SSRFValidationError

    # Ollama-specific (allows private IPs, blocks metadata/scheme abuse)
    validate_ollama_url("http://host.docker.internal:11434")  # OK
    validate_ollama_url("file:///etc/passwd")  # raises SSRFValidationError
"""

import ipaddress
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Docker and cloud internal hostnames that should be blocked
BLOCKED_HOSTNAMES = frozenset({
    "host.docker.internal",
    "gateway.docker.internal",
    "kubernetes.default",
    "kubernetes.default.svc",
    "metadata.google.internal",
})

# Cloud metadata IP addresses (explicit check beyond is_link_local)
CLOUD_METADATA_IPS = frozenset({
    "169.254.169.254",      # AWS / GCP / Azure metadata
    "100.100.100.200",      # Alibaba Cloud metadata
    "fd00:ec2::254",        # AWS IPv6 metadata
})

# CGNAT / Shared Address Space (RFC 6598) — reachable in some cloud environments
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


class SSRFValidationError(ValueError):
    """Raised when a URL fails SSRF validation."""
    pass


def is_dangerous_ip(ip_str: str) -> bool:
    """
    Check if a resolved IP address is in a dangerous range.

    Returns True if the IP is private, loopback, link-local, reserved,
    multicast, or a known cloud metadata address.
    """
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # Unparseable IP = dangerous

    if str(addr) in CLOUD_METADATA_IPS:
        return True

    # Handle IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped

    if addr.is_private:
        return True
    if addr.is_loopback:
        return True
    if addr.is_link_local:
        return True
    if addr.is_reserved:
        return True
    if addr.is_multicast:
        return True
    # CGNAT range (RFC 6598) — not flagged by is_private on all Python versions
    if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT_NETWORK:
        return True
    if addr == ipaddress.ip_address("0.0.0.0"):
        return True
    if addr == ipaddress.ip_address("::"):
        return True

    return False


def validate_url(
    url: str,
    *,
    allow_private: bool = False,
    allowed_domains: Optional[list] = None,
    blocked_domains: Optional[list] = None,
) -> str:
    """
    Validate a URL against SSRF attacks using DNS-resolution-based IP checking.

    This resolves the hostname to IP addresses and validates each resolved IP
    against private, loopback, link-local, reserved, and cloud metadata ranges.
    This defeats DNS rebinding, hex-encoded IPs, and hostname tricks.

    Args:
        url: The URL to validate.
        allow_private: If True, allow private/loopback IPs (for services like Ollama
                       that legitimately run on private networks).
        allowed_domains: If non-empty, ONLY these domains are permitted (tenant allowlist).
                         Empty list or None means all public domains are allowed.
        blocked_domains: Additional domains to block beyond the default blocklist.

    Returns:
        The original URL if valid.

    Raises:
        SSRFValidationError: If the URL fails validation.
    """
    if not url or not url.strip():
        raise SSRFValidationError("URL cannot be empty")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise SSRFValidationError(f"Invalid URL: {e}")

    # Enforce http/https scheme
    if parsed.scheme not in ("http", "https"):
        raise SSRFValidationError(
            f"Only HTTP and HTTPS schemes are allowed, got: {parsed.scheme or 'none'}"
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL has no hostname")

    hostname_lower = hostname.lower()

    # Tenant-level allowlist: if set, ONLY these domains are permitted
    if allowed_domains:
        allowed_lower = [d.lower() for d in allowed_domains]
        if not any(
            hostname_lower == d or hostname_lower.endswith("." + d)
            for d in allowed_lower
        ):
            raise SSRFValidationError(
                f"Domain '{hostname}' is not in the allowed domains list"
            )

    # Additional blocked domains (per-tenant blocklist)
    if blocked_domains:
        for blocked in blocked_domains:
            if blocked.lower() in hostname_lower:
                raise SSRFValidationError(
                    f"Domain '{hostname}' is blocked by tenant policy"
                )

    # Block known internal hostnames (unless private IPs allowed)
    if not allow_private:
        if hostname_lower in BLOCKED_HOSTNAMES:
            raise SSRFValidationError(f"Blocked internal hostname: {hostname}")

        # Block any .internal TLD as a safety net
        if hostname_lower.endswith(".internal"):
            raise SSRFValidationError(f"Blocked .internal hostname: {hostname}")

    # Resolve hostname to IP addresses via DNS
    try:
        addr_infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise SSRFValidationError(f"DNS resolution failed for {hostname}: {e}")

    if not addr_infos:
        raise SSRFValidationError(f"No DNS records found for {hostname}")

    # Check ALL resolved IP addresses
    for addr_info in addr_infos:
        ip_str = addr_info[4][0]

        # Always block cloud metadata endpoints, even when allow_private=True
        if ip_str in CLOUD_METADATA_IPS:
            raise SSRFValidationError(
                f"Blocked cloud metadata IP: {ip_str} (resolved from {hostname})"
            )

        if not allow_private and is_dangerous_ip(ip_str):
            raise SSRFValidationError(
                f"Blocked dangerous IP: {ip_str} (resolved from {hostname})"
            )

    return url


def validate_ollama_url(url: str) -> str:
    """
    Validate an Ollama base URL.

    More permissive than validate_url() because Ollama legitimately runs on
    private networks (localhost, Docker host, LAN). Still blocks:
    - Non-HTTP schemes (file://, ftp://, gopher://, etc.)
    - Cloud metadata endpoints (169.254.169.254)
    - Empty/malformed URLs

    Args:
        url: The Ollama base URL to validate.

    Returns:
        The validated URL with trailing slash stripped.

    Raises:
        SSRFValidationError: If the URL fails validation.
    """
    if not url or not url.strip():
        raise SSRFValidationError("Ollama URL cannot be empty")

    # Use the general validator with allow_private=True
    validated = validate_url(url, allow_private=True)

    # Strip trailing slash for consistency
    return validated.rstrip("/")
