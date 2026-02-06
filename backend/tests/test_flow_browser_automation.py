"""
Unit tests for Browser Automation Step Handler in Flow Engine (Phase 14.5)

Tests cover:
- BrowserAutomationStepHandler execution
- Template variable resolution
- Screenshot path propagation
- Error handling
- Token tracking in flows

Run: pytest backend/tests/test_flow_browser_automation.py -v
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestBrowserAutomationStepHandlerInstantiation:
    """Tests for handler instantiation."""

    def test_handler_in_flow_engine_handlers(self):
        """Test that browser_automation handler is registered."""
        from flows.flow_engine import FlowEngine

        # Create engine with mocked db
        mock_db = MagicMock()
        engine = FlowEngine(db=mock_db)

        assert "browser_automation" in engine.handlers
        assert "BrowserAutomation" in engine.handlers  # Legacy casing

    def test_handler_has_required_attributes(self):
        """Test handler has required attributes."""
        from flows.flow_engine import BrowserAutomationStepHandler

        mock_db = MagicMock()
        mock_sender = MagicMock()
        mock_tracker = MagicMock()

        handler = BrowserAutomationStepHandler(mock_db, mock_sender, mock_tracker)

        assert handler.db == mock_db
        assert handler.mcp_sender == mock_sender
        assert handler.token_tracker == mock_tracker


class TestBrowserAutomationStepHandlerExecution:
    """Tests for handler execution."""

    @pytest.fixture
    def handler(self):
        """Create handler instance for testing."""
        from flows.flow_engine import BrowserAutomationStepHandler

        mock_db = MagicMock()
        mock_sender = MagicMock()
        mock_tracker = MagicMock()

        return BrowserAutomationStepHandler(mock_db, mock_sender, mock_tracker)

    @pytest.fixture
    def mock_step(self):
        """Create mock FlowNode step."""
        step = MagicMock()
        step.id = 1
        step.config_json = json.dumps({
            "prompt": "take a screenshot of example.com"
        })
        return step

    @pytest.fixture
    def mock_flow_run(self):
        """Create mock FlowRun."""
        flow_run = MagicMock()
        flow_run.id = 1
        flow_run.tenant_id = "test_tenant"
        return flow_run

    @pytest.fixture
    def mock_step_run(self):
        """Create mock FlowNodeRun."""
        step_run = MagicMock()
        step_run.id = 1
        return step_run

    @pytest.mark.asyncio
    async def test_execute_with_prompt(self, handler, mock_step, mock_flow_run, mock_step_run):
        """Test execution with natural language prompt."""
        input_data = {}

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Screenshot captured successfully",
                metadata={
                    "screenshot_paths": ["/tmp/screenshot.png"],
                    "actions_executed": 2,
                    "actions_succeeded": 2,
                    "provider": "playwright",
                    "mode": "container"
                }
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step, input_data, mock_flow_run, mock_step_run)

            assert result["status"] == "completed"
            assert "screenshot_paths" in result
            assert result["actions_executed"] == 2
            MockSkill.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_with_url(self, handler, mock_flow_run, mock_step_run):
        """Test execution with direct URL."""
        mock_step = MagicMock()
        mock_step.id = 1
        mock_step.config_json = json.dumps({
            "url": "https://example.com"
        })

        input_data = {}

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Navigated to example.com",
                metadata={
                    "screenshot_paths": [],
                    "actions_executed": 1,
                    "provider": "playwright",
                    "mode": "container"
                }
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step, input_data, mock_flow_run, mock_step_run)

            assert result["status"] == "completed"
            # Verify skill was called with "navigate to https://example.com"
            call_args = mock_skill_instance.process.call_args
            message = call_args[0][0]
            assert "navigate to" in message.body.lower() or "example.com" in message.body.lower()

    @pytest.mark.asyncio
    async def test_execute_with_template_variables(self, handler, mock_flow_run, mock_step_run):
        """Test template variable resolution in prompt."""
        mock_step = MagicMock()
        mock_step.id = 1
        mock_step.config_json = json.dumps({
            "prompt": "take a screenshot of {{target_url}}"
        })

        input_data = {"target_url": "https://github.com"}

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Screenshot of github.com",
                metadata={
                    "screenshot_paths": ["/tmp/github.png"],
                    "actions_executed": 2
                }
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step, input_data, mock_flow_run, mock_step_run)

            # Verify template was resolved
            call_args = mock_skill_instance.process.call_args
            message = call_args[0][0]
            assert "github.com" in message.body

    @pytest.mark.asyncio
    async def test_execute_missing_config(self, handler, mock_flow_run, mock_step_run):
        """Test execution with missing prompt and URL."""
        mock_step = MagicMock()
        mock_step.id = 1
        mock_step.config_json = json.dumps({})  # Empty config

        input_data = {}

        result = await handler.execute(mock_step, input_data, mock_flow_run, mock_step_run)

        assert result["status"] == "failed"
        assert "error" in result
        assert "missing" in result["error"].lower() or "required" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_skill_failure(self, handler, mock_step, mock_flow_run, mock_step_run):
        """Test handling of skill failure."""
        input_data = {}

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=False,
                output="Navigation failed: timeout",
                metadata={
                    "error": "timeout",
                    "actions_executed": 0
                }
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step, input_data, mock_flow_run, mock_step_run)

            assert result["status"] == "failed"
            assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_exception_handling(self, handler, mock_step, mock_flow_run, mock_step_run):
        """Test handling of unexpected exceptions."""
        input_data = {}

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            MockSkill.side_effect = Exception("Unexpected error")

            result = await handler.execute(mock_step, input_data, mock_flow_run, mock_step_run)

            assert result["status"] == "failed"
            assert "Unexpected error" in result["error"]


class TestBrowserAutomationStepHandlerConfig:
    """Tests for configuration handling."""

    @pytest.fixture
    def handler(self):
        """Create handler instance for testing."""
        from flows.flow_engine import BrowserAutomationStepHandler

        return BrowserAutomationStepHandler(MagicMock(), MagicMock(), MagicMock())

    @pytest.fixture
    def mock_flow_run(self):
        """Create mock FlowRun."""
        flow_run = MagicMock()
        flow_run.id = 1
        flow_run.tenant_id = "test_tenant"
        return flow_run

    @pytest.fixture
    def mock_step_run(self):
        """Create mock FlowNodeRun."""
        step_run = MagicMock()
        step_run.id = 1
        return step_run

    @pytest.mark.asyncio
    async def test_custom_mode_config(self, handler, mock_flow_run, mock_step_run):
        """Test custom mode configuration."""
        mock_step = MagicMock()
        mock_step.id = 1
        mock_step.config_json = json.dumps({
            "prompt": "take a screenshot",
            "mode": "host",
            "allowed_user_keys": ["+5511999999999"]
        })

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Success",
                metadata={"mode": "host"}
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step, {}, mock_flow_run, mock_step_run)

            # Verify config was passed to skill
            call_args = mock_skill_instance.process.call_args
            config = call_args[0][1]
            assert config["mode"] == "host"

    @pytest.mark.asyncio
    async def test_custom_timeout_config(self, handler, mock_flow_run, mock_step_run):
        """Test custom timeout configuration."""
        mock_step = MagicMock()
        mock_step.id = 1
        mock_step.config_json = json.dumps({
            "prompt": "take a screenshot",
            "timeout_seconds": 60
        })

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Success",
                metadata={}
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step, {}, mock_flow_run, mock_step_run)

            # Verify timeout was passed to skill
            call_args = mock_skill_instance.process.call_args
            config = call_args[0][1]
            assert config["timeout_seconds"] == 60


class TestBrowserAutomationStepHandlerOutputFormat:
    """Tests for output format consistency."""

    @pytest.fixture
    def handler(self):
        """Create handler instance for testing."""
        from flows.flow_engine import BrowserAutomationStepHandler

        return BrowserAutomationStepHandler(MagicMock(), MagicMock(), MagicMock())

    @pytest.fixture
    def mock_flow_run(self):
        """Create mock FlowRun."""
        flow_run = MagicMock()
        flow_run.id = 1
        flow_run.tenant_id = "test_tenant"
        return flow_run

    @pytest.fixture
    def mock_step_run(self):
        """Create mock FlowNodeRun."""
        step_run = MagicMock()
        step_run.id = 1
        return step_run

    @pytest.mark.asyncio
    async def test_output_contains_required_fields(self, handler, mock_flow_run, mock_step_run):
        """Test that output contains all required fields."""
        mock_step = MagicMock()
        mock_step.id = 1
        mock_step.config_json = json.dumps({"prompt": "navigate to example.com"})

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Navigation complete",
                metadata={
                    "screenshot_paths": [],
                    "actions_executed": 1,
                    "actions_succeeded": 1,
                    "provider": "playwright",
                    "mode": "container"
                }
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step, {}, mock_flow_run, mock_step_run)

            # Required fields
            assert "status" in result
            assert "output" in result
            assert "screenshot_paths" in result
            assert "actions_executed" in result
            assert "executed_at" in result

    @pytest.mark.asyncio
    async def test_screenshot_paths_available_for_downstream(self, handler, mock_flow_run, mock_step_run):
        """Test screenshot paths are available for downstream steps."""
        mock_step = MagicMock()
        mock_step.id = 1
        mock_step.config_json = json.dumps({"prompt": "screenshot example.com"})

        expected_paths = ["/tmp/screenshot1.png", "/tmp/screenshot2.png"]

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Screenshots taken",
                metadata={
                    "screenshot_paths": expected_paths,
                    "actions_executed": 2
                }
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step, {}, mock_flow_run, mock_step_run)

            # Verify paths are in output for template access
            assert result["screenshot_paths"] == expected_paths


class TestBrowserAutomationStepHandlerTokenTracking:
    """Tests for token tracking in flows."""

    @pytest.mark.asyncio
    async def test_token_tracker_passed_to_skill(self):
        """Test that token_tracker is passed to skill."""
        from flows.flow_engine import BrowserAutomationStepHandler

        mock_db = MagicMock()
        mock_sender = MagicMock()
        mock_tracker = MagicMock()

        handler = BrowserAutomationStepHandler(mock_db, mock_sender, mock_tracker)

        mock_step = MagicMock()
        mock_step.id = 1
        mock_step.config_json = json.dumps({"prompt": "test"})

        mock_flow_run = MagicMock()
        mock_flow_run.id = 1
        mock_flow_run.tenant_id = "test"

        mock_step_run = MagicMock()
        mock_step_run.id = 1

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Success",
                metadata={}
            ))
            MockSkill.return_value = mock_skill_instance

            await handler.execute(mock_step, {}, mock_flow_run, mock_step_run)

            # Verify token_tracker was passed to skill
            MockSkill.assert_called_once_with(db=mock_db, token_tracker=mock_tracker)


class TestFlowEngineWithBrowserAutomation:
    """Integration tests for FlowEngine with browser automation steps."""

    def test_flow_engine_has_browser_automation_handler(self):
        """Test FlowEngine registers browser automation handler."""
        from flows.flow_engine import FlowEngine

        mock_db = MagicMock()
        engine = FlowEngine(db=mock_db)

        # Both lowercase and PascalCase should work
        assert "browser_automation" in engine.handlers
        assert "BrowserAutomation" in engine.handlers

        # Should be the same handler type
        from flows.flow_engine import BrowserAutomationStepHandler
        assert isinstance(engine.handlers["browser_automation"], BrowserAutomationStepHandler)
        assert isinstance(engine.handlers["BrowserAutomation"], BrowserAutomationStepHandler)
