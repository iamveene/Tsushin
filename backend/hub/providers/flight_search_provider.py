"""
Flight Search Provider - Abstract Base Class
Defines the interface that all flight search providers must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging


@dataclass
class FlightSearchRequest:
    """
    Standardized flight search request.
    Provider-agnostic representation of search parameters.
    """
    origin: str                    # IATA code (e.g., "GRU", "JFK")
    destination: str               # IATA code (e.g., "JFK", "LHR")
    departure_date: str            # YYYY-MM-DD format
    return_date: Optional[str] = None     # YYYY-MM-DD (optional, for round-trip)
    adults: int = 1
    children: int = 0
    infants: int = 0
    travel_class: str = "ECONOMY"  # ECONOMY, PREMIUM_ECONOMY, BUSINESS, FIRST
    currency: str = "USD"
    max_results: int = 5
    prefer_direct: bool = False

    def __post_init__(self):
        """Validate request parameters"""
        self.origin = self.origin.upper()
        self.destination = self.destination.upper()

        if len(self.origin) != 3 or len(self.destination) != 3:
            raise ValueError("Airport codes must be 3 letters (IATA format)")

        if self.adults < 1 or self.adults > 9:
            raise ValueError("Adults must be between 1 and 9")

        if self.travel_class not in ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"]:
            raise ValueError("Invalid travel class")


@dataclass
class FlightSegment:
    """Individual flight segment within an itinerary"""
    carrier_code: str              # Airline IATA code (e.g., "AA", "DL")
    flight_number: str
    departure_airport: str         # IATA code
    arrival_airport: str           # IATA code
    departure_time: str            # ISO format datetime
    arrival_time: str              # ISO format datetime
    duration: str                  # e.g., "2h 30m"
    aircraft: Optional[str] = None
    cabin_class: Optional[str] = None


@dataclass
class FlightOffer:
    """
    Standardized flight offer result.
    Provider-agnostic representation of a flight option.
    """
    id: str
    price: float
    currency: str
    airline: str                   # Primary airline name
    carrier_codes: List[str]       # All airline codes in itinerary
    duration: str                  # Outbound duration (e.g., "5h 30m")
    departure_time: str            # Outbound departure time
    arrival_time: str              # Outbound arrival time
    stops: int                     # Number of stops on outbound (0 = direct)
    segments: List[FlightSegment]  # Outbound segment information
    # Return flight fields (for round-trip)
    return_departure_time: Optional[str] = None   # Return departure time
    return_arrival_time: Optional[str] = None     # Return arrival time
    return_duration: Optional[str] = None         # Return duration
    return_stops: Optional[int] = None            # Number of stops on return
    return_segments: List[FlightSegment] = field(default_factory=list)  # Return segments
    # Other fields
    booking_url: Optional[str] = None
    validating_airline: Optional[str] = None
    last_ticketing_date: Optional[str] = None
    is_refundable: bool = False

    def is_direct(self) -> bool:
        """Check if outbound is a direct flight"""
        return self.stops == 0

    def is_round_trip(self) -> bool:
        """Check if this is a round-trip offer"""
        return self.return_departure_time is not None


@dataclass
class FlightSearchResponse:
    """
    Standardized search response.
    Contains search results and metadata from any provider.
    """
    success: bool
    offers: List[FlightOffer]
    provider: str                  # Provider identifier (e.g., "amadeus")
    search_request: FlightSearchRequest
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)  # Provider-specific data
    search_timestamp: datetime = field(default_factory=datetime.utcnow)

    def get_cheapest(self) -> Optional[FlightOffer]:
        """Get the cheapest flight offer"""
        if not self.offers:
            return None
        return min(self.offers, key=lambda x: x.price)

    def get_fastest(self) -> Optional[FlightOffer]:
        """Get the fastest flight offer"""
        if not self.offers:
            return None
        # Parse duration strings and find minimum
        def parse_duration(duration_str: str) -> int:
            """Convert duration string to minutes"""
            total_minutes = 0
            parts = duration_str.replace('h', '').replace('m', '').split()
            if len(parts) >= 1:
                total_minutes += int(parts[0]) * 60
            if len(parts) >= 2:
                total_minutes += int(parts[1])
            return total_minutes

        return min(self.offers, key=lambda x: parse_duration(x.duration))

    def get_direct_flights(self) -> List[FlightOffer]:
        """Get only direct flights"""
        return [offer for offer in self.offers if offer.is_direct()]


class FlightSearchProvider(ABC):
    """
    Abstract base class for flight search providers.
    All flight search providers (Amadeus, Skyscanner, etc.) must implement this interface.

    This enables provider-agnostic flight search where agents can switch
    between different providers without code changes.
    """

    def __init__(self, integration, db):
        """
        Initialize provider with Hub integration.

        Args:
            integration: HubIntegration instance (e.g., AmadeusIntegration)
            db: Database session
        """
        self.integration = integration
        self.db = db
        self.provider_name = self.get_provider_name()
        self.logger = logging.getLogger(f"{__name__}.{self.provider_name}")

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Return provider identifier.

        Returns:
            Provider name (e.g., 'amadeus', 'skyscanner', 'google_flights')
        """
        pass

    @abstractmethod
    async def search_flights(self, request: FlightSearchRequest) -> FlightSearchResponse:
        """
        Execute flight search with provider API.

        Args:
            request: Standardized search request

        Returns:
            Standardized search response with flight offers
        """
        pass

    @abstractmethod
    async def health_check(self) -> Dict:
        """
        Check provider API connectivity and token validity.

        Returns:
            Health status dict with keys:
            - status: "healthy" | "degraded" | "unavailable"
            - message: Human-readable status message
            - details: Additional diagnostic information
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are correctly configured.

        Returns:
            True if credentials are valid, False otherwise
        """
        pass

    def format_results(self, response: FlightSearchResponse) -> str:
        """
        Format search results for agent response.

        Default implementation that providers can override for custom formatting.

        Args:
            response: Search response to format

        Returns:
            Formatted string for agent output
        """
        if not response.success:
            request = response.search_request
            is_round_trip = request.return_date is not None
            output = [f"❌ Error searching flights: {response.error}"]
            output.append("")
            output.append(f"**Route:** {request.origin} ↔ {request.destination}" if is_round_trip else f"**Route:** {request.origin} → {request.destination}")
            output.append(f"**Departure:** {request.departure_date}")
            if is_round_trip:
                output.append(f"**Return:** {request.return_date}")
            output.append(f"**Passengers:** {request.adults} adult(s)")
            output.append("\n---")
            output.append(f"**🔗 View on Google Flights:** {self._generate_google_flights_url(request)}")
            return "\n".join(output)

        request = response.search_request
        is_round_trip = request.return_date is not None

        if not response.offers:
            output = [f"✈️ **Flight Search Results** (via {response.provider.title()})\n"]
            output.append(
                f"**Route:** {request.origin} ↔ {request.destination}"
                if is_round_trip
                else f"**Route:** {request.origin} → {request.destination}"
            )
            output.append(f"**Departure:** {request.departure_date}")
            if is_round_trip:
                output.append(f"**Return:** {request.return_date}")
            output.append(f"**Passengers:** {request.adults} adult(s)")
            output.append("\nNo flights found for your search criteria.")
            output.append("\n---")
            output.append(f"**🔗 View on Google Flights:** {self._generate_google_flights_url(request)}")
            return "\n".join(output)

        output = [f"✈️ **Flight Search Results** (via {response.provider.title()})\n"]
        output.append(f"**Route:** {request.origin} ↔ {request.destination}" if is_round_trip else f"**Route:** {request.origin} → {request.destination}")
        output.append(f"**Departure:** {request.departure_date}")

        if is_round_trip:
            output.append(f"**Return:** {request.return_date}")

        output.append(f"**Passengers:** {request.adults} adult(s)")
        output.append(f"\nFound {len(response.offers)} option(s):\n")

        for idx, offer in enumerate(response.offers[:request.max_results], 1):
            outbound_stops_text = "Direct" if offer.stops == 0 else f"{offer.stops} stop(s)"

            output.append(f"\n**Option {idx}:**")
            output.append(f"  💰 **Total Price:** {offer.currency} {offer.price:.2f}")
            output.append(f"  ✈️  **Airline(s):** {', '.join(offer.carrier_codes)}")

            # Outbound flight
            output.append(f"\n  📤 **OUTBOUND** ({request.origin} → {request.destination})")
            output.append(f"      ⏱️  Duration: {offer.duration} ({outbound_stops_text})")
            output.append(f"      🛫 Departure: {offer.departure_time}")
            output.append(f"      🛬 Arrival: {offer.arrival_time}")

            # Return flight (if round-trip)
            if offer.is_round_trip():
                return_stops_text = "Direct" if offer.return_stops == 0 else f"{offer.return_stops} stop(s)"
                output.append(f"\n  📥 **RETURN** ({request.destination} → {request.origin})")
                output.append(f"      ⏱️  Duration: {offer.return_duration} ({return_stops_text})")
                output.append(f"      🛫 Departure: {offer.return_departure_time}")
                output.append(f"      🛬 Arrival: {offer.return_arrival_time}")

            # Show refundability if available
            if offer.is_refundable:
                output.append(f"  ♻️  Refundable")

        # Add recommendations section
        output.append("\n---")
        output.append("**💡 RECOMMENDATIONS:**\n")

        # Best price overall
        cheapest = response.get_cheapest()
        if cheapest:
            cheapest_idx = response.offers.index(cheapest) + 1
            output.append(f"💰 **Best Price:** Option {cheapest_idx} - {cheapest.currency} {cheapest.price:.2f}")

        # Best outbound (shortest duration)
        best_outbound = self._get_shortest_outbound(response.offers[:request.max_results])
        if best_outbound:
            outbound_idx = response.offers.index(best_outbound) + 1
            output.append(f"📤 **Best Outbound:** Option {outbound_idx} - {best_outbound.duration} ({request.origin}→{request.destination})")

        # Best return (shortest duration) - only for round-trips
        if is_round_trip:
            best_return = self._get_shortest_return(response.offers[:request.max_results])
            if best_return:
                return_idx = response.offers.index(best_return) + 1
                output.append(f"📥 **Best Return:** Option {return_idx} - {best_return.return_duration} ({request.destination}→{request.origin})")

        # Direct flights info
        direct_flights = response.get_direct_flights()
        if direct_flights and len(direct_flights) < len(response.offers):
            output.append(f"✈️  **Direct outbound flights available:** {len(direct_flights)}")

        # Add Google Flights link
        google_flights_url = self._generate_google_flights_url(request)
        output.append("\n---")
        output.append(f"**🔗 View on Google Flights:** {google_flights_url}")

        return "\n".join(output)

    def _parse_duration_to_minutes(self, duration_str: str) -> int:
        """Convert duration string like '14h 20m' to minutes."""
        if not duration_str:
            return float('inf')
        total_minutes = 0
        parts = duration_str.replace('h', '').replace('m', '').split()
        if len(parts) >= 1:
            try:
                total_minutes += int(parts[0]) * 60
            except ValueError:
                pass
        if len(parts) >= 2:
            try:
                total_minutes += int(parts[1])
            except ValueError:
                pass
        return total_minutes if total_minutes > 0 else float('inf')

    def _get_shortest_outbound(self, offers: List[FlightOffer]) -> Optional[FlightOffer]:
        """Get the offer with shortest outbound flight duration."""
        if not offers:
            return None
        return min(offers, key=lambda x: self._parse_duration_to_minutes(x.duration))

    def _get_shortest_return(self, offers: List[FlightOffer]) -> Optional[FlightOffer]:
        """Get the offer with shortest return flight duration."""
        valid_offers = [o for o in offers if o.is_round_trip() and o.return_duration]
        if not valid_offers:
            return None
        return min(valid_offers, key=lambda x: self._parse_duration_to_minutes(x.return_duration))

    def _generate_google_flights_url(self, request: FlightSearchRequest) -> str:
        """
        Generate a Google Flights URL with pre-filled search parameters.

        Args:
            request: Flight search request with origin, destination, dates, etc.

        Returns:
            Google Flights URL string with pre-filled parameters

        Example:
            One-way: https://www.google.com/travel/flights?q=Flights%20to%20FCO%20from%20VIX%20on%202026-06-04%20oneway&curr=BRL
            Round-trip: https://www.google.com/travel/flights?q=Flights%20to%20FCO%20from%20VIX%20on%202026-06-04%20through%202026-06-22&curr=BRL
        """
        from urllib.parse import quote

        # Build the query string
        query_parts = [
            f"Flights to {request.destination} from {request.origin}",
            f"on {request.departure_date}"
        ]

        if request.return_date:
            query_parts.append(f"through {request.return_date}")
        else:
            query_parts.append("oneway")

        if request.adults > 1:
            query_parts.append(f"with {request.adults} seats")

        query = " ".join(query_parts)
        encoded_query = quote(query)

        return f"https://www.google.com/travel/flights?q={encoded_query}&curr={request.currency}"

    def get_provider_info(self) -> Dict:
        """
        Get provider information and status.

        Returns:
            Provider info dict with name, status, configuration
        """
        return {
            "name": self.provider_name,
            "integration_id": self.integration.id if self.integration else None,
            "is_active": self.integration.is_active if self.integration else False,
            "health_status": self.integration.health_status if self.integration else "unknown"
        }
