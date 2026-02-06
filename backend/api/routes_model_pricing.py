"""
Model Pricing API Routes

Allows configuration of model pricing for cost estimation in the debug panel.
Tenants can customize pricing per model or use system defaults.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import logging

from db import get_db
from auth_dependencies import get_current_user_required, require_permission
from models_rbac import User
from models import ModelPricing
from analytics.token_tracker import MODEL_PRICING as DEFAULT_PRICING

logger = logging.getLogger(__name__)
router = APIRouter()


# === Schemas ===

class ModelPricingItem(BaseModel):
    """Schema for a single model pricing entry."""
    id: Optional[int] = None
    model_provider: str = Field(..., description="Provider name: openai, anthropic, gemini, ollama")
    model_name: str = Field(..., description="Model name: gpt-4o, claude-3-5-sonnet, etc.")
    display_name: Optional[str] = Field(None, description="Human-readable name for UI")
    input_cost_per_million: float = Field(..., ge=0, description="Cost per 1M input tokens in USD")
    output_cost_per_million: float = Field(..., ge=0, description="Cost per 1M output tokens in USD")
    cached_input_cost_per_million: Optional[float] = Field(None, ge=0, description="Cost per 1M cached input tokens")
    is_active: bool = Field(True, description="Whether this pricing is active")
    is_default: bool = Field(False, description="Whether this is from default/fallback pricing")

    class Config:
        from_attributes = True


class ModelPricingListResponse(BaseModel):
    """Response for listing all model pricing."""
    pricing: List[ModelPricingItem]
    count: int


class ModelPricingUpdateRequest(BaseModel):
    """Request to update model pricing."""
    model_provider: str
    model_name: str
    display_name: Optional[str] = None
    input_cost_per_million: float = Field(..., ge=0)
    output_cost_per_million: float = Field(..., ge=0)
    cached_input_cost_per_million: Optional[float] = Field(None, ge=0)
    is_active: bool = True


class ModelPricingBulkUpdateRequest(BaseModel):
    """Request to bulk update model pricing."""
    pricing: List[ModelPricingUpdateRequest]


# === Endpoints ===

@router.get("/api/settings/model-pricing", response_model=ModelPricingListResponse)
async def get_model_pricing(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get all model pricing configurations.

    Returns tenant-specific pricing if available, otherwise falls back to system defaults.
    """
    tenant_id = current_user.tenant_id

    # Get tenant-specific pricing
    tenant_pricing = db.query(ModelPricing).filter(
        ModelPricing.tenant_id == tenant_id
    ).all()

    # Build response with tenant pricing
    pricing_map = {}
    for p in tenant_pricing:
        key = f"{p.model_provider}:{p.model_name}"
        pricing_map[key] = ModelPricingItem(
            id=p.id,
            model_provider=p.model_provider,
            model_name=p.model_name,
            display_name=p.display_name,
            input_cost_per_million=p.input_cost_per_million,
            output_cost_per_million=p.output_cost_per_million,
            cached_input_cost_per_million=p.cached_input_cost_per_million,
            is_active=p.is_active,
            is_default=False
        )

    # Add default pricing for models not in tenant pricing
    for model_name, costs in DEFAULT_PRICING.items():
        # Determine provider from model name
        provider = _get_provider_from_model(model_name)
        key = f"{provider}:{model_name}"

        if key not in pricing_map:
            pricing_map[key] = ModelPricingItem(
                model_provider=provider,
                model_name=model_name,
                display_name=_format_display_name(model_name),
                input_cost_per_million=costs.get("prompt", 0),
                output_cost_per_million=costs.get("completion", 0),
                cached_input_cost_per_million=None,
                is_active=True,
                is_default=True
            )

    # Sort by provider then model name
    pricing_list = sorted(
        pricing_map.values(),
        key=lambda x: (x.model_provider, x.model_name)
    )

    return ModelPricingListResponse(
        pricing=pricing_list,
        count=len(pricing_list)
    )


@router.put("/api/settings/model-pricing/{model_provider}/{model_name}")
async def update_model_pricing(
    model_provider: str,
    model_name: str,
    request: ModelPricingUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Update or create pricing for a specific model.

    Requires org.settings.write permission.
    """
    tenant_id = current_user.tenant_id

    # Find existing pricing
    existing = db.query(ModelPricing).filter(
        ModelPricing.tenant_id == tenant_id,
        ModelPricing.model_provider == model_provider,
        ModelPricing.model_name == model_name
    ).first()

    if existing:
        # Update existing
        existing.display_name = request.display_name
        existing.input_cost_per_million = request.input_cost_per_million
        existing.output_cost_per_million = request.output_cost_per_million
        existing.cached_input_cost_per_million = request.cached_input_cost_per_million
        existing.is_active = request.is_active
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)

        return ModelPricingItem(
            id=existing.id,
            model_provider=existing.model_provider,
            model_name=existing.model_name,
            display_name=existing.display_name,
            input_cost_per_million=existing.input_cost_per_million,
            output_cost_per_million=existing.output_cost_per_million,
            cached_input_cost_per_million=existing.cached_input_cost_per_million,
            is_active=existing.is_active,
            is_default=False
        )
    else:
        # Create new
        new_pricing = ModelPricing(
            tenant_id=tenant_id,
            model_provider=model_provider,
            model_name=model_name,
            display_name=request.display_name,
            input_cost_per_million=request.input_cost_per_million,
            output_cost_per_million=request.output_cost_per_million,
            cached_input_cost_per_million=request.cached_input_cost_per_million,
            is_active=request.is_active
        )
        db.add(new_pricing)
        db.commit()
        db.refresh(new_pricing)

        return ModelPricingItem(
            id=new_pricing.id,
            model_provider=new_pricing.model_provider,
            model_name=new_pricing.model_name,
            display_name=new_pricing.display_name,
            input_cost_per_million=new_pricing.input_cost_per_million,
            output_cost_per_million=new_pricing.output_cost_per_million,
            cached_input_cost_per_million=new_pricing.cached_input_cost_per_million,
            is_active=new_pricing.is_active,
            is_default=False
        )


@router.post("/api/settings/model-pricing/bulk")
async def bulk_update_model_pricing(
    request: ModelPricingBulkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Bulk update model pricing.

    Useful for resetting all pricing or importing pricing configurations.
    """
    tenant_id = current_user.tenant_id
    updated_count = 0
    created_count = 0

    for item in request.pricing:
        existing = db.query(ModelPricing).filter(
            ModelPricing.tenant_id == tenant_id,
            ModelPricing.model_provider == item.model_provider,
            ModelPricing.model_name == item.model_name
        ).first()

        if existing:
            existing.display_name = item.display_name
            existing.input_cost_per_million = item.input_cost_per_million
            existing.output_cost_per_million = item.output_cost_per_million
            existing.cached_input_cost_per_million = item.cached_input_cost_per_million
            existing.is_active = item.is_active
            existing.updated_at = datetime.utcnow()
            updated_count += 1
        else:
            new_pricing = ModelPricing(
                tenant_id=tenant_id,
                model_provider=item.model_provider,
                model_name=item.model_name,
                display_name=item.display_name,
                input_cost_per_million=item.input_cost_per_million,
                output_cost_per_million=item.output_cost_per_million,
                cached_input_cost_per_million=item.cached_input_cost_per_million,
                is_active=item.is_active
            )
            db.add(new_pricing)
            created_count += 1

    db.commit()

    return {
        "status": "success",
        "updated": updated_count,
        "created": created_count,
        "total": updated_count + created_count
    }


@router.delete("/api/settings/model-pricing/{model_provider}/{model_name}")
async def delete_model_pricing(
    model_provider: str,
    model_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Delete custom pricing for a model (reverts to system default).
    """
    tenant_id = current_user.tenant_id

    existing = db.query(ModelPricing).filter(
        ModelPricing.tenant_id == tenant_id,
        ModelPricing.model_provider == model_provider,
        ModelPricing.model_name == model_name
    ).first()

    if not existing:
        raise HTTPException(status_code=404, detail="Custom pricing not found")

    db.delete(existing)
    db.commit()

    return {"status": "success", "message": f"Custom pricing for {model_provider}/{model_name} deleted"}


@router.post("/api/settings/model-pricing/reset")
async def reset_to_defaults(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Reset all custom pricing to system defaults.

    Deletes all tenant-specific pricing configurations.
    """
    tenant_id = current_user.tenant_id

    deleted = db.query(ModelPricing).filter(
        ModelPricing.tenant_id == tenant_id
    ).delete()

    db.commit()

    return {
        "status": "success",
        "message": f"Deleted {deleted} custom pricing entries, reverting to system defaults"
    }


# === Helper Functions ===

def _get_provider_from_model(model_name: str) -> str:
    """Determine provider from model name."""
    model_lower = model_name.lower()

    if model_lower.startswith("gpt-") or model_lower.startswith("whisper") or model_lower.startswith("tts-"):
        return "openai"
    elif model_lower.startswith("claude-"):
        return "anthropic"
    elif model_lower.startswith("gemini"):
        return "gemini"
    elif model_lower in ["kokoro"]:
        return "kokoro"
    elif model_lower in ["elevenlabs"]:
        return "elevenlabs"
    elif model_lower in ["llama3.2", "llama3.1", "llama3", "mistral", "mixtral", "qwen2.5", "codellama"]:
        return "ollama"
    else:
        return "unknown"


def _format_display_name(model_name: str) -> str:
    """Format model name for display."""
    # Common formatting rules
    name = model_name.replace("-", " ").replace("_", " ")

    # Specific model name formatting
    display_map = {
        # OpenAI LLMs
        "gpt-4o": "GPT-4o",
        "gpt-4o-mini": "GPT-4o Mini",
        "gpt-4": "GPT-4",
        "gpt-4-turbo": "GPT-4 Turbo",
        "gpt-3.5-turbo": "GPT-3.5 Turbo",
        # OpenAI Audio
        "whisper-1": "Whisper (Audio Transcription)",
        "tts-1": "OpenAI TTS Standard",
        "tts-1-hd": "OpenAI TTS HD",
        # Anthropic
        "claude-3-5-sonnet-20241022": "Claude 3.5 Sonnet",
        "claude-3-5-sonnet-latest": "Claude 3.5 Sonnet (Latest)",
        "claude-3-5-haiku-20241022": "Claude 3.5 Haiku",
        "claude-3-opus-20240229": "Claude 3 Opus",
        "claude-3-opus-latest": "Claude 3 Opus (Latest)",
        "claude-3-sonnet-20240229": "Claude 3 Sonnet",
        "claude-3-haiku-20240307": "Claude 3 Haiku",
        # Google Gemini
        "gemini-2.5-pro": "Gemini 2.5 Pro",
        "gemini-2.5-flash": "Gemini 2.5 Flash",
        "gemini-2.0-flash": "Gemini 2.0 Flash",
        "gemini-1.5-pro": "Gemini 1.5 Pro",
        "gemini-1.5-flash": "Gemini 1.5 Flash",
        # TTS Providers
        "kokoro": "Kokoro TTS (Free)",
        "elevenlabs": "ElevenLabs TTS",
        # Local Models (Ollama)
        "llama3.2": "Llama 3.2 (Local)",
        "llama3.1": "Llama 3.1 (Local)",
        "llama3": "Llama 3 (Local)",
        "mistral": "Mistral (Local)",
        "mixtral": "Mixtral (Local)",
        "qwen2.5": "Qwen 2.5 (Local)",
        "codellama": "Code Llama (Local)",
    }

    return display_map.get(model_name, name.title())
