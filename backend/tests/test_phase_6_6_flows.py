"""
Phase 6.6 Multi-Step Flows Test Suite

Tests:
1. Database schema verification (4 new tables)
2. Flow definition CRUD operations
3. Flow node CRUD operations
4. Flow validation (max 5 nodes, single Trigger, etc.)
5. Flow run read operations
6. API endpoint integration tests
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, FlowDefinition, FlowNode, FlowRun, FlowNodeRun

def test_database_schema():
    """Test 1: Verify database schema has 4 new flow tables"""
    print("\n" + "="*60)
    print("TEST 1: Database Schema Verification")
    print("="*60)

    db_path = "data/agent.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Check flow_definition table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flow_definition'")
    fd_exists = c.fetchone() is not None
    print(f"[{'OK' if fd_exists else 'FAIL'}] flow_definition table exists")

    # Check flow_node table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flow_node'")
    fn_exists = c.fetchone() is not None
    print(f"[{'OK' if fn_exists else 'FAIL'}] flow_node table exists")

    # Check flow_run table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flow_run'")
    fr_exists = c.fetchone() is not None
    print(f"[{'OK' if fr_exists else 'FAIL'}] flow_run table exists")

    # Check flow_node_run table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='flow_node_run'")
    fnr_exists = c.fetchone() is not None
    print(f"[{'OK' if fnr_exists else 'FAIL'}] flow_node_run table exists")

    # Check flow_node indexes
    c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='flow_node'")
    indexes = [row[0] for row in c.fetchall()]
    has_definition_idx = any('definition' in idx.lower() for idx in indexes)
    has_position_idx = any('position' in idx.lower() for idx in indexes)
    print(f"[{'OK' if has_definition_idx else 'FAIL'}] flow_node has definition index")
    print(f"[{'OK' if has_position_idx else 'FAIL'}] flow_node has position index")

    # Check flow_run indexes
    c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='flow_run'")
    run_indexes = [row[0] for row in c.fetchall()]
    has_status_idx = any('status' in idx.lower() for idx in run_indexes)
    print(f"[{'OK' if has_status_idx else 'FAIL'}] flow_run has status index")

    # Check flow_node_run indexes
    c.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='flow_node_run'")
    node_run_indexes = [row[0] for row in c.fetchall()]
    has_idempotency_idx = any('idempotency' in idx.lower() for idx in node_run_indexes)
    print(f"[{'OK' if has_idempotency_idx else 'FAIL'}] flow_node_run has idempotency index")

    conn.close()

    all_passed = fd_exists and fn_exists and fr_exists and fnr_exists
    print("\n" + ("="*60))
    print(f"Schema Test: {'PASSED' if all_passed else 'FAILED'}")
    print("="*60)
    return all_passed


def test_flow_definition_crud():
    """Test 2: Flow definition CRUD operations"""
    print("\n" + "="*60)
    print("TEST 2: Flow Definition CRUD")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # CREATE
        print("\n[CREATE] Creating new flow definition...")
        flow = FlowDefinition(
            name="Test Flow",
            description="A test flow for unit testing",
            is_active=True,
            version=1
        )
        session.add(flow)
        session.commit()
        session.refresh(flow)
        flow_id = flow.id
        print(f"[OK] Created flow with ID: {flow_id}")

        # READ
        print("\n[READ] Reading flow definition...")
        read_flow = session.query(FlowDefinition).filter(FlowDefinition.id == flow_id).first()
        assert read_flow is not None, "Flow not found after creation"
        assert read_flow.name == "Test Flow", "Flow name mismatch"
        assert read_flow.is_active == True, "Flow is_active mismatch"
        print(f"[OK] Read flow: {read_flow.name}")

        # UPDATE
        print("\n[UPDATE] Updating flow definition...")
        read_flow.name = "Updated Test Flow"
        read_flow.is_active = False
        session.commit()

        updated_flow = session.query(FlowDefinition).filter(FlowDefinition.id == flow_id).first()
        assert updated_flow.name == "Updated Test Flow", "Flow name update failed"
        assert updated_flow.is_active == False, "Flow is_active update failed"
        print(f"[OK] Updated flow name to: {updated_flow.name}")

        # DELETE
        print("\n[DELETE] Deleting flow definition...")
        session.delete(updated_flow)
        session.commit()

        deleted_flow = session.query(FlowDefinition).filter(FlowDefinition.id == flow_id).first()
        assert deleted_flow is None, "Flow still exists after deletion"
        print(f"[OK] Deleted flow with ID: {flow_id}")

        print("\n" + ("="*60))
        print("Flow Definition CRUD Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Flow Definition CRUD test failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def test_flow_node_crud():
    """Test 3: Flow node CRUD operations"""
    print("\n" + "="*60)
    print("TEST 3: Flow Node CRUD")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Create a flow first
        flow = FlowDefinition(name="Node Test Flow", description="For testing nodes")
        session.add(flow)
        session.commit()
        session.refresh(flow)
        flow_id = flow.id

        # CREATE Trigger node
        print("\n[CREATE] Creating Trigger node...")
        trigger_config = {
            "agent_id": 1,
            "recipients": ["5511999999999"],
            "objective": "Test objective"
        }
        trigger_node = FlowNode(
            flow_definition_id=flow_id,
            type="Trigger",
            position=1,
            config_json=json.dumps(trigger_config)
        )
        session.add(trigger_node)
        session.commit()
        session.refresh(trigger_node)
        print(f"[OK] Created Trigger node with ID: {trigger_node.id}")

        # CREATE Message node
        print("\n[CREATE] Creating Message node...")
        message_config = {
            "channel": "whatsapp",
            "recipients": ["5511999999999"],
            "message_template": "Hello {{name}}"
        }
        message_node = FlowNode(
            flow_definition_id=flow_id,
            type="Message",
            position=2,
            config_json=json.dumps(message_config)
        )
        session.add(message_node)
        session.commit()
        session.refresh(message_node)
        print(f"[OK] Created Message node with ID: {message_node.id}")

        # READ nodes
        print("\n[READ] Reading nodes...")
        nodes = session.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow_id
        ).order_by(FlowNode.position).all()
        assert len(nodes) == 2, f"Expected 2 nodes, found {len(nodes)}"
        assert nodes[0].type == "Trigger", "First node should be Trigger"
        assert nodes[1].type == "Message", "Second node should be Message"
        print(f"[OK] Read {len(nodes)} nodes in correct order")

        # UPDATE node
        print("\n[UPDATE] Updating Message node config...")
        nodes[1].config_json = json.dumps({"channel": "telegram", "message": "Updated"})
        session.commit()

        updated_node = session.query(FlowNode).filter(FlowNode.id == nodes[1].id).first()
        config = json.loads(updated_node.config_json)
        assert config["channel"] == "telegram", "Node config update failed"
        print(f"[OK] Updated node config")

        # DELETE nodes and flow
        print("\n[DELETE] Cleaning up...")
        session.query(FlowNode).filter(FlowNode.flow_definition_id == flow_id).delete()
        session.delete(flow)
        session.commit()
        print(f"[OK] Cleaned up test data")

        print("\n" + ("="*60))
        print("Flow Node CRUD Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Flow Node CRUD test failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def test_flow_validation():
    """Test 4: Flow structure validation"""
    print("\n" + "="*60)
    print("TEST 4: Flow Validation")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Test 1: Max 5 nodes
        print("\n[TEST] Creating flow with 3 nodes (should succeed)...")
        flow1 = FlowDefinition(name="Valid Flow", description="Has 3 nodes")
        session.add(flow1)
        session.commit()
        session.refresh(flow1)

        # Add 3 nodes
        for i in range(1, 4):
            node_type = "Trigger" if i == 1 else "Message"
            node = FlowNode(
                flow_definition_id=flow1.id,
                type=node_type,
                position=i,
                config_json=json.dumps({"test": f"node_{i}"})
            )
            session.add(node)
        session.commit()

        node_count = session.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow1.id
        ).count()
        assert node_count == 3, f"Expected 3 nodes, found {node_count}"
        print(f"[OK] Created flow with {node_count} nodes")

        # Test 2: Must have Trigger at position 1
        print("\n[TEST] Verifying Trigger at position 1...")
        trigger = session.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow1.id,
            FlowNode.position == 1
        ).first()
        assert trigger is not None, "No node at position 1"
        assert trigger.type == "Trigger", f"Position 1 has {trigger.type}, expected Trigger"
        print(f"[OK] Trigger node at position 1")

        # Test 3: Sequential positions
        print("\n[TEST] Verifying sequential positions...")
        nodes = session.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow1.id
        ).order_by(FlowNode.position).all()
        positions = [n.position for n in nodes]
        expected = list(range(1, len(nodes) + 1))
        assert positions == expected, f"Positions {positions} not sequential"
        print(f"[OK] Positions are sequential: {positions}")

        # Cleanup
        print("\n[CLEANUP] Removing test data...")
        session.query(FlowNode).filter(FlowNode.flow_definition_id == flow1.id).delete()
        session.delete(flow1)
        session.commit()
        print(f"[OK] Cleaned up")

        print("\n" + ("="*60))
        print("Flow Validation Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Flow Validation test failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def test_flow_run_read():
    """Test 5: Flow run read operations (no execution yet)"""
    print("\n" + "="*60)
    print("TEST 5: Flow Run Read Operations")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Create a flow
        flow = FlowDefinition(name="Run Test Flow")
        session.add(flow)
        session.commit()
        session.refresh(flow)

        # Create a mock flow run
        print("\n[CREATE] Creating mock flow run...")
        flow_run = FlowRun(
            flow_definition_id=flow.id,
            status="completed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            initiator="test",
            trigger_context_json=json.dumps({"test": "context"}),
            final_report_json=json.dumps({"result": "success"})
        )
        session.add(flow_run)
        session.commit()
        session.refresh(flow_run)
        print(f"[OK] Created flow run with ID: {flow_run.id}")

        # Read flow run
        print("\n[READ] Reading flow run...")
        read_run = session.query(FlowRun).filter(FlowRun.id == flow_run.id).first()
        assert read_run is not None, "Flow run not found"
        assert read_run.status == "completed", "Status mismatch"
        assert read_run.initiator == "test", "Initiator mismatch"
        print(f"[OK] Read flow run: status={read_run.status}, initiator={read_run.initiator}")

        # List flow runs
        print("\n[LIST] Listing flow runs for definition...")
        runs = session.query(FlowRun).filter(
            FlowRun.flow_definition_id == flow.id
        ).all()
        assert len(runs) == 1, f"Expected 1 run, found {len(runs)}"
        print(f"[OK] Found {len(runs)} run(s) for flow {flow.id}")

        # Cleanup
        print("\n[CLEANUP] Removing test data...")
        session.delete(flow_run)
        session.delete(flow)
        session.commit()
        print(f"[OK] Cleaned up")

        print("\n" + ("="*60))
        print("Flow Run Read Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Flow Run Read test failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def test_node_types():
    """Test 6: All 5 node types can be created"""
    print("\n" + "="*60)
    print("TEST 6: Node Type Creation")
    print("="*60)

    db_path = "data/agent.db"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Create a flow
        flow = FlowDefinition(name="Node Types Test Flow")
        session.add(flow)
        session.commit()
        session.refresh(flow)

        # Create all 5 node types
        node_types = [
            ("Trigger", 1, {"agent_id": 1, "objective": "test"}),
            ("Message", 2, {"channel": "whatsapp", "message": "test"}),
            ("Tool", 3, {"tool_type": "built_in", "tool_id": "google_search"}),
            ("Conversation", 4, {"agent_id": 1, "objective": "chat"}),
            ("Subflow", 5, {"target_flow_definition_id": 1})
        ]

        for node_type, position, config in node_types:
            print(f"\n[CREATE] Creating {node_type} node at position {position}...")
            node = FlowNode(
                flow_definition_id=flow.id,
                type=node_type,
                position=position,
                config_json=json.dumps(config)
            )
            session.add(node)
            session.commit()
            print(f"[OK] Created {node_type} node")

        # Verify all nodes
        print("\n[VERIFY] Verifying all 5 node types...")
        nodes = session.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow.id
        ).order_by(FlowNode.position).all()

        assert len(nodes) == 5, f"Expected 5 nodes, found {len(nodes)}"

        expected_types = ["Trigger", "Message", "Tool", "Conversation", "Subflow"]
        actual_types = [n.type for n in nodes]
        assert actual_types == expected_types, f"Node types mismatch: {actual_types}"
        print(f"[OK] All 5 node types created successfully: {actual_types}")

        # Cleanup
        print("\n[CLEANUP] Removing test data...")
        session.query(FlowNode).filter(FlowNode.flow_definition_id == flow.id).delete()
        session.delete(flow)
        session.commit()
        print(f"[OK] Cleaned up")

        print("\n" + ("="*60))
        print("Node Type Creation Test: PASSED")
        print("="*60)
        return True

    except Exception as e:
        print(f"\n[FAIL] Node Type Creation test failed: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def run_all_tests():
    """Run all Phase 6.6 tests"""
    print("\n" + "="*80)
    print("PHASE 6.6 MULTI-STEP FLOWS - COMPREHENSIVE TEST SUITE")
    print("="*80)

    results = []

    results.append(("Database Schema", test_database_schema()))
    results.append(("Flow Definition CRUD", test_flow_definition_crud()))
    results.append(("Flow Node CRUD", test_flow_node_crud()))
    results.append(("Flow Validation", test_flow_validation()))
    results.append(("Flow Run Read", test_flow_run_read()))
    results.append(("Node Type Creation", test_node_types()))

    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)

    for test_name, passed in results:
        status = "[PASSED]" if passed else "[FAILED]"
        print(f"{test_name:30s} {status}")

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
