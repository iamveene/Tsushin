"""
Web Search Skill - Search the web using pluggable providers.

Uses the SearchProviderRegistry to support multiple providers:
- Brave Search: Fast, privacy-focused (default)
- Google Search: Coming soon
- Bing Search: Coming soon
"""

import logging
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseSkill, InboundMessage, SkillResult
from hub.providers import SearchProviderRegistry, SearchRequest
from hub.providers.search_provider import SearchResponse, SearchResult


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
    execution_mode = "tool"

    def _resolve_tenant_id(self) -> Optional[str]:
        """Resolve tenant_id from agent context for API key lookups."""
        agent_id = getattr(self, '_agent_id', None)
        if agent_id and self._db_session:
            try:
                from models import Agent
                agent = self._db_session.query(Agent).filter(Agent.id == agent_id).first()
                if agent:
                    return agent.tenant_id
            except Exception:
                pass
        return None

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

    @staticmethod
    def _reference_now() -> datetime:
        return datetime.now(ZoneInfo("America/Sao_Paulo"))

    def _normalize_relative_dates(self, text: str) -> str:
        """Expand relative date phrases into explicit dates or ranges."""
        now = self._reference_now()
        normalized = text

        replacements = {
            r"\bhoje\b": now.strftime("%d/%m/%Y"),
            r"\btoday\b": now.strftime("%Y-%m-%d"),
            r"\bontem\b": (now - timedelta(days=1)).strftime("%d/%m/%Y"),
            r"\byesterday\b": (now - timedelta(days=1)).strftime("%Y-%m-%d"),
        }

        start_of_week = now - timedelta(days=now.weekday())
        last_week_start = start_of_week - timedelta(days=7)
        last_week_end = start_of_week - timedelta(days=1)
        replacements[r"\bsemana passada\b"] = (
            f"semana de {last_week_start.strftime('%d/%m/%Y')} "
            f"a {last_week_end.strftime('%d/%m/%Y')}"
        )
        replacements[r"\blast week\b"] = (
            f"week from {last_week_start.strftime('%Y-%m-%d')} "
            f"to {last_week_end.strftime('%Y-%m-%d')}"
        )

        for pattern, replacement in replacements.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

        return normalized

    async def _get_agent_ai_client(self):
        """Create an AI client using the agent's configured LLM."""
        from agent.ai_client import AIClient
        from models import Agent

        provider = 'gemini'
        model = 'gemini-2.5-flash'

        if self._db_session and hasattr(self, '_agent_id') and self._agent_id:
            agent = self._db_session.query(Agent).filter(Agent.id == self._agent_id).first()
            if agent:
                provider = agent.model_provider or 'gemini'
                model = agent.model_name or 'gemini-2.5-flash'
                logger.debug(f"Using agent's LLM: {provider}/{model}")

        return AIClient(
            provider=provider,
            model_name=model,
            db=self._db_session,
            token_tracker=self._token_tracker,
            tenant_id=self._resolve_tenant_id()
        )

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

            # BUG-341: Normalize provider alias — "serpapi" is served by the "google" registry key
            PROVIDER_ALIASES = {"serpapi": "google"}
            provider_name = PROVIDER_ALIASES.get(provider_name, provider_name)

            tenant_id = config.get("tenant_id")

            # BUG-333: Check if any search provider integration is configured at all
            available = SearchProviderRegistry.get_available_providers()
            if not available:
                return SkillResult(
                    success=False,
                    output=(
                        "Web search is not configured for this agent. "
                        "Please set up a search provider in the Hub (Settings > Hub > Web Search) "
                        "and link it to this agent's skill integrations."
                    ),
                    metadata={'error': 'no_providers_available'}
                )

            # Get provider instance from registry (with tenant_id for API key lookup)
            provider = SearchProviderRegistry.get_provider(
                provider_name,
                db=self._db_session,
                token_tracker=self.token_tracker,
                tenant_id=tenant_id
            )

            if not provider:
                # BUG-333: Friendly message when provider exists in registry but not linked/configured
                return SkillResult(
                    success=False,
                    output=(
                        f"Web search is not configured for this agent. "
                        f"Please set up a search provider in the Hub (Settings > Hub > Web Search) "
                        f"and link it to this agent's skill integrations. "
                        f"Available providers: {', '.join(available)}"
                    ),
                    metadata={'error': 'provider_not_found', 'available_providers': available}
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
            logger.info(f"🔍 Web search: provider={provider_name}, query={query.strip()[:120]}")
            print(f"🔍 Web search: provider={provider_name}, query={query.strip()[:120]}", flush=True)
            response = await provider.search(request)

            if not response.success:
                # BUG-333: Detect unconfigured API key scenario and surface a helpful message
                error_lower = (response.error or "").lower()
                if "api key not configured" in error_lower or "not configured" in error_lower:
                    return SkillResult(
                        success=False,
                        output=(
                            "Web search is not configured for this agent. "
                            "Please set up a search provider in the Hub (Settings > Hub > Web Search) "
                            "and link it to this agent's skill integrations."
                        ),
                        metadata={'error': 'api_key_not_configured', 'provider': provider_name}
                    )
                return SkillResult(
                    success=False,
                    output=f"❌ Search failed: {response.error}",
                    metadata={'error': response.error, 'provider': provider_name}
                )

            return await self._build_search_result(
                message=message,
                config=config,
                query=query,
                provider_name=provider_name,
                response=response
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
            ai_client = await self._get_agent_ai_client()

            system_prompt = """You are a search query extractor. Parse user requests and return ONLY the search query, nothing else."""

            user_prompt = f"""Extract the search query from this message. Return ONLY the search query text, nothing else.

Current date in Sao Paulo, Brazil: {self._reference_now().strftime("%Y-%m-%d")}
If the user uses relative dates like today, yesterday, or last week, resolve them to absolute dates in the query.

Examples:
- "Search for best restaurants in New York" → best restaurants in New York
- "Pesquise sobre inteligência artificial" → inteligência artificial
- "Can you look up weather in London?" → weather in London
- "Find information about Python programming" → Python programming
- "quais os numeros da megasena da semana passada" → números mega-sena semana de 06/04/2026 a 12/04/2026

User message: "{message}"

Search query:"""

            response = await ai_client.generate(system_prompt, user_prompt)

            if response.get('error'):
                logger.error(f"AI query extraction error: {response['error']}")
                # Fallback: use the original message with search keywords removed
                return self._simple_query_extraction(message)

            query = response.get('answer', '').strip()

            if query and len(query) > 2:
                query = self._normalize_relative_dates(query)
                logger.info(f"Extracted search query: {query}")
                return query

            # Fallback
            return self._simple_query_extraction(message)
        except Exception as e:
            logger.error(f"Query extraction failed: {e}", exc_info=True)
            return self._simple_query_extraction(message)

    @staticmethod
    def _compact_result(result: SearchResult) -> Dict[str, str]:
        return {
            'title': result.title,
            'url': result.url,
            'description': result.description or ''
        }

    def _fallback_answer_from_results(self, query: str, response: SearchResponse) -> str:
        """Return a concise, direct answer without relying on another LLM call."""
        if not response.results:
            return f"Não encontrei resultados relevantes para: {query}"

        top = response.results[0]
        summary = (top.description or top.title or "").strip()
        if not summary:
            summary = f"Encontrei resultados sobre: {query}"

        lines = [summary]
        source_count = min(2, len(response.results))
        if source_count > 0:
            lines.append("")
            lines.append("Fontes:")
            for result in response.results[:source_count]:
                lines.append(f"- {result.title}: {result.url}")
        return "\n".join(lines)

    def _extract_lottery_numbers_from_results(
        self,
        original_message: str,
        response: SearchResponse,
    ) -> Optional[str]:
        """Extract obvious lottery number sequences directly from snippets."""
        message_lower = original_message.lower()
        if not any(token in message_lower for token in ["mega-sena", "megasena", "dezenas", "números", "numeros"]):
            return None

        number_sequence_pattern = re.compile(r"(?<!\d)(\d{1,2}(?:[\s,.-]+\d{1,2}){5})(?!\d)")

        for result in response.results[:5]:
            haystack = " ".join(part for part in [result.title, result.description or ""] if part)
            match = number_sequence_pattern.search(haystack)
            if not match:
                continue

            raw_numbers = re.findall(r"\d{1,2}", match.group(1))
            if len(raw_numbers) != 6:
                continue

            numbers = ", ".join(num.zfill(2) for num in raw_numbers)
            source_lines = [
                f"- {src.title}: {src.url}"
                for src in response.results[:2]
            ]
            return (
                f"Os números encontrados foram: {numbers}\n\n"
                f"Fontes:\n" + "\n".join(source_lines)
            )

        return None

    async def _synthesize_answer_from_results(
        self,
        original_message: str,
        query: str,
        response: SearchResponse,
    ) -> Optional[str]:
        """Turn raw search results into a direct answer with a small source list."""
        if not response.results:
            return None

        try:
            ai_client = await self._get_agent_ai_client()
            results_payload = "\n\n".join(
                [
                    f"Result {idx}:\n"
                    f"Title: {result.title}\n"
                    f"URL: {result.url}\n"
                    f"Snippet: {result.description or '(none)'}"
                    for idx, result in enumerate(response.results[:5], 1)
                ]
            )

            system_prompt = (
                "You answer user questions using web search results.\n"
                "Rules:\n"
                "- Answer in the same language as the user.\n"
                "- Give the direct answer first, in 1-3 short sentences.\n"
                "- Use only the provided search results.\n"
                "- Respect the exact time period asked by the user. Do not silently replace it with a newer or older period.\n"
                "- If the answer is uncertain or partial, say so plainly.\n"
                "- If the user asks for numbers, values, dates, names, or versions and they appear in the results, include them explicitly.\n"
                "- After the answer, include 'Fontes:' and 1-2 source links.\n"
                "- Keep the response compact and natural for chat apps.\n"
                "- Do not dump all search results.\n"
            )

            user_prompt = (
                f"Original user message: {original_message}\n"
                f"Search query used: {query}\n\n"
                f"Search results:\n{results_payload}\n\n"
                "Write the final answer for the user now."
            )

            synthesis = await ai_client.generate(system_prompt, user_prompt)
            if synthesis.get('error'):
                logger.warning(f"Search answer synthesis error: {synthesis['error']}")
                return None

            answer = (synthesis.get('answer') or "").strip()
            return answer or None
        except Exception as e:
            logger.warning(f"Search answer synthesis failed: {e}")
            return None

    async def _build_search_result(
        self,
        message: InboundMessage,
        config: Dict[str, Any],
        query: str,
        provider_name: str,
        response: SearchResponse,
    ) -> SkillResult:
        """Format provider output into a direct end-user answer."""
        lottery_numbers = self._extract_lottery_numbers_from_results(message.body, response)
        if lottery_numbers:
            formatted_output = lottery_numbers
        else:
            synthesized = await self._synthesize_answer_from_results(
                original_message=message.body,
                query=query,
                response=response,
            )
            formatted_output = synthesized or self._fallback_answer_from_results(query, response)

        return SkillResult(
            success=True,
            output=formatted_output,
            metadata={
                'query': query,
                'provider': provider_name,
                'result_count': response.result_count,
                'request_time_ms': response.request_time_ms,
                'results': [self._compact_result(r) for r in response.results],
                'presentation': 'direct_answer_with_sources'
            }
        )

    def _simple_query_extraction(self, message: str) -> Optional[str]:
        """
        Simple fallback for query extraction without AI.
        Removes common search trigger words and returns the rest.

        Args:
            message: Original message

        Returns:
            Cleaned query or None
        """
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
        query = self._normalize_relative_dates(query)
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
            "keywords": [],
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

            # BUG-341: Normalize provider alias — "serpapi" is served by the "google" registry key
            PROVIDER_ALIASES = {"serpapi": "google"}
            provider_name = PROVIDER_ALIASES.get(provider_name, provider_name)

            tenant_id = config.get("tenant_id")

            # BUG-333: Check if any search provider integration is configured at all
            available = SearchProviderRegistry.get_available_providers()
            if not available:
                return SkillResult(
                    success=False,
                    output=(
                        "Web search is not configured for this agent. "
                        "Please set up a search provider in the Hub (Settings > Hub > Web Search) "
                        "and link it to this agent's skill integrations."
                    ),
                    metadata={"error": "no_providers_available"}
                )

            # Get provider instance from registry (with tenant_id for API key lookup)
            provider = SearchProviderRegistry.get_provider(
                provider_name,
                db=self._db_session,
                token_tracker=self.token_tracker,
                tenant_id=tenant_id
            )

            if not provider:
                # BUG-333: Friendly message when provider not found
                return SkillResult(
                    success=False,
                    output=(
                        "Web search is not configured for this agent. "
                        "Please set up a search provider in the Hub (Settings > Hub > Web Search) "
                        "and link it to this agent's skill integrations. "
                        f"Available providers: {', '.join(available)}"
                    ),
                    metadata={"error": "provider_not_found", "available_providers": available}
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
            logger.info(f"🔍 Web search: provider={provider_name}, query={query.strip()[:120]}")
            print(f"🔍 Web search: provider={provider_name}, query={query.strip()[:120]}", flush=True)
            response = await provider.search(request)

            if not response.success:
                # BUG-333: Detect unconfigured API key scenario and surface a helpful message
                error_lower = (response.error or "").lower()
                if "api key not configured" in error_lower or "not configured" in error_lower:
                    return SkillResult(
                        success=False,
                        output=(
                            "Web search is not configured for this agent. "
                            "Please set up a search provider in the Hub (Settings > Hub > Web Search) "
                            "and link it to this agent's skill integrations."
                        ),
                        metadata={"error": "api_key_not_configured", "provider": provider_name}
                    )
                return SkillResult(
                    success=False,
                    output=f"Search failed: {response.error}",
                    metadata={"error": response.error, "provider": provider_name}
                )

            return await self._build_search_result(
                message=message,
                config=config,
                query=query,
                provider_name=provider_name,
                response=response
            )

        except Exception as e:
            logger.error(f"SearchSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error performing search: {str(e)}",
                metadata={"error": str(e)}
            )
