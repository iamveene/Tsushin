"""Shared provider and credential alias rules.

Provider ids are what skills and integrations store in config (for example
``brave`` or ``google_flights``). API key services are what the Tool APIs page
persists in ``api_keys.service`` (for example ``brave_search`` or ``serpapi``).
Keeping this mapping in one place prevents configured-state checks, runtime
resolvers, and legacy fallbacks from drifting apart.
"""

from __future__ import annotations

from typing import Dict, Tuple


SEARCH_PROVIDER_ALIASES: Dict[str, str] = {
    "brave_search": "brave",
    "google_search": "google",
    "serpapi": "google",
}

FLIGHT_PROVIDER_ALIASES: Dict[str, str] = {
    "serpapi": "google_flights",
}

API_KEY_SERVICE_CANDIDATES: Dict[str, Tuple[str, ...]] = {
    # Brave's provider id is "brave", but the Tool APIs service id is
    # "brave_search". Accept "brave" as a legacy/manual service name too.
    "brave": ("brave_search", "brave"),
    "brave_search": ("brave_search", "brave"),
    # SerpAPI backs both Google Search and Google Flights. Keep request-specific
    # priority so a dedicated legacy key still wins when the caller asked for it.
    "google": ("serpapi", "google_flights"),
    "google_search": ("serpapi", "google_flights"),
    "serpapi": ("serpapi", "google_flights"),
    "google_flights": ("google_flights", "serpapi"),
}

GOOGLE_FLIGHTS_API_KEY_SERVICES = API_KEY_SERVICE_CANDIDATES["google_flights"]


def normalize_search_provider_id(provider_id: str) -> str:
    """Return the canonical SearchProviderRegistry id for a stored provider."""
    normalized = str(provider_id or "").strip().lower()
    return SEARCH_PROVIDER_ALIASES.get(normalized, normalized)


def normalize_flight_provider_id(provider_id: str) -> str:
    """Return the canonical FlightProviderRegistry id for a stored provider."""
    normalized = str(provider_id or "").strip().lower()
    return FLIGHT_PROVIDER_ALIASES.get(normalized, normalized)


def get_api_key_service_candidates(service_or_provider: str) -> Tuple[str, ...]:
    """Return API-key service ids that can satisfy a provider/service request.

    The first item is the preferred source for that exact request; later items
    are compatibility fallbacks.
    """
    normalized = str(service_or_provider or "").strip().lower()
    if not normalized:
        return tuple()
    return API_KEY_SERVICE_CANDIDATES.get(normalized, (normalized,))
