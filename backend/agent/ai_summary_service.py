"""
AI Summary Service for Persona Auto-Generation
Generates concise summaries of persona characteristics using system-level AI model.
"""
import logging
from typing import Optional
from agent.ai_client import AIClient

logger = logging.getLogger(__name__)


class AISummaryService:
    """
    Service for generating AI-powered persona summaries.
    Should use agent's configured LLM (model_provider and model_name).
    """

    def __init__(self, model_provider: str = None, model_name: str = None, db=None):
        """
        Initialize AI Summary Service.

        Args:
            model_provider: AI provider (REQUIRED: should be agent's model_provider)
            model_name: Specific model name (REQUIRED: should be agent's model_name)
            db: Database session for loading API keys
        """
        # Warn if using fallback instead of agent's configured LLM
        if not model_provider or not model_name:
            logger.warning(
                f"AISummaryService initialized without explicit LLM config. "
                f"Using fallback: provider={model_provider or 'gemini'}, model={model_name or 'gemini-2.5-pro'}. "
                f"This should be the agent's configured model_provider and model_name."
            )

        self.model_provider = model_provider if model_provider else "gemini"
        self.model_name = model_name if model_name else "gemini-2.5-pro"
        self.ai_client = AIClient(
            provider=self.model_provider,
            model_name=self.model_name,
            db=db
        )

    def generate_persona_summary(
        self,
        name: str,
        description: str,
        role: Optional[str] = None,
        role_description: Optional[str] = None,
        tone_preset_name: Optional[str] = None,
        custom_tone: Optional[str] = None,
        personality_traits: Optional[str] = None,
        enabled_skills: list = None,
        guardrails: Optional[str] = None
    ) -> str:
        """
        Generate AI summary for a persona based on its characteristics.

        Args:
            name: Persona name
            description: Persona description
            role: Role title (optional)
            role_description: Role details (optional)
            tone_preset_name: Tone preset name (optional)
            custom_tone: Custom tone description (optional)
            personality_traits: Personality characteristics (optional)
            enabled_skills: List of enabled skills (optional)
            guardrails: Safety rules (optional)

        Returns:
            AI-generated summary (2-3 sentences)
        """
        enabled_skills = enabled_skills or []

        # Build persona characteristics for summary
        characteristics = []
        characteristics.append(f"Name: {name}")
        characteristics.append(f"Description: {description}")

        if role:
            characteristics.append(f"Role: {role}")
        if role_description:
            characteristics.append(f"Role Description: {role_description}")

        # Tone information
        if custom_tone:
            characteristics.append(f"Tone: {custom_tone}")
        elif tone_preset_name:
            characteristics.append(f"Tone Preset: {tone_preset_name}")

        if personality_traits:
            characteristics.append(f"Personality Traits: {personality_traits}")

        if enabled_skills:
            characteristics.append(f"Skills: {', '.join(map(str, enabled_skills))}")

        if guardrails:
            characteristics.append(f"Guardrails: {guardrails}")

        # Create prompt for AI
        prompt = f"""You are a helpful assistant that summarizes AI agent personas.

Based on the following persona characteristics, generate a concise summary (2-3 sentences) that captures:
1. The persona's core identity and role
2. Key personality traits and communication style
3. Specialized capabilities or focus areas

Persona Characteristics:
{chr(10).join(characteristics)}

Generate a natural, flowing summary that describes this persona's essence. Keep it concise and professional."""

        try:
            # Generate summary using AI
            response = self.ai_client.chat([{"role": "user", "content": prompt}])
            summary = response.strip()

            logger.info(f"Generated AI summary for persona '{name}': {summary[:100]}...")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate AI summary for persona '{name}': {e}")
            # Fallback to basic summary
            fallback = f"{name} is {description.lower() if description else 'a custom persona'}"
            if role:
                fallback += f" serving as a {role.lower()}"
            fallback += "."
            return fallback

    async def generate_persona_summary_async(self, **kwargs) -> str:
        """
        Async version of generate_persona_summary.
        (For future async support - currently wraps sync version)
        """
        return self.generate_persona_summary(**kwargs)
