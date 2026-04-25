"""
BUG-706 regression: FOLLOWUP_PATTERNS must catch common EN interrogatives
("what was the IP?", "where did you find it?", etc.) so the agent can re-use
prior structured tool DATA instead of re-firing the same tool.

Existing PT/ES patterns must keep matching too — we don't want to regress
multilingual follow-up detection.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.followup_detector import (
    FOLLOWUP_PATTERNS,
    is_followup_to_prior_skill,
)


HISTORY_WITH_TOOL = [
    {"role": "user", "content": "scan example.com"},
    {
        "role": "assistant",
        "content": "Found the IP.",
        "tool_result": {
            "skill_type": "nmap",
            "operation": "quick_scan",
            "data": {"ip": "93.184.216.34"},
        },
    },
]


@pytest.mark.parametrize(
    "message",
    [
        # English interrogatives — the BUG-706 reproducer + sibling phrasings
        "what was the IP address you found?",
        "What did you discover?",
        "which one was the most relevant?",
        "Which target had the open ports?",
        "who owns that IP?",
        "where did you find it?",
        "Where was that data from?",
        "when was it last seen?",
        "why did the scan fail on the second host?",
        "how many ports were open?",
        # Pronoun phrasings
        "give me that one again",
        "the first one looks suspicious",
        "the previous one please",
        # Existing English patterns (regression safety)
        "Which of these is most important?",
        "compare those for me",
        # Portuguese / Spanish patterns must still match (regression safety)
        "qual desses é mais importante?",
        "resume isso",
        "entre eles, qual parece urgente?",
        "o que voce encontrou?",
        "esse aqui é o melhor?",
    ],
)
def test_followup_detector_catches_followup_phrasings(message):
    """All these messages should map back to the prior tool's skill_type."""
    assert is_followup_to_prior_skill(message, HISTORY_WITH_TOOL) == "nmap"


@pytest.mark.parametrize(
    "message",
    [
        # Fresh-fetch wording must still win over follow-up wording
        "show me the latest scan",
        "scan it again with fresh data",
        "buscar de novo",
        "novos resultados por favor",
        # Plain unrelated text — no follow-up signal at all
        "hello there",
        "tell me a joke",
    ],
)
def test_followup_detector_does_not_match_fresh_or_unrelated(message):
    assert is_followup_to_prior_skill(message, HISTORY_WITH_TOOL) is None


def test_followup_patterns_include_new_en_interrogatives():
    """Exact regex coverage check — guards against accidental rollback."""
    joined = "\n".join(FOLLOWUP_PATTERNS)
    for token in ("what", "which", "who", "where", "when", "how"):
        assert token in joined, f"FOLLOWUP_PATTERNS must include EN '{token}'"
    # Pronoun phrasings
    assert "that one" in joined
    assert "most recent" in joined
