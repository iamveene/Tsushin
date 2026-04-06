"""
System AI Configuration Service
Phase 17 → Phase 27: Provider-Instance-Based System AI

Provides centralized access to system-level AI configuration.
Used by skills, classifiers, and other system components that need to make AI calls.

Phase 27: The system AI config now points to an existing ProviderInstance
instead of maintaining its own duplicated provider/model lists.
Legacy fallback (direct provider/model in Config) is preserved for backward compatibility.
"""
import logging
from typing import Tuple, Optional, Dict
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default fallback values (used when no config exists or on error)
DEFAULT_SYSTEM_AI_PROVIDER = "gemini"
DEFAULT_SYSTEM_AI_MODEL = "gemini-2.5-flash"


def get_system_ai_config(db: Session) -> Tuple[str, str, Optional[int]]:
    """
    Get system-level AI provider, model, and optional provider_instance_id.

    Resolution order:
      1. If system_ai_provider_instance_id is set → resolve vendor from that instance
      2. Else fall back to legacy system_ai_provider / system_ai_model columns

    Returns:
        Tuple of (provider, model_name, provider_instance_id)
        provider_instance_id is None when using legacy direct config.
    """
    try:
        from models import Config, ProviderInstance

        config = db.query(Config).first()
        if not config:
            logger.warning("No Config found in database, using defaults")
            return (DEFAULT_SYSTEM_AI_PROVIDER, DEFAULT_SYSTEM_AI_MODEL, None)

        # Preferred path: resolve from ProviderInstance
        if config.system_ai_provider_instance_id:
            instance = db.query(ProviderInstance).filter(
                ProviderInstance.id == config.system_ai_provider_instance_id,
                ProviderInstance.is_active == True,  # noqa: E712
            ).first()
            if instance:
                provider = instance.vendor
                model = config.system_ai_model or DEFAULT_SYSTEM_AI_MODEL
                logger.debug(
                    f"System AI config (instance): provider={provider}, "
                    f"model={model}, instance_id={instance.id}"
                )
                return (provider, model, instance.id)
            else:
                logger.warning(
                    f"System AI provider_instance_id={config.system_ai_provider_instance_id} "
                    "not found or inactive, falling back to legacy config"
                )

        # Legacy fallback
        provider = config.system_ai_provider or DEFAULT_SYSTEM_AI_PROVIDER
        model = config.system_ai_model or DEFAULT_SYSTEM_AI_MODEL
        logger.debug(f"System AI config (legacy): provider={provider}, model={model}")
        return (provider, model, None)

    except Exception as e:
        logger.error(f"Error loading system AI config: {e}")
        return (DEFAULT_SYSTEM_AI_PROVIDER, DEFAULT_SYSTEM_AI_MODEL, None)


def get_system_ai_config_dict(db: Session) -> Dict:
    """
    Get system AI config as a dictionary for API responses.
    Includes provider instance details when available.
    """
    provider, model, instance_id = get_system_ai_config(db)
    result = {
        "provider": provider,
        "model_name": model,
        "provider_instance_id": instance_id,
    }

    # Enrich with instance details if available
    if instance_id:
        try:
            from models import ProviderInstance
            instance = db.query(ProviderInstance).get(instance_id)
            if instance:
                result["instance_name"] = instance.instance_name
                result["vendor"] = instance.vendor
        except Exception:
            pass

    return result


async def test_system_ai_connection(
    db: Session,
    provider_instance_id: Optional[int] = None,
    model: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Dict:
    """
    Test connection to the system AI provider using a ProviderInstance.

    Args:
        db: Database session
        provider_instance_id: Provider instance to test (uses current config if not specified)
        model: Model to test (uses current config if not specified)
        tenant_id: Tenant ID for token tracking
    """
    try:
        # Resolve from current config if not specified
        if not provider_instance_id or not model:
            cfg_provider, cfg_model, cfg_instance_id = get_system_ai_config(db)
            provider_instance_id = provider_instance_id or cfg_instance_id
            model = model or cfg_model
            provider = cfg_provider
        else:
            # Resolve provider from instance
            from models import ProviderInstance
            instance = db.query(ProviderInstance).get(provider_instance_id)
            provider = instance.vendor if instance else "unknown"

        from agent.ai_client import AIClient

        token_tracker = None
        if tenant_id:
            from analytics.token_tracker import TokenTracker
            token_tracker = TokenTracker(db, tenant_id)

        client = AIClient(
            provider=provider,
            model_name=model,
            db=db,
            token_tracker=token_tracker,
            tenant_id=tenant_id,
            provider_instance_id=provider_instance_id,
        )

        result = await client.generate(
            system_prompt="You are a test assistant. Respond with exactly: OK",
            user_message="Test connection. Reply with OK.",
            operation_type="connection_test",
        )

        if result.get("error"):
            return {
                "success": False,
                "message": f"API Error: {result['error']}",
                "provider": provider,
                "model": model,
            }

        answer = result.get("answer", "")
        if "OK" in answer.upper() or len(answer) > 0:
            return {
                "success": True,
                "message": f"Successfully connected to {provider}/{model}",
                "provider": provider,
                "model": model,
                "token_usage": result.get("token_usage"),
            }
        else:
            return {
                "success": False,
                "message": f"Unexpected response from {provider}/{model}",
                "provider": provider,
                "model": model,
            }

    except ValueError as e:
        return {
            "success": False,
            "message": f"Configuration error: {e}",
            "provider": provider if 'provider' in dir() else "unknown",
            "model": model or "unknown",
            "error": str(e),
        }
    except Exception as e:
        logger.error(f"Error testing system AI connection: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Connection failed: {str(e)}",
            "provider": provider if 'provider' in dir() else "unknown",
            "model": model or "unknown",
            "error": str(e),
        }


def update_system_ai_config(
    db: Session,
    provider_instance_id: int,
    model: str,
) -> Dict:
    """
    Update system AI configuration to point to a ProviderInstance + model.

    Args:
        db: Database session
        provider_instance_id: FK to provider_instance table
        model: Model name to use from that instance
    """
    try:
        from models import Config, ProviderInstance

        # Validate instance exists and is active
        instance = db.query(ProviderInstance).filter(
            ProviderInstance.id == provider_instance_id,
            ProviderInstance.is_active == True,  # noqa: E712
        ).first()
        if not instance:
            return {
                "success": False,
                "message": f"Provider instance {provider_instance_id} not found or inactive.",
            }

        config = db.query(Config).first()
        if not config:
            return {
                "success": False,
                "message": "No Config found in database. Please run initial setup first.",
            }

        config.system_ai_provider_instance_id = provider_instance_id
        config.system_ai_provider = instance.vendor  # Keep legacy column in sync
        config.system_ai_model = model
        db.commit()

        logger.info(
            f"System AI config updated: instance={instance.instance_name} "
            f"(id={instance.id}), vendor={instance.vendor}, model={model}"
        )

        return {
            "success": True,
            "message": f"System AI set to {instance.instance_name} / {model}",
            "provider_instance_id": instance.id,
            "instance_name": instance.instance_name,
            "vendor": instance.vendor,
            "model": model,
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Error updating system AI config: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to update configuration: {str(e)}",
        }
