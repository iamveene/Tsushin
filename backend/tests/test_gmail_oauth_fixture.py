import base64
import email.utils
import time
from datetime import datetime, timezone
from email.message import EmailMessage

import httpx


REQUIRED_SCOPES = {
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
}


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
