"""Tenant-scoped browser session profile helpers.

Browser automation profiles let UI-authored flows reuse an authenticated
storage state for portals that block fresh scripted logins with CAPTCHA.
The profile is still explicit in the Flow editor: browser steps point at a
named profile instead of hiding login/session behavior inside a custom runner.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import BrowserAutomationIntegration, HubIntegration
from services.encryption_key_service import get_api_key_encryption_key


class BrowserSessionProfileError(RuntimeError):
    """Raised for user-actionable browser session profile failures."""


_PROFILE_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def normalize_profile_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = _PROFILE_RE.sub("-", str(value).strip()).strip("-._")
    return normalized[:120] or None


def get_browser_session_encryptor(db: Session) -> TokenEncryption:
    master_key = get_api_key_encryption_key(db)
    if not master_key:
        raise BrowserSessionProfileError("missing_browser_session_encryption_key")
    return TokenEncryption(master_key.encode())


def _identifier(tenant_id: str) -> str:
    return f"{tenant_id}:browser_session_profile"


def encrypt_storage_state(db: Session, tenant_id: str, storage_state: Dict[str, Any]) -> str:
    return get_browser_session_encryptor(db).encrypt(
        json.dumps(storage_state, ensure_ascii=False),
        _identifier(tenant_id),
    )


def decrypt_storage_state(db: Session, tenant_id: str, encrypted: Optional[str]) -> Optional[Dict[str, Any]]:
    if not encrypted:
        return None
    raw = get_browser_session_encryptor(db).decrypt(encrypted, _identifier(tenant_id))
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise BrowserSessionProfileError("invalid_storage_state")
    return parsed


def parse_storage_state(raw: Any) -> Dict[str, Any]:
    if raw is None or raw == "":
        raise BrowserSessionProfileError("storage_state_required")
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, dict):
        raise BrowserSessionProfileError("storage_state_must_be_object")
    cookies = parsed.get("cookies", [])
    origins = parsed.get("origins", [])
    if cookies is None:
        cookies = []
    if origins is None:
        origins = []
    if not isinstance(cookies, list) or not isinstance(origins, list):
        raise BrowserSessionProfileError("storage_state_has_invalid_shape")
    parsed["cookies"] = cookies
    parsed["origins"] = origins
    return parsed


def summarize_storage_state(storage_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not storage_state:
        return {"cookie_count": 0, "origin_count": 0, "domains": []}
    cookies = storage_state.get("cookies") if isinstance(storage_state, dict) else []
    origins = storage_state.get("origins") if isinstance(storage_state, dict) else []
    domains = sorted({
        str(cookie.get("domain") or "").lstrip(".")
        for cookie in (cookies or [])
        if isinstance(cookie, dict) and cookie.get("domain")
    })
    return {
        "cookie_count": len(cookies or []),
        "origin_count": len(origins or []),
        "domains": domains[:12],
    }


def storage_state_summary_json(storage_state: Optional[Dict[str, Any]]) -> str:
    return json.dumps(summarize_storage_state(storage_state), ensure_ascii=False)


def load_profile_storage_state(
    db: Session,
    tenant_id: str,
    *,
    integration_id: Optional[int] = None,
    profile_name: Optional[str] = None,
    require_active: bool = True,
) -> tuple[Optional[BrowserAutomationIntegration], Optional[Dict[str, Any]]]:
    """Load and decrypt a tenant-owned browser session profile."""

    query = (
        db.query(BrowserAutomationIntegration)
        .join(HubIntegration, HubIntegration.id == BrowserAutomationIntegration.id)
        .filter(HubIntegration.tenant_id == tenant_id)
        .filter(HubIntegration.type == "browser_automation")
    )
    if require_active:
        query = query.filter(HubIntegration.is_active == True)  # noqa: E712
    if integration_id is not None:
        query = query.filter(BrowserAutomationIntegration.id == integration_id)
    else:
        normalized = normalize_profile_name(profile_name)
        if not normalized:
            return None, None
        query = query.filter(BrowserAutomationIntegration.session_profile_name == normalized)

    integration = query.order_by(BrowserAutomationIntegration.id.desc()).first()
    if not integration:
        return None, None

    state = decrypt_storage_state(db, tenant_id, integration.storage_state_encrypted)
    return integration, state


def apply_storage_state(
    db: Session,
    integration: BrowserAutomationIntegration,
    tenant_id: str,
    storage_state: Dict[str, Any],
) -> None:
    parsed = parse_storage_state(storage_state)
    integration.storage_state_encrypted = encrypt_storage_state(db, tenant_id, parsed)
    integration.storage_state_imported_at = datetime.utcnow()
    integration.storage_state_summary_json = storage_state_summary_json(parsed)
