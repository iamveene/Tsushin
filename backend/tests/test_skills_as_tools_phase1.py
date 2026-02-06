"""
Skills-as-Tools Phase 1: Foundation Tests

Tests for the MCP tool definition infrastructure added to BaseSkill and SkillManager.
"""

import pytest
from typing import Dict, Any, Optional
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch

from agent.skills.base import BaseSkill, InboundMessage, SkillResult


class TestInboundMessageChannel:
    """Test the new channel field on InboundMessage."""

    def test_inbound_message_default_channel(self):
        """Channel should default to None when not specified."""
        msg = InboundMessage(
            id="test-1",
            sender="user@test",
            sender_key="user@test",
            body="Hello",
            chat_id="chat-1",
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow()
        )
        assert msg.channel is None

    def test_inbound_message_whatsapp_channel(self):
        """Can specify whatsapp channel."""
        msg = InboundMessage(
            id="test-1",
            sender="user@test",
            sender_key="user@test",
            body="Hello",
            chat_id="chat-1",
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow(),
            channel="whatsapp"
        )
        assert msg.channel == "whatsapp"

    def test_inbound_message_playground_channel(self):
        """Can specify playground channel."""
        msg = InboundMessage(
            id="test-1",
            sender="user@test",
            sender_key="user@test",
            body="Hello",
            chat_id="chat-1",
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow(),
            channel="playground"
        )
        assert msg.channel == "playground"

    def test_inbound_message_flow_channel(self):
        """Can specify flow channel for flow step execution."""
        msg = InboundMessage(
            id="flow_123_step_1",
            sender="flow_step",
            sender_key="flow_123",
            body="Execute skill",
            chat_id="flow_123",
            chat_name="Flow: 123",
            is_group=False,
            timestamp=datetime.utcnow(),
            channel="flow"
        )
        assert msg.channel == "flow"


class ConcreteTestSkill(BaseSkill):
    """Concrete implementation of BaseSkill for testing."""

    skill_type = "test_skill"
    skill_name = "Test Skill"
    skill_description = "A test skill for unit tests"
    execution_mode = "legacy"

    async def can_handle(self, message: InboundMessage) -> bool:
        return "test" in message.body.lower()

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        return SkillResult(
            success=True,
            output="Test processed",
            metadata={"test": True}
        )


class ToolEnabledTestSkill(BaseSkill):
    """Test skill with MCP tool definition."""

    skill_type = "tool_test_skill"
    skill_name = "Tool Test Skill"
    skill_description = "A test skill with tool definition"
    execution_mode = "tool"

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        return {
            "name": "test_tool",
            "title": "Test Tool",
            "description": "A test tool for unit testing",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "First parameter"},
                    "param2": {"type": "integer", "description": "Second parameter"}
                },
                "required": ["param1"]
            },
            "annotations": {
                "destructive": False,
                "idempotent": True
            }
        }

    async def can_handle(self, message: InboundMessage) -> bool:
        return False  # Tool mode only

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        return SkillResult(success=False, output="Use execute_tool()", metadata={})

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        return SkillResult(
            success=True,
            output=f"Executed with param1={arguments.get('param1')}",
            metadata={"arguments": arguments}
        )


class TestBaseSkillExecutionModes:
    """Test execution mode checking methods."""

    def test_is_tool_enabled_legacy_mode(self):
        """Legacy mode should not enable tool."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "legacy"}
        assert skill.is_tool_enabled(config) is False

    def test_is_tool_enabled_programmatic_mode(self):
        """Programmatic mode (alias for legacy) should not enable tool."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "programmatic"}
        assert skill.is_tool_enabled(config) is False

    def test_is_tool_enabled_tool_mode(self):
        """Tool mode should enable tool."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "tool"}
        assert skill.is_tool_enabled(config) is True

    def test_is_tool_enabled_agentic_mode(self):
        """Agentic mode (alias for tool) should enable tool."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "agentic"}
        assert skill.is_tool_enabled(config) is True

    def test_is_tool_enabled_hybrid_mode(self):
        """Hybrid mode should enable tool."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "hybrid"}
        assert skill.is_tool_enabled(config) is True

    def test_is_tool_enabled_passive_mode(self):
        """Passive mode should not enable tool."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "passive"}
        assert skill.is_tool_enabled(config) is False

    def test_is_tool_enabled_special_mode(self):
        """Special mode should not enable tool."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "special"}
        assert skill.is_tool_enabled(config) is False

    def test_is_tool_enabled_uses_class_default(self):
        """Should use class default when config doesn't specify mode."""
        skill = ConcreteTestSkill()
        skill.execution_mode = "tool"
        assert skill.is_tool_enabled({}) is True

    def test_is_legacy_enabled_legacy_mode(self):
        """Legacy mode should enable legacy."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "legacy"}
        assert skill.is_legacy_enabled(config) is True

    def test_is_legacy_enabled_hybrid_mode(self):
        """Hybrid mode should enable legacy."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "hybrid"}
        assert skill.is_legacy_enabled(config) is True

    def test_is_legacy_enabled_tool_mode(self):
        """Tool mode should not enable legacy."""
        skill = ConcreteTestSkill()
        config = {"execution_mode": "tool"}
        assert skill.is_legacy_enabled(config) is False

    def test_is_legacy_enabled_default_is_true(self):
        """Legacy should be enabled by default for backward compatibility."""
        skill = ConcreteTestSkill()
        assert skill.is_legacy_enabled({}) is True


class TestBaseSkillMCPToolDefinition:
    """Test MCP tool definition methods."""

    def test_get_mcp_tool_definition_returns_none_by_default(self):
        """Base class should return None for MCP definition."""
        skill = ConcreteTestSkill()
        assert skill.get_mcp_tool_definition() is None

    def test_get_mcp_tool_definition_returns_dict(self):
        """Skill with MCP definition should return valid dict."""
        mcp_def = ToolEnabledTestSkill.get_mcp_tool_definition()
        assert mcp_def is not None
        assert mcp_def["name"] == "test_tool"
        assert "inputSchema" in mcp_def
        assert mcp_def["inputSchema"]["required"] == ["param1"]

    def test_get_input_schema_default(self):
        """Default input schema should be empty object."""
        schema = ConcreteTestSkill.get_input_schema()
        assert schema == {"type": "object", "properties": {}}

    def test_get_output_schema_default(self):
        """Default output schema should be None."""
        assert ConcreteTestSkill.get_output_schema() is None


class TestBaseSkillProviderAdapters:
    """Test provider adapter methods."""

    def test_to_openai_tool_format(self):
        """Should convert MCP to OpenAI format."""
        openai_def = ToolEnabledTestSkill.to_openai_tool()
        assert openai_def is not None
        assert openai_def["type"] == "function"
        assert openai_def["function"]["name"] == "test_tool"
        assert openai_def["function"]["description"] == "A test tool for unit testing"
        assert "parameters" in openai_def["function"]

    def test_to_openai_tool_returns_none_when_no_mcp(self):
        """Should return None when no MCP definition."""
        assert ConcreteTestSkill.to_openai_tool() is None

    def test_to_anthropic_tool_format(self):
        """Should convert MCP to Anthropic format."""
        anthropic_def = ToolEnabledTestSkill.to_anthropic_tool()
        assert anthropic_def is not None
        assert "type" not in anthropic_def  # Anthropic doesn't use type wrapper
        assert anthropic_def["name"] == "test_tool"
        assert "input_schema" in anthropic_def
        assert anthropic_def["input_schema"]["required"] == ["param1"]

    def test_to_anthropic_tool_returns_none_when_no_mcp(self):
        """Should return None when no MCP definition."""
        assert ConcreteTestSkill.to_anthropic_tool() is None

    def test_get_tool_definition_backward_compat(self):
        """get_tool_definition should return OpenAI format for backward compat."""
        tool_def = ToolEnabledTestSkill.get_tool_definition()
        openai_def = ToolEnabledTestSkill.to_openai_tool()
        assert tool_def == openai_def


class TestBaseSkillToolExecution:
    """Test tool execution method."""

    @pytest.mark.asyncio
    async def test_execute_tool_raises_not_implemented(self):
        """Default execute_tool should raise NotImplementedError."""
        skill = ConcreteTestSkill()
        msg = InboundMessage(
            id="test-1",
            sender="user@test",
            sender_key="user@test",
            body="Hello",
            chat_id="chat-1",
            chat_name=None,
            is_group=False,
            timestamp=datetime.utcnow()
        )
        with pytest.raises(NotImplementedError):
            await skill.execute_tool({}, msg, {})

    @pytest.mark.asyncio
    async def test_execute_tool_with_implementation(self):
        """Skill with execute_tool implementation should work."""
        skill = ToolEnabledTestSkill()
        msg = InboundMessage(
            id="test-1",
            sender="user@test",
            sender_key="user@test",
            body="",
            chat_id="chat-1",
            chat_name=None,
            is_group=False,
            timestamp=datetime.utcnow()
        )
        result = await skill.execute_tool({"param1": "hello"}, msg, {})
        assert result.success is True
        assert "hello" in result.output


class TestSkillManagerToolMethods:
    """Test SkillManager tool-related methods."""

    def test_find_skill_by_tool_name(self):
        """Should find skill by MCP tool name."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        # Register our test skill
        manager.register_skill(ToolEnabledTestSkill)

        skill_class = manager._find_skill_by_tool_name("test_tool")
        assert skill_class is not None
        assert skill_class.skill_type == "tool_test_skill"

    def test_find_skill_by_tool_name_not_found(self):
        """Should return None for unknown tool name."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        skill_class = manager._find_skill_by_tool_name("nonexistent_tool")
        assert skill_class is None

    def test_validate_arguments_valid(self):
        """Should pass validation for valid arguments."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"}
            },
            "required": ["name"]
        }
        error = manager._validate_arguments({"name": "test", "count": 5}, schema)
        assert error is None

    def test_validate_arguments_missing_required(self):
        """Should fail validation for missing required field."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }
        error = manager._validate_arguments({}, schema)
        assert error is not None
        assert "name" in error

    def test_validate_arguments_wrong_type(self):
        """Should fail validation for wrong type."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        schema = {
            "type": "object",
            "properties": {
                "count": {"type": "integer"}
            }
        }
        error = manager._validate_arguments({"count": "not a number"}, schema)
        assert error is not None
        assert "integer" in error

    def test_create_skill_instance_normal(self):
        """Should create normal skill instance."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        manager.register_skill(ConcreteTestSkill)

        db_mock = MagicMock()
        instance = manager._create_skill_instance(ConcreteTestSkill, db_mock, 1)
        assert isinstance(instance, ConcreteTestSkill)


class TestShellSkillBackwardCompatibility:
    """Test that existing ShellSkill patterns still work."""

    def test_shell_skill_has_get_tool_definition(self):
        """ShellSkill should have get_tool_definition method."""
        from agent.skills.shell_skill import ShellSkill

        tool_def = ShellSkill.get_tool_definition()
        assert tool_def is not None
        # ShellSkill uses the old format, but get_tool_definition now wraps to_openai_tool
        # which wraps get_mcp_tool_definition, which ShellSkill doesn't implement yet
        # So it should return its own implementation
        assert "name" in tool_def or "function" in tool_def

    def test_shell_skill_is_tool_enabled(self):
        """ShellSkill should support is_tool_enabled method."""
        from agent.skills.shell_skill import ShellSkill

        skill = ShellSkill()
        # Default is programmatic mode
        assert skill.is_tool_enabled({}) is False
        # Agentic mode enables tool
        assert skill.is_tool_enabled({"execution_mode": "agentic"}) is True
