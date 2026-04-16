"""
CDP URL Validator

Validates Chrome DevTools Protocol endpoint URLs.
Only loopback addresses and host.docker.internal are permitted.

This is intentionally separate from ssrf_validator.py:
ssrf_validator blocks host.docker.internal for navigation targets (correct).
CDP connections legitimately target the host machine.
"""

from urllib.parse import urlparse

ALLOWED_CDP_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "::1",
    "host.docker.internal",
})

ALLOWED_CDP_PORT_RANGE = (1024, 65535)
DEFAULT_CDP_URL = "http://host.docker.internal:9222"


class CDPURLError(ValueError):
    """Raised when a CDP URL fails validation."""
    pass


def validate_cdp_url(url: str) -> str:
    """
    Validate a Chrome DevTools Protocol endpoint URL.

    Only localhost, 127.0.0.1, ::1, and host.docker.internal are permitted.
    Port must be in non-privileged range (1024-65535).

    Args:
        url: CDP endpoint URL (e.g., "http://host.docker.internal:9222")

    Returns:
        The validated URL string.

    Raises:
        CDPURLError: If the URL is invalid or points to a disallowed host.
    """
    if not url or not url.strip():
        raise CDPURLError("CDP URL cannot be empty")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise CDPURLError(f"Invalid URL: {e}")

    if parsed.scheme not in ("http", "https"):
        raise CDPURLError(f"CDP URL must use http or https, got: {parsed.scheme}")

    hostname = (parsed.hostname or "").lower()
    if hostname not in ALLOWED_CDP_HOSTS:
        raise CDPURLError(
            f"CDP connections are only allowed to: {', '.join(sorted(ALLOWED_CDP_HOSTS))}. "
            f"Got: {hostname}"
        )

    port = parsed.port
    if port is not None:
        if not (ALLOWED_CDP_PORT_RANGE[0] <= port <= ALLOWED_CDP_PORT_RANGE[1]):
            raise CDPURLError(
                f"CDP port must be in range {ALLOWED_CDP_PORT_RANGE[0]}-{ALLOWED_CDP_PORT_RANGE[1]}, "
                f"got: {port}"
            )

    return url
