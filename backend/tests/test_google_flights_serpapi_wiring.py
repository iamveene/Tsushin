from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (BACKEND_ROOT / relative).read_text(encoding="utf-8")


def test_google_flights_runtime_accepts_unified_serpapi_key():
    registry = _read("hub/providers/registry.py")
    provider = _read("hub/providers/google_flights_provider.py")

    assert 'GOOGLE_FLIGHTS_API_KEY_SERVICES = ("google_flights", "serpapi")' in registry
    assert "get_decrypted_api_key(api_key.service" in registry
    assert 'for service_name in ("google_flights", "serpapi")' in provider


def test_serpapi_key_syncs_google_flights_integration():
    source = _read("api/routes_api_keys.py")

    assert 'GOOGLE_FLIGHTS_API_KEY_SERVICES = {"google_flights", "serpapi"}' in source
    assert "api_key.service in GOOGLE_FLIGHTS_API_KEY_SERVICES" in source
    assert "HubIntegration.type == 'google_flights'" in source
    assert 'identifier = f"apikey_google_flights_{api_key.tenant_id or \'system\'}"' in source


def test_flight_provider_agent_link_writes_agent_skill_and_uses_tenant_provider():
    source = _read("api/routes_flight_providers.py")

    assert "from models import Agent, AgentSkill, AmadeusIntegration" in source
    assert "FlightProviderRegistry.get_provider(update.provider, db, tenant_id=ctx.tenant_id)" in source
    assert 'AgentSkill.skill_type == "flight_search"' in source
    assert "skill.is_enabled = True" in source
    assert "agent.config" not in source


def test_google_flights_catalog_treats_serpapi_as_configured():
    source = _read("api/routes_hub_providers.py")

    assert 'ApiKey.service.in_(("google_flights", "serpapi"))' in source
