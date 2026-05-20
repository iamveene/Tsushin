import asyncio
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importing the hub package pulls in services that type-check Docker surfaces.
# This focused registry test does not need the Docker SDK installed locally.
docker_stub = types.ModuleType("docker")
docker_stub.DockerClient = object
docker_stub.errors = types.SimpleNamespace(NotFound=Exception)
sys.modules.setdefault("docker", docker_stub)

from hub.providers.search_provider import SearchProvider, SearchProviderStatus  # noqa: E402
from hub.providers.search_registry import SearchProviderRegistry  # noqa: E402


def test_search_provider_catalog_and_status_pass_tenant_context(monkeypatch):
    seen_tenants = []

    class TenantAwareProvider(SearchProvider):
        def __init__(self, db=None, token_tracker=None, tenant_id=None, load_credentials=True):
            super().__init__(
                db=db,
                token_tracker=token_tracker,
                tenant_id=tenant_id,
                load_credentials=load_credentials,
            )
            seen_tenants.append((tenant_id, load_credentials))

        def get_provider_name(self):
            return "tenant_fake"

        def get_display_name(self):
            return "Tenant Fake"

        async def search(self, request):
            raise AssertionError("search should not run during catalog/status checks")

        async def health_check(self):
            return SearchProviderStatus(
                provider="tenant_fake",
                status="healthy",
                message="ok",
                available=True,
            )

    monkeypatch.setattr(SearchProviderRegistry, "_providers", {"tenant_fake": TenantAwareProvider})
    monkeypatch.setattr(SearchProviderRegistry, "_provider_configs", {"tenant_fake": {}})

    providers = SearchProviderRegistry.list_providers(tenant_id="tenant-a")
    assert providers[0]["id"] == "tenant_fake"
    assert seen_tenants == [("tenant-a", False)]

    seen_tenants.clear()
    status = asyncio.run(
        SearchProviderRegistry.get_provider_status("tenant_fake", tenant_id="tenant-a")
    )
    assert status.available is True
    assert seen_tenants == [("tenant-a", True)]
