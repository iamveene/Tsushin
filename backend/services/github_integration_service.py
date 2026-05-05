"""Shared GitHub Hub integration helpers.

Mirrors :mod:`services.jira_integration_service` exactly. The PAT is treated
as an API credential, so we use ``get_api_key_encryption_key`` (NOT the
webhook key) for encryption / decryption.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import GitHubIntegration
from services.encryption_key_service import get_api_key_encryption_key


# GitHub REST API base URL — every PAT-authenticated call goes here. Stored
# as a constant so resolve_github_config() always returns the same value.
GITHUB_API_BASE_URL: str = "https://api.github.com"


@dataclass(frozen=True)
class GitHubResolvedConfig:
    """Resolved view of a :class:`GitHubIntegration` row used by services."""

    site_url: str
    auth_method: str
    pat_token_encrypted: Optional[str]
    default_owner: Optional[str]
    default_repo: Optional[str]
    provider_mode: str
    github_integration_id: Optional[int]


def normalize_optional(value: Optional[str]) -> Optional[str]:
    """Strip whitespace, return ``None`` for empty values."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def pat_preview(token: str) -> str:
    """Return a masked preview of the PAT (e.g. ``ghp_...wxyz``).

    Mirrors :func:`services.jira_integration_service.token_preview`.
    """
    if not token:
        return ""
    if len(token) <= 8:
        return f"{token[:2]}..."
    return f"{token[:4]}...{token[-4:]}"


def get_github_encryptor(db: Session) -> TokenEncryption:
    """Return a :class:`TokenEncryption` bound to the API-key master key.

    PATs are LLM-style API credentials, so we share the API-key encryption
    key (already used for OpenAI/Anthropic keys) rather than the webhook key.
    """
    master_key = get_api_key_encryption_key(db)
    if not master_key:
        raise ValueError("missing_github_encryption_key")
    return TokenEncryption(master_key.encode())


def encrypt_github_pat(db: Session, tenant_id: str, plaintext: str) -> str:
    return get_github_encryptor(db).encrypt(plaintext, tenant_id)


def decrypt_github_pat(
    db: Session, tenant_id: str, encrypted: Optional[str]
) -> Optional[str]:
    if not encrypted:
        return None
    return get_github_encryptor(db).decrypt(encrypted, tenant_id)


def load_github_integration(
    db: Session,
    *,
    tenant_id: str,
    integration_id: int,
    require_active: bool = False,
) -> Optional[GitHubIntegration]:
    """Load a tenant-scoped :class:`GitHubIntegration` row by id."""
    if not tenant_id:
        return None
    query = db.query(GitHubIntegration).filter(
        GitHubIntegration.id == integration_id,
        GitHubIntegration.tenant_id == tenant_id,
        GitHubIntegration.type == "github",
    )
    if require_active:
        query = query.filter(GitHubIntegration.is_active == True)  # noqa: E712
    return query.first()


def resolve_github_config(
    db: Session,
    integration: GitHubIntegration,
) -> GitHubResolvedConfig:
    """Return a flat config view for callers that don't want to touch ORM rows."""
    return GitHubResolvedConfig(
        site_url=GITHUB_API_BASE_URL,
        auth_method=integration.auth_method or "pat",
        pat_token_encrypted=integration.pat_token_encrypted,
        default_owner=integration.default_owner,
        default_repo=integration.default_repo,
        provider_mode=getattr(integration, "provider_mode", None) or "programmatic",
        github_integration_id=integration.id,
    )
