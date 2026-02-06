"""
Phase 13.1: Step Output Injection - Integration Tests

Tests for step output injection in multi-step workflow execution.
Verifies that step outputs are correctly passed to subsequent steps
via the template system.
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime

from flows.flow_engine import FlowEngine, FlowStepHandler, NotificationStepHandler
from flows.template_parser import TemplateParser
from models import FlowDefinition, FlowNode, FlowRun, FlowNodeRun


class TestFlowEngineStepContext:
    """Test FlowEngine's step context building."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        return db

    @pytest.fixture
    def flow_engine(self, mock_db):
        """Create FlowEngine instance."""
        with patch('flows.flow_engine.MCPSender'):
            engine = FlowEngine(mock_db)
        return engine

    def test_build_step_context_empty(self, flow_engine):
        """Test building context with no completed steps."""
        flow_run = MagicMock()
        flow_run.id = 1
        flow_run.flow_definition_id = 1
        flow_run.status = "running"
        flow_run.initiator = "api"

        context = flow_engine._build_step_context(
            flow_run=flow_run,
            completed_step_runs=[],
            trigger_context={"target": "192.168.1.0/24"}
        )

        assert context["flow"]["id"] == 1
        assert context["target"] == "192.168.1.0/24"
        assert context["previous_step"] is None
        assert context["steps"] == {}

    def test_build_step_context_single_step(self, flow_engine, mock_db):
        """Test building context with one completed step."""
        # Setup mock step definition
        step = MagicMock()
        step.position = 1
        step.name = "network_scan"
        step.type = "tool"
        step.config_json = '{"output_alias": "scan_results"}'
        mock_db.query.return_value.filter.return_value.first.return_value = step

        # Setup mock step run
        step_run = MagicMock()
        step_run.flow_node_id = 1
        step_run.status = "completed"
        step_run.error_text = None
        step_run.execution_time_ms = 150
        step_run.retry_count = 0
        step_run.output_json = json.dumps({
            "raw_output": "Port 22: Open\nPort 80: Open",
            "success": True,
            "summary": "Scan completed"
        })

        flow_run = MagicMock()
        flow_run.id = 1

        context = flow_engine._build_step_context(
            flow_run=flow_run,
            completed_step_runs=[step_run],
            trigger_context=None
        )

        # Check step_1 reference
        assert "step_1" in context
        assert context["step_1"]["status"] == "completed"
        assert context["step_1"]["success"] is True
        assert context["step_1"]["raw_output"] == "Port 22: Open\nPort 80: Open"

        # Check name reference
        assert "network_scan" in context
        assert context["network_scan"]["success"] is True

        # Check output_alias reference
        assert "scan_results" in context
        assert context["scan_results"]["success"] is True

        # Check previous_step
        assert context["previous_step"]["status"] == "completed"

    def test_build_step_context_multiple_steps(self, flow_engine, mock_db):
        """Test building context with multiple completed steps."""
        # Setup mock step definitions
        steps = {
            1: MagicMock(position=1, name="step_a", type="tool", config_json='{}'),
            2: MagicMock(position=2, name="step_b", type="tool", config_json='{}')
        }

        def get_step(step_id):
            mock_query = MagicMock()
            mock_query.filter.return_value.first.return_value = steps.get(step_id)
            return mock_query

        mock_db.query.return_value = MagicMock()
        mock_db.query.return_value.filter.side_effect = lambda cond: get_step(
            cond.right.value if hasattr(cond, 'right') else 1
        )

        # Setup mock step runs
        step_runs = [
            MagicMock(
                flow_node_id=1,
                status="completed",
                error_text=None,
                execution_time_ms=100,
                retry_count=0,
                output_json=json.dumps({"result": "A"})
            ),
            MagicMock(
                flow_node_id=2,
                status="completed",
                error_text=None,
                execution_time_ms=200,
                retry_count=0,
                output_json=json.dumps({"result": "B"})
            )
        ]

        # Override the filter to return correct step
        def side_effect(*args, **kwargs):
            mock = MagicMock()
            mock.first.return_value = steps[1]  # Default to step 1
            return mock

        mock_db.query.return_value.filter.side_effect = side_effect

        flow_run = MagicMock()
        flow_run.id = 1

        # Build context - need to simulate step lookups
        with patch.object(mock_db, 'query') as mock_query:
            def query_side_effect(model):
                mock_result = MagicMock()
                def filter_side_effect(cond):
                    # Extract step_id from condition
                    step_id = 1
                    if hasattr(cond, 'right') and hasattr(cond.right, 'value'):
                        step_id = cond.right.value
                    mock_filter = MagicMock()
                    mock_filter.first.return_value = steps.get(step_id, steps[1])
                    return mock_filter
                mock_result.filter.side_effect = filter_side_effect
                return mock_result

            mock_query.side_effect = query_side_effect

            context = flow_engine._build_step_context(
                flow_run=flow_run,
                completed_step_runs=step_runs,
                trigger_context=None
            )

        # The previous_step should be the last one
        assert context["previous_step"] is not None


class TestStepHandlerTemplateResolution:
    """Test template resolution in step handlers."""

    def test_replace_variables_basic(self):
        """Test basic variable replacement in step handler."""
        with patch('flows.flow_engine.MCPSender'):
            handler = FlowStepHandler(MagicMock(), MagicMock())

        context = {"name": "John", "status": "active"}
        result = handler._replace_variables("Hello {{name}}", context)
        assert result == "Hello John"

    def test_replace_variables_step_reference(self):
        """Test step reference replacement."""
        with patch('flows.flow_engine.MCPSender'):
            handler = FlowStepHandler(MagicMock(), MagicMock())

        context = {
            "step_1": {
                "status": "completed",
                "raw_output": "Scan results here"
            }
        }

        result = handler._replace_variables("Step status: {{step_1.status}}", context)
        assert result == "Step status: completed"

    def test_replace_variables_conditional(self):
        """Test conditional in step handler."""
        with patch('flows.flow_engine.MCPSender'):
            handler = FlowStepHandler(MagicMock(), MagicMock())

        context = {"step_1": {"success": True}}
        result = handler._replace_variables(
            "{{#if step_1.success}}OK{{else}}FAIL{{/if}}",
            context
        )
        assert result == "OK"

    def test_replace_variables_helper(self):
        """Test helper function in step handler."""
        with patch('flows.flow_engine.MCPSender'):
            handler = FlowStepHandler(MagicMock(), MagicMock())

        context = {"output": "This is a very long output that needs truncation"}
        result = handler._replace_variables("{{truncate output 20}}", context)
        assert len(result) <= 20 + 3  # +3 for "..."


class TestNotificationStepWithInjection:
    """Test NotificationStepHandler with step output injection."""

    @pytest.fixture
    def notification_handler(self):
        """Create NotificationStepHandler instance."""
        with patch('flows.flow_engine.MCPSender') as mock_sender:
            mock_sender_instance = MagicMock()
            mock_sender.return_value = mock_sender_instance
            handler = NotificationStepHandler(MagicMock(), mock_sender_instance)
            handler.mcp_sender.send_message = AsyncMock(return_value=True)
            handler._resolve_mcp_url = MagicMock(return_value="http://localhost:8080/api")
            handler._check_mcp_connection = MagicMock(return_value=True)
        return handler

    @pytest.mark.asyncio
    async def test_notification_with_step_reference(self, notification_handler):
        """Test notification using previous step output."""
        step = MagicMock()
        step.config_json = json.dumps({
            "recipient": "5527999999999",
            "message_template": "Scan status: {{step_1.status}}\nResults: {{step_1.summary}}"
        })

        input_data = {
            "step_1": {
                "status": "completed",
                "summary": "Found 3 open ports",
                "success": True
            }
        }

        flow_run = MagicMock()
        step_run = MagicMock()

        result = await notification_handler.execute(step, input_data, flow_run, step_run)

        assert "Scan status: completed" in result.get("message_sent", "")
        assert "Found 3 open ports" in result.get("message_sent", "")

    @pytest.mark.asyncio
    async def test_notification_with_conditional(self, notification_handler):
        """Test notification with conditional based on step success."""
        step = MagicMock()
        step.config_json = json.dumps({
            "recipient": "5527999999999",
            "message_template": "Task {{#if previous_step.success}}completed successfully ✅{{else}}failed ❌{{/if}}"
        })

        input_data = {
            "previous_step": {
                "status": "completed",
                "success": True
            }
        }

        flow_run = MagicMock()
        step_run = MagicMock()

        result = await notification_handler.execute(step, input_data, flow_run, step_run)

        assert "completed successfully ✅" in result.get("message_sent", "")

    @pytest.mark.asyncio
    async def test_notification_with_truncate(self, notification_handler):
        """Test notification with truncated output."""
        step = MagicMock()
        step.config_json = json.dumps({
            "recipient": "5527999999999",
            "message_template": "Output: {{truncate step_1.raw_output 50}}"
        })

        long_output = "A" * 100  # 100 characters
        input_data = {
            "step_1": {
                "raw_output": long_output
            }
        }

        flow_run = MagicMock()
        step_run = MagicMock()

        result = await notification_handler.execute(step, input_data, flow_run, step_run)

        message = result.get("message_sent", "")
        # Output: prefix + truncated content + ...
        assert len(message) < len("Output: ") + 100


class TestEndToEndScenarios:
    """End-to-end test scenarios."""

    def test_scan_and_notify_flow_template(self):
        """Test a typical scan->notify flow template."""
        # Simulate completed tool step
        tool_output = {
            "tool_used": "nmap",
            "status": "completed",
            "success": True,
            "raw_output": """
Starting Nmap scan...
Host: 192.168.1.1
  Port 22/tcp: open (SSH)
  Port 80/tcp: open (HTTP)
  Port 443/tcp: open (HTTPS)
Scan complete.
            """.strip(),
            "summary": "3 open ports found",
            "parameters": {
                "target": "192.168.1.0/24"
            }
        }

        # Build context like FlowEngine would
        context = {
            "flow": {"id": 1},
            "step_1": tool_output,
            "network_scan": tool_output,
            "previous_step": tool_output,
            **tool_output  # Root-level for backward compat
        }

        # Notification template
        template = """🔍 Network Scan Complete

Target: {{step_1.parameters.target}}
Status: {{#if step_1.success}}✅ Success{{else}}❌ Failed{{/if}}
Summary: {{step_1.summary}}

Results:
{{truncate step_1.raw_output 200}}"""

        parser = TemplateParser(context)
        result = parser.render(template)

        assert "192.168.1.0/24" in result
        assert "✅ Success" in result
        assert "3 open ports found" in result
        assert "Port 22/tcp: open" in result

    def test_multi_step_with_error_handling(self):
        """Test multi-step flow with error in middle step."""
        context = {
            "step_1": {
                "status": "completed",
                "success": True,
                "output": "Step 1 OK"
            },
            "step_2": {
                "status": "failed",
                "success": False,
                "error": "Connection refused",
                "output": None
            },
            "previous_step": {
                "status": "failed",
                "success": False,
                "error": "Connection refused"
            }
        }

        template = """Flow Execution Report

Step 1: {{#if step_1.success}}✅{{else}}❌{{/if}} - {{step_1.output}}
Step 2: {{#if step_2.success}}✅{{else}}❌{{/if}} - {{default step_2.error "No error"}}

Overall: {{#if previous_step.success}}All steps completed{{else}}Flow had errors{{/if}}"""

        parser = TemplateParser(context)
        result = parser.render(template)

        assert "Step 1: ✅" in result
        assert "Step 2: ❌" in result
        assert "Connection refused" in result
        assert "Flow had errors" in result

    def test_flow_with_output_alias(self):
        """Test flow where step uses output_alias."""
        # Simulate context built with output_alias
        tool_output = {
            "status": "completed",
            "data": {"users": ["alice", "bob", "charlie"]}
        }

        context = {
            "step_1": tool_output,
            "fetch_users": tool_output,  # By name
            "user_list": tool_output,     # By output_alias
            "previous_step": tool_output
        }

        template = "Users found: {{join user_list.data.users ', '}}"

        parser = TemplateParser(context)
        result = parser.render(template)

        assert "alice, bob, charlie" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
