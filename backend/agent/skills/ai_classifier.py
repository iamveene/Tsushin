"""
Phase 7.1.1.2: AI Skill Classifier
Shared AI classification helper for all skills with configurable keywords.

Provides intent classification and entity extraction using various LLM providers.

Phase 17: Updated to use system AI configuration instead of hardcoded defaults.
"""

from typing import Optional, List, Dict, Any
import logging
from agent.ai_client import AIClient
from services.system_ai_config import get_system_ai_config, DEFAULT_SYSTEM_AI_PROVIDER, DEFAULT_SYSTEM_AI_MODEL

logger = logging.getLogger(__name__)


class AISkillClassifier:
    """
    Shared AI classification helper for skills.

    Provides:
    - Intent classification (is this message requesting X?)
    - Entity extraction (extract agent name, date, etc.)
    - Multiple model support (gemini, gpt, claude)
    - Error handling and fallback
    """

    def __init__(self):
        """Initialize the AI classifier"""
        # AIClient instances created per request (different models)

    async def classify_intent(
        self,
        message: str,
        skill_name: str,
        skill_description: str,
        model: Optional[str] = None,
        custom_examples: Optional[Dict[str, List[str]]] = None,
        db = None
    ) -> bool:
        """
        Classify if a message matches a skill's intent.

        Args:
            message: User message to classify
            skill_name: Name of the skill (e.g., "Agent Switcher")
            skill_description: What the skill does
            model: AI model to use for classification (uses system config if None)
            custom_examples: Optional custom YES/NO examples for classification
            db: Database session for loading API keys (Phase 7.4) and system config (Phase 17)

        Returns:
            True if message matches skill intent, False otherwise

        Example:
            classifier = AISkillClassifier()
            is_match = await classifier.classify_intent(
                message="I want to talk to another agent",
                skill_name="Agent Switcher",
                skill_description="Switches the user's default agent for DM conversations",
                db=db_session  # Uses system AI config
            )
            # is_match = True
        """
        try:
            # Phase 17: Use system AI config if model not explicitly specified
            if model is None and db is not None:
                provider, model = get_system_ai_config(db)
                logger.debug(f"Using system AI config: provider={provider}, model={model}")
            elif model is None:
                model = DEFAULT_SYSTEM_AI_MODEL
                logger.debug(f"No db provided, using default model: {model}")

            # Build classification prompt with explicit examples for better accuracy
            # Use custom examples if provided, otherwise use default Agent Switcher examples
            if custom_examples:
                yes_examples = custom_examples.get('yes', [])
                no_examples = custom_examples.get('no', [])
                yes_text = "\n".join([f"- {ex}" for ex in yes_examples])
                no_text = "\n".join([f"- {ex}" for ex in no_examples])

                system_prompt = f"""You are a message intent classifier for a skill system.

Skill: {skill_name}
Purpose: {skill_description}

Your task: Determine if messages are requesting what this skill does.

EXAMPLES of YES (matches this skill):
{yes_text}

EXAMPLES of NO (does NOT match this skill):
{no_text}

Be flexible with:
- Filler words ("e", "então", "por favor", "please")
- Audio transcription artifacts
- Informal language and word order variations

Answer with ONLY "YES" or "NO" (no explanation)."""
            else:
                # Default examples for Agent Switcher
                system_prompt = f"""You are a message intent classifier for a skill system.

Skill: {skill_name}
Purpose: {skill_description}

Your task: Determine if the user is requesting to PERMANENTLY CHANGE/SWITCH their default agent.

IMPORTANT: Focus on PERMANENT REASSIGNMENT, not temporary conversations.

EXAMPLES of YES (agent switch requests):
- "Switch to agent Assistant"
- "Invocar agente Tsushin"
- "Mudar para agente Agendador"
- "Change my default agent to X"
- "e invocar a gente Assistant" (audio: filler word + switch command)
- "Trocar para agente X"
- "I want to switch agents"
- "Mudar meu agente para X"

EXAMPLES of NO (NOT agent switch requests):
- "Can you connect me with X?" (asking for help, not switching)
- "I want to talk to X" (temporary question for X)
- "Tell agent X about this" (forwarding a message)
- "What can agent X do?" (asking about capabilities)

Be flexible with:
- Filler words ("e", "então", "por favor", "please")
- Audio transcription artifacts ("a gente" vs "agente")
- Informal language and word order variations

Answer with ONLY "YES" or "NO" (no explanation)."""

            user_prompt = f"""Message: "{message}"

Question: Is this message requesting what this skill does?

Answer (YES or NO):"""

            # Call AI with small, fast model
            provider, model_name = self._parse_model(model)

            # Create AIClient instance for this request (Phase 7.4: pass db for API key loading)
            ai_client = AIClient(provider=provider, model_name=model_name, db=db)

            # Log the prompts for debugging
            logger.debug(f"AI Classification - System: {system_prompt[:100]}...")
            logger.debug(f"AI Classification - User: {user_prompt}")

            response_dict = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=user_prompt
            )

            # Extract answer from response
            answer = response_dict.get("answer", "").strip().upper()
            raw_response = response_dict.get("answer", "")  # Keep raw for logging
            error = response_dict.get("error")
            result = "YES" in answer

            # Detailed logging
            if error:
                logger.error(f"AI Classification error: {error}")

            logger.info(
                f"AI Intent Classification: skill={skill_name}, "
                f"message='{message[:50]}...', raw_answer='{raw_response}', result={result}, model={model}"
            )

            # Log token usage if available
            token_usage = response_dict.get("token_usage")
            if token_usage:
                logger.debug(f"AI Classification token usage: {token_usage}")

            return result

        except Exception as e:
            logger.error(
                f"Error in AI intent classification for {skill_name}: {e}",
                exc_info=True
            )
            # Fallback: return False (don't trigger skill on error)
            return False

    async def extract_entity(
        self,
        message: str,
        entity_type: str,
        available_options: Optional[List[str]] = None,
        model: Optional[str] = None,
        db = None
    ) -> Optional[str]:
        """
        Extract a specific entity from a message.

        Args:
            message: User message
            entity_type: Type of entity to extract (e.g., "agent name", "date", "time")
            available_options: List of valid options (for validation)
            model: AI model to use (uses system config if None)
            db: Database session for loading API keys (Phase 7.4) and system config (Phase 17)

        Returns:
            Extracted entity or None if not found

        Example:
            entity = await classifier.extract_entity(
                message="Switch to agent Assistant please",
                entity_type="agent name",
                available_options=["Assistant", "Tsushin", "Scheduler"],
                db=db_session  # Uses system AI config
            )
            # entity = "Assistant"
        """
        try:
            # Phase 17: Use system AI config if model not explicitly specified
            if model is None and db is not None:
                provider, model = get_system_ai_config(db)
                logger.debug(f"Entity extraction using system AI config: provider={provider}, model={model}")
            elif model is None:
                model = DEFAULT_SYSTEM_AI_MODEL
                logger.debug(f"No db provided, using default model: {model}")

            # Build extraction prompt
            options_text = ""
            if available_options:
                options_text = f"\nValid options: {', '.join(available_options)}"

            system_prompt = f"""You are an entity extractor. Extract specific information from messages.

Your task: Extract the {entity_type} from user messages.
- Respond with ONLY the {entity_type} (no explanation)
- If not found, respond: NONE
- Match against valid options if provided"""

            user_prompt = f"""Message: "{message}"{options_text}

Extract the {entity_type}:"""

            # Call AI
            provider, model_name = self._parse_model(model)

            # Create AIClient instance for this request (Phase 7.4: pass db for API key loading)
            ai_client = AIClient(provider=provider, model_name=model_name, db=db)

            response_dict = await ai_client.generate(
                system_prompt=system_prompt,
                user_message=user_prompt
            )

            # Extract entity from response
            entity = response_dict.get("answer", "").strip()
            error = response_dict.get("error")

            # Log errors
            if error:
                logger.error(f"Entity extraction error: {error}")

            # Log raw response for debugging
            logger.debug(f"Entity extraction raw response: '{entity}'")

            # Check if entity is valid
            if entity.upper() == "NONE":
                logger.info(f"Entity extraction: {entity_type} not found in '{message[:50]}...'")
                return None

            # Validate against options if provided
            if available_options:
                # Case-insensitive match
                for option in available_options:
                    if option.lower() == entity.lower():
                        logger.info(
                            f"Entity extraction: {entity_type}='{option}' from '{message[:50]}...'"
                        )
                        return option

                # No exact match - log warning but return extracted value
                logger.warning(
                    f"Entity extraction: '{entity}' not in valid options {available_options}"
                )
                return entity

            logger.info(f"Entity extraction: {entity_type}='{entity}' from '{message[:50]}...'")
            return entity

        except Exception as e:
            logger.error(
                f"Error in entity extraction ({entity_type}): {e}",
                exc_info=True
            )
            return None

    def _parse_model(self, model: str) -> tuple[str, str]:
        """
        Parse model string into provider and model name.

        Phase 7.5: Enhanced to support Ollama models.

        Args:
            model: Model identifier (e.g., "gemini-2.5-flash", "gpt-3.5-turbo", "gemma2:4b")

        Returns:
            Tuple of (provider, model_name)

        Example:
            provider, model_name = _parse_model("gemini-2.5-flash")
            # provider = "gemini", model_name = "gemini-2.5-flash"

            provider, model_name = _parse_model("gemma2:4b")
            # provider = "ollama", model_name = "gemma2:4b"
        """
        # Map model prefixes to providers
        if model.startswith("gemini"):
            return ("gemini", model)
        elif model.startswith("gpt"):
            return ("openai", model)
        elif model.startswith("claude"):
            return ("anthropic", model)
        elif ":" in model or model.lower().startswith(("llama", "gemma", "mistral", "deepseek")):
            # Phase 7.5: Ollama models typically have format "model:tag" (e.g., "gemma2:4b")
            # Or are common Ollama model names (case-insensitive check)
            return ("ollama", model)
        else:
            # Default to gemini for unknown models
            logger.warning(f"Unknown model '{model}', defaulting to gemini-2.5-flash")
            return ("gemini", "gemini-2.5-flash")


# Global singleton instance
_classifier: Optional[AISkillClassifier] = None


def get_classifier() -> AISkillClassifier:
    """
    Get the global AISkillClassifier instance (singleton pattern).

    Returns:
        AISkillClassifier instance
    """
    global _classifier
    if _classifier is None:
        _classifier = AISkillClassifier()
    return _classifier
