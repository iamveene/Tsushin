"""
Weather Skill - Get weather information using OpenWeatherMap API

Allows agents to provide weather information and forecasts.
Migrated from API Tools to Skills system for better configuration management.
"""

import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from .base import BaseSkill, InboundMessage, SkillResult


logger = logging.getLogger(__name__)


class WeatherSkill(BaseSkill):
    """
    Weather information skill using OpenWeatherMap API.

    Provides current weather and forecasts for any location.
    API key is loaded from the database (Studio → API Keys) or environment.

    Skills-as-Tools (Phase 2):
    - Tool name: get_weather
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    """

    skill_type = "weather"
    skill_name = "Weather"
    skill_description = "Get weather forecasts using OpenWeatherMap API"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize weather skill.

        Args:
            db: Database session for API key loading
        """
        super().__init__()
        self._db = db

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Detect if message contains weather intent.

        Looks for weather-related keywords in multiple languages.

        Args:
            message: Inbound message

        Returns:
            True if message is about weather
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
            logger.debug(f"WeatherSkill: No keyword match in '{text[:50]}...'")
            return False

        logger.info(f"WeatherSkill: Keywords matched in '{text[:50]}...'")

        # Step 2: AI fallback (optional, for intent verification)
        if use_ai_fallback:
            result = await self._ai_classify(message.body, config)
            logger.info(f"WeatherSkill: AI classification result={result}")
            return result

        return True

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process weather request.

        Steps:
        1. Extract location from message
        2. Call OpenWeatherMap API
        3. Format and return results

        Args:
            message: Inbound message with weather request
            config: Skill configuration

        Returns:
            SkillResult with weather information
        """
        try:
            logger.info(f"WeatherSkill: Processing message: {message.body}")

            # Get database session
            db = self._db
            if not db:
                from sqlalchemy.orm import sessionmaker
                from db import get_engine
                import os

                engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
                SessionLocal = sessionmaker(bind=engine)
                db = SessionLocal()

            # Initialize weather tool with db session for API key
            from agent.tools.weather_tool import WeatherTool
            weather_tool = WeatherTool(db=db)

            # Extract location and request type using AI
            params = await self._extract_weather_params(message.body, config)

            if not params or not params.get('location'):
                return SkillResult(
                    success=False,
                    output="❌ Could not determine the location. Please specify a city or location (e.g., 'weather in London' or 'previsão para São Paulo').",
                    metadata={'error': 'location_extraction_failed'}
                )

            location = params['location']
            request_type = params.get('type', 'current')  # 'current' or 'forecast'
            units = config.get('units', 'metric')

            # Get weather data
            if request_type == 'forecast':
                days = params.get('days', config.get('forecast_days', 3))
                weather_result = weather_tool.get_forecast(location, days=days, units=units)
                if 'error' not in weather_result:
                    formatted_output = weather_tool.format_forecast_data(weather_result)
                else:
                    formatted_output = f"❌ {weather_result['error']}"
            else:
                weather_result = weather_tool.get_current_weather(location, units=units)
                if 'error' not in weather_result:
                    formatted_output = weather_tool.format_weather_data(weather_result)
                else:
                    formatted_output = f"❌ {weather_result['error']}"

            if 'error' in weather_result:
                return SkillResult(
                    success=False,
                    output=formatted_output,
                    metadata={'error': weather_result['error']}
                )

            return SkillResult(
                success=True,
                output=formatted_output,
                metadata={
                    'location': location,
                    'type': request_type,
                    'units': units,
                    'data': weather_result
                }
            )

        except Exception as e:
            logger.error(f"WeatherSkill error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error getting weather: {str(e)}",
                metadata={'error': str(e)}
            )

    async def _extract_weather_params(self, message: str, config: Dict[str, Any]) -> Optional[Dict]:
        """
        Extract weather parameters from natural language message using AI.

        Args:
            message: Natural language message
            config: Skill configuration

        Returns:
            Dict with location, type, and optional days
        """
        try:
            from agent.ai_client import AIClient
            import json
            import re

            # Create AI client for parsing using agent's configured LLM
            ai_client = AIClient(
                provider=config.get('model_provider', 'gemini'),
                model_name=config.get('model_name', 'gemini-2.5-flash'),
                db=self._db
            )

            system_prompt = """You are a weather request parser. Extract location and request type from weather queries and return ONLY valid JSON."""

            user_prompt = f"""Parse this weather request and extract structured data.
Return ONLY a JSON object with these fields (no other text):

{{
    "location": "city name, optionally with country code",
    "type": "current" or "forecast",
    "days": number of days for forecast (if applicable, 1-5)
}}

Examples:
- "What's the weather in London?" → {{"location": "London", "type": "current"}}
- "Previsão do tempo para São Paulo" → {{"location": "São Paulo,BR", "type": "forecast", "days": 3}}
- "5 day forecast for New York" → {{"location": "New York,US", "type": "forecast", "days": 5}}
- "Clima em Tokyo amanhã" → {{"location": "Tokyo,JP", "type": "forecast", "days": 1}}

User request: "{message}"

Return JSON only:"""

            response = await ai_client.generate(system_prompt, user_prompt)

            if response.get('error'):
                logger.error(f"AI weather param extraction error: {response['error']}")
                return self._simple_location_extraction(message)

            # Extract JSON from response
            answer = response.get('answer', '')
            json_match = re.search(r'\{[^{}]+\}', answer)

            if json_match:
                params = json.loads(json_match.group())
                if params.get('location'):
                    logger.info(f"Extracted weather params: {params}")
                    return params

            # Fallback
            return self._simple_location_extraction(message)

        except Exception as e:
            logger.error(f"Weather param extraction failed: {e}", exc_info=True)
            return self._simple_location_extraction(message)

    def _simple_location_extraction(self, message: str) -> Optional[Dict]:
        """
        Simple fallback for location extraction without AI.

        Args:
            message: Original message

        Returns:
            Dict with location or None
        """
        import re

        # Common patterns for location extraction
        patterns = [
            r'(?:weather|clima|tempo|previsão|forecast)\s+(?:in|em|para|for)\s+([A-Za-zÀ-ÿ\s]+)',
            r'(?:in|em|para|for)\s+([A-Za-zÀ-ÿ\s]+?)(?:\?|\.|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                if len(location) > 2:
                    return {
                        'location': location,
                        'type': 'forecast' if 'forecast' in message.lower() or 'previsão' in message.lower() else 'current'
                    }

        return None

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for weather skill.

        Returns:
            Default config dict
        """
        return {
            "keywords": [
                # English
                "weather", "forecast", "temperature", "rain", "sunny", "cloudy",
                "climate", "humidity", "wind",
                # Portuguese
                "tempo", "clima", "previsão", "temperatura", "chuva", "sol",
                "nublado", "umidade", "vento", "meteorologia"
            ],
            "use_ai_fallback": True,
            "ai_model": "gemini-2.5-flash",
            "units": "metric",  # 'metric' (Celsius), 'imperial' (Fahrenheit)
            "forecast_days": 3
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
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords that trigger weather queries"
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
                "units": {
                    "type": "string",
                    "enum": ["metric", "imperial"],
                    "description": "Temperature units (metric=Celsius, imperial=Fahrenheit)",
                    "default": "metric"
                },
                "forecast_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "description": "Default number of days for forecasts",
                    "default": 3
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
        Return MCP-compliant tool definition for weather lookup.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools
        """
        return {
            "name": "get_weather",
            "title": "Weather Lookup",
            "description": (
                "Get current weather conditions and forecast for a location. "
                "Use when user asks about weather, temperature, climate, or forecast for any city or location."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City name, optionally with country code (e.g., 'Tokyo', 'London,UK', 'New York,US')"
                    },
                    "forecast_type": {
                        "type": "string",
                        "enum": ["current", "forecast"],
                        "description": "Type of weather data: 'current' for current conditions, 'forecast' for multi-day forecast",
                        "default": "current"
                    },
                    "units": {
                        "type": "string",
                        "enum": ["metric", "imperial"],
                        "description": "Temperature units: 'metric' (Celsius) or 'imperial' (Fahrenheit)",
                        "default": "metric"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days for forecast (1-5), only used when forecast_type is 'forecast'",
                        "default": 3
                    }
                },
                "required": ["location"]
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

        Weather queries are generally safe - no specific risk patterns.
        """
        return {
            "expected_intents": [
                "Get current weather for a location",
                "Get weather forecast for a location",
                "Check temperature and conditions"
            ],
            "expected_patterns": [
                "weather", "forecast", "temperature", "clima", "tempo", "previsão"
            ],
            "risk_notes": None  # Weather queries are low-risk
        }

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute weather lookup as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - location: City/location to get weather for (required)
                - forecast_type: 'current' or 'forecast' (optional, default 'current')
                - units: 'metric' or 'imperial' (optional, default 'metric')
                - days: Number of forecast days 1-5 (optional, default 3)
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with weather information
        """
        location = arguments.get("location")
        forecast_type = arguments.get("forecast_type", "current")
        units = arguments.get("units", config.get("units", "metric"))
        days = arguments.get("days", config.get("forecast_days", 3))

        if not location:
            return SkillResult(
                success=False,
                output="Location is required",
                metadata={"error": "missing_location"}
            )

        try:
            logger.info(f"WeatherSkill.execute_tool: location='{location}', type={forecast_type}, units={units}")

            # Get database session
            db = self._db or self._db_session
            if not db:
                from sqlalchemy.orm import sessionmaker
                from db import get_engine
                import os

                engine = get_engine(os.getenv("INTERNAL_DB_PATH", "./data/agent.db"))
                SessionLocal = sessionmaker(bind=engine)
                db = SessionLocal()

            # Initialize weather tool with db session for API key
            from agent.tools.weather_tool import WeatherTool
            weather_tool = WeatherTool(db=db)

            # Get weather data based on type
            if forecast_type == "forecast":
                weather_result = weather_tool.get_forecast(location, days=days, units=units)
                if "error" not in weather_result:
                    formatted_output = weather_tool.format_forecast_data(weather_result)
                else:
                    return SkillResult(
                        success=False,
                        output=f"Failed to get forecast: {weather_result['error']}",
                        metadata={"error": weather_result["error"]}
                    )
            else:
                weather_result = weather_tool.get_current_weather(location, units=units)
                if "error" not in weather_result:
                    formatted_output = weather_tool.format_weather_data(weather_result)
                else:
                    return SkillResult(
                        success=False,
                        output=f"Failed to get weather: {weather_result['error']}",
                        metadata={"error": weather_result["error"]}
                    )

            return SkillResult(
                success=True,
                output=formatted_output,
                metadata={
                    "location": location,
                    "forecast_type": forecast_type,
                    "units": units,
                    "data": weather_result
                }
            )

        except Exception as e:
            logger.error(f"WeatherSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error getting weather: {str(e)}",
                metadata={"error": str(e)}
            )
