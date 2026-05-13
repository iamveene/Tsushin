import json
import os
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
GMAIL_FIXTURE_PATH = FIXTURES_DIR / "gmail_oauth.enc"


def _load_gmail_oauth_fixture() -> dict:
    fixture_key = os.getenv("TSN_GMAIL_FIXTURE_KEY")
    if not fixture_key:
        raise RuntimeError(
            "TSN_GMAIL_FIXTURE_KEY is not set; Gmail OAuth fixture validation cannot run and the Phase 0.5 gate must remain blocked."
        )

    if not GMAIL_FIXTURE_PATH.exists():
        raise FileNotFoundError(
            f"{GMAIL_FIXTURE_PATH} is missing; export a real send-scoped Gmail fixture first."
        )

    try:
        payload = Fernet(fixture_key.encode("utf-8")).decrypt(GMAIL_FIXTURE_PATH.read_bytes())
    except InvalidToken as exc:
        raise RuntimeError(
            "TSN_GMAIL_FIXTURE_KEY does not decrypt backend/tests/fixtures/gmail_oauth.enc."
        ) from exc

    data = json.loads(payload.decode("utf-8"))
    scopes = data.get("scopes", [])
    if isinstance(scopes, str):
        data["scopes"] = [scope for scope in scopes.split() if scope]
    return data


@pytest.fixture(scope="session")
def gmail_oauth_fixture() -> dict:
    return _load_gmail_oauth_fixture()
