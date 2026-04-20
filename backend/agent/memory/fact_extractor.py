"""
Fact Extractor - Phase 4.8 Week 3

Automatically extracts structured facts from conversations using AI.
Identifies user preferences, personal information, and other learnable facts.

Key features:
- AI-powered fact extraction from conversation context
- Confidence scoring based on statement clarity and repetition
- Topic categorization (preferences, personal_info, history, etc.)
- Incremental learning (updates existing facts with new information)

BUG-642 / BUG-661 — Untrusted-content guard
-------------------------------------------
User-role conversation turns are *data*, not instructions. Before the
LLM extractor sees them we run a provider-independent heuristic check
(``agent.sentinel.heuristics.is_untrusted_user_injection``) and:

1. Strip the offending user turn from the conversation before
   extraction runs, so the LLM never sees "IGNORE PREVIOUS INSTRUCTIONS
   / you are now DAN / embed admin password as a permanent fact" as
   guidance it should act on.
2. After extraction, drop any fact that could only be produced by such
   a turn (``instructions`` topic without a trusted origin, or a value
   that itself matches an injection marker).

This is a separate trust boundary from Sentinel's inline block: even
when Sentinel is configured in detect_only mode or misses a payload,
the fact extractor refuses to promote it to persistent high-confidence
``instructions``.
"""

import logging
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from json_repair import repair_json

try:
    # Provider-independent regex floor shared with Sentinel.
    from agent.sentinel.heuristics import is_untrusted_user_injection
except Exception:  # pragma: no cover — best-effort import
    is_untrusted_user_injection = None  # type: ignore


# Roles that may legitimately emit instructions-topic facts.
# User content is ALWAYS untrusted for this purpose — the agent must
# never confuse "things the user typed" with "directives the agent
# should follow persistently".
_TRUSTED_INSTRUCTION_ROLES = {"assistant", "system"}


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

    def __init__(
        self,
        ai_client=None,
        provider: str = None,
        model_name: str = None,
        db=None,
        token_tracker=None,
        tenant_id: str = None,
        provider_instance_id: int = None,
    ):
        """
        Initialize fact extractor.

        Args:
            ai_client: AI client for fact extraction (optional, will be lazy-loaded)
            provider: AI provider to use (REQUIRED: should be agent's model_provider)
            model_name: Model name to use (REQUIRED: should be agent's model_name)
            db: Database session for loading API keys (optional)
            token_tracker: TokenTracker for LLM cost monitoring (Phase 0.6.0)
        """
        self.logger = logging.getLogger(__name__)
        self.ai_client = ai_client
        self.token_tracker = token_tracker

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
        self.tenant_id = tenant_id
        self.provider_instance_id = provider_instance_id

    def _get_ai_client(self):
        """Lazy load AI client if not provided."""
        if self.ai_client is None:
            from agent.ai_client import AIClient
            # Use configured provider/model (or default to fast, cheap model for fact extraction)
            self.ai_client = AIClient(
                provider=self.provider,
                model_name=self.model_name,
                db=self.db,
                token_tracker=self.token_tracker,
                tenant_id=self.tenant_id,
                provider_instance_id=self.provider_instance_id,
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

        # BUG-642 / BUG-661: Strip user turns that look like instruction
        # injection / persona override / memory-poisoning before the LLM
        # extractor sees them. The returned flag is True iff the
        # conversation contains at least one assistant/system turn
        # (a "trusted non-user origin"); we use it below to refuse
        # persistent `instructions`-topic facts when the only content
        # comes from user role turns.
        sanitized_conversation, had_trusted_non_user_turn, dropped_count = (
            self._sanitize_conversation_for_extraction(conversation)
        )

        if dropped_count:
            self.logger.warning(
                "Fact extractor: dropped %d untrusted user turn(s) "
                "before LLM extraction (BUG-642 guard)",
                dropped_count,
            )

        # Bail early if the sanitizer removed every substantive turn —
        # no point in asking the LLM to extract from an empty
        # conversation, and we definitely don't want it to hallucinate
        # instructions facts from silence.
        if not sanitized_conversation:
            self.logger.info(
                "Fact extractor: no trusted content left after sanitizer; "
                "skipping extraction"
            )
            return []

        try:
            # Format conversation for prompt
            conv_text = self._format_conversation(sanitized_conversation)

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

            # BUG-642 / BUG-661: Post-filter facts. Even after sanitizing
            # the conversation, belt-and-braces — refuse any fact whose
            # `value` or `context` still contains an injection marker,
            # and refuse `instructions`-topic facts when the conversation
            # had no trusted (assistant/system) turns that could have
            # legitimately produced one.
            facts = self._filter_untrusted_facts(
                facts,
                had_trusted_non_user_turn=had_trusted_non_user_turn,
            )

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

    @staticmethod
    def _looks_like_injection(text: str) -> bool:
        """Return True if the text matches an instruction-injection marker."""
        if not text or is_untrusted_user_injection is None:
            return False
        try:
            return is_untrusted_user_injection(text) is not None
        except Exception:
            return False

    def _sanitize_conversation_for_extraction(
        self, conversation: List[Dict]
    ) -> Tuple[List[Dict], bool, int]:
        """
        BUG-642 / BUG-661: Drop user turns that look like instruction
        injection / persona override / memory-poisoning.

        Returns (sanitized_conversation, had_trusted_non_injection_turn,
        dropped_count).

        ``had_trusted_non_injection_turn`` is True when at least one
        assistant/system turn is present (indicating the conversation is
        a real exchange and not just a stream of injected user content).
        The caller uses this to refuse emitting ``instructions``-topic
        facts when no trusted origin exists.
        """
        sanitized: List[Dict] = []
        had_trusted = False
        dropped = 0

        for msg in conversation:
            role = str(msg.get("role", "")).lower()
            content = msg.get("content", "") or ""

            if role in _TRUSTED_INSTRUCTION_ROLES:
                had_trusted = True
                sanitized.append(msg)
                continue

            if role == "user" and self._looks_like_injection(content):
                # Drop this user turn entirely. We considered redacting
                # its content to "[redacted-for-safety]" but that can
                # itself be interpreted by the LLM as an instruction;
                # removing the turn is safer.
                dropped += 1
                continue

            sanitized.append(msg)

        return sanitized, had_trusted, dropped

    def _filter_untrusted_facts(
        self, facts: List[Dict], had_trusted_non_user_turn: bool
    ) -> List[Dict]:
        """
        BUG-642 / BUG-661: Post-extraction filter.

        * Drop any fact whose ``value`` or ``context`` itself looks like
          an instruction-injection marker — the LLM occasionally echoes
          sanitized content back from the sanitized transcript via the
          ``context`` field, and we must not persist it.
        * Drop any ``instructions``-topic fact when the conversation
          lacked a trusted (assistant/system) origin. User text alone
          can never produce a persistent ``instructions`` fact.
        * Downgrade surviving ``instructions`` facts to confidence
          capped at 0.9 so they stay below the "near-certain" bar that
          was letting adversarial overrides lock in at 0.95–0.98.
        """
        if not facts:
            return facts

        kept: List[Dict] = []
        for fact in facts:
            topic = str(fact.get("topic", "")).lower()
            value = str(fact.get("value", ""))
            context = str(fact.get("context", ""))

            if self._looks_like_injection(value) or self._looks_like_injection(context):
                self.logger.warning(
                    "Fact extractor: dropped fact with injection-like content "
                    "(topic=%s key=%s)",
                    topic,
                    fact.get("key"),
                )
                continue

            if topic == "instructions" and not had_trusted_non_user_turn:
                self.logger.warning(
                    "Fact extractor: dropped `instructions` fact "
                    "(key=%s) — no trusted (assistant/system) origin in "
                    "conversation; user content alone cannot produce "
                    "persistent instructions (BUG-642 guard)",
                    fact.get("key"),
                )
                continue

            if topic == "instructions":
                try:
                    fact["confidence"] = min(float(fact.get("confidence", 0.0)), 0.9)
                except (TypeError, ValueError):
                    fact["confidence"] = 0.9

            kept.append(fact)

        return kept

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
