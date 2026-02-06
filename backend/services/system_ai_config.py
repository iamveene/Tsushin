"""
System AI Configuration Service
Phase 17: Tenant-Configurable System AI Provider

Provides centralized access to system-level AI configuration.
Used by skills, classifiers, and other system components that need to make AI calls.

This replaces all hardcoded "gemini-2.5-flash" defaults throughout the codebase,
allowing tenants to configure which AI provider is used for system operations.

Default: Gemini (gemini-2.5-flash) - fast and affordable for system operations.
"""
import logging
from typing import Tuple, Optional, Dict, List
from functools import lru_cache
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default fallback values (used when no config exists or on error)
DEFAULT_SYSTEM_AI_PROVIDER = "gemini"
DEFAULT_SYSTEM_AI_MODEL = "gemini-2.5-flash"

# Predefined model options per provider (for UI dropdown)
PROVIDER_MODELS: Dict[str, List[Dict[str, str]]] = {
    "gemini": [
        {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash (Recommended)", "description": "Fast & affordable"},
        {"value": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "description": "Most capable"},
        {"value": "gemini-2.0-flash", "label": "Gemini 2.0 Flash", "description": "Previous generation"},
    ],
    "anthropic": [
        {"value": "claude-3-5-haiku-20241022", "label": "Claude 3.5 Haiku (Recommended)", "description": "Fast & affordable"},
        {"value": "claude-3-5-sonnet-20241022", "label": "Claude 3.5 Sonnet", "description": "Best overall"},
        {"value": "claude-3-opus-20240229", "label": "Claude 3 Opus", "description": "Most capable"},
    ],
    "openai": [
        {"value": "gpt-4o-mini", "label": "GPT-4o Mini (Recommended)", "description": "Fast & affordable"},
        {"value": "gpt-4o", "label": "GPT-4o", "description": "Most capable"},
        {"value": "gpt-4-turbo", "label": "GPT-4 Turbo", "description": "Previous generation"},
    ],
    "openrouter": [
        {"value": "google/gemini-2.5-flash", "label": "Gemini 2.5 Flash via OpenRouter", "description": "Fast & affordable"},
        {"value": "anthropic/claude-3.5-haiku", "label": "Claude 3.5 Haiku via OpenRouter", "description": "Anthropic's fast model"},
        {"value": "openai/gpt-4o-mini", "label": "GPT-4o Mini via OpenRouter", "description": "OpenAI's fast model"},
        {"value": "meta-llama/llama-3.1-8b-instruct:free", "label": "Llama 3.1 8B (Free)", "description": "Free tier"},
    ],
}

# Provider display names for UI
PROVIDERS = [
    {"value": "gemini", "label": "Google Gemini", "description": "Recommended - Fast and reliable"},
    {"value": "anthropic", "label": "Anthropic Claude", "description": "High quality reasoning"},
    {"value": "openai", "label": "OpenAI GPT", "description": "Industry standard"},
    {"value": "openrouter", "label": "OpenRouter", "description": "Multi-provider gateway"},
]


def get_system_ai_config(db: Session) -> Tuple[str, str]:
    """
    Get system-level AI provider and model from Config table.

    This is the single source of truth for system AI configuration.
    All skills and classifiers should call this instead of hardcoding defaults.

    Args:
        db: Database session

    Returns:
        Tuple of (provider, model_name)
        Example: ("gemini", "gemini-2.5-flash")

    Usage:
        from services.system_ai_config import get_system_ai_config

        provider, model = get_system_ai_config(db)
        ai_client = AIClient(provider=provider, model_name=model, db=db)
    """
    try:
        from models import Config

        config = db.query(Config).first()
        if config:
            provider = config.system_ai_provider or DEFAULT_SYSTEM_AI_PROVIDER
            model = config.system_ai_model or DEFAULT_SYSTEM_AI_MODEL
            logger.debug(f"System AI config loaded: provider={provider}, model={model}")
            return (provider, model)
        else:
            logger.warning("No Config found in database, using defaults")
            return (DEFAULT_SYSTEM_AI_PROVIDER, DEFAULT_SYSTEM_AI_MODEL)

    except Exception as e:
        logger.error(f"Error loading system AI config: {e}")
        return (DEFAULT_SYSTEM_AI_PROVIDER, DEFAULT_SYSTEM_AI_MODEL)


def get_system_ai_config_dict(db: Session) -> Dict[str, str]:
    """
    Get system AI config as a dictionary.
    Useful for JSON API responses and config injection.

    Args:
        db: Database session

    Returns:
        Dict with provider and model_name keys
    """
    provider, model = get_system_ai_config(db)
    return {
        "provider": provider,
        "model_name": model
    }


def get_available_providers() -> List[Dict[str, str]]:
    """
    Get list of available AI providers for UI dropdown.

    Returns:
        List of provider options with value, label, and description
    """
    return PROVIDERS


def get_models_for_provider(provider: str) -> List[Dict[str, str]]:
    """
    Get list of available models for a specific provider.

    Args:
        provider: Provider name (gemini, anthropic, openai, openrouter)

    Returns:
        List of model options with value, label, and description
    """
    return PROVIDER_MODELS.get(provider, [])


async def test_system_ai_connection(db: Session, provider: Optional[str] = None, model: Optional[str] = None) -> Dict:
    """
    Test connection to the system AI provider.

    If provider/model not specified, uses current config values.

    Args:
        db: Database session
        provider: Optional provider to test (uses config if not specified)
        model: Optional model to test (uses config if not specified)

    Returns:
        Dict with success, message, and details
    """
    try:
        # Get config if not specified
        if not provider or not model:
            config_provider, config_model = get_system_ai_config(db)
            provider = provider or config_provider
            model = model or config_model

        # Import here to avoid circular imports
        from agent.ai_client import AIClient

        # Create client and send test message
        client = AIClient(provider=provider, model_name=model, db=db)

        result = await client.generate(
            system_prompt="You are a test assistant. Respond with exactly: OK",
            user_message="Test connection. Reply with OK.",
            operation_type="connection_test"
        )

        if result.get("error"):
            return {
                "success": False,
                "message": f"API Error: {result['error']}",
                "provider": provider,
                "model": model
            }

        answer = result.get("answer", "")
        if "OK" in answer.upper() or len(answer) > 0:
            return {
                "success": True,
                "message": f"Successfully connected to {provider}/{model}",
                "provider": provider,
                "model": model,
                "token_usage": result.get("token_usage")
            }
        else:
            return {
                "success": False,
                "message": f"Unexpected response from {provider}/{model}",
                "provider": provider,
                "model": model,
                "response": answer[:100]
            }

    except ValueError as e:
        # API key not found
        return {
            "success": False,
            "message": f"API key not configured for {provider}",
            "provider": provider,
            "model": model,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Error testing system AI connection: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "provider": provider,
            "model": model,
            "error": str(e)
        }


def update_system_ai_config(db: Session, provider: str, model: str) -> Dict:
    """
    Update system AI configuration.

    Args:
        db: Database session
        provider: New provider (gemini, anthropic, openai, openrouter)
        model: New model name

    Returns:
        Dict with success status and message
    """
    try:
        from models import Config

        # Validate provider
        valid_providers = [p["value"] for p in PROVIDERS]
        if provider not in valid_providers:
            return {
                "success": False,
                "message": f"Invalid provider: {provider}. Must be one of: {valid_providers}"
            }

        # Get or create config
        config = db.query(Config).first()
        if not config:
            return {
                "success": False,
                "message": "No Config found in database. Please run initial setup first."
            }

        # Update config
        config.system_ai_provider = provider
        config.system_ai_model = model
        db.commit()

        logger.info(f"System AI config updated: provider={provider}, model={model}")

        return {
            "success": True,
            "message": f"System AI configuration updated to {provider}/{model}",
            "provider": provider,
            "model": model
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating system AI config: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to update configuration: {str(e)}"
        }
