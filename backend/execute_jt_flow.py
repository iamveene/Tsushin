"""
Script to execute the JT Bot shipment status flow.

Usage:
    python execute_jt_flow.py <flow_id>
"""
import sys
import asyncio
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, '/app')

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import FlowDefinition, FlowRun, FlowNodeRun, ConversationThread
from flows.flow_engine import FlowEngine
import os

# Database setup
db_url = os.environ.get('DATABASE_URL', 'sqlite:////app/data/agent.db')
engine = create_engine(db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


async def execute_flow(flow_id: int):
    """Execute the flow and monitor progress."""
    db = SessionLocal()

    try:
        # Check if flow exists
        flow = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id).first()
        if not flow:
            print(f"❌ Flow {flow_id} not found")
            return

        print(f"🚀 Executing Flow: {flow.name} (ID={flow.id})")
        print(f"   Description: {flow.description}")
        print(f"   Steps: {len(flow.steps)}")
        print()

        # Create flow engine
        engine_instance = FlowEngine(db)

        # Execute flow
        print("⏳ Starting flow execution...")
        start_time = datetime.utcnow()

        flow_run = await engine_instance.run_flow(
            flow_definition_id=flow_id,
            trigger_context={"timestamp": start_time.isoformat()},
            initiator="script",
            trigger_type="immediate"
        )

        end_time = datetime.utcnow()
        elapsed = int((end_time - start_time).total_seconds())

        print(f"\n✅ Flow execution completed!")
        print(f"   Flow Run ID: {flow_run.id}")
        print(f"   Status: {flow_run.status}")
        print(f"   Execution Time: {elapsed}s")
        print(f"   Completed Steps: {flow_run.completed_steps}/{flow_run.total_steps}")

        if flow_run.status == "failed":
            print(f"   ❌ Error: {flow_run.error_text}")

        # Display step details
        print(f"\n📊 Step Execution Details:")
        step_runs = db.query(FlowNodeRun).filter(
            FlowNodeRun.flow_run_id == flow_run.id
        ).order_by(FlowNodeRun.id).all()

        for step_run in step_runs:
            step = db.query(FlowDefinition).join(FlowDefinition.steps).filter(
                FlowDefinition.id == flow_id
            ).first()

            print(f"\n   Step {step_run.id}: {step_run.status}")

            if step_run.output_json:
                import json
                output = json.loads(step_run.output_json)

                # Display relevant output fields
                if "thread_id" in output:
                    print(f"      Thread ID: {output['thread_id']}")
                if "conversation_status" in output:
                    print(f"      Conversation Status: {output['conversation_status']}")
                if "current_turn" in output:
                    print(f"      Turns: {output['current_turn']}")
                if "summary" in output:
                    print(f"      Summary: {output['summary'][:200]}...")
                if "wait_time_seconds" in output:
                    print(f"      Wait Time: {output['wait_time_seconds']}s")

        # Check for conversation thread
        print(f"\n💬 Conversation Thread Details:")
        threads = db.query(ConversationThread).join(FlowNodeRun).filter(
            FlowNodeRun.flow_run_id == flow_run.id
        ).all()

        if threads:
            for thread in threads:
                print(f"   Thread ID: {thread.id}")
                print(f"   Status: {thread.status}")
                print(f"   Turns: {thread.current_turn}/{thread.max_turns}")
                print(f"   Goal Achieved: {thread.goal_achieved}")
                if thread.goal_summary:
                    print(f"   Summary: {thread.goal_summary}")

                # Display conversation history
                print(f"\n   📝 Conversation Transcript:")
                for i, msg in enumerate(thread.conversation_history, 1):
                    role = "Agent" if msg["role"] == "agent" else "User"
                    content = msg["content"][:100]
                    print(f"      {i}. [{role}] {content}...")
        else:
            print("   No conversation threads found")

        print(f"\n🎯 Flow execution completed successfully!")

    except Exception as e:
        print(f"❌ Error executing flow: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python execute_jt_flow.py <flow_id>")
        sys.exit(1)

    flow_id = int(sys.argv[1])
    asyncio.run(execute_flow(flow_id))
