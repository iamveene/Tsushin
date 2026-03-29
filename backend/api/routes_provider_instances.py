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
    available_models: List[str] = []
    is_default: bool = False


class ProviderInstanceUpdate(BaseModel):
    instance_name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
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


class UrlValidationRequest(BaseModel):
    url: str


class UrlValidationResponse(BaseModel):
    valid: bool
    error: Optional[str] = None


# ==================== Helpers ====================

VALID_VENDORS = {"openai", "anthropic", "gemini", "groq", "grok", "openrouter", "ollama", "custom"}


def _encrypt_provider_key(plaintext_key: str, tenant_id: str, instance_id: int, db: Session) -> Optional[str]:
    """Encrypt a provider instance API key for storage."""
    try:
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            logger.error("Failed to get encryption key for provider instance key encryption")
            return None

        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"provider_instance_{instance_id}_{tenant_id}"
        return encryptor.encrypt(plaintext_key, identifier)
    except Exception as e:
        logger.error(f"Failed to encrypt provider instance key: {e}")
        return None


def _decrypt_provider_key(instance: ProviderInstance, db: Session) -> Optional[str]:
    """Decrypt a provider instance API key."""
    if not instance.api_key_encrypted:
        return None
    try:
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            logger.error("Failed to get encryption key for provider instance key decryption")
            return None

        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"provider_instance_{instance.id}_{instance.tenant_id}"
        return encryptor.decrypt(instance.api_key_encrypted, identifier)
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
        available_models=instance.available_models or [],
        is_default=instance.is_default,
        is_active=instance.is_active,
        health_status=instance.health_status or "unknown",
        health_status_reason=instance.health_status_reason,
        last_health_check=instance.last_health_check.isoformat() if instance.last_health_check else None,
    )


# ==================== Endpoints ====================

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

    # Create instance
    instance = ProviderInstance(
        tenant_id=ctx.tenant_id,
        vendor=vendor,
        instance_name=data.instance_name,
        base_url=data.base_url,
        available_models=data.available_models,
        is_default=data.is_default,
        is_active=True,
        health_status="unknown",
    )
    db.add(instance)
    db.flush()  # Get the ID for encryption identifier

    # Encrypt and store API key if provided
    if data.api_key:
        encrypted = _encrypt_provider_key(data.api_key, ctx.tenant_id, instance.id, db)
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
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/provider-instances/{instance_id}/test-connection", response_model=TestConnectionResponse)
async def test_provider_connection(
    instance_id: int,
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

    # Determine a test model
    from api.routes_integrations import PROVIDER_TEST_MODELS
    test_model = None
    if instance.available_models:
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

        client = AIClient(
            provider=instance.vendor if instance.vendor != "custom" else "openai",
            model_name=test_model,
            db=db,
            tenant_id=instance.tenant_id,
            max_tokens=20,
        )

        # Override base_url and API key if instance has custom values
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
        error_message = str(e)
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

    elif instance.vendor == "openrouter" and instance.base_url:
        # OpenRouter-compatible: query /v1/models
        import httpx
        base_url = instance.base_url.rstrip("/") if instance.base_url else "https://openrouter.ai/api/v1"

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
        # Cloud providers: return curated known models
        KNOWN_MODELS = {
            "openai": [
                "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4",
                "gpt-3.5-turbo", "o1", "o1-mini", "o3-mini",
            ],
            "anthropic": [
                "claude-sonnet-4-20250514", "claude-3-5-haiku-20241022",
                "claude-3-opus-20240229", "claude-3-haiku-20240307",
            ],
            "gemini": [
                "gemini-2.5-flash", "gemini-2.5-pro",
                "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash",
            ],
            "groq": [
                "llama-3.3-70b-versatile", "llama-3.1-8b-instant",
                "mixtral-8x7b-32768", "gemma2-9b-it",
            ],
            "grok": [
                "grok-3", "grok-3-mini", "grok-2",
            ],
            "openrouter": [
                "google/gemini-2.5-flash", "anthropic/claude-sonnet-4",
                "meta-llama/llama-3.1-8b-instruct:free",
            ],
        }
        models = KNOWN_MODELS.get(instance.vendor, [])

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

    try:
        validate_url(data.url)
        return UrlValidationResponse(valid=True)
    except SSRFValidationError as e:
        return UrlValidationResponse(valid=False, error=str(e))
