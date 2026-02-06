"""
Baseline tests to document current LLM configuration behavior.

These tests capture the CURRENT behavior (with hardcoding) so we can
verify our changes don't break existing functionality. These tests
document the bugs we're fixing, not the desired behavior.

NOTE: These tests may fail after we fix the hardcoded LLM references.
That's expected! They're here to ensure we understand the current state.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.orm import Session


@pytest.mark.asyncio
class TestCurrentBehaviorBaseline:
    """Document current behavior before refactoring."""

    async def test_search_skill_current_uses_hardcoded_gemini(self, test_db):
        """
        BASELINE: SearchSkill currently uses hardcoded Gemini.

        This documents the bug: SearchSkill creates AIClient with
        provider="gemini" and model_name="gemini-2.5-flash" regardless
        of agent configuration.
        """
        from agent.skills.search_skill import SearchSkill
        from models import InboundMessage

        with patch('agent.skills.search_skill.AIClient') as mock_ai_client:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(return_value={
                'answer': '{"query": "test", "result_count": 5}',
                'token_usage': {},
                'error': None
            })
            mock_ai_client.return_value = mock_instance

            skill = SearchSkill()
            message = InboundMessage(
                body="search for Python tutorials",
                sender_key="test_user",
                channel_type="whatsapp"
            )

            config = {
                'agent_id': 1,
                'tenant_id': 'test',
                'model_provider': 'anthropic',  # Agent configured with Anthropic
                'model_name': 'claude-3-5-sonnet',
            }

            # Execute skill
            try:
                await skill.process(message, config)
            except:
                pass  # Ignore errors, we just want to see what was called

            # BASELINE: Currently uses hardcoded Gemini
            if mock_ai_client.called:
                call_kwargs = mock_ai_client.call_args.kwargs
                # Document the bug: should use config but uses hardcoded values
                print(f"SearchSkill currently uses: provider={call_kwargs.get('provider')}, model={call_kwargs.get('model_name')}")

    async def test_weather_skill_current_uses_hardcoded_gemini(self, test_db):
        """
        BASELINE: WeatherSkill currently uses hardcoded Gemini.

        This documents the bug: WeatherSkill creates AIClient with
        provider="gemini" and model_name="gemini-2.5-flash" regardless
        of agent configuration.
        """
        from agent.skills.weather_skill import WeatherSkill
        from models import InboundMessage

        with patch('agent.skills.weather_skill.AIClient') as mock_ai_client:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(return_value={
                'answer': '{"location": "London", "include_forecast": true}',
                'token_usage': {},
                'error': None
            })
            mock_ai_client.return_value = mock_instance

            skill = WeatherSkill()
            message = InboundMessage(
                body="What's the weather in London?",
                sender_key="test_user",
                channel_type="whatsapp"
            )

            config = {
                'agent_id': 1,
                'tenant_id': 'test',
                'model_provider': 'openai',  # Agent configured with OpenAI
                'model_name': 'gpt-4o',
            }

            # Execute skill
            try:
                await skill.process(message, config)
            except:
                pass  # Ignore errors, we just want to see what was called

            # BASELINE: Currently uses hardcoded Gemini
            if mock_ai_client.called:
                call_kwargs = mock_ai_client.call_args.kwargs
                print(f"WeatherSkill currently uses: provider={call_kwargs.get('provider')}, model={call_kwargs.get('model_name')}")

    async def test_flight_skill_current_uses_hardcoded_gemini(self, test_db):
        """
        BASELINE: FlightSearchSkill currently uses hardcoded Gemini.
        """
        from agent.skills.flight_search_skill import FlightSearchSkill
        from models import InboundMessage

        with patch('agent.skills.flight_search_skill.AIClient') as mock_ai_client:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(return_value={
                'answer': '{"origin": "NYC", "destination": "LON"}',
                'token_usage': {},
                'error': None
            })
            mock_ai_client.return_value = mock_instance

            skill = FlightSearchSkill()
            message = InboundMessage(
                body="Find flights from NYC to London",
                sender_key="test_user",
                channel_type="whatsapp"
            )

            config = {
                'agent_id': 1,
                'tenant_id': 'test',
                'model_provider': 'anthropic',
                'model_name': 'claude-3-5-sonnet',
            }

            # Execute skill
            try:
                await skill.process(message, config)
            except:
                pass

            if mock_ai_client.called:
                call_kwargs = mock_ai_client.call_args.kwargs
                print(f"FlightSearchSkill currently uses: provider={call_kwargs.get('provider')}, model={call_kwargs.get('model_name')}")

    async def test_fact_extractor_current_fallback_behavior(self, test_db):
        """
        BASELINE: FactExtractor falls back to Gemini when provider/model not specified.

        This documents the bug: FactExtractor uses hardcoded defaults
        when provider or model_name are None.
        """
        from agent.memory.fact_extractor import FactExtractor

        with patch('agent.memory.fact_extractor.AIClient') as mock_ai_client:
            mock_instance = MagicMock()
            mock_instance.generate = AsyncMock(return_value={
                'answer': '[]',
                'token_usage': {},
                'error': None
            })
            mock_ai_client.return_value = mock_instance

            # Create with None values (current behavior in some code paths)
            extractor = FactExtractor(
                provider=None,  # Will fall back to "gemini"
                model_name=None,  # Will fall back to "gemini-2.5-flash"
                db=test_db
            )

            # BASELINE: Documents the fallback behavior
            assert extractor.provider == "gemini", "Currently falls back to gemini"
            assert extractor.model_name == "gemini-2.5-flash", "Currently falls back to gemini-2.5-flash"
            print(f"FactExtractor fallback: provider={extractor.provider}, model={extractor.model_name}")

    async def test_flows_skill_current_intent_detection_fallback(self, test_db):
        """
        BASELINE: FlowsSkill uses multiple Gemini fallbacks for intent detection.
        """
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        # Test the get_intent_model method
        config_without_intent_model = {'agent_id': 1}

        # This will fall back to gemini-2.5-flash
        intent_model = skill._get_intent_model(config_without_intent_model)

        # BASELINE: Documents current fallback
        print(f"FlowsSkill intent model fallback: {intent_model}")
        # Expected: "gemini-2.5-flash" (the hardcoded default)


@pytest.mark.asyncio
class TestCurrentMemorySystemBaseline:
    """Document current memory system behavior."""

    async def test_agent_memory_system_current_fact_extractor_usage(self, test_db):
        """
        BASELINE: AgentMemorySystem may not pass LLM config to FactExtractor.
        """
        from agent.memory.agent_memory_system import AgentMemorySystem

        with patch('agent.memory.agent_memory_system.FactExtractor') as mock_fact_extractor:
            mock_instance = MagicMock()
            mock_fact_extractor.return_value = mock_instance

            config = {
                'agent_id': 1,
                'tenant_id': 'test',
                'model_provider': 'anthropic',
                'model_name': 'claude-3-5-sonnet',
            }

            # Create memory system
            memory_system = AgentMemorySystem(
                agent_id=1,
                tenant_id='test',
                config=config,
                db_session=test_db
            )

            # Check what was passed to FactExtractor
            if mock_fact_extractor.called:
                call_kwargs = mock_fact_extractor.call_args.kwargs
                print(f"AgentMemorySystem passes to FactExtractor: provider={call_kwargs.get('provider')}, model={call_kwargs.get('model_name')}")


if __name__ == "__main__":
    # Run with: pytest tests/test_llm_config_baseline.py -v -s
    pytest.main([__file__, "-v", "-s"])
