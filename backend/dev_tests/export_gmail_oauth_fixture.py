#!/usr/bin/env python3
"""
Export a real Gmail OAuth fixture from the live database.

This is intentionally strict: it refuses to write a fixture unless the chosen
integration has both gmail.readonly and gmail.send scopes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy import text


REPO_BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = REPO_BACKEND.parent
if str(REPO_BACKEND) not in sys.path:
    sys.path.insert(0, str(REPO_BACKEND))

from hub.security import TokenEncryption  # noqa: E402


REQUIRED_SCOPES = {
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
}


def _load_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _get_database_url(env_values: dict[str, str]) -> str:
    explicit = os.getenv("DATABASE_URL") or env_values.get("DATABASE_URL")
    if explicit:
        return explicit

    password = os.getenv("POSTGRES_PASSWORD") or env_values.get("POSTGRES_PASSWORD")
    if not password:
        raise SystemExit("DATABASE_URL is not set and POSTGRES_PASSWORD was not found in .env.")

    user = os.getenv("POSTGRES_USER") or env_values.get("POSTGRES_USER") or "tsushin"
    host = os.getenv("POSTGRES_HOST") or env_values.get("POSTGRES_HOST") or "localhost"
    port = os.getenv("POSTGRES_PORT") or env_values.get("POSTGRES_PORT") or "5432"
    db_name = os.getenv("POSTGRES_DB") or env_values.get("POSTGRES_DB") or "tsushin"
    return f"postgresql://{user}:{quote_plus(password)}@{host}:{port}/{db_name}"


def _get_google_key(env_values: dict[str, str]) -> str:
    explicit = os.getenv("GOOGLE_ENCRYPTION_KEY") or env_values.get("GOOGLE_ENCRYPTION_KEY")
    if explicit:
        return explicit
    raise SystemExit("GOOGLE_ENCRYPTION_KEY is not set in the environment or .env.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--integration-id", type=int, required=True, help="GmailIntegration.id to export")
    parser.add_argument(
        "--output",
        default=str(REPO_BACKEND / "tests" / "fixtures" / "gmail_oauth.enc"),
        help="Encrypted fixture output path",
    )
    parser.add_argument(
        "--key-env",
        default="TSN_GMAIL_FIXTURE_KEY",
        help="Environment variable containing the Fernet fixture key",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_values = _load_env_file()
    fixture_key = os.getenv(args.key_env)
    if not fixture_key:
        raise SystemExit(
            f"{args.key_env} is not set. Provide a Fernet key to encrypt the Gmail fixture."
        )

    engine = create_engine(_get_database_url(env_values))
    with engine.connect() as conn:
        integration = conn.execute(
            text(
                """
                SELECT hi.id, hi.tenant_id, gi.email_address
                FROM hub_integration hi
                JOIN gmail_integration gi ON gi.id = hi.id
                WHERE hi.id = :integration_id
                """
            ),
            {"integration_id": args.integration_id},
        ).mappings().first()
        if not integration:
            raise SystemExit(f"Gmail integration {args.integration_id} was not found.")

        token = conn.execute(
            text(
                """
                SELECT refresh_token_encrypted, scope
                FROM oauth_token
                WHERE integration_id = :integration_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"integration_id": args.integration_id},
        ).mappings().first()
        if not token:
            raise SystemExit(f"No OAuth token found for Gmail integration {args.integration_id}.")

        scopes = set((token["scope"] or "").split())
        missing = REQUIRED_SCOPES - scopes
        if missing:
            raise SystemExit(
                "Refusing to export fixture because the selected integration is missing "
                f"required scopes: {sorted(missing)}"
            )

        credentials = conn.execute(
            text(
                """
                SELECT client_id, client_secret_encrypted
                FROM google_oauth_credentials
                WHERE tenant_id = :tenant_id
                LIMIT 1
                """
            ),
            {"tenant_id": integration["tenant_id"]},
        ).mappings().first()
        if not credentials:
            raise SystemExit(
                f"No Google OAuth credentials configured for tenant {integration['tenant_id']}."
            )

    token_encryption = TokenEncryption(_get_google_key(env_values).encode("utf-8"))
    client_secret = token_encryption.decrypt(
        credentials["client_secret_encrypted"],
        integration["tenant_id"],
    )
    refresh_token = token_encryption.decrypt(
        token["refresh_token_encrypted"],
        integration["email_address"],
    )

    if not client_secret:
        raise SystemExit("Failed to decrypt the Google OAuth client secret.")
    if not refresh_token:
        raise SystemExit("Failed to decrypt the Gmail refresh token.")

    payload = {
        "integration_id": integration["id"],
        "tenant_id": integration["tenant_id"],
        "email": integration["email_address"],
        "client_id": credentials["client_id"],
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "scopes": sorted(scopes),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(
        Fernet(fixture_key.encode("utf-8")).encrypt(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        )
    )
    print(f"Exported Gmail OAuth fixture for integration {integration['id']} -> {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
