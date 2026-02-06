"""
Google Flights Provider (via SerpApi)
Implementation of FlightSearchProvider interface for Google Flights.
"""

import logging
import httpx
import json
from typing import Dict, List, Optional
from datetime import datetime

from .flight_search_provider import (
    FlightSearchProvider,
    FlightSearchRequest,
    FlightSearchResponse,
    FlightOffer,
    FlightSegment
)
from models import GoogleFlightsIntegration, ApiKey
from hub.security import TokenEncryption
from services.encryption_key_service import get_api_key_encryption_key


logger = logging.getLogger(__name__)


class GoogleFlightsProvider(FlightSearchProvider):
    """
    Google Flights implementation using SerpApi.
    """

    BASE_URL = "https://serpapi.com/search"

    def __init__(self, integration: GoogleFlightsIntegration, db):
        super().__init__(integration, db)
        self.api_key = None
        self.currency = integration.default_currency or "USD"
        self.hl = integration.default_language or "en"

        # CRIT-004 fix: Use dedicated API key encryption key (not JWT_SECRET_KEY)
        # This ensures decryption works across container restarts
        encryption_key = get_api_key_encryption_key(db)
        encryptor = None
        if encryption_key:
            encryptor = TokenEncryption(encryption_key.encode())

        # Try to decrypt the encrypted API key from GoogleFlightsIntegration first
        if encryptor and integration.api_key_encrypted:
            try:
                # Use consistent identifier with ApiKey table
                identifier = f"apikey_google_flights_{integration.tenant_id or 'system'}"
                self.api_key = encryptor.decrypt(integration.api_key_encrypted, identifier)
                logger.info("GoogleFlightsProvider: Decrypted API key from integration")
            except Exception as e:
                logger.warning(f"GoogleFlightsProvider: Could not decrypt API key from integration: {e}")
                self.api_key = None

        # Fallback: Try to get API key from ApiKey table (using api_key_service for correct decryption)
        if not self.api_key:
            try:
                from services.api_key_service import get_api_key as get_decrypted_api_key
                tenant_id = integration.tenant_id
                self.api_key = get_decrypted_api_key('google_flights', db, tenant_id=tenant_id)
                if self.api_key:
                    logger.info(f"GoogleFlightsProvider: Got API key from ApiKey service (tenant: {tenant_id})")
                else:
                    logger.warning("GoogleFlightsProvider: No API key found in ApiKey table")
            except Exception as fallback_error:
                logger.error(f"GoogleFlightsProvider: Fallback API key lookup failed: {fallback_error}")

        # Final fallback: Try environment variable SERPAPI_KEY or GOOGLE_FLIGHTS_API_KEY
        if not self.api_key:
            import os
            env_key = os.environ.get("SERPAPI_KEY") or os.environ.get("GOOGLE_FLIGHTS_API_KEY")
            if env_key:
                self.api_key = env_key
                logger.info("GoogleFlightsProvider: Using API key from environment variable")

        if not self.api_key:
            raise ValueError("GoogleFlightsProvider: No valid API key available")

    def get_provider_name(self) -> str:
        return "google_flights"

    async def search_flights(self, request: FlightSearchRequest) -> FlightSearchResponse:
        """
        Execute flight search using SerpApi (Google Flights Engine).
        """
        try:
            # Store request for currency access in parsing
            self.search_request = request

            # 1. Prepare Parameters
            params = {
                "engine": "google_flights",
                "api_key": self.api_key,
                "departure_id": request.origin,
                "arrival_id": request.destination,
                "outbound_date": request.departure_date,
                "currency": request.currency or self.currency,
                "hl": self.hl,
                "adults": request.adults,
                "children": request.children,
                "infants_in_seat": request.infants,
                "stops": "1" if request.prefer_direct else "0", # 0 = any, 1 = 1 stop or fewer, 2 = 2 stops or fewer. API is tricky here.
                                                                # Actually Google Flights URL param 's' (stops): 0=Any, 1=Nonstop, 2=1 stop or fewer
                                                                # SerpApi documentation says: stops: 0 (Any), 1 (Nonstop), 2 (1 stop), 3 (2 stops)
                                                                # Let's assume prefer_direct means "Nonstop" -> stops=1
            }

            # SerpApi is sensitive to locale on some routes (e.g., VIX ↔ FCO round-trip).
            # Use Brazil locale when currency or language indicates PT/BR.
            currency = request.currency or self.currency
            hl_normalized = (self.hl or "").lower()
            if currency == "BRL" or hl_normalized.startswith("pt"):
                params["gl"] = "br"

            if request.prefer_direct:
                params["stops"] = "1"

            if request.return_date:
                params["return_date"] = request.return_date
                params["type"] = "1" # Round trip
            else:
                params["type"] = "2" # One way

            # Travel class mapping
            # 1: Economy, 2: Premium Economy, 3: Business, 4: First
            class_map = {
                "ECONOMY": "1",
                "PREMIUM_ECONOMY": "2",
                "BUSINESS": "3",
                "FIRST": "4"
            }
            params["seat_class"] = class_map.get(request.travel_class, "1")

            # 2. Execute Request
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.BASE_URL, params=params)

                if response.status_code != 200:
                    error_msg = f"SerpApi Error: {response.status_code} - {response.text}"
                    return FlightSearchResponse(
                        success=False,
                        offers=[],
                        provider=self.provider_name,
                        search_request=request,
                        error=error_msg
                    )

                data = response.json()

                if "error" in data:
                    return FlightSearchResponse(
                        success=False,
                        offers=[],
                        provider=self.provider_name,
                        search_request=request,
                        error=data["error"]
                    )

                # 3. Parse Results (outbound flights)
                offers = self._parse_serpapi_results(data, is_outbound=True)

                # 4. For round-trip, fetch return flights for top offers
                if request.return_date and offers:
                    # Limit to top N offers to avoid too many API calls
                    max_return_lookups = min(request.max_results, 5)

                    for offer in offers[:max_return_lookups]:
                        if hasattr(offer, '_departure_token') and offer._departure_token:
                            try:
                                return_data = await self._fetch_return_flights(
                                    request, offer._departure_token, client
                                )
                                if return_data:
                                    self._populate_return_info(offer, return_data)
                            except Exception as e:
                                logger.warning(f"Failed to fetch return flights: {e}")

                return FlightSearchResponse(
                    success=True,
                    offers=offers,
                    provider=self.provider_name,
                    search_request=request,
                    metadata={"serpapi_search_metadata": data.get("search_metadata", {})}
                )

        except Exception as e:
            logger.error(f"Google Flights search failed: {e}", exc_info=True)
            return FlightSearchResponse(
                success=False,
                offers=[],
                provider=self.provider_name,
                search_request=request,
                error=str(e)
            )

    def _parse_serpapi_results(self, data: Dict, is_outbound: bool = True) -> List[FlightOffer]:
        offers = []

        # SerpApi returns 'best_flights' and 'other_flights'
        # We'll combine them
        flight_lists = [data.get("best_flights", []), data.get("other_flights", [])]

        for flight_list in flight_lists:
            for item in flight_list:
                try:
                    # Extract flights (segments)
                    flights_data = item.get("flights", [])
                    segments = []
                    carrier_codes = set()
                    airline_names = set()

                    total_duration_minutes = item.get("total_duration", 0)

                    for f in flights_data:
                        # Airline info
                        airline = f.get("airline", "Unknown")
                        airline_names.add(airline)
                        # We don't always get IATA code easily from SerpApi display,
                        # usually it's in logo URL or we just use name.
                        # For standardized code, we might leave empty if unavailable.

                        # Times
                        dep_time = f.get("departure_airport", {}).get("time", "")
                        arr_time = f.get("arrival_airport", {}).get("time", "")

                        # Airports
                        dep_code = f.get("departure_airport", {}).get("id", "")
                        arr_code = f.get("arrival_airport", {}).get("id", "")

                        # Flight Number
                        flight_num = f.get("flight_number", "")

                        segment = FlightSegment(
                            carrier_code=airline[:2].upper(), # Approx if not provided
                            flight_number=flight_num,
                            departure_airport=dep_code,
                            arrival_airport=arr_code,
                            departure_time=dep_time,
                            arrival_time=arr_time,
                            duration=f"{f.get('duration', 0)}m",
                            aircraft=f.get("airplane"),
                            cabin_class=f.get("travel_class")
                        )
                        segments.append(segment)
                        carrier_codes.add(segment.carrier_code)

                    if not segments:
                        continue

                    # Top level info
                    price = float(item.get("price", 0))
                    # Use currency from search request, fallback to provider default
                    currency = self.search_request.currency if hasattr(self, 'search_request') else self.currency

                    # Times from first/last segment
                    departure_time = segments[0].departure_time
                    arrival_time = segments[-1].arrival_time

                    # Duration formatting
                    hours = total_duration_minutes // 60
                    minutes = total_duration_minutes % 60
                    duration_str = f"{hours}h {minutes}m"

                    offer = FlightOffer(
                        id=f"gf_{len(offers)}", # No persistent ID from SerpApi
                        price=price,
                        currency=currency, # Use request currency
                        airline=", ".join(airline_names),
                        carrier_codes=list(carrier_codes),
                        duration=duration_str,
                        departure_time=departure_time,
                        arrival_time=arrival_time,
                        stops=len(segments) - 1,
                        segments=segments,
                        booking_url=None, # SerpApi might provide links via Google Flights URL
                        is_refundable=False # Info often hidden in extensions
                    )

                    # Store departure_token for round-trip return flight lookup
                    if is_outbound and "departure_token" in item:
                        offer._departure_token = item["departure_token"]

                    offers.append(offer)

                except Exception as e:
                    logger.warning(f"Error parsing flight item: {e}")
                    continue

        return offers

    async def _fetch_return_flights(
        self,
        request: FlightSearchRequest,
        departure_token: str,
        client: httpx.AsyncClient
    ) -> Optional[Dict]:
        """Fetch return flight options using the departure_token from outbound search."""
        try:
            # SerpApi requires base parameters + departure_token for return flights
            params = {
                "engine": "google_flights",
                "api_key": self.api_key,
                "departure_id": request.origin,
                "arrival_id": request.destination,
                "outbound_date": request.departure_date,
                "return_date": request.return_date,
                "departure_token": departure_token,
                "currency": request.currency or self.currency,
                "hl": self.hl,
                "type": "1",  # Round trip
                "adults": request.adults,
            }

            logger.debug(f"Fetching return flights with token: {departure_token[:50]}...")
            response = await client.get(self.BASE_URL, params=params)

            if response.status_code != 200:
                error_text = response.text[:200] if response.text else "No error details"
                logger.warning(f"Return flights fetch failed: {response.status_code} - {error_text}")
                return None

            data = response.json()

            if "error" in data:
                logger.warning(f"Return flights API error: {data['error']}")
                return None

            return data

        except Exception as e:
            logger.warning(f"Exception fetching return flights: {e}")
            return None

    def _populate_return_info(self, offer: FlightOffer, return_data: Dict) -> None:
        """Populate return flight information in the offer from fetched data."""
        try:
            # Get the best return flight option
            return_flights = return_data.get("best_flights", []) or return_data.get("other_flights", [])

            if not return_flights:
                logger.debug("No return flights found in response")
                return

            # Use the first (best) return option
            best_return = return_flights[0]
            flights_data = best_return.get("flights", [])

            if not flights_data:
                return

            # Parse return segments
            return_segments = []
            return_airline_names = set()

            for f in flights_data:
                airline = f.get("airline", "Unknown")
                return_airline_names.add(airline)

                dep_time = f.get("departure_airport", {}).get("time", "")
                arr_time = f.get("arrival_airport", {}).get("time", "")
                dep_code = f.get("departure_airport", {}).get("id", "")
                arr_code = f.get("arrival_airport", {}).get("id", "")
                flight_num = f.get("flight_number", "")

                segment = FlightSegment(
                    carrier_code=airline[:2].upper(),
                    flight_number=flight_num,
                    departure_airport=dep_code,
                    arrival_airport=arr_code,
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration=f"{f.get('duration', 0)}m",
                    aircraft=f.get("airplane"),
                    cabin_class=f.get("travel_class")
                )
                return_segments.append(segment)

            if not return_segments:
                return

            # Populate return flight info
            return_duration_minutes = best_return.get("total_duration", 0)
            hours = return_duration_minutes // 60
            minutes = return_duration_minutes % 60

            offer.return_departure_time = return_segments[0].departure_time
            offer.return_arrival_time = return_segments[-1].arrival_time
            offer.return_duration = f"{hours}h {minutes}m"
            offer.return_stops = len(return_segments) - 1
            offer.return_segments = return_segments

            # Add return airlines to carrier codes
            for seg in return_segments:
                if seg.carrier_code and seg.carrier_code not in offer.carrier_codes:
                    offer.carrier_codes.append(seg.carrier_code)

            logger.debug(f"Populated return flight: {offer.return_departure_time} -> {offer.return_arrival_time}")

        except Exception as e:
            logger.warning(f"Error populating return info: {e}")

    async def health_check(self) -> Dict:
        """Check if API key is valid by making a lightweight request."""
        try:
            # Minimal search (Coffee in Austin - default SerpApi test)
            # But we should use google_flights engine to be sure
            params = {
                "engine": "google_flights",
                "api_key": self.api_key,
                "departure_id": "JFK",
                "arrival_id": "LHR",
                "outbound_date": "2026-12-01",
                "type": "2" # One way to avoid missing return_date error
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.BASE_URL, params=params)
                if response.status_code == 200:
                    return {"status": "healthy", "message": "SerpApi connection successful"}
                else:
                    return {"status": "unavailable", "message": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "unavailable", "message": str(e)}

    async def validate_credentials(self) -> bool:
        health = await self.health_check()
        return health["status"] == "healthy"
