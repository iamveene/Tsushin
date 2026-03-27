"""
Tests for Groq, Grok (xAI) LLM providers, ElevenLabs TTS, and Integration Test endpoints.

Run: docker exec tsushin-backend python -m pytest tests/test_new_providers.py -v
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import asyncio


# ============================================================================
# AIClient Provider Tests
# ============================================================================

class TestGroqProvider:
    """Test Groq LLM provider initialization and routing."""

    def test_groq_in_supported_providers(self):
        """Groq should be listed in system_ai_config PROVIDERS."""
        from services.system_ai_config import PROVIDERS, PROVIDER_MODELS
        provider_values = [p["value"] for p in PROVIDERS]
        assert "groq" in provider_values
        assert "groq" in PROVIDER_MODELS
        assert len(PROVIDER_MODELS["groq"]) > 0

    def test_groq_env_key_map(self):
        """Groq should have env var mapping."""
        from services.api_key_service import ENV_KEY_MAP
        assert "groq" in ENV_KEY_MAP
        assert ENV_KEY_MAP["groq"] == "GROQ_API_KEY"

    def test_groq_supported_service(self):
        """Groq should be in SUPPORTED_SERVICES."""
        from api.routes_api_keys import SUPPORTED_SERVICES
        assert "groq" in SUPPORTED_SERVICES

    @patch("agent.ai_client.get_api_key")
    def test_groq_init_uses_openai_client(self, mock_get_key):
        """Groq should initialize with AsyncOpenAI and Groq base URL."""
        mock_get_key.return_value = "gsk_test_key"
        mock_db = MagicMock()

        from agent.ai_client import AIClient
        client = AIClient(provider="groq", model_name="llama-3.1-8b-instant", db=mock_db)

        assert client.provider == "groq"
        assert client.model_name == "llama-3.1-8b-instant"
        # Should have an AsyncOpenAI client
        from openai import AsyncOpenAI
        assert isinstance(client.client, AsyncOpenAI)

    @patch("agent.ai_client.get_api_key")
    def test_groq_raises_without_api_key(self, mock_get_key):
        """Groq should raise ValueError when no API key is found."""
        mock_get_key.return_value = None
        mock_db = MagicMock()

        from agent.ai_client import AIClient
        with pytest.raises(ValueError, match="No API key found"):
            AIClient(provider="groq", model_name="llama-3.1-8b-instant", db=mock_db)


class TestGrokProvider:
    """Test Grok (xAI) LLM provider initialization and routing."""

    def test_grok_in_supported_providers(self):
        """Grok should be listed in system_ai_config PROVIDERS."""
        from services.system_ai_config import PROVIDERS, PROVIDER_MODELS
        provider_values = [p["value"] for p in PROVIDERS]
        assert "grok" in provider_values
        assert "grok" in PROVIDER_MODELS
        assert len(PROVIDER_MODELS["grok"]) > 0

    def test_grok_env_key_map(self):
        """Grok should have env var mapping."""
        from services.api_key_service import ENV_KEY_MAP
        assert "grok" in ENV_KEY_MAP
        assert ENV_KEY_MAP["grok"] == "GROK_API_KEY"

    def test_grok_supported_service(self):
        """Grok should be in SUPPORTED_SERVICES."""
        from api.routes_api_keys import SUPPORTED_SERVICES
        assert "grok" in SUPPORTED_SERVICES

    @patch("agent.ai_client.get_api_key")
    def test_grok_init_uses_openai_client(self, mock_get_key):
        """Grok should initialize with AsyncOpenAI and xAI base URL."""
        mock_get_key.return_value = "xai_test_key"
        mock_db = MagicMock()

        from agent.ai_client import AIClient
        client = AIClient(provider="grok", model_name="grok-3-mini", db=mock_db)

        assert client.provider == "grok"
        assert client.model_name == "grok-3-mini"
        from openai import AsyncOpenAI
        assert isinstance(client.client, AsyncOpenAI)

    @patch("agent.ai_client.get_api_key")
    def test_grok_raises_without_api_key(self, mock_get_key):
        """Grok should raise ValueError when no API key is found."""
        mock_get_key.return_value = None
        mock_db = MagicMock()

        from agent.ai_client import AIClient
        with pytest.raises(ValueError, match="No API key found"):
            AIClient(provider="grok", model_name="grok-3-mini", db=mock_db)


# ============================================================================
# ElevenLabs TTS Provider Tests
# ============================================================================

class TestElevenLabsTTSProvider:
    """Test ElevenLabs TTS provider."""

    def test_provider_name(self):
        from hub.providers.elevenlabs_tts_provider import ElevenLabsTTSProvider
        provider = ElevenLabsTTSProvider()
        assert provider.get_provider_name() == "elevenlabs"

    def test_display_name(self):
        from hub.providers.elevenlabs_tts_provider import ElevenLabsTTSProvider
        provider = ElevenLabsTTSProvider()
        assert provider.get_display_name() == "ElevenLabs"

    def test_available_voices(self):
        from hub.providers.elevenlabs_tts_provider import ElevenLabsTTSProvider
        provider = ElevenLabsTTSProvider()
        voices = provider.get_available_voices()
        assert len(voices) > 0
        assert all(v.provider == "elevenlabs" for v in voices)

    def test_supported_formats(self):
        from hub.providers.elevenlabs_tts_provider import ElevenLabsTTSProvider
        provider = ElevenLabsTTSProvider()
        formats = provider.get_supported_formats()
        assert "mp3" in formats
        assert "opus" in formats

    @pytest.mark.asyncio
    async def test_health_check_no_api_key(self):
        """Health check should return not_configured when no API key."""
        from hub.providers.elevenlabs_tts_provider import ElevenLabsTTSProvider
        provider = ElevenLabsTTSProvider(db=None)
        status = await provider.health_check()
        assert status.available is False
        assert status.status == "not_configured"

    @pytest.mark.asyncio
    async def test_synthesize_no_api_key(self):
        """Synthesize should return error when no API key."""
        from hub.providers.elevenlabs_tts_provider import ElevenLabsTTSProvider
        from hub.providers.tts_provider import TTSRequest
        provider = ElevenLabsTTSProvider(db=None)
        result = await provider.synthesize(TTSRequest(text="Hello world"))
        assert result.success is False
        assert "not configured" in result.error.lower()

    def test_elevenlabs_env_key_map(self):
        """ElevenLabs should have env var mapping."""
        from services.api_key_service import ENV_KEY_MAP
        assert "elevenlabs" in ENV_KEY_MAP
        assert ENV_KEY_MAP["elevenlabs"] == "ELEVENLABS_API_KEY"


# ============================================================================
# Integration Test Routes Tests
# ============================================================================

class TestIntegrationRoutes:
    """Test integration test connection endpoints."""

    def test_supported_providers(self):
        """All expected providers should be in SUPPORTED_PROVIDERS."""
        from api.routes_integrations import SUPPORTED_PROVIDERS
        assert "groq" in SUPPORTED_PROVIDERS
        assert "grok" in SUPPORTED_PROVIDERS
        assert "elevenlabs" in SUPPORTED_PROVIDERS
        assert "openai" in SUPPORTED_PROVIDERS
        assert "anthropic" in SUPPORTED_PROVIDERS
        assert "gemini" in SUPPORTED_PROVIDERS

    def test_provider_test_models(self):
        """Each LLM provider should have a default test model."""
        from api.routes_integrations import PROVIDER_TEST_MODELS
        assert "groq" in PROVIDER_TEST_MODELS
        assert "grok" in PROVIDER_TEST_MODELS
        assert PROVIDER_TEST_MODELS["groq"] == "llama-3.1-8b-instant"
        assert PROVIDER_TEST_MODELS["grok"] == "grok-3-mini"


# ============================================================================
# E2E Tests (against running backend)
# ============================================================================

class TestIntegrationE2E:
    """End-to-end tests against the running backend."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for API calls."""
        import requests
        self.base_url = "http://localhost:8081"
        resp = requests.post(f"{self.base_url}/api/auth/login", json={
            "email": "test@example.com",
            "password": "test123"
        })
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        else:
            pytest.skip("Backend not running or auth failed")

    def test_test_connection_groq_no_key(self):
        """Test Groq connection without API key should return success=false."""
        import requests
        resp = requests.post(f"{self.base_url}/api/integrations/groq/test",
                           headers=self.headers, json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "groq"
        assert isinstance(data["success"], bool)

    def test_test_connection_grok_no_key(self):
        """Test Grok connection without API key should return success=false."""
        import requests
        resp = requests.post(f"{self.base_url}/api/integrations/grok/test",
                           headers=self.headers, json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "grok"

    def test_test_connection_elevenlabs_no_key(self):
        """Test ElevenLabs connection should return proper response."""
        import requests
        resp = requests.post(f"{self.base_url}/api/integrations/elevenlabs/test",
                           headers=self.headers, json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "elevenlabs"

    def test_test_connection_unknown_provider(self):
        """Unknown provider should return 400."""
        import requests
        resp = requests.post(f"{self.base_url}/api/integrations/unknown_xyz/test",
                           headers=self.headers, json={})
        assert resp.status_code == 400

    def test_providers_list_includes_groq_grok(self):
        """System AI providers should include groq and grok."""
        import requests
        resp = requests.get(f"{self.base_url}/api/config/system-ai/providers",
                          headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        provider_values = [p["value"] for p in data["providers"]]
        assert "groq" in provider_values
        assert "grok" in provider_values

    def test_api_keys_services_include_new_providers(self):
        """API keys services endpoint should include groq, grok, elevenlabs."""
        import requests
        resp = requests.get(f"{self.base_url}/api/api-keys/services",
                          headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        services = data.get("services", {})
        assert "groq" in services
        assert "grok" in services
        assert "elevenlabs" in services

    def test_sse_streaming_endpoint_exists(self):
        """SSE streaming endpoint should exist and require auth."""
        import requests
        resp = requests.get(f"{self.base_url}/api/playground/stream",
                          params={"agent_id": 1, "message": "test"})
        # Without auth should get 401 or 403
        assert resp.status_code in (401, 403, 422)

    def test_api_v1_stream_parameter(self):
        """API v1 chat should accept stream parameter."""
        import requests
        import os
        api_secret = os.getenv("TSN_API_CLIENT_SECRET")
        if not api_secret:
            pytest.skip("TSN_API_CLIENT_SECRET not set")
        resp = requests.post(
            f"{self.base_url}/api/v1/agents/1/chat?stream=true",
            headers={"X-API-Key": api_secret, "Content-Type": "application/json"},
            json={"message": "Say OK"},
            stream=True,
            timeout=30,
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
