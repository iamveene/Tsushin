"""
Image Analysis Skill
Interpret user-provided images using Gemini multimodal models.

Designed for inbound media messages (e.g. WhatsApp images) where the user wants
the agent to describe, interpret, summarize, OCR, or answer questions about an
attached image.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional, TYPE_CHECKING

import httpx

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from services.provider_instance_service import ProviderInstanceService

if TYPE_CHECKING:
    from analytics.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class ImageAnalysisSkill(BaseSkill):
    """
    Analyze attached images with Gemini multimodal understanding.

    Behavior:
    - Image only -> describe the image automatically
    - Image + caption/question -> answer based on the image and caption
    - Image + edit-like instruction -> defer to ImageSkill if enabled
    """

    skill_type = "image_analysis"
    skill_name = "Image Analysis"
    skill_description = "Describe, interpret, summarize, and extract information from attached images"
    execution_mode = "special"

    SUPPORTED_IMAGE_FORMATS = {
        "image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif",
        "image"
    }

    SUPPORTED_MODELS = {
        "gemini-2.5-flash": "Gemini 2.5 Flash (Recommended)",
        "gemini-2.5-pro": "Gemini 2.5 Pro",
        "gemini-2.0-flash": "Gemini 2.0 Flash"
    }

    def __init__(self, token_tracker: Optional["TokenTracker"] = None):
        super().__init__()
        self.token_tracker = token_tracker
        self._intent_cache: Dict[str, str] = {}  # message.id -> "generate" | "edit" | "none"

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Handle only attached images.

        If the caption is an image-edit/generate request (LLM-classified, not
        keyword-matched), defer to ImageSkill instead of analyzing.
        """
        if not message.media_type or message.media_type.lower() not in self.SUPPORTED_IMAGE_FORMATS:
            return False

        config = getattr(self, "_config", {}) or self.get_default_config()
        caption = (message.body or "").strip()

        if caption and await self._looks_like_edit_request(message, config):
            logger.info("ImageAnalysisSkill: caption classified as image edit, deferring to ImageSkill")
            return False

        logger.info("ImageAnalysisSkill: image message accepted for analysis")
        return True

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """Analyze the attached image and return a direct text response."""
        try:
            image_path = message.media_path

            if (not image_path or not os.path.exists(image_path)) and message.media_url:
                image_path = await self._download_image(message.media_url, message.id)

            if not image_path or not os.path.exists(image_path):
                return SkillResult(
                    success=False,
                    output="Nao consegui acessar a imagem. Tente enviar novamente.",
                    metadata={"error": "image_not_found", "skip_ai": True, "skill_type": self.skill_type}
                )

            prompt = self._build_analysis_prompt(message, config)
            model = config.get("model", self.get_default_config()["model"])

            result = await self._analyze_image_with_gemini(
                image_path=image_path,
                prompt=prompt,
                model=model
            )

            if not result.get("success"):
                return SkillResult(
                    success=False,
                    output=f"Falha ao analisar a imagem: {result.get('error', 'erro desconhecido')}",
                    metadata={
                        "error": result.get("error"),
                        "skip_ai": True,
                        "skill_type": self.skill_type
                    }
                )

            analysis_text = result.get("analysis", "").strip()
            if not analysis_text:
                return SkillResult(
                    success=False,
                    output="Nao consegui extrair uma analise util da imagem.",
                    metadata={"error": "empty_analysis", "skip_ai": True, "skill_type": self.skill_type}
                )

            if self.token_tracker:
                self._track_usage(
                    model=model,
                    prompt=prompt,
                    message=message,
                    result=result
                )

            return SkillResult(
                success=True,
                output=analysis_text,
                metadata={
                    "skip_ai": True,
                    "skill_type": self.skill_type,
                    "model": model,
                    "analysis_prompt": prompt
                }
            )

        except Exception as e:
            logger.error(f"ImageAnalysisSkill process error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Erro ao analisar a imagem: {str(e)}",
                metadata={"error": str(e), "skip_ai": True, "skill_type": self.skill_type}
            )

    async def _analyze_image_with_gemini(
        self,
        image_path: str,
        prompt: str,
        model: str
    ) -> Dict[str, Any]:
        """Send image + prompt to Gemini and extract a text response."""
        try:
            api_key = await self._get_api_key()
            if not api_key:
                return {"success": False, "error": "Gemini API key not configured"}

            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)

            with open(image_path, "rb") as f:
                image_data = f.read()

            mime_type = self._guess_mime_type(image_path)
            image_part = types.Part.from_bytes(data=image_data, mime_type=mime_type)

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=[prompt, image_part]
            )

            analysis_text = self._extract_response_text(response)
            if not analysis_text:
                return {"success": False, "error": "No text analysis returned by Gemini"}

            return {
                "success": True,
                "analysis": analysis_text,
                "input_tokens": len(prompt) // 4 + len(image_data) // 1000,
                "output_tokens": len(analysis_text) // 4
            }

        except Exception as e:
            logger.error(f"Gemini image analysis error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _build_analysis_prompt(self, message: InboundMessage, config: Dict[str, Any]) -> str:
        """Build a multimodal prompt, using the user's caption when available."""
        user_text = (message.body or "").strip()
        base_prompt = config.get(
            "analysis_prompt",
            self.get_default_config()["analysis_prompt"]
        ).strip()

        if user_text:
            return (
                f"{base_prompt}\n\n"
                f"User request: {user_text}\n\n"
                "Answer in the same language as the user's request when possible."
            )

        return (
            f"{base_prompt}\n\n"
            "No extra user instructions were provided. Describe the image briefly, "
            "identify the main elements, and mention any visible text if relevant."
        )

    async def _looks_like_edit_request(self, message: InboundMessage, config: Dict[str, Any]) -> bool:
        """
        Decide whether to defer this image+caption to ImageSkill.

        Uses the shared LLM classifier (same prompt/options as ImageSkill) to
        keep handoff decisions consistent between the two skills.
        """
        caption = (message.body or "").strip()
        if not caption:
            return False

        if message.id in self._intent_cache:
            return self._intent_cache[message.id] in ("edit", "generate")

        from agent.skills.ai_classifier import get_classifier
        classifier = get_classifier()

        prompt_message = (
            f"User message: \"{caption}\"\n"
            f"Context: An image has already been provided in this turn.\n\n"
            "Classify what image operation the user is asking for:\n"
            "- generate: user wants the system to CREATE a brand-new image from text\n"
            "- edit: user wants to MODIFY the attached image (change, remove, add, fix, "
            "enhance, recolor, crop, replace background, etc.)\n"
            "- none: the caption is a question/comment about the image, not an edit "
            "request (e.g. \"what is this?\", \"bonita né?\", \"explain\")"
        )

        intent = await classifier.extract_entity(
            message=prompt_message,
            entity_type="image operation",
            available_options=["generate", "edit", "none"],
            model=config.get("ai_model"),
            db=self._db_session,
            token_tracker=self.token_tracker,
            tenant_id=self._resolve_tenant_id_for_classifier(config),
        )

        normalized = (intent or "none").strip().lower()
        if normalized not in ("generate", "edit", "none"):
            normalized = "none"

        if len(self._intent_cache) >= 256:
            self._intent_cache.pop(next(iter(self._intent_cache)))
        self._intent_cache[message.id] = normalized

        logger.info(
            f"ImageAnalysisSkill: handoff classifier={normalized} for caption '{caption[:60]}'"
        )
        return normalized in ("edit", "generate")

    def _extract_response_text(self, response: Any) -> str:
        """Extract text safely from google-genai responses."""
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        parts = getattr(response, "parts", None) or []
        texts = []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text.strip():
                texts.append(part_text.strip())

        return "\n\n".join(texts).strip()

    async def _download_image(self, url: str, message_id: str) -> Optional[str]:
        """Fallback download if only a URL is available."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None

                content_type = response.headers.get("content-type", "image/jpeg")
                extension = ".jpg"
                if "png" in content_type:
                    extension = ".png"
                elif "webp" in content_type:
                    extension = ".webp"
                elif "gif" in content_type:
                    extension = ".gif"

                import tempfile
                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=extension,
                    prefix=f"img_analysis_{message_id}_"
                ) as tmp:
                    tmp.write(response.content)
                    return tmp.name
        except Exception as e:
            logger.error(f"ImageAnalysisSkill download failed: {e}", exc_info=True)
            return None

    def _guess_mime_type(self, image_path: str) -> str:
        """Infer MIME type from file extension."""
        lower = image_path.lower()
        if lower.endswith(".png"):
            return "image/png"
        if lower.endswith(".webp"):
            return "image/webp"
        if lower.endswith(".gif"):
            return "image/gif"
        return "image/jpeg"

    async def _get_api_key(self) -> Optional[str]:
        """Load Gemini API key from the tenant ProviderInstance."""
        try:
            if self._db_session:
                tenant_id = None
                if isinstance(getattr(self, "_config", None), dict):
                    tenant_id = self._config.get("tenant_id")
                if tenant_id:
                    return ProviderInstanceService.resolve_default_api_key("gemini", tenant_id, self._db_session)
            return None
        except Exception:
            return None

    def _track_usage(
        self,
        model: str,
        prompt: str,
        message: InboundMessage,
        result: Dict[str, Any]
    ) -> None:
        """Best-effort token/cost accounting."""
        try:
            self.token_tracker.track_usage(
                operation_type="image_analysis",
                model_provider="gemini",
                model_name=model,
                prompt_tokens=result.get("input_tokens", 0),
                completion_tokens=result.get("output_tokens", 0),
                agent_id=getattr(self, "_agent_id", None),
                skill_type=self.skill_type,
                sender_key=message.sender_key,
                message_id=message.id
            )
        except Exception as e:
            logger.warning(f"Failed to track image analysis usage: {e}")

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "model": "gemini-2.5-flash",
            "analysis_prompt": (
                "Analyze the attached image carefully. Answer the user's request if one exists. "
                "If the image contains text, summarize or extract the important parts. "
                "If it is a screenshot, explain the key issue or information visible. "
                "Be concise but useful."
            ),
            "enabled_channels": ["whatsapp", "playground", "telegram", "slack", "discord"]
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model": {
                    "type": "string",
                    "description": "Gemini multimodal model for image understanding",
                    "enum": list(cls.SUPPORTED_MODELS.keys()),
                    "default": "gemini-2.5-flash"
                },
                "analysis_prompt": {
                    "type": "string",
                    "description": "Base instruction used when analyzing attached images"
                },
                "enabled_channels": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["whatsapp", "playground", "telegram", "slack", "discord"]},
                    "description": "Channels where this skill is active"
                }
            },
            "required": ["model"]
        }
