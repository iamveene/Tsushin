"""Generic Password Vault provider wrappers.

This module keeps the provider abstraction separate from the Hub integration
model. 1Password is the first implementation; other vaults can expose the same
methods without changing the Password Vault skill.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.password_vault_service import OnePasswordProvider, redact_payload


class OnePasswordVaultProvider:
    """Secret-safe facade around a 1Password client."""

    provider = "onepassword"

    def __init__(self, token: Optional[str] = None, client: Optional[Any] = None) -> None:
        self.client = client or OnePasswordProvider(token or "")

    def _wrap(self, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            wrapped = dict(result)
        else:
            wrapped = {"result": result}
        wrapped.setdefault("success", True)
        wrapped.setdefault("provider", self.provider)
        return redact_payload(wrapped)

    def test_connection(self) -> Dict[str, Any]:
        if hasattr(self.client, "test_connection"):
            return self._wrap(self.client.test_connection())
        return self._wrap({"vaults": self.client.list_vaults()})

    def list_items(self, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self.client, "list_items"):
            return self._wrap({"items": self.client.list_items(**kwargs)})
        return self._wrap({"items": []})

    def read_item(self, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self.client, "read_item"):
            return self._wrap(self.client.read_item(**kwargs))
        item_id = kwargs.get("item_id") or kwargs.get("item_ref")
        vault = kwargs.get("vault")
        return self._wrap({"item": self.client.get_item(item_id, vault)})

    def create_item(self, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self.client, "create_item"):
            return self._wrap(self.client.create_item(**kwargs))
        return self._wrap({"status": "unsupported"})

    def update_item(self, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self.client, "update_item"):
            return self._wrap(self.client.update_item(**kwargs))
        return self._wrap({"status": "unsupported"})

    def delete_item(self, **kwargs: Any) -> Dict[str, Any]:
        if hasattr(self.client, "delete_item"):
            return self._wrap(self.client.delete_item(**kwargs))
        return self._wrap({"status": "unsupported"})


PasswordVaultProvider = OnePasswordVaultProvider
