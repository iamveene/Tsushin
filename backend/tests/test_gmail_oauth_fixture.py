import base64
import email.utils
import os
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import httpx
import pytest


# The Gmail OAuth fixture file is encrypted with TSN_GMAIL_FIXTURE_KEY (a
# Fernet key). Without the key, conftest's session-scoped ``gmail_oauth_fixture``
# raises a RuntimeError and every test in this module errors out at setup.
# In the standard backend container the key is intentionally not present, so
# skip the whole module cleanly when it is missing or the encrypted blob is
# absent — the Phase 0.5 release gate is enforced by the dedicated fixture
# CI workflow which exports the key explicitly.
_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "gmail_oauth.enc"
if not os.getenv("TSN_GMAIL_FIXTURE_KEY") or not _FIXTURE_PATH.exists():
    pytest.skip(
        "Gmail OAuth fixture not available in this environment "
        "(TSN_GMAIL_FIXTURE_KEY unset or backend/tests/fixtures/gmail_oauth.enc "
        "missing). Phase 0.5 gate runs only in the dedicated fixture CI job.",
        allow_module_level=True,
    )


REQUIRED_SCOPES = {
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
}
DRAFT_COMPATIBLE_SCOPES = {
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://mail.google.com/",
}
REQUIRE_COMPOSE_ENV = "TSN_GMAIL_REQUIRE_COMPOSE_SCOPE"


def test_gmail_oauth_fixture_compose_readiness_is_explicit(gmail_oauth_fixture):
    scopes = set(gmail_oauth_fixture["scopes"])
    has_draft_scope = bool(scopes & DRAFT_COMPATIBLE_SCOPES)
    if os.getenv(REQUIRE_COMPOSE_ENV) == "1":
        assert has_draft_scope, (
            "Gmail fixture is not Phase 3.1 draft-ready. Re-authorize with "
            "gmail.compose, gmail.modify, or mail.google.com/ before treating "
            "compose/draft live gates as green."
        )
        return

    if not has_draft_scope:
        pytest.xfail(
            "Current Gmail fixture is send-only. Set "
            f"{REQUIRE_COMPOSE_ENV}=1 after root reauthorization to enforce "
            "the Phase 3.1 compose/draft gate."
        )


def test_gmail_oauth_fixture_authenticates_lists_and_sends_email(gmail_oauth_fixture):
    scopes = set(gmail_oauth_fixture["scopes"])
    missing = REQUIRED_SCOPES - scopes
    assert not missing, f"Gmail fixture missing required scopes: {sorted(missing)}"

    token_response = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": gmail_oauth_fixture["client_id"],
            "client_secret": gmail_oauth_fixture["client_secret"],
            "refresh_token": gmail_oauth_fixture["refresh_token"],
            "grant_type": "refresh_token",
        },
        timeout=20.0,
    )
    token_response.raise_for_status()

    access_token = token_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    profile_response = httpx.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/profile",
        headers=headers,
        timeout=20.0,
    )
    profile_response.raise_for_status()
    profile = profile_response.json()
    assert profile["emailAddress"] == gmail_oauth_fixture["email"]

    list_response = httpx.get(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages",
        headers=headers,
        params={"maxResults": 1},
        timeout=20.0,
    )
    list_response.raise_for_status()
    payload = list_response.json()
    assert len(payload.get("messages", [])) >= 1, "Gmail fixture account must contain at least one message"

    subject = f"Tsushin Phase 0.5 Gmail fixture {datetime.now(timezone.utc).isoformat()}"
    message = EmailMessage()
    message["To"] = gmail_oauth_fixture["email"]
    message["From"] = gmail_oauth_fixture["email"]
    message["Subject"] = subject
    message["Date"] = email.utils.format_datetime(datetime.now(timezone.utc))
    message.set_content(
        "Automated Phase 0.5 Gmail fixture verification email.\n"
        "This proves the dedicated release gate account has gmail.send."
    )
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    send_response = httpx.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers=headers,
        json={"raw": raw_message},
        timeout=20.0,
    )
    send_response.raise_for_status()
    sent_message = send_response.json()
    assert sent_message.get("id"), "Gmail send response did not include a message id"

    search_params = {
        "q": f'in:sent subject:"{subject}"',
        "maxResults": 1,
    }
    for _ in range(10):
        sent_list_response = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers=headers,
            params=search_params,
            timeout=20.0,
        )
        sent_list_response.raise_for_status()
        sent_payload = sent_list_response.json()
        if sent_payload.get("messages"):
            break
        time.sleep(1.0)
    else:
        raise AssertionError("Sent mailbox did not show the verification email within 10 seconds")
