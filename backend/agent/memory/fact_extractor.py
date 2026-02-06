"""
Fact Extractor - Phase 4.8 Week 3

Automatically extracts structured facts from conversations using AI.
Identifies user preferences, personal information, and other learnable facts.

Key features:
- AI-powered fact extraction from conversation context
- Confidence scoring based on statement clarity and repetition
- Topic categorization (preferences, personal_info, history, etc.)
- Incremental learning (updates existing facts with new information)
"""

import logging
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from json_repair import repair_json


class FactExtractor:
    """
    Extracts structured facts from conversations using AI analysis.

    Fact Format:
    {
        "topic": "preferences" | "personal_info" | "history" | "relationships" | "goals",
        "key": "favorite_color",
        "value": "blue",
        "confidence": 0.9,
        "context": "User said they love blue"
    }
    """

    # System prompt for fact extraction
    EXTRACTION_PROMPT = """You are a fact extraction assistant. Analyze the conversation and extract structured facts about the user.

IMPORTANT: Your response MUST be ONLY a valid JSON array. Do not include any explanatory text before or after the JSON.

Extract facts in the following categories:
- preferences: likes, dislikes, favorites, hobbies
- personal_info: name, job, location, age, family
- history: past events, experiences, stories
- relationships: friends, family, colleagues mentioned
- goals: future plans, aspirations, intentions
- instructions: explicit memorization requests, keywords, responses to remember
- communication_style: slangs, frequently used words, tone preferences, formality level
- inside_jokes: recurring jokes, references, memes used by the sender
- linguistic_patterns: emoji usage, greeting style, farewell style, signature phrases

**CRITICAL - Instruction Patterns:**
When the user says things like:
- "quando eu perguntar X, responda Y" (when I ask X, respond Y)
- "memorize que X é Y" (memorize that X is Y)
- "lembre que a palavra chave de X é Y" (remember that X's keyword is Y)
- "sempre responda X quando..." (always respond X when...)

Extract these as "instructions" topic with:
- key: Subject or trigger (e.g., "keyword_alice", "response_for_X")
- value: The full instruction or response to give
- confidence: 0.95 or higher (user is explicitly instructing)

For each fact, provide:
1. topic: One of the categories above (including "instructions")
2. key: A short identifier (e.g., "favorite_food", "job", "keyword_alice")
3. value: The actual fact value or instruction
4. confidence: 0.0-1.0 based on how clear/certain the statement is
5. context: Brief quote or context from the conversation

Only extract facts that are:
- Clearly stated or strongly implied
- About the USER or explicit instructions from user
- Persistent/memorable (not temporary states like "I'm hungry")

Format your response as a JSON array of fact objects.
If no facts found, return an empty array [].

Example responses:
[
    {
        "topic": "instructions",
        "key": "keyword_alice",
        "value": "SecretWord123",
        "confidence": 0.98,
        "context": "User instructed: when I ask about Alice's keyword, reply SecretWord123"
    },
    {
        "topic": "preferences",
        "key": "favorite_color",
        "value": "blue",
        "confidence": 0.9,
        "context": "User said: I love blue, it's my favorite color"
    },
    {
        "topic": "communication_style",
        "key": "slang_cool",
        "value": "awesome",
        "confidence": 0.85,
        "context": "User consistently uses 'awesome' instead of 'cool' (observed 5 times)"
    },
    {
        "topic": "inside_jokes",
        "key": "alice_reference",
        "value": "Refers to Alice as 'our buddy' affectionately",
        "confidence": 0.9,
        "context": "User called Alice 'our buddy' multiple times in playful context"
    },
    {
        "topic": "linguistic_patterns",
        "key": "greeting_style",
        "value": "Uses casual 'e aí' or 'opa' instead of formal greetings",
        "confidence": 0.8,
        "context": "User greets with 'e aí' in most conversations"
    }
]

Conversation to analyze:
"""

    def __init__(self, ai_client=None, provider: str = None, model_name: str = None, db=None):
        """
        Initialize fact extractor.

        Args:
            ai_client: AI client for fact extraction (optional, will be lazy-loaded)
            provider: AI provider to use (REQUIRED: should be agent's model_provider)
            model_name: Model name to use (REQUIRED: should be agent's model_name)
            db: Database session for loading API keys (optional)
        """
        self.logger = logging.getLogger(__name__)
        self.ai_client = ai_client

        # Warn if using fallback instead of agent's configured LLM
        if not provider or not model_name:
            self.logger.warning(
                f"FactExtractor initialized without explicit LLM config. "
                f"Using fallback: provider={provider or 'gemini'}, model={model_name or 'gemini-2.5-flash'}. "
                f"This should be the agent's configured model_provider and model_name."
            )

        # Use provided values or fallback (with warning logged above)
        self.provider = provider if provider else "gemini"
        self.model_name = model_name if model_name else "gemini-2.5-flash"
        self.db = db

    def _get_ai_client(self):
        """Lazy load AI client if not provided."""
        if self.ai_client is None:
            from agent.ai_client import AIClient
            # Use configured provider/model (or default to fast, cheap model for fact extraction)
            self.ai_client = AIClient(
                provider=self.provider,
                model_name=self.model_name,
                db=self.db
            )
        return self.ai_client

    async def extract_facts(
        self,
        conversation: List[Dict],
        user_id: str,
        agent_id: int
    ) -> List[Dict]:
        """
        Extract facts from a conversation.

        Args:
            conversation: List of message dicts with 'role' and 'content'
            user_id: User identifier
            agent_id: Agent identifier

        Returns:
            List of extracted fact dictionaries
        """
        if not conversation:
            return []

        try:
            # Format conversation for prompt
            conv_text = self._format_conversation(conversation)

            # Build full prompt
            full_prompt = self.EXTRACTION_PROMPT + conv_text

            # Call AI to extract facts
            client = self._get_ai_client()

            # Use AIClient's generate method (system_prompt, user_message)
            # Using empty system prompt since instructions are in the user prompt
            result = await client.generate(
                system_prompt="You are a fact extraction assistant.",
                user_message=full_prompt
            )

            # Parse JSON response from result
            if result.get("error"):
                self.logger.error(f"AI generation error: {result['error']}")
                return []

            response_text = result.get("answer", "")
            facts = self._parse_extraction_response(response_text)

            # Add metadata
            for fact in facts:
                fact['user_id'] = user_id
                fact['agent_id'] = agent_id
                fact['extracted_at'] = datetime.utcnow().isoformat() + "Z"

            self.logger.info(f"Extracted {len(facts)} facts from conversation")
            return facts

        except Exception as e:
            self.logger.error(f"Fact extraction failed: {e}")
            return []

    def _format_conversation(self, conversation: List[Dict]) -> str:
        """
        Format conversation messages into readable text.

        Args:
            conversation: List of message dicts

        Returns:
            Formatted conversation string
        """
        lines = []
        for msg in conversation:
            role = msg.get('role', 'unknown').upper()
            content = msg.get('content', '')
            sender_name = msg.get('sender_name', '')

            if sender_name:
                lines.append(f"[{role} - {sender_name}]: {content}")
            else:
                lines.append(f"[{role}]: {content}")

        return "\n".join(lines)

    def _parse_extraction_response(self, response: str) -> List[Dict]:
        """
        Parse AI response into structured facts.

        Args:
            response: AI response text

        Returns:
            List of fact dictionaries
        """
        try:
            # Try to find JSON array in response
            response = response.strip()

            # Handle code blocks
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            # Try to find JSON array if it's embedded in text
            if response and not response.startswith('['):
                # Look for first '[' and last ']'
                start_idx = response.find('[')
                end_idx = response.rfind(']')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    response = response[start_idx:end_idx+1]

            # Parse JSON (with repair fallback for malformed JSON)
            try:
                facts = json.loads(response)
            except json.JSONDecodeError:
                # Try to repair malformed JSON from LLM
                self.logger.warning("Initial JSON parse failed, attempting repair...")
                repaired = repair_json(response)
                facts = json.loads(repaired)
                self.logger.info("Successfully repaired and parsed JSON")

            # Validate structure
            if not isinstance(facts, list):
                self.logger.warning("Response is not a list, wrapping in array")
                facts = [facts]

            # Validate each fact
            validated_facts = []
            for fact in facts:
                if self._validate_fact(fact):
                    validated_facts.append(fact)
                else:
                    self.logger.warning(f"Invalid fact structure: {fact}")

            return validated_facts

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON: {e}")
            self.logger.error(f"AI Response (first 500 chars): {response[:500]}")
            # Try a more lenient approach - extract JSON with regex
            try:
                import re
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    # Try to fix common JSON issues
                    json_str = json_str.replace('\n', ' ').replace('\r', '')
                    self.logger.info(f"Attempting to parse extracted JSON (first 300 chars): {json_str[:300]}...")
                    facts = json.loads(json_str)
                    if isinstance(facts, list):
                        validated_facts = [fact for fact in facts if self._validate_fact(fact)]
                        self.logger.info(f"Successfully extracted {len(validated_facts)} facts using regex fallback")
                        return validated_facts
            except Exception as fallback_error:
                self.logger.error(f"Fallback JSON extraction also failed: {fallback_error}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error parsing response: {e}")
            return []

    def _validate_fact(self, fact: Dict) -> bool:
        """
        Validate fact structure.

        Args:
            fact: Fact dictionary

        Returns:
            True if valid
        """
        required_fields = ['topic', 'key', 'value', 'confidence']

        # Check required fields
        for field in required_fields:
            if field not in fact:
                return False

        # Validate types
        if not isinstance(fact['topic'], str):
            return False
        if not isinstance(fact['key'], str):
            return False
        if not isinstance(fact['value'], str):
            return False

        # Validate confidence
        try:
            confidence = float(fact['confidence'])
            if confidence < 0.0 or confidence > 1.0:
                return False
            fact['confidence'] = confidence  # Normalize
        except (ValueError, TypeError):
            return False

        # Validate topic
        valid_topics = [
            'preferences', 'personal_info', 'history', 'relationships', 'goals',
            'instructions', 'communication_style', 'inside_jokes', 'linguistic_patterns'
        ]
        if fact['topic'] not in valid_topics:
            self.logger.warning(f"Unknown topic '{fact['topic']}', using 'personal_info'")
            fact['topic'] = 'personal_info'

        return True

    def calculate_updated_confidence(
        self,
        old_confidence: float,
        new_confidence: float,
        observation_count: int = 2
    ) -> float:
        """
        Calculate updated confidence when a fact is reinforced.

        Uses a weighted average that increases confidence with repeated observations.

        Args:
            old_confidence: Previous confidence score
            new_confidence: New observation confidence
            observation_count: Number of times this fact has been observed

        Returns:
            Updated confidence score (capped at 1.0)
        """
        # Weighted average: newer observations slightly more weight
        weight = 0.6  # Weight for new observation
        base_confidence = (1 - weight) * old_confidence + weight * new_confidence

        # Boost confidence for repeated observations
        repetition_boost = min(0.1 * (observation_count - 1), 0.2)

        final_confidence = min(base_confidence + repetition_boost, 1.0)

        return final_confidence

    def should_extract_facts(
        self,
        conversation: List[Dict],
        min_user_messages: int = 3,
        min_total_length: int = 50,
        agent_id: Optional[int] = None,
        db_session: Optional[object] = None
    ) -> bool:
        """
        Determine if conversation is substantial enough for fact extraction.

        Args:
            conversation: List of message dicts
            min_user_messages: Minimum user messages required
            min_total_length: Minimum total character count
            agent_id: Agent ID (for checking adaptive_personality skill)
            db_session: Database session (for checking adaptive_personality skill)

        Returns:
            True if extraction should be attempted
        """
        if not conversation:
            return False

        # Check for explicit instruction patterns (ALWAYS extract these)
        instruction_patterns = [
            'quando eu perguntar', 'quando perguntar', 'memorize', 'lembre',
            'palavra chave', 'password', 'codigo', 'when i ask',
            'remember that', 'memorize this', 'keyword', 'secret word'
        ]

        for msg in conversation:
            content = msg.get('content', '').lower()
            if any(pattern in content for pattern in instruction_patterns):
                self.logger.info(f"Instruction pattern detected, forcing fact extraction")
                return True

        # Phase 4.8 Week 3: Check if adaptive_personality skill is enabled
        # If enabled, lower threshold for communication pattern detection
        adaptive_personality_enabled = False
        if agent_id and db_session:
            try:
                from models import AgentSkill
                skill = db_session.query(AgentSkill).filter(
                    AgentSkill.agent_id == agent_id,
                    AgentSkill.skill_type == "adaptive_personality",
                    AgentSkill.is_enabled == True
                ).first()
                adaptive_personality_enabled = (skill is not None)
                if adaptive_personality_enabled:
                    self.logger.debug(f"Adaptive personality enabled for agent {agent_id}, lowering extraction threshold")
            except Exception as e:
                self.logger.warning(f"Could not check adaptive_personality skill: {e}")

        # Adjust thresholds if adaptive personality is enabled
        if adaptive_personality_enabled:
            # Lower threshold: extract after just 2 messages for pattern detection
            min_user_messages = min(min_user_messages, 2)
            min_total_length = min(min_total_length, 30)

        # Count user messages
        user_messages = [msg for msg in conversation if msg.get('role') == 'user']
        if len(user_messages) < min_user_messages:
            return False

        # Check total length
        total_length = sum(len(msg.get('content', '')) for msg in conversation)
        if total_length < min_total_length:
            return False

        return True

    def merge_facts(self, existing: Dict, new_fact: Dict) -> Dict:
        """
        Merge a new fact with an existing one.

        Args:
            existing: Existing fact data
            new_fact: New fact to merge

        Returns:
            Merged fact dictionary
        """
        # If values are different, prefer higher confidence
        if existing['value'] != new_fact['value']:
            if new_fact['confidence'] > existing['confidence']:
                # New fact has higher confidence, use it
                return {
                    'value': new_fact['value'],
                    'confidence': new_fact['confidence'],
                    'updated': True
                }
            else:
                # Keep existing value, slight confidence boost for reinforcement
                return {
                    'value': existing['value'],
                    'confidence': min(existing['confidence'] + 0.05, 1.0),
                    'updated': False
                }
        else:
            # Same value, boost confidence
            new_confidence = self.calculate_updated_confidence(
                existing['confidence'],
                new_fact['confidence']
            )
            return {
                'value': existing['value'],
                'confidence': new_confidence,
                'updated': True
            }
