"""
Weather Command Service

Handles /weather slash command operations:
- /weather <location>     - Get current weather
- /weather forecast <location> [days] - Get weather forecast

Uses WeatherTool for direct execution (zero AI tokens).
"""

import logging
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class WeatherCommandService:
    """
    Service for executing weather slash commands.

    Provides programmatic access to weather functionality without AI involvement.
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

    def _get_weather_tool(self):
        """
        Get weather tool with API key from database.

        Raises ValueError if API key is not configured.
        """
        from agent.tools.weather_tool import WeatherTool

        tool = WeatherTool(db=self.db)

        if not tool.api_key:
            raise ValueError(
                "Weather API key not configured. "
                "Add your OpenWeatherMap API key in Studio -> API Keys."
            )

        return tool

    def _get_skill_units(self, agent_id: int) -> str:
        """
        Get temperature units from agent's weather skill config.

        Args:
            agent_id: Agent ID

        Returns:
            Units string ('metric' or 'imperial')
        """
        try:
            from models import AgentSkill

            skill = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_type == "weather",
                AgentSkill.is_enabled == True
            ).first()

            if skill and skill.config:
                return skill.config.get('units', 'metric')
        except Exception as e:
            self.logger.warning(f"Could not get weather skill config: {e}")

        return 'metric'

    async def execute_current(
        self,
        tenant_id: str,
        agent_id: int,
        location: str,
        units: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get current weather for a location.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            location: City name (e.g., "London", "New York,US")
            units: Temperature units ('metric' or 'imperial'), defaults to agent config
        """
        try:
            if not location or not location.strip():
                return {
                    "status": "error",
                    "action": "weather_current",
                    "message": (
                        "Please specify a location.\n\n"
                        "**Usage:** `/weather <location>`\n\n"
                        "**Examples:**\n"
                        "- `/weather London`\n"
                        "- `/weather New York,US`\n"
                        "- `/weather Sao Paulo,BR`"
                    )
                }

            weather_tool = self._get_weather_tool()

            # Use provided units or get from skill config
            if not units:
                units = self._get_skill_units(agent_id)

            # Get current weather
            weather_data = weather_tool.get_current_weather(location.strip(), units=units)

            if 'error' in weather_data:
                return {
                    "status": "error",
                    "action": "weather_current",
                    "location": location,
                    "error": weather_data['error'],
                    "message": f"{weather_data['error']}"
                }

            # Format output
            formatted = weather_tool.format_weather_data(weather_data)

            return {
                "status": "success",
                "action": "weather_current",
                "location": weather_data.get('location', location),
                "country": weather_data.get('country'),
                "data": weather_data,
                "message": formatted
            }

        except ValueError as e:
            return {
                "status": "error",
                "action": "weather_current",
                "error": str(e),
                "message": f"{str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error in execute_current: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "weather_current",
                "error": str(e),
                "message": f"Failed to fetch weather: {str(e)}"
            }

    async def execute_forecast(
        self,
        tenant_id: str,
        agent_id: int,
        location: str,
        days: int = 3,
        units: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get weather forecast for a location.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            location: City name
            days: Number of forecast days (1-5)
            units: Temperature units
        """
        try:
            if not location or not location.strip():
                return {
                    "status": "error",
                    "action": "weather_forecast",
                    "message": (
                        "Please specify a location.\n\n"
                        "**Usage:** `/weather forecast <location> [days]`\n\n"
                        "**Examples:**\n"
                        "- `/weather forecast London`\n"
                        "- `/weather forecast Tokyo 5`"
                    )
                }

            weather_tool = self._get_weather_tool()

            # Use provided units or get from skill config
            if not units:
                units = self._get_skill_units(agent_id)

            # Clamp days between 1-5
            days = max(1, min(5, days))

            # Get forecast
            forecast_data = weather_tool.get_forecast(location.strip(), days=days, units=units)

            if 'error' in forecast_data:
                return {
                    "status": "error",
                    "action": "weather_forecast",
                    "location": location,
                    "error": forecast_data['error'],
                    "message": f"{forecast_data['error']}"
                }

            # Format output
            formatted = weather_tool.format_forecast_data(forecast_data)

            return {
                "status": "success",
                "action": "weather_forecast",
                "location": forecast_data.get('location', location),
                "country": forecast_data.get('country'),
                "days": len(forecast_data.get('forecast', [])),
                "data": forecast_data,
                "message": formatted
            }

        except ValueError as e:
            return {
                "status": "error",
                "action": "weather_forecast",
                "error": str(e),
                "message": f"{str(e)}"
            }
        except Exception as e:
            self.logger.error(f"Error in execute_forecast: {e}", exc_info=True)
            return {
                "status": "error",
                "action": "weather_forecast",
                "error": str(e),
                "message": f"Failed to fetch forecast: {str(e)}"
            }
