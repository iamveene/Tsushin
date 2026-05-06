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


def test_flow_step_config_preserves_financial_utility_automation_metadata():
    schemas = _import_any("schemas")
    config_cls = _get_attr_any(schemas, "FlowStepConfig")
    step_type = _get_attr_any(schemas, "StepType")

    assert step_type.FINANCIAL_UTILITY_AUTOMATION.value == "financial_utility_automation"

    payload = {
        "financial_automation_template": "moderna_condominio_sao_blas_204",
        "financial_provider": "moderna",
        "financial_unit_id": "0204",
        "financial_asset": "AP Ed. San Blass",
        "financial_address": "Rua Piratininga 111, Praia da Costa, Vila Velha",
        "financial_customer_code": "1051548",
        "financial_delivery_location": "PADRAO",
        "financial_username_field": "email",
        "financial_password_field": "password",
        "financial_browser_timeout_ms": 30000,
        "financial_notification_enabled": False,
        "financial_notification_recipient": "@Vini",
        "financial_notification_agent_id": 1,
        "financial_password_vault_integration_id": 17,
        "financial_password_vault_provider": "onepassword",
        "financial_password_vault_vault_id": "lriprlys6dhrzhqlmwlhmgkw2m",
        "financial_password_vault_vault_name": "FinanApp",
        "financial_password_vault_item_id": "jpsqxvax44tmv46d3uo6enhkl4",
        "financial_password_vault_item_title": "Moderna Condominio",
        "financial_password_vault_field_name": "password",
        "financial_password_vault_reference": "op://FinanApp/Moderna Condominio/password",
    }

    dumped = config_cls(**payload).model_dump()

    for key, value in payload.items():
        assert dumped[key] == value


def test_flow_engine_registers_financial_utility_automation_handler():
    source = (BACKEND_ROOT / "flows" / "flow_engine.py").read_text(encoding="utf-8")

    assert "FinancialUtilityAutomationStepHandler" in source
    assert '"financial_utility_automation"' in source
    assert "FinancialAutomationService" in source
    assert "run_moderna_condominio" in source
    assert "run_consigaz_sao_blas" in source
    assert "run_medsenior_samedil" in source


def test_flow_engine_registers_ui_first_financial_primitives():
    schemas = _import_any("schemas")
    step_type = _get_attr_any(schemas, "StepType")
    config_cls = _get_attr_any(schemas, "FlowStepConfig")
    source = (BACKEND_ROOT / "flows" / "flow_engine.py").read_text(encoding="utf-8")

    assert step_type.HTTP_REQUEST.value == "http_request"
    assert step_type.DATA_TRANSFORM.value == "data_transform"
    assert step_type.FINANCIAL_RECORD_STORE.value == "financial_record_store"
    assert step_type.FINANCIAL_BILL_STORE.value == "financial_bill_store"
    assert '"http_request": HttpRequestStepHandler' in source
    assert '"data_transform": DataTransformStepHandler' in source
    assert '"financial_record_store": FinancialRecordStoreStepHandler' in source
    assert '"financial_bill_store": FinancialBillStoreStepHandler' in source

    dumped = config_cls(
        http_method="POST",
        http_url="https://example.invalid/api",
        http_headers=[{"key": "Authorization", "value": "{{vault.secret_handle}}"}],
        transform_mode="financial_parser",
        financial_parser_mode="consigaz_utility_bill",
        source_steps={"boleto": "step_2", "nota": "step_3"},
        record_kind="tax_obligation",
        financial_record_source_step="parsed_tax",
        financial_dedupe_key="{{provider}}:{{asset}}:{{period_key}}",
    ).model_dump()

    assert dumped["http_method"] == "POST"
    assert dumped["financial_parser_mode"] == "consigaz_utility_bill"
    assert dumped["record_kind"] == "tax_obligation"


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


def test_financial_templates_expand_to_visible_ui_first_nodes():
    templates_module = _import_any("services.flow_template_seeding")
    schemas = _import_any("schemas")
    step_type = _get_attr_any(schemas, "StepType")

    templates = [
        template for template in templates_module.list_templates()
        if template.id.startswith("financial_")
    ]

    template_ids = {template.id for template in templates}
    assert template_ids == {
        "financial_cond_sao_blas_boleto",
        "financial_consigaz_sao_blas",
        "financial_medsenior_samedil_mae",
        "financial_cypreste_superlogica",
        "financial_edp_es",
    }
    assert "financial_detran_es_ipva" not in template_ids
    assert "financial_b3_investidor" not in template_ids
    assert "financial_pmvv_iptu" not in template_ids
    assert "financial_husky_transfers" not in template_ids
    assert templates_module.FINANCIAL_PROFILES["husky_transfers"]["template_enabled"] is False
    for template in templates:
        flow = template.build(
            {
                "name": template.name,
                "agent_id": 1,
                "channel": "whatsapp",
                "recipient": "+5511999999999",
                "password_vault_integration_id": 17,
                "vault": "FinanApp",
            },
            "tenant-a",
        )
        step_values = [step.type.value if hasattr(step.type, "value") else step.type for step in flow.steps]
        assert step_type.FINANCIAL_UTILITY_AUTOMATION.value not in step_values
        assert step_values[:2] == [step_type.PASSWORD_VAULT.value, step_type.PASSWORD_VAULT.value]
        assert step_type.DATA_TRANSFORM.value in step_values
        assert step_type.GATE.value in step_values
        assert step_type.NOTIFICATION.value in step_values

        browser_steps = [step for step in flow.steps if step.type == step_type.BROWSER_AUTOMATION]
        dumped_flow = json.dumps(flow.model_dump(), default=str)
        assert len(browser_steps) >= 6
        assert all(step.config.use_tool_mode for step in browser_steps)
        assert all(step.config.tool_action for step in browser_steps)
        assert all("example" not in (step.config.url or "") for step in browser_steps)
        assert not re.search(r"Basic\s+[A-Za-z0-9+/=]{12,}", dumped_flow)
        assert "{{credentials." not in dumped_flow
        if "__codexTemplateContext" in dumped_flow:
            assert any(step.name.startswith("context_") for step in browser_steps)
        if template.id != "financial_consigaz_sao_blas":
            assert any(step.config.tool_action in {"wait_for", "wait_for_url"} for step in browser_steps)
        else:
            basic_auth_step = next(step for step in flow.steps if step.name == "vault_basic_auth")
            assert basic_auth_step.config.action == "compose_basic_auth"
            assert basic_auth_step.config.username_handle == "{{vault_username.secret_handle}}"
            assert basic_auth_step.config.password_handle == "{{vault_password.secret_handle}}"
            vault_field_names = [
                step.config.field_name
                for step in flow.steps
                if step.type == step_type.PASSWORD_VAULT and step.config.field_name
            ]
            assert "username" in vault_field_names
            assert "Codigo_Client" in vault_field_names
        assert any(step.config.tool_action in {"extract", "execute_script"} for step in browser_steps)
        if template.id == "financial_medsenior_samedil_mae":
            optional_steps = [step for step in browser_steps if step.on_failure == "continue"]
            assert optional_steps
            assert all(step.config.optional is True for step in optional_steps)
            assert all(step.config.treat_failure_as_skipped is True for step in optional_steps)
        if template.id == "financial_edp_es":
            vault_field_names = [
                step.config.field_name
                for step in flow.steps
                if step.type == step_type.PASSWORD_VAULT and step.config.field_name
            ]
            assert "cpf" in vault_field_names
            gate_step = next(step for step in flow.steps if step.type == step_type.GATE)
            assert gate_step.config.gate_conditions == [
                {
                    "field": "conditions.notification_state",
                    "operator": "in",
                    "value": ["new_boleto", "barcode_changed", "pending_no_barcode"],
                },
            ]
        transform_step = next(step for step in flow.steps if step.type == step_type.DATA_TRANSFORM)
        assert transform_step.config.extraction_rules or transform_step.config.financial_parser_mode


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


def test_data_transform_consigaz_parser_returns_redacted_preview_and_raw_bill_handle():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "DataTransformStepHandler")
    from services.password_vault_service import SecretHandleRegistry

    boleto_json = {
        "dsRetorno": {
            "tt-cliente-retorno": [
                {
                    "cod_tit_acr": "B123",
                    "situacao_pagto": "Aberto",
                    "tt-dados-gerais": [
                        {
                            "vencimento": "10/05/2026",
                            "referencia": "05/2026",
                            "valor-total": "123,45",
                            "linha-digitavel": LONG_BARCODE,
                        }
                    ],
                }
            ]
        }
    }
    boleto_handle = SecretHandleRegistry.issue(
        json.dumps({"status_code": 200, "json": boleto_json, "body": json.dumps(boleto_json)}),
        {"kind": "http_response"},
    )["secret_handle"]
    nota_handle = SecretHandleRegistry.issue(
        json.dumps({"status_code": 200, "json": {}, "body": "{}"}),
        {"kind": "http_response"},
    )["secret_handle"]

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=11,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "financial_parser_mode": "consigaz_utility_bill",
                        "source_steps": {
                            "boleto_json": "boleto_response",
                            "nota_json": "nota_response",
                        },
                        "financial_unit_id": "AP0204",
                        "emit_raw_bill_handle": True,
                    }
                ),
            ),
            {
                "boleto_response": {"raw_response_handle": boleto_handle},
                "nota_response": {"raw_response_handle": nota_handle},
            },
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1002),
        )
    )

    assert output["status"] == "completed"
    assert output["record_kind"] == "utility_bill"
    assert output["raw_bill_handle"].startswith("pvh_")
    assert output["conditions"]["has_barcode"] is True
    assert LONG_BARCODE not in json.dumps(output, sort_keys=True)

    raw_bill = json.loads(SecretHandleRegistry.resolve(output["raw_bill_handle"]))
    assert raw_bill["barcode"] == LONG_BARCODE
    assert raw_bill["provider"] == "consigaz"


def test_financial_bill_store_persists_utility_bill_without_hidden_notification(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialBillStoreStepHandler")
    from services.password_vault_service import SecretHandleRegistry
    import services.financial_automation_service as financial_service

    captured = {}
    raw_bill_handle = SecretHandleRegistry.issue(
        json.dumps(
            {
                "record_kind": "utility_bill",
                "provider": "consigaz",
                "automation_id": "consigaz_visible_flow",
                "unit_id": "AP0204",
                "reference_month": "2026-05",
                "due_date": "10/05/2026",
                "amount": "123,45",
                "status": "Aberto",
                "barcode": LONG_BARCODE,
            }
        ),
        {"kind": "financial_record", "record_kind": "utility_bill"},
    )["secret_handle"]

    def fake_upsert(self, extracted, config, *, flow_run_id):
        captured["extracted"] = extracted
        captured["config"] = config
        captured["flow_run_id"] = flow_run_id
        return {
            "record": SimpleNamespace(
                id=777,
                automation_key=extracted["automation_key"],
                provider=extracted["provider"],
                unit_id=extracted["unit_id"],
                asset="AP Ed. San Blass",
                reference_month=extracted["reference_month"],
                due_date=extracted["due_date"],
                amount_cents=12345,
                status=extracted["status"],
                barcode_preview="[REDACTED:47:9999]",
            ),
            "created": True,
            "updated": False,
            "barcode_changed": True,
        }

    def fail_notification(*_args, **_kwargs):
        raise AssertionError("financial_bill_store must not create notifications")

    monkeypatch.setattr(financial_service.FinancialAutomationService, "_upsert_bill", fake_upsert)
    monkeypatch.setattr(financial_service.FinancialAutomationService, "_maybe_create_notification", fail_notification)

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=12,
                timeout_seconds=30,
                config_json=json.dumps({"financial_bill_handle": raw_bill_handle}),
            ),
            {},
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1003),
        )
    )

    assert captured["extracted"]["barcode"] == LONG_BARCODE
    assert captured["flow_run_id"] == 99
    assert output["status"] == "completed"
    assert output["record_store_model"] == "financial_utility_bill"
    assert output["dedupe"]["created"] is True
    assert output["conditions"]["should_notify"] is True
    assert output["linha_digitavel"].startswith("pvh_")
    assert output["barcode_delivery_handle"] == output["linha_digitavel"]
    assert SecretHandleRegistry.resolve(output["linha_digitavel"]) == LONG_BARCODE
    assert LONG_BARCODE not in json.dumps(output, sort_keys=True)


def test_notification_delivers_linha_digitavel_but_persists_redacted_message(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "NotificationStepHandler")
    from services.password_vault_service import SecretHandleRegistry

    captured = {}
    linha_digitavel_handle = SecretHandleRegistry.issue(
        LONG_BARCODE,
        {"kind": "financial_barcode", "tenant_id": "tenant-a"},
    )["secret_handle"]

    class FakeMCPSender:
        async def send_message(self, recipient, message, **kwargs):
            captured["recipient"] = recipient
            captured["message"] = message
            captured["kwargs"] = kwargs
            return True

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=FakeMCPSender())
    monkeypatch.setattr(
        handler,
        "_resolve_mcp_url_and_secret",
        lambda *_args, **_kwargs: ("http://127.0.0.1:8080/api", None),
    )
    monkeypatch.setattr(handler, "_check_mcp_connection", lambda *_args, **_kwargs: True)

    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=15,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "channel": "whatsapp",
                        "recipient": "+15551234567",
                        "message_template": (
                            "Linha digitavel: {{financial_store.linha_digitavel}} "
                            "preview {{financial_store.barcode_preview}}"
                        ),
                    }
                ),
            ),
            {
                "financial_store": {
                    "barcode_preview": "[REDACTED:47:9999]",
                    "linha_digitavel": linha_digitavel_handle,
                    "barcode_delivery_handle": linha_digitavel_handle,
                }
            },
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1006),
        )
    )

    assert output["status"] == "completed"
    assert output["success"] is True
    assert captured["recipient"] == "+15551234567"
    assert LONG_BARCODE in captured["message"]
    assert "[REDACTED:47:9999]" not in captured["message"]
    persisted = json.dumps(output, sort_keys=True)
    assert LONG_BARCODE not in persisted
    assert "[REDACTED_DIGITS" in persisted


def test_financial_bill_store_skips_explicit_no_pending_bill_without_persisting(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialBillStoreStepHandler")
    import services.financial_automation_service as financial_service

    def fail_upsert(*_args, **_kwargs):
        raise AssertionError("no pending bill runs must not upsert an empty utility bill")

    monkeypatch.setattr(financial_service.FinancialAutomationService, "_upsert_bill", fail_upsert)

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=14,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "financial_bill": {
                            "record_kind": "utility_bill",
                            "automation_id": "medsenior_samedil_plano_saude_mae",
                            "provider": "medsenior",
                            "unit_id": "Plano Saude Mae",
                            "reference_month": "",
                            "period_key": "latest",
                            "amount": "",
                            "due_date": "",
                            "status": "no_pending_bills",
                            "barcode": "",
                        }
                    }
                ),
            ),
            {},
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1005),
        )
    )

    assert output["status"] == "skipped"
    assert output["reason"] == "no_financial_bill_detected"
    assert output["dedupe"]["created"] is False
    assert output["conditions"]["no_open_bills"] is True
    assert output["conditions"]["should_notify"] is False


def test_financial_reference_month_preserves_iso_month_before_due_date_fallback():
    import services.financial_automation_service as financial_service

    assert financial_service._to_reference_month("2026-04", "11/05/2026") == "04/2026"
    assert financial_service._to_reference_month("Vencimento em 05/05/2026") == "05/2026"


def test_financial_record_store_delegates_generic_records_to_store_service(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialRecordStoreStepHandler")
    import services.financial_automation_service as financial_service

    captured = {}

    def fake_store(self, record, config, *, flow_run_id):
        captured["record"] = record
        captured["config"] = config
        captured["flow_run_id"] = flow_run_id
        return {
            "status": "completed",
            "success": True,
            "record_kind": record["record_kind"],
            "record_id": 991,
            "dedupe": {
                "dedupe_key": "tax_obligation:pmvv:imovel-204:2026",
                "created": True,
                "updated": False,
            },
            "conditions": {
                "record_kind": record["record_kind"],
                "created": True,
                "updated": False,
                "should_notify": True,
            },
            "redacted": True,
        }

    monkeypatch.setattr(financial_service.FinancialAutomationService, "store_financial_record", fake_store)
    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=13,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "record_kind": "tax_obligation",
                        "financial_record": {
                            "provider": "pmvv",
                            "unit_id": "imovel-204",
                            "period": "2026",
                            "barcode": LONG_BARCODE,
                            "secret": "do-not-store-clear",
                        },
                    }
                ),
            ),
            {},
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1004),
        )
    )

    assert captured["record"]["record_kind"] == "tax_obligation"
    assert captured["record"]["barcode"] == LONG_BARCODE
    assert captured["flow_run_id"] == 99
    assert output["status"] == "completed"
    assert output["record_kind"] == "tax_obligation"
    assert output["dedupe"]["created"] is True
    assert output["conditions"]["should_notify"] is True

    persisted = json.dumps(output, sort_keys=True)
    assert LONG_BARCODE not in persisted
    assert "do-not-store-clear" not in persisted


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
    assert defaults["execution_mode"] == "tool"
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

def test_classify_utility_bill_state_returns_new_boleto_for_created_record_with_barcode():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialRecordStoreStepHandler")
    state = handler_cls._classify_utility_bill_state(
        created=True, barcode_changed=False, has_barcode=True, unpaid=True,
    )
    assert state == "new_boleto"


def test_classify_utility_bill_state_returns_pending_no_barcode_for_created_record_without_barcode():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialRecordStoreStepHandler")
    state = handler_cls._classify_utility_bill_state(
        created=True, barcode_changed=False, has_barcode=False, unpaid=True,
    )
    assert state == "pending_no_barcode"


def test_classify_utility_bill_state_returns_barcode_changed_when_barcode_updates():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialRecordStoreStepHandler")
    state = handler_cls._classify_utility_bill_state(
        created=False, barcode_changed=True, has_barcode=True, unpaid=True,
    )
    assert state == "barcode_changed"


def test_classify_utility_bill_state_returns_paid_when_bill_is_paid():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialRecordStoreStepHandler")
    state = handler_cls._classify_utility_bill_state(
        created=False, barcode_changed=False, has_barcode=True, unpaid=False,
    )
    assert state == "paid"


def test_classify_utility_bill_state_returns_unchanged_when_existing_record_has_no_change():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialRecordStoreStepHandler")
    state = handler_cls._classify_utility_bill_state(
        created=False, barcode_changed=False, has_barcode=True, unpaid=True,
    )
    assert state == "unchanged"


def test_classify_utility_bill_state_returns_unchanged_for_existing_record_without_barcode():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialRecordStoreStepHandler")
    state = handler_cls._classify_utility_bill_state(
        created=False, barcode_changed=False, has_barcode=False, unpaid=True,
    )
    assert state == "unchanged"


def test_classify_utility_bill_state_default_notify_states_excludes_passive_states():
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialRecordStoreStepHandler")
    notify = set(handler_cls.DEFAULT_NOTIFY_STATES)
    assert notify == {"new_boleto", "barcode_changed", "pending_no_barcode"}
    # paid, unchanged, no_pending_bills, error must not be on the default notify list
    assert "paid" not in notify
    assert "unchanged" not in notify
    assert "no_pending_bills" not in notify
    assert "error" not in notify


# =============================================================================
# Bill store integration — state propagation through handler output
# =============================================================================

def test_financial_bill_store_emits_pending_no_barcode_when_open_bill_has_no_barcode(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialBillStoreStepHandler")
    import services.financial_automation_service as financial_service

    def fake_upsert(self, extracted, config, *, flow_run_id):
        return {
            "record": SimpleNamespace(
                id=901,
                automation_key=extracted["automation_key"],
                provider=extracted["provider"],
                unit_id=extracted["unit_id"],
                asset="EDP Casa Paraju",
                reference_month=extracted.get("reference_month") or "2026-05",
                due_date=extracted.get("due_date") or "",
                amount_cents=0,
                status="pendente",
                barcode_preview="",
            ),
            "created": True,
            "updated": False,
            "barcode_changed": False,
        }

    monkeypatch.setattr(financial_service.FinancialAutomationService, "_upsert_bill", fake_upsert)

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=18,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "financial_bill": {
                            "record_kind": "utility_bill",
                            "automation_id": "edp_conta_luz_es",
                            "provider": "edp",
                            "unit_id": "casa-paraju",
                            "reference_month": "2026-05",
                            "status": "pendente",
                            "amount": "",
                            "due_date": "",
                            "barcode": "",
                        }
                    }
                ),
            ),
            {},
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1101),
        )
    )

    assert output["status"] == "completed"
    assert output["notification_state"] == "pending_no_barcode"
    assert output["conditions"]["notification_state"] == "pending_no_barcode"
    assert output["conditions"]["should_notify"] is True
    assert output["barcode_detected"] is False


def test_financial_bill_store_no_pending_bill_path_emits_no_pending_bills_state(monkeypatch):
    flow_module = _import_any("flows.flow_engine")
    handler_cls = _get_attr_any(flow_module, "FinancialBillStoreStepHandler")
    import services.financial_automation_service as financial_service

    def fail_upsert(*_args, **_kwargs):
        raise AssertionError("no pending bill runs must not upsert an empty utility bill")

    monkeypatch.setattr(financial_service.FinancialAutomationService, "_upsert_bill", fail_upsert)

    handler = handler_cls(db=SimpleNamespace(), mcp_sender=SimpleNamespace())
    output = asyncio.run(
        handler.execute(
            SimpleNamespace(
                id=19,
                timeout_seconds=30,
                config_json=json.dumps(
                    {
                        "financial_bill": {
                            "record_kind": "utility_bill",
                            "automation_id": "medsenior_samedil_plano_saude_mae",
                            "provider": "medsenior",
                            "unit_id": "Plano Saude Mae",
                            "status": "no_pending_bills",
                            "barcode": "",
                            "amount": "",
                        }
                    }
                ),
            ),
            {},
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=1102),
        )
    )

    assert output["status"] == "skipped"
    assert output["notification_state"] == "no_pending_bills"
    assert output["conditions"]["notification_state"] == "no_pending_bills"
    assert output["conditions"]["should_notify"] is False
    assert output["conditions"]["no_open_bills"] is True


# =============================================================================
# Notification step — state-aware template selection
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
                    "asset": "EDP Casa Paraju",
                    "notification_state": "pending_no_barcode",
                }
            },
            SimpleNamespace(id=99, tenant_id="tenant-a"),
            SimpleNamespace(id=2001),
        )
    )

    assert output["status"] == "completed"
    assert "Conta em aberto sem linha digitável: EDP Casa Paraju" in captured["message"]
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
