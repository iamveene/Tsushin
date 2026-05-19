"""Shared GitLab Hub integration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import GitLabIntegration
from services.encryption_key_service import get_api_key_encryption_key


GITLAB_API_BASE_URL = "https://gitlab.com/api/v4"


@dataclass(frozen=True)
class GitLabResolvedConfig:
    site_url: str
    auth_method: str
    pat_token_encrypted: Optional[str]
    default_namespace: Optional[str]
    default_project: Optional[str]
    default_project_path: Optional[str]
    provider_mode: str
    gitlab_integration_id: Optional[int]


def normalize_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def normalize_project_path(value: Optional[str]) -> Optional[str]:
    normalized = normalize_optional(value)
    if not normalized:
        return None
    project_path = "/".join(part for part in normalized.strip("/").split("/") if part)
    return project_path or None


def pat_preview(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 8:
        return f"{token[:2]}..."
    return f"{token[:4]}...{token[-4:]}"


def get_gitlab_encryptor(db: Session) -> TokenEncryption:
    master_key = get_api_key_encryption_key(db)
    if not master_key:
        raise ValueError("missing_gitlab_encryption_key")
    return TokenEncryption(master_key.encode())


def encrypt_gitlab_pat(db: Session, tenant_id: str, plaintext: str) -> str:
    return get_gitlab_encryptor(db).encrypt(plaintext, tenant_id)


def decrypt_gitlab_pat(
    db: Session, tenant_id: str, encrypted: Optional[str]
) -> Optional[str]:
    if not encrypted:
        return None
    return get_gitlab_encryptor(db).decrypt(encrypted, tenant_id)


def load_gitlab_integration(
    db: Session,
    *,
    tenant_id: str,
    integration_id: int,
    require_active: bool = False,
) -> Optional[GitLabIntegration]:
    if not tenant_id:
        return None
    query = db.query(GitLabIntegration).filter(
        GitLabIntegration.id == integration_id,
        GitLabIntegration.tenant_id == tenant_id,
        GitLabIntegration.type == "gitlab",
    )
    if require_active:
        query = query.filter(GitLabIntegration.is_active == True)  # noqa: E712
    return query.first()


def resolve_gitlab_config(
    db: Session,
    integration: GitLabIntegration,
) -> GitLabResolvedConfig:
    del db
    return GitLabResolvedConfig(
        site_url=GITLAB_API_BASE_URL,
        auth_method=integration.auth_method or "pat",
        pat_token_encrypted=integration.pat_token_encrypted,
        default_namespace=integration.default_namespace,
        default_project=integration.default_project,
        default_project_path=integration.default_project_path,
        provider_mode=getattr(integration, "provider_mode", None) or "programmatic",
        gitlab_integration_id=integration.id,
    )
