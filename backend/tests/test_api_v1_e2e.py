"""
Public API v1 — End-to-End Tests
Tests the full API lifecycle against a running backend at localhost:8081.

Run with: pytest tests/test_api_v1_e2e.py -v --timeout=120
Requires: Backend running at http://localhost:8081
"""

import os
import time
import pytest
import requests

API_URL = os.getenv("E2E_API_URL", "http://localhost:8081")

# Test user credentials (must exist in the running instance)
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "test123"


@pytest.fixture(scope="module")
def user_token():
    """Get a user JWT for internal API access."""
    resp = requests.post(f"{API_URL}/api/auth/login", json={
        "email": TEST_EMAIL, "password": TEST_PASSWORD,
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def api_client_creds(user_token):
    """Create an API client and return (client_id, client_secret)."""
    resp = requests.post(f"{API_URL}/api/clients", json={
        "name": f"E2E Test {int(time.time())}",
        "description": "Automated E2E test client",
        "role": "api_owner",
        "rate_limit_rpm": 120,
    }, headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 201, f"Create client failed: {resp.text}"
    data = resp.json()
    return data["client_id"], data["client_secret"]


@pytest.fixture(scope="module")
def api_token(api_client_creds):
    """Get a v1 API token via OAuth2 exchange."""
    client_id, client_secret = api_client_creds
    resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })
    assert resp.status_code == 200, f"Token exchange failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def api_headers(api_token):
    """Bearer token headers for v1 API calls."""
    return {"Authorization": f"Bearer {api_token}"}


@pytest.fixture(scope="module")
def direct_headers(api_client_creds):
    """X-API-Key headers for direct auth mode."""
    _, client_secret = api_client_creds
    return {"X-API-Key": client_secret}


# ============================================================================
# OAuth2 Token Exchange
# ============================================================================

class TestOAuth2TokenExchange:

    def test_valid_exchange(self, api_client_creds):
        client_id, client_secret = api_client_creds
        resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 3600
        assert "scope" in data

    def test_invalid_grant_type(self, api_client_creds):
        client_id, client_secret = api_client_creds
        resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
        })
        assert resp.status_code == 400

    def test_wrong_secret(self, api_client_creds):
        client_id, _ = api_client_creds
        resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": "tsn_cs_wrong_secret_here",
        })
        assert resp.status_code == 401

    def test_nonexistent_client(self):
        resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": "tsn_ci_nonexistent",
            "client_secret": "tsn_cs_whatever",
        })
        assert resp.status_code == 401


# ============================================================================
# Agent Listing
# ============================================================================

class TestAgentListing:

    def test_list_agents_bearer(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/agents", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "meta" in data
        assert data["meta"]["total"] > 0

    def test_list_agents_direct_key(self, direct_headers):
        resp = requests.get(f"{API_URL}/api/v1/agents", headers=direct_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["meta"]["total"] > 0

    def test_list_agents_pagination(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/agents?page=1&per_page=2", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) <= 2
        assert data["meta"]["per_page"] == 2

    def test_get_agent_detail(self, api_headers):
        # Get first agent
        resp = requests.get(f"{API_URL}/api/v1/agents", headers=api_headers)
        agents = resp.json()["data"]
        if agents:
            agent_id = agents[0]["id"]
            detail_resp = requests.get(f"{API_URL}/api/v1/agents/{agent_id}", headers=api_headers)
            assert detail_resp.status_code == 200
            detail = detail_resp.json()
            assert "system_prompt" in detail
            assert "skills_detail" in detail

    def test_agent_not_found(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/agents/99999", headers=api_headers)
        assert resp.status_code == 404


# ============================================================================
# Permission Enforcement
# ============================================================================

class TestPermissionEnforcement:

    def test_no_auth_returns_401(self):
        resp = requests.get(f"{API_URL}/api/v1/agents")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        resp = requests.get(f"{API_URL}/api/v1/agents",
                           headers={"Authorization": "Bearer invalid_token"})
        assert resp.status_code == 401

    def test_readonly_cannot_create(self, user_token):
        """Create a readonly client and verify it can't create agents."""
        # Create readonly client
        resp = requests.post(f"{API_URL}/api/clients", json={
            "name": f"Readonly Test {int(time.time())}",
            "role": "api_readonly",
        }, headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 201
        creds = resp.json()

        # Get token
        token_resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
        })
        token = token_resp.json()["access_token"]

        # Try to create agent — should fail
        create_resp = requests.post(f"{API_URL}/api/v1/agents", json={
            "name": "Should Fail",
            "system_prompt": "test",
        }, headers={"Authorization": f"Bearer {token}"})
        assert create_resp.status_code == 403


# ============================================================================
# Resource Listing
# ============================================================================

class TestResourceListing:

    def test_list_skills(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/skills", headers=api_headers)
        assert resp.status_code == 200
        assert "data" in resp.json()
        assert len(resp.json()["data"]) > 0

    def test_list_personas(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/personas", headers=api_headers)
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_list_tone_presets(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/tone-presets", headers=api_headers)
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_list_tools(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/tools", headers=api_headers)
        assert resp.status_code == 200
        assert "data" in resp.json()


# ============================================================================
# Rate Limiting Headers
# ============================================================================

class TestRateLimitHeaders:

    def test_request_id_header(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/agents", headers=api_headers)
        assert "x-request-id" in resp.headers
        assert resp.headers["x-request-id"].startswith("req_")

    def test_rate_limit_headers(self, api_headers):
        resp = requests.get(f"{API_URL}/api/v1/agents", headers=api_headers)
        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers


# ============================================================================
# Agent Chat (Sync)
# ============================================================================

class TestAgentChat:

    def test_sync_chat(self, api_headers):
        """Send a message and get a response (real LLM call)."""
        # Get first active agent
        agents_resp = requests.get(f"{API_URL}/api/v1/agents?is_active=true", headers=api_headers)
        agents = agents_resp.json()["data"]
        if not agents:
            pytest.skip("No active agents available")

        agent_id = agents[0]["id"]
        resp = requests.post(
            f"{API_URL}/api/v1/agents/{agent_id}/chat",
            json={"message": "Reply with exactly one word: hello"},
            headers={**api_headers, "Content-Type": "application/json"},
            timeout=120,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["message"] is not None
        assert len(data["message"]) > 0
        assert data["agent_name"] is not None
        assert data["execution_time_ms"] is not None

    def test_chat_nonexistent_agent(self, api_headers):
        resp = requests.post(
            f"{API_URL}/api/v1/agents/99999/chat",
            json={"message": "Hello"},
            headers={**api_headers, "Content-Type": "application/json"},
        )
        assert resp.status_code == 404


# ============================================================================
# Client Management (Internal API)
# ============================================================================

class TestClientManagement:

    def test_list_clients(self, user_token):
        resp = requests.get(f"{API_URL}/api/clients",
                           headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_and_rotate(self, user_token):
        # Create
        resp = requests.post(f"{API_URL}/api/clients", json={
            "name": f"Rotate E2E {int(time.time())}",
            "role": "api_agent_only",
        }, headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 201
        old_secret = resp.json()["client_secret"]
        client_id = resp.json()["client_id"]

        # Rotate
        rotate_resp = requests.post(
            f"{API_URL}/api/clients/{client_id}/rotate-secret",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert rotate_resp.status_code == 200
        new_secret = rotate_resp.json()["client_secret"]
        assert new_secret != old_secret

        # Old secret should fail token exchange
        old_token_resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": old_secret,
        })
        assert old_token_resp.status_code == 401

        # New secret should work
        new_token_resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": new_secret,
        })
        assert new_token_resp.status_code == 200

    def test_revoke_client(self, user_token):
        # Create
        resp = requests.post(f"{API_URL}/api/clients", json={
            "name": f"Revoke E2E {int(time.time())}",
            "role": "api_agent_only",
        }, headers={"Authorization": f"Bearer {user_token}"})
        client_id = resp.json()["client_id"]
        secret = resp.json()["client_secret"]

        # Revoke
        revoke_resp = requests.delete(
            f"{API_URL}/api/clients/{client_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert revoke_resp.status_code == 204

        # Token exchange should fail
        token_resp = requests.post(f"{API_URL}/api/v1/oauth/token", data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
        })
        assert token_resp.status_code == 401
