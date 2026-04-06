"""
Phase 21: Provider Instance Management API Routes

Provides CRUD endpoints for multi-instance LLM provider configuration,
connection testing, model discovery, and URL validation.
Each tenant can manage multiple provider instances (e.g., multiple OpenAI-compatible
servers, Ollama instances, or custom LLM gateways).
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging
import time

from models import ProviderInstance, ProviderConnectionAudit
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
)

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


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None


class TestConnectionRawRequest(BaseModel):
    vendor: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None  # Model to test — avoids relying on hardcoded fallback


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


# ==================== Helpers ====================

VALID_VENDORS = {"openai", "anthropic", "gemini", "groq", "grok", "deepseek", "openrouter", "ollama", "vertex_ai", "custom"}


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
    "anthropic": [
        "claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5",
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
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


@router.post("/provider-instances/discover-models-raw")
async def discover_models_raw(data: DiscoverModelsRawRequest):
    """
    Live-discover models from a provider endpoint using a raw API key
    (no saved instance required). Public endpoint — intended to be called
    during setup and during pre-save modal configuration, so the model
    dropdown reflects what the provider actually exposes right now.

    The supplied API key is used only for this single outbound request
    and is never stored or logged.

    Supports: gemini, openai, groq, grok, deepseek, openrouter (any
    OpenAI-compatible /models endpoint). Falls back to {"models": []}
    on failure — callers should keep their static suggestions as a
    secondary fallback.
    """
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
                    {m.get("id") for m in body.get("data", []) if isinstance(m, dict) and m.get("id")}
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

    # If setting as default, unset other defaults for this vendor
    if data.is_default:
        db.query(ProviderInstance).filter(
            ProviderInstance.tenant_id == ctx.tenant_id,
            ProviderInstance.vendor == vendor,
            ProviderInstance.id != instance.id,
        ).update({"is_default": False})

    db.commit()
    db.refresh(instance)
    logger.info(f"Created provider instance '{data.instance_name}' (vendor={vendor}) for tenant {ctx.tenant_id}")
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
            # Empty string = clear the key
            instance.api_key_encrypted = None

    if data.available_models is not None:
        instance.available_models = data.available_models

    if data.is_default is not None:
        instance.is_default = data.is_default
        if data.is_default:
            # Unset other defaults for this vendor
            db.query(ProviderInstance).filter(
                ProviderInstance.tenant_id == instance.tenant_id,
                ProviderInstance.vendor == instance.vendor,
                ProviderInstance.id != instance.id,
            ).update({"is_default": False})

    if data.is_active is not None:
        instance.is_active = data.is_active

    instance.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(instance)
    logger.info(f"Updated provider instance {instance_id} for tenant {instance.tenant_id}")
    return _to_response(instance, db)


@router.delete("/provider-instances/{instance_id}")
def delete_provider_instance(
    instance_id: int,
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

    instance.is_active = False
    instance.updated_at = datetime.utcnow()
    db.commit()
    logger.info(f"Soft-deleted provider instance {instance_id} for tenant {instance.tenant_id}")
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

    # Resolve API key: instance-specific first, then fall back to tenant/system key
    api_key = _decrypt_provider_key(instance, db)
    if not api_key:
        # Fall back to tenant-level API key for this vendor
        from services.api_key_service import get_api_key
        api_key = get_api_key(instance.vendor, db, tenant_id=instance.tenant_id)

    if not api_key and instance.vendor not in ("ollama",):
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
            max_tokens=20,
            api_key=api_key,  # V060-PRV-002: exercise instance's own key (falls back to tenant key only when instance has none)
        )

        # Disable SDK retries for connection tests — fail fast instead of hanging
        _disable_sdk_retries(client)

        # Override base_url if instance has custom values
        if instance.base_url:
            if hasattr(client, 'client') and client.client:
                client.client.base_url = instance.base_url
            if instance.vendor == "ollama":
                client.ollama_base_url = instance.base_url

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
