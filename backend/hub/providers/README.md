# Hub Provider Registries

This package contains the provider abstraction layers used by Hub integrations and agent skills.

## Provider Families

| Family | Registry | Implemented providers | Notes |
|--------|----------|-----------------------|-------|
| Flight search | `registry.py` / `FlightProviderRegistry` | Amadeus, Google Flights | Shared request/response models live in `flight_search_provider.py` |
| TTS | `tts_registry.py` / `TTSProviderRegistry` | OpenAI, Kokoro, ElevenLabs | Used by the Audio TTS skill and Hub TTS configuration |
| Web search | `search_registry.py` / `SearchProviderRegistry` | Brave Search, Google (via SerpAPI) | Used by the Web Search skill |

## Quick Start

### Using a Flight Provider

```python
from backend.hub.providers import FlightProviderRegistry
from backend.hub.providers.flight_search_provider import FlightSearchRequest

provider = FlightProviderRegistry.get_provider("amadeus", db)

request = FlightSearchRequest(
    origin="GRU",
    destination="JFK",
    departure_date="2025-03-15",
    adults=1,
    currency="USD"
)

response = await provider.search_flights(request)

for offer in response.offers:
    print(f"{offer.airline}: {offer.currency} {offer.price}")
```

## Adding a Provider

1. Implement the relevant base class (`FlightSearchProvider`, `TTSProvider`, or `SearchProvider`).
2. Register the provider in the matching registry's `initialize_providers()` method.
3. Add the supporting Hub integration model and API wiring if the provider needs tenant configuration.
4. Expose any provider-specific configuration or health-check surface needed by the UI.

## Key Files

- `flight_search_provider.py`: Flight search base classes and data models
- `registry.py`: Flight provider registration and discovery
- `tts_provider.py` / `tts_registry.py`: TTS provider interfaces and registration
- `search_provider.py` / `search_registry.py`: Web search provider interfaces and registration
- `__init__.py`: Package exports
