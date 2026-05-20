"""Shared provider alias rules for typed integrations."""

from __future__ import annotations

from typing import Dict


SEARCH_PROVIDER_ALIASES: Dict[str, str] = {
    "brave_search": "brave",
    "google_search": "google",
    "serpapi": "google",
}

FLIGHT_PROVIDER_ALIASES: Dict[str, str] = {
    "serpapi": "google_flights",
}

def normalize_search_provider_id(provider_id: str) -> str:
    """Return the canonical SearchProviderRegistry id for a stored provider."""
    normalized = str(provider_id or "").strip().lower()
    return SEARCH_PROVIDER_ALIASES.get(normalized, normalized)


def normalize_flight_provider_id(provider_id: str) -> str:
    """Return the canonical FlightProviderRegistry id for a stored provider."""
    normalized = str(provider_id or "").strip().lower()
    return FLIGHT_PROVIDER_ALIASES.get(normalized, normalized)
