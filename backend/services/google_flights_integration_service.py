"""Typed Google Flights / SerpAPI credential helpers."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import GoogleFlightsIntegration
from services.encryption_key_service import get_api_key_encryption_key


def _identifier(tenant_id: str) -> str:
    return f"apikey_google_flights_{tenant_id}"


def encrypt_google_flights_key(api_key: str, tenant_id: str, db: Session) -> str:
    encryption_key = get_api_key_encryption_key(db)
    if not encryption_key:
        raise ValueError("Failed to get encryption key for Google Flights credential encryption")
    encryptor = TokenEncryption(encryption_key.encode())
    return encryptor.encrypt(api_key, _identifier(tenant_id))


def decrypt_google_flights_key(integration: GoogleFlightsIntegration, db: Session) -> str:
    encryption_key = get_api_key_encryption_key(db)
    if not encryption_key:
        raise ValueError("Failed to get encryption key for Google Flights credential decryption")
    encryptor = TokenEncryption(encryption_key.encode())
    return encryptor.decrypt(
        integration.api_key_encrypted,
        _identifier(integration.tenant_id),
    )


def get_google_flights_integration(
    tenant_id: Optional[str],
    db: Session,
) -> Optional[GoogleFlightsIntegration]:
    if not tenant_id:
        return None
    return (
        db.query(GoogleFlightsIntegration)
        .filter(
            GoogleFlightsIntegration.type == "google_flights",
            GoogleFlightsIntegration.tenant_id == tenant_id,
            GoogleFlightsIntegration.is_active == True,  # noqa: E712
        )
        .order_by(GoogleFlightsIntegration.id.desc())
        .first()
    )


def resolve_google_flights_api_key(tenant_id: Optional[str], db: Session) -> Optional[str]:
    integration = get_google_flights_integration(tenant_id, db)
    if not integration:
        return None
    return decrypt_google_flights_key(integration, db)


def configure_google_flights_integration(
    *,
    tenant_id: str,
    api_key: str,
    db: Session,
    default_currency: str = "USD",
    default_language: str = "en",
) -> GoogleFlightsIntegration:
    if not api_key or not api_key.strip():
        raise ValueError("API key cannot be empty")

    encrypted_key = encrypt_google_flights_key(api_key.strip(), tenant_id, db)
    existing = get_google_flights_integration(tenant_id, db)
    if existing:
        existing.api_key_encrypted = encrypted_key
        existing.default_currency = default_currency
        existing.default_language = default_language
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    integration = GoogleFlightsIntegration(
        type="google_flights",
        name="Google Flights (SerpAPI)",
        display_name="Google Flights",
        is_active=True,
        tenant_id=tenant_id,
        api_key_encrypted=encrypted_key,
        default_currency=default_currency,
        default_language=default_language,
        health_status="unknown",
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return integration
