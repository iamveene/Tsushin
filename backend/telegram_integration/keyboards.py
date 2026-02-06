"""
Telegram Inline Keyboard Builder
Phase 10.1.1
"""

from typing import List, Dict, Any
import re
import json


def build_inline_keyboard(buttons: List[List[Dict[str, Any]]]) -> Dict:
    """
    Build inline keyboard markup from button definitions.

    Example:
        buttons = [
            [{"text": "Yes", "callback_data": "confirm_yes"}],
            [{"text": "No", "callback_data": "confirm_no"}]
        ]
    """
    return {"inline_keyboard": buttons}


def build_url_button(text: str, url: str) -> Dict:
    """Build a URL button."""
    return {"text": text, "url": url}


def build_callback_button(text: str, callback_data: str) -> Dict:
    """Build a callback button."""
    return {"text": text, "callback_data": callback_data}


def parse_keyboard_from_agent_response(response: str) -> tuple:
    """
    Parse inline keyboard JSON from agent response.

    Agent can include keyboard markup in response like:
    "Here are your options: {{KEYBOARD: [[{"text": "Yes", "callback_data": "yes"}]]}}

    Returns:
        (clean_text, keyboard_markup)
    """
    pattern = r'\{\{KEYBOARD:\s*(\[.*?\])\}\}'
    match = re.search(pattern, response, re.DOTALL)

    if match:
        try:
            buttons = json.loads(match.group(1))
            clean_text = re.sub(pattern, '', response).strip()
            return clean_text, build_inline_keyboard(buttons)
        except json.JSONDecodeError:
            pass

    return response, None
