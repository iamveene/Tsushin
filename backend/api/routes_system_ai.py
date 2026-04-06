"""
System AI Configuration API Routes
Phase 17 → Phase 27: Provider-Instance-Based System AI

Endpoints for managing system-level AI configuration.
The system AI now points to an existing ProviderInstance instead of
maintaining its own duplicated provider/model lists.

Security: All endpoints require authentication.
- GET endpoints require org.settings.read permission
- PUT/POST endpoints require org.settings.write permission
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from db import get_db
from models_rbac import User
from auth_dependencies import require_permission
from services.system_ai_config import (
    get_system_ai_config_dict,
    test_system_ai_connection,
    update_system_ai_config,
)

router = APIRouter(prefix="/api/config/system-ai", tags=["System AI Configuration"])


# ============================================================================
# Pydantic Models
# ============================================================================

class SystemAIConfigResponse(BaseModel):
    """Current system AI configuration"""
    provider: str = Field(..., description="AI provider vendor")
    model_name: str = Field(..., description="Model name")
    provider_instance_id: Optional[int] = Field(None, description="Linked ProviderInstance ID")
    instance_name: Optional[str] = Field(None, description="ProviderInstance display name")
    vendor: Optional[str] = Field(None, description="ProviderInstance vendor")


class SystemAIConfigUpdate(BaseModel):
    """Request to update system AI configuration — points to a ProviderInstance"""
    provider_instance_id: int = Field(..., description="ProviderInstance ID to use")
    model_name: str = Field(..., description="Model name from that instance")


class TestConnectionRequest(BaseModel):
    """Request to test AI connection via a ProviderInstance"""
    provider_instance_id: Optional[int] = Field(None, description="Instance to test (uses current if omitted)")
    model_name: Optional[str] = Field(None, description="Model to test (uses current if omitted)")


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
    provider_instance_id: Optional[int] = None
    instance_name: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("", response_model=SystemAIConfigResponse)
async def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
):
    """
    Get current system AI configuration.
    Returns the linked ProviderInstance and model used for system operations.
    """
    data = get_system_ai_config_dict(db)
    return SystemAIConfigResponse(**data)


@router.put("", response_model=UpdateResponse)
async def update_config(
    config: SystemAIConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
):
    """
    Update system AI configuration to use a specific ProviderInstance + model.
    """
    result = update_system_ai_config(db, config.provider_instance_id, config.model_name)
    return UpdateResponse(**result)


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(
    request: TestConnectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
):
    """
    Test connection to an AI provider instance.
    If provider_instance_id/model not specified, uses the current configuration.
    """
    result = await test_system_ai_connection(
        db,
        provider_instance_id=request.provider_instance_id,
        model=request.model_name,
        tenant_id=getattr(current_user, 'tenant_id', None),
    )
    return TestConnectionResponse(**result)


@router.post("/test-current", response_model=TestConnectionResponse)
async def test_current_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
):
    """
    Test connection using current system AI configuration.
    """
    result = await test_system_ai_connection(
        db,
        tenant_id=getattr(current_user, 'tenant_id', None),
    )
    return TestConnectionResponse(**result)
