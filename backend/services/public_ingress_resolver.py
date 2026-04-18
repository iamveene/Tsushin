"""Public ingress resolver — single source of truth for "what public HTTPS URL
reaches this backend on behalf of this tenant".

Before v0.6.1 three features each answered this question differently:

  1. `tenant.public_base_url` — free-text HTTPS string a tenant admin pasted,
     consumed directly by SlackSetupWizard / DiscordSetupWizard.
  2. Global Remote Access tunnel (`CloudflareTunnelService.public_url`) —
     live tunnel URL only visible to global admins on /system/remote-access.
  3. WebhookSetupModal — used `window.location.origin` client-side, which
     silently broke when an admin browsed via LAN IP.

This resolver returns an authoritative `IngressResult` with a `source` field
so every consumer (Slack/Discord wizards, Webhook modal, PublicBaseUrlCard)
renders the same URL, with a clear provenance badge.

Precedence (highest to lowest):
  1. override — tenant.public_base_url, if set and format-valid
  2. tunnel  — platform Cloudflare tunnel, if state == "running" and it has
               a public_url (ingress does NOT require the login-only
               `remote_access_enabled` flag — those concerns are decoupled)
  3. dev     — TSUSHIN_DEV_PUBLIC_BASE_URL env, if set
  4. none    — no ingress configured

Design notes:
  - The resolver is pure-sync and performs no network I/O. Format validation
    is cheap; DNS resolution is the caller's responsibility (done at write
    time in routes_tenant_settings._dns_check).
  - Reading `_state.public_url` on the tunnel singleton without the asyncio
    lock is safe under the service's --workers 1 deployment (see
    cloudflare_tunnel_service.py:25-27). CPython's GIL makes the pointer
    read atomic and `_state` is rebound as a whole snapshot under the lock.
  - If the override URL fails format validation, we keep source="override"
    and emit a `warning` rather than silently falling through — see
    reviewer feedback (silent demotion hides misconfiguration).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session  # noqa: F401  (kept for type clarity / future use)

from models_rbac import Tenant

logger = logging.getLogger(__name__)

IngressSource = Literal["override", "tunnel", "dev", "none"]

# Accepts any standard hostname (letters/digits/dots/dashes). The write-side
# validator in routes_tenant_settings performs the stricter DNS + scheme check.
_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-]{0,252}[a-zA-Z0-9]$")


@dataclass
class IngressResult:
    url: Optional[str]
    source: IngressSource
    warning: Optional[str] = None
    override_url: Optional[str] = None  # raw tenant.public_base_url regardless of which source wins


def _validate_url_shape(url: str) -> Optional[str]:
    """Return an error message if the URL is structurally malformed, else None."""
    try:
        parsed = urlparse(url)
    except Exception:  # pragma: no cover
        return "override URL is malformed"
    if parsed.scheme not in ("http", "https"):
        return "override URL must start with https:// (or http:// in dev)"
    if not parsed.hostname:
        return "override URL is missing a hostname"
    if not _HOSTNAME_RE.match(parsed.hostname):
        return "override URL hostname is invalid"
    return None


def resolve_public_ingress(tenant: Tenant) -> IngressResult:
    """Resolve the public HTTPS URL for the given tenant.

    Does NOT hit the database directly (the tenant row is expected to be
    pre-fetched by the caller). Does NOT perform DNS or HTTP probes — those
    belong at write time in the PATCH validator.
    """
    override_raw: Optional[str] = (tenant.public_base_url or None) if tenant else None

    # --- 1. Tenant override ---
    if override_raw:
        err = _validate_url_shape(override_raw)
        if err is None:
            return IngressResult(
                url=override_raw.rstrip("/"),
                source="override",
                override_url=override_raw,
            )
        # Invalid shape: keep the override source but surface the issue.
        # Consumers can still show the tenant WHAT is broken instead of
        # silently falling back to a different URL.
        return IngressResult(
            url=None,
            source="override",
            warning=f"Override URL stored but invalid: {err}",
            override_url=override_raw,
        )

    # --- 2. Platform tunnel ---
    tunnel_url = _peek_tunnel_url()
    if tunnel_url:
        return IngressResult(
            url=tunnel_url.rstrip("/"),
            source="tunnel",
            override_url=None,
        )

    # --- 3. Dev env var ---
    # Deferred import so `settings` changes during tests don't require
    # re-importing this module.
    import settings

    dev_url = getattr(settings, "DEV_PUBLIC_BASE_URL", None)
    if dev_url:
        dev_err = _validate_url_shape(dev_url)
        if dev_err is None:
            return IngressResult(url=dev_url.rstrip("/"), source="dev")
        logger.warning(
            "TSUSHIN_DEV_PUBLIC_BASE_URL is set but invalid (%s): %s",
            dev_url, dev_err,
        )

    # --- 4. None ---
    return IngressResult(url=None, source="none")


def _peek_tunnel_url() -> Optional[str]:
    """Read the current public_url from the global tunnel singleton, or None.

    Safe to call even before the tunnel lifespan has initialized — we catch
    the RuntimeError raised by get_cloudflare_tunnel_service() in that case.
    """
    try:
        from services.cloudflare_tunnel_service import get_cloudflare_tunnel_service
        service = get_cloudflare_tunnel_service()
    except RuntimeError:
        return None
    except Exception as exc:  # pragma: no cover
        logger.warning("Unexpected error accessing tunnel service: %s", exc)
        return None

    # Lock-free snapshot read — see module docstring re: safety under --workers 1.
    state = getattr(service, "_state", None)
    if state is None:
        return None
    if getattr(state, "state", None) != "running":
        return None
    public_url = getattr(state, "public_url", None)
    if not public_url:
        return None
    return public_url
