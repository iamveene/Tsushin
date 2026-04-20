"""
Sentinel Heuristic / Regex Floor
================================

Provider-independent pattern-matching layer that runs BEFORE the LLM
classifier. It catches well-known attack phrasings (BUG-643, BUG-656)
even when no LLM provider API key is configured, and acts as a strict
floor when the LLM classifier under-detects at level 1 (BUG-643) or
regresses at level 3 (BUG-644).

Design goals
------------
* Deterministic. No model call, no I/O, no I/O-side-effects.
* Conservative on benign content. Patterns must be phrased so that
  casual questions ("what is a prompt injection?", "remember I prefer
  dark mode") do not trip them.
* Superset safety. Level-N patterns are strict supersets of level-(N-1)
  patterns. A level-1 block remains a level-3 block.
* Shared with fact-extractor. ``is_untrusted_user_injection`` is used
  by the memory fact extractor to refuse to promote adversarial user
  content into persistent instructions (BUG-642, BUG-661).

The matcher does NOT attempt to classify non-attack prompts; it only
returns a match when a high-confidence attack marker is present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Pattern table
# ---------------------------------------------------------------------------
#
# Each entry is:
#   (detection_type, min_level, score, reason, compiled_regex)
#
# ``min_level`` is the lowest Sentinel aggressiveness level at which this
# pattern should fire when Sentinel is in block/warn_only/detect_only mode.
# ``level = 0`` (disabled) never fires heuristics.
# ``level >= 1`` fires patterns marked min_level=1.
# ``level >= 2`` also fires min_level=2, etc.
#
# NOTE: Keep patterns short and phrasing-specific.  We deliberately match
# imperative / declarative forms ("ignore previous instructions", "you
# are now DAN") and NOT interrogative forms ("what does prompt injection
# mean?"), so legitimate conversation doesn't trip the floor.


_PATTERNS: List[Tuple[str, int, float, str, re.Pattern]] = [
    # --- prompt_injection ---------------------------------------------------
    (
        "prompt_injection",
        1,
        0.95,
        "Attempt to override prior instructions (classic prompt-injection opener).",
        re.compile(
            r"\b("
            r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
            r"(instructions?|prompts?|rules?|directives?|messages?)"
            r"|disregard\s+(all\s+)?(previous|prior|above|earlier)\s+"
            r"(instructions?|prompts?|rules?)"
            r"|forget\s+(all\s+)?(your|the)\s+(previous|prior|system)\s+"
            r"(instructions?|prompts?|rules?)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_injection",
        1,
        0.9,
        "Attempt to extract the system prompt verbatim.",
        re.compile(
            r"\b("
            r"(reveal|print|show|output|dump|display|repeat)\s+"
            r"(me\s+)?(your\s+|the\s+)?(system|initial|hidden|secret)\s+"
            r"(prompt|instructions?|rules?|directives?)"
            r"|what\s+is\s+your\s+(system|initial|hidden)\s+prompt"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    # Portuguese variants
    (
        "prompt_injection",
        1,
        0.9,
        "Tentativa de sobrescrever instruções anteriores (pt-BR).",
        re.compile(
            r"\b("
            r"ignore\s+(todas?\s+)?(as\s+)?(instru[cç][õo]es?|regras?)\s+"
            r"(anteriores|pr[eé]vias|acima)"
            r"|esque[cç]a\s+(as\s+|suas\s+)?(instru[cç][õo]es|regras)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    # --- agent_takeover -----------------------------------------------------
    (
        "agent_takeover",
        1,
        0.95,
        "Persona-override attempt (e.g. 'you are now DAN' / 'act as an unrestricted AI').",
        re.compile(
            r"\b("
            r"you\s+are\s+now\s+(a\s+|an\s+)?(?!(?:ready|online|connected|done)\b)"
            r"[a-z0-9_\-\s]{0,40}?"
            r"(dan|unrestricted|jailbroken|uncensored|overlord|evil|admin|developer|god|root)"
            # "From now on you are <persona>" / "From now on, you will …"
            r"|from\s+now\s+on[,\s]+you\s+(are|will|must|shall|should)\b"
            r"[^.\n]{0,80}?"
            r"(dan|unrestricted|jailbroken|uncensored|overlord|evil|admin|"
            r"developer|god|root|obey|ignore|bypass|"
            r"(?:not\s+)?obey\s+me|"
            r"will\s+obey|"
            r"a\s+different|another\s+ai)"
            r"|pretend\s+(to\s+be|you\s+are)\s+(an?\s+)?(different|unrestricted|jailbroken|uncensored)"
            r"|act\s+as\s+(dan|an?\s+unrestricted|an?\s+uncensored|an?\s+evil|an?\s+overlord)"
            r"|roleplay\s+as\s+(dan|an?\s+unrestricted|an?\s+uncensored)"
            r")",
            re.IGNORECASE,
        ),
    ),
    (
        "agent_takeover",
        1,
        0.9,
        "Jailbreak persona marker (DAN / do-anything-now).",
        re.compile(
            r"\b("
            r"do\s+anything\s+now"
            r"|stay\s+in\s+character\s+as\s+dan"
            r"|developer\s+mode\s+(enabled|activated|on)"
            r")\b",
            re.IGNORECASE,
        ),
    ),
    # --- agent_escalation ---------------------------------------------------
    (
        "agent_escalation",
        2,
        0.85,
        "Inter-agent delegation intended to bypass security controls.",
        re.compile(
            r"\b("
            r"delegate\s+(this\s+)?to\s+(another|a\s+different)\s+agent\b"
            r"[^.\n]{0,60}\b(bypass|ignore|skip|disable|escalate)\b"
            r"|have\s+(another|a\s+different)\s+agent\s+"
            r"(bypass|ignore|skip|disable|escalate)"
            r"|ask\s+(another|the\s+admin|a\s+privileged)\s+agent\s+to\s+"
            r"(bypass|ignore|reveal|leak)"
            r")",
            re.IGNORECASE,
        ),
    ),
    # --- memory_poisoning ---------------------------------------------------
    (
        "memory_poisoning",
        1,
        0.95,
        "Attempt to plant persistent malicious override into memory.",
        re.compile(
            r"\b("
            r"remember\s+(this\s+)?(permanently|forever|always)"
            r"[^.\n]{0,80}\b(override|bypass|ignore|jailbreak|uncensored|unrestricted|disable\s+(sentinel|filter|security))"
            r"|memori[sz]e\s+(this\s+)?(permanently|forever|always)"
            r"[^.\n]{0,80}\b(override|bypass|ignore|jailbreak|uncensored|unrestricted)"
            r"|store\s+(this\s+)?(as\s+)?(a\s+)?(permanent|high\s*-?\s*priority|persistent)"
            r"[^.\n]{0,80}\b(override|rule|directive|instruction)"
            r")",
            re.IGNORECASE,
        ),
    ),
    (
        "memory_poisoning",
        1,
        0.9,
        "Persistent behaviour-poisoning prefix marker.",
        re.compile(
            r"("
            r"\balways\s+start\s+(every|each|all)\s+(future\s+)?(reply|response|message)\s+with\s+"
            r"[A-Z0-9_\-]{3,}"
            r"|\bprepend\s+[\"']?[A-Z0-9_\-]{3,}[\"']?\s+to\s+(every|each|all)\s+"
            r"(future\s+)?(reply|response)"
            # "treat (this|it|the following|that|<marker>) as higher priority than …"
            r"|\btreat\s+(this|it|that|the\s+following|[a-z0-9_\-]+)\s+as\s+"
            r"higher\s+priority\s+than\s+"
            r"(any\s+)?(system|developer|administrator|admin|tenant)\s*"
            r"(or\s+[a-z]+\s+)?(instructions?|prompts?|rules?)"
            # "Remember this permanently" + any explicit persistence marker
            r"|\bremember\s+(this\s+)?permanently\b[^.\n]{0,160}?"
            r"\b(override|bypass|ignore|jailbreak|uncensored|unrestricted|"
            r"higher\s+priority|always\s+(say|start|respond|reply)|"
            r"disable\s+(sentinel|filter|security))"
            r")",
            re.IGNORECASE,
        ),
    ),
    (
        "memory_poisoning",
        1,
        0.9,
        "Credential-style fact poisoning (admin/root/api-key injection).",
        re.compile(
            r"\b("
            r"(embed|store|save|remember)[^.\n]{0,40}\b"
            r"(admin\s+password|root\s+password|master\s+key|api[\s_-]*key|secret[\s_-]*key|access[\s_-]*token)"
            r"[^.\n]{0,40}\bis\b"
            r"|the\s+(admin|root|master)\s+password\s+is\b"
            r")",
            re.IGNORECASE,
        ),
    ),
    # --- vector_store_poisoning ---------------------------------------------
    (
        "vector_store_poisoning",
        2,
        0.85,
        "Instruction-bearing document aimed at the vector store / knowledge base.",
        re.compile(
            r"\b("
            r"(inject|embed|insert)\s+(this\s+)?(instruction|rule|directive|override)\s+"
            r"into\s+(the\s+)?(vector\s+store|knowledge\s+base|kb|rag|embeddings?)"
            r"|poison\s+(the\s+)?(vector\s+store|knowledge\s+base|embeddings?)"
            r")",
            re.IGNORECASE,
        ),
    ),
    # --- shell_malicious ----------------------------------------------------
    (
        "shell_malicious",
        1,
        0.98,
        "Destructive shell command ('rm -rf /' and variants).",
        re.compile(
            r"(?<![a-z0-9_/])rm\s+(-[rfRF]+\s+)+/\s*(\*|\.|$|['\"\s])",
            re.IGNORECASE,
        ),
    ),
    (
        "shell_malicious",
        1,
        0.95,
        "Reverse shell / pipe-to-shell pattern.",
        re.compile(
            r"("
            r"(curl|wget)\s+[^\|\n]{1,120}\|\s*(sh|bash|zsh|python|perl)\b"
            r"|bash\s+-i\s+>&\s*/dev/tcp/"
            r"|nc\s+-l(vp|p|v)?\s+\d+\s+-e\s+/bin/(sh|bash)"
            r")",
            re.IGNORECASE,
        ),
    ),
    # --- browser_ssrf -------------------------------------------------------
    (
        "browser_ssrf",
        1,
        0.9,
        "Browser navigation aimed at internal / metadata endpoint.",
        re.compile(
            r"("
            # "navigate to http://169.254.169.254/..." and variants
            r"\b(navigate|browse|fetch|go|open|browser_navigate|browser_goto|browser_open)"
            r"(\s+to)?\s+"
            r"(https?://)?(169\.254\.169\.254|localhost|127\.0\.0\.1|0\.0\.0\.0|"
            r"metadata\.google|host\.docker\.internal|kubernetes\.default|\[::1\])"
            # Bare "http://169.254.169.254" anywhere counts (cloud metadata)
            r"|https?://169\.254\.169\.254"
            r"|https?://metadata\.google"
            r")",
            re.IGNORECASE,
        ),
    ),
]


# Quick lookup used by the fact extractor (BUG-642): any pattern at
# min_level <= 1 on these detection types marks user content as
# "instruction-like and untrusted". We deliberately don't include
# browser/shell detections here — those are about tool misuse rather
# than instruction-injection.
_INSTRUCTION_LIKE_FAMILIES = {
    "prompt_injection",
    "agent_takeover",
    "agent_escalation",
    "memory_poisoning",
    "vector_store_poisoning",
}


@dataclass
class HeuristicMatch:
    """A single heuristic pattern that matched the content."""

    detection_type: str
    score: float
    reason: str
    matched_text: str
    pattern_level: int  # minimum aggressiveness level at which this fires


def match_heuristics(
    content: str,
    aggressiveness_level: int,
    enabled_detection_types: Optional[Iterable[str]] = None,
) -> List[HeuristicMatch]:
    """
    Evaluate the heuristic layer against the given content.

    Parameters
    ----------
    content:
        The user-visible text to evaluate. Truncate before calling.
    aggressiveness_level:
        Sentinel aggressiveness (0-3). 0 disables the heuristic layer.
    enabled_detection_types:
        Optional iterable of detection types currently enabled on the
        effective Sentinel profile. If provided, heuristics whose
        detection type is disabled are skipped so behaviour stays
        consistent with LLM-classifier-level overrides.

    Returns
    -------
    List of HeuristicMatch, possibly empty. The list is sorted by
    descending score so the caller can pick the first entry as the
    primary verdict.
    """

    if aggressiveness_level <= 0 or not content:
        return []

    enabled_set = set(enabled_detection_types) if enabled_detection_types else None

    matches: List[HeuristicMatch] = []
    for detection_type, min_level, score, reason, regex in _PATTERNS:
        if aggressiveness_level < min_level:
            continue
        if enabled_set is not None and detection_type not in enabled_set:
            continue
        m = regex.search(content)
        if m:
            matched = m.group(0)
            # Keep match short for logging so large content doesn't
            # leak full payloads into audit logs.
            if len(matched) > 180:
                matched = matched[:177] + "..."
            matches.append(
                HeuristicMatch(
                    detection_type=detection_type,
                    score=score,
                    reason=reason,
                    matched_text=matched,
                    pattern_level=min_level,
                )
            )

    matches.sort(key=lambda x: x.score, reverse=True)
    return matches


def evaluate_content(
    content: str,
    aggressiveness_level: int,
    enabled_detection_types: Optional[Iterable[str]] = None,
) -> Optional[HeuristicMatch]:
    """Return the highest-confidence heuristic match, or None if clean."""
    matches = match_heuristics(
        content, aggressiveness_level, enabled_detection_types
    )
    return matches[0] if matches else None


def is_untrusted_user_injection(content: str) -> Optional[HeuristicMatch]:
    """
    Fact-extractor guard (BUG-642, BUG-661).

    Called on *user*-role content before the fact extractor is
    allowed to promote anything to persistent structured facts. Returns
    the first instruction-like heuristic match, or None if the content
    shows no sign of being an instruction-injection / persona-override /
    memory-poisoning attempt.

    We run at aggressiveness_level=3 so this guard is deliberately more
    conservative than the runtime Sentinel profile — a user message that
    Sentinel's profile chose not to block may still be refused as a
    *source of persistent instructions*, because the fact extractor is
    a separate trust boundary from the assistant reply path.
    """
    if not content:
        return None
    matches = match_heuristics(content, aggressiveness_level=3)
    for m in matches:
        if m.detection_type in _INSTRUCTION_LIKE_FAMILIES:
            return m
    return None
