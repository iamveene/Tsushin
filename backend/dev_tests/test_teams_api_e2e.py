"""Live HTTP smoke skeleton for Agent Teams Phase 5 CRUD APIs.

This script is intentionally fixture-light: it never creates or mutates agents.
Provide existing tenant-owned agent IDs and an auth credential for the target
stack, and it will create temporary teams, exercise the expected Phase 5 HTTP
sequence, then soft-archive the teams it created.

Examples:
    TSUSHIN_BASE_URL=https://localhost \
    TSUSHIN_AUTH_COOKIE='session=...' \
    TSUSHIN_TEAM_AGENT_IDS='1,2' \
    TSUSHIN_TEAMS_API_PREFIXES='/api/teams' \
    python backend/dev_tests/test_teams_api_e2e.py

    TSUSHIN_BASE_URL=https://localhost \
    TSUSHIN_AUTH_TOKEN='...' \
    TSUSHIN_TEAM_AGENT_IDS='1,2' \
    python backend/dev_tests/test_teams_api_e2e.py

Pytest is opt-in to avoid accidental live writes:
    TSUSHIN_RUN_TEAMS_API_E2E=1 pytest -q backend/dev_tests/test_teams_api_e2e.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any

import requests


DEFAULT_PREFIXES = ("/api/teams", "/api/v1/teams")
ACTIVE_RUN_STATUSES = {"pending", "queued", "running", "in_progress", "processing", "started"}
TERMINAL_RUN_STATUSES = {
    "completed",
    "failed",
    "error",
    "timeout",
    "timed_out",
    "sentinel_blocked",
    "canceled",
    "cancelled",
}


class SmokeFailure(RuntimeError):
    """Raised for expected live-smoke failures with operator-facing context."""


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    prefixes: tuple[str, ...]
    agent_ids: tuple[str, ...]
    headers: dict[str, str]
    timeout_seconds: float
    verify_tls: bool
    run_wait_seconds: float
    skip_run: bool

    @classmethod
    def from_env_and_args(cls, argv: list[str] | None = None) -> "SmokeConfig":
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--base-url", default=os.getenv("TSUSHIN_BASE_URL", "https://localhost"))
        parser.add_argument(
            "--prefix",
            dest="prefixes",
            action="append",
            help="API prefix to smoke. Defaults to TSUSHIN_TEAMS_API_PREFIXES or both Phase 5 prefixes.",
        )
        parser.add_argument(
            "--agent-id",
            dest="agent_ids",
            action="append",
            help="Existing tenant-owned agent id to use as a temporary team member.",
        )
        parser.add_argument(
            "--timeout",
            type=float,
            default=float(os.getenv("TSUSHIN_HTTP_TIMEOUT_SECONDS", "20")),
            help="Per-request timeout in seconds.",
        )
        parser.add_argument(
            "--run-wait",
            type=float,
            default=float(os.getenv("TSUSHIN_TEAM_RUN_WAIT_SECONDS", "30")),
            help="Seconds to wait for a manual run before cleanup/cancel handling.",
        )
        parser.add_argument(
            "--verify-tls",
            action="store_true",
            default=os.getenv("TSUSHIN_VERIFY_TLS", "").lower() in {"1", "true", "yes"},
            help="Verify TLS certificates. Defaults off for localhost self-signed stacks.",
        )
        parser.add_argument(
            "--skip-run",
            action="store_true",
            default=os.getenv("TSUSHIN_SKIP_TEAM_RUN", "").lower() in {"1", "true", "yes"},
            help="Skip POST /runs when only CRUD/member smoke coverage is desired.",
        )
        args = parser.parse_args(argv)

        prefixes = tuple(_split_csv(os.getenv("TSUSHIN_TEAMS_API_PREFIXES", "")))
        if args.prefixes:
            prefixes = tuple(args.prefixes)
        if not prefixes:
            prefixes = DEFAULT_PREFIXES

        agent_ids = tuple(args.agent_ids or _split_csv(os.getenv("TSUSHIN_TEAM_AGENT_IDS", "")))
        if not agent_ids:
            raise SmokeFailure(
                "No existing team-member agents were provided. Set "
                "TSUSHIN_TEAM_AGENT_IDS='1,2' or pass --agent-id. This smoke "
                "does not create agents because that would make cleanup "
                "tenant- and model-dependent."
            )

        headers = _auth_headers_from_env()
        _validate_auth_prefix_compatibility(prefixes, headers)
        return cls(
            base_url=args.base_url.rstrip("/"),
            prefixes=tuple(_normalize_prefix(prefix) for prefix in prefixes),
            agent_ids=agent_ids,
            headers=headers,
            timeout_seconds=args.timeout,
            verify_tls=args.verify_tls,
            run_wait_seconds=args.run_wait,
            skip_run=args.skip_run,
        )


class TeamsApiSmokeClient:
    def __init__(self, config: SmokeConfig) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(config.headers)
        self.session.headers.setdefault("Content-Type", "application/json")
        if not config.verify_tls:
            requests.packages.urllib3.disable_warnings()  # type: ignore[attr-defined]

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> requests.Response:
        response = self.session.request(
            method,
            f"{self.config.base_url}{path}",
            json=payload,
            timeout=self.config.timeout_seconds,
            verify=self.config.verify_tls,
        )
        if expected and response.status_code not in expected:
            raise SmokeFailure(
                f"{method} {path} expected {expected}, got {response.status_code}: "
                f"{_response_excerpt(response)}"
            )
        return response


def run_smoke(config: SmokeConfig) -> None:
    client = TeamsApiSmokeClient(config)
    print(
        "Agent Teams Phase 5 API smoke starting: "
        f"base_url={config.base_url}, prefixes={','.join(config.prefixes)}, "
        f"agent_ids={','.join(config.agent_ids)}, skip_run={config.skip_run}"
    )
    for prefix in config.prefixes:
        _run_prefix_smoke(client, prefix)
    print("Agent Teams Phase 5 API smoke completed.")


def _run_prefix_smoke(client: TeamsApiSmokeClient, prefix: str) -> None:
    team_id: str | None = None
    run_id: str | None = None
    second_agent_added = False
    first_agent_id = client.config.agent_ids[0]
    second_agent_id = client.config.agent_ids[1] if len(client.config.agent_ids) > 1 else None

    print(f"[{prefix}] listing teams")
    client.request("GET", prefix, expected=(200,))

    try:
        team_name = f"Phase 5 API Smoke {int(time.time())}-{uuid.uuid4().hex[:8]}"
        create_payload = {
            "name": team_name,
            "description": "Temporary Agent Teams Phase 5 API smoke fixture.",
            "goal_text": "Exercise the Phase 5 CRUD API smoke path.",
            "topology": "line",
            "status": "active",
            "max_steps": 3,
            "members": [
                {
                    "agent_id": first_agent_id,
                    "role": "member",
                    "execution_order": 1,
                }
            ],
        }
        print(f"[{prefix}] creating temporary team")
        response = client.request("POST", prefix, expected=(200, 201), payload=create_payload)
        team_id = _extract_id(_json(response), "id", "team_id")
        if not team_id:
            raise SmokeFailure(f"POST {prefix} did not return a team id: {_response_excerpt(response)}")

        print(f"[{prefix}] reading team detail team_id={team_id}")
        client.request("GET", f"{prefix}/{team_id}", expected=(200,))

        print(f"[{prefix}] updating team metadata")
        client.request(
            "PUT",
            f"{prefix}/{team_id}",
            expected=(200,),
            payload={
                "name": f"{team_name} updated",
                "description": "Updated by Phase 5 API smoke.",
                "goal_text": "Confirm update semantics on a temporary team.",
                "max_steps": 4,
            },
        )

        if second_agent_id:
            print(f"[{prefix}] adding second member agent_id={second_agent_id}")
            add_response = client.request(
                "POST",
                f"{prefix}/{team_id}/members",
                expected=None,
                payload={
                    "agent_id": second_agent_id,
                    "role": "member",
                    "execution_order": 2,
                },
            )
            if add_response.status_code == 409:
                raise SmokeFailure(
                    f"POST {prefix}/{team_id}/members returned 409. Provide an "
                    "existing agent that is not already locked to another active "
                    f"team fixture. Body: {_response_excerpt(add_response)}"
                )
            if add_response.status_code not in {200, 201}:
                raise SmokeFailure(
                    f"POST {prefix}/{team_id}/members expected 200/201, got "
                    f"{add_response.status_code}: {_response_excerpt(add_response)}"
                )
            second_agent_added = True

            print(f"[{prefix}] reordering line members")
            _reorder_members(client, prefix, team_id, (first_agent_id, second_agent_id))

            print(f"[{prefix}] removing second member to verify snapshot restore path")
            client.request(
                "DELETE",
                f"{prefix}/{team_id}/members/{second_agent_id}",
                expected=(200, 204),
            )
            second_agent_added = False
        else:
            print(f"[{prefix}] one agent id supplied; member add/remove/order checks skipped")

        if client.config.skip_run:
            print(f"[{prefix}] manual run skipped by TSUSHIN_SKIP_TEAM_RUN/--skip-run")
        else:
            print(f"[{prefix}] starting manual run via background task using the team goal snapshot")
            run_response = client.request(
                "POST",
                f"{prefix}/{team_id}/runs",
                expected=(200, 201, 202),
            )
            run_id = _extract_id(_json(run_response), "run_id", "id", "team_run_id")
            print(f"[{prefix}] listing runs")
            client.request("GET", f"{prefix}/{team_id}/runs", expected=(200,))
            if run_id:
                print(f"[{prefix}] reading run detail run_id={run_id}")
                client.request("GET", f"{prefix}/{team_id}/runs/{run_id}", expected=(200,))
                _wait_for_run_to_settle(client, prefix, team_id, run_id)
            else:
                print(f"[{prefix}] run id was not returned; skipping run detail poll")
    finally:
        if team_id:
            if second_agent_added and second_agent_id:
                _best_effort_remove_member(client, prefix, team_id, second_agent_id)
            _best_effort_archive_team(client, prefix, team_id, run_id)


def _reorder_members(
    client: TeamsApiSmokeClient,
    prefix: str,
    team_id: str,
    agent_ids: tuple[str, ...],
) -> None:
    response = client.request(
        "PUT",
        f"{prefix}/{team_id}/members/order",
        expected=None,
        payload={
            "members": [
                {"agent_id": agent_id, "execution_order": index}
                for index, agent_id in enumerate(agent_ids, start=1)
            ]
        },
    )
    if response.status_code == 422:
        response = client.request(
            "PUT",
            f"{prefix}/{team_id}/members/order",
            expected=None,
            payload={"agent_ids": list(agent_ids)},
        )
    if response.status_code not in {200, 204}:
        raise SmokeFailure(
            f"PUT {prefix}/{team_id}/members/order expected 200/204, got "
            f"{response.status_code}: {_response_excerpt(response)}"
        )


def _wait_for_run_to_settle(
    client: TeamsApiSmokeClient,
    prefix: str,
    team_id: str,
    run_id: str,
) -> None:
    deadline = time.monotonic() + client.config.run_wait_seconds
    last_status: str | None = None
    while time.monotonic() < deadline:
        response = client.request("GET", f"{prefix}/{team_id}/runs/{run_id}", expected=None)
        if response.status_code != 200:
            print(
                f"[{prefix}] run poll returned {response.status_code}; cleanup will still run"
            )
            return
        status = _extract_status(_json(response))
        if status:
            last_status = status
        if status in TERMINAL_RUN_STATUSES:
            print(f"[{prefix}] run settled with status={status}")
            return
        if status and status not in ACTIVE_RUN_STATUSES:
            print(f"[{prefix}] run returned non-active status={status}")
            return
        time.sleep(1)
    print(
        f"[{prefix}] run did not settle within {client.config.run_wait_seconds:.0f}s "
        f"(last_status={last_status}); cleanup may attempt cancellation"
    )


def _best_effort_remove_member(
    client: TeamsApiSmokeClient,
    prefix: str,
    team_id: str,
    agent_id: str,
) -> None:
    response = client.request("DELETE", f"{prefix}/{team_id}/members/{agent_id}", expected=None)
    if response.status_code in {200, 204, 404}:
        print(f"[{prefix}] cleanup member removal status={response.status_code}")
        return
    print(
        f"[{prefix}] cleanup member removal failed with {response.status_code}: "
        f"{_response_excerpt(response)}"
    )


def _best_effort_archive_team(
    client: TeamsApiSmokeClient,
    prefix: str,
    team_id: str,
    run_id: str | None,
) -> None:
    response = client.request("DELETE", f"{prefix}/{team_id}", expected=None)
    if response.status_code in {200, 202, 204, 404}:
        print(f"[{prefix}] cleanup archive status={response.status_code} team_id={team_id}")
        return

    if response.status_code == 409 and run_id:
        print(f"[{prefix}] archive blocked by active run; attempting run cancel")
        cancel_response = client.request(
            "POST",
            f"{prefix}/{team_id}/runs/{run_id}/cancel",
            expected=None,
        )
        if cancel_response.status_code not in {200, 202, 204, 404, 409}:
            print(
                f"[{prefix}] cancel returned {cancel_response.status_code}: "
                f"{_response_excerpt(cancel_response)}"
            )
        _wait_for_run_to_settle(client, prefix, team_id, run_id)
        retry = client.request("DELETE", f"{prefix}/{team_id}", expected=None)
        if retry.status_code in {200, 202, 204, 404}:
            print(f"[{prefix}] cleanup archive retry status={retry.status_code} team_id={team_id}")
            return
        response = retry

    raise SmokeFailure(
        f"Cleanup could not soft-archive temporary team {team_id} through {prefix}. "
        f"Status {response.status_code}: {_response_excerpt(response)}"
    )


def _auth_headers_from_env() -> dict[str, str]:
    headers: dict[str, str] = {}
    cookie = os.getenv("TSUSHIN_AUTH_COOKIE")
    token = os.getenv("TSUSHIN_AUTH_TOKEN") or os.getenv("TSUSHIN_BEARER_TOKEN")
    api_key = os.getenv("TSUSHIN_API_KEY") or os.getenv("TSN_API_CLIENT_SECRET")
    extra_headers = os.getenv("TSUSHIN_EXTRA_HEADERS_JSON")

    if cookie:
        headers["Cookie"] = cookie
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if api_key:
        headers["X-API-Key"] = api_key
    if extra_headers:
        try:
            parsed = json.loads(extra_headers)
        except json.JSONDecodeError as exc:
            raise SmokeFailure(f"TSUSHIN_EXTRA_HEADERS_JSON is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
            raise SmokeFailure("TSUSHIN_EXTRA_HEADERS_JSON must be a JSON object with string keys.")
        headers.update({key: str(value) for key, value in parsed.items()})

    if not any(key in headers for key in ("Cookie", "Authorization", "X-API-Key")):
        raise SmokeFailure(
            "No auth credential provided. Set TSUSHIN_AUTH_COOKIE, "
            "TSUSHIN_AUTH_TOKEN, or TSUSHIN_API_KEY for the live stack."
        )
    return headers


def _validate_auth_prefix_compatibility(prefixes: tuple[str, ...], headers: dict[str, str]) -> None:
    has_v1_prefix = any(prefix.startswith("/api/v1/") or prefix == "/api/v1/teams" for prefix in prefixes)
    has_v1_auth = "Authorization" in headers or "X-API-Key" in headers
    if has_v1_prefix and not has_v1_auth:
        raise SmokeFailure(
            "The /api/v1/teams smoke requires TSUSHIN_AUTH_TOKEN or TSUSHIN_API_KEY. "
            "Cookie auth is only valid for the session-authenticated /api/teams surface. "
            "Set TSUSHIN_TEAMS_API_PREFIXES='/api/teams' to run the legacy smoke with a cookie."
        )


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_prefix(prefix: str) -> str:
    prefix = prefix.strip()
    if not prefix:
        raise SmokeFailure("Empty API prefix is not valid.")
    return prefix if prefix.startswith("/") else f"/{prefix}"


def _json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise SmokeFailure(
            f"Expected JSON from {response.request.method} {response.request.url}, "
            f"got: {_response_excerpt(response)}"
        ) from exc


def _extract_id(payload: Any, *keys: str) -> str | None:
    data = _unwrap(payload)
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value is not None:
            return str(value)
    return None


def _extract_status(payload: Any) -> str | None:
    data = _unwrap(payload)
    if isinstance(data, dict):
        status = data.get("status") or data.get("state")
        return str(status).lower() if status is not None else None
    return None


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            return data
    return payload


def _response_excerpt(response: requests.Response) -> str:
    text = response.text.strip()
    if not text:
        return "<empty body>"
    return text[:700]


def test_live_teams_api_e2e() -> None:
    if os.getenv("TSUSHIN_RUN_TEAMS_API_E2E") != "1":
        import pytest

        pytest.skip("Set TSUSHIN_RUN_TEAMS_API_E2E=1 to run the live Teams API smoke.")
    try:
        run_smoke(SmokeConfig.from_env_and_args([]))
    except SmokeFailure as exc:
        raise AssertionError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    try:
        run_smoke(SmokeConfig.from_env_and_args(argv))
    except SmokeFailure as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
