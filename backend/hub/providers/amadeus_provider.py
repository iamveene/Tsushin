"""
Amadeus Flight Provider
Implementation of FlightSearchProvider interface for Amadeus API.
"""

import logging
from typing import Dict, List
from datetime import datetime

from .flight_search_provider import (
    FlightSearchProvider,
    FlightSearchRequest,
    FlightSearchResponse,
    FlightOffer,
    FlightSegment
)
from hub.amadeus.amadeus_service import AmadeusService
from models import AmadeusIntegration


logger = logging.getLogger(__name__)


class AmadeusFlightProvider(FlightSearchProvider):
    """
    Amadeus API implementation of flight search provider.
    Converts between standardized provider interface and Amadeus-specific format.
    """

    def __init__(self, integration: AmadeusIntegration, db):
        """
        Initialize Amadeus provider.

        Args:
            integration: AmadeusIntegration instance
            db: Database session
        """
        super().__init__(integration, db)
        self.service = AmadeusService(integration, db)

    def get_provider_name(self) -> str:
        """Return provider identifier"""
        return "amadeus"

    async def search_flights(self, request: FlightSearchRequest) -> FlightSearchResponse:
        """
        Execute flight search using Amadeus API.
        Converts standardized request → Amadeus format → standardized response.

        Args:
            request: Standardized search request

        Returns:
            Standardized search response
        """
        try:
            # Call Amadeus API
            amadeus_results = await self.service.search_flights(
                origin=request.origin,
                destination=request.destination,
                departure_date=request.departure_date,
                return_date=request.return_date,
                adults=request.adults,
                children=request.children,
                infants=request.infants,
                travel_class=request.travel_class if request.travel_class != "ECONOMY" else None,
                currency=request.currency,
                max_results=request.max_results,
                prefer_direct=request.prefer_direct
            )

            # Check for errors
            if "error" in amadeus_results:
                return FlightSearchResponse(
                    success=False,
                    offers=[],
                    provider=self.provider_name,
                    search_request=request,
                    error=amadeus_results.get("message", "Unknown error")
                )

            # Convert Amadeus format to standardized FlightOffer format
            offers = self._convert_amadeus_offers(amadeus_results)

            return FlightSearchResponse(
                success=True,
                offers=offers,
                provider=self.provider_name,
                search_request=request,
                metadata={"raw_response": amadeus_results}
            )

        except Exception as e:
            self.logger.error(f"Flight search failed: {e}", exc_info=True)
            return FlightSearchResponse(
                success=False,
                offers=[],
                provider=self.provider_name,
                search_request=request,
                error=str(e)
            )

    def _convert_amadeus_offers(self, amadeus_data: Dict) -> List[FlightOffer]:
        """
        Convert Amadeus-specific format to standardized FlightOffer.

        Args:
            amadeus_data: Raw Amadeus API response

        Returns:
            List of standardized FlightOffer objects
        """
        offers = []

        # Extract data and dictionaries
        data = amadeus_data.get('data', [])
        dictionaries = amadeus_data.get('dictionaries', {})
        carriers = dictionaries.get('carriers', {})

        for offer_data in data:
            try:
                # Extract price
                price_info = offer_data.get('price', {})
                price = float(price_info.get('total', 0))
                currency = price_info.get('currency', 'USD')

                # Extract itineraries (outbound + return if applicable)
                itineraries = offer_data.get('itineraries', [])

                if not itineraries:
                    continue

                # Get first itinerary for main flight info
                first_itinerary = itineraries[0]
                segments = first_itinerary.get('segments', [])

                if not segments:
                    continue

                # Extract main flight info from first segment
                first_segment = segments[0]
                last_segment = segments[-1]

                departure = first_segment.get('departure', {})
                arrival = last_segment.get('arrival', {})

                # Calculate total stops
                total_stops = sum(seg.get('numberOfStops', 0) for seg in segments)
                if len(segments) > 1:
                    total_stops += (len(segments) - 1)  # Count connections

                # Get carrier info
                carrier_codes = list(set(seg.get('carrierCode') for seg in segments))
                primary_carrier_code = first_segment.get('carrierCode')
                airline_name = carriers.get(primary_carrier_code, primary_carrier_code)

                # Parse duration
                duration_iso = first_itinerary.get('duration', 'PT0M')
                duration_formatted = self._format_duration(duration_iso)

                # Convert segments to standardized format
                flight_segments = []
                for seg in segments:
                    seg_departure = seg.get('departure', {})
                    seg_arrival = seg.get('arrival', {})

                    flight_segment = FlightSegment(
                        carrier_code=seg.get('carrierCode', ''),
                        flight_number=seg.get('number', ''),
                        departure_airport=seg_departure.get('iataCode', ''),
                        arrival_airport=seg_arrival.get('iataCode', ''),
                        departure_time=seg_departure.get('at', ''),
                        arrival_time=seg_arrival.get('at', ''),
                        duration=self._format_duration(seg.get('duration', 'PT0M')),
                        aircraft=seg.get('aircraft', {}).get('code'),
                        cabin_class=seg.get('cabin')
                    )
                    flight_segments.append(flight_segment)

                # Format times
                departure_time = self._format_datetime(departure.get('at', ''))
                arrival_time = self._format_datetime(arrival.get('at', ''))

                # Extract return flight info if this is a round-trip
                return_departure_time = None
                return_arrival_time = None
                return_duration = None
                return_stops = None
                return_flight_segments = []

                if len(itineraries) > 1:
                    # Round-trip: process return itinerary
                    return_itinerary = itineraries[1]
                    return_segments = return_itinerary.get('segments', [])

                    if return_segments:
                        # Extract return flight info
                        return_first_segment = return_segments[0]
                        return_last_segment = return_segments[-1]

                        return_departure = return_first_segment.get('departure', {})
                        return_arrival = return_last_segment.get('arrival', {})

                        return_departure_time = self._format_datetime(return_departure.get('at', ''))
                        return_arrival_time = self._format_datetime(return_arrival.get('at', ''))

                        # Return duration
                        return_duration_iso = return_itinerary.get('duration', 'PT0M')
                        return_duration = self._format_duration(return_duration_iso)

                        # Return stops
                        return_stops = sum(seg.get('numberOfStops', 0) for seg in return_segments)
                        if len(return_segments) > 1:
                            return_stops += (len(return_segments) - 1)

                        # Convert return segments to standardized format
                        for seg in return_segments:
                            seg_departure = seg.get('departure', {})
                            seg_arrival = seg.get('arrival', {})

                            flight_segment = FlightSegment(
                                carrier_code=seg.get('carrierCode', ''),
                                flight_number=seg.get('number', ''),
                                departure_airport=seg_departure.get('iataCode', ''),
                                arrival_airport=seg_arrival.get('iataCode', ''),
                                departure_time=seg_departure.get('at', ''),
                                arrival_time=seg_arrival.get('at', ''),
                                duration=self._format_duration(seg.get('duration', 'PT0M')),
                                aircraft=seg.get('aircraft', {}).get('code'),
                                cabin_class=seg.get('cabin')
                            )
                            return_flight_segments.append(flight_segment)

                        # Add return carrier codes to overall list
                        return_carrier_codes = list(set(seg.get('carrierCode') for seg in return_segments))
                        carrier_codes = list(set(carrier_codes + return_carrier_codes))

                # Create FlightOffer with both outbound and return info
                offer = FlightOffer(
                    id=offer_data.get('id', ''),
                    price=price,
                    currency=currency,
                    airline=airline_name,
                    carrier_codes=carrier_codes,
                    duration=duration_formatted,
                    departure_time=departure_time,
                    arrival_time=arrival_time,
                    stops=total_stops,
                    segments=flight_segments,
                    return_departure_time=return_departure_time,
                    return_arrival_time=return_arrival_time,
                    return_duration=return_duration,
                    return_stops=return_stops,
                    return_segments=return_flight_segments,
                    validating_airline=offer_data.get('validatingAirlineCodes', [None])[0],
                    last_ticketing_date=offer_data.get('lastTicketingDate'),
                    is_refundable=self._check_refundable(offer_data)
                )

                offers.append(offer)

            except Exception as e:
                self.logger.warning(f"Failed to convert offer: {e}")
                continue

        return offers

    def _format_duration(self, duration_iso: str) -> str:
        """
        Format ISO 8601 duration to human readable.

        Args:
            duration_iso: ISO duration (e.g., "PT10H30M")

        Returns:
            Formatted duration (e.g., "10h 30m")
        """
        if not duration_iso or not duration_iso.startswith('PT'):
            return duration_iso

        duration = duration_iso[2:]  # Remove 'PT'
        hours = 0
        minutes = 0

        if 'H' in duration:
            hours_str, duration = duration.split('H')
            hours = int(hours_str)

        if 'M' in duration:
            minutes_str = duration.split('M')[0]
            minutes = int(minutes_str) if minutes_str else 0

        if hours and minutes:
            return f"{hours}h {minutes}m"
        elif hours:
            return f"{hours}h"
        elif minutes:
            return f"{minutes}m"
        else:
            return "N/A"

    def _format_datetime(self, dt_str: str) -> str:
        """
        Format ISO datetime to readable format.

        Args:
            dt_str: ISO datetime string

        Returns:
            Formatted datetime string
        """
        if not dt_str:
            return "N/A"

        try:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M')
        except:
            return dt_str

    def _check_refundable(self, offer_data: Dict) -> bool:
        """Check if offer is refundable from pricing options"""
        pricing_options = offer_data.get('pricingOptions', {})
        return pricing_options.get('refundableFare', False)

    async def health_check(self) -> Dict:
        """
        Check Amadeus API connectivity and token validity.

        Returns:
            Health status dict
        """
        return await self.service.health_check()

    async def validate_credentials(self) -> bool:
        """
        Validate that API credentials are correctly configured.

        Returns:
            True if credentials are valid, False otherwise
        """
        return await self.service.validate_credentials()
