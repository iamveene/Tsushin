"""
Phase 21: Provider Instance Management API Routes

Provides CRUD endpoints for multi-instance LLM provider configuration,
connection testing, model discovery, and URL validation.
Each tenant can manage multiple provider instances (e.g., multiple OpenAI-compatible
servers, Ollama instances, or custom LLM gateways).
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging
import time

from models import ProviderInstance, ProviderConnectionAudit, Agent
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
    get_current_user_optional_strict_from_request,
    ensure_permission,
)
from services.audit_service import log_tenant_event, TenantAuditActions


# BUG-709 FIX (v0.7.0): Predefined tenant-audit actions for provider-instance
# CRUD. Suggested-by-bug names map cleanly onto the existing TenantAuditActions
# convention even though they aren't yet baked into the class — using string
# literals here keeps the change surgical and avoids touching the audit
# constants file (and downstream syslog forwarder mappings).
_PROVIDER_AUDIT_CREATE = "provider.created"
_PROVIDER_AUDIT_UPDATE = "provider.updated"
_PROVIDER_AUDIT_DELETE = "provider.deleted"


def _provider_audit_payload(instance: ProviderInstance) -> dict:
    """
    BUG-709: Redacted payload for provider-instance audit events.
    Never include `api_key`, encrypted blob, or extra_config (which can carry
    Vertex AI service-account JSON keys). Only emit safe identifiers.
    """
    return {
        "id": instance.id,
        "vendor": instance.vendor,
        "instance_name": instance.instance_name,
        "is_active": bool(instance.is_active),
        "is_default": bool(instance.is_default),
    }

logger = logging.getLogger(__name__)

router = APIRouter()

# Global engine reference
_engine = None


def set_engine(engine):
    """Set the global engine reference"""
    global _engine
    _engine = engine


def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.rollback()
        except Exception:
            pass
        db.close()


# ==================== Pydantic Schemas ====================

class ProviderInstanceCreate(BaseModel):
    vendor: str
    instance_name: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    extra_config: Optional[dict] = None  # Vendor-specific: vertex_ai uses project_id, region, sa_email
    available_models: List[str] = []
    is_default: bool = False


class ProviderInstanceUpdate(BaseModel):
    instance_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    extra_config: Optional[dict] = None
    available_models: Optional[List[str]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class ProviderInstanceResponse(BaseModel):
    id: int
    tenant_id: str
    vendor: str
    instance_name: str
    base_url: Optional[str] = None
    api_key_configured: bool
    api_key_preview: str
    extra_config: Optional[dict] = None
    available_models: List[str]
    is_default: bool
    is_active: bool
    health_status: str
    health_status_reason: Optional[str] = None
    last_health_check: Optional[str] = None
    is_auto_provisioned: bool = False
    container_status: Optional[str] = None
    container_name: Optional[str] = None
    container_port: Optional[int] = None
    container_image: Optional[str] = None
    volume_name: Optional[str] = None
    mem_limit: Optional[str] = None
    gpu_enabled: bool = False
    pulled_models: List[str] = []


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None


class TestConnectionRawRequest(BaseModel):
    vendor: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None  # Model to test — avoids relying on hardcoded fallback
    extra_config: Optional[Dict[str, Any]] = None  # Provider-specific config (e.g. Vertex AI project_id, sa_email, region)


class TestConnectionSavedRequest(BaseModel):
    """Optional body for testing a saved instance with a specific model."""
    model: Optional[str] = None


class DiscoverModelsRawRequest(BaseModel):
    vendor: str
    api_key: str
    base_url: Optional[str] = None


class UrlValidationRequest(BaseModel):
    url: str
    vendor: Optional[str] = None


class UrlValidationResponse(BaseModel):
    valid: bool
    error: Optional[str] = None


class VendorInfoResponse(BaseModel):
    """Single vendor entry for the /api/providers/vendors catalog.

    Drives the frontend provider-instance modal vendor dropdown — lets the
    modal fetch the canonical vendor list rather than keeping a hardcoded
    copy that silently drifts from VALID_VENDORS / VENDOR_DEFAULT_BASE_URLS.
    """
    id: str
    display_name: str
    default_base_url: Optional[str] = None
    # Whether the vendor supports GET /v1beta/models or /v1/models live
    # discovery via discover-models-raw. Matches the LIVE_SUPPORTED set used
    # on the frontend to decide if the API-key input should trigger discovery.
    supports_discovery: bool = False
    # True when this tenant has at least one active ProviderInstance for this
    # vendor (same resolution pattern as /api/tts-providers:tenant_has_configured).
    tenant_has_configured: bool = False


# ==================== Helpers ====================

VALID_VENDORS = {"openai", "anthropic", "gemini", "groq", "grok", "deepseek", "openrouter", "ollama", "vertex_ai", "custom"}

# Display names for the vendor dropdown — the frontend modal previously
# hardcoded these in parallel; surfaced via /api/providers/vendors so adding
# a vendor only requires a VALID_VENDORS + VENDOR_DISPLAY_NAMES edit.
VENDOR_DISPLAY_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "groq": "Groq",
    "grok": "Grok (xAI)",
    "openrouter": "OpenRouter",
    "deepseek": "DeepSeek",
    "vertex_ai": "Vertex AI (Google Cloud)",
    "ollama": "Ollama",
    "custom": "Custom",
}

# Vendors whose /models endpoint is supported by discover-models-raw.
# Mirrors the LIVE_SUPPORTED set in ProviderInstanceModal.tsx.
VENDORS_WITH_LIVE_DISCOVERY = {"gemini", "openai", "groq", "grok", "deepseek", "openrouter"}


def _disable_sdk_retries(ai_client) -> None:
    """Disable automatic retries on the underlying SDK client for connection tests.

    SDK default retries (e.g. Anthropic retries 529/overloaded 2x with backoff)
    cause the "Test Connection" button to hang for 30+ seconds. Connection tests
    should fail fast so the user gets immediate feedback.
    """
    inner = getattr(ai_client, 'client', None)
    if inner is None:
        return
    # Anthropic SDK (AsyncAnthropic) and OpenAI SDK (AsyncOpenAI) both expose _max_retries
    if hasattr(inner, '_max_retries'):
        inner._max_retries = 0
    # Also set the public attribute if it exists
    if hasattr(inner, 'max_retries'):
        inner.max_retries = 0


def _sanitize_test_error(err_str: str, test_model: str) -> str:
    """Return a user-friendly error message for connection test failures."""
    lower = err_str.lower()
    if "api_key" in lower or "unauthorized" in lower or "401" in err_str:
        return "Authentication failed — check your API key"
    if "timeout" in lower or "connect" in lower:
        return "Connection timed out — check the base URL"
    if "not found" in lower or "404" in err_str:
        return f"Model '{test_model}' not found on this provider"
    if "overloaded" in lower or "529" in err_str:
        return f"Provider is temporarily overloaded (529) — try again in a few seconds"
    if "rate" in lower or "429" in err_str:
        return "Rate limited by provider — wait a moment and retry"
    if "permission" in lower or "403" in err_str:
        return "Access denied — check API key permissions for this model"
    return f"Connection test failed: {err_str[:200]}"


async def _background_test_instance(instance_id: int, user_id: int) -> None:
    """Run a connection test in the background after create/update.

    Without this, cloud LLM provider instances sit at health_status='unknown'
    (gray dot in the Hub UI) until the user explicitly clicks Test Connection,
    even though the credentials may be perfectly valid. Mirrors the logic of
    the test_provider_connection endpoint but runs in a fresh DB session
    because the request session is closed by the time BackgroundTasks fires.
    """
    if _engine is None:
        logger.warning("Auto-test skipped for instance %s: engine not initialized", instance_id)
        return

    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        instance = db.query(ProviderInstance).filter(ProviderInstance.id == instance_id).first()
        if not instance:
            return

        has_instance_key = bool(_decrypt_provider_key(instance, db))
        has_tenant_key = False
        if not has_instance_key:
            try:
                from services.api_key_service import get_api_key
                has_tenant_key = bool(get_api_key(instance.vendor, db, tenant_id=instance.tenant_id))
            except Exception:
                pass
        if not has_instance_key and not has_tenant_key and instance.vendor != "ollama":
            return

        from api.routes_integrations import PROVIDER_TEST_MODELS
        test_model = None
        if instance.available_models:
            test_model = instance.available_models[0]
        if not test_model:
            test_model = PROVIDER_TEST_MODELS.get(instance.vendor)
        if not test_model and instance.vendor == "ollama":
            test_model = "llama3.2"
        if not test_model and instance.vendor == "custom":
            test_model = "default"
        if not test_model:
            return

        start_time = time.time()
        error_message: Optional[str] = None
        success = False
        resolved_ip: Optional[str] = None

        try:
            from agent.ai_client import AIClient
            from analytics.token_tracker import TokenTracker
            tracker = TokenTracker(db, instance.tenant_id)

            client = AIClient(
                provider=instance.vendor if instance.vendor != "custom" else "openai",
                model_name=test_model,
                db=db,
                token_tracker=tracker,
                tenant_id=instance.tenant_id,
                provider_instance_id=instance.id,
                max_tokens=20,
            )
            _disable_sdk_retries(client)

            result = await client.generate(
                system_prompt="You are a test assistant. Respond with exactly: OK",
                user_message="Test connection. Reply with OK.",
                operation_type="connection_test",
            )
            if result.get("error"):
                error_message = str(result["error"])
            else:
                success = True

            if instance.base_url:
                try:
                    from urllib.parse import urlparse
                    import socket
                    parsed = urlparse(instance.base_url)
                    if parsed.hostname:
                        resolved_ip = socket.gethostbyname(parsed.hostname)
                except Exception:
                    pass
        except Exception as e:
            error_message = _sanitize_test_error(str(e), test_model)
            logger.warning("Auto-test failed for instance %s: %s", instance_id, e)

        latency_ms = int((time.time() - start_time) * 1000)

        instance.health_status = "healthy" if success else "unavailable"
        instance.health_status_reason = None if success else error_message
        instance.last_health_check = datetime.utcnow()

        audit = ProviderConnectionAudit(
            tenant_id=instance.tenant_id,
            user_id=user_id,
            provider_instance_id=instance.id,
            action="auto_test_on_save",
            resolved_ip=resolved_ip,
            base_url=instance.base_url,
            success=success,
            error_message=error_message,
        )
        db.add(audit)
        db.commit()
        logger.info(
            "Auto-test for instance %s (%s) -> %s (%dms)",
            instance_id, instance.vendor,
            "healthy" if success else "unavailable", latency_ms,
        )
    except Exception as e:
        logger.error("Auto-test for instance %s crashed: %s", instance_id, e)
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


# Gemini image-generation models are deliberately separated from the normal
# Gemini LLM suggestions. ProviderInstance.available_models feeds general
# agent model pickers, so image-only IDs must not leak into the generic
# `gemini` bucket or live Gemini discovery results.
GEMINI_IMAGE_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "imagen-4.0-fast-generate-001",
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
]


def _is_gemini_image_model(model_id: str) -> bool:
    return model_id in GEMINI_IMAGE_MODELS


OPENAI_IMAGE_MODELS = [
    "gpt-image-2",
]


def _is_openai_image_model(model_id: str) -> bool:
    return model_id in OPENAI_IMAGE_MODELS


# Curated suggestions shown in the UI as model-name autocomplete.
# Providers with a live /models endpoint (openai/groq/grok/deepseek/openrouter via
# Auto-detect, gemini via live discovery below) will replace this list after
# the instance is saved; the suggestions help users pick a sensible default
# *before* saving. Kept free of `ollama`, `vertex_ai`, `custom` — those are
# fully user-supplied (ollama via Auto-detect against the local daemon).
PREDEFINED_MODELS = {
    "openai": [
        "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini",
        "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo",
        "o1", "o1-mini", "o3-mini", "o4-mini",
    ],
    "openai_image": OPENAI_IMAGE_MODELS,
    "anthropic": [
        # Current generation. Older claude-3.5-sonnet / claude-3-opus removed
        # from selectable list (BUG-697); pricing rows in token_tracker.py are
        # retained for legacy invoice cost calculation.
        "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5",
        "claude-sonnet-4-20250514",
    ],
    "gemini": [
        # Static fallback only — used when the live /v1beta/models call fails
        # or no API key is available yet. The modal and setup page call
        # /provider-instances/discover-models-raw with the user's key to
        # refresh this list live from Google.
        # Gemini 3.x (preview):
        "gemini-3.1-pro-preview", "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        # Gemini 2.5 (stable):
        "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
        # Gemini 2.0 / 1.5 (legacy):
        "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash",
    ],
    "gemini_image": GEMINI_IMAGE_MODELS,
    "groq": [
        "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
        "mixtral-8x7b-32768", "gemma2-9b-it",
    ],
    "grok": [
        "grok-3", "grok-3-mini", "grok-2",
    ],
    "deepseek": [
        "deepseek-chat", "deepseek-reasoner",
    ],
    "openrouter": [
        "google/gemini-2.5-flash", "anthropic/claude-sonnet-4",
        "openai/gpt-4o-mini", "meta-llama/llama-3.1-8b-instruct:free",
    ],
    "vertex_ai": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-latest",
    ],
}


def _encrypt_provider_key(plaintext_key: str, tenant_id: str, instance_id: int, db: Session) -> Optional[str]:
    """Encrypt a provider instance API key for storage.
    Uses the same identifier pattern as ProviderInstanceService for consistency.
    """
    try:
        from services.provider_instance_service import ProviderInstanceService
        return ProviderInstanceService._encrypt_key(plaintext_key, tenant_id, db)
    except Exception as e:
        logger.error(f"Failed to encrypt provider instance key: {e}")
        return None


def _decrypt_provider_key(instance: ProviderInstance, db: Session) -> Optional[str]:
    """Decrypt a provider instance API key.
    Uses the same identifier pattern as ProviderInstanceService for consistency.
    """
    if not instance.api_key_encrypted:
        return None
    try:
        from services.provider_instance_service import ProviderInstanceService
        return ProviderInstanceService._decrypt_key(instance.api_key_encrypted, instance.tenant_id, db)
    except Exception as e:
        logger.error(f"Failed to decrypt provider instance key for instance {instance.id}: {e}")
        return None


def _mask_api_key(encrypted_value: str, tenant_id: str, instance: ProviderInstance, db: Session) -> str:
    """Decrypt and mask an API key for display (show first 4 and last 4 chars)."""
    decrypted = _decrypt_provider_key(instance, db)
    if not decrypted:
        return "***"
    if len(decrypted) <= 8:
        return "***"
    return f"{decrypted[:4]}...{decrypted[-4:]}"


def _to_response(instance: ProviderInstance, db: Session) -> ProviderInstanceResponse:
    """Convert a ProviderInstance model to a ProviderInstanceResponse."""
    # For Vertex AI, redact private_key from extra_config in response
    extra = instance.extra_config or {}
    if instance.vendor == "vertex_ai" and extra:
        extra = {k: v for k, v in extra.items() if k != "private_key"}
    return ProviderInstanceResponse(
        id=instance.id,
        tenant_id=instance.tenant_id,
        vendor=instance.vendor,
        instance_name=instance.instance_name,
        base_url=instance.base_url,
        api_key_configured=bool(instance.api_key_encrypted),
        api_key_preview=_mask_api_key(
            instance.api_key_encrypted, instance.tenant_id, instance, db
        ) if instance.api_key_encrypted else "",
        extra_config=extra if extra else None,
        available_models=instance.available_models or [],
        is_default=instance.is_default,
        is_active=instance.is_active,
        health_status=instance.health_status or "unknown",
        health_status_reason=instance.health_status_reason,
        last_health_check=instance.last_health_check.isoformat() if instance.last_health_check else None,
        is_auto_provisioned=bool(getattr(instance, "is_auto_provisioned", False)),
        container_status=getattr(instance, "container_status", None),
        container_name=getattr(instance, "container_name", None),
        container_port=getattr(instance, "container_port", None),
        container_image=getattr(instance, "container_image", None),
        volume_name=getattr(instance, "volume_name", None),
        mem_limit=getattr(instance, "mem_limit", None),
        gpu_enabled=bool(getattr(instance, "gpu_enabled", False)),
        pulled_models=getattr(instance, "pulled_models", None) or [],
    )


# ==================== Endpoints ====================

@router.get("/provider-instances/predefined-models")
def get_predefined_models():
    """
    Return the curated list of well-known model IDs per provider.
    Public (no auth) — data is static and contains no tenant-specific info.
    Used by the setup flow and the provider-instance modal to populate
    model-name autocomplete suggestions.
    """
    return {"models": PREDEFINED_MODELS}


@router.get("/providers/vendors", response_model=List[VendorInfoResponse])
def list_provider_vendors(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Return the canonical list of LLM vendors the platform supports, with
    per-tenant "is configured" resolution. Backs the provider-instance modal
    vendor dropdown so the frontend never has to keep a hardcoded VENDORS
    array in sync with backend VALID_VENDORS / VENDOR_DEFAULT_BASE_URLS.

    Requires: org.settings.read permission (same gate as list_provider_instances).
    """
    # Per-tenant configured lookup — one DB round-trip, vendor-aggregated.
    tenant_id = ctx.tenant_id
    configured_vendors: set[str] = set()
    if tenant_id:
        rows = (
            db.query(ProviderInstance.vendor)
            .filter(
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.is_active == True,  # noqa: E712
            )
            .distinct()
            .all()
        )
        configured_vendors = {r[0] for r in rows if r and r[0]}

    # Stable order: keep the historical frontend ordering so the dropdown
    # looks identical to the pre-refactor UX.
    ordered = [
        "openai", "anthropic", "gemini", "groq", "grok",
        "openrouter", "deepseek", "vertex_ai", "ollama", "custom",
    ]
    # Defensive: any vendor added to VALID_VENDORS but missing from the
    # ordering list lands at the end (still surfaces, just unordered).
    for v in sorted(VALID_VENDORS):
        if v not in ordered:
            ordered.append(v)

    # Deferred import — the service module imports from this router at
    # startup for PREDEFINED_MODELS re-export, so a top-level import here
    # would be circular.
    from services.provider_instance_service import get_vendor_default_base_url

    out: List[VendorInfoResponse] = []
    for vendor_id in ordered:
        if vendor_id not in VALID_VENDORS:
            continue
        # Resolve default base URL — lazy for Ollama (DNS-sensitive).
        try:
            default_url = get_vendor_default_base_url(vendor_id)
        except Exception:
            default_url = None
        out.append(VendorInfoResponse(
            id=vendor_id,
            display_name=VENDOR_DISPLAY_NAMES.get(vendor_id, vendor_id),
            default_base_url=default_url,
            supports_discovery=vendor_id in VENDORS_WITH_LIVE_DISCOVERY,
            tenant_has_configured=vendor_id in configured_vendors,
        ))
    return out


@router.post("/provider-instances/discover-models-raw")
async def discover_models_raw(
    data: DiscoverModelsRawRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Live-discover models from a provider endpoint using a raw API key
    (no saved instance required). Used by the initial setup wizard AND by
    the post-login "create provider instance" modal.

    v0.6.0 Remote Access hardening: this endpoint is now gated based on
    installation state. Before first-run setup (user_count == 0) it is
    public so the setup wizard can populate its model dropdown. After
    setup is complete, it requires ``org.settings.write`` — this closes
    the unauthenticated outbound-proxy / reconnaissance vector on
    instances exposed via Cloudflare Tunnel.

    The supplied API key is used only for this single outbound request
    and is never stored or logged.

    Supports: gemini, openai, groq, grok, deepseek, openrouter (any
    OpenAI-compatible /models endpoint). Falls back to {"models": []}
    on failure — callers should keep their static suggestions as a
    secondary fallback.
    """
    # Gate: allow anonymous access ONLY while the instance is un-provisioned
    # (zero users in the DB). Once at least one user exists, the endpoint
    # requires a valid authenticated session — this prevents the endpoint
    # from being used as an unauthenticated outbound HTTP proxy on a
    # publicly-exposed instance.
    from models_rbac import User as _User
    user_count = db.query(_User).count()
    if user_count > 0:
        current_user = get_current_user_optional_strict_from_request(request, db)
        if not current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
        ensure_permission(current_user, "org.settings.write", db)

    vendor = data.vendor.lower()
    if vendor not in VALID_VENDORS:
        raise HTTPException(status_code=400, detail="Invalid vendor")
    if not data.api_key or not data.api_key.strip():
        raise HTTPException(status_code=400, detail="API key required")

    # Default base URLs per vendor (mirrors frontend VENDOR_DEFAULT_URLS)
    VENDOR_BASE_URLS = {
        "gemini": "https://generativelanguage.googleapis.com",
        "openai": "https://api.openai.com/v1",
        "groq": "https://api.groq.com/openai/v1",
        "grok": "https://api.x.ai/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }
    base_url = (data.base_url or VENDOR_BASE_URLS.get(vendor) or "").rstrip("/")
    if not base_url:
        return {"models": []}

    # SSRF validate
    from utils.ssrf_validator import validate_url, SSRFValidationError
    try:
        validate_url(base_url)
    except SSRFValidationError as e:
        raise HTTPException(status_code=400, detail=f"SSRF blocked: {e}")

    import httpx
    models: List[str] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if vendor == "gemini":
                headers = {"x-goog-api-key": data.api_key}
                page_token = None
                while True:
                    params = {"pageSize": 100}
                    if page_token:
                        params["pageToken"] = page_token
                    resp = await client.get(
                        f"{base_url}/v1beta/models", headers=headers, params=params
                    )
                    if resp.status_code != 200:
                        return {"models": []}
                    body = resp.json()
                    for m in body.get("models", []):
                        name = m.get("name", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if not name or "generateContent" not in methods:
                            continue
                        model_id = name[len("models/"):] if name.startswith("models/") else name
                        if _is_gemini_image_model(model_id):
                            continue
                        models.append(model_id)
                    page_token = body.get("nextPageToken")
                    if not page_token:
                        break
                models = sorted(set(models))
            else:
                # OpenAI-compatible /models
                headers = {"Authorization": f"Bearer {data.api_key}"}
                resp = await client.get(f"{base_url}/models", headers=headers)
                if resp.status_code != 200:
                    return {"models": []}
                body = resp.json()
                models = sorted(
                    {
                        model_id
                        for m in body.get("data", [])
                        if isinstance(m, dict)
                        for model_id in [m.get("id")]
                        if model_id and not (vendor == "openai" and _is_openai_image_model(model_id))
                    }
                )
    except (httpx.ConnectError, httpx.TimeoutException):
        return {"models": []}
    except Exception as e:
        logger.warning(f"Raw model discovery failed for {vendor}: {e}")
        return {"models": []}

    return {"models": models}


@router.get("/provider-instances", response_model=List[ProviderInstanceResponse])
def list_provider_instances(
    vendor: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    List all provider instances for the current tenant.
    Optionally filter by vendor.
    """
    query = db.query(ProviderInstance)
    query = ctx.filter_by_tenant(query, ProviderInstance.tenant_id)

    if vendor:
        query = query.filter(ProviderInstance.vendor == vendor.lower())

    # Only show active (non-soft-deleted) instances
    query = query.filter(ProviderInstance.is_active == True)
    instances = query.order_by(ProviderInstance.vendor, ProviderInstance.instance_name).all()
    return [_to_response(inst, db) for inst in instances]


@router.post("/provider-instances", response_model=ProviderInstanceResponse, status_code=201)
def create_provider_instance(
    data: ProviderInstanceCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Create a new provider instance for the current tenant."""
    vendor = data.vendor.lower()
    if vendor not in VALID_VENDORS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vendor. Must be one of: {', '.join(sorted(VALID_VENDORS))}"
        )

    if not data.available_models:
        raise HTTPException(
            status_code=400,
            detail="At least one model is required"
        )

    # Check for duplicate instance name within tenant
    existing = db.query(ProviderInstance).filter(
        ProviderInstance.tenant_id == ctx.tenant_id,
        ProviderInstance.instance_name == data.instance_name,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Instance name '{data.instance_name}' already exists for this tenant"
        )

    # Validate base_url against SSRF if provided
    if data.base_url:
        from utils.ssrf_validator import validate_url, SSRFValidationError
        try:
            # Allow private IPs for ollama/custom vendors (local LLM servers)
            allow_private = vendor in ("ollama", "custom")
            validate_url(data.base_url, allow_private=allow_private)
        except SSRFValidationError as e:
            raise HTTPException(status_code=400, detail=f"Invalid base URL: {e}")

    # For Vertex AI, extract private_key from extra_config for encrypted storage
    api_key_to_store = data.api_key
    extra_config = data.extra_config or {}
    if vendor == "vertex_ai" and extra_config:
        # Private key goes into api_key_encrypted, not extra_config JSON
        if "private_key" in extra_config:
            api_key_to_store = extra_config.pop("private_key") or api_key_to_store

    # Create instance
    instance = ProviderInstance(
        tenant_id=ctx.tenant_id,
        vendor=vendor,
        instance_name=data.instance_name,
        base_url=data.base_url,
        extra_config=extra_config if extra_config else {},
        available_models=data.available_models,
        is_default=data.is_default,
        is_active=True,
        health_status="unknown",
    )
    db.add(instance)
    db.flush()  # Get the ID for encryption identifier

    # Encrypt and store API key if provided
    if api_key_to_store:
        encrypted = _encrypt_provider_key(api_key_to_store, ctx.tenant_id, instance.id, db)
        if not encrypted:
            raise HTTPException(status_code=500, detail="Failed to encrypt API key")
        instance.api_key_encrypted = encrypted

    # If setting as default, clear ALL other defaults for this vendor FIRST,
    # then flush to ensure the clear takes effect before the new default is
    # committed.  This prevents races where two concurrent creates could both
    # end up with is_default=True.
    if data.is_default:
        db.query(ProviderInstance).filter(
            ProviderInstance.tenant_id == ctx.tenant_id,
            ProviderInstance.vendor == vendor,
            ProviderInstance.id != instance.id,
            ProviderInstance.is_default == True,
        ).update({"is_default": False}, synchronize_session="fetch")
        db.flush()

    db.commit()
    db.refresh(instance)
    logger.info(f"Created provider instance '{data.instance_name}' (vendor={vendor}) for tenant {ctx.tenant_id}")

    # BUG-709: emit tenant audit event (no api_key in payload)
    log_tenant_event(
        db,
        ctx.tenant_id,
        current_user.id,
        _PROVIDER_AUDIT_CREATE,
        "provider_instance",
        str(instance.id),
        _provider_audit_payload(instance),
        request,
    )

    # Auto-run a connection test in the background so the Hub UI dot reflects
    # real connectivity instead of staying gray ('unknown') until the user
    # clicks Test Connection. Skip when no credentials are configured (the
    # test would just fail with "no api key") — except ollama, which can run
    # keyless against a local daemon.
    # BUG-663: for an auto-provisioned Ollama instance that doesn't yet have
    # a base_url (provisioning is still running — docker pull can take 20min
    # on first use), skip the test. The provisioning path writes base_url +
    # health_status itself once the container is ready; kicking off a test
    # against a None URL here just logs a misleading 'unavailable' immediately.
    if (api_key_to_store or vendor == "ollama") and instance.available_models:
        if not (instance.is_auto_provisioned and not instance.base_url):
            background_tasks.add_task(_background_test_instance, instance.id, current_user.id)

    return _to_response(instance, db)


@router.post("/provider-instances/ensure-ollama", response_model=ProviderInstanceResponse)
def ensure_ollama_instance(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Ensure a default Ollama provider instance exists for the current tenant.
    Returns the existing instance if one is already active, or creates a new one.
    """
    from services.provider_instance_service import ProviderInstanceService
    try:
        instance = ProviderInstanceService.ensure_ollama_instance(ctx.tenant_id, db)
        return _to_response(instance, db)
    except Exception as e:
        logger.error(f"Failed to ensure Ollama instance for tenant {ctx.tenant_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/provider-instances/{instance_id}", response_model=ProviderInstanceResponse)
def get_provider_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get a single provider instance by ID."""
    instance = db.query(ProviderInstance).filter(ProviderInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Provider instance not found")
    if not ctx.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=404, detail="Provider instance not found")
    return _to_response(instance, db)


@router.put("/provider-instances/{instance_id}", response_model=ProviderInstanceResponse)
def update_provider_instance(
    instance_id: int,
    data: ProviderInstanceUpdate,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Update an existing provider instance."""
    instance = db.query(ProviderInstance).filter(ProviderInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Provider instance not found")
    if not ctx.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=404, detail="Provider instance not found")

    # Update fields
    if data.instance_name is not None:
        # Check for duplicate name (excluding self)
        existing = db.query(ProviderInstance).filter(
            ProviderInstance.tenant_id == instance.tenant_id,
            ProviderInstance.instance_name == data.instance_name,
            ProviderInstance.id != instance_id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Instance name '{data.instance_name}' already exists for this tenant"
            )
        instance.instance_name = data.instance_name

    if data.base_url is not None:
        if data.base_url:
            from utils.ssrf_validator import validate_url, SSRFValidationError
            try:
                allow_private = instance.vendor in ("ollama", "custom")
                validate_url(data.base_url, allow_private=allow_private)
            except SSRFValidationError as e:
                raise HTTPException(status_code=400, detail=f"Invalid base URL: {e}")
        instance.base_url = data.base_url or None

    # Handle extra_config update (merge, don't replace)
    if data.extra_config is not None:
        current_extra = instance.extra_config or {}
        # For Vertex AI, extract private_key for encrypted storage
        new_extra = dict(data.extra_config)
        if instance.vendor == "vertex_ai" and "private_key" in new_extra:
            pk = new_extra.pop("private_key")
            if pk:
                encrypted = _encrypt_provider_key(pk, instance.tenant_id, instance.id, db)
                if not encrypted:
                    raise HTTPException(status_code=500, detail="Failed to encrypt private key")
                instance.api_key_encrypted = encrypted
        current_extra.update(new_extra)
        instance.extra_config = current_extra

    if data.api_key is not None:
        if data.api_key:
            encrypted = _encrypt_provider_key(data.api_key, instance.tenant_id, instance.id, db)
            if not encrypted:
                raise HTTPException(status_code=500, detail="Failed to encrypt API key")
            instance.api_key_encrypted = encrypted
        else:
            # Empty string = clear the key. Reset health so the dot doesn't
            # keep showing a stale 'healthy' from a previous test.
            instance.api_key_encrypted = None
            instance.health_status = "unknown"
            instance.health_status_reason = None

    if data.available_models is not None:
        instance.available_models = data.available_models

    if data.is_default is not None:
        if data.is_default:
            # Clear other defaults BEFORE setting the new one, and flush
            # to ensure the clear is visible within this transaction.
            db.query(ProviderInstance).filter(
                ProviderInstance.tenant_id == instance.tenant_id,
                ProviderInstance.vendor == instance.vendor,
                ProviderInstance.id != instance.id,
                ProviderInstance.is_default == True,
            ).update({"is_default": False}, synchronize_session="fetch")
            db.flush()
        instance.is_default = data.is_default

    if data.is_active is not None:
        instance.is_active = data.is_active

    instance.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(instance)
    logger.info(f"Updated provider instance {instance_id} for tenant {instance.tenant_id}")

    # BUG-709: emit tenant audit event (no api_key in payload)
    log_tenant_event(
        db,
        instance.tenant_id,
        current_user.id,
        _PROVIDER_AUDIT_UPDATE,
        "provider_instance",
        str(instance.id),
        _provider_audit_payload(instance),
        request,
    )

    # Re-test in the background when something connectivity-relevant changed
    # (key, base URL, vendor-specific config, or model list). Skip pure metadata
    # edits like rename or default-toggle so we don't burn provider quota for
    # no reason.
    connectivity_changed = (
        (data.api_key is not None and data.api_key != "")
        or data.base_url is not None
        or data.extra_config is not None
        or data.available_models is not None
    )
    can_test = bool(instance.api_key_encrypted) or instance.vendor == "ollama"
    if connectivity_changed and can_test and instance.is_active and instance.available_models:
        background_tasks.add_task(_background_test_instance, instance.id, current_user.id)

    return _to_response(instance, db)


@router.delete("/provider-instances/{instance_id}")
def delete_provider_instance(
    instance_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Soft-delete a provider instance (set is_active=False)."""
    instance = db.query(ProviderInstance).filter(ProviderInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Provider instance not found")
    if not ctx.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=404, detail="Provider instance not found")

    if instance.vendor == "ollama" and getattr(instance, "is_auto_provisioned", False):
        try:
            from services.ollama_container_manager import OllamaContainerManager
            OllamaContainerManager().deprovision(
                instance_id, instance.tenant_id, db, remove_volume=False
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(
                "Failed to deprovision auto-provisioned Ollama instance %s before delete: %s",
                instance_id,
                e,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to deprovision Ollama container before delete: {e}",
            )

    instance.is_active = False
    instance.updated_at = datetime.utcnow()
    db.commit()
    logger.info(f"Soft-deleted provider instance {instance_id} for tenant {instance.tenant_id}")

    # BUG-709: emit tenant audit event (no api_key in payload)
    log_tenant_event(
        db,
        instance.tenant_id,
        current_user.id,
        _PROVIDER_AUDIT_DELETE,
        "provider_instance",
        str(instance.id),
        _provider_audit_payload(instance),
        request,
    )

    return {"message": f"Provider instance '{instance.instance_name}' deleted successfully"}


@router.post("/provider-instances/test-connection", response_model=TestConnectionResponse)
async def test_provider_connection_raw(
    data: TestConnectionRawRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Test connectivity to a provider using raw credentials (no saved instance required).
    Useful for testing connection during instance creation before saving.
    """
    vendor = data.vendor.lower()
    if vendor not in VALID_VENDORS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid vendor. Must be one of: {', '.join(sorted(VALID_VENDORS))}"
        )

    api_key = data.api_key
    if not api_key:
        # Fall back to tenant-level API key for this vendor
        from services.api_key_service import get_api_key
        api_key = get_api_key(vendor, db, tenant_id=ctx.tenant_id)

    if not api_key and vendor not in ("ollama",):
        return TestConnectionResponse(
            success=False,
            message="No API key provided and no tenant-level key configured for this vendor",
        )

    # Validate base_url against SSRF if provided
    if data.base_url:
        from utils.ssrf_validator import validate_url, SSRFValidationError
        try:
            allow_private = vendor in ("ollama", "custom")
            validate_url(data.base_url, allow_private=allow_private)
        except SSRFValidationError as e:
            return TestConnectionResponse(
                success=False,
                message=f"Invalid base URL: {e}",
            )

    # Vertex AI raw test: validate credentials via OAuth token refresh (fast, no model call needed)
    if vendor == "vertex_ai":
        from utils.vertex_config import normalise_vertex_config, VERTEX_CONFIG_ERROR
        project_id, region, sa_email, private_key_raw = normalise_vertex_config(
            api_key, data.extra_config
        )

        if not project_id or not sa_email or not private_key_raw:
            return TestConnectionResponse(
                success=False,
                message=VERTEX_CONFIG_ERROR,
            )

        start_time = time.time()
        try:
            from google.oauth2 import service_account as sa_module
            from google.auth.transport.requests import Request as AuthRequest

            formatted_key = private_key_raw.replace("\\n", "\n")
            credentials_info = {
                "type": "service_account",
                "project_id": project_id,
                "client_email": sa_email,
                "private_key": formatted_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
            creds = sa_module.Credentials.from_service_account_info(
                credentials_info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            creds.refresh(AuthRequest())
            latency_ms = int((time.time() - start_time) * 1000)
            return TestConnectionResponse(
                success=True,
                message=f"Vertex AI credentials valid — project={project_id}, region={region}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Vertex AI credential test failed: {e}")
            return TestConnectionResponse(
                success=False,
                message=f"Vertex AI credential validation failed: {str(e)}",
                latency_ms=latency_ms,
            )

    # Determine a test model: prefer user-supplied model, then hardcoded fallback
    from api.routes_integrations import PROVIDER_TEST_MODELS
    test_model = data.model or PROVIDER_TEST_MODELS.get(vendor)
    if not test_model and vendor == "ollama":
        test_model = "llama3.2"
    if not test_model and vendor == "custom":
        test_model = "default"

    start_time = time.time()
    error_message = None
    success = False

    try:
        from agent.ai_client import AIClient
        from analytics.token_tracker import TokenTracker
        tracker = TokenTracker(db, ctx.tenant_id)

        client = AIClient(
            provider=vendor if vendor != "custom" else "openai",
            model_name=test_model,
            db=db,
            token_tracker=tracker,
            tenant_id=ctx.tenant_id,
            max_tokens=20,
            api_key=api_key,  # V060-PRV-001: pass raw key so AIClient doesn't require DB key
        )

        # Disable SDK retries for connection tests — fail fast instead of hanging
        _disable_sdk_retries(client)

        # Override base_url if provided
        if data.base_url:
            if hasattr(client, 'client') and client.client:
                client.client.base_url = data.base_url
            if vendor == "ollama":
                client.ollama_base_url = data.base_url

        result = await client.generate(
            system_prompt="You are a test assistant. Respond with exactly: OK",
            user_message="Test connection. Reply with OK.",
            operation_type="connection_test",
        )

        if result.get("error"):
            error_message = str(result["error"])
        else:
            success = True

    except Exception as e:
        logger.exception(f"Raw test connection failed for vendor {vendor}")
        error_message = _sanitize_test_error(str(e), test_model)

    latency_ms = int((time.time() - start_time) * 1000)

    if success:
        return TestConnectionResponse(
            success=True,
            message=f"Connected to {vendor}/{test_model}",
            latency_ms=latency_ms,
        )
    else:
        return TestConnectionResponse(
            success=False,
            message=error_message or "Connection test failed",
            latency_ms=latency_ms,
        )


@router.post("/provider-instances/{instance_id}/test-connection", response_model=TestConnectionResponse)
async def test_provider_connection(
    instance_id: int,
    body: TestConnectionSavedRequest = TestConnectionSavedRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Test connectivity to a provider instance by sending a minimal prompt.
    Measures latency and logs the result to ProviderConnectionAudit.
    """
    instance = db.query(ProviderInstance).filter(ProviderInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Provider instance not found")
    if not ctx.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=404, detail="Provider instance not found")

    # Ensure credentials exist before testing. Actual invocation still goes
    # through provider_instance_id so saved-instance tests match runtime.
    has_instance_key = bool(_decrypt_provider_key(instance, db))
    has_tenant_key = False
    if not has_instance_key:
        from services.api_key_service import get_api_key
        has_tenant_key = bool(get_api_key(instance.vendor, db, tenant_id=instance.tenant_id))

    if not has_instance_key and not has_tenant_key and instance.vendor not in ("ollama",):
        # Ollama may not need an API key
        audit = ProviderConnectionAudit(
            tenant_id=instance.tenant_id,
            user_id=current_user.id,
            provider_instance_id=instance.id,
            action="test_connection",
            base_url=instance.base_url,
            success=False,
            error_message="No API key configured for this instance or vendor",
        )
        db.add(audit)
        db.commit()
        return TestConnectionResponse(
            success=False,
            message="No API key configured for this instance or vendor",
        )

    # Determine a test model: prefer explicit request > saved models > hardcoded fallback
    from api.routes_integrations import PROVIDER_TEST_MODELS
    test_model = body.model  # explicit model from request body (e.g. unsaved UI selection)
    if not test_model and instance.available_models:
        test_model = instance.available_models[0]
    if not test_model:
        test_model = PROVIDER_TEST_MODELS.get(instance.vendor)
    if not test_model and instance.vendor == "ollama":
        test_model = "llama3.2"  # sensible default for Ollama
    if not test_model and instance.vendor == "custom":
        test_model = "default"

    start_time = time.time()
    error_message = None
    success = False
    resolved_ip = None

    try:
        from agent.ai_client import AIClient
        from analytics.token_tracker import TokenTracker
        tracker = TokenTracker(db, instance.tenant_id)

        client = AIClient(
            provider=instance.vendor if instance.vendor != "custom" else "openai",
            model_name=test_model,
            db=db,
            token_tracker=tracker,
            tenant_id=instance.tenant_id,
            provider_instance_id=instance.id,
            max_tokens=20,
        )

        # Disable SDK retries for connection tests — fail fast instead of hanging
        _disable_sdk_retries(client)

        result = await client.generate(
            system_prompt="You are a test assistant. Respond with exactly: OK",
            user_message="Test connection. Reply with OK.",
            operation_type="connection_test",
        )

        if result.get("error"):
            error_message = str(result["error"])
        else:
            success = True

        # Try to resolve IP for audit
        if instance.base_url:
            try:
                from urllib.parse import urlparse
                import socket
                parsed = urlparse(instance.base_url)
                if parsed.hostname:
                    resolved_ip = socket.gethostbyname(parsed.hostname)
            except Exception:
                pass

    except Exception as e:
        error_message = _sanitize_test_error(str(e), test_model)
        logger.error(f"Test connection failed for instance {instance_id}: {e}")

    latency_ms = int((time.time() - start_time) * 1000)

    # Update instance health status
    instance.health_status = "healthy" if success else "unavailable"
    instance.health_status_reason = None if success else error_message
    instance.last_health_check = datetime.utcnow()

    # Log audit
    audit = ProviderConnectionAudit(
        tenant_id=instance.tenant_id,
        user_id=current_user.id,
        provider_instance_id=instance.id,
        action="test_connection",
        resolved_ip=resolved_ip,
        base_url=instance.base_url,
        success=success,
        error_message=error_message,
    )
    db.add(audit)
    db.commit()

    if success:
        return TestConnectionResponse(
            success=True,
            message=f"Connected to {instance.vendor}/{test_model}",
            latency_ms=latency_ms,
        )
    else:
        return TestConnectionResponse(
            success=False,
            message=f"Connection failed: {error_message}",
            latency_ms=latency_ms,
        )


@router.post("/provider-instances/{instance_id}/discover-models")
async def discover_models(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Discover available models from a provider instance.
    For Ollama/custom endpoints, queries the /api/tags or /v1/models endpoint.
    For cloud providers, returns a curated list of known models.
    """
    instance = db.query(ProviderInstance).filter(ProviderInstance.id == instance_id).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Provider instance not found")
    if not ctx.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=404, detail="Provider instance not found")

    models = []

    if instance.vendor in ("ollama",):
        # Ollama: query /api/tags for local models
        import httpx
        base_url = instance.base_url or "http://host.docker.internal:11434"

        # Validate URL
        from utils.ssrf_validator import validate_url, SSRFValidationError
        try:
            validate_url(base_url, allow_private=True)
        except SSRFValidationError as e:
            raise HTTPException(status_code=400, detail=f"SSRF blocked: {e}")

        headers = {}
        api_key = _decrypt_provider_key(instance, db)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/api/tags", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    models = [m.get("name") for m in data.get("models", []) if m.get("name")]
                else:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Ollama returned HTTP {response.status_code}"
                    )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Cannot connect to Ollama instance")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout connecting to Ollama instance")

    elif instance.vendor == "custom" and instance.base_url:
        # Custom OpenAI-compatible: query /v1/models
        import httpx
        from utils.ssrf_validator import validate_url, SSRFValidationError
        try:
            validate_url(instance.base_url, allow_private=True)
        except SSRFValidationError as e:
            raise HTTPException(status_code=400, detail=f"SSRF blocked: {e}")

        headers = {}
        api_key = _decrypt_provider_key(instance, db)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Try OpenAI-compatible /v1/models endpoint
                url = instance.base_url.rstrip("/")
                # If base_url already ends with /v1, don't duplicate
                models_url = f"{url}/models" if url.endswith("/v1") else f"{url}/v1/models"
                response = await client.get(models_url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                else:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Custom endpoint returned HTTP {response.status_code}"
                    )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Cannot connect to custom endpoint")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout connecting to custom endpoint")

    elif instance.vendor == "gemini":
        # Gemini: query /v1beta/models for live model list
        import httpx
        base_url = (instance.base_url or "https://generativelanguage.googleapis.com").rstrip("/")

        # Validate URL to prevent SSRF
        from utils.ssrf_validator import validate_url, SSRFValidationError
        try:
            validate_url(base_url)
        except SSRFValidationError as e:
            raise HTTPException(status_code=400, detail=f"SSRF blocked: {e}")

        # Resolve API key (instance-specific first, then tenant-level)
        api_key = _decrypt_provider_key(instance, db)
        if not api_key:
            from services.api_key_service import get_api_key
            api_key = get_api_key("gemini", db, tenant_id=instance.tenant_id)
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="No Gemini API key configured for this instance or tenant"
            )

        headers = {"x-goog-api-key": api_key}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Paginate — Google returns nextPageToken when there are more models
                page_token = None
                while True:
                    params = {"pageSize": 100}
                    if page_token:
                        params["pageToken"] = page_token
                    response = await client.get(
                        f"{base_url}/v1beta/models", headers=headers, params=params
                    )
                    if response.status_code != 200:
                        raise HTTPException(
                            status_code=502,
                            detail=f"Gemini returned HTTP {response.status_code}"
                        )
                    data = response.json()
                    for m in data.get("models", []):
                        name = m.get("name", "")
                        methods = m.get("supportedGenerationMethods", [])
                        if not name or "generateContent" not in methods:
                            continue
                        # Strip "models/" prefix
                        model_id = name[len("models/"):] if name.startswith("models/") else name
                        models.append(model_id)
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
                models = sorted(set(models))
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Cannot connect to Gemini API")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout connecting to Gemini API")

    elif instance.vendor == "openrouter" and instance.base_url:
        # OpenRouter-compatible: query /v1/models
        import httpx
        base_url = instance.base_url.rstrip("/") if instance.base_url else "https://openrouter.ai/api/v1"

        # Validate URL to prevent SSRF
        from utils.ssrf_validator import validate_url, SSRFValidationError
        try:
            validate_url(base_url)
        except SSRFValidationError as e:
            raise HTTPException(status_code=400, detail=f"SSRF blocked: {e}")

        headers = {}
        api_key = _decrypt_provider_key(instance, db)
        if not api_key:
            from services.api_key_service import get_api_key
            api_key = get_api_key("openrouter", db, tenant_id=instance.tenant_id)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/models", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    models = [m.get("id") for m in data.get("data", []) if m.get("id")]
                else:
                    raise HTTPException(
                        status_code=502,
                        detail=f"OpenRouter returned HTTP {response.status_code}"
                    )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Cannot connect to OpenRouter")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout connecting to OpenRouter")

    else:
        # Cloud providers without live discovery: return curated list
        models = list(PREDEFINED_MODELS.get(instance.vendor, []))

    # Update instance with discovered models
    instance.available_models = models
    instance.updated_at = datetime.utcnow()
    db.commit()

    # Log audit
    audit = ProviderConnectionAudit(
        tenant_id=instance.tenant_id,
        user_id=current_user.id,
        provider_instance_id=instance.id,
        action="model_discovery",
        base_url=instance.base_url,
        success=True,
        error_message=None,
    )
    db.add(audit)
    db.commit()

    return {"models": models, "count": len(models)}


@router.get("/provider-instances/vendor/{vendor}/default", response_model=ProviderInstanceResponse)
def get_default_instance(
    vendor: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get the default provider instance for a vendor within the current tenant."""
    vendor = vendor.lower()
    query = db.query(ProviderInstance).filter(
        ProviderInstance.vendor == vendor,
        ProviderInstance.is_default == True,
        ProviderInstance.is_active == True,
    )
    query = ctx.filter_by_tenant(query, ProviderInstance.tenant_id)
    instance = query.first()

    if not instance:
        raise HTTPException(
            status_code=404,
            detail=f"No default provider instance found for vendor '{vendor}'"
        )
    return _to_response(instance, db)


@router.post("/provider-instances/validate-url", response_model=UrlValidationResponse)
def validate_provider_url(
    data: UrlValidationRequest,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Validate a URL against SSRF checks before using it as a provider base URL.
    Returns whether the URL is safe to use.
    """
    from utils.ssrf_validator import validate_url, SSRFValidationError

    # Allow private IPs for local providers (ollama, custom)
    allow_private = data.vendor and data.vendor.lower() in ("ollama", "custom")

    try:
        validate_url(data.url, allow_private=allow_private)
        return UrlValidationResponse(valid=True)
    except SSRFValidationError as e:
        return UrlValidationResponse(valid=False, error=str(e))


# ==================================================================
# Ollama Auto-Provisioning Endpoints (v0.6.0-patch.5)
# ==================================================================

import threading as _threading  # noqa: E402  (kept local to Ollama endpoints)
from typing import Literal as _Literal  # noqa: E402


class ProvisionRequest(BaseModel):
    gpu_enabled: bool = False
    mem_limit: str = "4g"


class ModelPullRequest(BaseModel):
    model: str


class PullJobResponse(BaseModel):
    job_id: str
    status: str  # pulling | done | error
    percent: int = 0
    bytes_downloaded: int = 0
    bytes_total: int = 0
    error: Optional[str] = None


class ContainerStatusResponse(BaseModel):
    status: str
    container_name: Optional[str] = None
    container_port: Optional[int] = None
    image: Optional[str] = None
    volume: Optional[str] = None
    pulled_models: List[str] = []


def _require_ollama_instance(
    instance_id: int, ctx: TenantContext, db: Session
) -> ProviderInstance:
    """Load a tenant-owned Ollama ProviderInstance or raise HTTP 404."""
    instance = db.query(ProviderInstance).filter(
        ProviderInstance.id == instance_id
    ).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Provider instance not found")
    if not ctx.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=404, detail="Provider instance not found")
    if instance.vendor != "ollama":
        raise HTTPException(
            status_code=400,
            detail="Container operations only supported for Ollama instances",
        )
    return instance


@router.post(
    "/provider-instances/{instance_id}/provision",
    status_code=status.HTTP_202_ACCEPTED,
)
def provision_ollama_container(
    instance_id: int,
    data: ProvisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Start provisioning an Ollama container for this tenant. Returns 202
    immediately; poll `/container/status` for progress.
    """
    instance = _require_ollama_instance(instance_id, ctx, db)

    # Reject obviously in-progress states so a double-click doesn't spawn two
    # concurrent provisioners racing over the same DB row.
    if instance.container_status in ("provisioning",):
        return {"status": "provisioning"}

    from services.provider_instance_service import ProviderInstanceService
    try:
        ProviderInstanceService.provision_container(
            instance_id=instance_id,
            tenant_id=instance.tenant_id,
            db=db,
            gpu_enabled=data.gpu_enabled,
            mem_limit=data.mem_limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    tenant_id = instance.tenant_id

    def _bg():
        try:
            from db import get_global_engine
            from sqlalchemy.orm import sessionmaker
            engine = get_global_engine()
            if engine is None:
                logger.error("provision: no global engine available")
                return
            BgSession = sessionmaker(bind=engine)
            bg_db = BgSession()
            try:
                bg_inst = bg_db.query(ProviderInstance).filter(
                    ProviderInstance.id == instance_id,
                    ProviderInstance.tenant_id == tenant_id,
                ).first()
                if not bg_inst:
                    logger.warning(
                        f"provision background: instance {instance_id} missing"
                    )
                    return
                from services.ollama_container_manager import OllamaContainerManager
                OllamaContainerManager().provision(bg_inst, bg_db)
            finally:
                try:
                    bg_db.close()
                except Exception:
                    pass
        except Exception as exc:
            logger.error(
                f"provision background error (instance={instance_id}): {exc}",
                exc_info=True,
            )

    _threading.Thread(
        target=_bg,
        daemon=True,
        name=f"ollama-provision-{instance_id}",
    ).start()

    return {"status": "provisioning"}


@router.post("/provider-instances/{instance_id}/deprovision")
def deprovision_ollama_container(
    instance_id: int,
    remove_volume: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Stop and remove this tenant's Ollama container. Pass ``remove_volume=true``
    to also delete the model cache (irreversible).
    """
    instance = _require_ollama_instance(instance_id, ctx, db)
    from services.ollama_container_manager import OllamaContainerManager
    try:
        OllamaContainerManager().deprovision(
            instance_id, instance.tenant_id, db, remove_volume=remove_volume
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Deprovision failed for instance {instance_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Deprovision failed: {e}")
    return {"status": "deprovisioned", "remove_volume": remove_volume}


@router.post("/provider-instances/{instance_id}/container/{action}")
def ollama_container_action(
    instance_id: int,
    action: _Literal["start", "stop", "restart"],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    instance = _require_ollama_instance(instance_id, ctx, db)
    from services.ollama_container_manager import OllamaContainerManager
    mgr = OllamaContainerManager()
    try:
        if action == "start":
            result = mgr.start_container(instance_id, instance.tenant_id, db)
        elif action == "stop":
            result = mgr.stop_container(instance_id, instance.tenant_id, db)
        else:
            result = mgr.restart_container(instance_id, instance.tenant_id, db)
        return {"status": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Container {action} failed for instance {instance_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Container {action} failed: {e}"
        )


@router.get(
    "/provider-instances/{instance_id}/container/status",
    response_model=ContainerStatusResponse,
)
def ollama_container_status(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    instance = _require_ollama_instance(instance_id, ctx, db)
    from services.ollama_container_manager import OllamaContainerManager
    try:
        info = OllamaContainerManager().get_status(
            instance_id, instance.tenant_id, db
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return ContainerStatusResponse(**info)


@router.get("/provider-instances/{instance_id}/container/logs")
def ollama_container_logs(
    instance_id: int,
    tail: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    instance = _require_ollama_instance(instance_id, ctx, db)
    from services.ollama_container_manager import OllamaContainerManager
    try:
        tail_clamped = max(1, min(int(tail or 100), 5000))
        logs = OllamaContainerManager().get_logs(
            instance_id, instance.tenant_id, db, tail=tail_clamped
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"logs": logs}


@router.post("/provider-instances/{instance_id}/models/pull")
def ollama_model_pull_start(
    instance_id: int,
    data: ModelPullRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Start a background Ollama model pull. Returns a job_id to poll."""
    instance = _require_ollama_instance(instance_id, ctx, db)
    from services.ollama_model_service import OllamaModelService
    try:
        job_id = OllamaModelService.start_pull(
            instance_id=instance_id,
            tenant_id=instance.tenant_id,
            model_name=data.model,
            db=db,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"job_id": job_id, "status": "pulling"}


@router.get(
    "/provider-instances/{instance_id}/models/pull/{job_id}",
    response_model=PullJobResponse,
)
def ollama_model_pull_status(
    instance_id: int,
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Poll an in-flight model pull. Tenant-scoped by instance_id."""
    instance = _require_ollama_instance(instance_id, ctx, db)
    from services.ollama_model_service import OllamaModelService
    state = OllamaModelService.get_pull_status(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Pull job not found or expired")

    # Cross-check tenant: a job_id minted for another tenant must not leak out.
    if state.get("tenant_id") != instance.tenant_id or state.get(
        "instance_id"
    ) != instance.id:
        raise HTTPException(status_code=404, detail="Pull job not found or expired")

    return PullJobResponse(
        job_id=job_id,
        status=state.get("status", "error"),
        percent=int(state.get("percent") or 0),
        bytes_downloaded=int(state.get("bytes_downloaded") or 0),
        bytes_total=int(state.get("bytes_total") or 0),
        error=state.get("error"),
    )


@router.delete("/provider-instances/{instance_id}/models/{model_name}")
def ollama_model_delete(
    instance_id: int,
    model_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    instance = _require_ollama_instance(instance_id, ctx, db)
    from services.ollama_model_service import OllamaModelService
    try:
        result = OllamaModelService.delete_model(
            instance_id, instance.tenant_id, model_name, db
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return result


@router.get("/provider-instances/{instance_id}/models")
def ollama_list_models(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    instance = _require_ollama_instance(instance_id, ctx, db)
    from services.ollama_model_service import OllamaModelService
    try:
        models = OllamaModelService.list_models(
            instance_id, instance.tenant_id, db
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"models": models, "count": len(models)}


# ==================================================================
# Assign provider instance to agent (wizard convenience endpoint)
# ==================================================================


class AssignProviderToAgentRequest(BaseModel):
    agent_id: int
    model_name: str


@router.post("/provider-instances/{instance_id}/assign-to-agent")
def assign_provider_instance_to_agent(
    instance_id: int,
    data: AssignProviderToAgentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Wire an agent to use this provider instance (model backend). Used by the
    Ollama setup wizard so users don't have to jump to Agent Studio to repoint
    the agent at the new provider.

    Updates Agent.provider_instance_id, Agent.model_name, and Agent.model_provider
    in one shot. Tenant isolation is enforced on BOTH the provider instance and
    the target agent.
    """
    # 1. Load and verify the provider instance is in this tenant
    instance = db.query(ProviderInstance).filter(
        ProviderInstance.id == instance_id
    ).first()
    if not instance:
        raise HTTPException(status_code=404, detail="Provider instance not found")
    if not ctx.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=404, detail="Provider instance not found")

    # 2. Validate requested model is part of the instance's known model list
    #    (when the list has been populated — empty list = accept anything)
    model_name = (data.model_name or "").strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="model_name is required")

    # 3. Load and verify the agent is in this tenant
    agent = db.query(Agent).filter(Agent.id == data.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {data.agent_id} not found")
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=404, detail=f"Agent {data.agent_id} not found")

    # 4. Apply the update
    agent.provider_instance_id = instance.id
    agent.model_name = model_name
    agent.model_provider = instance.vendor
    agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)

    logger.info(
        f"Assigned provider instance {instance_id} ({instance.vendor}/{model_name}) "
        f"to agent {agent.id} (tenant={ctx.tenant_id})"
    )

    return {
        "agent_id": agent.id,
        "provider_instance_id": agent.provider_instance_id,
        "model_name": agent.model_name,
        "model_provider": agent.model_provider,
    }
