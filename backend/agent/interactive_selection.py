import json
import re
from typing import List, Optional
DEFAULT_KEYWORDS = [
    "rastreio",
    "rastreamento",
    "rastrear",
    "pedido",
    "encomenda",
    "entrega",
    "status",
    "logístico",
    "logistica",
    "consultar",
    "consulta",
]



def _load_interactive_payload(message_content: str) -> Optional[dict]:
    if not message_content:
        return None

    stripped = message_content.strip()
    if not stripped.startswith("{"):
        return None

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    return payload


def _extract_option_titles(payload: dict) -> List[str]:
    options: List[str] = []

    buttons = payload.get("buttons") or []
    for button in buttons:
        if isinstance(button, dict):
            title = button.get("title")
            if title:
                options.append(title)

    sections = payload.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue
        rows = section.get("rows") or []
        for row in rows:
            if isinstance(row, dict):
                title = row.get("title")
                if title:
                    options.append(title)

    return options


def _find_tracking_number(objective: str) -> Optional[str]:
    if not objective:
        return None

    match = re.search(r"\b\d{10,18}\b", objective)
    if not match:
        return None

    return match.group(0)


def _extract_keywords(objective: str) -> List[str]:
    keywords = list(DEFAULT_KEYWORDS)
    if not objective:
        return keywords

    tokens = re.findall(r"\b\w+\b", objective.lower())
    for token in tokens:
        if len(token) >= 4 and token not in keywords:
            keywords.append(token)

    return keywords


def _menu_signature(payload: dict, options: List[str]) -> str:
    header = payload.get("header", "")
    body = payload.get("body", "")
    footer = payload.get("footer", "")
    signature_parts = [payload.get("type", ""), header, body, footer] + options
    return "|".join(part for part in signature_parts if part)


def get_menu_signature(message_content: str) -> Optional[str]:
    payload = _load_interactive_payload(message_content)
    if not payload:
        return None

    options = _extract_option_titles(payload)
    if not options:
        return None

    return _menu_signature(payload, options)


def _rank_options(options: List[str], keywords: List[str]) -> List[str]:
    scored = []
    for option in options:
        option_lower = option.lower()
        score = sum(1 for keyword in keywords if keyword in option_lower)
        scored.append((score, option))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [option for score, option in scored if score > 0]


def choose_interactive_option(
    message_content: str,
    objective: str,
    last_selection: Optional[str] = None
) -> Optional[str]:
    payload = _load_interactive_payload(message_content)
    if not payload:
        return None

    payload_type = payload.get("type")
    if payload_type not in {"list", "buttons", "interactive"} and not (
        payload.get("sections") or payload.get("buttons")
    ):
        return None

    options = _extract_option_titles(payload)
    if not options:
        return None

    tracking_number = _find_tracking_number(objective)
    if tracking_number:
        for option in options:
            if tracking_number in option:
                return option

    fallback_pattern = re.compile(
        r"\b(outro|outra|other|none of the above|nenhum|nenhuma)\b",
        re.IGNORECASE,
    )
    fallback_option = None
    for option in options:
        if fallback_pattern.search(option):
            fallback_option = option
            break

    keywords = _extract_keywords(objective)
    ranked = _rank_options(options, keywords)

    if last_selection:
        if fallback_option and fallback_option != last_selection:
            return fallback_option
        for option in ranked:
            if option != last_selection:
                return option
        for option in options:
            if option != last_selection:
                return option

    if fallback_option:
        return fallback_option

    if ranked:
        return ranked[0]

    return None
