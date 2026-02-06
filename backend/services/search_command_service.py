"""
Search Command Service

Handles /search slash command operations:
- /search "query"     - Search the web

Uses SearchProviderRegistry for direct execution (zero AI tokens).
"""

import logging
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SearchCommandService:
    """
    Service for executing search slash commands.

    Provides programmatic access to web search functionality without AI involvement.
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def _get_search_provider(self, agent_id: int, tenant_id: str = None):
        """
        Get search provider based on agent's skill config.

        Returns the configured provider or defaults to brave.
        Raises ValueError if no provider is available.
        """
        from hub.providers import SearchProviderRegistry

        # Initialize providers
        SearchProviderRegistry.initialize_providers()

        # Get agent's search skill config
        provider_name = "brave"  # default
        max_results = 5
        language = "en"
        country = "US"
        safe_search = True

        # Get tenant_id from agent if not provided
        if not tenant_id:
            try:
                from models import Agent
                agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                if agent:
                    tenant_id = agent.tenant_id
            except Exception:
                pass

        try:
            from models import AgentSkill

            skill = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_type == "web_search",
                AgentSkill.is_enabled == True
            ).first()

            if skill and skill.config:
                provider_name = skill.config.get('provider', 'brave')
                max_results = skill.config.get('max_results', 5)
                language = skill.config.get('language', 'en')
                country = skill.config.get('country', 'US')
                safe_search = skill.config.get('safe_search', True)
        except Exception as e:
            self.logger.warning(f"Could not get search skill config: {e}")

        # Get provider instance (with tenant_id for API key lookup)
        provider = SearchProviderRegistry.get_provider(provider_name, db=self.db, tenant_id=tenant_id)

        if not provider:
            # Try default provider
            default_provider = SearchProviderRegistry.get_default_provider()
            if default_provider:
                provider = SearchProviderRegistry.get_provider(default_provider, db=self.db, tenant_id=tenant_id)

        if not provider:
            available = SearchProviderRegistry.get_available_providers()
            if available:
                raise ValueError(
                    f"Search provider '{provider_name}' not configured. "
                    f"Available providers: {', '.join(available)}. "
                    "Configure API key in Studio -> API Keys."
                )
            raise ValueError(
                "No search providers configured. "
                "Add a Brave Search or SerpAPI key in Studio -> API Keys."
            )

        return provider, {
            'max_results': max_results,
            'language': language,
            'country': country,
            'safe_search': safe_search
        }

    async def execute_search(
        self,
        tenant_id: str,
        agent_id: int,
        query: str,
        count: Optional[int] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search the web for a query.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            query: Search query string
            count: Number of results (overrides skill config)
        """
        try:
            if not query or not query.strip():
                return {
                    "status": "error",
                    "action": "search",
                    "message": (
                        "Please specify a search query.\n\n"
                        "**Usage:** `/search \"query\"`\n\n"
                        "**Examples:**\n"
                        "- `/search \"best python libraries 2024\"`\n"
                        "- `/search \"weather API documentation\"`\n"
                        "- `/search \"latest AI news\"`"
                    )
                }

            provider, config = self._get_search_provider(agent_id)

            # Create search request
            from hub.providers import SearchRequest

            max_results = count if count else config['max_results']

            request = SearchRequest(
                query=query.strip(),
                count=max_results,
                language=config['language'],
                country=config['country'],
                safe_search=config['safe_search'],
                agent_id=agent_id
            )

            # Perform search
            response = await provider.search(request)

            if not response.success:
                return {
                    "status": "error",
                    "action": "search",
                    "query": query,
                    "error": response.error,
                    "message": f"Search failed: {response.error}"
                }

            # Format results
            formatted = response.format_results()

            return {
                "status": "success",
                "action": "search",
                "query": query,
                "provider": provider.__class__.__name__.replace('SearchProvider', '').lower(),
                "result_count": response.result_count,
                "results": [
                    {'title': r.title, 'url': r.url, 'description': r.description}
                    for r in response.results
                ],
                "message": formatted
            }

        except ValueError as e:
            return {
                "status": "error",
                "action": "search",
                "error": str(e),
                "message": f"{str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error in execute_search: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "search",
                "error": str(e),
                "message": f"Search failed: {str(e)}"
            }
