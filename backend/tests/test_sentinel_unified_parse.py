"""
V060-SEC-001: Regression tests for SentinelService._parse_unified_response.

Guards against the stale-docstring bug where only a subset of DETECTION_REGISTRY
threat types were accepted by hand. Parser now dynamically validates against
`list(DETECTION_REGISTRY.keys())`, so every registered detection type must
round-trip through _parse_unified_response as a real threat.

The parametrized cases iterate DETECTION_REGISTRY dynamically — do NOT hard-code
the list; that's exactly the regression we're guarding against.
"""

import json
import logging
import os
import sys

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sentinel_detections import DETECTION_REGISTRY
from services.sentinel_effective_config import SentinelEffectiveConfig
from services.sentinel_service import SentinelService


@pytest.fixture
def sentinel():
    """Construct SentinelService with a mocked DB session (parse path never touches DB)."""
    db = MagicMock()
    return SentinelService(db=db, tenant_id="test-tenant-parse")


@pytest.fixture
def block_config():
    """Effective config in block mode — threats should produce action='blocked'."""
    return SentinelEffectiveConfig(detection_mode="block")


def _llm_payload(threat_type: str, score: float, reason: str = "unit-test"):
    """Build the LLM-return shape consumed by _parse_unified_response."""
    return {
        "answer": json.dumps({
            "threat_type": threat_type,
            "score": score,
            "reason": reason,
        })
    }


# =============================================================================
# One case per DETECTION_REGISTRY key — dynamic, NOT hard-coded.
# =============================================================================


@pytest.mark.parametrize("threat_key", sorted(DETECTION_REGISTRY.keys()))
def test_every_registered_threat_type_round_trips(
    sentinel, block_config, threat_key
):
    """Every key in DETECTION_REGISTRY must be accepted as a valid threat type."""
    payload = _llm_payload(threat_key, score=0.9)

    result = sentinel._parse_unified_response(
        llm_result=payload,
        analysis_type="prompt",
        config=block_config,
        response_time_ms=10,
    )

    assert result.detection_type == threat_key, (
        f"Expected detection_type={threat_key!r} (from DETECTION_REGISTRY), "
        f"got {result.detection_type!r}. "
        f"Parser likely has a stale hard-coded allowlist."
    )
    assert result.is_threat_detected is True
    assert result.action == "blocked"
    assert result.threat_score == 0.9


# =============================================================================
# "none" case — no threat detected.
# =============================================================================


def test_none_threat_type_is_allowed(sentinel, block_config):
    """threat_type='none' with low score must produce is_threat_detected=False."""
    payload = _llm_payload("none", score=0.1)

    result = sentinel._parse_unified_response(
        llm_result=payload,
        analysis_type="prompt",
        config=block_config,
        response_time_ms=5,
    )

    assert result.is_threat_detected is False
    assert result.detection_type == "none"
    assert result.action == "allowed"


# =============================================================================
# Invalid threat_type — downgraded to "none", warning logged.
# =============================================================================


def test_invalid_threat_type_downgraded_to_none(sentinel, block_config, caplog):
    """Unknown threat_type must be coerced to 'none' and log a warning."""
    payload = _llm_payload("definitely_not_real", score=0.9)

    with caplog.at_level(logging.WARNING, logger="services.sentinel_service"):
        result = sentinel._parse_unified_response(
            llm_result=payload,
            analysis_type="prompt",
            config=block_config,
            response_time_ms=7,
        )

    assert result.detection_type == "none"
    assert result.is_threat_detected is False
    assert result.action == "allowed"
    assert "Invalid threat_type" in caplog.text
