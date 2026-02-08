"""
MemGuard Service — Memory Poisoning Detection

Two-layer defense against memory poisoning attacks:

Layer A (Pre-storage): Fast regex pattern matching on incoming messages.
    - High confidence (>0.7): Block immediately without LLM call
    - Medium confidence (0.3-0.7): Escalate to LLM for nuanced analysis
    - Low confidence (<0.3): Allow through

Layer B (Fact validation): Validates extracted facts before SemanticKnowledge storage.
    - Blocks facts with credential-like values
    - Blocks instruction-topic facts with command patterns
    - Flags contradictions against established high-confidence facts

Both layers are fail-open: errors allow content through.
Bilingual patterns: English + Portuguese.
"""

import re
import hashlib
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class MemGuardResult:
    """Result from Layer A pre-storage analysis."""
    is_poisoning: bool
    score: float
    reason: str
    blocked: bool
    escalated_to_llm: bool = False


@dataclass
class FactValidationResult:
    """Result from Layer B fact validation."""
    is_valid: bool
    reason: str = ""


# --- Layer A: Pattern Definitions ---

# Instruction planting patterns (EN + PT)
INSTRUCTION_PLANTING_PATTERNS = [
    # English
    r"(?:remember|memorize|store|save|keep)\s+(?:that|this|the following)\s*[:.]?\s*(?:when|if|always|never)",
    r"(?:remember|memorize)\s+(?:that|this)\s*[:.]?\s*(?:you\s+(?:are|should|must|will))",
    r"(?:from\s+now\s+on|going\s+forward|henceforth)\s*[,.]?\s*(?:always|never|you\s+(?:must|should|will))",
    r"(?:always|never)\s+(?:respond|reply|answer|say)\s+(?:with|that|in)",
    r"when\s+(?:i|someone|anyone)\s+(?:say|ask|type|send)s?\s+['\"]?.+['\"]?\s*,?\s*(?:respond|reply|answer|say)",
    # Portuguese
    r"(?:lembre|memorize|guarde|salve|anote)\s+(?:que|isso|o\s+seguinte)",
    r"(?:a\s+partir\s+de\s+agora|daqui\s+(?:em|pra)\s+(?:diante|frente))",
    r"(?:sempre|nunca)\s+(?:responda|diga|fale|mencione)",
    r"quando\s+(?:eu|algu[eé]m)\s+(?:perguntar|falar|dizer|enviar)\s+.+\s*,?\s*(?:responda|diga|fale)",
]

# Credential/secret injection patterns (EN + PT)
CREDENTIAL_INJECTION_PATTERNS = [
    # English
    r"(?:my|the|our)\s+(?:api\s*key|password|token|secret|credential|private\s*key|access\s*key)\s+(?:is|=|:)\s*\S+",
    r"(?:remember|memorize|store|save)\s+(?:my|the|this)\s+(?:api\s*key|password|token|secret|credential)",
    r"(?:api[_\s]?key|password|token|secret|credential)[_\s]?(?:is|=|:)\s*['\"]?\S{8,}",
    # Portuguese
    r"(?:minha?|a|o)\s+(?:senha|token|chave|segredo|credencial)\s+[eé]\s*:?\s*\S+",
    r"(?:lembre|memorize|guarde|salve)\s+(?:minha?|meu|a|o)\s+(?:senha|token|chave|segredo|credencial)",
]

# Identity override patterns (EN + PT)
IDENTITY_OVERRIDE_PATTERNS = [
    # English
    r"(?:remember|memorize)\s+(?:that\s+)?(?:you\s+are|your\s+(?:name|real\s+name|true\s+(?:name|identity))\s+is)",
    r"(?:your|the)\s+(?:real|true|actual)\s+(?:name|identity|purpose)\s+is",
    r"(?:remember|memorize)\s+(?:that\s+)?(?:your\s+purpose\s+is|you\s+were\s+(?:made|created|designed)\s+to)",
    # Portuguese
    r"(?:lembre|memorize)\s+(?:que\s+)?(?:voc[eê]\s+[eé]|seu\s+(?:nome|verdadeiro\s+nome)\s+[eé])",
    r"(?:seu|o\s+seu)\s+(?:verdadeiro|real)\s+(?:nome|prop[oó]sito|objetivo)\s+[eé]",
]

# Persistent behavior change patterns (EN + PT)
PERSISTENT_BEHAVIOR_PATTERNS = [
    # English
    r"(?:never|don'?t\s+ever)\s+(?:mention|tell|reveal|disclose|share|talk\s+about)",
    r"(?:always|every\s+time)\s+(?:ignore|skip|bypass|avoid)\s+(?:security|verification|authentication|checks)",
    r"(?:whenever|every\s+time|each\s+time)\s+(?:i|someone)\s+(?:ask|say|type)",
    # Portuguese
    r"(?:nunca|jamais)\s+(?:mencione|diga|revele|fale\s+sobre|compartilhe)",
    r"(?:sempre|toda\s+vez)\s+(?:ignore|pule|evite)\s+(?:a\s+)?(?:seguran[cç]a|verifica[cç][aã]o|autentica[cç][aã]o)",
]

# Compile all patterns for efficiency
_COMPILED_PATTERNS = {
    "instruction_planting": [re.compile(p, re.IGNORECASE) for p in INSTRUCTION_PLANTING_PATTERNS],
    "credential_injection": [re.compile(p, re.IGNORECASE) for p in CREDENTIAL_INJECTION_PATTERNS],
    "identity_override": [re.compile(p, re.IGNORECASE) for p in IDENTITY_OVERRIDE_PATTERNS],
    "persistent_behavior": [re.compile(p, re.IGNORECASE) for p in PERSISTENT_BEHAVIOR_PATTERNS],
}

# Pattern category weights (credential injection is highest risk)
_CATEGORY_WEIGHTS = {
    "credential_injection": 0.85,
    "identity_override": 0.75,
    "instruction_planting": 0.70,
    "persistent_behavior": 0.65,
}

# --- Layer B: Fact Validation Patterns ---

# Credential-like values in facts
CREDENTIAL_VALUE_PATTERNS = [
    re.compile(r"(?:api[_\s]?key|password|token|secret|credential|private[_\s]?key|access[_\s]?key)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"^[A-Za-z0-9+/=_\-]{20,}$"),  # Long random strings (tokens/keys)
    re.compile(r"^(?:sk|pk|ak|Bearer|token)[_\-][A-Za-z0-9]{16,}$", re.IGNORECASE),  # Common key prefixes
    re.compile(r"(?:senha|token|chave|segredo)\s*[:=]\s*\S+", re.IGNORECASE),  # Portuguese
]

# Command-like patterns in instruction facts
INSTRUCTION_COMMAND_PATTERNS = [
    re.compile(r"(?:always|never|must|should)\s+(?:respond|reply|answer|say|do|ignore|skip|bypass|mention|reveal|tell|disclose|share)", re.IGNORECASE),
    re.compile(r"(?:don'?t|do\s+not)\s+(?:verify|check|validate|authenticate|mention|reveal)", re.IGNORECASE),
    re.compile(r"(?:when\s+.+\s+(?:say|ask|type)s?\s*,?\s*(?:respond|reply|answer))", re.IGNORECASE),
    re.compile(r"(?:sempre|nunca|deve)\s+(?:responda|diga|ignore|pule|evite|mencione|revele)", re.IGNORECASE),
]


class MemGuardService:
    """
    Memory poisoning detection and prevention service.

    Provides two protection layers:
    - Layer A: Pre-storage message analysis (pattern matching + optional LLM)
    - Layer B: Fact validation before SemanticKnowledge writes
    """

    def __init__(self, db: Session, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logging.getLogger(f"{__name__}.{tenant_id}")

    async def analyze_for_memory_poisoning(
        self,
        content: str,
        agent_id: int,
        sender_key: str,
        config,
    ) -> MemGuardResult:
        """
        Layer A: Analyze a message for memory poisoning before storage.

        Uses fast regex patterns first. Only escalates to LLM for ambiguous
        scores (0.3-0.7). High confidence matches are blocked immediately.

        Args:
            content: Message text to analyze
            agent_id: Agent receiving the message
            sender_key: Sender identifier
            config: SentinelEffectiveConfig with detection settings

        Returns:
            MemGuardResult with analysis outcome
        """
        if not content or not content.strip():
            return MemGuardResult(is_poisoning=False, score=0.0, reason="", blocked=False)

        content_lower = content.lower().strip()

        # Phase 1: Fast pattern matching
        max_score = 0.0
        matched_category = ""
        matched_reason = ""

        for category, patterns in _COMPILED_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(content_lower):
                    weight = _CATEGORY_WEIGHTS[category]
                    if weight > max_score:
                        max_score = weight
                        matched_category = category
                        matched_reason = f"Pattern match: {category.replace('_', ' ')}"
                    break  # One match per category is enough

        # Phase 2: Decision based on score
        if max_score >= 0.7:
            # High confidence — block immediately, no LLM needed
            detection_mode = getattr(config, "detection_mode", "block")
            blocked = detection_mode == "block"

            self._log_analysis(
                agent_id=agent_id,
                sender_key=sender_key,
                content=content,
                is_threat=True,
                score=max_score,
                reason=matched_reason,
                action="blocked" if blocked else "detected",
            )

            return MemGuardResult(
                is_poisoning=True,
                score=max_score,
                reason=matched_reason,
                blocked=blocked,
            )

        elif max_score >= 0.3:
            # Ambiguous — escalate to LLM for nuanced analysis
            llm_result = await self._llm_analyze(content, agent_id, config)
            if llm_result:
                return llm_result

            # LLM failed — treat pattern match as sufficient at medium confidence
            detection_mode = getattr(config, "detection_mode", "block")
            blocked = detection_mode == "block"

            self._log_analysis(
                agent_id=agent_id,
                sender_key=sender_key,
                content=content,
                is_threat=True,
                score=max_score,
                reason=f"{matched_reason} (LLM escalation failed, using pattern score)",
                action="blocked" if blocked else "detected",
            )

            return MemGuardResult(
                is_poisoning=True,
                score=max_score,
                reason=f"{matched_reason} (LLM escalation failed)",
                blocked=blocked,
                escalated_to_llm=True,
            )

        # Low score — allow
        return MemGuardResult(is_poisoning=False, score=max_score, reason="", blocked=False)

    async def _llm_analyze(
        self,
        content: str,
        agent_id: int,
        config,
    ) -> Optional[MemGuardResult]:
        """
        Escalate to LLM for nuanced memory poisoning analysis.

        Only called for ambiguous pattern scores (0.3-0.7).

        Returns:
            MemGuardResult if LLM succeeds, None if LLM fails (fail-open)
        """
        try:
            from services.sentinel_detections import get_default_prompt

            aggressiveness = getattr(config, "aggressiveness_level", 1)
            prompt_template = get_default_prompt("memory_poisoning", aggressiveness)
            if not prompt_template:
                return None

            prompt = prompt_template.format(input=content)

            # Use the same LLM config as Sentinel
            llm_provider = getattr(config, "llm_provider", "gemini")
            llm_model = getattr(config, "llm_model", "gemini-2.5-flash-lite")
            max_tokens = getattr(config, "llm_max_tokens", 256)
            temperature = getattr(config, "llm_temperature", 0.1)
            timeout = getattr(config, "timeout_seconds", 5.0)

            from services.llm_service import get_llm_response
            import json

            answer = await get_llm_response(
                prompt=prompt,
                provider=llm_provider,
                model=llm_model,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )

            if not answer:
                return None

            # Parse response
            if "```json" in answer:
                answer = answer.split("```json")[1].split("```")[0].strip()
            elif "```" in answer:
                answer = answer.split("```")[1].split("```")[0].strip()

            parsed = json.loads(answer)
            is_threat = parsed.get("threat", False)
            score = float(parsed.get("score", 0.0))
            reason = parsed.get("reason", "")

            if is_threat and score > 0.3:
                detection_mode = getattr(config, "detection_mode", "block")
                blocked = detection_mode == "block"

                return MemGuardResult(
                    is_poisoning=True,
                    score=score,
                    reason=f"LLM analysis: {reason}",
                    blocked=blocked,
                    escalated_to_llm=True,
                )

            return MemGuardResult(
                is_poisoning=False,
                score=score,
                reason="",
                blocked=False,
                escalated_to_llm=True,
            )

        except Exception as e:
            self.logger.warning(f"MemGuard LLM analysis failed (fail-open): {e}")
            return None

    def validate_fact(
        self,
        fact: Dict,
        existing_facts: List[Dict],
        agent_id: int,
        user_id: str,
    ) -> FactValidationResult:
        """
        Layer B: Validate an extracted fact before storage.

        Checks for:
        1. Credential-like values (API keys, passwords, tokens)
        2. Command-like patterns in instruction facts
        3. Contradictions against established high-confidence facts

        Args:
            fact: Extracted fact dict with topic, key, value, confidence
            existing_facts: All existing facts for this user (batch-fetched)
            agent_id: Agent ID
            user_id: User identifier

        Returns:
            FactValidationResult indicating if fact is safe to store
        """
        topic = fact.get("topic", "")
        key = fact.get("key", "")
        value = str(fact.get("value", ""))
        confidence = float(fact.get("confidence", 0.0))

        # Check 1: Credential-like values in any fact
        for pattern in CREDENTIAL_VALUE_PATTERNS:
            if pattern.search(value):
                reason = f"Credential-like value detected in fact {topic}/{key}"
                self._log_fact_block(agent_id, user_id, fact, reason)
                return FactValidationResult(is_valid=False, reason=reason)

        # Check 2: Command-like patterns in instruction facts
        if topic == "instructions":
            for pattern in INSTRUCTION_COMMAND_PATTERNS:
                if pattern.search(value):
                    reason = f"Command pattern detected in instruction fact: {key}"
                    self._log_fact_block(agent_id, user_id, fact, reason)
                    return FactValidationResult(is_valid=False, reason=reason)

        # Check 3: Contradiction detection — high-confidence overrides
        if existing_facts and confidence > 0.0:
            for existing in existing_facts:
                if (existing.get("topic") == topic and
                    existing.get("key") == key and
                    existing.get("confidence", 0.0) >= 0.8 and
                    existing.get("value") != value):
                    # High-confidence fact being overridden with different value
                    # Only block if the new fact looks suspicious
                    if self._is_suspicious_override(existing, fact):
                        reason = (
                            f"Suspicious override of established fact: "
                            f"{topic}/{key} (confidence {existing.get('confidence', 0):.1f} -> {confidence:.1f})"
                        )
                        self._log_fact_block(agent_id, user_id, fact, reason)
                        return FactValidationResult(is_valid=False, reason=reason)

        return FactValidationResult(is_valid=True)

    def _is_suspicious_override(self, existing_fact: Dict, new_fact: Dict) -> bool:
        """
        Determine if overriding an established fact is suspicious.

        Suspicious if:
        - New value contains credential patterns
        - New value contains command patterns
        - New confidence is lower than existing (possible downgrade attack)
        - Topic is 'instructions' (high-risk category)
        """
        new_value = str(new_fact.get("value", ""))
        new_confidence = float(new_fact.get("confidence", 0.0))
        existing_confidence = float(existing_fact.get("confidence", 0.0))
        topic = new_fact.get("topic", "")

        # Credential patterns in new value
        for pattern in CREDENTIAL_VALUE_PATTERNS:
            if pattern.search(new_value):
                return True

        # Command patterns in new value
        for pattern in INSTRUCTION_COMMAND_PATTERNS:
            if pattern.search(new_value):
                return True

        # Confidence downgrade on sensitive topics
        if topic == "instructions" and new_confidence < existing_confidence:
            return True

        return False

    def _log_analysis(
        self,
        agent_id: int,
        sender_key: str,
        content: str,
        is_threat: bool,
        score: float,
        reason: str,
        action: str,
    ) -> None:
        """Log a MemGuard Layer A analysis to SentinelAnalysisLog."""
        try:
            from models import SentinelAnalysisLog

            input_content = content[:500] if content else ""
            input_hash = hashlib.sha256(content.encode()).hexdigest() if content else ""

            log_entry = SentinelAnalysisLog(
                tenant_id=self.tenant_id or "system",
                agent_id=agent_id,
                analysis_type="memory",
                detection_type="memory_poisoning",
                input_content=input_content,
                input_hash=input_hash,
                is_threat_detected=is_threat,
                threat_score=score,
                threat_reason=reason,
                action_taken=action,
                sender_key=sender_key,
                detection_mode_used=action,
            )

            self.db.add(log_entry)
            self.db.commit()
        except Exception as e:
            self.logger.error(f"Failed to log MemGuard analysis: {e}")
            try:
                self.db.rollback()
            except Exception:
                pass

    def _log_fact_block(
        self,
        agent_id: int,
        user_id: str,
        fact: Dict,
        reason: str,
    ) -> None:
        """Log a MemGuard Layer B fact block to SentinelAnalysisLog."""
        try:
            from models import SentinelAnalysisLog

            fact_repr = f"[{fact.get('topic', '?')}/{fact.get('key', '?')}] = {str(fact.get('value', ''))[:200]}"
            input_hash = hashlib.sha256(fact_repr.encode()).hexdigest()

            log_entry = SentinelAnalysisLog(
                tenant_id=self.tenant_id or "system",
                agent_id=agent_id,
                analysis_type="memory",
                detection_type="memory_poisoning",
                input_content=fact_repr[:500],
                input_hash=input_hash,
                is_threat_detected=True,
                threat_score=0.9,
                threat_reason=reason,
                action_taken="blocked",
                sender_key=user_id,
                detection_mode_used="block",
            )

            self.db.add(log_entry)
            self.db.commit()
        except Exception as e:
            self.logger.error(f"Failed to log MemGuard fact block: {e}")
            try:
                self.db.rollback()
            except Exception:
                pass
