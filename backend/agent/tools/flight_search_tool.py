"""
Flight Search Tool for Agents
Uses API key from database or environment variable to search flights via Amadeus API.
"""

import os
import re
import logging
import requests
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class FlightSearchTool:
    """
    Tool for searching flights using Amadeus API.

    Supports natural language queries and extracts flight search parameters.
    Can be enabled/disabled per agent via configuration.
    """

    # Keywords that trigger flight search (Portuguese and English)
    TRIGGER_KEYWORDS = [
        "voo", "voos", "passagem", "passagens", "flight", "flights",
        "plane ticket", "airplane", "avião", "viagem aérea", "voar"
    ]

    # Cities to IATA code mapping (common Brazilian cities)
    CITY_CODES = {
        # Brazilian cities
        "são paulo": "GRU", "sao paulo": "GRU", "sp": "GRU", "guarulhos": "GRU",
        "congonhas": "CGH",
        "rio de janeiro": "GIG", "rio": "GIG", "galeão": "GIG",
        "vitória": "VIX", "vitoria": "VIX",
        "belo horizonte": "CNF", "bh": "CNF", "confins": "CNF",
        "brasília": "BSB", "brasilia": "BSB",
        "salvador": "SSA",
        "recife": "REC",
        "fortaleza": "FOR",
        "porto alegre": "POA",
        "curitiba": "CWB",
        "manaus": "MAO",
        "florianópolis": "FLN", "florianopolis": "FLN",
        "natal": "NAT",

        # International cities
        "lisbon": "LIS", "lisboa": "LIS",
        "porto": "OPO",
        "madrid": "MAD",
        "barcelona": "BCN",
        "paris": "CDG",
        "london": "LHR", "londres": "LHR",
        "new york": "JFK", "nova york": "JFK", "ny": "JFK",
        "miami": "MIA",
        "orlando": "MCO",
        "los angeles": "LAX", "la": "LAX",
        "buenos aires": "EZE",
        "santiago": "SCL",
        "lima": "LIM",
        "bogota": "BOG", "bogotá": "BOG",
        "mexico city": "MEX", "cidade do méxico": "MEX",
        "cancun": "CUN", "cancún": "CUN",
        "dubai": "DXB",
        "tokyo": "NRT", "tóquio": "NRT",
        "toronto": "YYZ",
        "rome": "FCO", "roma": "FCO",
        "milan": "MXP", "milão": "MXP",
        "amsterdam": "AMS",
        "frankfurt": "FRA",
        "zurich": "ZRH",
        "malta": "MLA",
        "valletta": "MLA",
    }

    def __init__(self, db: Optional[Session] = None, api_key: str = None, api_secret: str = None):
        """
        Initialize FlightSearchTool.

        Args:
            db: Database session for loading API keys
            api_key: Optional explicit API key
            api_secret: Optional explicit API secret
        """
        self.db = db
        self._api_key = api_key
        self._api_secret = api_secret
        self.base_url = "https://test.api.amadeus.com"  # Use test environment by default
        self._access_token = None
        self._token_expires_at = None

    def _get_api_credentials(self) -> tuple:
        """Get API key and secret from provided values, database, or environment."""
        api_key = self._api_key
        api_secret = self._api_secret

        if not api_key and self.db:
            try:
                from models import ApiKey
                db_key = self.db.query(ApiKey).filter(
                    ApiKey.service == "amadeus",
                    ApiKey.is_active == True
                ).first()
                if db_key:
                    # The API key field might contain both key and secret separated by ":"
                    if ":" in db_key.api_key:
                        api_key, api_secret = db_key.api_key.split(":", 1)
                    else:
                        api_key = db_key.api_key
            except Exception as e:
                logger.warning(f"Failed to load API key from database: {e}")

        # Fall back to environment variables
        if not api_key:
            api_key = os.getenv("AMADEUS_API_KEY")
        if not api_secret:
            api_secret = os.getenv("AMADEUS_API_SECRET")

        return api_key, api_secret

    async def _get_access_token(self) -> Optional[str]:
        """Get OAuth2 access token from Amadeus API."""
        # Check if we have a valid cached token
        if self._access_token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at:
                return self._access_token

        api_key, api_secret = self._get_api_credentials()

        if not api_key or not api_secret:
            logger.error("Amadeus API credentials not configured")
            return None

        url = f"{self.base_url}/v1/security/oauth2/token"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        data = {
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": api_secret
        }

        try:
            response = requests.post(url, headers=headers, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            self._access_token = token_data.get('access_token')

            if self._access_token:
                expires_in = token_data.get('expires_in', 1799)
                self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in - 60)
                logger.info("Successfully obtained Amadeus access token")
                return self._access_token

            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Amadeus authentication failed: {e}")
            return None

    def should_handle(self, message: str) -> bool:
        """
        Check if this message should trigger flight search.

        Args:
            message: User message text

        Returns:
            True if message contains flight search keywords
        """
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in self.TRIGGER_KEYWORDS)

    def _resolve_city_code(self, location: str) -> str:
        """
        Resolve city name or code to IATA code.

        Args:
            location: City name or IATA code

        Returns:
            IATA code (3 letters)
        """
        location_lower = location.lower().strip()

        # Check if it's already an IATA code (3 uppercase letters)
        if len(location) == 3 and location.isalpha():
            return location.upper()

        # Look up in city codes dictionary
        if location_lower in self.CITY_CODES:
            return self.CITY_CODES[location_lower]

        # Try partial match
        for city, code in self.CITY_CODES.items():
            if location_lower in city or city in location_lower:
                return code

        # Return as-is if not found (let API validate)
        return location.upper()[:3]

    def _extract_date(self, message: str) -> Optional[str]:
        """
        Extract date from message in YYYY-MM-DD format.

        Args:
            message: User message text

        Returns:
            Date string in YYYY-MM-DD format or None
        """
        # Try to find explicit date patterns
        patterns = [
            r"(\d{4}-\d{2}-\d{2})",  # YYYY-MM-DD
            r"(\d{2}/\d{2}/\d{4})",   # DD/MM/YYYY
            r"(\d{2}-\d{2}-\d{4})",   # DD-MM-YYYY
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                date_str = match.group(1)
                # Convert to YYYY-MM-DD if needed
                if "/" in date_str or (date_str[2] == "-" and date_str[5] == "-"):
                    parts = re.split(r"[/-]", date_str)
                    if len(parts[0]) == 2:  # DD/MM/YYYY format
                        return f"{parts[2]}-{parts[1]}-{parts[0]}"
                return date_str

        # Try relative date parsing
        message_lower = message.lower()
        today = datetime.now()

        if "hoje" in message_lower or "today" in message_lower:
            return today.strftime("%Y-%m-%d")
        elif "amanhã" in message_lower or "tomorrow" in message_lower:
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "próxima semana" in message_lower or "next week" in message_lower:
            return (today + timedelta(weeks=1)).strftime("%Y-%m-%d")
        elif "próximo mês" in message_lower or "next month" in message_lower:
            return (today + timedelta(days=30)).strftime("%Y-%m-%d")

        # Default to tomorrow if no date found
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    async def search(
        self,
        origin: str,
        destination: str,
        departure_date: Optional[str] = None,
        return_date: Optional[str] = None,
        adults: int = 1,
        currency: str = "BRL",
        max_results: int = 5
    ) -> Dict:
        """
        Search for flights.

        Args:
            origin: Origin IATA code or city name
            destination: Destination IATA code or city name
            departure_date: Departure date (YYYY-MM-DD)
            return_date: Return date (optional)
            adults: Number of adult passengers
            currency: Currency code (default: BRL)
            max_results: Maximum results to return

        Returns:
            Search results dict
        """
        # Get access token
        token = await self._get_access_token()
        if not token:
            return {
                "success": False,
                "error": "Amadeus API credentials not configured or authentication failed",
                "results": []
            }

        # Resolve city codes
        origin_code = self._resolve_city_code(origin)
        destination_code = self._resolve_city_code(destination)

        # Default to tomorrow if no date provided
        if not departure_date:
            departure_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        url = f"{self.base_url}/v2/shopping/flight-offers"

        headers = {
            "Authorization": f"Bearer {token}"
        }

        params = {
            "originLocationCode": origin_code,
            "destinationLocationCode": destination_code,
            "departureDate": departure_date,
            "adults": adults,
            "max": max_results,
            "currencyCode": currency
        }

        if return_date:
            params["returnDate"] = return_date

        try:
            logger.info(f"Searching flights: {origin_code} → {destination_code}, date: {departure_date}")

            response = requests.get(url, headers=headers, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()
            offers = data.get("data", [])

            # Format results
            formatted_results = []
            for offer in offers:
                formatted_results.append(self._format_offer(offer, currency))

            return {
                "success": True,
                "origin": origin_code,
                "destination": destination_code,
                "departure_date": departure_date,
                "return_date": return_date,
                "results": formatted_results,
                "result_count": len(formatted_results)
            }

        except requests.exceptions.RequestException as e:
            logger.error(f"Flight search failed: {e}")
            error_detail = ""
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                except:
                    error_detail = str(e)

            return {
                "success": False,
                "error": str(e),
                "detail": error_detail,
                "results": []
            }

    def _format_offer(self, offer: Dict, currency: str) -> Dict:
        """Format a flight offer for display."""
        price = offer.get("price", {})
        itineraries = offer.get("itineraries", [])

        # Get first itinerary for outbound flight info
        outbound = itineraries[0] if itineraries else {}
        segments = outbound.get("segments", [])

        # Calculate stops
        stops = len(segments) - 1 if segments else 0

        # Get first and last segment for departure/arrival
        first_segment = segments[0] if segments else {}
        last_segment = segments[-1] if segments else {}

        # Get carrier info
        carrier_code = first_segment.get("carrierCode", "")
        flight_number = first_segment.get("number", "")

        # Parse times
        departure_time = first_segment.get("departure", {}).get("at", "")
        arrival_time = last_segment.get("arrival", {}).get("at", "")

        # Duration
        duration = outbound.get("duration", "")

        return {
            "id": offer.get("id"),
            "price": float(price.get("total", 0)),
            "currency": currency,
            "carrier": carrier_code,
            "flight_number": f"{carrier_code}{flight_number}",
            "departure": first_segment.get("departure", {}).get("iataCode", ""),
            "arrival": last_segment.get("arrival", {}).get("iataCode", ""),
            "departure_time": departure_time,
            "arrival_time": arrival_time,
            "duration": duration,
            "stops": stops,
            "is_direct": stops == 0
        }

    def format_results(self, search_result: Dict) -> str:
        """
        Format search results for agent response.

        Args:
            search_result: Search result dict

        Returns:
            Formatted string for display
        """
        if not search_result.get("success"):
            return f"❌ Erro na busca de voos: {search_result.get('error', 'Erro desconhecido')}"

        results = search_result.get("results", [])
        if not results:
            return "✈️ Nenhum voo encontrado para esta pesquisa."

        origin = search_result.get("origin", "")
        destination = search_result.get("destination", "")
        departure_date = search_result.get("departure_date", "")

        output = [f"✈️ **Resultados de Voo: {origin} → {destination}**"]
        output.append(f"📅 Data: {departure_date}\n")

        for idx, result in enumerate(results[:5], 1):
            stops_text = "Direto" if result.get("is_direct") else f"{result.get('stops')} parada(s)"
            duration = result.get("duration", "").replace("PT", "").lower()

            output.append(f"**Voo {idx}:**")
            output.append(f"🛫 {result.get('flight_number', '')}")
            output.append(f"⏱️ {duration} ({stops_text})")
            output.append(f"💰 {result.get('currency')} {result.get('price', 0):.2f}")
            output.append("")

        return "\n".join(output)
