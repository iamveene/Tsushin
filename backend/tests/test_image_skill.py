"""
Unit Tests for ImageSkill - Skills-as-Tools Architecture

Tests cover:
- MCP tool definition compliance
- execute_tool() behavior
- can_handle() for hybrid mode
- Image cache functionality
- Error handling
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent.skills.image_skill import ImageSkill
from agent.skills.base import InboundMessage, SkillResult


class TestImageSkillMCPDefinition:
    """Test MCP tool definition compliance."""

    def test_mcp_tool_definition_structure(self):
        """MCP definition has required fields."""
        mcp_def = ImageSkill.get_mcp_tool_definition()
        assert mcp_def is not None
        assert mcp_def["name"] == "generate_image"
        assert "title" in mcp_def
        assert "description" in mcp_def
        assert "inputSchema" in mcp_def
        assert "prompt" in mcp_def["inputSchema"]["properties"]
        assert "prompt" in mcp_def["inputSchema"]["required"]

    def test_mcp_input_schema_properties(self):
        """Input schema has expected properties."""
        mcp_def = ImageSkill.get_mcp_tool_definition()
        properties = mcp_def["inputSchema"]["properties"]

        # Check prompt
        assert properties["prompt"]["type"] == "string"

        # Check model
        assert "model" in properties
        assert "enum" in properties["model"]

        # Check aspect_ratio
        assert "aspect_ratio" in properties
        assert "enum" in properties["aspect_ratio"]

    def test_mcp_annotations(self):
        """MCP annotations indicate non-destructive operation."""
        mcp_def = ImageSkill.get_mcp_tool_definition()
        assert "annotations" in mcp_def
        assert mcp_def["annotations"]["destructive"] is False
        assert mcp_def["annotations"]["idempotent"] is False

    def test_to_openai_tool_format(self):
        """Converts to valid OpenAI tool format."""
        openai_def = ImageSkill.to_openai_tool()
        assert openai_def is not None
        assert openai_def["type"] == "function"
        assert "function" in openai_def
        assert openai_def["function"]["name"] == "generate_image"
        assert "parameters" in openai_def["function"]


class TestImageSkillSentinelContext:
    """Test Sentinel security context."""

    def test_sentinel_context_has_expected_fields(self):
        """Sentinel context has all required fields."""
        ctx = ImageSkill.get_sentinel_context()
        assert "expected_intents" in ctx
        assert "expected_patterns" in ctx
        assert "risk_notes" in ctx

    def test_sentinel_context_has_content(self):
        """Sentinel context has meaningful content."""
        ctx = ImageSkill.get_sentinel_context()
        assert len(ctx["expected_intents"]) > 0
        assert len(ctx["expected_patterns"]) > 0
        assert ctx["risk_notes"] is not None


class TestImageSkillConfiguration:
    """Test skill configuration."""

    def test_skill_attributes(self):
        """Skill has correct class attributes."""
        assert ImageSkill.skill_type == "image"
        assert ImageSkill.skill_name == "Image Generation & Editing"
        assert ImageSkill.execution_mode == "hybrid"

    def test_default_config(self):
        """Default config has required fields."""
        config = ImageSkill.get_default_config()
        assert "model" in config
        assert "edit_keywords" in config
        assert "generate_keywords" in config
        assert "execution_mode" in config
        assert config["execution_mode"] == "hybrid"

    def test_config_schema(self):
        """Config schema is valid JSON schema."""
        schema = ImageSkill.get_config_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "model" in schema["properties"]
        assert "edit_keywords" in schema["properties"]
        assert "generate_keywords" in schema["properties"]

    def test_supported_formats(self):
        """Supported image formats are defined."""
        assert "image/jpeg" in ImageSkill.SUPPORTED_IMAGE_FORMATS
        assert "image/png" in ImageSkill.SUPPORTED_IMAGE_FORMATS
        assert "image/webp" in ImageSkill.SUPPORTED_IMAGE_FORMATS


class TestImageSkillCanHandle:
    """Test can_handle() for hybrid mode."""

    def _create_message(self, body="", media_type=None, media_path=None, chat_id="chat1"):
        """Helper to create InboundMessage."""
        return InboundMessage(
            id="test1",
            sender="user@test",
            sender_key="user@test",
            body=body,
            chat_id=chat_id,
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow(),
            media_type=media_type,
            media_path=media_path,
            channel="whatsapp"
        )

    @pytest.mark.asyncio
    async def test_handles_image_with_caption_edit_mode(self):
        """Image with caption triggers EDIT mode."""
        skill = ImageSkill()
        message = self._create_message(
            body="Remove the background",
            media_type="image/jpeg",
            media_path="/tmp/test.jpg"
        )
        result = await skill.can_handle(message)
        assert result is True

    @pytest.mark.asyncio
    async def test_caches_image_without_caption(self):
        """Image without caption is cached."""
        skill = ImageSkill()
        message = self._create_message(
            body="",
            media_type="image/jpeg",
            media_path="/tmp/test.jpg",
            chat_id="test_chat"
        )
        result = await skill.can_handle(message)
        assert result is False  # Not handled directly
        assert skill._has_recent_image("test_chat") is True

    @pytest.mark.asyncio
    async def test_handles_text_with_cached_image_edit_mode(self):
        """Text edit request with recent cached image triggers EDIT mode."""
        skill = ImageSkill()

        # First cache an image
        image_msg = self._create_message(
            body="",
            media_type="image/jpeg",
            media_path="/tmp/test.jpg",
            chat_id="test_chat"
        )
        skill._cache_recent_image(image_msg)

        # Then send edit text
        text_msg = self._create_message(
            body="remove the person",
            chat_id="test_chat"
        )
        result = await skill.can_handle(text_msg)
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_generate_request_no_image(self):
        """Text-to-image request triggers GENERATE mode."""
        skill = ImageSkill()
        message = self._create_message(body="generate an image of a sunset")
        result = await skill.can_handle(message)
        assert result is True

    @pytest.mark.asyncio
    async def test_handles_draw_keyword(self):
        """Draw keyword triggers generation."""
        skill = ImageSkill()
        message = self._create_message(body="draw me a picture of a cat")
        result = await skill.can_handle(message)
        assert result is True

    @pytest.mark.asyncio
    async def test_rejects_unrelated_text(self):
        """Unrelated text is not handled."""
        skill = ImageSkill()
        message = self._create_message(body="What's the weather like?")
        result = await skill.can_handle(message)
        assert result is False


class TestImageSkillCache:
    """Test image cache functionality."""

    def _create_message(self, chat_id="chat1"):
        return InboundMessage(
            id="img1",
            sender="user",
            sender_key="user",
            body="",
            chat_id=chat_id,
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow(),
            media_type="image/jpeg",
            media_path="/tmp/test.jpg",
            media_url="http://example.com/img.jpg"
        )

    def test_cache_stores_image_info(self):
        """Cache stores image information."""
        skill = ImageSkill()
        message = self._create_message(chat_id="chat123")
        skill._cache_recent_image(message)

        assert skill._has_recent_image("chat123") is True
        cached = skill._get_recent_image("chat123")
        assert cached["message_id"] == "img1"
        assert cached["media_path"] == "/tmp/test.jpg"

    def test_cache_expires_after_5_minutes(self):
        """Cached images expire after 5 minutes."""
        skill = ImageSkill()
        skill._recent_images_cache["chat1"] = {
            "message_id": "old",
            "media_path": "/tmp/old.jpg",
            "timestamp": datetime.utcnow() - timedelta(minutes=6)
        }
        assert skill._has_recent_image("chat1") is False

    def test_cache_valid_within_5_minutes(self):
        """Cached images valid within 5 minutes."""
        skill = ImageSkill()
        skill._recent_images_cache["chat1"] = {
            "message_id": "recent",
            "media_path": "/tmp/recent.jpg",
            "timestamp": datetime.utcnow() - timedelta(minutes=4)
        }
        assert skill._has_recent_image("chat1") is True

    def test_cache_is_per_chat(self):
        """Different chats have independent caches."""
        skill = ImageSkill()
        msg1 = self._create_message(chat_id="chat_a")
        msg2 = self._create_message(chat_id="chat_b")

        skill._cache_recent_image(msg1)
        skill._cache_recent_image(msg2)

        assert skill._has_recent_image("chat_a") is True
        assert skill._has_recent_image("chat_b") is True
        assert skill._has_recent_image("chat_c") is False


class TestImageSkillExecuteTool:
    """Test execute_tool() for tool calls."""

    def _create_message(self):
        return InboundMessage(
            id="test",
            sender="user",
            sender_key="user",
            body="",
            chat_id="chat1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_execute_tool_missing_prompt(self):
        """Missing prompt returns error."""
        skill = ImageSkill()
        message = self._create_message()
        result = await skill.execute_tool({}, message, {})
        assert result.success is False
        assert "prompt" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_tool_empty_prompt(self):
        """Empty prompt returns error."""
        skill = ImageSkill()
        message = self._create_message()
        result = await skill.execute_tool({"prompt": ""}, message, {})
        assert result.success is False

    @pytest.mark.asyncio
    @patch.object(ImageSkill, '_generate_image_with_gemini')
    async def test_execute_tool_success(self, mock_generate):
        """Successful tool execution returns image path."""
        mock_generate.return_value = {
            "success": True,
            "output_path": "/tmp/generated.png",
            "input_tokens": 100,
            "output_tokens": 1000
        }

        skill = ImageSkill()
        message = self._create_message()
        result = await skill.execute_tool(
            {"prompt": "a beautiful sunset"},
            message,
            {}
        )

        assert result.success is True
        assert result.media_paths == ["/tmp/generated.png"]
        assert result.metadata["mode"] == "generate"
        assert result.metadata["skip_ai"] is True

    @pytest.mark.asyncio
    @patch.object(ImageSkill, '_generate_image_with_gemini')
    async def test_execute_tool_api_failure(self, mock_generate):
        """API failure returns error result."""
        mock_generate.return_value = {
            "success": False,
            "error": "API rate limit exceeded"
        }

        skill = ImageSkill()
        message = self._create_message()
        result = await skill.execute_tool(
            {"prompt": "a cat"},
            message,
            {}
        )

        assert result.success is False
        assert "rate limit" in result.output.lower() or "failed" in result.output.lower()


class TestImageSkillProcess:
    """Test process() method for legacy mode."""

    def _create_message(self, body="", media_type=None, media_path=None, chat_id="chat1"):
        return InboundMessage(
            id="test1",
            sender="user@test",
            sender_key="user@test",
            body=body,
            chat_id=chat_id,
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow(),
            media_type=media_type,
            media_path=media_path
        )

    @pytest.mark.asyncio
    async def test_process_no_instruction(self):
        """Process without instruction returns error."""
        skill = ImageSkill()
        message = self._create_message(body="", media_type="image/jpeg")
        result = await skill.process(message, {})
        assert result.success is False

    @pytest.mark.asyncio
    @patch.object(ImageSkill, '_generate_image_with_gemini')
    async def test_process_generate_mode(self, mock_generate):
        """Process in generate mode calls generation API."""
        mock_generate.return_value = {
            "success": True,
            "output_path": "/tmp/generated.png",
            "input_tokens": 100,
            "output_tokens": 1000
        }

        skill = ImageSkill()
        message = self._create_message(body="generate an image of a mountain")
        result = await skill.process(message, {})

        assert result.success is True
        assert result.metadata["mode"] == "generate"
        mock_generate.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(ImageSkill, '_edit_image_with_gemini')
    @patch('os.path.exists')
    async def test_process_edit_mode_with_image(self, mock_exists, mock_edit):
        """Process in edit mode with image calls edit API."""
        mock_exists.return_value = True
        mock_edit.return_value = {
            "success": True,
            "output_path": "/tmp/edited.png",
            "input_tokens": 200,
            "output_tokens": 1000
        }

        skill = ImageSkill()
        message = self._create_message(
            body="remove the background",
            media_type="image/jpeg",
            media_path="/tmp/input.jpg"
        )
        result = await skill.process(message, {})

        assert result.success is True
        assert result.metadata["mode"] == "edit"
        mock_edit.assert_called_once()


class TestImageSkillKeywordDetection:
    """Test keyword detection for generation and editing."""

    def _create_message(self, body):
        return InboundMessage(
            id="test",
            sender="user",
            sender_key="user",
            body=body,
            chat_id="chat1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_detect_generate_keywords_english(self):
        """Detects English generation keywords."""
        skill = ImageSkill()
        config = ImageSkill.get_default_config()

        # Test various keywords
        keywords = ["generate image", "create image", "draw", "imagine", "visualize"]
        for kw in keywords:
            msg = self._create_message(f"Please {kw} of a cat")
            result = await skill._is_generate_request(msg, config)
            assert result is True, f"Failed for keyword: {kw}"

    @pytest.mark.asyncio
    async def test_detect_generate_keywords_portuguese(self):
        """Detects Portuguese generation keywords."""
        skill = ImageSkill()
        config = ImageSkill.get_default_config()

        keywords = ["gerar imagem", "crie uma imagem", "desenhar", "desenhe"]
        for kw in keywords:
            msg = self._create_message(f"Por favor {kw} de um gato")
            result = await skill._is_generate_request(msg, config)
            assert result is True, f"Failed for keyword: {kw}"

    @pytest.mark.asyncio
    async def test_detect_edit_keywords(self):
        """Detects edit keywords."""
        skill = ImageSkill()
        config = ImageSkill.get_default_config()

        keywords = ["remove", "add", "change", "fix", "enhance", "crop"]
        for kw in keywords:
            msg = self._create_message(f"Please {kw} the background")
            result = await skill._is_edit_request(msg, config)
            assert result is True, f"Failed for keyword: {kw}"


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
