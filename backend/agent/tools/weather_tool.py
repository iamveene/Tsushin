"""
Weather Tool - Get weather information using OpenWeatherMap API

Provides current weather and forecasts for any location.
"""

import requests
import os
import logging
from typing import Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from services.api_key_service import get_api_key


class WeatherTool:
    """Tool for fetching weather information"""

    def __init__(self, api_key: Optional[str] = None, db: Optional[Session] = None):
        """
        Initialize Weather Tool

        Args:
            api_key: OpenWeatherMap API key (optional, overrides database/env)
            db: Database session for loading API key (Phase 4.6)
        """
        # Priority: explicit api_key > database > environment variable
        if api_key:
            self.api_key = api_key
        elif db:
            self.api_key = get_api_key('openweather', db)
        else:
            self.api_key = os.getenv('OPENWEATHER_API_KEY')

        self.base_url = "http://api.openweathermap.org/data/2.5"
        self.logger = logging.getLogger(__name__)

        if not self.api_key:
            self.logger.warning("OpenWeatherMap API key not configured")

    def get_current_weather(self, location: str, units: str = "metric") -> Dict:
        """
        Get current weather for a location

        Args:
            location: City name, e.g., "London", "New York,US", "Tokyo,JP"
            units: "metric" (Celsius), "imperial" (Fahrenheit), or "standard" (Kelvin)

        Returns:
            Dictionary with weather data or error
        """
        if not self.api_key:
            return {
                "error": "Weather API key not configured. Set OPENWEATHER_API_KEY environment variable."
            }

        try:
            url = f"{self.base_url}/weather"
            params = {
                "q": location,
                "appid": self.api_key,
                "units": units
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            return {
                "success": True,
                "location": data["name"],
                "country": data["sys"]["country"],
                "temperature": data["main"]["temp"],
                "feels_like": data["main"]["feels_like"],
                "temp_min": data["main"]["temp_min"],
                "temp_max": data["main"]["temp_max"],
                "humidity": data["main"]["humidity"],
                "pressure": data["main"]["pressure"],
                "description": data["weather"][0]["description"],
                "weather_main": data["weather"][0]["main"],
                "wind_speed": data["wind"]["speed"],
                "wind_deg": data["wind"].get("deg", 0),
                "cloudiness": data["clouds"]["all"],
                "visibility": data.get("visibility", 0),
                "units": units,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return {"error": f"Location '{location}' not found. Try including country code (e.g., 'London,UK')"}
            elif e.response.status_code == 401:
                return {"error": "Invalid API key"}
            else:
                return {"error": f"Weather API error: {e.response.status_code}"}

        except requests.exceptions.Timeout:
            return {"error": "Weather API request timed out"}

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Weather API request failed: {e}")
            return {"error": f"Failed to fetch weather data: {str(e)}"}

        except Exception as e:
            self.logger.error(f"Unexpected error in weather tool: {e}", exc_info=True)
            return {"error": f"Unexpected error: {str(e)}"}

    def get_forecast(self, location: str, days: int = 3, units: str = "metric") -> Dict:
        """
        Get weather forecast for a location

        Args:
            location: City name
            days: Number of days to forecast (max 5)
            units: Temperature units

        Returns:
            Dictionary with forecast data or error
        """
        if not self.api_key:
            return {
                "error": "Weather API key not configured. Set OPENWEATHER_API_KEY environment variable."
            }

        try:
            url = f"{self.base_url}/forecast"
            params = {
                "q": location,
                "appid": self.api_key,
                "units": units,
                "cnt": min(days * 8, 40)  # API returns 3-hour intervals (8 per day)
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Group by date
            forecast_by_date = {}
            for item in data["list"]:
                date = datetime.fromtimestamp(item["dt"]).strftime("%Y-%m-%d")
                if date not in forecast_by_date:
                    forecast_by_date[date] = {
                        "date": date,
                        "temp_min": item["main"]["temp_min"],
                        "temp_max": item["main"]["temp_max"],
                        "humidity": item["main"]["humidity"],
                        "description": item["weather"][0]["description"],
                        "weather_main": item["weather"][0]["main"],
                        "wind_speed": item["wind"]["speed"]
                    }
                else:
                    # Update min/max temps
                    forecast_by_date[date]["temp_min"] = min(
                        forecast_by_date[date]["temp_min"],
                        item["main"]["temp_min"]
                    )
                    forecast_by_date[date]["temp_max"] = max(
                        forecast_by_date[date]["temp_max"],
                        item["main"]["temp_max"]
                    )

            return {
                "success": True,
                "location": data["city"]["name"],
                "country": data["city"]["country"],
                "forecast": list(forecast_by_date.values())[:days],
                "units": units,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return {"error": f"Location '{location}' not found"}
            else:
                return {"error": f"Weather API error: {e.response.status_code}"}

        except Exception as e:
            self.logger.error(f"Error fetching forecast: {e}", exc_info=True)
            return {"error": f"Failed to fetch forecast: {str(e)}"}

    def format_weather_data(self, weather_data: Dict) -> str:
        """
        Format weather data into a human-readable string

        Args:
            weather_data: Weather data dictionary from get_current_weather()

        Returns:
            Formatted weather string
        """
        if "error" in weather_data:
            return f"❌ {weather_data['error']}"

        units = weather_data.get("units", "metric")
        temp_unit = "°C" if units == "metric" else "°F" if units == "imperial" else "K"
        wind_unit = "m/s" if units == "metric" else "mph"

        # Weather emoji mapping
        weather_emoji = {
            "Clear": "☀️",
            "Clouds": "☁️",
            "Rain": "🌧️",
            "Drizzle": "🌦️",
            "Thunderstorm": "⛈️",
            "Snow": "❄️",
            "Mist": "🌫️",
            "Fog": "🌫️",
            "Haze": "🌫️"
        }

        emoji = weather_emoji.get(weather_data["weather_main"], "🌡️")

        formatted = f"""{emoji} Weather in {weather_data['location']}, {weather_data['country']}

🌡️ Temperature: {weather_data['temperature']}{temp_unit} (feels like {weather_data['feels_like']}{temp_unit})
📊 Range: {weather_data['temp_min']}{temp_unit} - {weather_data['temp_max']}{temp_unit}
💧 Humidity: {weather_data['humidity']}%
🌤️ Conditions: {weather_data['description'].title()}
💨 Wind: {weather_data['wind_speed']} {wind_unit}
☁️ Cloudiness: {weather_data['cloudiness']}%"""

        return formatted

    def format_forecast_data(self, forecast_data: Dict) -> str:
        """
        Format forecast data into a human-readable string

        Args:
            forecast_data: Forecast data dictionary from get_forecast()

        Returns:
            Formatted forecast string
        """
        if "error" in forecast_data:
            return f"❌ {forecast_data['error']}"

        units = forecast_data.get("units", "metric")
        temp_unit = "°C" if units == "metric" else "°F" if units == "imperial" else "K"

        formatted = f"📅 {len(forecast_data['forecast'])}-Day Forecast for {forecast_data['location']}, {forecast_data['country']}\n\n"

        for day in forecast_data['forecast']:
            date_obj = datetime.strptime(day['date'], "%Y-%m-%d")
            day_name = date_obj.strftime("%A, %B %d")

            formatted += f"**{day_name}**\n"
            formatted += f"  🌡️ {day['temp_min']}{temp_unit} - {day['temp_max']}{temp_unit}\n"
            formatted += f"  🌤️ {day['description'].title()}\n"
            formatted += f"  💧 Humidity: {day['humidity']}%\n"
            formatted += f"  💨 Wind: {day['wind_speed']} m/s\n\n"

        return formatted
