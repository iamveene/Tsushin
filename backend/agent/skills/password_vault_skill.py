"""Password Vault skill.

Provider-neutral agent skill for reading vault metadata and resolving secret
references through approved Password Vault integrations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from services.password_vault_service import PasswordVaultError, PasswordVaultService, redact_payload


_ACTION_ORDER: List[str] = [
    "list_items",
    "read_item",
    "compose_basic_auth",
    "read_totp",
    "test_connection",
    "create_item",
    "update_item",
    "delete_item",
]


class PasswordVaultSkill(BaseSkill):
    skill_type = "password_vault"
    skill_name = "Password Vault"
    skill_description = (
        "Use approved vault providers to list secret metadata and resolve "
        "secret references for flows, agents, and channels without exposing raw values."
    )
    execution_mode = "tool"
    wizard_visible = True

    async def can_handle(self, message: InboundMessage) -> bool:
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        return SkillResult(
            success=False,
            output="Password Vault is tool-only. Use the Password Vault operation tool.",
            metadata={"error": "raw_text_disabled"},
        )

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "enabled": True,
            "provider": "onepassword",
            "integration_id": None,
            "external_reveal_enabled": False,
            "capabilities": {
                "list_items": {"enabled": True, "label": "List item metadata"},
                "read_item": {"enabled": True, "label": "Read item fields as handles/redacted output"},
                "compose_basic_auth": {"enabled": True, "label": "Compose Basic Auth from two short-lived handles"},
                "read_totp": {"enabled": False, "label": "Read TOTP as a short-lived handle"},
                "test_connection": {"enabled": True, "label": "Test provider connection"},
                "create_item": {"enabled": False, "label": "Create vault item"},
                "update_item": {"enabled": False, "label": "Update vault item"},
                "delete_item": {"enabled": False, "label": "Delete vault item"},
            },
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "provider": {"type": "string", "enum": ["onepassword"], "default": "onepassword"},
                "integration_id": {"type": ["integer", "null"], "description": "Password Vault Hub integration id"},
                "external_reveal_enabled": {
                    "type": "boolean",
                    "default": False,
                    "description": "Allow secret reveals to external channels. Off by default.",
                },
            },
            "required": [],
        }

    def _enabled_actions(self, config: Optional[Dict[str, Any]] = None) -> List[str]:
        config = config or getattr(self, "_config", {}) or {}
        defaults = self.get_default_config().get("capabilities", {})
        overrides = config.get("capabilities", {}) or {}
        enabled: List[str] = []
        for action in _ACTION_ORDER:
            default_entry = defaults.get(action, {}) or {}
            override_entry = overrides.get(action, {}) or {}
            merged = {**default_entry, **override_entry}
            if merged.get("enabled", False):
                enabled.append(action)
        return enabled

    def _is_capability_enabled(self, config: Optional[Dict[str, Any]], action: str) -> bool:
        return action in set(self._enabled_actions(config))

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:  # type: ignore[override]
        return cls._build_mcp_tool_definition(_ACTION_ORDER)

    def get_per_agent_mcp_tool_definition(self) -> Optional[Dict[str, Any]]:
        actions = self._enabled_actions()
        if not actions:
            return None
        return self._build_mcp_tool_definition(actions)

    @classmethod
    def _build_mcp_tool_definition(cls, actions: List[str]) -> Dict[str, Any]:
        return {
            "name": "password_vault_operation",
            "title": "Password Vault",
            "description": "List vault item metadata or resolve approved secret references as redacted outputs/short-lived handles.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": actions,
                        "description": "Password Vault operation to perform.",
                    },
                    "integration_id": {
                        "type": "integer",
                        "description": "Optional Password Vault integration id; defaults to the agent skill assignment.",
                    },
                    "vault": {"type": "string", "description": "Optional vault name override."},
                    "item_id": {"type": "string", "description": "Vault item title or id."},
                    "item_ref": {"type": "string", "description": "Alias for item_id."},
                    "field_name": {"type": "string", "description": "Field label/id/purpose to resolve."},
                    "username_handle": {"type": "string", "description": "Short-lived handle for the Basic Auth username."},
                    "password_handle": {"type": "string", "description": "Short-lived handle for the Basic Auth password or customer code."},
                    "scheme": {"type": "string", "enum": ["Basic"], "description": "Composed authorization scheme."},
                },
                "required": ["action"],
            },
            "annotations": {
                "destructive": any(action in actions for action in ("create_item", "update_item", "delete_item")),
                "idempotent": not any(action in actions for action in ("create_item", "update_item", "delete_item")),
                "audience": ["user"],
            },
        }

    def to_openai_tool(self) -> Optional[Dict[str, Any]]:  # type: ignore[override]
        mcp_def = self.get_per_agent_mcp_tool_definition()
        if not mcp_def:
            return None
        return {
            "type": "function",
            "function": {
                "name": mcp_def["name"],
                "description": mcp_def["description"],
                "parameters": mcp_def["inputSchema"],
            },
        }

    def to_anthropic_tool(self) -> Optional[Dict[str, Any]]:  # type: ignore[override]
        mcp_def = self.get_per_agent_mcp_tool_definition()
        if not mcp_def:
            return None
        return {
            "name": mcp_def["name"],
            "description": mcp_def["description"],
            "input_schema": mcp_def["inputSchema"],
        }

    def _resolve_integration_id(self, config: Optional[Dict[str, Any]]) -> Optional[int]:
        config = config or getattr(self, "_config", {}) or {}
        integration_id = config.get("integration_id")
        if integration_id:
            try:
                return int(integration_id)
            except (TypeError, ValueError):
                return None
        agent_id = getattr(self, "_agent_id", None)
        if not agent_id or not self._db_session:
            return None
        try:
            from models import AgentSkillIntegration

            row = (
                self._db_session.query(AgentSkillIntegration)
                .filter(
                    AgentSkillIntegration.agent_id == agent_id,
                    AgentSkillIntegration.skill_type == self.skill_type,
                )
                .first()
            )
            if row and row.integration_id:
                return int(row.integration_id)
        except Exception:
            return None
        return None

    def _service_and_integration(self, config: Optional[Dict[str, Any]] = None):
        if not self._db_session:
            raise PasswordVaultError("Database session unavailable for Password Vault skill.")
        agent_id = getattr(self, "_agent_id", None)
        tenant_id = (config or {}).get("tenant_id")
        if not tenant_id and agent_id:
            from models import Agent

            agent = self._db_session.query(Agent).filter(Agent.id == agent_id).first()
            tenant_id = getattr(agent, "tenant_id", None)
        if not tenant_id:
            raise PasswordVaultError("Tenant context missing for Password Vault skill.")
        integration_id = self._resolve_integration_id(config)
        if not integration_id:
            raise PasswordVaultError("Password Vault integration not configured.")
        service = PasswordVaultService(self._db_session, tenant_id=tenant_id)
        integration = service.load_integration(integration_id, require_active=True)
        return service, integration

    def _get_provider(self, config: Optional[Dict[str, Any]] = None):
        """Test hook and compatibility shim for provider-level unit tests."""
        from hub.providers.password_vault_provider import OnePasswordVaultProvider

        service, integration = self._service_and_integration(config)
        provider = service._provider(integration)  # noqa: SLF001 - intentional internal adapter bridge
        return OnePasswordVaultProvider(client=provider)

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any],
    ) -> SkillResult:
        action = (arguments or {}).get("action")
        if not action or action not in _ACTION_ORDER:
            return SkillResult(
                success=False,
                output=f"Unknown action '{action}'. Use one of: {', '.join(_ACTION_ORDER)}.",
                metadata={"error": "invalid_action"},
            )
        if not self._is_capability_enabled(config, action):
            return SkillResult(
                success=False,
                output=(
                    f"Action '{action}' is disabled for this agent. "
                    "Ask an admin to enable it in the Password Vault skill settings. [REDACTED]"
                ),
                metadata={"error": "capability_disabled", "action": action, "capability": action},
            )

        try:
            if action == "read_item" and not (arguments or {}).get("field_name"):
                provider = self._get_provider({**(config or {}), **(arguments or {})})
                result = provider.read_item(
                    item_id=(arguments or {}).get("item_id") or (arguments or {}).get("item_ref"),
                    vault=(arguments or {}).get("vault"),
                )
                safe = redact_payload(result)
                return SkillResult(
                    success=bool(safe.get("success", True)),
                    output="Password Vault operation completed.",
                    metadata=safe,
                )

            service, integration = self._service_and_integration({**(config or {}), **(arguments or {})})
            if action == "test_connection":
                result = service.test_connection(integration)
            elif action == "list_items":
                result = {
                    "success": True,
                    "provider": integration.provider,
                    "items": service.list_items(integration, vault=arguments.get("vault")),
                    "redacted": True,
                }
            elif action == "read_totp":
                result = service.read_totp(
                    integration,
                    item_ref=arguments.get("item_ref") or arguments.get("item_id"),
                    vault=arguments.get("vault"),
                )
            elif action == "compose_basic_auth":
                result = service.compose_basic_auth(
                    username_handle=arguments.get("username_handle") or arguments.get("username_secret_handle"),
                    password_handle=arguments.get("password_handle") or arguments.get("password_secret_handle"),
                    scheme=arguments.get("scheme") or "Basic",
                )
            elif action == "read_item":
                field_name = arguments.get("field_name")
                if field_name:
                    result = service.read_field(
                        integration,
                        item_ref=arguments.get("item_ref") or arguments.get("item_id"),
                        field_name=field_name,
                        vault=arguments.get("vault"),
                    )
                else:
                    raise PasswordVaultError("field_name_required_for_service_read")
            else:
                # Future write actions are represented in the schema but remain
                # disabled by default and unsupported by the 1Password adapter.
                return SkillResult(
                    success=False,
                    output=f"Action '{action}' is not implemented for this provider.",
                    metadata={"error": "unsupported_action", "action": action},
                )
        except PasswordVaultError as exc:
            return SkillResult(success=False, output=str(exc), metadata={"error": str(exc)})
        except Exception as exc:
            return SkillResult(success=False, output="Password Vault operation failed.", metadata={"error": str(exc)[:200]})

        safe = redact_payload(result)
        return SkillResult(
            success=bool(safe.get("success", True)),
            output="Password Vault operation completed.",
            metadata=safe,
        )
