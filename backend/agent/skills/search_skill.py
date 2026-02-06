"""
Web Search Skill - Search the web using pluggable providers.

Uses the SearchProviderRegistry to support multiple providers:
- Brave Search: Fast, privacy-focused (default)
- Google Search: Coming soon
- Bing Search: Coming soon
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from .base import BaseSkill, InboundMessage, SkillResult
from hub.providers import SearchProviderRegistry, SearchRequest


logger = logging.getLogger(__name__)


class SearchSkill(BaseSkill):
    """
    Multi-provider Web Search: Search the internet for information.

    When triggered by search-related keywords, this skill performs web searches
    using the configured provider and returns formatted results.

    PROVIDERS (via SearchProviderRegistry):
    - Brave Search: Fast and privacy-focused (default)
    - Google Search: Coming soon
    - Bing Search: Coming soon

    Configuration:
    {
        "provider": "brave",           # "brave", "google", or "bing"
        "max_results": 5,              # Number of results (1-20)
        "language": "en",              # Search language preference
        "country": "US",               # Search country preference
        "safe_search": true,           # Enable safe search filtering
        "keywords": [...],             # Trigger keywords
        "use_ai_fallback": true,       # Use AI to verify search intent
        "execution_mode": "hybrid"     # "tool", "legacy", or "hybrid"
    }

    Skills-as-Tools (Phase 2):
    - Tool name: web_search
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    """

    skill_type = "web_search"
    skill_name = "Web Search"
    skill_description = "Search the web using Brave Search (default provider)"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    def __init__(self, db: Optional[Session] = None, token_tracker=None):
        """
        Initialize search skill.

        Args:
            db: Database session for API key loading
            token_tracker: TokenTracker for usage tracking
        """
        super().__init__()
        # Use BaseSkill's standard _db_session attribute
        if db:
            self._db_session = db
        self.token_tracker = token_tracker

        # Initialize providers
        SearchProviderRegistry.initialize_providers()

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Detect if message contains search intent.

        Looks for search-related keywords in multiple languages.

        Args:
            message: Inbound message

        Returns:
            True if message is about web search
        """
        # Skills-as-Tools: If in tool-only mode, don't handle via keywords
        config = getattr(self, '_config', {}) or self.get_default_config()
        if not self.is_legacy_enabled(config):
            return False

        text = message.body.lower()
        keywords = config.get('keywords', self.get_default_config()['keywords'])
        use_ai_fallback = config.get('use_ai_fallback', True)

        # Step 1: Keyword pre-filter
        has_keywords = self._keyword_matches(message.body, keywords)

        if not has_keywords:
            logger.debug(f"SearchSkill: No keyword match in '{text[:50]}...'")
            return False

        logger.info(f"SearchSkill: Keywords matched in '{text[:50]}...'")

        # Step 2: AI fallback (optional, for intent verification)
        if use_ai_fallback:
            result = await self._ai_classify(message.body, config)
            logger.info(f"SearchSkill: AI classification result={result}")
            return result

        return True

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process search request using configured provider.

        Steps:
        1. Extract search query from message
        2. Get provider from config (default: brave)
        3. Call provider's search API
        4. Format and return results

        Args:
            message: Inbound message with search request
            config: Skill configuration

        Returns:
            SkillResult with search results
        """
        try:
            logger.info(f"SearchSkill: Processing message: {message.body}")

            # Get provider from config (default to brave)
            provider_name = config.get("provider", "brave").lower()
            tenant_id = config.get("tenant_id")

            # Get provider instance from registry (with tenant_id for API key lookup)
            provider = SearchProviderRegistry.get_provider(
                provider_name,
                db=self._db_session,
                token_tracker=self.token_tracker,
                tenant_id=tenant_id
            )

            if not provider:
                # Try to give helpful error message
                available = SearchProviderRegistry.get_available_providers()
                if available:
                    return SkillResult(
                        success=False,
                        output=f"❌ Search provider '{provider_name}' not available. Available providers: {', '.join(available)}",
                        metadata={'error': 'provider_not_found', 'available_providers': available}
                    )
                return SkillResult(
                    success=False,
                    output="❌ No search providers are configured. Please configure a search API key in Studio → API Keys.",
                    metadata={'error': 'no_providers_available'}
                )

            # Extract search query using AI
            query = await self._extract_search_query(message.body, config)

            if not query:
                return SkillResult(
                    success=False,
                    output="❌ Could not extract a search query from your message. Please be more specific about what you want to search for.",
                    metadata={'error': 'query_extraction_failed'}
                )

            # Create search request
            max_results = config.get('max_results', 5)
            request = SearchRequest(
                query=query,
                count=max_results,
                language=config.get('language', 'en'),
                country=config.get('country', 'US'),
                safe_search=config.get('safe_search', True),
                agent_id=getattr(self, '_agent_id', None),
                sender_key=message.sender_key,
                message_id=message.id
            )

            # Perform search
            response = await provider.search(request)

            if not response.success:
                return SkillResult(
                    success=False,
                    output=f"❌ Search failed: {response.error}",
                    metadata={'error': response.error, 'provider': provider_name}
                )

            # Format results
            formatted_output = response.format_results()

            return SkillResult(
                success=True,
                output=formatted_output,
                metadata={
                    'query': query,
                    'provider': provider_name,
                    'result_count': response.result_count,
                    'request_time_ms': response.request_time_ms,
                    'results': [
                        {'title': r.title, 'url': r.url, 'description': r.description}
                        for r in response.results
                    ]
                }
            )

        except Exception as e:
            logger.error(f"SearchSkill error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error performing search: {str(e)}",
                metadata={'error': str(e)}
            )

    async def _extract_search_query(self, message: str, config: Dict[str, Any]) -> Optional[str]:
        """
        Extract search query from natural language message using AI.

        Args:
            message: Natural language message
            config: Skill configuration

        Returns:
            Search query string or None if extraction fails
        """
        try:
            from agent.ai_client import AIClient
            from models import Agent

            # Get agent's LLM configuration from database
            provider = 'gemini'
            model = 'gemini-2.5-flash'

            if self._db_session and hasattr(self, '_agent_id') and self._agent_id:
                agent = self._db_session.query(Agent).filter(Agent.id == self._agent_id).first()
                if agent:
                    provider = agent.model_provider or 'gemini'
                    model = agent.model_name or 'gemini-2.5-flash'
                    logger.debug(f"Using agent's LLM: {provider}/{model}")

            # Create AI client for parsing using agent's configured LLM
            ai_client = AIClient(
                provider=provider,
                model_name=model,
                db=self._db_session
            )

            system_prompt = """You are a search query extractor. Parse user requests and return ONLY the search query, nothing else."""

            user_prompt = f"""Extract the search query from this message. Return ONLY the search query text, nothing else.

Examples:
- "Search for best restaurants in New York" → best restaurants in New York
- "Pesquise sobre inteligência artificial" → inteligência artificial
- "Can you look up weather in London?" → weather in London
- "Find information about Python programming" → Python programming

User message: "{message}"

Search query:"""

            response = await ai_client.generate(system_prompt, user_prompt)

            if response.get('error'):
                logger.error(f"AI query extraction error: {response['error']}")
                # Fallback: use the original message with search keywords removed
                return self._simple_query_extraction(message)

            query = response.get('answer', '').strip()

            if query and len(query) > 2:
                logger.info(f"Extracted search query: {query}")
                return query

            # Fallback
            return self._simple_query_extraction(message)

        except Exception as e:
            logger.error(f"Query extraction failed: {e}", exc_info=True)
            return self._simple_query_extraction(message)

    def _simple_query_extraction(self, message: str) -> Optional[str]:
        """
        Simple fallback for query extraction without AI.
        Removes common search trigger words and returns the rest.

        Args:
            message: Original message

        Returns:
            Cleaned query or None
        """
        import re

        # Remove common trigger phrases
        patterns = [
            r'^(search\s+for|search|look\s+up|find|busque|pesquise|procure)\s+',
            r'^(can\s+you\s+|could\s+you\s+|please\s+)',
            r'(\?|\.)$',
        ]

        query = message.lower()
        for pattern in patterns:
            query = re.sub(pattern, '', query, flags=re.IGNORECASE)

        query = query.strip()
        return query if len(query) > 2 else None

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for search skill.

        Returns:
            Default config dict
        """
        return {
            "provider": "brave",  # Default provider
            "keywords": [
                # English
                "search", "search for", "look up", "find", "google",
                "what is", "who is", "how to", "define",
                # Portuguese
                "busque", "buscar", "pesquise", "pesquisar", "procure", "procurar",
                "o que é", "quem é", "como fazer", "definição"
            ],
            "use_ai_fallback": True,
            "ai_model": "gemini-2.5-flash",
            "max_results": 5,
            "language": "en",
            "country": "US",
            "safe_search": True
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for skill configuration.

        Returns:
            Config schema dict
        """
        # Get available providers for enum
        SearchProviderRegistry.initialize_providers()
        available_providers = SearchProviderRegistry.get_available_providers()

        return {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": available_providers if available_providers else ["brave"],
                    "description": "Search provider to use",
                    "default": "brave"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords that trigger web search"
                },
                "use_ai_fallback": {
                    "type": "boolean",
                    "description": "Use AI to verify intent after keyword match",
                    "default": True
                },
                "ai_model": {
                    "type": "string",
                    "description": "AI model for intent classification",
                    "default": "gemini-2.5-flash"
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "Maximum number of search results",
                    "default": 5
                },
                "language": {
                    "type": "string",
                    "description": "Search language preference (e.g., 'en', 'pt')",
                    "default": "en"
                },
                "country": {
                    "type": "string",
                    "description": "Search country preference (e.g., 'US', 'BR')",
                    "default": "US"
                },
                "safe_search": {
                    "type": "boolean",
                    "description": "Enable safe search filtering",
                    "default": True
                },
                "execution_mode": {
                    "type": "string",
                    "enum": ["tool", "legacy", "hybrid"],
                    "description": "Execution mode: tool (AI decides), legacy (keywords only), hybrid (both)",
                    "default": "hybrid"
                }
            }
        }

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION (Phase 2)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        Return MCP-compliant tool definition for web search.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools
        """
        return {
            "name": "web_search",
            "title": "Web Search",
            "description": (
                "Search the web for information. Use when user asks to search for something, "
                "find information, look something up, or needs current data from the internet."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to execute"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (1-20)",
                        "default": 5
                    }
                },
                "required": ["query"]
            },
            "annotations": {
                "destructive": False,
                "idempotent": True,
                "audience": ["user", "assistant"]
            }
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Provides Sentinel with information about expected web search usage
        to prevent false positives on legitimate searches.
        """
        return {
            "expected_intents": [
                "Search the web for information",
                "Find data online",
                "Look up facts and information"
            ],
            "expected_patterns": [
                "search", "find", "look up", "google", "what is", "who is",
                "busque", "pesquise", "procure"
            ],
            "risk_notes": (
                "Flag searches for illegal content, weapons manufacturing, "
                "harmful information, or excessive search volume (potential abuse)."
            )
        }

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute web search as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - query: The search query (required)
                - max_results: Maximum results to return (optional, default 5)
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with search results
        """
        query = arguments.get("query")
        max_results = arguments.get("max_results", config.get("max_results", 5))

        if not query:
            return SkillResult(
                success=False,
                output="Search query is required",
                metadata={"error": "missing_query"}
            )

        try:
            logger.info(f"SearchSkill.execute_tool: query='{query}', max_results={max_results}")

            # Get provider from config (default to brave)
            provider_name = config.get("provider", "brave").lower()
            tenant_id = config.get("tenant_id")

            # Get provider instance from registry (with tenant_id for API key lookup)
            provider = SearchProviderRegistry.get_provider(
                provider_name,
                db=self._db_session,
                token_tracker=self.token_tracker,
                tenant_id=tenant_id
            )

            if not provider:
                available = SearchProviderRegistry.get_available_providers()
                if available:
                    return SkillResult(
                        success=False,
                        output=f"Search provider '{provider_name}' not available. Available: {', '.join(available)}",
                        metadata={"error": "provider_not_found", "available_providers": available}
                    )
                return SkillResult(
                    success=False,
                    output="No search providers configured. Configure a search API key in Studio → API Keys.",
                    metadata={"error": "no_providers_available"}
                )

            # Create search request
            request = SearchRequest(
                query=query,
                count=max_results,
                language=config.get("language", "en"),
                country=config.get("country", "US"),
                safe_search=config.get("safe_search", True),
                agent_id=getattr(self, "_agent_id", None),
                sender_key=message.sender_key,
                message_id=message.id
            )

            # Perform search
            response = await provider.search(request)

            if not response.success:
                return SkillResult(
                    success=False,
                    output=f"Search failed: {response.error}",
                    metadata={"error": response.error, "provider": provider_name}
                )

            # Format results
            formatted_output = response.format_results()

            return SkillResult(
                success=True,
                output=formatted_output,
                metadata={
                    "query": query,
                    "provider": provider_name,
                    "result_count": response.result_count,
                    "request_time_ms": response.request_time_ms,
                    "results": [
                        {"title": r.title, "url": r.url, "description": r.description}
                        for r in response.results
                    ]
                }
            )

        except Exception as e:
            logger.error(f"SearchSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error performing search: {str(e)}",
                metadata={"error": str(e)}
            )
