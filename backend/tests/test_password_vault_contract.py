"""
Password Vault provider / skill contract tests.

These tests intentionally describe the intended release behavior before the
implementation is fully wired. They follow the existing provider-shaped,
tool-only skill pattern used by Jira and Code Repository:

- tenant-scoped provider listing for /api/skill-providers/password_vault
- 1Password as the first programmatic provider
- per-agent capability-gated tool actions
- defense-in-depth capability checks at execute_tool()
- redaction before provider, skill, and flow-step results are persisted
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _ensure_package(package_name: str, relative_path: str):
    module = sys.modules.get(package_name)
    if module is None:
        module = types.ModuleType(package_name)
        module.__path__ = [str(BACKEND_ROOT / relative_path)]
        sys.modules[package_name] = module
    return module


_ensure_package("agent", "agent")
_ensure_package("agent.skills", os.path.join("agent", "skills"))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

argon2_stub = types.ModuleType("argon2")


class _PasswordHasher:
    def hash(self, value):
        return value

    def verify(self, hashed, plain):
        return hashed == plain


argon2_stub.PasswordHasher = _PasswordHasher
argon2_exceptions_stub = types.ModuleType("argon2.exceptions")
argon2_exceptions_stub.VerifyMismatchError = ValueError
argon2_exceptions_stub.InvalidHashError = ValueError
sys.modules.setdefault("argon2", argon2_stub)
sys.modules.setdefault("argon2.exceptions", argon2_exceptions_stub)

dateparser_stub = types.ModuleType("dateparser")
dateparser_stub.parse = lambda *_args, **_kwargs: None
sys.modules.setdefault("dateparser", dateparser_stub)


SENSITIVE_VALUES = [
    "correct-horse-battery-staple",
    "op://Engineering/Deploy Bot/password",
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_super_secret_token",
]
LONG_BARCODE = "83650000001234560048100999999999999999999999999"


def _import_any(*module_names: str):
    errors = []
    for module_name in module_names:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(f"{module_name}: {exc}")
    pytest.fail(
        "Password Vault module is not wired yet. Tried:\n" + "\n".join(errors)
    )


def _get_attr_any(module, *names: str):
    for name in names:
        if hasattr(module, name):
            return getattr(module, name)
    pytest.fail(
        f"{module.__name__} must expose one of: {', '.join(names)}"
    )


def _load_backend_module(module_name: str, relative_path: str):
    module_path = BACKEND_ROOT / relative_path
    if not module_path.exists():
        pytest.fail(f"{relative_path} is not wired yet for {module_name}")

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _assert_no_sensitive_values(document):
    serialized = json.dumps(document, sort_keys=True)
    for value in SENSITIVE_VALUES:
        assert value not in serialized
    assert "[REDACTED]" in serialized


def _make_password_vault_skill():
    module = _load_backend_module(
        "agent.skills.password_vault_skill",
        os.path.join("agent", "skills", "password_vault_skill.py"),
    )
    skill_cls = _get_attr_any(module, "PasswordVaultSkill")
    return skill_cls()


def test_skill_manager_registers_password_vault_skill():
    source = (BACKEND_ROOT / "agent" / "skills" / "skill_manager.py").read_text(
        encoding="utf-8"
    )

    assert "password_vault_skill" in source
    assert "PasswordVaultSkill" in source
    assert "password_vault" in source


def test_provider_listing_contract_for_password_vault_is_tenant_scoped_and_redacted():
    route_source = (
        BACKEND_ROOT / "api" / "routes_skill_integrations.py"
    ).read_text(encoding="utf-8")

    assert "skill_type == 'password_vault'" in route_source
    assert "PasswordVaultIntegration" in route_source
    assert "provider_type\": \"onepassword\"" in route_source
    assert "HubIntegration.tenant_id == ctx.tenant_id" in route_source
    assert "provider_mode" in route_source
    assert "health_status" in route_source

    password_vault_block = route_source.split("skill_type == 'password_vault'", 1)[1]
    password_vault_block = password_vault_block.split("elif skill_type ==", 1)[0]
    assert "token_encrypted" not in password_vault_block
    assert "service_account_token" not in password_vault_block
    assert "client_secret" not in password_vault_block
    assert "available_integrations" in password_vault_block


def test_password_vault_integration_test_route_matches_ui_result_contract():
    route_source = (BACKEND_ROOT / "api" / "routes_password_vault_integrations.py").read_text(encoding="utf-8")
    test_route_block = route_source.split("def test_password_vault_integration", 1)[1]
    test_route_block = test_route_block.split("@router.get", 1)[0]

    assert 'result["success"] = True' in test_route_block
    assert 'result["message"]' in test_route_block
    assert 'return {"success": False' in test_route_block


def test_password_vault_managed_secret_fields_are_ui_first_and_tenant_scoped():
    model_source = (BACKEND_ROOT / "models.py").read_text(encoding="utf-8")
    service_source = (BACKEND_ROOT / "services" / "password_vault_service.py").read_text(encoding="utf-8")
    route_source = (BACKEND_ROOT / "api" / "routes_password_vault_integrations.py").read_text(encoding="utf-8")
    client_source = (BACKEND_ROOT.parent / "frontend" / "lib" / "client.ts").read_text(encoding="utf-8")
    panel_source = (BACKEND_ROOT.parent / "frontend" / "components" / "password-vault" / "PasswordVaultIntegrationsPanel.tsx").read_text(encoding="utf-8")

    assert "class PasswordVaultSecretOverride" in model_source
    assert "value_encrypted" in model_source
    assert "tenant_id" in model_source
    assert "uq_password_vault_secret_override_field" in model_source

    assert "_read_override_value" in service_source
    assert "upsert_secret_override" in service_source
    assert "delete_secret_override" in service_source
    assert "encrypt_vault_token" in service_source
    assert "decrypt_vault_token" in service_source

    assert '/{integration_id}/secret-overrides' in route_source
    assert 'require_permission("hub.write")' in route_source
    assert "password_vault.managed_secret.upsert" in route_source

    assert "PasswordVaultSecretOverride" in client_source
    assert "createPasswordVaultSecretOverride" in client_source
    assert "listPasswordVaultSecretOverrides" in client_source
    assert "Managed fields" in panel_source
    assert "Save field" in panel_source


def test_flow_template_instantiation_resolves_password_vault_tenant_from_ui_resources():
    route_source = (BACKEND_ROOT / "api" / "routes_flows.py").read_text(encoding="utf-8")

    assert "def _resolve_template_tenant_id" in route_source
    assert 'params.get("agent_id")' in route_source
    assert 'params.get("password_vault_integration_id")' in route_source
    assert "Selected template resources belong to different tenants" in route_source
    assert "effective_tenant_id = _resolve_template_tenant_id" in route_source
    assert "tmpl.build(cleaned_params, effective_tenant_id)" in route_source
    assert "tenant_id=effective_tenant_id" in route_source


def test_required_password_vault_credentials_use_selected_integration_id():
    route_source = (BACKEND_ROOT / "api" / "routes_flows.py").read_text(encoding="utf-8")
    check_block = route_source.split("def _check_required_credentials", 1)[1]
    check_block = check_block.split("@router.post", 1)[0]

    assert 'params.get("password_vault_integration_id")' in check_block
    assert "PasswordVaultIntegration.id == int(integration_id)" in check_block
    assert "PasswordVaultIntegration.tenant_id == tenant_id" in check_block


def test_flow_step_config_preserves_password_vault_picker_metadata():
    schemas = _import_any("schemas")
    config_cls = _get_attr_any(schemas, "FlowStepConfig")

    payload = {
        "action": "read_item",
        "integration_id": 17,
        "vault": "lriprlys6dhrzhqlmwlhmgkw2m",
        "item_ref": "jpsqxvax44tmv46d3uo6enhkl4",
        "item_id": "jpsqxvax44tmv46d3uo6enhkl4",
        "field_name": "password",
        "password_vault_integration_id": 17,
        "password_vault_provider": "onepassword",
        "password_vault_vault_id": "lriprlys6dhrzhqlmwlhmgkw2m",
        "password_vault_vault_name": "FinanApp",
        "password_vault_item_id": "jpsqxvax44tmv46d3uo6enhkl4",
        "password_vault_item_title": "Moderna Condominio",
        "password_vault_field_name": "password",
        "password_vault_reference": "op://FinanApp/Moderna Condominio/password",
    }

    dumped = config_cls(**payload).model_dump()

    for key, value in payload.items():
        assert dumped[key] == value


def test_legacy_financial_utility_automation_step_is_removed():
    """Guardrail: the opaque provider-dispatch step and the finan migration
    nodes (record_store / financial_record_store / financial_bill_store) must
    stay deleted. Their removal was the goal of the finan-migration cleanup."""
    schemas = _import_any("schemas")
    step_type = _get_attr_any(schemas, "StepType")
    assert not hasattr(step_type, "FINANCIAL_UTILITY_AUTOMATION")
    assert not hasattr(step_type, "FINANCIAL_RECORD_STORE")
    assert not hasattr(step_type, "FINANCIAL_BILL_STORE")
    assert not hasattr(step_type, "RECORD_STORE")
    source = (BACKEND_ROOT / "flows" / "flow_engine.py").read_text(encoding="utf-8")
    assert "FinancialUtilityAutomationStepHandler" not in source
    assert "FinancialRecordStoreStepHandler" not in source
    assert "FinancialBillStoreStepHandler" not in source
    assert '"financial_utility_automation"' not in source
    assert '"financial_record_store"' not in source
    assert '"financial_bill_store"' not in source
    assert '"record_store"' not in source
    assert "run_moderna_condominio" not in source
    assert "run_consigaz_sao_blas" not in source
    assert "run_medsenior_samedil" not in source
    services_dir = BACKEND_ROOT / "services"
    assert not (services_dir / "financial_automation_service.py").exists()


def test_flow_step_config_has_no_finan_migration_fields():
    """Guardrail: FlowStepConfig must not re-grow the finan-migration field
    set. The cleanup deleted ~50 fields scattered across financial_*, record_*,
    emit_*_handle, parser_mode, and raw_bill_handle. If a future change adds
    any of these back, this test fails and the diff author can decide whether
    it's a real schema need or accidental re-pollution."""
    schemas = _import_any("schemas")
    config_cls = _get_attr_any(schemas, "FlowStepConfig")
    field_names = set(config_cls.model_fields.keys())
    forbidden = {
        "financial_provider", "financial_unit_id", "financial_asset",
        "financial_address", "financial_automation_key", "financial_automation_template",
        "financial_parser_mode", "financial_record_kind", "financial_record",
        "financial_record_handle", "financial_record_source_step",
        "financial_record_dedupe_key", "financial_record_payload",
        "financial_source_step", "financial_dedupe_key", "financial_bill",
        "financial_bill_handle", "financial_bill_source_step",
        "record_kind", "record_provider", "record_unit", "record_asset",
        "record_address", "record_automation_key", "record_source_step",
        "record_dedupe_key",
        "emit_record_handle", "emit_raw_handle",
        "emit_raw_bill_handle", "emit_financial_record_handle",
        "parser_mode", "raw_bill_handle", "issue_record_handle",
    }
    leaked = field_names & forbidden
    assert not leaked, f"FlowStepConfig regained finan-migration fields: {sorted(leaked)}"


def test_flow_templates_catalog_excludes_finan_templates():
    """Guardrail: the flow template catalog must not re-grow `Finan | …` or
    `financial_*` template ids. The dynamic registration from
    `.private/finan_profiles.json` was deleted in the finan-migration cleanup."""
    seeding = _import_any("services.flow_template_seeding")
    templates = seeding.list_templates()
    ids = [t.id for t in templates]
    names = [t.name for t in templates]
    finan_ids = [tid for tid in ids if tid.startswith("financial_")]
    finan_names = [n for n in names if n.startswith("Finan |") or n.startswith("Finan|")]
    assert not finan_ids, f"Template catalog regained financial_* ids: {finan_ids}"
    assert not finan_names, f"Template catalog regained 'Finan | …' templates: {finan_names}"


def test_gate_skip_condition_is_not_reported_as_failed_step():
    source = (BACKEND_ROOT / "flows" / "flow_engine.py").read_text(encoding="utf-8")

    assert 'result["skip_remaining_steps"] = True' in source
    assert 'result["status"] = "skipped" if gate_on_fail == "skip" else "failed"' in source
    assert 'output.get("status") == "skipped"' in source
    assert 'step_run.status = "skipped"' in source
    assert 'step_output.get("skip_remaining_steps")' in source
    assert 'remaining_step_run = FlowNodeRun(' in source
    assert '"upstream gate requested skip_remaining_steps"' in source
    assert 'sr.status in ("completed", "skipped")' in source
    assert '"steps_skipped"' in source


def test_browser_automation_uses_explicit_selector_actions_and_redacts_secret_handles(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    skill_module = _import_any("agent.skills.browser_automation_skill")
    handler_cls = _get_attr_any(flow_module, "BrowserAutomationStepHandler")
    from services.password_vault_service import SecretHandleRegistry

    captured = {}
    secret_value = "correct-horse-battery-staple"
    secret_handle = SecretHandleRegistry.issue(secret_value, {"kind": "test_secret"})["secret_handle"]

    class FakeBrowserAutomationSkill:
        def __init__(self, *args, **kwargs):
            pass

        def is_tool_enabled(self, _config):
            return True

        async def execute_tool(self, arguments, _message, _config):
            captured["arguments"] = arguments
            captured["config"] = _config
            return SimpleNamespace(
                success=True,
                output="Filled password field",
                media_paths=[],
                metadata={
                    "provider": "playwright",
                    "mode": "container",
                    "password": arguments["value"],
                    "text": f"linha digitavel {LONG_BARCODE}",
                },
            )

    monkeypatch.setattr(skill_module, "BrowserAutomationSkill", FakeBrowserAutomationSkill)

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=33,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "use_tool_mode": True,
                        "tool_action": "fill",
                        "selectors": [{
                            "name": "password",
                            "action": "fill",
                            "selector": "input[type='password']",
                            "value": "{{vault_password}}",
                        }],
                        "timeout_seconds": None,
                    }
                ),
            ),
            {"vault_password": secret_handle},
            SimpleNamespace(id=44, tenant_id="tenant-a"),
            SimpleNamespace(id=45),
        )
    )

    assert captured["arguments"]["action"] == "fill"
    assert captured["arguments"]["selector"] == "input[type='password']"
    assert captured["arguments"]["value"] == secret_value
    assert captured["config"]["timeout_seconds"] == 30
    assert output["status"] == "completed"
    assert output["raw_browser_result_handle"].startswith("pvh_")

    persisted = json.dumps(output, sort_keys=True)
    assert secret_value not in persisted
    assert LONG_BARCODE not in persisted
    assert "[REDACTED" in persisted


def test_captcha_guess_normalization_prefers_exact_length():
    skill_module = _import_any("agent.skills.browser_automation_skill")
    skill_cls = _get_attr_any(skill_module, "BrowserAutomationSkill")

    assert skill_cls._captcha_guess_lines("6252\n62562\n6252", expected_length=5) == ["62562"]
    assert skill_cls._captcha_guess_lines("f67ancx\nF67ANCX\nF67AW", expected_length=5) == ["f67aw"]
    assert skill_cls._captcha_guess_lines("6252\n62562\n6252") == ["6252", "62562"]
    assert skill_cls._captcha_guess_lines("m82\nmr82\nmr823", min_length=3, max_length=5) == [
        "m82",
        "mr82",
        "mr823",
    ]
    assert skill_cls._captcha_length_bounds({"captcha_min_length": 6, "captcha_max_length": 3}) == (3, 6)
    assert skill_cls._captcha_length_bounds({"captcha_length": 5, "captcha_min_length": 3}) == (5, 5)


def test_captcha_ollama_payload_honors_generation_bounds(monkeypatch, tmp_path):
    skill_module = _import_any("agent.skills.browser_automation_skill")
    skill_cls = _get_attr_any(skill_module, "BrowserAutomationSkill")

    image_path = tmp_path / "captcha.png"
    image_path.write_bytes(b"fake-image")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "178b63\n"}

    class FakeAsyncClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, json):
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr(skill_module.httpx, "AsyncClient", FakeAsyncClient)

    skill = skill_cls()
    guesses = asyncio.run(
        skill._captcha_guesses_from_ollama(
            str(image_path),
            {
                "ollama_base_url": "http://ollama.test",
                "ollama_model": "gemma4:latest",
                "solver_timeout_seconds": 240,
                "captcha_length": 6,
                "num_predict": 20,
                "num_ctx": "1024",
                "top_p": "0.1",
                "repeat_penalty": "1.05",
                "ollama_keep_alive": "30m",
            },
        )
    )

    assert guesses == ["178b63"]
    assert captured["timeout"] == 240
    assert captured["url"] == "http://ollama.test/api/generate"
    assert captured["payload"]["model"] == "gemma4:latest"
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["keep_alive"] == "30m"
    assert captured["payload"]["options"]["temperature"] == 0
    assert captured["payload"]["options"]["num_predict"] == 20
    assert captured["payload"]["options"]["num_ctx"] == 1024
    assert captured["payload"]["options"]["top_p"] == 0.1
    assert captured["payload"]["options"]["repeat_penalty"] == 1.05


def test_captcha_gemini_payload_uses_provider_instance_key(monkeypatch, tmp_path):
    skill_module = _import_any("agent.skills.browser_automation_skill")
    skill_cls = _get_attr_any(skill_module, "BrowserAutomationSkill")

    from PIL import Image
    import google.generativeai as genai

    image_path = tmp_path / "captcha.png"
    Image.new("RGB", (10, 10), "white").save(image_path)
    captured = {}

    class FakeGenerationConfig:
        def __init__(self, *, temperature, max_output_tokens):
            self.temperature = temperature
            self.max_output_tokens = max_output_tokens

    class FakeModel:
        def __init__(self, *, model_name, generation_config):
            captured["model_name"] = model_name
            captured["init_generation_config"] = generation_config

        def generate_content(self, parts, generation_config):
            captured["parts"] = parts
            captured["call_generation_config"] = generation_config
            return SimpleNamespace(text="cnz5l\n")

    def fake_configure(*, api_key):
        captured["api_key"] = api_key

    monkeypatch.setattr(genai, "GenerationConfig", FakeGenerationConfig)
    monkeypatch.setattr(genai, "GenerativeModel", FakeModel)
    monkeypatch.setattr(genai, "configure", fake_configure)

    skill = skill_cls()
    monkeypatch.setattr(skill, "_resolve_captcha_gemini_api_key", lambda _params: "gemini-key")

    guesses = asyncio.run(
        skill._captcha_guesses_from_gemini(
            str(image_path),
            {
                "gemini_model": "gemini-2.5-flash-lite",
                "captcha_length": 5,
                "num_predict": 30,
                "temperature": "0",
            },
        )
    )

    assert guesses == ["cnz5l"]
    assert captured["api_key"] == "gemini-key"
    assert captured["model_name"] == "gemini-2.5-flash-lite"
    assert captured["call_generation_config"].temperature == 0
    assert captured["call_generation_config"].max_output_tokens == 30
    assert "CAPTCHA" in captured["parts"][0]
    assert captured["parts"][1].size == (10, 10)


def test_browser_automation_reresolves_evicted_password_vault_handles(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    skill_module = _import_any("agent.skills.browser_automation_skill")
    vault_module = _import_any("services.password_vault_service")
    handler_cls = _get_attr_any(flow_module, "BrowserAutomationStepHandler")
    secret_registry_cls = _get_attr_any(vault_module, "SecretHandleRegistry")

    captured = {}
    secret_value = "fresh-from-provider"
    secret_handle = secret_registry_cls.issue(
        secret_value,
        {"kind": "test_secret", "tenant_id": "tenant-a"},
    )["secret_handle"]
    secret_registry_cls._handles.clear()

    class FakePasswordVaultService:
        def __init__(self, db, *, tenant_id):
            captured["tenant_id"] = tenant_id

        def load_integration(self, integration_id, require_active=True):
            captured["integration_id"] = integration_id
            captured["require_active"] = require_active
            return SimpleNamespace(id=integration_id)

        def resolve_field_value(self, integration, *, item_ref, field_name, vault=None):
            captured["item_ref"] = item_ref
            captured["field_name"] = field_name
            captured["vault"] = vault
            return secret_value

    class FakeBrowserAutomationSkill:
        def __init__(self, *args, **kwargs):
            pass

        def is_tool_enabled(self, _config):
            return True

        async def execute_tool(self, arguments, _message, _config):
            captured["arguments"] = arguments
            return SimpleNamespace(success=True, output="Filled field", media_paths=[], metadata={})

    monkeypatch.setattr(vault_module, "PasswordVaultService", FakePasswordVaultService)
    monkeypatch.setattr(skill_module, "BrowserAutomationSkill", FakeBrowserAutomationSkill)

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=34,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "use_tool_mode": True,
                        "tool_action": "fill",
                        "selectors": [{
                            "name": "password",
                            "action": "fill",
                            "selector": "input[type='password']",
                            "value": "{{vault_password.secret_handle}}",
                        }],
                    }
                ),
            ),
            {
                "flow": {"id": 44, "tenant_id": "tenant-a"},
                "vault_password": {
                    "secret_handle": secret_handle,
                    "integration_id": 17,
                    "vault": "FinanApp",
                    "item_ref": "Cypreste Superlogica",
                    "field_name": "password",
                },
            },
            SimpleNamespace(id=44, tenant_id="tenant-a"),
            SimpleNamespace(id=45),
        )
    )

    assert output["status"] == "completed"
    assert captured["arguments"]["value"] == secret_value
    assert captured["tenant_id"] == "tenant-a"
    assert captured["integration_id"] == 17
    assert captured["require_active"] is True
    assert captured["item_ref"] == "Cypreste Superlogica"
    assert captured["field_name"] == "password"
    assert captured["vault"] == "FinanApp"


def test_browser_config_coerces_null_timeout_to_default():
    provider_module = _import_any("hub.providers.browser_automation_provider")
    browser_config_cls = _get_attr_any(provider_module, "BrowserConfig")

    assert browser_config_cls(timeout_seconds=None).timeout_seconds == 30
    assert browser_config_cls(timeout_seconds=0).timeout_seconds == 1


def test_http_request_resolves_secret_handles_and_persists_redacted_preview(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "HttpRequestStepHandler")
    from services.password_vault_service import SecretHandleRegistry

    captured = {}
    secret_handle = SecretHandleRegistry.issue(
        "Bearer really-secret-token",
        {"kind": "test_secret"},
    )["secret_handle"]

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json", "set-cookie": "session=abc123"}
        text = json.dumps({"linhaDigitavel": LONG_BARCODE, "status": "aberto"})
        url = "https://api.test/boleto?token=really-secret-token"

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=10,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "http_method": "GET",
                        "http_url": "https://api.test/boleto",
                        "http_headers": {"Authorization": "{{auth_handle}}"},
                        "http_query": {"cpf": "123"},
                        "http_capture_raw_response": True,
                    }
                ),
            ),
            {"auth_handle": secret_handle},
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1001),
        )
    )

    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer really-secret-token"
    assert output["status"] == "completed"
    assert output["raw_response_handle"].startswith("pvh_")

    persisted = json.dumps(output, sort_keys=True)
    assert "really-secret-token" not in persisted
    assert "session=abc123" not in persisted
    assert LONG_BARCODE not in persisted
    assert "[REDACTED" in persisted


def test_password_vault_compose_basic_auth_uses_handles_and_persists_only_handle():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "PasswordVaultStepHandler")
    from services.password_vault_service import SecretHandleRegistry

    username_handle = SecretHandleRegistry.issue(
        "client-user",
        {"kind": "test_secret", "tenant_id": "tenant-a"},
    )["secret_handle"]
    password_handle = SecretHandleRegistry.issue(
        "client-pass",
        {"kind": "test_secret", "tenant_id": "tenant-a"},
    )["secret_handle"]

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=10,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "action": "compose_basic_auth",
                        "username_handle": username_handle,
                        "password_handle": password_handle,
                        "scheme": "Basic",
                        "output_alias": "vault_basic_auth",
                    }
                ),
            ),
            {},
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1001),
        )
    )

    assert output["status"] == "completed"
    assert output["secret_handle"].startswith("pvh_")
    assert SecretHandleRegistry.resolve(output["secret_handle"]) == "Basic Y2xpZW50LXVzZXI6Y2xpZW50LXBhc3M="

    persisted = json.dumps(output, sort_keys=True)
    assert "client-user" not in persisted
    assert "client-pass" not in persisted
    assert "Y2xpZW50LXVzZXI" not in persisted


def test_onepassword_provider_crud_and_test_connection_results_are_redacted():
    provider_module = _import_any(
        "hub.providers.password_vault_provider",
        "hub.password_vault.provider",
    )
    provider_cls = _get_attr_any(
        provider_module,
        "OnePasswordVaultProvider",
        "OnePasswordProvider",
    )

    provider = provider_cls(
        client=SimpleNamespace(
            test_connection=lambda: {
                "ok": True,
                "account": "acme.1password.com",
                "service_account_token": SENSITIVE_VALUES[3],
            },
            list_items=lambda **_kw: [
                {
                    "id": "item-1",
                    "title": "Deploy Bot",
                    "vault": "Engineering",
                    "fields": {
                        "username": "deploy@example.com",
                        "password": SENSITIVE_VALUES[0],
                    },
                }
            ],
            read_item=lambda **_kw: {
                "id": "item-1",
                "fields": {
                    "password": SENSITIVE_VALUES[0],
                    "api_key": SENSITIVE_VALUES[2],
                    "reference": SENSITIVE_VALUES[1],
                },
            },
            create_item=lambda **_kw: {
                "id": "item-2",
                "status": "created",
                "password": SENSITIVE_VALUES[0],
            },
            update_item=lambda **_kw: {
                "id": "item-1",
                "status": "updated",
                "token": SENSITIVE_VALUES[3],
            },
            delete_item=lambda **_kw: {
                "id": "item-1",
                "status": "deleted",
                "secret": SENSITIVE_VALUES[0],
            },
        )
    )

    for method_name, kwargs in [
        ("test_connection", {}),
        ("list_items", {"vault": "Engineering"}),
        ("read_item", {"item_id": "item-1"}),
        ("create_item", {"title": "Deploy Bot", "fields": {}}),
        ("update_item", {"item_id": "item-1", "fields": {}}),
        ("delete_item", {"item_id": "item-1"}),
    ]:
        result = getattr(provider, method_name)(**kwargs)
        assert result.get("success") is True
        assert "provider" in result
        _assert_no_sensitive_values(result)


def test_password_vault_skill_default_config_and_tool_spec_gate_write_actions():
    skill = _make_password_vault_skill()

    defaults = skill.get_default_config()
    assert skill.execution_mode == "tool"
    assert "execution_mode" not in defaults
    assert defaults["enabled"] is True
    assert defaults["integration_id"] is None
    assert defaults["provider"] == "onepassword"

    capabilities = defaults["capabilities"]
    assert capabilities["list_items"]["enabled"] is True
    assert capabilities["read_item"]["enabled"] is True
    assert capabilities["compose_basic_auth"]["enabled"] is True
    assert capabilities["test_connection"]["enabled"] is True
    assert capabilities["create_item"]["enabled"] is False
    assert capabilities["update_item"]["enabled"] is False
    assert capabilities["delete_item"]["enabled"] is False

    skill._config = {
        **defaults,
        "capabilities": {
            "list_items": {"enabled": True},
            "read_item": {"enabled": True},
            "test_connection": {"enabled": True},
            "create_item": {"enabled": False},
            "update_item": {"enabled": False},
            "delete_item": {"enabled": False},
        },
    }
    tool_def = skill.get_per_agent_mcp_tool_definition()

    assert tool_def["name"] == "password_vault_operation"
    actions = tool_def["inputSchema"]["properties"]["action"]["enum"]
    assert actions == ["list_items", "read_item", "compose_basic_auth", "test_connection"]
    assert "secret_value" not in tool_def["inputSchema"]["properties"]
    assert tool_def["annotations"]["destructive"] is False


def test_password_vault_skill_execute_tool_refuses_disabled_capability():
    skill = _make_password_vault_skill()
    config = {
        **skill.get_default_config(),
        "capabilities": {
            "list_items": {"enabled": True},
            "read_item": {"enabled": True},
            "test_connection": {"enabled": True},
            "create_item": {"enabled": False},
            "update_item": {"enabled": False},
            "delete_item": {"enabled": False},
        },
    }

    result = asyncio.run(
        skill.execute_tool(
            {
                "action": "create_item",
                "vault": "Engineering",
                "title": "Deploy Bot",
                "fields": {"password": SENSITIVE_VALUES[0]},
            },
            SimpleNamespace(body="create vault item", id="msg-1"),
            config,
        )
    )

    assert result.success is False
    assert result.metadata == {
        "error": "capability_disabled",
        "action": "create_item",
        "capability": "create_item",
    }
    _assert_no_sensitive_values(
        {"output": result.output, "metadata": result.metadata}
    )


def test_password_vault_skill_redacts_successful_tool_outputs_before_returning():
    skill = _make_password_vault_skill()
    config = {
        **skill.get_default_config(),
        "integration_id": 123,
        "capabilities": {"read_item": {"enabled": True}},
    }

    skill._get_provider = lambda _config=None: SimpleNamespace(
        read_item=lambda **_kw: {
            "success": True,
            "provider": "onepassword",
            "item": {
                "id": "item-1",
                "title": "Deploy Bot",
                "fields": {
                    "username": "deploy@example.com",
                    "password": SENSITIVE_VALUES[0],
                    "api_key": SENSITIVE_VALUES[2],
                    "reference": SENSITIVE_VALUES[1],
                },
            },
        }
    )

    result = asyncio.run(
        skill.execute_tool(
            {"action": "read_item", "item_id": "item-1"},
            SimpleNamespace(body="read vault item", id="msg-1"),
            config,
        )
    )

    assert result.success is True
    _assert_no_sensitive_values(
        {"output": result.output, "metadata": result.metadata}
    )


def test_flow_skill_step_redacts_password_vault_tool_output_before_persistence():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "SkillStepHandler")

    class FakePasswordVaultSkill:
        skill_type = "password_vault"
        skill_name = "Password Vault"

        @classmethod
        def get_default_config(cls):
            return {"execution_mode": "tool", "enabled": True}

        def is_tool_enabled(self, _config):
            return True

        async def execute_tool(self, _arguments, _message, _config):
            from agent.skills.base import SkillResult

            return SkillResult(
                success=True,
                output={
                    "item": {
                        "id": "item-1",
                        "fields": {
                            "password": SENSITIVE_VALUES[0],
                            "token": SENSITIVE_VALUES[3],
                        },
                    }
                },
                metadata={"api_key": SENSITIVE_VALUES[2]},
            )

    class FakeSkillManager:
        registry = {"password_vault": FakePasswordVaultSkill}

        async def get_skill_config(self, *_args, **_kwargs):
            return {"execution_mode": "tool", "enabled": True}

    query_result = SimpleNamespace(
        filter=lambda *_args, **_kw: SimpleNamespace(
            first=lambda: SimpleNamespace(tenant_id="tenant-a")
        )
    )
    handler = handler_cls(
        db=SimpleNamespace(query=lambda *_args, **_kw: query_result),
        mcp_sender=SimpleNamespace(),
    )

    async def fake_execute():
        skill_manager_module = importlib.import_module("agent.skills.skill_manager")
        original_skill_manager = getattr(skill_manager_module, "_skill_manager", None)
        skill_manager_module._skill_manager = FakeSkillManager()
        try:
            return await handler.execute(
                SimpleNamespace(
                    id=11,
                    agent_id=7,
                    config_json=json.dumps(
                        {
                            "skill_type": "password_vault",
                            "prompt": "read the deploy bot password",
                            "use_tool_mode": True,
                            "tool_arguments": {
                                "action": "read_item",
                                "item_id": "item-1",
                            },
                        }
                    ),
                ),
                {},
                SimpleNamespace(id=99, tenant_id="tenant-a", flow=None),
                SimpleNamespace(id=1001),
            )
        finally:
            skill_manager_module._skill_manager = original_skill_manager

    output = asyncio.run(fake_execute())

    assert output["skill_type"] == "password_vault"
    assert output["status"] == "completed"
    _assert_no_sensitive_values(output)


# =============================================================================
# Bill state classifier — unit tests
# =============================================================================


def test_notification_step_picks_state_template_matching_upstream_notification_state(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "NotificationStepHandler")

    captured = {}

    class FakeMCPSender:
        async def send_message(self, recipient, message, **_kwargs):
            captured["message"] = message
            return True

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=FakeMCPSender())
    monkeypatch.setattr(
        handler, "_resolve_mcp_url_and_secret",
        lambda *_args, **_kwargs: ("http://127.0.0.1:8080/api", None),
    )
    monkeypatch.setattr(handler, "_check_mcp_connection", lambda *_args, **_kwargs: True)

    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=21,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "channel": "whatsapp",
                        "recipient": "+15551234567",
                        "message_template": "Fallback: should not be used",
                        "message_templates_by_state": {
                            "new_boleto": "Novo boleto: {{financial_store.asset}}",
                            "pending_no_barcode": (
                                "Conta em aberto sem linha digitável: {{financial_store.asset}}"
                            ),
                            "no_pending_bills": "Sem boleto pendente: {{financial_store.asset}}",
                        },
                    }
                ),
            ),
            {
                "financial_store": {
                    "asset": "Test Utility Asset",
                    "notification_state": "pending_no_barcode",
                }
            },
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=2001),
        )
    )

    assert output["status"] == "completed"
    assert "Conta em aberto sem linha digitável: Test Utility Asset" in captured["message"]
    assert "Fallback" not in captured["message"]


def test_notification_step_falls_back_to_message_template_when_state_unknown(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "NotificationStepHandler")

    captured = {}

    class FakeMCPSender:
        async def send_message(self, recipient, message, **_kwargs):
            captured["message"] = message
            return True

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=FakeMCPSender())
    monkeypatch.setattr(
        handler, "_resolve_mcp_url_and_secret",
        lambda *_args, **_kwargs: ("http://127.0.0.1:8080/api", None),
    )
    monkeypatch.setattr(handler, "_check_mcp_connection", lambda *_args, **_kwargs: True)

    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=22,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "channel": "whatsapp",
                        "recipient": "+15551234567",
                        "message_template": "Fallback used",
                        "message_templates_by_state": {
                            "new_boleto": "Novo boleto",
                        },
                    }
                ),
            ),
            {
                "financial_store": {
                    "notification_state": "barcode_changed",
                }
            },
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=2002),
        )
    )

    assert output["status"] == "completed"
    assert captured["message"] == "Fallback used"


def test_notification_step_uses_default_key_when_state_unmatched(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "NotificationStepHandler")

    captured = {}

    class FakeMCPSender:
        async def send_message(self, recipient, message, **_kwargs):
            captured["message"] = message
            return True

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=FakeMCPSender())
    monkeypatch.setattr(
        handler, "_resolve_mcp_url_and_secret",
        lambda *_args, **_kwargs: ("http://127.0.0.1:8080/api", None),
    )
    monkeypatch.setattr(handler, "_check_mcp_connection", lambda *_args, **_kwargs: True)

    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=23,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "channel": "whatsapp",
                        "recipient": "+15551234567",
                        "message_templates_by_state": {
                            "new_boleto": "Novo",
                            "default": "Default branch hit",
                        },
                    }
                ),
            ),
            {
                "financial_store": {
                    "notification_state": "barcode_changed",
                }
            },
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=2003),
        )
    )

    assert output["status"] == "completed"
    assert captured["message"] == "Default branch hit"


# =============================================================================
# Gate operator — `in` membership for state-list gating
# =============================================================================

def test_gate_in_operator_passes_when_state_matches_list_value():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "GateStepHandler")
    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    assert handler._evaluate_condition("new_boleto", "in", ["new_boleto", "barcode_changed"], None) is True
    assert handler._evaluate_condition("paid", "in", ["new_boleto", "barcode_changed"], None) is False
    assert handler._evaluate_condition("new_boleto", "not_in", ["paid", "unchanged"], None) is True
    assert handler._evaluate_condition("paid", "not_in", ["paid", "unchanged"], None) is False
    assert handler._evaluate_condition("anything", "in", "not-a-list", None) is False
    assert handler._evaluate_condition("anything", "not_in", "not-a-list", None) is True
