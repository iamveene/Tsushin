"""
Image Skill - Skills-as-Tools Architecture
Generate new images or edit existing ones using Google Gemini.

Phase: Skills-as-Tools
- Tool name: generate_image
- Execution mode: hybrid (tool + legacy keyword modes)
- Edit mode is NOT exposed as tool (requires image input)
"""

import os
import logging
import asyncio
import tempfile
import httpx
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime
from PIL import Image
import io

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from services.api_key_service import get_api_key

if TYPE_CHECKING:
    from analytics.token_tracker import TokenTracker
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ImageSkill(BaseSkill):
    """
    AI-powered image skill using Google Gemini.

    Supports TWO modes:
    1. Image Generation: Create new images from text prompts (tool-callable)
    2. Image Editing: Modify existing images (media-triggered only)

    Skills-as-Tools:
    - Tool name: generate_image
    - Execution mode: hybrid (tool + legacy keyword modes)
    - Edit mode is NOT exposed as tool (requires image input)
    """

    skill_type = "image"
    skill_name = "Image Generation & Editing"
    skill_description = "Generate new images from text prompts or edit existing images using AI"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    SUPPORTED_IMAGE_FORMATS = {
        "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
        "image"  # MCP sometimes sends just "image" without the MIME subtype
    }

    SUPPORTED_MODELS = {
        "gemini-2.5-flash-image": "Nano Banana (Fast)",
        "gemini-3-pro-image-preview": "Nano Banana Pro (Quality)"
    }

    def __init__(self, token_tracker: Optional["TokenTracker"] = None):
        super().__init__()
        self.token_tracker = token_tracker
        self._recent_images_cache: Dict[str, dict] = {}  # chat_id -> {message_id, media_path, timestamp}

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        MCP-compliant tool definition for image generation.

        Note: Only generation is exposed. Edit mode requires image input
        which cannot be passed through tool calls.
        """
        return {
            "name": "generate_image",
            "title": "Image Generation",
            "description": (
                "Generate a new image from a text description using AI. "
                "Use when user asks to create, draw, generate, imagine, or visualize an image. "
                "For editing existing images, user must send the image directly."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Detailed description of the image to generate"
                    },
                    "model": {
                        "type": "string",
                        "enum": list(cls.SUPPORTED_MODELS.keys()),
                        "description": "Model to use for generation",
                        "default": "gemini-2.5-flash-image"
                    },
                    "aspect_ratio": {
                        "type": "string",
                        "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"],
                        "description": "Aspect ratio of the generated image",
                        "default": "1:1"
                    }
                },
                "required": ["prompt"]
            },
            "annotations": {
                "destructive": False,
                "idempotent": False,
                "audience": ["user", "assistant"]
            }
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """Security context for Sentinel threat analysis."""
        return {
            "expected_intents": [
                "Generate images from text descriptions",
                "Create artwork, illustrations, or visualizations",
                "Edit existing images with modifications",
                "Remove, add, or change elements in images"
            ],
            "expected_patterns": [
                "generate", "create", "draw", "imagine", "visualize", "make",
                "gerar", "criar", "desenhar", "imaginar",
                "edit", "remove", "add", "change", "modify", "fix", "enhance",
                "editar", "remover", "adicionar", "mudar"
            ],
            "risk_notes": (
                "Image requests are expected behavior. Still flag: "
                "NSFW/adult content requests, violence/gore, "
                "copyrighted characters, deepfakes of real people, "
                "misleading/harmful imagery, identity document forgery."
            )
        }

    # =========================================================================
    # SKILLS-AS-TOOLS: TOOL EXECUTION
    # =========================================================================

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute image generation as a tool call.

        Called by the agent's tool execution loop when AI invokes generate_image.
        """
        prompt = arguments.get("prompt")
        if not prompt:
            return SkillResult(
                success=False,
                output="Prompt is required. Please describe the image you want to generate.",
                metadata={"error": "missing_prompt", "skip_ai": True}
            )

        model = arguments.get("model", config.get("model", "gemini-2.5-flash-image"))
        aspect_ratio = arguments.get("aspect_ratio", "1:1")

        logger.info(f"ImageSkill.execute_tool: prompt='{prompt[:50]}...', model={model}")

        try:
            result = await self._generate_image_with_gemini(
                prompt=prompt,
                model=model,
                config=config,
                aspect_ratio=aspect_ratio
            )

            if not result.get("success"):
                return SkillResult(
                    success=False,
                    output=f"Image generation failed: {result.get('error', 'Unknown error')}",
                    metadata={"error": result.get("error"), "skip_ai": True}
                )

            output_path = result.get("output_path")

            # Token tracking
            if self.token_tracker:
                self._track_usage(
                    model=model,
                    instruction=prompt,
                    message=message,
                    result=result,
                    mode="generate"
                )

            return SkillResult(
                success=True,
                output="Image generated successfully!",
                metadata={
                    "mode": "generate",
                    "model": model,
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "output_path": output_path,
                    "skip_ai": True
                },
                media_paths=[output_path] if output_path else None
            )

        except Exception as e:
            logger.error(f"ImageSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error generating image: {str(e)}",
                metadata={"error": str(e), "skip_ai": True}
            )

    # =========================================================================
    # LEGACY MODE: CAN_HANDLE AND PROCESS
    # =========================================================================

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Determine if this skill should handle the message.

        Hybrid mode logic:
        - Always handle image+caption (EDIT mode, media-triggered)
        - In legacy mode: also handle keyword-based generation requests
        - In tool-only mode: only media-triggered edit
        """
        config = getattr(self, '_config', {}) or self.get_default_config()

        # Case 1: Image with caption → EDIT mode (always handled, regardless of mode)
        if message.media_type and message.media_type.lower() in self.SUPPORTED_IMAGE_FORMATS:
            if message.body and message.body.strip():
                logger.info(f"ImageSkill: Image with caption detected (EDIT mode)")
                return True
            # Image without caption - cache for potential follow-up
            self._cache_recent_image(message)
            return False

        # Case 2 & 3: Text message
        if message.body and not message.media_type:
            # Check if legacy mode is enabled for keyword detection
            if not self.is_legacy_enabled(config):
                return False

            # Check for generation keywords
            if await self._is_generate_request(message, config):
                logger.info(f"ImageSkill: Generation request detected (GENERATE mode)")
                return True

            # Check for edit keywords + recent image
            if await self._is_edit_request(message, config):
                if self._has_recent_image(message.chat_id):
                    logger.info(f"ImageSkill: Edit request with recent image (EDIT mode)")
                    return True

        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process image request (edit or generate).

        Determines mode and processes accordingly:
        - EDIT mode: Requires input image + instruction
        - GENERATE mode: Text prompt only, no input image
        """
        try:
            model = config.get("model", "gemini-2.5-flash-image")

            # Determine mode
            has_input_image = (
                (message.media_type and message.media_type.lower() in self.SUPPORTED_IMAGE_FORMATS) or
                self._has_recent_image(message.chat_id)
            )

            is_generate_request = await self._is_generate_request(message, config) if message.body else False

            # Mode selection: Generate if explicitly requested and no image, otherwise edit
            mode = "generate" if (is_generate_request and not has_input_image) else "edit"

            # Get instruction/prompt
            instruction = message.body
            if not instruction or not instruction.strip():
                return SkillResult(
                    success=False,
                    output="Please provide instructions for the image.",
                    metadata={"error": "no_instruction", "skip_ai": True}
                )

            if mode == "edit":
                # EDIT mode: Need input image
                if message.media_type and message.media_type.lower() in self.SUPPORTED_IMAGE_FORMATS:
                    image_path = message.media_path
                    image_url = message.media_url
                else:
                    cached_image = self._get_recent_image(message.chat_id)
                    if not cached_image:
                        return SkillResult(
                            success=False,
                            output="No recent image found. Please send an image first.",
                            metadata={"error": "no_recent_image", "skip_ai": True}
                        )
                    image_path = cached_image.get("media_path")
                    image_url = cached_image.get("media_url")

                # Download image if we only have URL
                if not image_path and image_url:
                    image_path = await self._download_image(image_url, message.id)

                if not image_path or not os.path.exists(image_path):
                    return SkillResult(
                        success=False,
                        output="Could not access the image. Please try sending it again.",
                        metadata={"error": "image_not_found", "skip_ai": True}
                    )

                # Call Gemini API for image editing
                result = await self._edit_image_with_gemini(
                    image_path=image_path,
                    instruction=instruction,
                    model=model,
                    config=config
                )
            else:
                # GENERATE mode: Text-to-image
                result = await self._generate_image_with_gemini(
                    prompt=instruction,
                    model=model,
                    config=config
                )

            if not result.get("success"):
                return SkillResult(
                    success=False,
                    output=f"Image processing failed: {result.get('error', 'Unknown error')}",
                    metadata={"error": result.get("error"), "skip_ai": True}
                )

            output_path = result.get("output_path")

            # Track usage
            if self.token_tracker:
                self._track_usage(model, instruction, message, result, mode)

            success_message = "Image edited successfully!" if mode == "edit" else "Image generated successfully!"

            return SkillResult(
                success=True,
                output=success_message,
                metadata={
                    "mode": mode,
                    "model": model,
                    "instruction": instruction,
                    "output_path": output_path,
                    "skip_ai": True
                },
                media_paths=[output_path] if output_path else None
            )

        except Exception as e:
            logger.error(f"ImageSkill process error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Image processing failed: {str(e)}",
                metadata={"error": str(e), "skip_ai": True}
            )

    # =========================================================================
    # GEMINI API INTEGRATION
    # =========================================================================

    async def _generate_image_with_gemini(
        self,
        prompt: str,
        model: str,
        config: Dict[str, Any],
        aspect_ratio: str = "1:1"
    ) -> Dict[str, Any]:
        """
        Call Gemini API to generate a new image from text prompt.

        Uses the google-genai SDK with Gemini image generation models.
        """
        try:
            api_key = await self._get_api_key()
            if not api_key:
                return {"success": False, "error": "Gemini API key not configured"}

            from google import genai
            from google.genai import types

            # Initialize client with API key
            client = genai.Client(api_key=api_key)

            # Configure image generation
            generate_config = types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            )

            # Generate image from text prompt
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=[f"Generate an image: {prompt}"],
                config=generate_config
            )

            # Extract image from response
            output_path = None
            for part in response.parts:
                if part.inline_data is not None:
                    # Save the image using as_image() method
                    image = part.as_image()
                    # Use shared directory for Docker volume (shared with MCP containers)
                    shared_dir = Path(tempfile.gettempdir()) / "tsushin_images"
                    shared_dir.mkdir(parents=True, exist_ok=True)

                    # Generate unique filename
                    filename = f"img_gen_{uuid.uuid4().hex[:8]}.png"
                    output_path = str(shared_dir / filename)
                    image.save(output_path)
                    break

            if not output_path:
                return {"success": False, "error": "No image generated in response"}

            # Estimate tokens
            input_tokens = len(prompt) // 4
            output_tokens = os.path.getsize(output_path) // 1000

            return {
                "success": True,
                "output_path": output_path,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }

        except Exception as e:
            logger.error(f"Gemini generation API error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _edit_image_with_gemini(
        self,
        image_path: str,
        instruction: str,
        model: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call Gemini API to edit an existing image.

        Uses the google-genai SDK with Gemini image models.
        """
        try:
            api_key = await self._get_api_key()
            if not api_key:
                return {"success": False, "error": "Gemini API key not configured"}

            from google import genai
            from google.genai import types

            # Initialize client with API key
            client = genai.Client(api_key=api_key)

            # Load input image
            with open(image_path, "rb") as f:
                image_data = f.read()

            # Determine MIME type
            if image_path.lower().endswith('.png'):
                mime_type = "image/png"
            elif image_path.lower().endswith(('.jpg', '.jpeg')):
                mime_type = "image/jpeg"
            elif image_path.lower().endswith('.webp'):
                mime_type = "image/webp"
            else:
                mime_type = "image/jpeg"

            # Create Part from image bytes
            image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)

            # Configure for image output
            generate_config = types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            )

            # Generate edited image
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=[f"Edit this image: {instruction}", image_part],
                config=generate_config
            )

            # Extract image from response
            output_path = None
            for part in response.parts:
                if part.inline_data is not None:
                    # Save the image using as_image() method
                    image = part.as_image()
                    # Use shared directory for Docker volume (shared with MCP containers)
                    shared_dir = Path(tempfile.gettempdir()) / "tsushin_images"
                    shared_dir.mkdir(parents=True, exist_ok=True)

                    # Generate unique filename
                    filename = f"img_edit_{uuid.uuid4().hex[:8]}.png"
                    output_path = str(shared_dir / filename)
                    image.save(output_path)
                    break

            if not output_path:
                return {"success": False, "error": "No edited image in response"}

            # Estimate tokens
            input_tokens = len(instruction) // 4 + len(image_data) // 1000
            output_tokens = os.path.getsize(output_path) // 1000

            return {
                "success": True,
                "output_path": output_path,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }

        except Exception as e:
            logger.error(f"Gemini edit API error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def _get_api_key(self) -> Optional[str]:
        """Get Gemini API key from database or environment."""
        try:
            if self._db_session:
                return get_api_key("gemini", self._db_session) or os.getenv("GEMINI_API_KEY")
            return os.getenv("GEMINI_API_KEY")
        except Exception:
            return os.getenv("GEMINI_API_KEY")

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _is_generate_request(self, message: InboundMessage, config: Dict[str, Any]) -> bool:
        """Check if message is requesting image generation (text-to-image)."""
        text = message.body.lower()
        keywords = config.get("generate_keywords", self.get_default_config()["generate_keywords"])

        for keyword in keywords:
            if keyword.lower() in text:
                return True

        return False

    async def _is_edit_request(self, message: InboundMessage, config: Dict[str, Any]) -> bool:
        """Check if message appears to be an image edit request."""
        text = message.body.lower()
        keywords = config.get("edit_keywords", self.get_default_config()["edit_keywords"])

        for keyword in keywords:
            if keyword.lower() in text:
                return True

        return False

    def _cache_recent_image(self, message: InboundMessage):
        """Cache image info for potential follow-up requests."""
        self._recent_images_cache[message.chat_id] = {
            "message_id": message.id,
            "media_url": message.media_url,
            "media_path": message.media_path,
            "media_type": message.media_type,
            "timestamp": datetime.utcnow(),
            "sender": message.sender
        }
        logger.debug(f"Cached image from message {message.id} for chat {message.chat_id}")

    def _has_recent_image(self, chat_id: str) -> bool:
        """Check if we have a recent image cached for this chat."""
        if chat_id not in self._recent_images_cache:
            return False
        cached = self._recent_images_cache[chat_id]
        age = (datetime.utcnow() - cached["timestamp"]).total_seconds()
        return age < 300  # 5 minutes

    def _get_recent_image(self, chat_id: str) -> Optional[dict]:
        """Get cached recent image for chat."""
        if self._has_recent_image(chat_id):
            return self._recent_images_cache[chat_id]
        return None

    async def _download_image(self, url: str, message_id: str) -> Optional[str]:
        """Download image from URL to temp file."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "image/jpeg")
                    ext = ".jpg" if "jpeg" in content_type else ".png"
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=ext, prefix=f"img_input_{message_id}_"
                    ) as tmp:
                        tmp.write(response.content)
                        return tmp.name
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
        return None

    def _track_usage(
        self,
        model: str,
        instruction: str,
        message: InboundMessage,
        result: Dict[str, Any],
        mode: str = "edit"
    ):
        """Track token usage for this operation."""
        try:
            operation_type = "image_edit" if mode == "edit" else "image_generate"
            self.token_tracker.track_usage(
                operation_type=operation_type,
                model_provider="gemini",
                model_name=model,
                prompt_tokens=result.get("input_tokens", 0),
                completion_tokens=result.get("output_tokens", 0),
                agent_id=getattr(self, '_agent_id', None),
                skill_type="image",
                sender_key=message.sender_key,
                message_id=message.id
            )
        except Exception as e:
            logger.warning(f"Failed to track image usage: {e}")

    # =========================================================================
    # CONFIGURATION
    # =========================================================================

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "model": "gemini-2.5-flash-image",
            "edit_keywords": [
                "edit image", "editar imagem", "edit this", "editar isso",
                "remove", "remover", "add", "adicionar", "change", "mudar",
                "fix", "corrigir", "enhance", "melhorar", "crop", "cortar"
            ],
            "generate_keywords": [
                "generate image", "generate an image", "create image", "create an image",
                "gerar imagem", "crie uma imagem", "draw", "desenhar", "desenhe",
                "make an image", "imagine", "visualize"
            ],
            "use_ai_fallback": True,
            "lookback_messages": 5,
            "processing_message": "Processing your image, please wait...",
            "enabled_channels": ["whatsapp", "playground"],
            "execution_mode": "hybrid"
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Gemini model for image generation/editing",
                    "enum": list(cls.SUPPORTED_MODELS.keys()),
                    "default": "gemini-2.5-flash-image"
                },
                "edit_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords that trigger image editing"
                },
                "generate_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords that trigger image generation"
                },
                "lookback_messages": {
                    "type": "integer",
                    "description": "Messages to search for images (edit mode)",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5
                },
                "processing_message": {
                    "type": "string",
                    "description": "Message shown while processing",
                    "default": "Processing your image, please wait..."
                },
                "enabled_channels": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["whatsapp", "playground", "telegram"]},
                    "description": "Channels where this skill is active"
                },
                "execution_mode": {
                    "type": "string",
                    "enum": ["tool", "legacy", "hybrid"],
                    "description": "Execution mode: tool (AI decides), legacy (keywords only), hybrid (both)",
                    "default": "hybrid"
                }
            },
            "required": ["model"]
        }
