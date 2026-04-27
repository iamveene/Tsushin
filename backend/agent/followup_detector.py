"""Detect follow-ups that should reuse prior structured skill results."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional


FOLLOWUP_PATTERNS = [
    r"\b(this|that|these|those|it|them|which|qual|quais|isso|esses|essas|eles|elas|deles|delas)\b",
    r"\b(of these|from those|among them|qual desses|quais desses|entre eles|entre esses)\b",
    r"\b(more important|mais importante|best|melhor|priorit|resum|summari[sz]e|compare|comparar)\b",
    r"\b(the first|the second|o primeiro|a primeira|o segundo|a segunda|último|ultimo|last one)\b",
    # BUG-706: EN interrogatives — common in follow-ups like "what was the IP?",
    # "where did you find it?", "when was it last seen?", "how many were there?".
    # PT/ES equivalents are also covered so multilingual follow-ups still match.
    r"\b(what|which|who|whom|whose|where|when|why|how)\b",
    r"\b(o que|que|quem|onde|quando|porque|por que|por quê|como|qual\s+(?:foi|era|é))\b",
    # Pronoun phrasings and demonstrative referencing
    r"\b(that one|this one|these ones|those ones|the one (?:that|which|with)|the one you)\b",
    r"\b(the (?:first|second|third|fourth|fifth|last|latest|previous|earlier|recent|most recent) one)\b",
    r"\b(esse|essa|esta|este|aquele|aquela|aquilo|o\s+que\s+você|o\s+que\s+voce)\b",
]

FRESH_FETCH_PATTERNS = [
    r"\b(new|fresh|latest|recent|unread|refresh|reload|fetch again|search again)\b",
    r"\b(novos?|novas?|recentes?|atualiz|recarreg|buscar de novo|pesquisar de novo)\b",
    r"\b(emails?\s+novos?|novos?\s+emails?|mensagens?\s+novas?)\b",
]


def _iter_tool_results(history: Iterable[Dict[str, Any]]) -> Iterable[Dict[str, Any]]:
    for msg in reversed(list(history or [])):
        if not isinstance(msg, dict):
            continue
        tool_result = msg.get("tool_result")
        if isinstance(tool_result, dict):
            yield tool_result
            continue
        metadata = msg.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("tool_result"), dict):
            yield metadata["tool_result"]


def is_fresh_fetch_request(message: str) -> bool:
    """Return True when the user appears to ask for newly fetched data."""
    text = (message or "").lower()
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in FRESH_FETCH_PATTERNS)


def is_followup_to_prior_skill(
    message: str,
    history: List[Dict[str, Any]],
) -> Optional[str]:
    """
    Return the prior skill_type when a message appears to refer to stored data.

    Fresh-fetch wording intentionally wins over pronoun/reference wording so
    "emails novos" and "latest emails" can call the tool again.
    """
    if not message or not history or is_fresh_fetch_request(message):
        return None

    text = message.lower()
    has_followup_language = any(
        re.search(pattern, text, re.IGNORECASE) for pattern in FOLLOWUP_PATTERNS
    )
    if not has_followup_language:
        return None

    for tool_result in _iter_tool_results(history):
        skill_type = tool_result.get("skill_type")
        if isinstance(skill_type, str) and skill_type:
            return skill_type
    return None


def truncate_json_bytes(value: Any, max_bytes: int) -> Any:
    """Return a JSON-safe value whose serialized form fits roughly in max_bytes."""
    try:
        encoded = json.dumps(value, ensure_ascii=False)
    except TypeError:
        encoded = json.dumps(str(value), ensure_ascii=False)

    if len(encoded.encode("utf-8")) <= max_bytes:
        return value

    if isinstance(value, dict):
        truncated = dict(value)
        data = truncated.get("data")
        if isinstance(data, dict):
            truncated_data = dict(data)
            for key, item in list(truncated_data.items()):
                if isinstance(item, list) and item:
                    trimmed = []
                    for element in item:
                        candidate = dict(truncated)
                        candidate_data = dict(truncated_data)
                        candidate_data[key] = trimmed + [element]
                        candidate["data"] = candidate_data
                        if len(json.dumps(candidate, ensure_ascii=False).encode("utf-8")) > max_bytes:
                            break
                        trimmed.append(element)
                    truncated_data[key] = trimmed
            truncated["data"] = truncated_data
            if len(json.dumps(truncated, ensure_ascii=False).encode("utf-8")) <= max_bytes:
                return truncated

    suffix = '", "_truncated": true}'
    raw = encoded.encode("utf-8")[: max(0, max_bytes - len(suffix.encode("utf-8")))]
    text = raw.decode("utf-8", errors="ignore")
    return {"summary": text, "_truncated": True}


def build_data_block(tool_results: List[Dict[str, Any]], max_bytes: int) -> str:
    """Format structured tool results as a prompt DATA block."""
    bounded = [truncate_json_bytes(result, max_bytes) for result in tool_results]
    return "DATA:\n" + json.dumps(bounded, ensure_ascii=False, indent=2)
