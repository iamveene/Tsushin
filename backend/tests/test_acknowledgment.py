"""
Tests for status acknowledgment detection.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.acknowledgment import should_acknowledge_status


def test_acknowledge_status_with_date():
    message = (
        "sua entrega está em trânsito, sua entrega está prevista para ocorrer até 2026-01-22 23:59:59."
    )
    assert should_acknowledge_status(message) is True


def test_do_not_acknowledge_request_for_input():
    message = "Por favor, me informe novamente os 15 ou 18 dígitos do seu número de rastreio."
    assert should_acknowledge_status(message) is False


def test_do_not_acknowledge_without_date():
    message = "sua entrega está em trânsito."
    assert should_acknowledge_status(message) is False
