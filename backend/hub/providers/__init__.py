"""
Providers Package
Provides pluggable provider architectures for various services:
- Flight Search Providers (Amadeus, Skyscanner, etc.)
- TTS Providers (OpenAI, Kokoro, ElevenLabs, etc.)
- Web Search Providers (Brave, Google, etc.)
"""

# Flight Search Providers
from .flight_search_provider import (
    FlightSearchProvider,
    FlightSearchRequest,
    FlightSearchResponse,
    FlightOffer,
    FlightSegment
)
from .registry import FlightProviderRegistry

# TTS Providers
from .tts_provider import (
    TTSProvider,
    TTSRequest,
    TTSResponse,
    VoiceInfo,
    ProviderStatus
)
from .tts_registry import TTSProviderRegistry

# Web Search Providers
from .search_provider import (
    SearchProvider,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchProviderStatus
)
from .search_registry import SearchProviderRegistry

__all__ = [
    # Flight Search
    "FlightSearchProvider",
    "FlightSearchRequest",
    "FlightSearchResponse",
    "FlightOffer",
    "FlightSegment",
    "FlightProviderRegistry",
    # TTS
    "TTSProvider",
    "TTSRequest",
    "TTSResponse",
    "VoiceInfo",
    "ProviderStatus",
    "TTSProviderRegistry",
    # Web Search
    "SearchProvider",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "SearchProviderStatus",
    "SearchProviderRegistry"
]
