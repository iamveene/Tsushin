"""
Integration Test Connection API Routes

Provides test-connection endpoints for all supported integrations.
Validates API keys by making minimal test requests to each provider.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, Dict
import logging

from db import get_db
from models_rbac import User
from auth_dependencies import require_permission, get_tenant_context, TenantContext

router = APIRouter(prefix="/api/integrations", tags=["Integration Tests"])
logger = logging.getLogger(__name__)

# Default models for testing each provider (cheap/fast models)
PROVIDER_TEST_MODELS = {
    "groq": "llama-3.1-8b-instant",
    "grok": "grok-3",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-20241022",
    "gemini": "gemini-2.5-flash",
    "openrouter": "meta-llama/llama-3.1-8b-instruct:free",
    "deepseek": "deepseek-chat",
}

SUPPORTED_PROVIDERS = list(PROVIDER_TEST_MODELS.keys()) + ["elevenlabs"]


class TestConnectionRequest(BaseModel):
    model: Optional[str] = Field(None, description="Model to test (uses default if not specified)")


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    provider: str
    details: Optional[Dict] = None
    error: Optional[str] = None


@router.post("/{provider}/test", response_model=TestConnectionResponse)
async def test_integration_connection(
    provider: str,
    request: TestConnectionRequest = TestConnectionRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Test connection for a configured integration provider."""
    provider = provider.lower()

    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider: {provider}. Supported: {SUPPORTED_PROVIDERS}"
        )

    try:
        if provider == "elevenlabs":
            return await _test_elevenlabs(db)
        else:
            return await _test_llm_provider(provider, request.model, db, ctx.tenant_id)
    except Exception as e:
        logger.error(f"Error testing {provider} connection: {e}", exc_info=True)
        return TestConnectionResponse(
            success=False,
            message=f"Connection test failed: {str(e)}",
            provider=provider,
            error=str(e)
        )


async def _test_llm_provider(
    provider: str, model: Optional[str], db: Session, tenant_id: str
) -> TestConnectionResponse:
    """Test an LLM provider by sending a minimal test message."""
    from agent.ai_client import AIClient

    test_model = model or PROVIDER_TEST_MODELS.get(provider)
    if not test_model:
        return TestConnectionResponse(
            success=False,
            message=f"No default test model for {provider}",
            provider=provider,
        )

    try:
        from analytics.token_tracker import TokenTracker
        tracker = TokenTracker(db, tenant_id)

        client = AIClient(
            provider=provider,
            model_name=test_model,
            db=db,
            token_tracker=tracker,
            tenant_id=tenant_id,
            max_tokens=20,
        )

        result = await client.generate(
            system_prompt="You are a test assistant. Respond with exactly: OK",
            user_message="Test connection. Reply with OK.",
            operation_type="connection_test",
        )

        if result.get("error"):
            return TestConnectionResponse(
                success=False,
                message=f"API error: {result['error']}",
                provider=provider,
                error=result["error"],
            )

        answer = result.get("answer", "")
        return TestConnectionResponse(
            success=True,
            message=f"Connected to {provider}/{test_model}",
            provider=provider,
            details={
                "model": test_model,
                "response_preview": answer[:100],
                "token_usage": result.get("token_usage"),
            },
        )

    except ValueError as e:
        # API key not found
        return TestConnectionResponse(
            success=False,
            message=f"API key not configured for {provider}",
            provider=provider,
            error=str(e),
        )


async def _test_elevenlabs(db: Session) -> TestConnectionResponse:
    """Test ElevenLabs connection via health check."""
    from hub.providers.elevenlabs_tts_provider import ElevenLabsTTSProvider

    provider = ElevenLabsTTSProvider(db=db)
    status = await provider.health_check()

    return TestConnectionResponse(
        success=status.available,
        message=status.message,
        provider="elevenlabs",
        details=status.details if status.details else None,
        error=None if status.available else status.message,
    )
