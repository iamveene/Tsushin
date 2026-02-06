"""
Phase 4.6: API Key Management Routes
Phase 7.9.2: Added tenant isolation for multi-tenancy support
Phase SEC-001: Added encryption at rest for API keys (CRIT-003 fix)

Provides endpoints for CRUD operations on API keys for LLM providers and tool services.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import httpx
import os
import logging

from models import ApiKey, GoogleFlightsIntegration, HubIntegration
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
    get_current_user_required
)
from hub.security import TokenEncryption
from services.encryption_key_service import get_api_key_encryption_key

logger = logging.getLogger(__name__)

router = APIRouter()

# Global engine reference
_engine = None

def set_engine(engine):
    """Set the global engine reference"""
    global _engine
    _engine = engine

# Dependency to get database session
def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Pydantic schemas
class ApiKeyCreate(BaseModel):
    service: str  # 'anthropic', 'openai', 'gemini', 'brave_search', 'openweather', 'amadeus', 'google_flights', 'serpapi'
    api_key: str
    is_active: bool = True


class ApiKeyUpdate(BaseModel):
    api_key: Optional[str] = None
    is_active: Optional[bool] = None


class ApiKeyResponse(BaseModel):
    id: int
    service: str
    api_key_preview: str  # Masked key for security (e.g., "sk-...xyz")
    is_active: bool
    tenant_id: Optional[str] = None
    created_at: Optional[datetime] = None  # Optional to handle legacy records
    updated_at: Optional[datetime] = None  # Optional to handle legacy records

    class Config:
        from_attributes = True


# Supported services
SUPPORTED_SERVICES = {
    'anthropic': 'Anthropic (Claude)',
    'openai': 'OpenAI (GPT)',
    'gemini': 'Google Gemini',
    'openrouter': 'OpenRouter',
    'brave_search': 'Brave Search API',
    'openweather': 'OpenWeatherMap',
    'amadeus': 'Amadeus (Flight Search)',
    'google_flights': 'Google Flights (SerpApi)',
    'serpapi': 'SerpAPI (Google Search)'
}


def mask_api_key(key: str) -> str:
    """Mask API key for display (show first 4 and last 4 chars)"""
    if not key:
        return '***'
    if len(key) <= 8:
        return '***'
    return f"{key[:4]}...{key[-4:]}"


def _encrypt_api_key_for_storage(plaintext_key: str, service: str, tenant_id: Optional[str], db: Session) -> Optional[str]:
    """Encrypt an API key for storage using the API key-specific encryption key (MED-001 fix)."""
    try:
        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            logger.error("Failed to get encryption key for API key encryption")
            return None
        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"apikey_{service}_{tenant_id or 'system'}"
        return encryptor.encrypt(plaintext_key, identifier)
    except Exception as e:
        logger.error(f"Failed to encrypt API key for {service}: {e}")
        return None


def _decrypt_api_key_for_display(api_key_record: ApiKey, db: Session) -> Optional[str]:
    """Decrypt an API key for display (masking). Falls back to plaintext for migration compatibility."""
    # Try encrypted field first
    if api_key_record.api_key_encrypted:
        try:
            # MED-001 security fix: Use dedicated API key encryption key
            encryption_key = get_api_key_encryption_key(db)
            if encryption_key:
                encryptor = TokenEncryption(encryption_key.encode())
                identifier = f"apikey_{api_key_record.service}_{api_key_record.tenant_id or 'system'}"
                return encryptor.decrypt(api_key_record.api_key_encrypted, identifier)
        except Exception as e:
            logger.error(f"Failed to decrypt API key for {api_key_record.service}: {e}")
            return None
    # Fall back to plaintext (migration compatibility)
    return api_key_record.api_key


def to_api_key_response(k: ApiKey, db: Session) -> ApiKeyResponse:
    """Convert ApiKey model to response (with decryption for masking)"""
    # Get decrypted key for masking
    decrypted_key = _decrypt_api_key_for_display(k, db)
    return ApiKeyResponse(
        id=k.id,
        service=k.service,
        api_key_preview=mask_api_key(decrypted_key) if decrypted_key else '***',
        is_active=k.is_active,
        tenant_id=k.tenant_id,
        created_at=k.created_at,
        updated_at=k.updated_at
    )


def sync_to_hub_integration(db: Session, api_key: ApiKey, plaintext_key: str):
    """
    Sync ApiKey to HubIntegration for services that use the new Provider architecture.

    Args:
        db: Database session
        api_key: The ApiKey record
        plaintext_key: The plaintext API key (needed for re-encryption for HubIntegration)
    """
    if api_key.service == 'google_flights':
        # Check if integration exists
        integration = db.query(HubIntegration).filter(
            HubIntegration.type == 'google_flights',
            HubIntegration.tenant_id == api_key.tenant_id
        ).first()

        # CRIT-004 fix: Use dedicated API key encryption key (not JWT_SECRET_KEY)
        # This ensures encryption persists across container restarts
        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            logger.error("Failed to get encryption key for GoogleFlightsIntegration sync")
            return
        encryptor = TokenEncryption(encryption_key.encode())
        # Use consistent identifier with ApiKey table
        identifier = f"apikey_google_flights_{api_key.tenant_id or 'system'}"
        encrypted_key = encryptor.encrypt(plaintext_key, identifier)

        if integration:
            # Update existing
            # Since integration is a HubIntegration object (polymorphic load?),
            # we need to ensure we have the GoogleFlightsIntegration object or cast it
            # If it was loaded as HubIntegration, we might need to query the child
            gf = db.query(GoogleFlightsIntegration).filter(GoogleFlightsIntegration.id == integration.id).first()
            if gf:
                gf.api_key_encrypted = encrypted_key
                # Update parent fields
                gf.is_active = api_key.is_active
        else:
            # Create new via inheritance
            gf = GoogleFlightsIntegration(
                # Hub fields
                name="Google Flights (SerpApi)",
                display_name="Google Flights",
                is_active=api_key.is_active,
                tenant_id=api_key.tenant_id,

                # Child fields
                api_key_encrypted=encrypted_key,
                default_currency="USD",
                default_language="en"
            )
            db.add(gf)


@router.get("/api-keys", response_model=List[ApiKeyResponse])
def list_api_keys(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List all configured API keys (masked).

    Phase 7.9.2: Returns keys for the user's tenant AND shared keys (NULL tenant_id).
    Global admins see all keys.
    """
    query = db.query(ApiKey)

    # Apply tenant filtering - include tenant's keys AND shared (NULL tenant_id) keys
    query = ctx.filter_by_tenant(query, ApiKey.tenant_id)

    keys = query.all()
    return [to_api_key_response(k, db) for k in keys]


@router.get("/api-keys/services")
def list_supported_services():
    """List all supported services for API key configuration"""
    return {"services": SUPPORTED_SERVICES}


@router.get("/api-keys/{service}", response_model=ApiKeyResponse)
def get_api_key_route(
    service: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get API key for a specific service (masked).

    Phase 7.9.2: Priority lookup:
    1. Tenant-specific key first
    2. Fallback to shared key (NULL tenant_id)
    """
    # First try tenant-specific key
    if ctx.tenant_id:
        key = db.query(ApiKey).filter(
            ApiKey.service == service,
            ApiKey.tenant_id == ctx.tenant_id
        ).first()

        if key:
            return to_api_key_response(key, db)

    # Fallback to shared key (NULL tenant_id)
    key = db.query(ApiKey).filter(
        ApiKey.service == service,
        ApiKey.tenant_id.is_(None)
    ).first()

    if not key:
        raise HTTPException(status_code=404, detail=f"API key for '{service}' not found")

    # Verify user can access this resource
    if not ctx.can_access_resource(key.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this API key")

    return to_api_key_response(key, db)


@router.post("/api-keys", response_model=ApiKeyResponse, status_code=201)
def create_or_update_api_key(
    data: ApiKeyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Create or update an API key for a service.

    Phase 7.9.2: Creates tenant-specific key. Use global admin to create shared keys.
    Phase SEC-001: API keys are now encrypted at rest.
    """
    # Validate service
    if data.service not in SUPPORTED_SERVICES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported service. Must be one of: {', '.join(SUPPORTED_SERVICES.keys())}"
        )

    # Encrypt the API key
    encrypted_key = _encrypt_api_key_for_storage(data.api_key, data.service, ctx.tenant_id, db)
    if not encrypted_key:
        raise HTTPException(status_code=500, detail="Failed to encrypt API key")

    # Check if key already exists for this tenant
    existing = db.query(ApiKey).filter(
        ApiKey.service == data.service,
        ApiKey.tenant_id == ctx.tenant_id
    ).first()

    if existing:
        # Update existing key - store encrypted, clear plaintext
        existing.api_key_encrypted = encrypted_key
        existing.api_key = None  # Clear plaintext for security
        existing.is_active = data.is_active
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        result = existing
    else:
        # Create new key for this tenant - encrypted only
        new_key = ApiKey(
            service=data.service,
            api_key=None,  # No plaintext storage
            api_key_encrypted=encrypted_key,
            is_active=data.is_active,
            tenant_id=ctx.tenant_id  # Assign to user's tenant
        )
        db.add(new_key)
        db.commit()
        db.refresh(new_key)
        result = new_key

    # Sync to HubIntegration if needed (pass plaintext for re-encryption)
    try:
        sync_to_hub_integration(db, result, data.api_key)
        db.commit()
    except Exception as e:
        # Don't fail the request if sync fails, but log it
        logger.warning(f"Failed to sync API key to HubIntegration: {e}")

    return to_api_key_response(result, db)


@router.put("/api-keys/{service}", response_model=ApiKeyResponse)
def update_api_key(
    service: str,
    data: ApiKeyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update an existing API key.

    Phase 7.9.2: Only updates keys belonging to user's tenant (or shared if global admin).
    Phase SEC-001: API keys are now encrypted at rest.
    """
    # Find key - first try tenant-specific, then shared
    key = db.query(ApiKey).filter(
        ApiKey.service == service,
        ApiKey.tenant_id == ctx.tenant_id
    ).first()

    if not key and ctx.is_global_admin:
        # Global admin can update shared keys
        key = db.query(ApiKey).filter(
            ApiKey.service == service,
            ApiKey.tenant_id.is_(None)
        ).first()

    if not key:
        raise HTTPException(status_code=404, detail=f"API key for '{service}' not found")

    # Verify access
    if not ctx.can_access_resource(key.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this API key")

    plaintext_key_for_sync = None
    if data.api_key is not None:
        # Encrypt the new key
        encrypted_key = _encrypt_api_key_for_storage(data.api_key, service, key.tenant_id, db)
        if not encrypted_key:
            raise HTTPException(status_code=500, detail="Failed to encrypt API key")
        key.api_key_encrypted = encrypted_key
        key.api_key = None  # Clear plaintext for security
        plaintext_key_for_sync = data.api_key

    if data.is_active is not None:
        key.is_active = data.is_active

    key.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(key)

    # Sync to HubIntegration if needed (only if key was updated)
    if plaintext_key_for_sync:
        try:
            sync_to_hub_integration(db, key, plaintext_key_for_sync)
            db.commit()
        except Exception as e:
            logger.warning(f"Failed to sync API key to HubIntegration: {e}")

    return to_api_key_response(key, db)


@router.delete("/api-keys/{service}")
def delete_api_key(
    service: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete an API key.

    Phase 7.9.2: Only deletes keys belonging to user's tenant (or shared if global admin).
    """
    # Find key - first try tenant-specific, then shared (for global admin)
    key = db.query(ApiKey).filter(
        ApiKey.service == service,
        ApiKey.tenant_id == ctx.tenant_id
    ).first()

    if not key and ctx.is_global_admin:
        # Global admin can delete shared keys
        key = db.query(ApiKey).filter(
            ApiKey.service == service,
            ApiKey.tenant_id.is_(None)
        ).first()

    if not key:
        raise HTTPException(status_code=404, detail=f"API key for '{service}' not found")

    # Verify access
    if not ctx.can_access_resource(key.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this API key")

    db.delete(key)
    db.commit()
    return {"message": f"API key for '{service}' deleted successfully"}


# ==================== Ollama Integration (Phase 5.2) ====================

@router.get("/ollama/health")
async def check_ollama_health(db: Session = Depends(get_db)):
    """
    Check Ollama local LLM service health status.
    Returns online/offline status and available models.
    Phase 5.2.1: Uses configured base URL from Config table.

    Note: This is a system-wide health check, no tenant isolation needed.
    """
    # Load from Config table if available, otherwise from env var
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    ollama_api_key = None

    from models import Config
    config = db.query(Config).first()
    if config and config.ollama_base_url:
        ollama_base_url = config.ollama_base_url
    if config and config.ollama_api_key:
        ollama_api_key = config.ollama_api_key

    try:
        headers = {}
        if ollama_api_key:
            headers["Authorization"] = f"Bearer {ollama_api_key}"

        async with httpx.AsyncClient(timeout=5.0, headers=headers if headers else None) as client:
            response = await client.get(f"{ollama_base_url}/api/tags")

            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])

                return {
                    "status": "online",
                    "base_url": ollama_base_url,
                    "available": True,
                    "models_count": len(models),
                    "models": [
                        {
                            "name": m.get("name"),
                            "size": m.get("size", 0),
                            "modified_at": m.get("modified_at")
                        }
                        for m in models
                    ]
                }
            else:
                return {
                    "status": "error",
                    "base_url": ollama_base_url,
                    "available": False,
                    "error": f"HTTP {response.status_code}"
                }
    except httpx.ConnectError:
        return {
            "status": "offline",
            "base_url": ollama_base_url,
            "available": False,
            "error": "Cannot connect to Ollama. Start with: ollama serve"
        }
    except Exception as e:
        return {
            "status": "error",
            "base_url": ollama_base_url,
            "available": False,
            "error": str(e)
        }
