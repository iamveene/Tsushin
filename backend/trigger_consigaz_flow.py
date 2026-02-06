#!/usr/bin/env python3
"""
Trigger Consigaz flow execution for testing
"""

import sys
import asyncio
sys.path.append('/app')

from db import get_db
from flows.flow_engine import FlowEngine

async def trigger_flow():
    """Execute the Consigaz flow (ID 66)"""
    db = next(get_db())

    try:
        print("=" * 80)
        print("TRIGGERING CONSIGAZ FLOW (ID 66)")
        print("=" * 80)

        engine = FlowEngine(db)

        print("\n📋 Executing flow...")
        flow_run = await engine.run_flow(
            flow_definition_id=66,
            trigger_context={},
            initiator="manual_test"
        )

        print(f"\n✅ Flow execution initiated!")
        print(f"   Flow Run ID: {flow_run.id}")
        print(f"   Status: {flow_run.status}")

        if flow_run.status == "completed":
            print("\n🎉 Flow completed successfully!")
        elif flow_run.status == "failed":
            print(f"\n❌ Flow failed: {flow_run.error_text}")
        else:
            print(f"\n⏳ Flow status: {flow_run.status}")

        # Check for conversation thread
        from models import ConversationThread
        thread = db.query(ConversationThread).filter(
            ConversationThread.agent_id == 17
        ).order_by(ConversationThread.started_at.desc()).first()

        if thread:
            print(f"\n💬 Conversation Thread Created:")
            print(f"   Thread ID: {thread.id}")
            print(f"   Status: {thread.status}")
            print(f"   Recipient: {thread.recipient}")
            print(f"   Current Turn: {thread.current_turn}/{thread.max_turns}")
            print(f"   Objective: {thread.objective[:100]}...")

        return flow_run

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(trigger_flow())
