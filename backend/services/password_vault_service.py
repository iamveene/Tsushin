"""Password Vault provider service.

The public contract is provider-shaped and secret-safe. Callers get metadata,
redacted previews, or short-lived handles; raw secret values stay inside this
service boundary for trusted executors.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import PasswordVaultIntegration, PasswordVaultSecretOverride
from services.encryption_key_service import get_api_key_encryption_key


class PasswordVaultError(RuntimeError):
    """Raised for user-actionable password vault failures."""


def normalize_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def token_preview(token: str) -> str:
    value = str(token or "")
    if len(value) <= 10:
        return f"{value[:3]}..."
    return f"{value[:5]}...{value[-4:]}"


def redacted_preview(value: Optional[str]) -> str:
    if not value:
        return "[REDACTED]"
    return f"[REDACTED:{len(value)}]"


_SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "client_secret",
    "credential",
    "cvv",
    "otp",
    "password",
    "secret",
    "secret_value",
    "service_account_token",
    "token",
    "value",
}

_HANDLE_KEYS = {
    "secret_handle",
    "raw_response_handle",
    "raw_browser_result_handle",
    "raw_bill_handle",
    "financial_record_handle",
    "financial_bill_handle",
}


def redact_payload(payload: Any) -> Any:
    """Recursively redact secret-looking values from provider/skill outputs."""
    if isinstance(payload, dict):
        redacted: Dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in _HANDLE_KEYS and isinstance(value, str) and value.startswith("pvh_"):
                redacted[key] = value
            elif any(marker in lowered for marker in _SENSITIVE_KEYS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_payload(value)
        return redacted
    if isinstance(payload, list):
        return [redact_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact_payload(item) for item in payload)
    if isinstance(payload, str) and payload.strip().lower().startswith("op://"):
        return "[REDACTED]"
    return payload


def _json_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item).strip() for item in parsed if str(item).strip()]


def _dump_json_list(values: Optional[Iterable[str]]) -> Optional[str]:
    cleaned = [str(item).strip() for item in (values or []) if str(item).strip()]
    return json.dumps(cleaned) if cleaned else None


def get_password_vault_encryptor(db: Session) -> TokenEncryption:
    master_key = get_api_key_encryption_key(db)
    if not master_key:
        raise PasswordVaultError("missing_password_vault_encryption_key")
    return TokenEncryption(master_key.encode())


def encrypt_vault_token(db: Session, tenant_id: str, plaintext: str) -> str:
    return get_password_vault_encryptor(db).encrypt(plaintext, tenant_id)


def decrypt_vault_token(db: Session, tenant_id: str, encrypted: Optional[str]) -> Optional[str]:
    if not encrypted:
        return None
    return get_password_vault_encryptor(db).decrypt(encrypted, tenant_id)


@dataclass(frozen=True)
class SecretHandle:
    handle: str
    expires_at: float
    value: str
    metadata: Dict[str, Any]


class SecretHandleRegistry:
    """Small in-process TTL store for trusted programmatic handoff."""

    _handles: Dict[str, SecretHandle] = {}
    _ttl_seconds = 300

    @classmethod
    def issue(cls, value: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        cls._prune()
        handle = "pvh_" + secrets.token_urlsafe(24)
        expires_at = time.time() + cls._ttl_seconds
        cls._handles[handle] = SecretHandle(
            handle=handle,
            expires_at=expires_at,
            value=value,
            metadata={k: v for k, v in metadata.items() if k != "value"},
        )
        return {
            "secret_handle": handle,
            "expires_at": datetime.utcfromtimestamp(expires_at).isoformat() + "Z",
            "ttl_seconds": cls._ttl_seconds,
        }

    @classmethod
    def resolve(cls, handle: str) -> str:
        cls._prune()
        entry = cls._handles.get(handle)
        if not entry:
            raise PasswordVaultError("secret_handle_not_found_or_expired")
        return entry.value

    @classmethod
    def resolve_for_tenant(cls, handle: str, tenant_id: Optional[str]) -> str:
        cls._prune()
        entry = cls._handles.get(handle)
        if not entry:
            raise PasswordVaultError("secret_handle_not_found_or_expired")
        handle_tenant = (entry.metadata or {}).get("tenant_id")
        if tenant_id and handle_tenant and handle_tenant != tenant_id:
            raise PasswordVaultError("secret_handle_tenant_mismatch")
        return entry.value

    @classmethod
    def _prune(cls) -> None:
        now = time.time()
        expired = [key for key, item in cls._handles.items() if item.expires_at <= now]
        for key in expired:
            cls._handles.pop(key, None)


class OnePasswordProvider:
    provider = "onepassword"

    def __init__(self, token: str, *, op_bin: Optional[str] = None) -> None:
        if not token:
            raise PasswordVaultError("1Password service account token is not configured")
        self.token = token
        self.op_bin = op_bin or os.getenv("OP_BIN") or "op"

    def _run(self, args: List[str], timeout: int = 20) -> str:
        env = {**os.environ, "OP_SERVICE_ACCOUNT_TOKEN": self.token}
        try:
            completed = subprocess.run(
                [self.op_bin, *args],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
                text=True,
            )
        except FileNotFoundError as exc:
            raise PasswordVaultError("1Password CLI not available in this runtime") from exc
        except subprocess.TimeoutExpired as exc:
            raise PasswordVaultError("1Password CLI timed out") from exc

        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "1Password CLI failed").strip()
            raise PasswordVaultError(message[:500])
        return completed.stdout

    def list_vaults(self) -> List[Dict[str, Any]]:
        raw = self._run(["vault", "list", "--format", "json"])
        vaults = json.loads(raw or "[]")
        return [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "type": item.get("type"),
            }
            for item in vaults
        ]

    def list_items(self, vault: str) -> List[Dict[str, Any]]:
        raw = self._run(["item", "list", "--vault", vault, "--format", "json"])
        items = json.loads(raw or "[]")
        return [
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "category": item.get("category"),
                "tags": item.get("tags") or [],
                "updated_at": item.get("updated_at"),
            }
            for item in items
        ]

    def get_item(self, item_ref: str, vault: str) -> Dict[str, Any]:
        raw = self._run(["item", "get", item_ref, "--vault", vault, "--format", "json"])
        return json.loads(raw or "{}")

    def get_otp(self, item_ref: str, vault: str) -> str:
        raw = self._run(["item", "get", item_ref, "--otp", "--vault", vault])
        return raw.strip()


class PasswordVaultService:
    def __init__(self, db: Session, *, tenant_id: str) -> None:
        if not tenant_id:
            raise PasswordVaultError("tenant_id_required")
        self.db = db
        self.tenant_id = tenant_id

    @staticmethod
    def serialize_allowed_items(values: Optional[Iterable[str]]) -> Optional[str]:
        return _dump_json_list(values)

    @staticmethod
    def serialize_allowed_fields(values: Optional[Iterable[str]]) -> Optional[str]:
        return _dump_json_list(values)

    @staticmethod
    def allowed_items(integration: PasswordVaultIntegration) -> List[str]:
        return _json_list(integration.allowed_items_json)

    @staticmethod
    def allowed_fields(integration: PasswordVaultIntegration) -> List[str]:
        return _json_list(integration.allowed_fields_json)

    def load_integration(
        self,
        integration_id: int,
        *,
        require_active: bool = False,
    ) -> PasswordVaultIntegration:
        query = self.db.query(PasswordVaultIntegration).filter(
            PasswordVaultIntegration.id == integration_id,
            PasswordVaultIntegration.tenant_id == self.tenant_id,
            PasswordVaultIntegration.type == "password_vault",
        )
        if require_active:
            query = query.filter(PasswordVaultIntegration.is_active == True)  # noqa: E712
        integration = query.first()
        if integration is None:
            raise PasswordVaultError("password_vault_integration_not_found")
        return integration

    def _provider(self, integration: PasswordVaultIntegration) -> OnePasswordProvider:
        provider = (integration.provider or "onepassword").strip().lower()
        if provider != "onepassword":
            raise PasswordVaultError(f"Unsupported password vault provider: {provider}")
        token = decrypt_vault_token(self.db, self.tenant_id, integration.token_encrypted)
        return OnePasswordProvider(token or "")

    def _vault(self, integration: PasswordVaultIntegration, vault: Optional[str] = None) -> str:
        resolved = (
            normalize_optional(vault)
            or normalize_optional(integration.default_vault)
            or normalize_optional(integration.default_vault_id)
        )
        if not resolved:
            raise PasswordVaultError("vault_required")
        return resolved

    def _check_item_scope(self, integration: PasswordVaultIntegration, item_ref: str) -> None:
        allowed = self.allowed_items(integration)
        if allowed and item_ref not in allowed:
            raise PasswordVaultError("item_not_allowed_by_integration_scope")

    def _check_field_scope(self, integration: PasswordVaultIntegration, field_name: Optional[str]) -> None:
        allowed = self.allowed_fields(integration)
        if allowed and field_name and field_name not in allowed:
            raise PasswordVaultError("field_not_allowed_by_integration_scope")

    def _override_query(
        self,
        integration: PasswordVaultIntegration,
        *,
        item_ref: str,
        field_name: str,
        vault: Optional[str] = None,
    ):
        resolved_vault = normalize_optional(vault)
        query = self.db.query(PasswordVaultSecretOverride).filter(
            PasswordVaultSecretOverride.tenant_id == self.tenant_id,
            PasswordVaultSecretOverride.integration_id == integration.id,
            PasswordVaultSecretOverride.item_ref == item_ref,
            PasswordVaultSecretOverride.field_name == field_name,
        )
        if resolved_vault is None:
            query = query.filter(PasswordVaultSecretOverride.vault.is_(None))
        else:
            query = query.filter(PasswordVaultSecretOverride.vault == resolved_vault)
        return query

    def _read_override_value(
        self,
        integration: PasswordVaultIntegration,
        *,
        item_ref: str,
        field_name: str,
        vault: Optional[str] = None,
        item_aliases: Optional[List[str]] = None,
        vault_aliases: Optional[List[str]] = None,
    ) -> Optional[str]:
        item_candidates = [
            candidate for candidate in dict.fromkeys(
                [normalize_optional(item_ref), *(normalize_optional(alias) for alias in (item_aliases or []))]
            )
            if candidate
        ]
        vault_candidates = [
            candidate for candidate in dict.fromkeys(
                [
                    normalize_optional(vault),
                    normalize_optional(integration.default_vault),
                    normalize_optional(integration.default_vault_id),
                    *(normalize_optional(alias) for alias in (vault_aliases or [])),
                ]
            )
            if candidate
        ]
        rows = self.db.query(PasswordVaultSecretOverride).filter(
            PasswordVaultSecretOverride.tenant_id == self.tenant_id,
            PasswordVaultSecretOverride.integration_id == integration.id,
            PasswordVaultSecretOverride.field_name == field_name,
        ).all()
        matches = [
            row for row in rows
            if row.item_ref in item_candidates
            and (row.vault is None or row.vault in vault_candidates)
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda row: (
                2 if row.item_ref == item_ref else 1,
                2 if row.vault == normalize_optional(vault) else 1 if row.vault else 0,
                row.updated_at or row.created_at or datetime.min,
            ),
            reverse=True,
        )
        override = matches[0]
        return decrypt_vault_token(self.db, self.tenant_id, override.value_encrypted)

    def list_secret_overrides(self, integration: PasswordVaultIntegration) -> List[Dict[str, Any]]:
        rows = self.db.query(PasswordVaultSecretOverride).filter(
            PasswordVaultSecretOverride.tenant_id == self.tenant_id,
            PasswordVaultSecretOverride.integration_id == integration.id,
        ).order_by(
            PasswordVaultSecretOverride.vault.asc().nullsfirst(),
            PasswordVaultSecretOverride.item_ref.asc(),
            PasswordVaultSecretOverride.field_name.asc(),
        ).all()
        return [self.serialize_secret_override(row) for row in rows]

    @staticmethod
    def serialize_secret_override(row: PasswordVaultSecretOverride) -> Dict[str, Any]:
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "integration_id": row.integration_id,
            "vault": row.vault,
            "item_ref": row.item_ref,
            "field_name": row.field_name,
            "field_type": row.field_type,
            "value_preview": row.value_preview or "[REDACTED]",
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def upsert_secret_override(
        self,
        integration: PasswordVaultIntegration,
        *,
        item_ref: str,
        field_name: str,
        value: str,
        vault: Optional[str] = None,
        field_type: str = "CONCEALED",
    ) -> PasswordVaultSecretOverride:
        item_ref = normalize_optional(item_ref) or ""
        field_name = normalize_optional(field_name) or ""
        if not item_ref or not field_name:
            raise PasswordVaultError("item_ref_and_field_name_required")
        if value is None or str(value) == "":
            raise PasswordVaultError("secret_value_required")
        self._check_item_scope(integration, item_ref)
        self._check_field_scope(integration, field_name)
        normalized_vault = normalize_optional(vault)
        normalized_type = (normalize_optional(field_type) or "CONCEALED").upper()
        row = self._override_query(
            integration,
            item_ref=item_ref,
            field_name=field_name,
            vault=normalized_vault,
        ).first()
        if row is None:
            row = PasswordVaultSecretOverride(
                tenant_id=self.tenant_id,
                integration_id=integration.id,
                vault=normalized_vault,
                item_ref=item_ref,
                field_name=field_name,
            )
        row.field_type = normalized_type
        row.value_encrypted = encrypt_vault_token(self.db, self.tenant_id, str(value))
        row.value_preview = redacted_preview(str(value))
        row.updated_at = datetime.utcnow()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_secret_override(
        self,
        integration: PasswordVaultIntegration,
        secret_id: int,
        *,
        item_ref: Optional[str] = None,
        field_name: Optional[str] = None,
        value: Optional[str] = None,
        vault: Optional[str] = None,
        field_type: Optional[str] = None,
    ) -> PasswordVaultSecretOverride:
        row = self.db.query(PasswordVaultSecretOverride).filter(
            PasswordVaultSecretOverride.id == secret_id,
            PasswordVaultSecretOverride.tenant_id == self.tenant_id,
            PasswordVaultSecretOverride.integration_id == integration.id,
        ).first()
        if row is None:
            raise PasswordVaultError("managed_secret_field_not_found")
        if item_ref is not None:
            row.item_ref = normalize_optional(item_ref) or row.item_ref
        if field_name is not None:
            row.field_name = normalize_optional(field_name) or row.field_name
        if vault is not None:
            row.vault = normalize_optional(vault)
        if field_type is not None:
            row.field_type = (normalize_optional(field_type) or "CONCEALED").upper()
        self._check_item_scope(integration, row.item_ref)
        self._check_field_scope(integration, row.field_name)
        if value is not None:
            if str(value) == "":
                raise PasswordVaultError("secret_value_required")
            row.value_encrypted = encrypt_vault_token(self.db, self.tenant_id, str(value))
            row.value_preview = redacted_preview(str(value))
        row.updated_at = datetime.utcnow()
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def delete_secret_override(self, integration: PasswordVaultIntegration, secret_id: int) -> None:
        row = self.db.query(PasswordVaultSecretOverride).filter(
            PasswordVaultSecretOverride.id == secret_id,
            PasswordVaultSecretOverride.tenant_id == self.tenant_id,
            PasswordVaultSecretOverride.integration_id == integration.id,
        ).first()
        if row is None:
            raise PasswordVaultError("managed_secret_field_not_found")
        self.db.delete(row)
        self.db.commit()

    def test_connection(self, integration: PasswordVaultIntegration) -> Dict[str, Any]:
        provider = self._provider(integration)
        vaults = provider.list_vaults()
        configured_vault = integration.default_vault
        has_configured_vault = any(v.get("name") == configured_vault or v.get("id") == integration.default_vault_id for v in vaults)
        integration.last_health_check = datetime.utcnow()
        integration.health_status = "healthy" if vaults else "degraded"
        integration.health_status_reason = None if vaults else "No vaults returned by provider"
        self.db.add(integration)
        self.db.commit()
        return {
            "success": True,
            "provider": integration.provider,
            "vault_count": len(vaults),
            "configured_vault_found": has_configured_vault,
            "vaults": vaults,
        }

    def list_vaults(self, integration: PasswordVaultIntegration) -> List[Dict[str, Any]]:
        if not integration.allow_metadata_read:
            raise PasswordVaultError("metadata_read_not_allowed")
        return self._provider(integration).list_vaults()

    def list_items(self, integration: PasswordVaultIntegration, *, vault: Optional[str] = None) -> List[Dict[str, Any]]:
        if not integration.allow_metadata_read:
            raise PasswordVaultError("metadata_read_not_allowed")
        resolved_vault = self._vault(integration, vault)
        items = self._provider(integration).list_items(resolved_vault)
        allowed = set(self.allowed_items(integration))
        if allowed:
            items = [item for item in items if item.get("title") in allowed or item.get("id") in allowed]
        return items

    def read_field(
        self,
        integration: PasswordVaultIntegration,
        *,
        item_ref: str,
        field_name: str,
        vault: Optional[str] = None,
        issue_handle: bool = True,
    ) -> Dict[str, Any]:
        if not integration.allow_secret_read:
            raise PasswordVaultError("secret_read_not_allowed")
        item_ref = normalize_optional(item_ref) or ""
        field_name = normalize_optional(field_name) or ""
        if not item_ref or not field_name:
            raise PasswordVaultError("item_ref_and_field_name_required")
        self._check_item_scope(integration, item_ref)
        self._check_field_scope(integration, field_name)
        resolved_vault = self._vault(integration, vault)
        value = None
        provider_error: Optional[Exception] = None
        item: Optional[Dict[str, Any]] = None
        try:
            item = self._provider(integration).get_item(item_ref, resolved_vault)
            value = self._extract_field_value(item, field_name)
        except Exception as exc:
            provider_error = exc
        if value is None:
            value = self._read_override_value(
                integration,
                item_ref=item_ref,
                field_name=field_name,
                vault=resolved_vault,
                item_aliases=[item.get("title"), item.get("id")] if item else None,
            )
        if value is None:
            if provider_error and not isinstance(provider_error, PasswordVaultError):
                raise PasswordVaultError(str(provider_error)) from provider_error
            raise PasswordVaultError("field_not_found")
        result = {
            "success": True,
            "provider": integration.provider,
            "integration_id": integration.id,
            "vault": resolved_vault,
            "item_ref": item_ref,
            "field_name": field_name,
            "value_preview": redacted_preview(value),
            "redacted": True,
        }
        if issue_handle:
            result.update(SecretHandleRegistry.issue(value, {**result, "tenant_id": self.tenant_id}))
        return result

    def compose_basic_auth(
        self,
        *,
        username_handle: str,
        password_handle: str,
        scheme: str = "Basic",
        issue_handle: bool = True,
    ) -> Dict[str, Any]:
        if not username_handle or not password_handle:
            raise PasswordVaultError("username_handle_and_password_handle_required")
        resolved_scheme = normalize_optional(scheme) or "Basic"
        if resolved_scheme.lower() != "basic":
            raise PasswordVaultError("unsupported_composed_secret_scheme")
        username = SecretHandleRegistry.resolve_for_tenant(str(username_handle), self.tenant_id)
        password = SecretHandleRegistry.resolve_for_tenant(str(password_handle), self.tenant_id)
        return self.compose_basic_auth_values(
            username=username,
            password=password,
            scheme=resolved_scheme,
            issue_handle=issue_handle,
        )

    def compose_basic_auth_values(
        self,
        *,
        username: str,
        password: str,
        scheme: str = "Basic",
        issue_handle: bool = True,
    ) -> Dict[str, Any]:
        resolved_scheme = normalize_optional(scheme) or "Basic"
        if resolved_scheme.lower() != "basic":
            raise PasswordVaultError("unsupported_composed_secret_scheme")
        if not username or not password:
            raise PasswordVaultError("composed_secret_source_empty")
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        value = f"Basic {token}"
        result = {
            "success": True,
            "provider": "password_vault",
            "operation": "compose_basic_auth",
            "scheme": "Basic",
            "value_preview": redacted_preview(value),
            "redacted": True,
        }
        if issue_handle:
            result.update(SecretHandleRegistry.issue(value, {**result, "tenant_id": self.tenant_id}))
        return result

    def resolve_field_value(
        self,
        integration: PasswordVaultIntegration,
        *,
        item_ref: str,
        field_name: str,
        vault: Optional[str] = None,
    ) -> str:
        """Return a raw field value for trusted in-process executors only."""
        if not integration.allow_secret_read:
            raise PasswordVaultError("secret_read_not_allowed")
        item_ref = normalize_optional(item_ref) or ""
        field_name = normalize_optional(field_name) or ""
        if not item_ref or not field_name:
            raise PasswordVaultError("item_ref_and_field_name_required")
        self._check_item_scope(integration, item_ref)
        self._check_field_scope(integration, field_name)
        resolved_vault = self._vault(integration, vault)
        value = None
        provider_error: Optional[Exception] = None
        item: Optional[Dict[str, Any]] = None
        try:
            item = self._provider(integration).get_item(item_ref, resolved_vault)
            value = self._extract_field_value(item, field_name)
        except Exception as exc:
            provider_error = exc
        if value is None:
            value = self._read_override_value(
                integration,
                item_ref=item_ref,
                field_name=field_name,
                vault=resolved_vault,
                item_aliases=[item.get("title"), item.get("id")] if item else None,
            )
        if value is None:
            if provider_error and not isinstance(provider_error, PasswordVaultError):
                raise PasswordVaultError(str(provider_error)) from provider_error
            raise PasswordVaultError("field_not_found")
        return value

    def read_totp(
        self,
        integration: PasswordVaultIntegration,
        *,
        item_ref: str,
        vault: Optional[str] = None,
        issue_handle: bool = True,
    ) -> Dict[str, Any]:
        if not integration.allow_totp_read:
            raise PasswordVaultError("totp_read_not_allowed")
        item_ref = normalize_optional(item_ref) or ""
        if not item_ref:
            raise PasswordVaultError("item_ref_required")
        self._check_item_scope(integration, item_ref)
        resolved_vault = self._vault(integration, vault)
        value = self._provider(integration).get_otp(item_ref, resolved_vault)
        if not value:
            raise PasswordVaultError("otp_not_found")
        result = {
            "success": True,
            "provider": integration.provider,
            "integration_id": integration.id,
            "vault": resolved_vault,
            "item_ref": item_ref,
            "field_name": "otp",
            "value_preview": redacted_preview(value),
            "redacted": True,
        }
        if issue_handle:
            result.update(SecretHandleRegistry.issue(value, {**result, "tenant_id": self.tenant_id}))
        return result

    @staticmethod
    def _extract_field_value(item: Dict[str, Any], field_name: str) -> Optional[str]:
        wanted = field_name.strip().lower()
        for field in item.get("fields") or []:
            labels = [
                field.get("label"),
                field.get("id"),
                field.get("type"),
                field.get("purpose"),
            ]
            for label in labels:
                if label and str(label).strip().lower() == wanted:
                    value = field.get("value")
                    return str(value) if value is not None else None
        if wanted == "username":
            for field in item.get("fields") or []:
                if field.get("purpose") == "USERNAME" and field.get("value"):
                    return str(field.get("value"))
        if wanted == "password":
            for field in item.get("fields") or []:
                if field.get("purpose") == "PASSWORD" and field.get("value"):
                    return str(field.get("value"))
        return None
