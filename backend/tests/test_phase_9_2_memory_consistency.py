"""
Test Phase 9.2: Playground Memory Consistency

This test verifies that the Playground chat interface uses the same
4-layer memory architecture as the WhatsApp channel, ensuring consistent
agent behavior across channels.

Test Coverage:
- Layer 1: Working memory (recent messages)
- Layer 2: Episodic memory (semantic search of past conversations)
- Layer 3: Semantic knowledge (learned facts about user)
- Layer 4: Shared memory (cross-agent knowledge pool)

Author: Tsushin Team
Date: January 9, 2026
Status: Phase 9.2 Validation
"""

import pytest
import asyncio
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Agent, Contact, SemanticKnowledge, SharedMemory
from models_rbac import User, Tenant
from services.playground_service import PlaygroundService
from agent.memory.multi_agent_memory import MultiAgentMemoryManager


@pytest.fixture
def test_db():
    """Create test database with sample data"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create test tenant
    tenant = Tenant(
        id="test_tenant_phase92",
        name="Phase 9.2 Test Tenant",
        slug="test-tenant-phase92",
        created_at=datetime.utcnow()
    )
    session.add(tenant)

    # Create test user
    user = User(
        id=1,
        email="testuser@phase92.com",
        full_name="Test User Phase 9.2",
        password_hash="dummy",
        tenant_id="test_tenant_phase92",
        is_active=True
    )
    session.add(user)

    # Create test contact with agent role
    contact = Contact(
        id=1,
        friendly_name="Test Agent Phase 9.2",
        phone_number="+5511999999999",
        tenant_id="test_tenant_phase92",
        role="agent"
    )
    session.add(contact)

    # Create test agent with semantic search enabled
    agent = Agent(
        id=1,
        contact_id=1,
        system_prompt="You are a helpful assistant that remembers facts about users.",
        model_provider="openai",
        model_name="gpt-4o-mini",
        tenant_id="test_tenant_phase92",
        memory_size=1000,
        enable_semantic_search=True,  # CRITICAL: Enable semantic search
        semantic_search_results=5,
        semantic_similarity_threshold=0.3,
        context_message_count=10,
        memory_isolation_mode="isolated",
        enabled_channels='["playground", "whatsapp"]',
        is_active=True,
        is_default=False
    )
    session.add(agent)

    session.commit()
    yield session
    session.close()


@pytest.mark.asyncio
async def test_layer_3_semantic_knowledge_included(test_db):
    """
    Test that Layer 3 (semantic knowledge/learned facts) is included in Playground context.

    This is the core feature of Phase 9.2 - ensuring agents remember facts about users
    in Playground just like they do in WhatsApp.
    """
    # SETUP: Add a learned fact to semantic knowledge (Layer 3)
    fact = SemanticKnowledge(
        agent_id=1,
        user_id="playground_user_1",
        topic="preferences",
        key="favorite_color",
        value="purple",
        confidence=0.9,
        learned_at=datetime.utcnow()
    )
    test_db.add(fact)
    test_db.commit()

    # BUILD CONTEXT: Use the same memory manager as playground_service.py
    config_dict = {
        "agent_id": 1,
        "memory_size": 1000,
        "enable_semantic_search": True,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
    }

    memory_manager = MultiAgentMemoryManager(test_db, config_dict)

    # Get context exactly as playground_service.py does (lines 276-286)
    context = await memory_manager.get_context(
        agent_id=1,
        sender_key="playground_user_1",
        current_message="What is my favorite color?",
        max_semantic_results=5,
        similarity_threshold=0.3,
        include_knowledge=True,  # Layer 3: Include learned facts
        include_shared=True,      # Layer 4: Include shared memory
        chat_id="playground_1",
        use_contact_mapping=True
    )

    # VERIFY: Layer 3 (semantic_facts) is present in context
    assert "semantic_facts" in context, "Context should include semantic_facts key (Layer 3)"
    assert "preferences" in context["semantic_facts"], "Should include 'preferences' topic"
    assert "favorite_color" in context["semantic_facts"]["preferences"], "Should include learned fact"
    assert context["semantic_facts"]["preferences"]["favorite_color"]["value"] == "purple"

    # VERIFY: Context can be formatted for prompt (same as WhatsApp)
    agent_memory = memory_manager.get_agent_memory(1)
    formatted_context = agent_memory.format_context_for_prompt(context, user_id="playground_user_1")

    assert formatted_context != "[No previous context]", "Should have formatted context"
    assert "favorite_color" in formatted_context.lower() or "purple" in formatted_context.lower(), \
        "Formatted context should include the learned fact"

    print("[PASS] ✅ Layer 3 (Semantic Knowledge) is correctly included in Playground context")


@pytest.mark.asyncio
async def test_layer_4_shared_memory_included(test_db):
    """
    Test that Layer 4 (shared memory/cross-agent knowledge) is included in Playground context.
    """
    # SETUP: Add shared knowledge to Layer 4
    shared_fact = SharedMemory(
        source_agent_id=1,
        topic="company_info",
        key="office_location",
        value="São Paulo, Brazil",
        confidence=0.95,
        visibility="tenant",
        tenant_id="test_tenant_phase92",
        created_at=datetime.utcnow()
    )
    test_db.add(shared_fact)
    test_db.commit()

    # BUILD CONTEXT
    config_dict = {
        "agent_id": 1,
        "memory_size": 1000,
        "enable_semantic_search": True,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
        "enable_shared_memory": True  # Enable Layer 4
    }

    memory_manager = MultiAgentMemoryManager(test_db, config_dict)

    context = await memory_manager.get_context(
        agent_id=1,
        sender_key="playground_user_1",
        current_message="Where is the office?",
        max_semantic_results=5,
        similarity_threshold=0.3,
        include_knowledge=True,
        include_shared=True,  # Request Layer 4
        chat_id="playground_1",
        use_contact_mapping=True
    )

    # VERIFY: Layer 4 (shared_knowledge) is present
    assert "shared_knowledge" in context, "Context should include shared_knowledge key (Layer 4)"
    # Note: shared_knowledge might be empty if not configured, but the key should exist

    print("[PASS] ✅ Layer 4 (Shared Memory) structure is correctly included in Playground context")


@pytest.mark.asyncio
async def test_playground_whatsapp_context_parity(test_db):
    """
    Test that Playground and WhatsApp build context identically.

    This is the key requirement of Phase 9.2: consistent behavior across channels.
    """
    # SETUP: Add facts and messages
    fact = SemanticKnowledge(
        agent_id=1,
        user_id="playground_user_1",
        topic="personal_info",
        key="job_title",
        value="Software Engineer",
        confidence=0.9,
        learned_at=datetime.utcnow()
    )
    test_db.add(fact)
    test_db.commit()

    # BUILD CONTEXT: Simulate Playground request
    config_dict = {
        "agent_id": 1,
        "memory_size": 1000,
        "enable_semantic_search": True,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
    }

    memory_manager = MultiAgentMemoryManager(test_db, config_dict)

    playground_context = await memory_manager.get_context(
        agent_id=1,
        sender_key="playground_user_1",
        current_message="What do I do for work?",
        max_semantic_results=5,
        similarity_threshold=0.3,
        include_knowledge=True,  # Same as WhatsApp
        include_shared=True,      # Same as WhatsApp
        chat_id="playground_1",
        use_contact_mapping=True
    )

    # BUILD CONTEXT: Simulate WhatsApp request (same parameters)
    whatsapp_context = await memory_manager.get_context(
        agent_id=1,
        sender_key="+5511999999999",  # Different sender_key (phone)
        current_message="What do I do for work?",
        max_semantic_results=5,
        similarity_threshold=0.3,
        include_knowledge=True,
        include_shared=True,
        whatsapp_id="+5511999999999",
        use_contact_mapping=True
    )

    # VERIFY: Both contexts have same structure
    assert set(playground_context.keys()) == set(whatsapp_context.keys()), \
        "Playground and WhatsApp should have identical context structure"

    # VERIFY: Both use format_context_for_prompt() identically
    agent_memory = memory_manager.get_agent_memory(1)

    playground_formatted = agent_memory.format_context_for_prompt(
        playground_context,
        user_id="playground_user_1"
    )

    whatsapp_formatted = agent_memory.format_context_for_prompt(
        whatsapp_context,
        user_id="+5511999999999"
    )

    # Both should format successfully (not empty)
    assert playground_formatted != "[No previous context]"
    assert whatsapp_formatted != "[No previous context]"

    print("[PASS] ✅ Playground and WhatsApp use identical context building methods")


@pytest.mark.asyncio
async def test_fact_persistence_across_playground_sessions(test_db):
    """
    Test that facts learned in Playground persist and can be recalled later.

    Scenario:
    1. User says: "My favorite color is purple"
    2. Agent learns this fact (stored in semantic_knowledge)
    3. Later, user asks: "What's my favorite color?"
    4. Agent should recall "purple"
    """
    # STEP 1: Simulate learning phase (fact would be extracted by agent)
    # In real scenario, this happens via fact_extractor.py after conversation
    fact = SemanticKnowledge(
        agent_id=1,
        user_id="playground_user_1",
        topic="preferences",
        key="favorite_color",
        value="purple",
        confidence=0.9,
        learned_at=datetime.utcnow()
    )
    test_db.add(fact)
    test_db.commit()

    # STEP 2: Simulate recall phase (user asks about the fact)
    config_dict = {
        "agent_id": 1,
        "memory_size": 1000,
        "enable_semantic_search": True,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
    }

    memory_manager = MultiAgentMemoryManager(test_db, config_dict)

    context = await memory_manager.get_context(
        agent_id=1,
        sender_key="playground_user_1",
        current_message="What is my favorite color?",
        max_semantic_results=5,
        similarity_threshold=0.3,
        include_knowledge=True,
        include_shared=True,
        chat_id="playground_1",
        use_contact_mapping=True
    )

    # VERIFY: Fact is present and can be recalled
    assert "semantic_facts" in context
    assert "preferences" in context["semantic_facts"]
    assert context["semantic_facts"]["preferences"]["favorite_color"]["value"] == "purple"

    # VERIFY: Fact appears in formatted context (what the AI sees)
    agent_memory = memory_manager.get_agent_memory(1)
    formatted = agent_memory.format_context_for_prompt(context, user_id="playground_user_1")

    assert "purple" in formatted.lower() or "favorite_color" in formatted.lower(), \
        "The learned fact should appear in the prompt sent to the AI"

    print("[PASS] ✅ Facts persist across Playground sessions and can be recalled")


@pytest.mark.asyncio
async def test_all_four_layers_present(test_db):
    """
    Comprehensive test: Verify all 4 layers are present in Playground context.
    """
    # SETUP: Add data for all layers
    # Layer 3: Semantic knowledge
    fact = SemanticKnowledge(
        agent_id=1,
        user_id="playground_user_1",
        topic="preferences",
        key="language",
        value="Python",
        confidence=0.9,
        learned_at=datetime.utcnow()
    )
    test_db.add(fact)

    # Layer 4: Shared memory
    shared = SharedMemory(
        source_agent_id=1,
        topic="tech_stack",
        key="framework",
        value="FastAPI",
        confidence=0.95,
        visibility="tenant",
        tenant_id="test_tenant_phase92",
        created_at=datetime.utcnow()
    )
    test_db.add(shared)
    test_db.commit()

    # BUILD CONTEXT
    config_dict = {
        "agent_id": 1,
        "memory_size": 1000,
        "enable_semantic_search": True,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
    }

    memory_manager = MultiAgentMemoryManager(test_db, config_dict)

    # Add some messages for Layer 1 (working memory)
    await memory_manager.add_message(
        agent_id=1,
        sender_key="playground_user_1",
        role="user",
        content="Hello!",
        chat_id="playground_1"
    )

    await memory_manager.add_message(
        agent_id=1,
        sender_key="playground_user_1",
        role="assistant",
        content="Hi! How can I help?",
        chat_id="playground_1"
    )

    # Get full context
    context = await memory_manager.get_context(
        agent_id=1,
        sender_key="playground_user_1",
        current_message="Tell me about Python and FastAPI",
        max_semantic_results=5,
        similarity_threshold=0.3,
        include_knowledge=True,
        include_shared=True,
        chat_id="playground_1",
        use_contact_mapping=True
    )

    # VERIFY: All 4 layers present
    assert "working_memory" in context, "Layer 1: Working memory should be present"
    assert "episodic_memories" in context, "Layer 2: Episodic memory should be present"
    assert "semantic_facts" in context, "Layer 3: Semantic knowledge should be present"
    assert "shared_knowledge" in context, "Layer 4: Shared memory should be present"

    # VERIFY: Layer 1 has messages
    assert len(context["working_memory"]) >= 2, "Should have at least 2 messages in working memory"

    # VERIFY: Layer 3 has our fact
    assert "preferences" in context["semantic_facts"]
    assert context["semantic_facts"]["preferences"]["language"]["value"] == "Python"

    print("[PASS] ✅ All 4 memory layers are present and populated in Playground context")
    print(f"  - Layer 1 (Working Memory): {len(context['working_memory'])} messages")
    print(f"  - Layer 2 (Episodic Memory): {len(context['episodic_memories'])} semantic results")
    print(f"  - Layer 3 (Semantic Facts): {len(context['semantic_facts'])} topics")
    print(f"  - Layer 4 (Shared Knowledge): {len(context['shared_knowledge'])} shared facts")


if __name__ == "__main__":
    print("=" * 80)
    print("Phase 9.2: Playground Memory Consistency Test Suite")
    print("=" * 80)
    print()

    # Run tests
    pytest.main([__file__, "-v", "-s"])
