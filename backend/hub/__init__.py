"""
Hub Integration System

Provides a unified architecture for integrating external services
(Asana, Slack, Linear, etc.) into the Tsushin agent system.

Provider architectures:
- Flight Search Providers (Amadeus, Skyscanner, etc.)
- TTS Providers (OpenAI, Kokoro, ElevenLabs, etc.)
- Browser Automation Providers (Playwright, MCP Browser, etc.)
"""

from hub.base import HubIntegrationBase
from hub.providers import FlightProviderRegistry, TTSProviderRegistry
from hub.providers.browser_automation_registry import BrowserAutomationRegistry

# Initialize providers on module import
FlightProviderRegistry.initialize_providers()
TTSProviderRegistry.initialize_providers()
BrowserAutomationRegistry.initialize_providers()

__all__ = [
    'HubIntegrationBase',
    'FlightProviderRegistry',
    'TTSProviderRegistry',
    'BrowserAutomationRegistry'
]
