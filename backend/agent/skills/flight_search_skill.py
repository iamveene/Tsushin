"""
Flight Search Skill - Provider-Agnostic
Allows agents to search for flights using configured provider (Amadeus, Skyscanner, etc.).
"""

import logging
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session

from .base import BaseSkill, InboundMessage, SkillResult
from hub.providers import FlightProviderRegistry
from hub.providers.flight_search_provider import FlightSearchRequest


logger = logging.getLogger(__name__)


class FlightSearchSkill(BaseSkill):
    """
    Provider-agnostic flight search skill.
    Delegates to configured provider (Amadeus, Skyscanner, etc.).

    Skills-as-Tools (Phase 3):
    - Tool name: search_flights
    - Execution mode: hybrid (supports both tool and legacy keyword modes)

    The provider is selected per-agent via agent configuration:
    agent.config = {
        "skills": {
            "flight_search": {
                "enabled": true,
                "provider": "amadeus",  # or "skyscanner", "google_flights"
                "settings": {
                    "default_currency": "BRL",
                    "max_results": 5
                }
            }
        }
    }
    """

    skill_type = "flight_search"
    skill_name = "Flight Search"
    skill_description = "Search for flights using configured provider (Amadeus, Skyscanner, etc.)"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    def __init__(self, db: Optional[Session] = None, provider_name: str = "amadeus"):
        """
        Initialize flight search skill.

        Args:
            db: Database session (optional, will be set via set_db_session by SkillManager)
            provider_name: Provider to use (default: "amadeus")
        """
        super().__init__()
        # If db is passed during construction, set it via BaseSkill's _db_session
        # This maintains compatibility with both direct instantiation and SkillManager
        if db:
            self._db_session = db
        self.provider_name = provider_name
        self.provider = None
        self._provider_tenant_id = None

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Detect if message contains flight search intent.

        Looks for flight-related keywords in multiple languages.

        Args:
            message: Inbound message

        Returns:
            True if message is about flight search
        """
        # Skills-as-Tools: If in tool-only mode, don't handle via keywords
        config = getattr(self, '_config', {}) or self.get_default_config()
        if not self.is_legacy_enabled(config):
            return False

        text = message.body.lower()

        # Get configuration
        keywords = config.get('keywords', self.get_default_config()['keywords'])
        use_ai_fallback = config.get('use_ai_fallback', True)

        # Step 1: Keyword pre-filter
        has_keywords = self._keyword_matches(message.body, keywords)

        if not has_keywords:
            logger.debug(f"FlightSearchSkill: No keyword match in '{text[:50]}...'")
            return False

        logger.info(f"FlightSearchSkill: Keywords matched in '{text[:50]}...'")

        # Step 2: AI fallback (optional, for intent verification)
        if use_ai_fallback:
            result = await self._ai_classify(message.body, config)
            logger.info(f"FlightSearchSkill: AI classification result={result}")
            return result

        return True

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process flight search request.

        Steps:
        1. Extract flight parameters from message (origin, destination, dates)
        2. Get configured provider
        3. Execute search via provider
        4. Format and return results

        Args:
            message: Inbound message with flight search request
            config: Skill configuration

        Returns:
            SkillResult with flight search results
        """
        try:
            logger.info(f"FlightSearchSkill: Processing message: {message.body}")

            # Get database session
            if not self._db_session:
                from sqlalchemy.orm import sessionmaker
                from db import get_engine
                import os

                engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
                SessionLocal = sessionmaker(bind=engine)
                self._db_session = SessionLocal()

            # Get provider configuration
            provider_name = config.get('provider', self.provider_name)
            provider_settings = config.get('settings', {})

            # Initialize provider
            provider = await self._get_provider(provider_name)
            if not provider:
                return SkillResult(
                    success=True,
                    output=f"❌ Flight search provider '{provider_name}' is not configured. Please configure it in the Hub settings.",
                    metadata={
                        'error': 'provider_not_configured',
                        'skip_ai': True,
                        'provider': provider_name
                    }
                )

            # Extract flight parameters using AI
            parameters = await self._extract_flight_parameters(message.body)

            if not parameters:
                return SkillResult(
                    success=False,
                    output="❌ Could not understand flight search request. Please include: origin city, destination city, and date.",
                    metadata={'error': 'parameter_extraction_failed'}
                )

            # Execute flight search
            result = await self.search_flights_direct(
                origin=parameters.get('origin'),
                destination=parameters.get('destination'),
                departure_date=parameters.get('departure_date'),
                return_date=parameters.get('return_date'),
                adults=parameters.get('adults', 1),
                currency=parameters.get('currency', provider_settings.get('default_currency', 'BRL')),
                max_results=provider_settings.get('max_results', 5),
                provider_name=provider_name
            )

            if result['success']:
                return SkillResult(
                    success=True,
                    output=result['output'],
                    metadata={
                        'provider': provider_name,
                        'offers_count': len(result['offers']),
                        'parameters': parameters
                    }
                )
            else:
                return SkillResult(
                    success=True,
                    output=result.get('output') or f"❌ Flight search failed: {result.get('error', 'Unknown error')}",
                    metadata={
                        'error': result.get('error'),
                        'provider': provider_name,
                        'parameters': parameters,
                        'skip_ai': True
                    }
                )

        except Exception as e:
            logger.error(f"FlightSearchSkill error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error searching flights: {str(e)}",
                metadata={'error': str(e)}
            )

    async def search_flights_direct(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        currency: str = "BRL",
        max_results: int = 5,
        provider_name: Optional[str] = None
    ) -> Dict:
        """
        Direct flight search method (bypassing message processing).

        Use this method when you have structured parameters and want
        to skip natural language parsing.

        Args:
            origin: Origin airport IATA code (e.g., "GRU")
            destination: Destination airport IATA code (e.g., "JFK")
            departure_date: Departure date in YYYY-MM-DD format
            return_date: Return date in YYYY-MM-DD format (optional)
            adults: Number of adult passengers
            currency: Currency code (default: "BRL")
            max_results: Maximum number of results (default: 5)
            provider_name: Override provider (default: use configured provider)

        Returns:
            Dict with search results or error

        Example:
            skill = FlightSearchSkill(db)
            result = await skill.search_flights_direct(
                origin="GRU",
                destination="JFK",
                departure_date="2025-03-15",
                adults=1,
                currency="USD"
            )
        """
        try:
            # Use specified provider or fall back to configured
            provider_name = provider_name or self.provider_name

            # Get provider
            provider = await self._get_provider(provider_name)
            if not provider:
                return {
                    "success": False,
                    "error": f"Provider '{provider_name}' not configured"
                }

            # Build search request
            request = FlightSearchRequest(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                adults=adults,
                currency=currency,
                max_results=max_results
            )

            # Execute search
            response = await provider.search_flights(request)

            # Format results
            formatted_output = provider.format_results(response)
            error_message = response.error if not response.success else None

            return {
                "success": response.success,
                "output": formatted_output,
                "error": error_message,
                "offers": [
                    {
                        "price": offer.price,
                        "currency": offer.currency,
                        "airline": offer.airline,
                        "duration": offer.duration,
                        "stops": offer.stops,
                        "departure_time": offer.departure_time,
                        "arrival_time": offer.arrival_time
                    }
                    for offer in response.offers
                ],
                "provider": provider_name,
                "metadata": response.metadata
            }

        except Exception as e:
            logger.error(f"Direct flight search failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _extract_flight_parameters(self, message: str) -> Optional[Dict]:
        """
        Extract flight search parameters from natural language using AI.

        Args:
            message: Natural language message

        Returns:
            Dict with flight parameters or None if extraction fails
        """
        try:
            from agent.ai_client import AIClient
            from datetime import datetime

            # Get config from instance or use defaults
            skill_config = getattr(self, '_config', {}) or self.get_default_config()

            # Create AI client for parsing using agent's configured LLM
            ai_client = AIClient(
                provider=skill_config.get('model_provider', 'gemini'),
                model_name=skill_config.get('model_name', 'gemini-2.5-flash'),
                db=self._db_session
            )

            system_prompt = """You are a flight search parameter extractor. Parse flight requests and return ONLY valid JSON."""

            user_prompt = f"""Parse this flight search request and extract structured data.
Return ONLY a JSON object with these fields (no other text):

{{
    "origin": "3-letter IATA airport code",
    "destination": "3-letter IATA airport code",
    "departure_date": "YYYY-MM-DD",
    "return_date": "YYYY-MM-DD or null for one-way trips",
    "adults": number of passengers (1-9, default 1 if not specified),
    "currency": "3-letter currency code"
}}

Common airport codes:
- Brazil: GRU/CGH (São Paulo), GIG/SDU (Rio), VIX (Vitória), BSB (Brasília), CNF (Belo Horizonte), SSA (Salvador), REC (Recife), POA (Porto Alegre), CWB (Curitiba), FOR (Fortaleza)
- Europe: FCO/CIA (Rome), LHR/LGW (London), CDG/ORY (Paris), MAD (Madrid), LIS (Lisbon), FRA (Frankfurt), AMS (Amsterdam), BCN (Barcelona)
- Americas: JFK/EWR/LGA (New York), LAX (Los Angeles), MIA (Miami), ORD (Chicago), EZE (Buenos Aires), SCL (Santiago), BOG (Bogotá), MEX (Mexico City)

Passenger count patterns (Portuguese):
- "para dois passageiros" / "2 passageiros" / "dois adultos" → adults: 2
- "para três pessoas" / "3 adultos" → adults: 3
- "para mim e minha esposa" / "eu e mais uma pessoa" → adults: 2
- No mention of passengers → adults: 1 (default)

Examples:

1. One-way, 1 passenger (English):
   "Flights from London to New York on Feb 28"
   → {{"origin": "LHR", "destination": "JFK", "departure_date": "2026-02-28", "return_date": null, "adults": 1, "currency": "USD"}}

2. Round-trip, 1 passenger (Portuguese):
   "Voos de São Paulo para Buenos Aires dia 15/03, volta dia 20/03"
   → {{"origin": "GRU", "destination": "EZE", "departure_date": "2026-03-15", "return_date": "2026-03-20", "adults": 1, "currency": "BRL"}}

3. Round-trip, 2 passengers (Portuguese):
   "busque voos para dois passageiros saindo de VIX para FCO dia 4 de Junho de 2026 volta dia 22 de Junho de 2026 em BRL"
   → {{"origin": "VIX", "destination": "FCO", "departure_date": "2026-06-04", "return_date": "2026-06-22", "adults": 2, "currency": "BRL"}}

4. One-way, 1 passenger (Portuguese):
   "busque voos saindo de VIX para FCO dia 4 de Junho de 2026 em BRL"
   → {{"origin": "VIX", "destination": "FCO", "departure_date": "2026-06-04", "return_date": null, "adults": 1, "currency": "BRL"}}

5. Round-trip, 3 passengers (English):
   "Find flights for 3 adults from NYC to LAX on March 10 returning March 17"
   → {{"origin": "JFK", "destination": "LAX", "departure_date": "2026-03-10", "return_date": "2026-03-17", "adults": 3, "currency": "USD"}}

Current date: {datetime.now().strftime('%Y-%m-%d')}

User request: "{message}"

Return JSON only:"""

            response = await ai_client.generate(system_prompt, user_prompt)

            if response.get('error'):
                logger.error(f"AI parameter extraction error: {response['error']}")
                return None

            # Extract JSON from response
            import json
            import re

            answer = response.get('answer', '')
            json_match = re.search(r'\{[^{}]+\}', answer)

            if json_match:
                params = json.loads(json_match.group())

                # Validate required fields
                if params.get('origin') and params.get('destination') and params.get('departure_date'):
                    logger.info(f"Extracted flight parameters: {params}")
                    return params

            logger.warning("Could not extract valid parameters from AI response")
            return None

        except Exception as e:
            logger.error(f"Parameter extraction failed: {e}", exc_info=True)
            return None

    def _get_tenant_id(self) -> Optional[str]:
        if not self._db_session or not getattr(self, "_agent_id", None):
            return None

        try:
            from models import Agent
            agent = self._db_session.query(Agent).filter(Agent.id == self._agent_id).first()
            return agent.tenant_id if agent else None
        except Exception as e:
            logger.warning(f"Failed to resolve tenant_id for agent {self._agent_id}: {e}")
            return None

    async def _get_provider(self, provider_name: str):
        """
        Get and cache provider instance.

        Args:
            provider_name: Provider identifier

        Returns:
            Provider instance or None
        """
        tenant_id = self._get_tenant_id()

        if (
            not self.provider
            or self.provider.provider_name != provider_name
            or self._provider_tenant_id != tenant_id
        ):
            self.provider = FlightProviderRegistry.get_provider(
                provider_name,
                self._db_session,
                tenant_id=tenant_id
            )
            self._provider_tenant_id = tenant_id
        return self.provider

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION (Phase 3)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        Return MCP-compliant tool definition for flight search.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools
        """
        return {
            "name": "search_flights",
            "title": "Flight Search",
            "description": (
                "Search for flights between airports. Use when user asks about flights, airfare, "
                "or travel between cities. Returns flight options with prices, airlines, and times."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "origin": {
                        "type": "string",
                        "description": "Origin airport IATA code (e.g., 'JFK', 'GRU', 'LHR')"
                    },
                    "destination": {
                        "type": "string",
                        "description": "Destination airport IATA code (e.g., 'LAX', 'FCO', 'CDG')"
                    },
                    "departure_date": {
                        "type": "string",
                        "description": "Departure date in YYYY-MM-DD format"
                    },
                    "return_date": {
                        "type": "string",
                        "description": "Return date in YYYY-MM-DD format (optional, for round trips)"
                    },
                    "passengers": {
                        "type": "integer",
                        "description": "Number of adult passengers",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 9
                    },
                    "cabin_class": {
                        "type": "string",
                        "enum": ["economy", "business", "first"],
                        "description": "Cabin class preference",
                        "default": "economy"
                    },
                    "currency": {
                        "type": "string",
                        "description": "Currency code for prices (e.g., 'USD', 'BRL', 'EUR')",
                        "default": "BRL"
                    }
                },
                "required": ["origin", "destination", "departure_date"]
            },
            "annotations": {
                "destructive": False,
                "idempotent": True,
                "audience": ["user", "assistant"]
            }
        }

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute flight search as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - origin: Origin airport IATA code (required)
                - destination: Destination airport IATA code (required)
                - departure_date: Departure date YYYY-MM-DD (required)
                - return_date: Return date YYYY-MM-DD (optional)
                - passengers: Number of passengers (default: 1)
                - cabin_class: economy/business/first (default: economy)
                - currency: Currency code (default: BRL)
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with flight search results
        """
        origin = arguments.get("origin")
        destination = arguments.get("destination")
        departure_date = arguments.get("departure_date")
        return_date = arguments.get("return_date")
        passengers = arguments.get("passengers", 1)
        currency = arguments.get("currency", config.get("settings", {}).get("default_currency", "BRL"))

        # Validate required arguments
        if not origin:
            return SkillResult(
                success=False,
                output="Origin airport code is required (e.g., 'JFK', 'GRU')",
                metadata={"error": "missing_origin"}
            )

        if not destination:
            return SkillResult(
                success=False,
                output="Destination airport code is required (e.g., 'LAX', 'FCO')",
                metadata={"error": "missing_destination"}
            )

        if not departure_date:
            return SkillResult(
                success=False,
                output="Departure date is required in YYYY-MM-DD format",
                metadata={"error": "missing_departure_date"}
            )

        try:
            logger.info(f"FlightSearchSkill.execute_tool: {origin} -> {destination} on {departure_date}")

            # Get database session if needed
            if not self._db_session:
                from sqlalchemy.orm import sessionmaker
                from db import get_engine
                import os

                engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
                SessionLocal = sessionmaker(bind=engine)
                self._db_session = SessionLocal()

            # Get provider configuration
            provider_name = config.get('provider', self.provider_name)
            provider_settings = config.get('settings', {})
            max_results = provider_settings.get('max_results', 5)

            # Initialize provider
            provider = await self._get_provider(provider_name)
            if not provider:
                return SkillResult(
                    success=False,
                    output=f"Flight search provider '{provider_name}' is not configured. Please configure it in Hub settings.",
                    metadata={
                        'error': 'provider_not_configured',
                        'provider': provider_name
                    }
                )

            # Execute flight search using direct method
            result = await self.search_flights_direct(
                origin=origin.upper(),
                destination=destination.upper(),
                departure_date=departure_date,
                return_date=return_date,
                adults=passengers,
                currency=currency,
                max_results=max_results,
                provider_name=provider_name
            )

            if result['success']:
                return SkillResult(
                    success=True,
                    output=result['output'],
                    metadata={
                        'provider': provider_name,
                        'offers_count': len(result.get('offers', [])),
                        'origin': origin.upper(),
                        'destination': destination.upper(),
                        'departure_date': departure_date,
                        'return_date': return_date
                    }
                )
            else:
                return SkillResult(
                    success=False,
                    output=result.get('output') or f"Flight search failed: {result.get('error', 'Unknown error')}",
                    metadata={
                        'error': result.get('error'),
                        'provider': provider_name
                    }
                )

        except Exception as e:
            logger.error(f"FlightSearchSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error searching flights: {str(e)}",
                metadata={"error": str(e)}
            )

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Phase 20: Skill-aware Sentinel security system.
        Provides context about expected flight search behaviors
        so legitimate commands aren't blocked.

        Returns:
            Sentinel context dict with expected intents and patterns
        """
        return {
            "expected_intents": [
                "Search for flights between cities",
                "Find airfare and flight prices",
                "Check flight availability",
                "Book travel between airports"
            ],
            "expected_patterns": [
                "flight", "flights", "fly", "airfare", "airline",
                "voo", "voos", "passagem", "passagens", "aérea",
                "JFK", "LAX", "GRU", "LHR", "FCO"
            ],
            "risk_notes": "Low risk - read-only flight search queries",
            "risk_level": "low"
        }

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for flight search skill.

        Returns:
            Default config dict
        """
        return {
            "execution_mode": "hybrid",
            "keywords": [
                # English
                "flight", "flights", "fly", "airfare", "airline", "airplane",
                "plane ticket", "air ticket", "book flight",
                # Portuguese
                "voo", "voos", "passagem", "passagens", "aérea", "aéreas",
                "voar", "avião", "companhia aérea", "bilhete aéreo"
            ],
            "use_ai_fallback": True,
            "ai_model": "gemini-2.5-flash",
            "provider": "google_flights",  # Default provider - uses SerpApi
            "settings": {
                "default_currency": "BRL",
                "max_results": 5,
                "prefer_direct_flights": False
            }
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for skill configuration.

        Returns:
            Config schema dict
        """
        return {
            "type": "object",
            "properties": {
                "execution_mode": {
                    "type": "string",
                    "enum": ["tool", "legacy", "hybrid"],
                    "description": "Execution mode: tool (LLM decides), legacy (keywords), hybrid (both)",
                    "default": "hybrid"
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords that trigger flight search (legacy/hybrid mode)"
                },
                "use_ai_fallback": {
                    "type": "boolean",
                    "description": "Use AI to verify intent after keyword match"
                },
                "ai_model": {
                    "type": "string",
                    "description": "AI model for intent classification"
                },
                "provider": {
                    "type": "string",
                    "enum": ["amadeus", "skyscanner", "google_flights"],
                    "description": "Flight search provider to use"
                },
                "settings": {
                    "type": "object",
                    "properties": {
                        "default_currency": {
                            "type": "string",
                            "description": "Default currency code (e.g., 'BRL', 'USD')"
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "Maximum number of flight results"
                        },
                        "prefer_direct_flights": {
                            "type": "boolean",
                            "description": "Prefer non-stop flights when available"
                        }
                    }
                }
            }
        }

    async def _ai_classify(self, message: str, config: Dict[str, Any]) -> bool:
        """
        Use AI to classify message intent.

        Phase 7.1: Helper method for AI-based intent detection.
        Phase 7.4: Passes database session for API key loading.

        Args:
            message: Message text to classify
            config: Skill configuration (must contain ai_model)

        Returns:
            True if AI classifies message as matching skill intent

        Example:
            config = {"ai_model": "gemini-2.5-flash"}
            result = await self._ai_classify("Can you switch my agent?", config)
        """
        from agent.skills.ai_classifier import get_classifier

        classifier = get_classifier()
        ai_model = config.get("ai_model", "gemini-2.5-flash")

        custom_examples = {
            "yes": [
                "Find flights from NYC to LON",
                "Search for a flight to Paris",
                "Preciso de passagem aérea para Miami",
                "Ver preços de voos para Tokyo",
                "Quero viajar de avião para Lisboa",
                "Flight price from LAX to JFK",
                "Check flights",
                "Quanto custa ir de SP para Londres",
                "Procure voos para mim"
            ],
            "no": [
                "I want to switch agent",
                "What is the weather?",
                "Who are you?",
                "Translate this text",
                "Generate an image",
                "Add to calendar",
                "Schedule a meeting"
            ]
        }

        return await classifier.classify_intent(
            message=message,
            skill_name=self.skill_name,
            skill_description=self.skill_description,
            model=ai_model,
            custom_examples=custom_examples,
            db=self._db_session  # Pass database session for API key loading
        )

    def _keyword_matches(self, message: str, keywords: List[str]) -> bool:
        """
        Check if message contains any of the specified keywords (case-insensitive).

        Args:
            message: Message text to check
            keywords: List of keywords to match

        Returns:
            True if any keyword found in message
        """
        if not keywords:
            return False

        message_lower = message.lower()
        return any(keyword.lower() in message_lower for keyword in keywords)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.skill_type}>"
