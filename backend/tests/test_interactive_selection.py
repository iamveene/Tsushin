"""
Tests for deterministic interactive menu selection.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.interactive_selection import choose_interactive_option


def _build_list_message(options):
    return json.dumps({
        "type": "list",
        "sections": [
            {
                "title": "Menu",
                "rows": [
                    {"id": str(index + 1), "title": option}
                    for index, option in enumerate(options)
                ]
            }
        ]
    })


def test_selects_tracking_number_when_present():
    message = _build_list_message([
        "888030510077193",
        "Outro número"
    ])
    objective = "Código de rastreio: 888030510077193"

    selection = choose_interactive_option(message, objective)

    assert selection == "888030510077193"


def test_selects_outro_when_tracking_missing():
    message = _build_list_message([
        "888030510077193",
        "Outro número"
    ])
    objective = "Código de rastreio: 888030565349400"

    selection = choose_interactive_option(message, objective)

    assert selection == "Outro número"


def test_returns_none_for_non_interactive_payload():
    selection = choose_interactive_option("Olá, tudo bem?", "Código de rastreio: 888030565349400")

    assert selection is None


def test_selects_keyword_match_when_no_tracking_or_outro():
    message = _build_list_message([
        "Consultar pedido",
        "Falar com atendente"
    ])
    objective = "Objetivo: Verificar o status logístico da encomenda."

    selection = choose_interactive_option(message, objective)

    assert selection == "Consultar pedido"


def test_selects_alternative_on_repeat_menu():
    message = _build_list_message([
        "Consultar pedido",
        "Falar com atendente"
    ])
    objective = "Objetivo: Verificar o status logístico da encomenda."

    selection = choose_interactive_option(message, objective, last_selection="Consultar pedido")

    assert selection == "Falar com atendente"
