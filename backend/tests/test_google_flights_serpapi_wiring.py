from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (BACKEND_ROOT / relative).read_text(encoding="utf-8")


def test_google_flights_runtime_uses_typed_integration_only():
    provider = _read("hub/providers/google_flights_provider.py")

    assert "decrypt_google_flights_key" in provider
    assert "ApiKey" not in provider
    assert "get_api_key" not in provider


def test_google_flights_setup_uses_typed_config_endpoint():
    source = _read("api/routes_hub_providers.py")

    assert '@router.post("/travel-providers/google_flights/configure"' in source
    assert "configure_google_flights_integration(" in source
    assert 'tenant_has_configured=True' in source


def test_flight_provider_agent_link_writes_agent_skill_and_uses_tenant_provider():
    source = _read("api/routes_flight_providers.py")

    assert "from models import Agent, AgentSkill, AmadeusIntegration" in source
    assert "provider_id = normalize_flight_provider_id(update.provider)" in source
    assert "FlightProviderRegistry.get_provider(provider_id, db, tenant_id=ctx.tenant_id)" in source
    assert 'AgentSkill.skill_type == "flight_search"' in source
    assert "skill.is_enabled = True" in source
    assert "agent.config" not in source


def test_google_flights_catalog_checks_typed_hub_integration():
    source = _read("api/routes_hub_providers.py")

    assert "HubIntegration.type == provider_id" in source
    assert "has_api_key(" not in source


def test_provider_aliases_cover_search_and_flight_id_drift():
    aliases = _read("services/provider_aliases.py")
    search_skill = _read("agent/skills/search_skill.py")
    flight_skill = _read("agent/skills/flight_search_skill.py")

    assert '"brave_search": "brave"' in aliases
    assert '"google_search": "google"' in aliases
    assert '"serpapi": "google"' in aliases
    assert '"serpapi": "google_flights"' in aliases
    assert "normalize_search_provider_id(provider_name)" in search_skill
    assert "normalize_flight_provider_id(provider_name)" in flight_skill
