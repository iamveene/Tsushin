"""Typed credential store for hosted web-search providers.

This replaces the retired ``api_key`` runtime resolver for Brave Search,
Tavily, and SerpAPI-backed Google Search.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import SearchProviderIntegration
from services.encryption_key_service import get_api_key_encryption_key
from services.provider_aliases import normalize_search_provider_id


SUPPORTED_SEARCH_CREDENTIAL_PROVIDERS = {"brave", "google", "tavily"}


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"


def _identifier(tenant_id: str, provider_id: str) -> str:
    return f"search_provider_{tenant_id}_{provider_id}"


def _encrypt_api_key(api_key: str, tenant_id: str, provider_id: str, db: Session) -> str:
    encryption_key = get_api_key_encryption_key(db)
    if not encryption_key:
        raise ValueError("Failed to get encryption key for search provider credential encryption")
    encryptor = TokenEncryption(encryption_key.encode())
    return encryptor.encrypt(api_key, _identifier(tenant_id, provider_id))


def _decrypt_api_key(row: SearchProviderIntegration, db: Session) -> str:
    encryption_key = get_api_key_encryption_key(db)
    if not encryption_key:
        raise ValueError("Failed to get encryption key for search provider credential decryption")
    encryptor = TokenEncryption(encryption_key.encode())
    return encryptor.decrypt(row.api_key_encrypted, _identifier(row.tenant_id, row.provider_id))


def get_search_provider_integration(
    provider_id: str,
    tenant_id: Optional[str],
    db: Session,
) -> Optional[SearchProviderIntegration]:
    normalized = normalize_search_provider_id(provider_id)
    if not tenant_id:
        return None
    return (
        db.query(SearchProviderIntegration)
        .filter(
            SearchProviderIntegration.provider_id == normalized,
            SearchProviderIntegration.tenant_id == tenant_id,
            SearchProviderIntegration.is_active == True,  # noqa: E712
        )
        .order_by(SearchProviderIntegration.id.desc())
        .first()
    )


def has_search_provider_credentials(provider_id: str, tenant_id: Optional[str], db: Session) -> bool:
    return get_search_provider_integration(provider_id, tenant_id, db) is not None


def resolve_search_provider_api_key(provider_id: str, tenant_id: Optional[str], db: Session) -> Optional[str]:
    row = get_search_provider_integration(provider_id, tenant_id, db)
    if not row:
        return None
    return _decrypt_api_key(row, db)


def configure_search_provider(
    *,
    provider_id: str,
    tenant_id: str,
    api_key: str,
    db: Session,
    display_name: Optional[str] = None,
    default_country: str = "US",
    default_language: str = "en",
) -> SearchProviderIntegration:
    normalized = normalize_search_provider_id(provider_id)
    if normalized not in SUPPORTED_SEARCH_CREDENTIAL_PROVIDERS:
        raise ValueError(f"Unsupported hosted search provider: {provider_id}")
    if not api_key or not api_key.strip():
        raise ValueError("API key cannot be empty")

    existing = get_search_provider_integration(normalized, tenant_id, db)
    encrypted = _encrypt_api_key(api_key.strip(), tenant_id, normalized, db)
    label = display_name or {
        "brave": "Brave Search",
        "google": "Google Search (SerpAPI)",
        "tavily": "Tavily",
    }.get(normalized, normalized)

    if existing:
        existing.api_key_encrypted = encrypted
        existing.api_key_preview = _mask_key(api_key.strip())
        existing.display_name = label
        existing.default_country = default_country
        existing.default_language = default_language
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    row = SearchProviderIntegration(
        type="search_provider",
        name=label,
        display_name=label,
        tenant_id=tenant_id,
        provider_id=normalized,
        api_key_encrypted=encrypted,
        api_key_preview=_mask_key(api_key.strip()),
        default_country=default_country,
        default_language=default_language,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
