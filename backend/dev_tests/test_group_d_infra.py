"""
Group D regression guard — infra / install / observability bug sprint.

Exercises the pure-Python bits of the Group D fixes so we can confirm future
regressions without needing to spin up a Docker stack:

- BUG-649 / BUG-650: Ollama container manager reopens its SQLAlchemy session
  around long-running health waits AND sanitizes error text before persisting.
- BUG-651: TTSInstanceService.mark_pending_auto_provision flips the flags
  before the background worker fires.
- BUG-652: VectorStoreInstanceService.SUPPORTED_VENDORS includes chroma.
- BUG-653: install.py's self-signed Caddyfile generator drops default_sni for
  IP-literal binds but keeps it for real hostnames.
- BUG-654: docker-compose.yml declares TSN_AUTH_RATE_LIMIT exactly once.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

# Backend package path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.ollama_container_manager import (  # noqa: E402
    _sanitize_health_reason,
    OllamaContainerManager,
)
from services.vector_store_instance_service import (  # noqa: E402
    SUPPORTED_VENDORS as VS_SUPPORTED_VENDORS,
)


ROOT = Path(__file__).resolve().parents[2]
INSTALL_PY = ROOT / "install.py"
COMPOSE_YML = ROOT / "docker-compose.yml"

# These tests introspect repo-root files which are not mounted into the backend
# container. Skip them transparently there so the in-container test loop still
# exercises the Python-level fixes; the host-side pytest run still guards
# install.py / docker-compose.yml changes.
_REPO_ROOT_AVAILABLE = INSTALL_PY.exists() and COMPOSE_YML.exists()
skip_if_no_repo_root = pytest.mark.skipif(
    not _REPO_ROOT_AVAILABLE,
    reason="Repo-root files not mounted (e.g. running inside backend container)",
)


# ------------------------------------------------------------- BUG-650 sanitize

def test_bug650_sanitize_strips_sql_and_container_ids():
    raw = (
        "Failed to run docker 7a9f2b1c8d3e4f5a6b7c8d9e0f1a2b3c: "
        "IntegrityError (psycopg2.errors.ForeignKeyViolation) [SQL: INSERT INTO "
        "provider_instance (container_id) VALUES ('deadbeefcafe0123')] "
        "(Background on this error at: https://sqlalche.me/e/20/gkpj)"
    )
    cleaned = _sanitize_health_reason(raw)
    # No raw hex container IDs
    assert not re.search(r"\b[a-f0-9]{12,}\b", cleaned), cleaned
    # No SQL / background noise
    assert "[SQL:" not in cleaned
    assert "Background on this error" not in cleaned
    assert "psycopg2" not in cleaned
    # Still under the column limit (500)
    assert len(cleaned) <= 500


def test_bug650_sanitize_preserves_short_messages():
    raw = "Port 6700 already in use on host"
    assert _sanitize_health_reason(raw) == "Port 6700 already in use on host"


def test_bug650_sanitize_handles_empty():
    assert _sanitize_health_reason("") == ""
    assert _sanitize_health_reason(None) == ""  # type: ignore[arg-type]


# ------------------------------------------------------------- BUG-649 wait helper

def test_bug649_wait_for_health_detached_handles_none_base_url():
    """The detached wait accepts raw base_url without a live instance."""
    mgr = OllamaContainerManager.__new__(OllamaContainerManager)  # skip __init__
    assert mgr._wait_for_health_detached(None) is False
    assert mgr._wait_for_health_detached("") is False


# ------------------------------------------------------------- BUG-652 vendors

def test_bug652_chroma_is_supported_vendor():
    assert "chroma" in VS_SUPPORTED_VENDORS
    # Must still list the real external vendors.
    assert {"mongodb", "pinecone", "qdrant"}.issubset(VS_SUPPORTED_VENDORS)


# ------------------------------------------------------------- BUG-653 caddy

@skip_if_no_repo_root
def test_bug653_install_py_drops_default_sni_for_ip_bind():
    """The self-signed branch should omit `default_sni` entirely for IPs."""
    src = INSTALL_PY.read_text()
    # Locate the selfsigned block
    marker = "elif ssl_mode == 'selfsigned':"
    assert marker in src
    idx = src.index(marker)
    # Look at the ~40 lines that follow — the IP branch should set
    # global_block = "" (empty) rather than `default_sni localhost`.
    snippet = src[idx:idx + 1500]
    assert "global_block = \"\"" in snippet, (
        "BUG-653: selfsigned branch must emit empty global_block for IP binds"
    )
    # The broken behaviour was EMITTING `default_sni localhost` in the
    # generated Caddyfile content — catch that specific code path, not the
    # explanatory comment text.
    assert "default_sni localhost\\n" not in snippet, (
        "BUG-653: the generated Caddyfile must not hard-code "
        "`default_sni localhost` for IP-literal binds"
    )
    assert "'localhost' if self._is_ip" not in snippet, (
        "BUG-653: the IP->localhost SNI fallback must be gone"
    )


# ------------------------------------------------------------- BUG-654 compose

@skip_if_no_repo_root
def test_bug654_single_tsn_auth_rate_limit_in_compose():
    content = COMPOSE_YML.read_text()
    matches = re.findall(r"^\s*-\s*TSN_AUTH_RATE_LIMIT=", content, re.MULTILINE)
    assert len(matches) == 1, (
        f"BUG-654: expected exactly 1 TSN_AUTH_RATE_LIMIT declaration, "
        f"found {len(matches)}"
    )


# ------------------------------------------------------------- BUG-651 tts

def test_bug651_tts_mark_pending_auto_provision_exists():
    """The service must expose mark_pending_auto_provision so the route can
    flip is_auto_provisioned=True BEFORE returning the 202 response."""
    from services.tts_instance_service import TTSInstanceService
    assert hasattr(TTSInstanceService, "mark_pending_auto_provision")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
