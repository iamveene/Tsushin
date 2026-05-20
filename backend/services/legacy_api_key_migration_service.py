"""Idempotent migration from legacy ApiKey rows to typed credentials.

This is deliberately runtime-blocking: active legacy rows must either migrate
cleanly or the backend startup fails before any request path can resolve a
fallback credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from constants.llm_models import DEFAULT_PROVIDER_MODELS
from hub.security import TokenEncryption
from models import (
    AmadeusIntegration,
    ApiKey,
    GoogleFlightsIntegration,
    ProviderInstance,
    SearchProviderIntegration,
    SearxngInstance,
    TTSInstance,
)
from models_rbac import Tenant
from services.api_key_service import _decrypt_api_key
from services.encryption_key_service import get_amadeus_encryption_key
from services.google_flights_integration_service import (
    encrypt_google_flights_key,
    get_google_flights_integration,
)
from services.provider_instance_service import ProviderInstanceService
from services.search_provider_integration_service import (
    _encrypt_api_key as encrypt_search_provider_key,
    _mask_key as mask_search_provider_key,
)
from services.tts_instance_service import TTSInstanceService

logger = logging.getLogger(__name__)


AI_VENDOR_SERVICES = {
    "openai",
    "anthropic",
    "gemini",
    "openrouter",
    "groq",
    "grok",
    "deepseek",
}
VERTEX_SERVICES = {
    "vertex_ai",
    "vertex_ai_project_id",
    "vertex_ai_region",
    "vertex_ai_sa_email",
}
SEARCH_SERVICE_TO_PROVIDER = {
    "brave": "brave",
    "brave_search": "brave",
    "tavily": "tavily",
    "google": "google",
    "google_search": "google",
    "serpapi": "google",
}
TRAVEL_SERVICES = {"google_flights", "amadeus"}
KNOWN_SERVICES = (
    AI_VENDOR_SERVICES
    | VERTEX_SERVICES
    | set(SEARCH_SERVICE_TO_PROVIDER)
    | TRAVEL_SERVICES
    | {"elevenlabs", "searxng"}
)


@dataclass(frozen=True)
class LegacyCredential:
    row: ApiKey
    tenant_id: str
    plaintext: str


def _active_tenant_ids(db: Session) -> List[str]:
    return [
        tenant_id
        for (tenant_id,) in db.query(Tenant.id)
        .filter(Tenant.is_active == True)  # noqa: E712
        .order_by(Tenant.id)
        .all()
        if tenant_id
    ]


def _expand_rows_to_tenants(rows: Iterable[ApiKey], db: Session) -> List[LegacyCredential]:
    tenant_ids = _active_tenant_ids(db)
    out: List[LegacyCredential] = []
    errors: List[str] = []

    for row in rows:
        service = (row.service or "").strip().lower()
        if service not in KNOWN_SERVICES:
            errors.append(f"id={row.id} service={row.service!r} is not mapped")
            continue

        plaintext = _decrypt_api_key(row, db)
        if not plaintext:
            errors.append(f"id={row.id} service={row.service!r} could not be decrypted")
            continue

        targets = [row.tenant_id] if row.tenant_id else tenant_ids
        if not targets:
            errors.append(
                f"id={row.id} service={row.service!r} is system-wide but no active tenants exist"
            )
            continue
        for tenant_id in targets:
            out.append(LegacyCredential(row=row, tenant_id=tenant_id, plaintext=plaintext.strip()))

    if errors:
        raise RuntimeError("Legacy ApiKey migration blocked: " + "; ".join(errors))
    return out


def _unique_provider_name(db: Session, tenant_id: str, base: str) -> str:
    existing = {
        name
        for (name,) in db.query(ProviderInstance.instance_name)
        .filter(ProviderInstance.tenant_id == tenant_id)
        .all()
    }
    if base not in existing:
        return base
    idx = 2
    while f"{base} {idx}" in existing:
        idx += 1
    return f"{base} {idx}"


def _unique_tts_name(db: Session, tenant_id: str, base: str) -> str:
    existing = {
        name
        for (name,) in db.query(TTSInstance.instance_name)
        .filter(TTSInstance.tenant_id == tenant_id)
        .all()
    }
    if base not in existing:
        return base
    idx = 2
    while f"{base} {idx}" in existing:
        idx += 1
    return f"{base} {idx}"


def _resolve_existing_provider_key(instance: ProviderInstance, db: Session) -> Optional[str]:
    if not instance.api_key_encrypted:
        return None
    try:
        return ProviderInstanceService.resolve_api_key(instance, db)
    except Exception:
        return None


def _upsert_provider_instance(
    db: Session,
    *,
    tenant_id: str,
    vendor: str,
    api_key: str,
    extra_config: Optional[dict] = None,
) -> bool:
    active_rows = (
        db.query(ProviderInstance)
        .filter(
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.vendor == vendor,
            ProviderInstance.is_active == True,  # noqa: E712
        )
        .order_by(ProviderInstance.is_default.desc(), ProviderInstance.id.asc())
        .all()
    )

    for row in active_rows:
        if _resolve_existing_provider_key(row, db) == api_key:
            if extra_config:
                row.extra_config = {**(row.extra_config or {}), **extra_config}
            return False

    unkeyed = next((row for row in active_rows if not row.api_key_encrypted), None)
    target = unkeyed
    if target is None and not active_rows:
        default_model = DEFAULT_PROVIDER_MODELS.get(vendor, "default")
        target = ProviderInstance(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=_unique_provider_name(db, tenant_id, f"{vendor.title()} (Migrated)"),
            base_url=None,
            available_models=[default_model],
            is_default=True,
            is_active=True,
            health_status="unknown",
        )
        db.add(target)
        db.flush()
    elif target is None:
        default_model = DEFAULT_PROVIDER_MODELS.get(vendor, "default")
        target = ProviderInstance(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=_unique_provider_name(db, tenant_id, f"{vendor.title()} (Migrated)"),
            base_url=None,
            available_models=[default_model],
            is_default=False,
            is_active=True,
            health_status="unknown",
        )
        db.add(target)
        db.flush()

    target.api_key_encrypted = ProviderInstanceService._encrypt_key(api_key, tenant_id, db)
    if extra_config:
        target.extra_config = {**(target.extra_config or {}), **extra_config}
    if not any(row.is_default for row in active_rows):
        target.is_default = True
    return True


def _upsert_elevenlabs_tts(db: Session, tenant_id: str, api_key: str) -> bool:
    active_rows = (
        db.query(TTSInstance)
        .filter(
            TTSInstance.tenant_id == tenant_id,
            TTSInstance.vendor == "elevenlabs",
            TTSInstance.is_active == True,  # noqa: E712
        )
        .order_by(TTSInstance.is_default.desc(), TTSInstance.id.asc())
        .all()
    )
    target = active_rows[0] if active_rows else None
    if target is None:
        target = TTSInstance(
            tenant_id=tenant_id,
            vendor="elevenlabs",
            instance_name=_unique_tts_name(db, tenant_id, "ElevenLabs (Migrated)"),
            description="Migrated from retired Service API Keys",
            is_default=True,
            is_active=True,
            health_status="unknown",
        )
        db.add(target)
        db.flush()

    target.api_key_encrypted = TTSInstanceService._encrypt_key(api_key, tenant_id, db)
    target.api_key_preview = TTSInstanceService.mask_api_key(api_key)
    return True


def _upsert_search_provider(db: Session, tenant_id: str, provider_id: str, api_key: str) -> bool:
    row = (
        db.query(SearchProviderIntegration)
        .filter(
            SearchProviderIntegration.provider_id == provider_id,
            SearchProviderIntegration.tenant_id == tenant_id,
            SearchProviderIntegration.is_active == True,  # noqa: E712
        )
        .order_by(SearchProviderIntegration.id.desc())
        .first()
    )
    label = {
        "brave": "Brave Search",
        "google": "Google Search (SerpAPI)",
        "tavily": "Tavily",
    }[provider_id]
    encrypted = encrypt_search_provider_key(api_key, tenant_id, provider_id, db)
    if row is None:
        row = SearchProviderIntegration(
            type="search_provider",
            name=label,
            display_name=label,
            tenant_id=tenant_id,
            provider_id=provider_id,
            api_key_encrypted=encrypted,
            api_key_preview=mask_search_provider_key(api_key),
            default_country="US",
            default_language="en",
            is_active=True,
        )
        db.add(row)
        db.flush()
    row.api_key_encrypted = encrypted
    row.api_key_preview = mask_search_provider_key(api_key)
    row.default_country = row.default_country or "US"
    row.default_language = row.default_language or "en"
    return True


def _upsert_google_flights(db: Session, tenant_id: str, api_key: str) -> bool:
    if not api_key or not api_key.strip():
        raise RuntimeError(f"Legacy Google Flights credential for tenant={tenant_id} is empty")

    encrypted_key = encrypt_google_flights_key(api_key.strip(), tenant_id, db)
    row = get_google_flights_integration(tenant_id, db)
    if row is None:
        row = GoogleFlightsIntegration(
            type="google_flights",
            name="Google Flights (Migrated)",
            display_name="Google Flights",
            is_active=True,
            tenant_id=tenant_id,
            api_key_encrypted=encrypted_key,
            default_currency="USD",
            default_language="en",
            health_status="unknown",
        )
        db.add(row)
        db.flush()
    else:
        row.api_key_encrypted = encrypted_key
        row.is_active = True
    return True


def _upsert_amadeus(db: Session, tenant_id: str, value: str) -> bool:
    if ":" not in value:
        raise RuntimeError(
            f"Legacy Amadeus credential for tenant={tenant_id} must be client_id:client_secret"
        )
    api_key, api_secret = value.split(":", 1)
    api_key = api_key.strip()
    api_secret = api_secret.strip()
    if not api_key or not api_secret:
        raise RuntimeError(f"Legacy Amadeus credential for tenant={tenant_id} is incomplete")

    encryption_key = get_amadeus_encryption_key(db)
    if not encryption_key:
        raise RuntimeError("Amadeus encryption key is not configured")

    row = (
        db.query(AmadeusIntegration)
        .filter(
            AmadeusIntegration.type == "amadeus",
            AmadeusIntegration.tenant_id == tenant_id,
        )
        .first()
    )
    if row is None:
        row = AmadeusIntegration(
            type="amadeus",
            name="Amadeus (Migrated)",
            display_name="Amadeus",
            tenant_id=tenant_id,
            is_active=True,
            environment="test",
            api_key=api_key,
            default_currency="BRL",
            max_results=5,
            health_status="unknown",
            api_secret_encrypted="pending",
        )
        db.add(row)
        db.flush()
    else:
        row.api_key = api_key
        row.is_active = True

    encryptor = TokenEncryption(encryption_key.encode())
    row.api_secret_encrypted = encryptor.encrypt(api_secret, f"amadeus_{row.id}")
    return True


def _upsert_searxng(db: Session, tenant_id: str, base_url: str) -> bool:
    row = (
        db.query(SearxngInstance)
        .filter(
            SearxngInstance.tenant_id == tenant_id,
            SearxngInstance.is_active == True,  # noqa: E712
        )
        .order_by(SearxngInstance.id.desc())
        .first()
    )
    if row is None:
        row = SearxngInstance(
            tenant_id=tenant_id,
            vendor="searxng",
            instance_name="SearXNG (Migrated)",
            description="Migrated from retired Service API Keys",
            base_url=base_url,
            extra_config={},
            is_auto_provisioned=False,
            is_active=True,
            health_status="unknown",
        )
        db.add(row)
        db.flush()
    else:
        row.base_url = base_url
    return True


def _collect_vertex_groups(credentials: Iterable[LegacyCredential]) -> Dict[str, Dict[str, LegacyCredential]]:
    groups: Dict[str, Dict[str, LegacyCredential]] = {}
    for item in credentials:
        service = item.row.service.strip().lower()
        if service in VERTEX_SERVICES:
            groups.setdefault(item.tenant_id, {})[service] = item
    return groups


def migrate_active_legacy_api_keys(db: Session) -> Dict[str, int]:
    """Migrate all active ApiKey rows to typed credential models and disable them."""
    rows = db.query(ApiKey).filter(ApiKey.is_active == True).order_by(ApiKey.id.asc()).all()  # noqa: E712
    if not rows:
        return {
            "legacy_rows_seen": 0,
            "legacy_rows_disabled": 0,
            "typed_rows_touched": 0,
        }

    credentials = _expand_rows_to_tenants(rows, db)
    typed_rows_touched = 0

    vertex_groups = _collect_vertex_groups(credentials)
    for tenant_id, group in vertex_groups.items():
        private_key = group.get("vertex_ai")
        project_id = group.get("vertex_ai_project_id")
        sa_email = group.get("vertex_ai_sa_email")
        if not private_key or not project_id or not sa_email:
            raise RuntimeError(
                f"Legacy Vertex AI credentials for tenant={tenant_id} are incomplete; "
                "expected vertex_ai, vertex_ai_project_id, and vertex_ai_sa_email"
            )
        region = group.get("vertex_ai_region")
        typed_rows_touched += int(
            _upsert_provider_instance(
                db,
                tenant_id=tenant_id,
                vendor="vertex_ai",
                api_key=private_key.plaintext,
                extra_config={
                    "project_id": project_id.plaintext,
                    "region": region.plaintext if region else "us-east5",
                    "sa_email": sa_email.plaintext,
                },
            )
        )

    for item in credentials:
        service = item.row.service.strip().lower()
        if service in VERTEX_SERVICES:
            continue
        if service in AI_VENDOR_SERVICES:
            typed_rows_touched += int(
                _upsert_provider_instance(
                    db,
                    tenant_id=item.tenant_id,
                    vendor=service,
                    api_key=item.plaintext,
                )
            )
        elif service == "elevenlabs":
            typed_rows_touched += int(_upsert_elevenlabs_tts(db, item.tenant_id, item.plaintext))
        elif service in SEARCH_SERVICE_TO_PROVIDER:
            provider_id = SEARCH_SERVICE_TO_PROVIDER[service]
            typed_rows_touched += int(
                _upsert_search_provider(db, item.tenant_id, provider_id, item.plaintext)
            )
        elif service == "google_flights":
            typed_rows_touched += int(_upsert_google_flights(db, item.tenant_id, item.plaintext))
        elif service == "amadeus":
            typed_rows_touched += int(_upsert_amadeus(db, item.tenant_id, item.plaintext))
        elif service == "searxng":
            typed_rows_touched += int(_upsert_searxng(db, item.tenant_id, item.plaintext))
        else:
            raise RuntimeError(f"Legacy ApiKey service {service!r} was not migrated")

    now = datetime.utcnow()
    for row in rows:
        row.is_active = False
        row.updated_at = now

    db.commit()
    logger.info(
        "Migrated and disabled %s active legacy ApiKey row(s); typed rows touched=%s",
        len(rows),
        typed_rows_touched,
    )
    return {
        "legacy_rows_seen": len(rows),
        "legacy_rows_disabled": len(rows),
        "typed_rows_touched": typed_rows_touched,
    }
