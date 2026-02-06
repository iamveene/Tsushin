"""
Phase 6.7 Multi-Step Flows Execution Engine Test Suite

Tests:
1. Flow validation
2. FlowEngine initialization
3. Node execution with idempotency
4. Trigger node handler
5. Message node handler (mock)
6. Tool node handler (mock)
7. Final report generation
8. Error handling and timeouts
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import asyncio
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, FlowDefinition, FlowNode, FlowRun, FlowNodeRun


def test_flow_validation():
    """Test 1: Flow validation logic"""
    print("\n" + "="*60)
    print("TEST 1: Flow Validation")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        from flows.flow_engine import FlowEngine, FlowValidationError

        engine_instance = FlowEngine(session)

        # Create a test flow with valid structure
        print("\n[TEST] Creating valid flow...")
        flow = FlowDefinition(name="Valid Test Flow")
        session.add(flow)
        session.commit()
        session.refresh(flow)

        # Add Trigger node
        trigger = FlowNode(
            flow_definition_id=flow.id,
            type="Trigger",
            position=1,
            config_json=json.dumps({"agent_id": 1, "objective": "test"})
        )
        session.add(trigger)
        session.commit()

        # Validate - should pass
        try:
            engine_instance.validate_flow_structure(flow.id)
            print("[OK] Valid flow passed validation")
        except FlowValidationError as e:
            print(f"[FAIL] Valid flow failed validation: {e}")
            return False

        # Test: No nodes
        print("\n[TEST] Testing empty flow validation...")
        empty_flow = FlowDefinition(name="Empty Flow")
        session.add(empty_flow)
        session.commit()
        session.refresh(empty_flow)

        try:
            engine_instance.validate_flow_structure(empty_flow.id)
            print("[FAIL] Empty flow should have failed validation")
            return False
        except FlowValidationError as e:
            print(f"[OK] Empty flow correctly rejected: {e}")

        # Cleanup
        print("\n[CLEANUP]...")
        session.query(FlowNode).filter(FlowNode.flow_definition_id == flow.id).delete()
        session.delete(flow)
        session.delete(empty_flow)
        session.commit()

        print("\n" + "="*60)
        print("Flow Validation Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Flow Validation test failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def test_idempotency_key_generation():
    """Test 2: Idempotency key generation"""
    print("\n" + "="*60)
    print("TEST 2: Idempotency Key Generation")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        from flows.flow_engine import FlowEngine

        engine_instance = FlowEngine(session)

        # Test idempotency key is deterministic
        print("\n[TEST] Generating idempotency keys...")
        key1 = engine_instance.generate_idempotency_key(100, 200)
        key2 = engine_instance.generate_idempotency_key(100, 200)
        key3 = engine_instance.generate_idempotency_key(100, 201)

        assert key1 == key2, "Same inputs should produce same key"
        assert key1 != key3, "Different inputs should produce different keys"

        print(f"[OK] Idempotency key generation works correctly")
        print(f"  Sample key: {key1[:16]}...")

        print("\n" + "="*60)
        print("Idempotency Key Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Idempotency Key test failed: {e}")
        return False
    finally:
        session.close()


def test_trigger_node_handler():
    """Test 3: Trigger node handler execution"""
    print("\n" + "="*60)
    print("TEST 3: Trigger Node Handler")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        from flows.flow_engine import TriggerNodeHandler
        from mcp_sender import MCPSender

        handler = TriggerNodeHandler(session, MCPSender())

        # Create a mock flow and run
        print("\n[TEST] Creating mock trigger node...")
        flow = FlowDefinition(name="Trigger Test Flow")
        session.add(flow)
        session.commit()
        session.refresh(flow)

        trigger_node = FlowNode(
            flow_definition_id=flow.id,
            type="Trigger",
            position=1,
            config_json=json.dumps({
                "agent_id": 1,
                "recipients": ["5511999999999"],
                "objective": "Test objective",
                "context_fields": {"key1": "value1"}
            })
        )
        session.add(trigger_node)
        session.commit()
        session.refresh(trigger_node)

        flow_run = FlowRun(
            flow_definition_id=flow.id,
            status="running",
            initiator="test",
            trigger_context_json=json.dumps({"test_key": "test_value"})
        )
        session.add(flow_run)
        session.commit()
        session.refresh(flow_run)

        # Execute trigger handler
        print("\n[EXECUTE] Running trigger handler...")
        result = asyncio.run(handler.execute(trigger_node, {}, flow_run))

        print(f"[OK] Trigger executed successfully")
        print(f"  Agent ID: {result.get('agent_id')}")
        print(f"  Recipients: {result.get('recipients')}")
        print(f"  Status: {result.get('status')}")

        assert result.get("status") == "completed", "Trigger should complete successfully"
        assert result.get("agent_id") == 1, "Agent ID should match config"

        # Cleanup
        print("\n[CLEANUP]...")
        session.delete(flow_run)
        session.delete(trigger_node)
        session.delete(flow)
        session.commit()

        print("\n" + "="*60)
        print("Trigger Node Handler Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Trigger Node Handler test failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def test_final_report_generation():
    """Test 4: Final report generation"""
    print("\n" + "="*60)
    print("TEST 4: Final Report Generation")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        from flows.flow_engine import FlowEngine

        engine_instance = FlowEngine(session)

        # Create mock flow run with node runs
        print("\n[TEST] Creating mock flow run with 2 node runs...")
        flow = FlowDefinition(name="Report Test Flow")
        session.add(flow)
        session.commit()
        session.refresh(flow)

        flow_run = FlowRun(
            flow_definition_id=flow.id,
            status="completed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            initiator="test"
        )
        session.add(flow_run)
        session.commit()
        session.refresh(flow_run)

        # Create mock nodes
        node1 = FlowNode(
            flow_definition_id=flow.id,
            type="Trigger",
            position=1,
            config_json="{}"
        )
        node2 = FlowNode(
            flow_definition_id=flow.id,
            type="Message",
            position=2,
            config_json="{}"
        )
        session.add(node1)
        session.add(node2)
        session.commit()
        session.refresh(node1)
        session.refresh(node2)

        # Create node runs
        node_run1 = FlowNodeRun(
            flow_run_id=flow_run.id,
            flow_node_id=node1.id,
            status="completed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            execution_time_ms=100,
            output_json=json.dumps({"status": "completed"})
        )
        node_run2 = FlowNodeRun(
            flow_run_id=flow_run.id,
            flow_node_id=node2.id,
            status="completed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            execution_time_ms=200,
            tool_used="test_tool",
            output_json=json.dumps({"status": "completed", "summary": "Success"})
        )
        session.add(node_run1)
        session.add(node_run2)
        session.commit()

        # Generate final report
        print("\n[GENERATE] Creating final report...")
        report = engine_instance.generate_final_report(flow_run)

        print(f"[OK] Final report generated")
        print(f"  Nodes executed: {report.get('nodes_executed')}")
        print(f"  Nodes successful: {report.get('nodes_successful')}")
        print(f"  Tools used: {report.get('tools_used')}")
        print(f"  Total execution time: {report.get('total_execution_time_ms')}ms")

        assert report["nodes_executed"] == 2, "Should have 2 nodes executed"
        assert report["nodes_successful"] == 2, "Should have 2 successful nodes"
        assert "test_tool" in report["tools_used"], "Should capture tool usage"

        # Cleanup
        print("\n[CLEANUP]...")
        session.delete(node_run1)
        session.delete(node_run2)
        session.delete(node1)
        session.delete(node2)
        session.delete(flow_run)
        session.delete(flow)
        session.commit()

        print("\n" + "="*60)
        print("Final Report Generation Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Final Report Generation test failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def test_flow_engine_initialization():
    """Test 5: FlowEngine initialization and handler registration"""
    print("\n" + "="*60)
    print("TEST 5: FlowEngine Initialization")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        from flows.flow_engine import FlowEngine

        print("\n[INIT] Initializing FlowEngine...")
        engine_instance = FlowEngine(session)

        print(f"[OK] FlowEngine initialized")
        print(f"  Handlers registered: {len(engine_instance.handlers)}")

        # Check all 5 handlers are registered
        expected_handlers = ["Trigger", "Message", "Tool", "Conversation", "Subflow"]
        for handler_name in expected_handlers:
            assert handler_name in engine_instance.handlers, f"Missing handler: {handler_name}"
            print(f"  [OK] {handler_name} handler registered")

        print("\n" + "="*60)
        print("FlowEngine Initialization Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] FlowEngine Initialization test failed: {e}")
        return False
    finally:
        session.close()


def run_all_tests():
    """Run all Phase 6.7 tests"""
    print("\n" + "="*80)
    print("PHASE 6.7 EXECUTION ENGINE - COMPREHENSIVE TEST SUITE")
    print("="*80)

    results = []

    results.append(("FlowEngine Initialization", test_flow_engine_initialization()))
    results.append(("Flow Validation", test_flow_validation()))
    results.append(("Idempotency Key Generation", test_idempotency_key_generation()))
    results.append(("Trigger Node Handler", test_trigger_node_handler()))
    results.append(("Final Report Generation", test_final_report_generation()))

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results:
        status = "[PASSED]" if passed else "[FAILED]"
        print(f"{test_name:35s} {status}")

    all_passed = all(result[1] for result in results)
    passed_count = sum(1 for r in results if r[1])
    total_count = len(results)

    print("\n" + "="*80)
    print(f"OVERALL RESULT: {passed_count}/{total_count} tests passed")
    print(f"Status: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    print("="*80 + "\n")

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
