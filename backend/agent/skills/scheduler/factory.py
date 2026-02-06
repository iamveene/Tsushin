"""
Scheduler Provider Factory

Factory class for instantiating scheduler providers based on configuration.
Handles provider selection, integration lookup, and fallback logic.
"""

from typing import Dict, List, Optional, Type
import logging

from sqlalchemy.orm import Session

from .base import (
    SchedulerProviderBase,
    SchedulerProviderType,
    ProviderNotConfiguredError,
)
from .flows_provider import FlowsProvider

logger = logging.getLogger(__name__)


class SchedulerProviderFactory:
    """
    Factory for creating scheduler provider instances.

    Supports:
        - FlowsProvider (built-in, default)
        - GoogleCalendarProvider (requires integration)
        - AsanaProvider (requires integration)

    Usage:
        # Get default provider (Flows)
        provider = SchedulerProviderFactory.get_provider(
            provider_type="flows",
            db=db_session,
            tenant_id="tenant_123"
        )

        # Get Google Calendar provider
        provider = SchedulerProviderFactory.get_provider(
            provider_type="google_calendar",
            integration_id=5,
            db=db_session,
            tenant_id="tenant_123"
        )

        # Get provider for an agent (reads from AgentSkillIntegration)
        provider = SchedulerProviderFactory.get_provider_for_agent(
            agent_id=1,
            db=db_session
        )
    """

    # Registry of provider classes
    _providers: Dict[str, Type[SchedulerProviderBase]] = {
        SchedulerProviderType.FLOWS.value: FlowsProvider,
        # GoogleCalendarProvider and AsanaProvider will be registered when implemented
    }

    @classmethod
    def register_provider(cls, provider_type: str, provider_class: Type[SchedulerProviderBase]) -> None:
        """
        Register a new provider type.

        Args:
            provider_type: Provider type identifier (e.g., "google_calendar")
            provider_class: Provider class (must extend SchedulerProviderBase)
        """
        cls._providers[provider_type] = provider_class
        logger.info(f"Registered scheduler provider: {provider_type}")

    @classmethod
    def get_provider(
        cls,
        provider_type: str,
        db: Session,
        tenant_id: Optional[str] = None,
        integration_id: Optional[int] = None,
        agent_id: Optional[int] = None,
        config: Optional[Dict] = None,
        **kwargs
    ) -> SchedulerProviderBase:
        """
        Get a scheduler provider instance.

        Args:
            provider_type: Provider type ("flows", "google_calendar", "asana")
            db: Database session
            tenant_id: Tenant ID for multi-tenant isolation
            integration_id: Hub integration ID (required for external providers)
            agent_id: Agent ID (optional, for context)
            config: Optional configuration including permissions
            **kwargs: Additional provider-specific arguments

        Returns:
            Configured SchedulerProviderBase instance

        Raises:
            ProviderNotConfiguredError: If provider type is invalid or integration missing
        """
        # Normalize provider type
        provider_type = provider_type.lower().strip()

        # Check if provider is registered
        if provider_type not in cls._providers:
            available = list(cls._providers.keys())
            raise ProviderNotConfiguredError(
                provider_type,
                f"Unknown provider '{provider_type}'. Available: {available}"
            )

        provider_class = cls._providers[provider_type]

        # Handle built-in Flows provider (no integration needed)
        if provider_type == SchedulerProviderType.FLOWS.value:
            return provider_class(db=db, tenant_id=tenant_id, agent_id=agent_id, config=config)

        # For external providers, integration_id is required
        if not integration_id:
            raise ProviderNotConfiguredError(
                provider_type,
                f"Provider '{provider_type}' requires an integration_id"
            )

        # Verify integration exists and belongs to tenant
        from models import HubIntegration

        integration = db.query(HubIntegration).filter(
            HubIntegration.id == integration_id
        ).first()

        if not integration:
            raise ProviderNotConfiguredError(
                provider_type,
                f"Integration {integration_id} not found"
            )

        # Verify tenant access
        if tenant_id and integration.tenant_id and integration.tenant_id != tenant_id:
            raise ProviderNotConfiguredError(
                provider_type,
                f"Integration {integration_id} belongs to a different tenant"
            )

        # Create provider with integration and config
        return provider_class(
            db=db,
            tenant_id=tenant_id,
            integration_id=integration_id,
            config=config,
            **kwargs
        )

    @classmethod
    def get_provider_for_agent(
        cls,
        agent_id: int,
        db: Session,
        skill_type: str = "flows"
    ) -> SchedulerProviderBase:
        """
        Get the scheduler provider configured for a specific agent.

        Reads from AgentSkillIntegration to determine which provider and
        integration the agent uses for scheduling, including permission configuration.

        Args:
            agent_id: Agent ID
            db: Database session
            skill_type: Skill type to look up (default: "flows")

        Returns:
            Configured SchedulerProviderBase for the agent with permissions applied

        Note:
            Falls back to FlowsProvider if no configuration exists.
            Permissions default to full access (read+write) for backward compatibility.
        """
        from models import Agent

        # Get agent for tenant_id
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            logger.warning(f"Agent {agent_id} not found, using default Flows provider")
            return FlowsProvider(db=db, agent_id=agent_id)

        tenant_id = agent.tenant_id

        # Try to get skill integration configuration
        try:
            from models import AgentSkillIntegration

            skill_config = db.query(AgentSkillIntegration).filter(
                AgentSkillIntegration.agent_id == agent_id,
                AgentSkillIntegration.skill_type == skill_type
            ).first()

            if skill_config:
                provider_type = skill_config.scheduler_provider or SchedulerProviderType.FLOWS.value
                integration_id = skill_config.integration_id

                # Parse config if it's a JSON string
                import json
                config = skill_config.config or {}
                if isinstance(config, str):
                    config = json.loads(config)

                logger.info(
                    f"Agent {agent_id} scheduler config: provider={provider_type}, "
                    f"integration_id={integration_id}, permissions={config.get('permissions')}"
                )

                return cls.get_provider(
                    provider_type=provider_type,
                    db=db,
                    tenant_id=tenant_id,
                    integration_id=integration_id,
                    agent_id=agent_id,
                    config=config
                )
        except Exception as e:
            # AgentSkillIntegration table might not exist yet during migration
            logger.debug(f"Could not load AgentSkillIntegration for agent {agent_id}: {e}")

        # Default to Flows provider
        logger.info(f"Agent {agent_id} using default Flows provider")
        return FlowsProvider(db=db, tenant_id=tenant_id, agent_id=agent_id)

    @classmethod
    def get_available_providers(cls, tenant_id: Optional[str], db: Session) -> List[Dict]:
        """
        Get list of available providers for a tenant.

        Returns all registered providers with their availability status
        based on whether the tenant has configured integrations.

        Args:
            tenant_id: Tenant ID
            db: Database session

        Returns:
            List of provider info dicts:
            [
                {
                    "type": "flows",
                    "name": "Built-in Flows",
                    "description": "...",
                    "available": True,
                    "requires_integration": False,
                    "integrations": []
                },
                {
                    "type": "google_calendar",
                    "name": "Google Calendar",
                    "available": True,
                    "requires_integration": True,
                    "integrations": [
                        {"id": 5, "display_name": "Work Calendar", "email": "work@gmail.com"},
                        ...
                    ]
                },
                ...
            ]
        """
        result = []

        for provider_type, provider_class in cls._providers.items():
            info = {
                "type": provider_type,
                "name": provider_class.provider_name,
                "description": provider_class.provider_description,
                "capabilities": {
                    "end_time": provider_class.supports_end_time,
                    "location": provider_class.supports_location,
                    "attendees": provider_class.supports_attendees,
                    "recurrence": provider_class.supports_recurrence,
                    "reminders": provider_class.supports_reminders,
                    "availability": provider_class.supports_availability,
                },
                "requires_integration": provider_type != SchedulerProviderType.FLOWS.value,
                "integrations": [],
            }

            # Flows is always available
            if provider_type == SchedulerProviderType.FLOWS.value:
                info["available"] = True
            else:
                # Check for integrations
                integrations = cls._get_integrations_for_provider(
                    provider_type, tenant_id, db
                )
                info["integrations"] = integrations
                info["available"] = len(integrations) > 0

            result.append(info)

        return result

    @classmethod
    def _get_integrations_for_provider(
        cls,
        provider_type: str,
        tenant_id: Optional[str],
        db: Session
    ) -> List[Dict]:
        """
        Get available integrations for a provider type.

        Args:
            provider_type: Provider type
            tenant_id: Tenant ID
            db: Database session

        Returns:
            List of integration info dicts
        """
        from models import HubIntegration

        # Map provider type to integration type
        type_map = {
            "google_calendar": "calendar",
            "asana": "asana",
        }

        integration_type = type_map.get(provider_type)
        if not integration_type:
            return []

        # Query integrations
        query = db.query(HubIntegration).filter(
            HubIntegration.type == integration_type,
            HubIntegration.is_active == True
        )

        if tenant_id:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    HubIntegration.tenant_id == tenant_id,
                    HubIntegration.tenant_id.is_(None)  # Shared integrations
                )
            )

        integrations = query.all()

        result = []
        for integration in integrations:
            info = {
                "id": integration.id,
                "name": integration.name,
                "display_name": getattr(integration, 'display_name', None) or integration.name,
                "type": integration.type,
            }

            # Add type-specific fields
            if integration_type == "calendar":
                info["email"] = getattr(integration, 'email_address', None)
                info["calendar_id"] = getattr(integration, 'default_calendar_id', 'primary')
            elif integration_type == "asana":
                info["workspace_name"] = getattr(integration, 'workspace_name', None)
                info["workspace_gid"] = getattr(integration, 'workspace_gid', None)

            result.append(info)

        return result


# Convenience function for registering providers at module load time
def register_calendar_provider():
    """Register Google Calendar provider when available."""
    try:
        from .calendar_provider import GoogleCalendarProvider
        SchedulerProviderFactory.register_provider(
            SchedulerProviderType.GOOGLE_CALENDAR.value,
            GoogleCalendarProvider
        )
    except ImportError:
        logger.debug("GoogleCalendarProvider not available")


def register_asana_provider():
    """Register Asana provider when available."""
    try:
        from .asana_provider import AsanaProvider
        SchedulerProviderFactory.register_provider(
            SchedulerProviderType.ASANA.value,
            AsanaProvider
        )
    except ImportError:
        logger.debug("AsanaProvider not available")


# Auto-register providers when module is imported
# (providers will be registered when their files are created)
