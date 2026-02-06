"""
Tests for session reset detection helpers.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.session_reset import should_attempt_session_reset, reset_message_for_attempt


def test_detects_mid_conversation_prompt():
    message = "Há mais algo que eu possa fazer por você?"
    assert should_attempt_session_reset(message) is True


def test_detects_service_evaluation_prompt():
    message = "Avaliação do serviço - Obrigada por ligar para J&T EXPRESS."
    assert should_attempt_session_reset(message) is True


def test_ignores_normal_message():
    message = "OK! Por favor, me informe seu número de rastreio."
    assert should_attempt_session_reset(message) is False


def test_reset_message_sequence():
    assert reset_message_for_attempt(0) == "menu"
    assert reset_message_for_attempt(1) == "0"
