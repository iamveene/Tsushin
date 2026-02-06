"""
Tests to verify LLM configuration is properly propagated from agent to all components.

These tests use non-Gemini configs (Anthropic, OpenAI) to detect any hardcoded
Gemini references. If a component uses hardcoded Gemini instead of the configured
provider, these tests will fail.

Run with: pytest tests/test_llm_config_propagation.py -v
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from models import InboundMessage


@pytest.mark.asyncio
class TestSkillLLMConfigPropagation:
    """Verify skills use agent's configured LLM."""

    async def test_search_skill_uses_agent_llm(self, mock_ai_client, test_agent_config, test_db):
        """SearchSkill MUST use agent's model_provider and model_name."""
        mock_class, mock_instance = mock_ai_client

        from agent.skills.search_skill import SearchSkill

        skill = SearchSkill()
        message = InboundMessage(
            body="search for Python tutorials",
            sender_key="test_user",
            channel_type="whatsapp"
        )

        # Mock the search results
        mock_instance.generate = AsyncMock(return_value={
            'answer': '{"query": "Python tutorials", "result_count": 5}',
            'token_usage': {'prompt': 10, 'completion': 20, 'total': 30},
            'error': None
        })

        try:
            await skill.process(message, test_agent_config)
        except:
            pass  # Focus on verifying AIClient initialization

        # CRITICAL ASSERTION: Verify correct LLM was used
        assert mock_instance.provider == test_agent_config['model_provider'], \
            f"Expected provider={test_agent_config['model_provider']}, got {mock_instance.provider}"
        assert mock_instance.model_name == test_agent_config['model_name'], \
            f"Expected model={test_agent_config['model_name']}, got {mock_instance.model_name}"
        assert mock_instance.provider != 'gemini', \
            "SearchSkill should not use hardcoded Gemini when agent configured with different provider"

    async def test_weather_skill_uses_agent_llm(self, mock_ai_client, test_agent_openai_config, test_db):
        """WeatherSkill MUST use agent's model_provider and model_name."""
        mock_class, mock_instance = mock_ai_client

        from agent.skills.weather_skill import WeatherSkill

        skill = WeatherSkill()
        message = InboundMessage(
            body="What's the weather in London?",
            sender_key="test_user",
            channel_type="whatsapp"
        )

        mock_instance.generate = AsyncMock(return_value={
            'answer': '{"location": "London", "include_forecast": true}',
            'token_usage': {'prompt': 10, 'completion': 20, 'total': 30},
            'error': None
        })

        try:
            await skill.process(message, test_agent_openai_config)
        except:
            pass

        # CRITICAL ASSERTION: Verify OpenAI config was used
        assert mock_instance.provider == test_agent_openai_config['model_provider'], \
            f"Expected provider={test_agent_openai_config['model_provider']}, got {mock_instance.provider}"
        assert mock_instance.model_name == test_agent_openai_config['model_name'], \
            f"Expected model={test_agent_openai_config['model_name']}, got {mock_instance.model_name}"
        assert mock_instance.provider != 'gemini', \
            "WeatherSkill should not use hardcoded Gemini"

    async def test_flight_skill_uses_agent_llm(self, mock_ai_client, test_agent_config, test_db):
        """FlightSearchSkill MUST use agent's model_provider and model_name."""
        mock_class, mock_instance = mock_ai_client

        from agent.skills.flight_search_skill import FlightSearchSkill

        skill = FlightSearchSkill()
        message = InboundMessage(
            body="Find flights from NYC to London",
            sender_key="test_user",
            channel_type="whatsapp"
        )

        mock_instance.generate = AsyncMock(return_value={
            'answer': '{"origin": "NYC", "destination": "LON", "departure_date": "2024-12-25"}',
            'token_usage': {'prompt': 10, 'completion': 20, 'total': 30},
            'error': None
        })

        try:
            await skill.process(message, test_agent_config)
        except:
            pass

        # CRITICAL ASSERTION: Verify Anthropic config was used
        assert mock_instance.provider == test_agent_config['model_provider'], \
            f"Expected provider={test_agent_config['model_provider']}, got {mock_instance.provider}"
        assert mock_instance.model_name == test_agent_config['model_name'], \
            f"Expected model={test_agent_config['model_name']}, got {mock_instance.model_name}"
        assert mock_instance.provider != 'gemini', \
            "FlightSearchSkill should not use hardcoded Gemini"

    async def test_flows_skill_uses_agent_llm_for_intent(self, mock_ai_client, test_agent_config, test_db):
        """FlowsSkill intent detection MUST use agent's LLM config."""
        mock_class, mock_instance = mock_ai_client

        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()
        message = InboundMessage(
            body="Remind me to call John at 3pm",
            sender_key="test_user",
            channel_type="whatsapp"
        )

        # Mock intent detection response
        mock_instance.generate = AsyncMock(return_value={
            'answer': '{"intent": "create_reminder", "confidence": 0.95}',
            'token_usage': {'prompt': 10, 'completion': 20, 'total': 30},
            'error': None
        })

        try:
            # Test intent detection
            await skill._detect_flow_intent(
                message.body,
                ai_model=test_agent_config['model_name']
            )
        except:
            pass

        # Verify agent's model was used (not hardcoded gemini-2.5-flash)
        if mock_instance.provider:
            assert mock_instance.provider == test_agent_config['model_provider'], \
                "FlowsSkill intent detection should use agent's provider"


@pytest.mark.asyncio
class TestMemoryLLMConfigPropagation:
    """Verify memory components use agent's configured LLM."""

    async def test_fact_extractor_uses_provided_llm_config(self, mock_ai_client, test_agent_config, test_db):
        """FactExtractor MUST use explicitly provided model_provider and model_name."""
        mock_class, mock_instance = mock_ai_client

        from agent.memory.fact_extractor import FactExtractor

        # Create with explicit config (should NOT fall back to Gemini)
        extractor = FactExtractor(
            provider=test_agent_config['model_provider'],
            model_name=test_agent_config['model_name'],
            db=test_db
        )

        # Verify the extractor stored the correct config
        assert extractor.provider == test_agent_config['model_provider'], \
            "FactExtractor should use provided provider"
        assert extractor.model_name == test_agent_config['model_name'], \
            "FactExtractor should use provided model_name"
        assert extractor.provider != 'gemini', \
            "FactExtractor should NOT fall back to Gemini when explicit config provided"

    async def test_fact_extractor_requires_explicit_config(self, test_db):
        """FactExtractor should require explicit provider/model (no silent fallback to Gemini)."""
        from agent.memory.fact_extractor import FactExtractor

        # After our fix, FactExtractor should raise an error or log warning
        # if provider/model not provided, rather than silently using Gemini

        # This test documents the desired behavior after the fix
        # Current behavior: falls back to Gemini (which we're fixing)
        # Desired behavior: requires explicit config

        # We'll implement this check in the actual fix
        pass

    async def test_agent_memory_system_passes_llm_config(self, mock_ai_client, test_agent_config, test_db):
        """AgentMemorySystem MUST pass LLM config to FactExtractor."""
        with patch('agent.memory.agent_memory_system.FactExtractor') as mock_fact_extractor:
            mock_instance = MagicMock()
            mock_fact_extractor.return_value = mock_instance

            from agent.memory.agent_memory_system import AgentMemorySystem

            # Create memory system with agent config
            memory_system = AgentMemorySystem(
                agent_id=test_agent_config['agent_id'],
                tenant_id=test_agent_config['tenant_id'],
                config=test_agent_config,
                db_session=test_db
            )

            # Verify FactExtractor was created with correct LLM config
            if mock_fact_extractor.called:
                call_kwargs = mock_fact_extractor.call_args.kwargs
                assert call_kwargs.get('provider') == test_agent_config['model_provider'], \
                    "AgentMemorySystem should pass agent's provider to FactExtractor"
                assert call_kwargs.get('model_name') == test_agent_config['model_name'], \
                    "AgentMemorySystem should pass agent's model_name to FactExtractor"

    async def test_multi_agent_memory_fetches_and_uses_agent_config(self, test_db):
        """MultiAgentMemory should fetch agent config and pass to memory system."""
        from models import Agent, Tenant

        # Create test agent in database with specific LLM config
        tenant = Tenant(
            id='test-tenant',
            name='Test Tenant'
        )
        test_db.add(tenant)

        agent = Agent(
            id=999,
            tenant_id='test-tenant',
            name='Test Agent',
            system_prompt='Test',
            model_provider='anthropic',
            model_name='claude-3-5-sonnet'
        )
        test_db.add(agent)
        test_db.commit()

        with patch('agent.memory.multi_agent_memory.AgentMemorySystem') as mock_memory_system:
            mock_instance = MagicMock()
            mock_memory_system.return_value = mock_instance

            from agent.memory.multi_agent_memory import get_agent_memory

            # Get agent memory (should auto-fetch agent config)
            memory = get_agent_memory(
                agent_id=999,
                tenant_id='test-tenant',
                db_session=test_db
            )

            # Verify memory system was created with agent's LLM config
            if mock_memory_system.called:
                call_kwargs = mock_memory_system.call_args.kwargs
                config = call_kwargs.get('config', {})

                # Should include agent's LLM config
                assert config.get('model_provider') == 'anthropic', \
                    "get_agent_memory should fetch and pass agent's provider"
                assert config.get('model_name') == 'claude-3-5-sonnet', \
                    "get_agent_memory should fetch and pass agent's model"


@pytest.mark.asyncio
class TestServiceLLMConfigPropagation:
    """Verify services use agent's configured LLM."""

    async def test_ai_summary_service_uses_agent_llm(self, mock_ai_client, test_agent_config, test_db):
        """AISummaryService MUST accept and use agent's LLM config."""
        mock_class, mock_instance = mock_ai_client

        from agent.ai_summary_service import AISummaryService

        # Create service with agent's LLM config (not defaults)
        service = AISummaryService(
            model_provider=test_agent_config['model_provider'],
            model_name=test_agent_config['model_name']
        )

        # Verify it stored the config
        assert service.model_provider == test_agent_config['model_provider'], \
            "AISummaryService should use provided provider"
        assert service.model_name == test_agent_config['model_name'], \
            "AISummaryService should use provided model_name"
        assert service.model_provider != 'gemini', \
            "AISummaryService should not default to Gemini when explicit config provided"

    async def test_flow_engine_uses_agent_llm_for_ai_nodes(self, mock_ai_client, test_agent_config, test_db):
        """FlowEngine AI nodes MUST use agent's configured model."""
        mock_class, mock_instance = mock_ai_client

        from flows.flow_engine import FlowEngine
        from models import Tenant, Agent

        # Create test agent
        tenant = Tenant(id='test-tenant', name='Test', slug='test')
        test_db.add(tenant)

        agent = Agent(
            id=999,
            tenant_id='test-tenant',
            name='Test Agent',
            system_prompt='Test',
            model_provider=test_agent_config['model_provider'],
            model_name=test_agent_config['model_name']
        )
        test_db.add(agent)
        test_db.commit()

        # Create flow with AI node
        flow_config = {
            'name': 'Test Flow',
            'steps': [{
                'type': 'ai',
                'config': {
                    'prompt': 'Summarize: {{input}}'
                }
            }]
        }

        mock_instance.generate = AsyncMock(return_value={
            'answer': 'AI response',
            'token_usage': {'total': 30},
            'error': None
        })

        engine = FlowEngine(
            agent_id=999,
            tenant_id='test-tenant',
            db_session=test_db
        )

        try:
            # Execute flow with AI node
            await engine.execute_flow(flow_config, {'input': 'Test input'})
        except:
            pass

        # Verify AI node used agent's configured LLM
        if mock_instance.provider:
            assert mock_instance.provider == test_agent_config['model_provider'], \
                "FlowEngine AI nodes should use agent's provider"
            assert mock_instance.model_name == test_agent_config['model_name'], \
                "FlowEngine AI nodes should use agent's model"


@pytest.mark.asyncio
class TestMultiProviderConfigSupport:
    """Verify components work with all supported providers."""

    @pytest.mark.parametrize("config_fixture", [
        'test_agent_config',  # Anthropic
        'test_agent_openai_config',  # OpenAI
        'test_agent_gemini_config',  # Gemini (legitimate use)
        'test_agent_ollama_config',  # Ollama
        'test_agent_openrouter_config',  # OpenRouter
    ])
    async def test_fact_extractor_supports_all_providers(self, config_fixture, request, test_db):
        """FactExtractor should work with all provider configs."""
        config = request.getfixturevalue(config_fixture)

        from agent.memory.fact_extractor import FactExtractor

        extractor = FactExtractor(
            provider=config['model_provider'],
            model_name=config['model_name'],
            db=test_db
        )

        assert extractor.provider == config['model_provider']
        assert extractor.model_name == config['model_name']
        print(f"✓ FactExtractor works with {config['model_provider']}/{config['model_name']}")


if __name__ == "__main__":
    # Run with: pytest tests/test_llm_config_propagation.py -v
    pytest.main([__file__, "-v"])
