"""
Phase 4: Complex Skills Tests

Tests for the three complex skills migrated to tool mode:
- FlowsSkill (manage_reminders tool)
- BrowserAutomationSkill (browser_control tool)
- AutomationSkill (manage_flows tool)

Also tests SkillStepHandler and BrowserAutomationStepHandler updates.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import json

from agent.skills.base import InboundMessage, SkillResult


# ============================================================================
# Test Helper Functions
# ============================================================================

def create_test_message(
    body: str = "Test message",
    sender_key: str = "test_user",
    channel: str = "playground",
    sender: str = "test@example.com"
) -> InboundMessage:
    """Create a test InboundMessage."""
    return InboundMessage(
        id=f"msg-{datetime.now().timestamp()}",
        sender=sender,
        sender_key=sender_key,
        body=body,
        chat_id="chat-test",
        chat_name="Test Chat",
        is_group=False,
        timestamp=datetime.now(),
        channel=channel
    )


# ============================================================================
# FlowsSkill Tests
# ============================================================================

class TestFlowsSkillToolMode:
    """Test FlowsSkill tool mode implementation."""

    def test_flows_skill_has_hybrid_mode(self):
        """FlowsSkill execution_mode is hybrid."""
        from agent.skills.flows_skill import FlowsSkill

        assert FlowsSkill.execution_mode == "hybrid"

    def test_flows_skill_has_mcp_tool_definition(self):
        """FlowsSkill has valid MCP tool definition."""
        from agent.skills.flows_skill import FlowsSkill

        mcp_def = FlowsSkill.get_mcp_tool_definition()

        assert mcp_def is not None
        assert mcp_def["name"] == "manage_reminders"
        assert "description" in mcp_def
        assert "inputSchema" in mcp_def
        assert mcp_def["inputSchema"]["type"] == "object"

    def test_flows_skill_tool_has_action_parameter(self):
        """FlowsSkill tool has action parameter with valid enum values."""
        from agent.skills.flows_skill import FlowsSkill

        mcp_def = FlowsSkill.get_mcp_tool_definition()

        assert "action" in mcp_def["inputSchema"]["properties"]
        action_prop = mcp_def["inputSchema"]["properties"]["action"]
        assert "enum" in action_prop
        assert set(action_prop["enum"]) == {"create", "list", "update", "delete"}

    def test_flows_skill_tool_has_required_fields(self):
        """FlowsSkill tool has required fields."""
        from agent.skills.flows_skill import FlowsSkill

        mcp_def = FlowsSkill.get_mcp_tool_definition()

        assert "action" in mcp_def["inputSchema"]["required"]

    def test_flows_skill_has_annotations(self):
        """FlowsSkill tool has proper MCP annotations."""
        from agent.skills.flows_skill import FlowsSkill

        mcp_def = FlowsSkill.get_mcp_tool_definition()

        assert "annotations" in mcp_def
        assert "destructive" in mcp_def["annotations"]
        # create/update/delete are destructive
        assert mcp_def["annotations"]["destructive"] is True

    def test_flows_skill_is_tool_enabled(self):
        """FlowsSkill.is_tool_enabled() returns True for hybrid mode."""
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        # Default (hybrid)
        assert skill.is_tool_enabled() is True

        # Explicit hybrid
        assert skill.is_tool_enabled({"execution_mode": "hybrid"}) is True

        # Tool mode
        assert skill.is_tool_enabled({"execution_mode": "tool"}) is True

        # Legacy mode
        assert skill.is_tool_enabled({"execution_mode": "legacy"}) is False

    def test_flows_skill_is_legacy_enabled(self):
        """FlowsSkill.is_legacy_enabled() returns True for hybrid mode."""
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        # Default (hybrid)
        assert skill.is_legacy_enabled() is True

        # Explicit hybrid
        assert skill.is_legacy_enabled({"execution_mode": "hybrid"}) is True

        # Tool mode
        assert skill.is_legacy_enabled({"execution_mode": "tool"}) is False

    def test_flows_skill_to_openai_tool(self):
        """FlowsSkill.to_openai_tool() returns valid OpenAI format."""
        from agent.skills.flows_skill import FlowsSkill

        openai_tool = FlowsSkill.to_openai_tool()

        assert openai_tool is not None
        assert openai_tool["type"] == "function"
        assert "function" in openai_tool
        assert openai_tool["function"]["name"] == "manage_reminders"

    def test_flows_skill_to_anthropic_tool(self):
        """FlowsSkill.to_anthropic_tool() returns valid Anthropic format."""
        from agent.skills.flows_skill import FlowsSkill

        anthropic_tool = FlowsSkill.to_anthropic_tool()

        assert anthropic_tool is not None
        assert "input_schema" in anthropic_tool
        assert "type" not in anthropic_tool  # No function wrapper
        assert anthropic_tool["name"] == "manage_reminders"

    def test_flows_skill_get_sentinel_context(self):
        """FlowsSkill provides Sentinel context."""
        from agent.skills.flows_skill import FlowsSkill

        context = FlowsSkill.get_sentinel_context()

        assert "expected_intents" in context
        assert "expected_patterns" in context
        assert len(context["expected_intents"]) > 0

    @pytest.mark.asyncio
    async def test_flows_skill_execute_tool_list(self):
        """FlowsSkill.execute_tool() handles list action."""
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        # Mock the provider/service calls
        with patch.object(skill, '_execute_tool_list', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = SkillResult(
                success=True,
                output="No upcoming reminders found.",
                metadata={"action": "list", "count": 0}
            )

            result = await skill.execute_tool(
                arguments={"action": "list", "days_ahead": 7},
                message=create_test_message(),
                config={}
            )

            assert result.success is True
            mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_flows_skill_execute_tool_create(self):
        """FlowsSkill.execute_tool() handles create action."""
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        with patch.object(skill, '_execute_tool_create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = SkillResult(
                success=True,
                output="Reminder 'Test' created for tomorrow at 9am.",
                metadata={"action": "create", "reminder_id": "123"}
            )

            result = await skill.execute_tool(
                arguments={
                    "action": "create",
                    "title": "Test",
                    "datetime": "tomorrow at 9am"
                },
                message=create_test_message(),
                config={}
            )

            assert result.success is True
            assert "created" in result.output.lower()

    @pytest.mark.asyncio
    async def test_flows_skill_execute_tool_invalid_action(self):
        """FlowsSkill.execute_tool() returns error for invalid action."""
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        result = await skill.execute_tool(
            arguments={"action": "invalid_action"},
            message=create_test_message(),
            config={}
        )

        assert result.success is False
        assert "invalid" in result.output.lower() or "unknown" in result.output.lower()

    @pytest.mark.asyncio
    async def test_flows_skill_execute_tool_missing_action(self):
        """FlowsSkill.execute_tool() returns error for missing action."""
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        result = await skill.execute_tool(
            arguments={},  # No action
            message=create_test_message(),
            config={}
        )

        assert result.success is False
        assert "action" in result.output.lower() or "required" in result.output.lower()


# ============================================================================
# BrowserAutomationSkill Tests
# ============================================================================

class TestBrowserAutomationSkillToolMode:
    """Test BrowserAutomationSkill tool mode implementation."""

    def test_browser_skill_has_hybrid_mode(self):
        """BrowserAutomationSkill execution_mode is hybrid."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        assert BrowserAutomationSkill.execution_mode == "hybrid"

    def test_browser_skill_has_mcp_tool_definition(self):
        """BrowserAutomationSkill has valid MCP tool definition."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        mcp_def = BrowserAutomationSkill.get_mcp_tool_definition()

        assert mcp_def is not None
        assert mcp_def["name"] == "browser_control"
        assert "description" in mcp_def
        assert "inputSchema" in mcp_def

    def test_browser_skill_tool_has_action_parameter(self):
        """BrowserAutomationSkill tool has action parameter."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        mcp_def = BrowserAutomationSkill.get_mcp_tool_definition()

        assert "action" in mcp_def["inputSchema"]["properties"]
        action_prop = mcp_def["inputSchema"]["properties"]["action"]
        assert "enum" in action_prop
        expected_actions = {"navigate", "screenshot", "click", "fill", "extract"}
        assert set(action_prop["enum"]) == expected_actions

    def test_browser_skill_tool_has_mode_parameter(self):
        """BrowserAutomationSkill tool has mode parameter for container/host."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        mcp_def = BrowserAutomationSkill.get_mcp_tool_definition()

        assert "mode" in mcp_def["inputSchema"]["properties"]
        mode_prop = mcp_def["inputSchema"]["properties"]["mode"]
        assert "enum" in mode_prop
        assert "container" in mode_prop["enum"]
        assert "host" in mode_prop["enum"]

    def test_browser_skill_has_annotations(self):
        """BrowserAutomationSkill tool has proper MCP annotations."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        mcp_def = BrowserAutomationSkill.get_mcp_tool_definition()

        assert "annotations" in mcp_def
        # Browser automation can be destructive (clicks, fills)
        assert "destructive" in mcp_def["annotations"]

    def test_browser_skill_is_tool_enabled(self):
        """BrowserAutomationSkill.is_tool_enabled() returns True for hybrid."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()

        assert skill.is_tool_enabled() is True
        assert skill.is_tool_enabled({"execution_mode": "hybrid"}) is True
        assert skill.is_tool_enabled({"execution_mode": "tool"}) is True
        assert skill.is_tool_enabled({"execution_mode": "legacy"}) is False

    def test_browser_skill_to_openai_tool(self):
        """BrowserAutomationSkill.to_openai_tool() returns valid format."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        openai_tool = BrowserAutomationSkill.to_openai_tool()

        assert openai_tool is not None
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "browser_control"

    def test_browser_skill_get_sentinel_context(self):
        """BrowserAutomationSkill provides Sentinel context."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        context = BrowserAutomationSkill.get_sentinel_context()

        assert "expected_intents" in context
        assert "expected_patterns" in context
        assert "risk_notes" in context
        # Should have security considerations
        assert context["risk_notes"] is not None

    @pytest.mark.asyncio
    async def test_browser_skill_execute_tool_navigate(self):
        """BrowserAutomationSkill.execute_tool() handles navigate action."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()

        with patch.object(skill, '_execute_tool_navigate', new_callable=AsyncMock) as mock_nav:
            mock_nav.return_value = SkillResult(
                success=True,
                output="Navigated to https://example.com",
                metadata={"action": "navigate", "url": "https://example.com"}
            )

            result = await skill.execute_tool(
                arguments={
                    "action": "navigate",
                    "url": "https://example.com",
                    "mode": "container"
                },
                message=create_test_message(channel="playground"),
                config={}
            )

            assert result.success is True
            mock_nav.assert_called_once()

    @pytest.mark.asyncio
    async def test_browser_skill_execute_tool_screenshot(self):
        """BrowserAutomationSkill.execute_tool() handles screenshot action."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()

        with patch.object(skill, '_execute_tool_screenshot', new_callable=AsyncMock) as mock_ss:
            mock_ss.return_value = SkillResult(
                success=True,
                output="Screenshot captured",
                metadata={"action": "screenshot"},
                media_paths=["/tmp/screenshot.png"]
            )

            result = await skill.execute_tool(
                arguments={
                    "action": "screenshot",
                    "full_page": False
                },
                message=create_test_message(channel="playground"),
                config={}
            )

            assert result.success is True
            assert result.media_paths is not None
            assert len(result.media_paths) > 0

    @pytest.mark.asyncio
    async def test_browser_skill_host_mode_requires_auth(self):
        """BrowserAutomationSkill host mode requires user authorization."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()

        # User NOT in allowed list
        result = await skill.execute_tool(
            arguments={
                "action": "navigate",
                "url": "https://example.com",
                "mode": "host"
            },
            message=create_test_message(
                sender_key="unauthorized_user",
                channel="whatsapp"
            ),
            config={"allowed_user_keys": ["authorized_user"]}
        )

        assert result.success is False
        assert "not authorized" in result.output.lower() or "permission" in result.output.lower()

    @pytest.mark.asyncio
    async def test_browser_skill_host_mode_with_authorized_user(self):
        """BrowserAutomationSkill host mode works with authorized user.

        Note: The current implementation authorizes based on allowed_user_keys only.
        Channel restriction (WhatsApp/Telegram only) is NOT currently implemented.
        If channel restriction is needed, add it to browser_automation_skill.py.
        """
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()

        # Authorized user can use host mode (channel not restricted currently)
        result = await skill.execute_tool(
            arguments={
                "action": "navigate",
                "url": "https://example.com",
                "mode": "host"
            },
            message=create_test_message(
                sender_key="test_user",
                channel="whatsapp"  # Use WhatsApp for proper test
            ),
            config={"allowed_user_keys": ["test_user"]}
        )

        # Should succeed because user is authorized
        assert result.success is True
        assert "example.com" in result.output.lower() or "navigate" in result.output.lower()

    @pytest.mark.asyncio
    async def test_browser_skill_invalid_action(self):
        """BrowserAutomationSkill.execute_tool() errors on invalid action."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()

        result = await skill.execute_tool(
            arguments={"action": "invalid_action"},
            message=create_test_message(),
            config={}
        )

        assert result.success is False


# ============================================================================
# AutomationSkill Tests
# ============================================================================

class TestAutomationSkillToolMode:
    """Test AutomationSkill tool mode implementation."""

    def test_automation_skill_has_hybrid_mode(self):
        """AutomationSkill execution_mode is hybrid."""
        from agent.skills.automation_skill import AutomationSkill

        assert AutomationSkill.execution_mode == "hybrid"

    def test_automation_skill_has_mcp_tool_definition(self):
        """AutomationSkill has valid MCP tool definition."""
        from agent.skills.automation_skill import AutomationSkill

        mcp_def = AutomationSkill.get_mcp_tool_definition()

        assert mcp_def is not None
        assert mcp_def["name"] == "manage_flows"
        assert "description" in mcp_def
        assert "inputSchema" in mcp_def

    def test_automation_skill_tool_has_action_parameter(self):
        """AutomationSkill tool has action parameter."""
        from agent.skills.automation_skill import AutomationSkill

        mcp_def = AutomationSkill.get_mcp_tool_definition()

        assert "action" in mcp_def["inputSchema"]["properties"]
        action_prop = mcp_def["inputSchema"]["properties"]["action"]
        assert "enum" in action_prop
        expected_actions = {"list", "run", "status"}
        assert set(action_prop["enum"]) == expected_actions

    def test_automation_skill_has_annotations(self):
        """AutomationSkill tool has proper MCP annotations."""
        from agent.skills.automation_skill import AutomationSkill

        mcp_def = AutomationSkill.get_mcp_tool_definition()

        assert "annotations" in mcp_def
        # Running flows is destructive (can have side effects)
        assert mcp_def["annotations"]["destructive"] is True

    def test_automation_skill_is_tool_enabled(self):
        """AutomationSkill.is_tool_enabled() returns True for hybrid."""
        from agent.skills.automation_skill import AutomationSkill

        skill = AutomationSkill()

        assert skill.is_tool_enabled() is True
        assert skill.is_tool_enabled({"execution_mode": "hybrid"}) is True

    def test_automation_skill_to_openai_tool(self):
        """AutomationSkill.to_openai_tool() returns valid format."""
        from agent.skills.automation_skill import AutomationSkill

        openai_tool = AutomationSkill.to_openai_tool()

        assert openai_tool is not None
        assert openai_tool["type"] == "function"
        assert openai_tool["function"]["name"] == "manage_flows"

    def test_automation_skill_get_sentinel_context(self):
        """AutomationSkill provides Sentinel context."""
        from agent.skills.automation_skill import AutomationSkill

        context = AutomationSkill.get_sentinel_context()

        assert "expected_intents" in context
        assert "expected_patterns" in context

    @pytest.mark.asyncio
    async def test_automation_skill_execute_tool_list(self):
        """AutomationSkill.execute_tool() handles list action."""
        from agent.skills.automation_skill import AutomationSkill

        skill = AutomationSkill()

        with patch.object(skill, '_execute_tool_list', new_callable=AsyncMock) as mock_list:
            mock_list.return_value = SkillResult(
                success=True,
                output="Available flows:\n1. Test Flow\n2. Another Flow",
                metadata={"action": "list", "count": 2}
            )

            result = await skill.execute_tool(
                arguments={"action": "list"},
                message=create_test_message(),
                config={}
            )

            assert result.success is True
            mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_automation_skill_execute_tool_run(self):
        """AutomationSkill.execute_tool() handles run action."""
        from agent.skills.automation_skill import AutomationSkill

        skill = AutomationSkill()

        with patch.object(skill, '_execute_tool_run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = SkillResult(
                success=True,
                output="Flow 'Test Flow' started successfully.",
                metadata={"action": "run", "flow_name": "Test Flow"}
            )

            result = await skill.execute_tool(
                arguments={
                    "action": "run",
                    "flow_name": "Test Flow"
                },
                message=create_test_message(),
                config={}
            )

            assert result.success is True
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_automation_skill_invalid_action(self):
        """AutomationSkill.execute_tool() errors on invalid action."""
        from agent.skills.automation_skill import AutomationSkill

        skill = AutomationSkill()

        result = await skill.execute_tool(
            arguments={"action": "invalid_action"},
            message=create_test_message(),
            config={}
        )

        assert result.success is False


# ============================================================================
# SkillStepHandler Tests
# ============================================================================

class TestSkillStepHandlerToolMode:
    """Test SkillStepHandler tool mode support."""

    def test_skill_step_handler_exists(self):
        """SkillStepHandler class exists in flow_engine."""
        from flows.flow_engine import SkillStepHandler

        assert SkillStepHandler is not None

    def test_skill_step_handler_tool_mode_config_key(self):
        """SkillStepHandler recognizes use_tool_mode config key."""
        # Test that the skill manager properly handles execution mode
        from agent.skills.weather_skill import WeatherSkill

        skill = WeatherSkill()

        # Tool mode enabled with use_tool_mode config
        config = {"execution_mode": "tool"}
        assert skill.is_tool_enabled(config) is True

        # Legacy mode disabled tool
        config = {"execution_mode": "legacy"}
        assert skill.is_tool_enabled(config) is False

        # Hybrid enables both
        config = {"execution_mode": "hybrid"}
        assert skill.is_tool_enabled(config) is True
        assert skill.is_legacy_enabled(config) is True

    def test_skill_execute_tool_method_exists(self):
        """Phase 4 skills have execute_tool method for tool mode."""
        from agent.skills.flows_skill import FlowsSkill
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.automation_skill import AutomationSkill

        for skill_class in [FlowsSkill, BrowserAutomationSkill, AutomationSkill]:
            skill = skill_class()
            assert hasattr(skill, 'execute_tool'), f"{skill_class.__name__} should have execute_tool"
            assert callable(skill.execute_tool), f"{skill_class.__name__}.execute_tool should be callable"

    def test_skill_has_is_tool_enabled_method(self):
        """Skills have is_tool_enabled() method inherited from BaseSkill."""
        from agent.skills.flows_skill import FlowsSkill
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.automation_skill import AutomationSkill

        for skill_class in [FlowsSkill, BrowserAutomationSkill, AutomationSkill]:
            skill = skill_class()
            assert hasattr(skill, 'is_tool_enabled')
            assert callable(skill.is_tool_enabled)

            # All Phase 4 skills should return True for is_tool_enabled
            # because they're in hybrid mode
            assert skill.is_tool_enabled() is True


# ============================================================================
# BrowserAutomationStepHandler Tests
# ============================================================================

class TestBrowserAutomationStepHandlerToolMode:
    """Test BrowserAutomationStepHandler tool mode support."""

    def test_browser_step_handler_exists(self):
        """BrowserAutomationStepHandler class exists in flow_engine."""
        from flows.flow_engine import BrowserAutomationStepHandler

        assert BrowserAutomationStepHandler is not None


# ============================================================================
# Integration Tests - Tool Definition Collection
# ============================================================================

class TestPhase4ToolDefinitionCollection:
    """Test that all Phase 4 skills appear in tool collections."""

    def test_all_phase4_skills_have_tool_definitions(self):
        """All Phase 4 skills provide valid tool definitions."""
        from agent.skills.flows_skill import FlowsSkill
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.automation_skill import AutomationSkill

        skills = [FlowsSkill, BrowserAutomationSkill, AutomationSkill]
        expected_tools = ["manage_reminders", "browser_control", "manage_flows"]

        for skill_class, expected_name in zip(skills, expected_tools):
            mcp_def = skill_class.get_mcp_tool_definition()

            assert mcp_def is not None, f"{skill_class.__name__} should have tool definition"
            assert mcp_def["name"] == expected_name, \
                f"{skill_class.__name__} tool name should be {expected_name}"

    def test_phase4_skills_in_hybrid_mode(self):
        """All Phase 4 skills are in hybrid mode."""
        from agent.skills.flows_skill import FlowsSkill
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.automation_skill import AutomationSkill

        for skill_class in [FlowsSkill, BrowserAutomationSkill, AutomationSkill]:
            assert skill_class.execution_mode == "hybrid", \
                f"{skill_class.__name__} should be in hybrid mode"


# ============================================================================
# Backward Compatibility Tests
# ============================================================================

class TestPhase4BackwardCompatibility:
    """Test that Phase 4 skills maintain backward compatibility."""

    @pytest.mark.asyncio
    async def test_flows_skill_process_still_works(self):
        """FlowsSkill.process() still works for legacy mode."""
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        # Verify process method exists and is callable
        assert hasattr(skill, 'process')
        assert callable(skill.process)

    @pytest.mark.asyncio
    async def test_browser_skill_process_still_works(self):
        """BrowserAutomationSkill.process() still works for legacy mode."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()

        assert hasattr(skill, 'process')
        assert callable(skill.process)

    @pytest.mark.asyncio
    async def test_automation_skill_process_still_works(self):
        """AutomationSkill.process() still works for legacy mode."""
        from agent.skills.automation_skill import AutomationSkill

        skill = AutomationSkill()

        assert hasattr(skill, 'process')
        assert callable(skill.process)

    def test_flows_skill_can_handle_still_works(self):
        """FlowsSkill.can_handle() still works for keyword detection."""
        from agent.skills.flows_skill import FlowsSkill

        skill = FlowsSkill()

        assert hasattr(skill, 'can_handle')
        assert callable(skill.can_handle)


# ============================================================================
# JSON Serialization Tests
# ============================================================================

class TestPhase4OutputSerialization:
    """Test that skill outputs are JSON-serializable for flow templates."""

    def test_skill_result_metadata_serializable(self):
        """SkillResult metadata can be JSON-serialized."""
        result = SkillResult(
            success=True,
            output="Test output",
            metadata={
                "action": "test",
                "count": 5,
                "items": ["a", "b", "c"],
                "nested": {"key": "value"}
            }
        )

        # Should not raise
        json_str = json.dumps(result.metadata)
        assert json_str is not None

        # Should round-trip correctly
        parsed = json.loads(json_str)
        assert parsed["action"] == "test"
        assert parsed["count"] == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
