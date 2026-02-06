import json
import sys
import types

import pytest

from flows.flow_engine import SummarizationStepHandler
from mcp_sender import MCPSender
from models import ConversationThread, FlowDefinition, FlowNode, FlowRun, FlowNodeRun


@pytest.mark.asyncio
async def test_summary_requires_completed_thread(test_db):
    flow = FlowDefinition(name="Summary Flow")
    test_db.add(flow)
    test_db.commit()
    test_db.refresh(flow)

    config = {
        "thread_id": 1,
        "wait_for_completion": True,
        "max_wait_seconds": 0
    }
    step = FlowNode(
        flow_definition_id=flow.id,
        type="summarization",
        position=1,
        config_json=json.dumps(config)
    )
    test_db.add(step)
    test_db.commit()
    test_db.refresh(step)

    flow_run = FlowRun(flow_definition_id=flow.id, status="running")
    test_db.add(flow_run)
    test_db.commit()
    test_db.refresh(flow_run)

    step_run = FlowNodeRun(flow_run_id=flow_run.id, flow_node_id=step.id, status="running")
    test_db.add(step_run)
    test_db.commit()
    test_db.refresh(step_run)

    thread = ConversationThread(
        id=1,
        status="active",
        current_turn=1,
        max_turns=5,
        recipient="5511990000001",
        agent_id=17,
        conversation_history=[]
    )
    test_db.add(thread)
    test_db.commit()

    handler = SummarizationStepHandler(test_db, MCPSender())
    result = await handler.execute(step, {}, flow_run, step_run)

    assert result["status"] == "failed"
    assert result["summary"] == ""
    assert "not completed" in result["error"]


@pytest.mark.asyncio
async def test_summary_generates_after_completion(test_db, monkeypatch):
    fake_genai = types.SimpleNamespace()

    class FakeResponse:
        text = "Resumo final"

    class FakeModel:
        def __init__(self, model):
            self.model = model

        def generate_content(self, prompt):
            return FakeResponse()

    fake_genai.configure = lambda api_key: None
    fake_genai.GenerativeModel = FakeModel
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

    flow = FlowDefinition(name="Summary Flow Completed")
    test_db.add(flow)
    test_db.commit()
    test_db.refresh(flow)

    config = {
        "thread_id": 2,
        "wait_for_completion": True
    }
    step = FlowNode(
        flow_definition_id=flow.id,
        type="summarization",
        position=1,
        config_json=json.dumps(config)
    )
    test_db.add(step)
    test_db.commit()
    test_db.refresh(step)

    flow_run = FlowRun(flow_definition_id=flow.id, status="running")
    test_db.add(flow_run)
    test_db.commit()
    test_db.refresh(flow_run)

    step_run = FlowNodeRun(flow_run_id=flow_run.id, flow_node_id=step.id, status="running")
    test_db.add(step_run)
    test_db.commit()
    test_db.refresh(step_run)

    thread = ConversationThread(
        id=2,
        status="completed",
        current_turn=3,
        max_turns=5,
        recipient="5511990000001",
        agent_id=17,
        conversation_history=[
            {"role": "agent", "content": "Oi", "timestamp": "2026-01-19T19:00:00Z"},
            {"role": "user", "content": "Preciso do boleto", "timestamp": "2026-01-19T19:00:10Z"}
        ]
    )
    test_db.add(thread)
    test_db.commit()

    handler = SummarizationStepHandler(test_db, MCPSender())
    result = await handler.execute(step, {}, flow_run, step_run)

    assert result["status"] == "completed"
    assert result["summary"] == "Resumo final"
