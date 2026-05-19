from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (BACKEND_ROOT / relative).read_text(encoding="utf-8")


def test_google_flights_runtime_accepts_unified_serpapi_key():
    registry = _read("hub/providers/registry.py")
    provider = _read("hub/providers/google_flights_provider.py")
    aliases = _read("services/provider_aliases.py")

    assert 'GOOGLE_FLIGHTS_API_KEY_SERVICES = API_KEY_SERVICE_CANDIDATES["google_flights"]' in aliases
    assert "from services.provider_aliases import GOOGLE_FLIGHTS_API_KEY_SERVICES" in registry
    assert "get_decrypted_api_key(api_key.service" in registry
    assert 'get_decrypted_api_key("google_flights"' in provider


def test_serpapi_key_syncs_google_flights_integration():
    source = _read("api/routes_api_keys.py")

    assert "from services.provider_aliases import GOOGLE_FLIGHTS_API_KEY_SERVICES" in source
    assert "api_key.service in GOOGLE_FLIGHTS_API_KEY_SERVICES" in source
    assert "HubIntegration.type == 'google_flights'" in source
    assert 'identifier = f"apikey_google_flights_{api_key.tenant_id or \'system\'}"' in source


def test_flight_provider_agent_link_writes_agent_skill_and_uses_tenant_provider():
    source = _read("api/routes_flight_providers.py")

    assert "from models import Agent, AgentSkill, AmadeusIntegration" in source
    assert "provider_id = normalize_flight_provider_id(update.provider)" in source
    assert "FlightProviderRegistry.get_provider(provider_id, db, tenant_id=ctx.tenant_id)" in source
    assert 'AgentSkill.skill_type == "flight_search"' in source
    assert "skill.is_enabled = True" in source
    assert "agent.config" not in source


def test_google_flights_catalog_treats_serpapi_as_configured():
    source = _read("api/routes_hub_providers.py")

    assert "has_api_key(provider_id, db, tenant_id=tenant_id)" in source


def test_provider_aliases_cover_search_and_flight_config_drift():
    aliases = _read("services/provider_aliases.py")
    search_skill = _read("agent/skills/search_skill.py")
    flows = _read("api/routes_flows.py")

    assert '"brave": ("brave_search", "brave")' in aliases
    assert '"google": ("serpapi", "google_flights")' in aliases
    assert '"google_flights": ("google_flights", "serpapi")' in aliases
    assert "normalize_search_provider_id(provider_name)" in search_skill
    assert "get_api_key_service_candidates(service)" in flows
