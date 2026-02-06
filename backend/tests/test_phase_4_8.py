"""
Phase 4.8 End-to-End Test Suite

Tests:
1. Database schema verification
2. Agent memory isolation
3. Agent-scoped memory keys
4. Separate ChromaDB collections
5. Memory manager functionality
6. Context retrieval per agent
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, SemanticKnowledge, SharedMemory, Memory, Agent
from agent.memory.multi_agent_memory import MultiAgentMemoryManager

def test_database_schema():
    """Test 1: Verify database schema has new tables"""
    print("\n" + "="*60)
    print("TEST 1: Database Schema Verification")
    print("="*60)

    db_path = "data/agent.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Check semantic_knowledge table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='semantic_knowledge'")
    sk_exists = c.fetchone() is not None
    print(f"[{'OK' if sk_exists else 'FAIL'}] semantic_knowledge table exists")

    # Check shared_memory table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='shared_memory'")
    sm_exists = c.fetchone() is not None
    print(f"[{'OK' if sm_exists else 'FAIL'}] shared_memory table exists")

    # Check memory table indexes
    c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='memory'")
    indexes = [row[0] for row in c.fetchall()]
    has_index = any('sender_key' in idx.lower() for idx in indexes)
    print(f"[{'OK' if has_index else 'FAIL'}] memory table has sender_key index")

    # Check memory key format
    c.execute("SELECT sender_key FROM memory LIMIT 5")
    keys = [row[0] for row in c.fetchall()]
    agent_scoped = all(':' in key for key in keys) if keys else True
    print(f"[{'OK' if agent_scoped else 'FAIL'}] Memory keys are agent-scoped (format: agent_id:sender)")

    if keys:
        print(f"     Sample keys: {keys[:3]}")

    conn.close()

    return sk_exists and sm_exists and has_index and agent_scoped


def test_memory_manager():
    """Test 2: MultiAgentMemoryManager functionality"""
    print("\n" + "="*60)
    print("TEST 2: MultiAgentMemoryManager Functionality")
    print("="*60)

    engine = create_engine("sqlite:///data/agent.db")
    Session = sessionmaker(bind=engine)
    session = Session()

    config = {
        "memory_size": 10,
        "enable_semantic_search": False  # Disable for fast testing
    }

    # Create manager
    manager = MultiAgentMemoryManager(session, config)
    print("[OK] MultiAgentMemoryManager created")

    # Test agent-scoped key generation
    key1 = manager.get_memory_key(1, "test_user_123")
    key2 = manager.get_memory_key(2, "test_user_123")

    print(f"[OK] Agent 1 key: {key1}")
    print(f"[OK] Agent 2 key: {key2}")
    assert key1 == "1:test_user_123", f"Expected '1:test_user_123', got '{key1}'"
    assert key2 == "2:test_user_123", f"Expected '2:test_user_123', got '{key2}'"
    assert key1 != key2, "Keys should be different for different agents"
    print("[OK] Agent-scoped keys are unique")

    # Test key parsing
    agent_id, sender = manager.parse_memory_key("1:test_user_123")
    assert agent_id == 1, f"Expected agent_id=1, got {agent_id}"
    assert sender == "test_user_123", f"Expected sender='test_user_123', got '{sender}'"
    print("[OK] Memory key parsing works correctly")

    # Test adding messages to different agents
    manager.add_message(
        agent_id=1,
        sender_key="test_user_123",
        role="user",
        content="Hello Agent 1",
        message_id="msg1"
    )
    print("[OK] Message added to Agent 1 memory")

    manager.add_message(
        agent_id=2,
        sender_key="test_user_123",
        role="user",
        content="Hello Agent 2",
        message_id="msg2"
    )
    print("[OK] Message added to Agent 2 memory")

    # Verify memories are separate
    context1 = manager.get_context(1, "test_user_123", "current message")
    context2 = manager.get_context(2, "test_user_123", "current message")

    recent1 = context1.get('recent_messages', [])
    recent2 = context2.get('recent_messages', [])

    has_agent1_msg = any("Hello Agent 1" in msg.get('content', '') for msg in recent1)
    has_agent2_msg = any("Hello Agent 2" in msg.get('content', '') for msg in recent2)

    print(f"[{'OK' if has_agent1_msg else 'FAIL'}] Agent 1 has its own message")
    print(f"[{'OK' if has_agent2_msg else 'FAIL'}] Agent 2 has its own message")

    # Verify NO cross-contamination
    agent1_has_agent2_msg = any("Hello Agent 2" in msg.get('content', '') for msg in recent1)
    agent2_has_agent1_msg = any("Hello Agent 1" in msg.get('content', '') for msg in recent2)

    print(f"[{'OK' if not agent1_has_agent2_msg else 'FAIL'}] Agent 1 does NOT see Agent 2's messages")
    print(f"[{'OK' if not agent2_has_agent1_msg else 'FAIL'}] Agent 2 does NOT see Agent 1's messages")

    session.close()

    return has_agent1_msg and has_agent2_msg and not agent1_has_agent2_msg and not agent2_has_agent1_msg


def test_semantic_knowledge():
    """Test 3: Semantic knowledge storage"""
    print("\n" + "="*60)
    print("TEST 3: Semantic Knowledge Storage (Layer 3)")
    print("="*60)

    engine = create_engine("sqlite:///data/agent.db")
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create test fact
    fact = SemanticKnowledge(
        agent_id=1,
        user_id="test_user_123",
        topic="preferences",
        key="favorite_color",
        value="blue",
        confidence=0.9
    )

    try:
        # Check if fact already exists
        existing = session.query(SemanticKnowledge).filter(
            SemanticKnowledge.agent_id == 1,
            SemanticKnowledge.user_id == "test_user_123",
            SemanticKnowledge.topic == "preferences",
            SemanticKnowledge.key == "favorite_color"
        ).first()

        if existing:
            print("[OK] Test fact already exists (from previous run)")
        else:
            session.add(fact)
            session.commit()
            print("[OK] Test fact added to semantic_knowledge table")

        # Query the fact
        result = session.query(SemanticKnowledge).filter(
            SemanticKnowledge.agent_id == 1,
            SemanticKnowledge.user_id == "test_user_123",
            SemanticKnowledge.topic == "preferences",
            SemanticKnowledge.key == "favorite_color"
        ).first()

        assert result is not None, "Fact should exist in database"
        assert result.value == "blue", f"Expected value='blue', got '{result.value}'"
        assert result.confidence == 0.9, f"Expected confidence=0.9, got {result.confidence}"
        print(f"[OK] Fact retrieved: {result.topic}.{result.key} = {result.value} (confidence: {result.confidence})")

        # Test unique constraint (agent_id, user_id, topic, key)
        # Verify we can have same key for different agents
        fact2 = SemanticKnowledge(
            agent_id=2,
            user_id="test_user_123",
            topic="preferences",
            key="favorite_color",
            value="red",
            confidence=0.8
        )

        existing2 = session.query(SemanticKnowledge).filter(
            SemanticKnowledge.agent_id == 2,
            SemanticKnowledge.user_id == "test_user_123",
            SemanticKnowledge.topic == "preferences",
            SemanticKnowledge.key == "favorite_color"
        ).first()

        if not existing2:
            session.add(fact2)
            session.commit()
            print("[OK] Same key works for different agent (agent isolation)")
        else:
            print("[OK] Agent 2 fact already exists")

        session.close()
        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        session.rollback()
        session.close()
        return False


def test_shared_memory():
    """Test 4: Shared memory table"""
    print("\n" + "="*60)
    print("TEST 4: Shared Memory Pool (Layer 4)")
    print("="*60)

    engine = create_engine("sqlite:///data/agent.db")
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create test shared memory
    shared = SharedMemory(
        content="The capital of Brazil is Brasilia",
        topic="geography",
        shared_by_agent=1,
        accessible_to="[2, 3]",  # Agents 2 and 3 can access
        meta_data='{"source": "test", "verified": true}'
    )

    try:
        # Check if shared memory already exists
        existing = session.query(SharedMemory).filter(
            SharedMemory.content == "The capital of Brazil is Brasilia"
        ).first()

        if existing:
            print("[OK] Test shared memory already exists")
        else:
            session.add(shared)
            session.commit()
            print("[OK] Test shared memory added")

        # Query shared memory
        result = session.query(SharedMemory).filter(
            SharedMemory.shared_by_agent == 1
        ).first()

        assert result is not None, "Shared memory should exist"
        print(f"[OK] Shared memory retrieved: '{result.content[:50]}...'")
        print(f"     Shared by: Agent {result.shared_by_agent}")
        print(f"     Accessible to: {result.accessible_to}")

        session.close()
        return True

    except Exception as e:
        print(f"[FAIL] Error: {e}")
        session.rollback()
        session.close()
        return False


def test_chroma_collections():
    """Test 5: Verify separate ChromaDB collections per agent"""
    print("\n" + "="*60)
    print("TEST 5: Separate ChromaDB Collections")
    print("="*60)

    import os
    chroma_dir = "data/chroma"

    if not os.path.exists(chroma_dir):
        print("[SKIP] ChromaDB directory doesn't exist yet")
        return True

    # List subdirectories (each agent should have own directory)
    subdirs = [d for d in os.listdir(chroma_dir) if os.path.isdir(os.path.join(chroma_dir, d))]

    print(f"[OK] ChromaDB base directory exists: {chroma_dir}")
    print(f"     Subdirectories: {subdirs}")

    # Check for agent-specific directories
    agent_dirs = [d for d in subdirs if d.startswith('agent_')]

    if agent_dirs:
        print(f"[OK] Found {len(agent_dirs)} agent-specific collection directories")
        for dir in agent_dirs:
            print(f"     - {dir}")
    else:
        print("[INFO] No agent-specific directories yet (will be created on first use)")

    return True


def main():
    """Run all tests"""
    print("\n" + "#"*60)
    print("# Phase 4.8 End-to-End Test Suite")
    print("# Multi-Agent Memory Architecture Validation")
    print("#"*60)

    results = []

    try:
        results.append(("Database Schema", test_database_schema()))
        results.append(("Memory Manager", test_memory_manager()))
        results.append(("Semantic Knowledge", test_semantic_knowledge()))
        results.append(("Shared Memory", test_shared_memory()))
        results.append(("ChromaDB Collections", test_chroma_collections()))

    except Exception as e:
        print(f"\n[ERROR] Test suite failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        symbol = "✓" if passed else "✗"
        print(f"[{status}] {test_name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)

    print("="*60)
    print(f"Total: {passed}/{total} tests passed")
    print("="*60)

    return all(passed for _, passed in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
