"""
Fixtures for testing LLM configuration and AIClient mocking.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


@pytest.fixture
def mock_ai_client():
    """
    Mock AIClient that captures initialization parameters.

    Returns a tuple of (mock_class, mock_instance) where:
    - mock_class is the patched AIClient class
    - mock_instance has provider/model_name attributes set during __init__

    Usage:
        def test_something(mock_ai_client):
            mock_class, mock_instance = mock_ai_client
            # ... call code that creates AIClient
            assert mock_instance.provider == 'anthropic'
            assert mock_instance.model_name == 'claude-3-5-sonnet'
    """
    with patch('agent.ai_client.AIClient') as mock_class:
        mock_instance = MagicMock()
        mock_instance.generate = AsyncMock(return_value={
            'answer': 'Mocked LLM response',
            'token_usage': {'prompt': 10, 'completion': 20, 'total': 30},
            'error': None
        })
        mock_instance.provider = None
        mock_instance.model_name = None
        mock_instance.db = None

        def capture_init(provider, model_name, db=None, **kwargs):
            """Capture initialization parameters."""
            mock_instance.provider = provider
            mock_instance.model_name = model_name
            mock_instance.db = db
            return mock_instance

        mock_class.side_effect = capture_init
        yield mock_class, mock_instance


@pytest.fixture
def test_agent_config():
    """
    Test configuration with non-Gemini LLM to detect hardcoding.

    Uses Anthropic/Claude to ensure tests catch any hardcoded Gemini references.
    """
    return {
        'agent_id': 999,
        'tenant_id': 'test-tenant',
        'model_provider': 'anthropic',  # Non-Gemini to detect hardcoding
        'model_name': 'claude-3-5-sonnet',
        'system_prompt': 'Test agent',
        'temperature': 0.7,
        'max_tokens': 4096,
    }


@pytest.fixture
def test_agent_openai_config():
    """
    Test configuration with OpenAI to verify provider switching.
    """
    return {
        'agent_id': 888,
        'tenant_id': 'test-tenant',
        'model_provider': 'openai',
        'model_name': 'gpt-4o',
        'system_prompt': 'Test agent with OpenAI',
        'temperature': 0.7,
        'max_tokens': 4096,
    }


@pytest.fixture
def test_agent_gemini_config():
    """
    Test configuration with Gemini (legitimate use case).
    """
    return {
        'agent_id': 777,
        'tenant_id': 'test-tenant',
        'model_provider': 'gemini',
        'model_name': 'gemini-2.5-pro',
        'system_prompt': 'Test agent with Gemini',
        'temperature': 0.7,
        'max_tokens': 8192,
    }


@pytest.fixture
def test_agent_ollama_config():
    """
    Test configuration with Ollama for local model testing.
    """
    return {
        'agent_id': 666,
        'tenant_id': 'test-tenant',
        'model_provider': 'ollama',
        'model_name': 'llama3.1:8b',
        'system_prompt': 'Test agent with Ollama',
        'temperature': 0.7,
        'max_tokens': 4096,
    }


@pytest.fixture
def test_agent_openrouter_config():
    """
    Test configuration with OpenRouter.
    """
    return {
        'agent_id': 555,
        'tenant_id': 'test-tenant',
        'model_provider': 'openrouter',
        'model_name': 'anthropic/claude-3.5-sonnet',
        'system_prompt': 'Test agent with OpenRouter',
        'temperature': 0.7,
        'max_tokens': 4096,
    }
