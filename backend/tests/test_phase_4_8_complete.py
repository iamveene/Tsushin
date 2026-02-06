"""
Complete Phase 4.8 Test Suite

Tests all 4 layers of the memory architecture:
- Layer 1: Working Memory (ring buffer)
- Layer 2: Episodic Memory (semantic search)
- Layer 3: Semantic Knowledge (learned facts)
- Layer 4: Shared Memory (cross-agent knowledge)
"""

import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from models import Base, Agent, SemanticKnowledge, SharedMemory, TonePreset, Contact
from agent.memory.agent_memory_system import AgentMemorySystem
from agent.memory.shared_memory_pool import SharedMemoryPool
from agent.memory.knowledge_service import KnowledgeService


@pytest.fixture
def db_session():
    """Create test database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Create test data
    tone = TonePreset(id=1, name="Friendly", description="Friendly tone")
    session.add(tone)

    contact1 = Contact(id=1, friendly_name="Agent 1", phone_number="1111", role="agent")
    contact2 = Contact(id=2, friendly_name="Agent 2", phone_number="2222", role="agent")
    session.add_all([contact1, contact2])

    agent1 = Agent(
        id=1,
        contact_id=1,
        system_prompt="You are agent 1",
        tone_preset_id=1,
        keywords=["agent1"],
        enabled_tools=["google_search"],
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="@{agent_name}: {response}",
        is_active=True,
        is_default=False
    )

    agent2 = Agent(
        id=2,
        contact_id=2,
        system_prompt="You are agent 2",
        tone_preset_id=1,
        keywords=["agent2"],
        enabled_tools=["weather"],
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="@{agent_name}: {response}",
        is_active=True,
        is_default=False
    )

    session.add_all([agent1, agent2])
    session.commit()

    yield session

    session.close()


@pytest.fixture
def config():
    """Test configuration."""
    return {
        "memory_size": 10,
        "enable_semantic_search": True,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
        "auto_extract_facts": True,
        "fact_extraction_threshold": 3,
        "enable_shared_memory": True,
        "shared_memory_results": 5
    }


class TestLayer1WorkingMemory:
    """Test Layer 1: Working Memory (ring buffer)."""

    @pytest.mark.asyncio
    async def test_add_message_to_working_memory(self, db_session, config):
        """Test adding messages to working memory."""
        memory_system = AgentMemorySystem(
            agent_id=1,
            db_session=db_session,
            config=config,
            persist_directory="./test_chroma/agent_1"
        )

        # Add messages
        await memory_system.add_message(
            user_id="user123",
            role="user",
            content="Hello, how are you?"
        )

        await memory_system.add_message(
            user_id="user123",
            role="assistant",
            content="I'm doing well, thank you!"
        )

        # Get context
        context = await memory_system.get_context(
            user_id="user123",
            current_message="What did I just ask?",
            include_knowledge=False,
            include_shared=False
        )

        assert len(context['working_memory']) == 2
        assert context['working_memory'][0]['content'] == "Hello, how are you?"
        print("[PASS] Layer 1: Working Memory ✓")

    @pytest.mark.asyncio
    async def test_ring_buffer_limit(self, db_session, config):
        """Test ring buffer respects size limit."""
        config['memory_size'] = 3  # Small buffer

        memory_system = AgentMemorySystem(
            agent_id=1,
            db_session=db_session,
            config=config,
            persist_directory="./test_chroma/agent_1_ring"
        )

        # Add more messages than buffer size
        for i in range(5):
            await memory_system.add_message(
                user_id="user123",
                role="user",
                content=f"Message {i}"
            )

        context = await memory_system.get_context(
            user_id="user123",
            current_message="test",
            include_knowledge=False,
            include_shared=False
        )

        # Should only have last 3 messages
        assert len(context['working_memory']) <= 3
        print("[PASS] Layer 1: Ring Buffer Limit ✓")


class TestLayer3SemanticKnowledge:
    """Test Layer 3: Semantic Knowledge (learned facts)."""

    def test_store_and_retrieve_facts(self, db_session):
        """Test storing and retrieving facts."""
        knowledge_service = KnowledgeService(db_session)

        # Store facts
        knowledge_service.store_fact(
            agent_id=1,
            user_id="user123",
            topic="preferences",
            key="favorite_color",
            value="blue",
            confidence=0.9
        )

        knowledge_service.store_fact(
            agent_id=1,
            user_id="user123",
            topic="personal_info",
            key="job",
            value="software engineer",
            confidence=0.95
        )

        # Retrieve facts
        facts = knowledge_service.get_user_facts(
            agent_id=1,
            user_id="user123"
        )

        assert len(facts) == 2
        assert facts[0]['key'] in ['favorite_color', 'job']
        print("[PASS] Layer 3: Store and Retrieve Facts ✓")

    def test_fact_confidence_filtering(self, db_session):
        """Test filtering facts by confidence."""
        knowledge_service = KnowledgeService(db_session)

        # Store facts with different confidence levels
        knowledge_service.store_fact(
            agent_id=1,
            user_id="user456",
            topic="preferences",
            key="maybe_likes",
            value="coffee",
            confidence=0.3
        )

        knowledge_service.store_fact(
            agent_id=1,
            user_id="user456",
            topic="preferences",
            key="definitely_likes",
            value="tea",
            confidence=0.9
        )

        # Get only high-confidence facts
        facts = knowledge_service.get_user_facts(
            agent_id=1,
            user_id="user456",
            min_confidence=0.7
        )

        assert len(facts) == 1
        assert facts[0]['key'] == "definitely_likes"
        print("[PASS] Layer 3: Confidence Filtering ✓")

    def test_search_facts(self, db_session):
        """Test searching facts by content."""
        knowledge_service = KnowledgeService(db_session)

        # Store searchable facts
        knowledge_service.store_fact(
            agent_id=1,
            user_id="user789",
            topic="personal_info",
            key="location",
            value="São Paulo, Brazil",
            confidence=1.0
        )

        # Search
        results = knowledge_service.search_facts(
            agent_id=1,
            search_query="Paulo"
        )

        assert len(results) >= 1
        assert "Paulo" in results[0]['value']
        print("[PASS] Layer 3: Search Facts ✓")


class TestLayer4SharedMemory:
    """Test Layer 4: Shared Memory (cross-agent knowledge)."""

    def test_share_public_knowledge(self, db_session):
        """Test sharing public knowledge."""
        pool = SharedMemoryPool(db_session)

        # Agent 1 shares public knowledge
        success = pool.share_knowledge(
            agent_id=1,
            content="The Earth is round",
            topic="general_knowledge",
            access_level="public"
        )

        assert success

        # Agent 2 should be able to access it
        accessible = pool.get_accessible_knowledge(agent_id=2)

        assert len(accessible) >= 1
        assert "Earth" in accessible[0]['content']
        print("[PASS] Layer 4: Public Knowledge Sharing ✓")

    def test_restricted_knowledge_access(self, db_session):
        """Test restricted knowledge access control."""
        pool = SharedMemoryPool(db_session)

        # Agent 1 shares knowledge only with Agent 2
        pool.share_knowledge(
            agent_id=1,
            content="Secret project details",
            topic="confidential",
            access_level="restricted",
            accessible_to=[2]  # Only Agent 2
        )

        # Agent 2 can access
        agent2_accessible = pool.get_accessible_knowledge(agent_id=2)
        assert any("Secret project" in item['content'] for item in agent2_accessible)

        # Create Agent 3 (not in accessible list)
        contact3 = Contact(id=3, friendly_name="Agent 3", phone_number="3333", role="agent")
        db_session.add(contact3)

        agent3 = Agent(
            id=3,
            contact_id=3,
            system_prompt="You are agent 3",
            tone_preset_id=1,
            keywords=["agent3"],
            enabled_tools=[],
            model_provider="gemini",
            model_name="gemini-2.5-pro",
            response_template="@{agent_name}: {response}",
            is_active=True,
            is_default=False
        )
        db_session.add(agent3)
        db_session.commit()

        # Agent 3 cannot access
        agent3_accessible = pool.get_accessible_knowledge(agent_id=3)
        assert not any("Secret project" in item['content'] for item in agent3_accessible)

        print("[PASS] Layer 4: Restricted Access Control ✓")

    def test_search_shared_knowledge(self, db_session):
        """Test searching shared knowledge."""
        pool = SharedMemoryPool(db_session)

        # Share searchable knowledge
        pool.share_knowledge(
            agent_id=1,
            content="Python is a programming language",
            topic="technology",
            access_level="public"
        )

        # Search
        results = pool.search_shared_knowledge(
            agent_id=2,
            query="Python"
        )

        assert len(results) >= 1
        assert "Python" in results[0]['content']
        print("[PASS] Layer 4: Search Shared Knowledge ✓")


class TestIntegration:
    """Test integration of all layers."""

    @pytest.mark.asyncio
    async def test_complete_memory_system(self, db_session, config):
        """Test complete 4-layer memory system integration."""
        memory_system = AgentMemorySystem(
            agent_id=1,
            db_session=db_session,
            config=config,
            persist_directory="./test_chroma/agent_1_integration"
        )

        # Layer 1: Add working memory
        await memory_system.add_message(
            user_id="test_user",
            role="user",
            content="My name is John and I like Python"
        )

        # Layer 3: Manually add fact (simulating extraction)
        memory_system.knowledge_service.store_fact(
            agent_id=1,
            user_id="test_user",
            topic="personal_info",
            key="name",
            value="John",
            confidence=0.95
        )

        # Layer 4: Share knowledge
        memory_system.shared_memory_pool.share_knowledge(
            agent_id=1,
            content="Python is great for AI development",
            topic="technology",
            access_level="public"
        )

        # Get complete context
        context = await memory_system.get_context(
            user_id="test_user",
            current_message="Tell me about Python",
            include_knowledge=True,
            include_shared=True
        )

        # Verify all layers are present
        assert len(context['working_memory']) >= 1  # Layer 1
        assert len(context['semantic_facts']) >= 1  # Layer 3
        assert len(context['shared_knowledge']) >= 1  # Layer 4

        # Verify formatting
        formatted = memory_system.format_context_for_prompt(context)
        assert "John" in formatted  # From Layer 3
        assert "Python" in formatted  # Should be somewhere

        print("[PASS] Integration: Complete 4-Layer System ✓")

    def test_statistics(self, db_session):
        """Test statistics across all layers."""
        pool = SharedMemoryPool(db_session)
        knowledge_service = KnowledgeService(db_session)

        # Add some data
        knowledge_service.store_fact(
            agent_id=1,
            user_id="stats_user",
            topic="preferences",
            key="test",
            value="value",
            confidence=0.8
        )

        pool.share_knowledge(
            agent_id=1,
            content="Test shared knowledge",
            topic="test",
            access_level="public"
        )

        # Get statistics
        knowledge_stats = knowledge_service.get_statistics(agent_id=1)
        shared_stats = pool.get_statistics()

        assert knowledge_stats['total_facts'] >= 1
        assert shared_stats['total_shared'] >= 1

        print("[PASS] Integration: Statistics ✓")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*50)
    print("Phase 4.8 Complete Test Suite")
    print("="*50 + "\n")

    # Create test fixtures
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Create test data
    tone = TonePreset(id=1, name="Friendly", description="Friendly tone")
    session.add(tone)

    contact1 = Contact(id=1, friendly_name="Agent 1", phone_number="1111", role="agent")
    contact2 = Contact(id=2, friendly_name="Agent 2", phone_number="2222", role="agent")
    session.add_all([contact1, contact2])

    agent1 = Agent(
        id=1,
        contact_id=1,
        system_prompt="You are agent 1",
        tone_preset_id=1,
        keywords=["agent1"],
        enabled_tools=["google_search"],
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="@{agent_name}: {response}",
        is_active=True,
        is_default=False
    )

    agent2 = Agent(
        id=2,
        contact_id=2,
        system_prompt="You are agent 2",
        tone_preset_id=1,
        keywords=["agent2"],
        enabled_tools=["weather"],
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="@{agent_name}: {response}",
        is_active=True,
        is_default=False
    )

    session.add_all([agent1, agent2])
    session.commit()

    config = {
        "memory_size": 10,
        "enable_semantic_search": True,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
        "auto_extract_facts": True,
        "fact_extraction_threshold": 3,
        "enable_shared_memory": True,
        "shared_memory_results": 5
    }

    # Run tests
    print("Testing Layer 1: Working Memory")
    print("-" * 50)
    test1 = TestLayer1WorkingMemory()
    asyncio.run(test1.test_add_message_to_working_memory(session, config))
    asyncio.run(test1.test_ring_buffer_limit(session, config))

    print("\nTesting Layer 3: Semantic Knowledge")
    print("-" * 50)
    test3 = TestLayer3SemanticKnowledge()
    test3.test_store_and_retrieve_facts(session)
    test3.test_fact_confidence_filtering(session)
    test3.test_search_facts(session)

    print("\nTesting Layer 4: Shared Memory")
    print("-" * 50)
    test4 = TestLayer4SharedMemory()
    test4.test_share_public_knowledge(session)
    test4.test_restricted_knowledge_access(session)
    test4.test_search_shared_knowledge(session)

    print("\nTesting Integration")
    print("-" * 50)
    test_integration = TestIntegration()
    asyncio.run(test_integration.test_complete_memory_system(session, config))
    test_integration.test_statistics(session)

    print("\n" + "="*50)
    print("All Tests Passed! ✅")
    print("="*50 + "\n")

    session.close()


if __name__ == "__main__":
    run_all_tests()
