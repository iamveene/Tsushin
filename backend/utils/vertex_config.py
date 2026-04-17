"""Vertex AI credential normalisation.

Accepts user input in multiple formats (raw PEM + split extra_config, OR full
service-account JSON pasted as the api_key value) and returns the canonical
four-tuple the rest of the backend expects. Keeps the error message honest
about what fields/shapes are actually accepted.
"""

from __future__ import annotations

import json
from typing import Tuple


VERTEX_CONFIG_ERROR = (
    "Vertex AI requires project_id, sa_email (or service_account_email), and "
    "private_key. Paste the full service-account JSON into the api_key field, "
    "or provide the PEM private key in api_key plus project_id/region/sa_email "
    "in extra_config."
)


def normalise_vertex_config(
    api_key: str | None,
    extra_config: dict | None,
) -> Tuple[str, str, str, str]:
    """Return (project_id, region, sa_email, private_key) for Vertex AI.

    api_key may be either:
      - a raw PEM private-key string, OR
      - a full service-account JSON blob (pasted as-is from the Google console).

    extra_config may carry keys:
      - project_id
      - region  (or the Google-native alias `location`)
      - sa_email  (or the Google-native alias `service_account_email`)

    Values pulled from a parsed JSON api_key take precedence over extra_config
    for the three SA-intrinsic fields (project_id, client_email, private_key).
    Region never comes from the JSON — it's a deployment choice, not a property
    of the service account.
    """
    raw_api_key = (api_key or "").strip()
    private_key = raw_api_key
    sa_email_from_json: str | None = None
    project_id_from_json: str | None = None

    if raw_api_key.startswith("{"):
        try:
            sa_json = json.loads(raw_api_key)
        except (json.JSONDecodeError, TypeError):
            sa_json = None
        if isinstance(sa_json, dict):
            private_key = (sa_json.get("private_key") or "").strip()
            sa_email_from_json = sa_json.get("client_email") or None
            project_id_from_json = sa_json.get("project_id") or None

    ec = extra_config or {}
    project_id = project_id_from_json or ec.get("project_id") or ""
    region = ec.get("region") or ec.get("location") or "us-east5"
    sa_email = (
        sa_email_from_json
        or ec.get("sa_email")
        or ec.get("service_account_email")
        or ""
    )

    return project_id, region, sa_email, private_key
