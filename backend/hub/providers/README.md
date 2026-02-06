# Flight Search Providers

This directory contains the provider abstraction layer for flight search.

## Quick Start

### Using a Provider

```python
from backend.hub.providers import FlightProviderRegistry
from backend.hub.providers.flight_search_provider import FlightSearchRequest

# Get provider instance
provider = FlightProviderRegistry.get_provider("amadeus", db)

# Create search request
request = FlightSearchRequest(
    origin="GRU",
    destination="JFK",
    departure_date="2025-03-15",
    adults=1,
    currency="USD"
)

# Execute search
response = await provider.search_flights(request)

# Access results
for offer in response.offers:
    print(f"{offer.airline}: {offer.currency} {offer.price}")
```

### Adding a New Provider

1. Create provider class implementing `FlightSearchProvider`
2. Register in `registry.py` `initialize_providers()` method
3. Create Hub integration model in `models.py`
4. Add API configuration endpoints

See `FLIGHT_SEARCH_PROVIDER_ARCHITECTURE.md` for detailed instructions.

## Available Providers

- **Amadeus**: Production-ready (OAuth2, test/production environments)
- **Skyscanner**: Planned
- **Google Flights**: Planned

## Files

- `flight_search_provider.py`: Abstract base class and data models
- `amadeus_provider.py`: Amadeus API implementation
- `registry.py`: Provider registration and discovery
- `__init__.py`: Package exports
