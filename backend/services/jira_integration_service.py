"""Shared Jira Tool API integration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from channels.jira.utils import normalize_jira_site_url
from hub.security import TokenEncryption
from models import JiraChannelInstance, JiraIntegration
from services.encryption_key_service import get_webhook_encryption_key


@dataclass(frozen=True)
class JiraResolvedConfig:
    site_url: str
    project_key: Optional[str]
    auth_email: Optional[str]
    api_token_encrypted: Optional[str]
    api_token_preview: Optional[str]
    jira_integration_id: Optional[int]


def normalize_optional(value: Optional[str], *, upper: bool = False) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized.upper() if upper else normalized


def token_preview(token: str) -> str:
    if len(token) <= 8:
        return f"{token[:2]}..."
    return f"{token[:4]}...{token[-4:]}"


def get_jira_encryptor(db: Session) -> TokenEncryption:
    master_key = get_webhook_encryption_key(db)
    if not master_key:
        raise ValueError("missing_jira_encryption_key")
    return TokenEncryption(master_key.encode())


def encrypt_jira_token(db: Session, tenant_id: str, plaintext: str) -> str:
    return get_jira_encryptor(db).encrypt(plaintext, tenant_id)


def decrypt_jira_token(db: Session, tenant_id: str, encrypted: Optional[str]) -> Optional[str]:
    if not encrypted:
        return None
    return get_jira_encryptor(db).decrypt(encrypted, tenant_id)


def load_jira_integration(
    db: Session,
    *,
    tenant_id: str,
    integration_id: int,
    require_active: bool = False,
) -> Optional[JiraIntegration]:
    if not tenant_id:
        return None
    query = db.query(JiraIntegration).filter(
        JiraIntegration.id == integration_id,
        JiraIntegration.tenant_id == tenant_id,
        JiraIntegration.type == "jira",
    )
    if require_active:
        query = query.filter(JiraIntegration.is_active == True)  # noqa: E712
    return query.first()


def resolve_jira_config(db: Session, instance: JiraChannelInstance) -> JiraResolvedConfig:
    """Return linked Hub Jira config, or legacy trigger config when unlinked."""

    if instance.jira_integration_id:
        integration = load_jira_integration(
            db,
            tenant_id=instance.tenant_id,
            integration_id=instance.jira_integration_id,
        )
        if integration is None:
            raise ValueError("jira_integration_not_found")
        return JiraResolvedConfig(
            site_url=normalize_jira_site_url(integration.site_url),
            project_key=integration.project_key,
            auth_email=integration.auth_email,
            api_token_encrypted=integration.api_token_encrypted,
            api_token_preview=integration.api_token_preview,
            jira_integration_id=integration.id,
        )

    return JiraResolvedConfig(
        site_url=normalize_jira_site_url(instance.site_url),
        project_key=instance.project_key,
        auth_email=instance.auth_email,
        api_token_encrypted=instance.api_token_encrypted,
        api_token_preview=instance.api_token_preview,
        jira_integration_id=None,
    )
