import sys
import types
import asyncio

# The hub package imports the broader services package during collection, and
# that path only needs the docker type surface here. Keep this regression test
# focused on TTS status routing instead of requiring a local Docker SDK install.
docker_stub = types.ModuleType("docker")
docker_stub.DockerClient = object
docker_stub.errors = types.SimpleNamespace(NotFound=Exception)
sys.modules.setdefault("docker", docker_stub)

from hub.providers.tts_provider import ProviderStatus, TTSProvider, TTSRequest, TTSResponse
from hub.providers.tts_registry import TTSProviderRegistry


class TenantAwareStatusProvider(TTSProvider):
    def get_provider_name(self) -> str:
        return "tenant_aware_status"

    def get_display_name(self) -> str:
        return "Tenant Aware Status"

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        return TTSResponse(success=True, provider=self.provider_name)

    def get_available_voices(self):
        return []

    async def health_check(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.provider_name,
            status="healthy" if self.tenant_id else "not_configured",
            message="tenant context checked",
            available=bool(self.tenant_id),
            details={"tenant_id": self.tenant_id},
        )


def test_tts_provider_status_receives_tenant_context():
    original_providers = TTSProviderRegistry._providers.copy()
    original_configs = TTSProviderRegistry._provider_configs.copy()
    try:
        TTSProviderRegistry.register_provider(
            "tenant_aware_status",
            TenantAwareStatusProvider,
            {"requires_api_key": True},
        )

        status = asyncio.run(
            TTSProviderRegistry.get_provider_status(
                "tenant_aware_status",
                db=None,
                tenant_id="tenant-status",
            )
        )

        assert status.available is True
        assert status.status == "healthy"
        assert status.details["tenant_id"] == "tenant-status"
    finally:
        TTSProviderRegistry._providers = original_providers
        TTSProviderRegistry._provider_configs = original_configs
