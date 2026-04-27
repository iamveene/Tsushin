"""Shared Jira trigger helpers."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse


def normalize_jira_site_url(value: str) -> str:
    """Return the canonical Jira Cloud site URL used for REST calls and links."""

    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("site_url must be an http(s) URL")

    path = (parsed.path or "").rstrip("/")
    if path.lower() == "/jira":
        path = ""
    if path == "/":
        path = ""

    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def jira_issue_link(site_url: str, issue_key: str | None) -> str | None:
    key = str(issue_key or "").strip()
    if not key:
        return None
    return f"{normalize_jira_site_url(site_url)}/browse/{key}"


def jira_description_to_text(value: Any, *, max_chars: int = 800) -> str:
    """Convert Jira plain text or Atlassian Document Format into a short string."""

    text = _description_text(value)
    text = " ".join(text.split())
    if len(text) > max_chars:
        return text[: max_chars - 3].rstrip() + "..."
    return text


def _description_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_description_text(item) for item in value)
    if not isinstance(value, dict):
        return str(value)

    pieces: list[str] = []
    node_text = value.get("text")
    if isinstance(node_text, str):
        pieces.append(node_text)
    for child in value.get("content") or []:
        pieces.append(_description_text(child))
    return " ".join(piece for piece in pieces if piece)
