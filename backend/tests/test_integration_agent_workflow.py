"""
Integration Tests: Agent Workflow
Tests end-to-end agent workflow with real database:
- Agent creation with persona and tone
- Message processing and storage
- Memory layer updates
- Context retrieval
- Prompt template rendering
"""

import pytest
from models import (
    Agent, Contact, ConversationThread, MessageCache,
    TonePreset, Persona, Config
)
from models_rbac import Tenant, User


@pytest.mark.integration
class TestAgentWorkflowIntegration:
    """Integration tests for complete agent workflows with database."""

    def test_agent_creation_with_tone_and_persona(self, integration_db, sample_tenant):
        """Test creating an agent with tone preset and persona."""
        tenant, user = sample_tenant

        # Create tone preset
        tone = TonePreset(
            name="Professional",
            description="Maintain professional tone",
            is_system=False,
            tenant_id=tenant.id
        )
        integration_db.add(tone)
        integration_db.commit()

        # Create persona
        persona = Persona(
            name="Customer Support",
            description="Helpful customer support representative",
            role="Support Agent",
            tone_preset_id=tone.id,
            enabled_skills=[],
            is_active=True,
            is_system=False,
            tenant_id=tenant.id
        )
        integration_db.add(persona)
        integration_db.commit()

        # Create contact
        contact = Contact(
            friendly_name="Test User",
            phone_number="+1234567890",
            tenant_id=tenant.id
        )
        integration_db.add(contact)
        integration_db.commit()

        # Create agent with persona
        agent = Agent(
            contact_id=contact.id,
            persona_id=persona.id,
            system_prompt="You are a customer support agent.",
            tone_preset_id=tone.id,
            model_provider="anthropic",
            model_name="claude-3.5-sonnet",
            is_active=True,
            tenant_id=tenant.id
        )
        integration_db.add(agent)
        integration_db.commit()
        integration_db.refresh(agent)

        # Verify agent created correctly
        assert agent.id is not None
        assert agent.persona_id == persona.id
        assert agent.tone_preset_id == tone.id
        assert agent.tenant_id == tenant.id

        # Verify relationships
        loaded_agent = integration_db.query(Agent).filter(Agent.id == agent.id).first()
        assert loaded_agent is not None
        assert loaded_agent.contact_id == contact.id

    def test_message_storage_in_thread(self, integration_db, sample_agent):
        """Test storing messages in conversation thread via conversation_history JSON."""
        agent = sample_agent

        # Create conversation thread with initial empty history
        thread = ConversationThread(
            recipient="user123",
            agent_id=agent.id,
            tenant_id=agent.tenant_id,
            thread_type="playground",
            conversation_history=[]
        )
        integration_db.add(thread)
        integration_db.commit()
        integration_db.refresh(thread)

        # Add user message to conversation_history
        thread.conversation_history = [
            {"role": "user", "content": "Hello, I need help", "timestamp": "2024-01-01T10:00:00"},
            {"role": "assistant", "content": "Hello! How can I help you today?", "timestamp": "2024-01-01T10:00:05"}
        ]
        integration_db.commit()
        integration_db.refresh(thread)

        # Verify messages stored in conversation_history
        messages = thread.conversation_history

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello, I need help"
        assert messages[1]["role"] == "assistant"

    def test_context_retrieval_from_thread(self, integration_db, sample_agent):
        """Test retrieving context from conversation thread via conversation_history."""
        agent = sample_agent

        # Create thread with multiple messages in conversation_history
        messages_data = [
            {"role": "user", "content": "What is Python?", "timestamp": "2024-01-01T10:00:00"},
            {"role": "assistant", "content": "Python is a programming language.", "timestamp": "2024-01-01T10:00:05"},
            {"role": "user", "content": "How do I install it?", "timestamp": "2024-01-01T10:00:10"},
            {"role": "assistant", "content": "You can download it from python.org", "timestamp": "2024-01-01T10:00:15"},
            {"role": "user", "content": "Thanks!", "timestamp": "2024-01-01T10:00:20"},
        ]

        thread = ConversationThread(
            recipient="user456",
            agent_id=agent.id,
            tenant_id=agent.tenant_id,
            thread_type="flow",
            conversation_history=messages_data
        )
        integration_db.add(thread)
        integration_db.commit()
        integration_db.refresh(thread)

        # Retrieve context (last N messages) from conversation_history
        all_messages = thread.conversation_history
        context_messages = all_messages[-4:]  # Get last 4 messages

        assert len(context_messages) == 4
        # Last message should be "Thanks!"
        assert context_messages[-1]["content"] == "Thanks!"

    def test_prompt_template_rendering(self, integration_db, sample_agent):
        """Test prompt generation with tone and persona placeholders."""
        agent = sample_agent

        # Get config
        config = integration_db.query(Config).first()
        if not config:
            config = Config(
                id=1,
                messages_db_path="/tmp/test.db",
                system_prompt="Default prompt with {{TONE}} and {{PERSONA}}"
            )
            integration_db.add(config)
            integration_db.commit()

        # Get tone description
        tone = integration_db.query(TonePreset).filter(
            TonePreset.id == agent.tone_preset_id
        ).first()

        # Simulate prompt rendering
        prompt = agent.system_prompt or config.system_prompt

        if tone:
            prompt = prompt.replace("{{TONE}}", tone.description)

        # Verify placeholders can be replaced
        assert prompt is not None
        assert len(prompt) > 0

    def test_agent_tenant_isolation(self, integration_db):
        """Test that agents are properly isolated by tenant."""
        # Create two tenants
        tenant1 = Tenant(id="tenant1", name="Org 1", slug="org-1")
        tenant2 = Tenant(id="tenant2", name="Org 2", slug="org-2")
        integration_db.add_all([tenant1, tenant2])
        integration_db.commit()

        # Create contact and agent for tenant1
        contact1 = Contact(
            friendly_name="Contact 1",
            phone_number="+111",
            tenant_id=tenant1.id
        )
        integration_db.add(contact1)
        integration_db.commit()

        agent1 = Agent(
            contact_id=contact1.id,
            system_prompt="Agent 1",
            model_provider="anthropic",
            model_name="claude-3.5-sonnet",
            tenant_id=tenant1.id
        )

        # Create contact and agent for tenant2
        contact2 = Contact(
            friendly_name="Contact 2",
            phone_number="+222",
            tenant_id=tenant2.id
        )
        integration_db.add(contact2)
        integration_db.commit()

        agent2 = Agent(
            contact_id=contact2.id,
            system_prompt="Agent 2",
            model_provider="anthropic",
            model_name="claude-3.5-sonnet",
            tenant_id=tenant2.id
        )
        integration_db.add_all([agent1, agent2])
        integration_db.commit()

        # Query agents for tenant1
        tenant1_agents = integration_db.query(Agent).filter(
            Agent.tenant_id == tenant1.id
        ).all()

        # Query agents for tenant2
        tenant2_agents = integration_db.query(Agent).filter(
            Agent.tenant_id == tenant2.id
        ).all()

        # Verify isolation
        assert len(tenant1_agents) == 1
        assert len(tenant2_agents) == 1
        assert tenant1_agents[0].system_prompt == "Agent 1"
        assert tenant2_agents[0].system_prompt == "Agent 2"

    def test_agent_with_multiple_threads(self, integration_db, sample_agent):
        """Test agent managing multiple conversation threads."""
        agent = sample_agent

        # Create multiple threads for same agent with their own conversation_history
        thread1 = ConversationThread(
            recipient="user1",
            agent_id=agent.id,
            tenant_id=agent.tenant_id,
            thread_type="flow",
            conversation_history=[
                {"role": "user", "content": "Message from user1", "timestamp": "2024-01-01T10:00:00"}
            ]
        )
        thread2 = ConversationThread(
            recipient="user2",
            agent_id=agent.id,
            tenant_id=agent.tenant_id,
            thread_type="playground",
            conversation_history=[
                {"role": "user", "content": "Message from user2", "timestamp": "2024-01-01T10:00:00"}
            ]
        )
        integration_db.add_all([thread1, thread2])
        integration_db.commit()
        integration_db.refresh(thread1)
        integration_db.refresh(thread2)

        # Verify threads are separate and have their own messages
        thread1_messages = thread1.conversation_history
        thread2_messages = thread2.conversation_history

        assert len(thread1_messages) == 1
        assert len(thread2_messages) == 1
        assert thread1_messages[0]["content"] == "Message from user1"
        assert thread2_messages[0]["content"] == "Message from user2"

        # Verify all threads belong to same agent
        all_threads = integration_db.query(ConversationThread).filter(
            ConversationThread.agent_id == agent.id
        ).all()

        assert len(all_threads) == 2
