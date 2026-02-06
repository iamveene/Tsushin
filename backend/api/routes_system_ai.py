"""
System AI Configuration API Routes
Phase 17: Tenant-Configurable System AI Provider

Provides endpoints for managing system-level AI configuration.

Security: HIGH-007 fix - All endpoints require authentication (2026-02-02)
- GET endpoints require org.settings.read permission
- PUT/POST endpoints require org.settings.write permission
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from db import get_db
from models_rbac import User
from auth_dependencies import require_permission
from services.system_ai_config import (
    get_system_ai_config,
    get_system_ai_config_dict,
    get_available_providers,
    get_models_for_provider,
    test_system_ai_connection,
    update_system_ai_config,
    PROVIDER_MODELS,
)

router = APIRouter(prefix="/api/config/system-ai", tags=["System AI Configuration"])


# ============================================================================
# Pydantic Models
# ============================================================================

class SystemAIConfigResponse(BaseModel):
    """Current system AI configuration"""
    provider: str = Field(..., description="AI provider (gemini, anthropic, openai, openrouter)")
    model_name: str = Field(..., description="Model name")


class SystemAIConfigUpdate(BaseModel):
    """Request to update system AI configuration"""
    provider: str = Field(..., description="AI provider (gemini, anthropic, openai, openrouter)")
    model_name: str = Field(..., description="Model name")


class ProviderOption(BaseModel):
    """Provider option for dropdown"""
    value: str
    label: str
    description: str


class ModelOption(BaseModel):
    """Model option for dropdown"""
    value: str
    label: str
    description: str


class ProvidersResponse(BaseModel):
    """List of available providers"""
    providers: List[ProviderOption]


class ModelsResponse(BaseModel):
    """List of available models for a provider"""
    provider: str
    models: List[ModelOption]


class AllModelsResponse(BaseModel):
    """All models grouped by provider"""
    models_by_provider: Dict[str, List[ModelOption]]


class TestConnectionRequest(BaseModel):
    """Request to test AI connection"""
    provider: Optional[str] = Field(None, description="Provider to test (uses current config if not specified)")
    model_name: Optional[str] = Field(None, description="Model to test (uses current config if not specified)")


class TestConnectionResponse(BaseModel):
    """Result of connection test"""
    success: bool
    message: str
    provider: str
    model: str
    token_usage: Optional[Dict] = None
    error: Optional[str] = None


class UpdateResponse(BaseModel):
    """Result of config update"""
    success: bool
    message: str
    provider: Optional[str] = None
    model: Optional[str] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("", response_model=SystemAIConfigResponse)
async def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read"))
):
    """
    Get current system AI configuration.

    Returns the currently configured AI provider and model used for
    system operations (intent classification, skill routing, AI summaries).

    Requires: org.settings.read permission
    """
    provider, model = get_system_ai_config(db)
    return SystemAIConfigResponse(provider=provider, model_name=model)


@router.put("", response_model=UpdateResponse)
async def update_config(
    config: SystemAIConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Update system AI configuration.

    Changes the AI provider and model used for system operations.
    Recommended to test connection before updating.

    Requires: org.settings.write permission
    """
    result = update_system_ai_config(db, config.provider, config.model_name)
    return UpdateResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        provider=result.get("provider"),
        model=result.get("model")
    )


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers(
    current_user: User = Depends(require_permission("org.settings.read"))
):
    """
    Get list of available AI providers.

    Returns all supported providers with their labels and descriptions.

    Requires: org.settings.read permission
    """
    providers = get_available_providers()
    return ProvidersResponse(providers=[ProviderOption(**p) for p in providers])


@router.get("/models/{provider}", response_model=ModelsResponse)
async def list_models_for_provider(
    provider: str,
    current_user: User = Depends(require_permission("org.settings.read"))
):
    """
    Get list of available models for a specific provider.

    Returns predefined model options for the given provider.

    Requires: org.settings.read permission
    """
    models = get_models_for_provider(provider)
    if not models:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider}' not found or has no predefined models"
        )
    return ModelsResponse(
        provider=provider,
        models=[ModelOption(**m) for m in models]
    )


@router.get("/models", response_model=AllModelsResponse)
async def list_all_models(
    current_user: User = Depends(require_permission("org.settings.read"))
):
    """
    Get all available models grouped by provider.

    Returns all predefined model options for all providers.

    Requires: org.settings.read permission
    """
    models_by_provider = {
        provider: [ModelOption(**m) for m in models]
        for provider, models in PROVIDER_MODELS.items()
    }
    return AllModelsResponse(models_by_provider=models_by_provider)


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(
    request: TestConnectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Test connection to an AI provider.

    Sends a simple test message to verify the API key is configured
    and the provider is accessible. If provider/model not specified,
    uses the current configuration.

    Requires: org.settings.write permission
    """
    result = await test_system_ai_connection(
        db,
        provider=request.provider,
        model=request.model_name
    )
    return TestConnectionResponse(**result)


@router.post("/test-current", response_model=TestConnectionResponse)
async def test_current_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Test connection using current system AI configuration.

    Shortcut endpoint that tests the currently configured provider/model.

    Requires: org.settings.write permission
    """
    result = await test_system_ai_connection(db)
    return TestConnectionResponse(**result)
