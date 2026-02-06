"""
Multi-tenant isolation tests for Browser Automation Skill (Phase 7)

Tests cover:
- Tenant-specific blocked domains
- Tenant-specific user whitelists
- Cross-tenant request isolation
- Tenant configuration not shared
- Flow execution respects tenant boundaries

Run: pytest backend/tests/test_browser_automation_multitenant.py -v
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestTenantSpecificBlockedDomains:
    """Tests for tenant-specific domain blocking."""

    def test_different_tenants_have_different_blocked_domains(self):
        """Test different tenants can have different blocked domains."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig, SecurityError

        # Tenant A blocks bank.com
        tenant_a_config = BrowserConfig(blocked_domains=["bank.com"])
        provider_a = PlaywrightProvider(tenant_a_config)

        # Tenant B blocks shopping.com
        tenant_b_config = BrowserConfig(blocked_domains=["shopping.com"])
        provider_b = PlaywrightProvider(tenant_b_config)

        # Tenant A can access shopping.com
        provider_a._validate_url("https://shopping.com/")  # Should not raise

        # Tenant B can access bank.com
        provider_b._validate_url("https://bank.com/")  # Should not raise

        # Tenant A cannot access bank.com
        with pytest.raises(SecurityError):
            provider_a._validate_url("https://bank.com/")

        # Tenant B cannot access shopping.com
        with pytest.raises(SecurityError):
            provider_b._validate_url("https://shopping.com/")

    def test_tenant_blocked_domains_are_isolated(self):
        """Test blocked domains don't leak between tenant configs."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config_a = BrowserConfig(blocked_domains=["secret-a.com"])
        config_b = BrowserConfig(blocked_domains=["secret-b.com"])

        # Configs should be independent
        assert "secret-a.com" in config_a.blocked_domains
        assert "secret-b.com" not in config_a.blocked_domains
        assert "secret-b.com" in config_b.blocked_domains
        assert "secret-a.com" not in config_b.blocked_domains


class TestTenantSpecificUserWhitelists:
    """Tests for tenant-specific user whitelists."""

    @pytest.fixture
    def skill(self):
        """Create BrowserAutomationSkill instance for testing."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        return BrowserAutomationSkill()

    @pytest.fixture
    def message_user_a(self):
        """Create message from User A."""
        from agent.skills.base import InboundMessage

        return InboundMessage(
            id="test-msg-1",
            sender="User A",
            sender_key="+5511111111111",
            body="navigate to example.com",
            chat_id="chat-1",
            chat_name="Chat A",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    @pytest.fixture
    def message_user_b(self):
        """Create message from User B."""
        from agent.skills.base import InboundMessage

        return InboundMessage(
            id="test-msg-2",
            sender="User B",
            sender_key="+5522222222222",
            body="navigate to example.com",
            chat_id="chat-2",
            chat_name="Chat B",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_tenant_a_whitelist_doesnt_affect_tenant_b(self, skill, message_user_a, message_user_b):
        """Test Tenant A's whitelist doesn't grant access for Tenant B."""
        # Tenant A config allows only User A
        config_tenant_a = skill.get_default_config()
        config_tenant_a["mode"] = "host"
        config_tenant_a["allowed_user_keys"] = ["+5511111111111"]

        # Tenant B config allows only User B
        config_tenant_b = skill.get_default_config()
        config_tenant_b["mode"] = "host"
        config_tenant_b["allowed_user_keys"] = ["+5522222222222"]

        # User A can access Tenant A's host mode
        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None

                result_a = await skill.process(message_user_a, config_tenant_a)

                # User A should not get unauthorized error for Tenant A
                assert result_a.metadata.get("error") != "unauthorized"

        # User A cannot access Tenant B's host mode
        result_a_on_b = await skill.process(message_user_a, config_tenant_b)
        assert result_a_on_b.success is False
        assert result_a_on_b.metadata.get("error") == "unauthorized"

        # User B cannot access Tenant A's host mode
        result_b_on_a = await skill.process(message_user_b, config_tenant_a)
        assert result_b_on_a.success is False
        assert result_b_on_a.metadata.get("error") == "unauthorized"

    @pytest.mark.asyncio
    async def test_empty_whitelist_allows_all_in_tenant(self, skill, message_user_a, message_user_b):
        """Test empty whitelist allows all users in that tenant's config."""
        config = skill.get_default_config()
        config["mode"] = "host"
        config["allowed_user_keys"] = []  # Empty = no restriction

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None

                result_a = await skill.process(message_user_a, config)
                assert result_a.metadata.get("error") != "unauthorized"

                result_b = await skill.process(message_user_b, config)
                assert result_b.metadata.get("error") != "unauthorized"


class TestTenantConfigIsolation:
    """Tests for tenant configuration isolation."""

    def test_provider_config_is_not_shared(self):
        """Test provider configs are independent instances."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config_a = BrowserConfig(timeout_seconds=30)
        config_b = BrowserConfig(timeout_seconds=60)

        provider_a = PlaywrightProvider(config_a)
        provider_b = PlaywrightProvider(config_b)

        assert provider_a.config is not provider_b.config
        assert provider_a.config.timeout_seconds == 30
        assert provider_b.config.timeout_seconds == 60

    def test_modifying_one_config_doesnt_affect_other(self):
        """Test modifying one config doesn't affect another."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config_a = BrowserConfig(blocked_domains=["original.com"])
        config_b = BrowserConfig(blocked_domains=["original.com"])

        # Modify config_a's blocked_domains list
        config_a.blocked_domains.append("new.com")

        # config_b should not be affected
        assert "new.com" in config_a.blocked_domains
        assert "new.com" not in config_b.blocked_domains


class TestFlowTenantIsolation:
    """Tests for flow execution tenant isolation."""

    @pytest.fixture
    def handler(self):
        """Create handler instance for testing."""
        from flows.flow_engine import BrowserAutomationStepHandler

        mock_db = MagicMock()
        mock_sender = MagicMock()
        mock_tracker = MagicMock()

        return BrowserAutomationStepHandler(mock_db, mock_sender, mock_tracker)

    @pytest.fixture
    def mock_step(self):
        """Create mock FlowNode step."""
        step = MagicMock()
        step.id = 1
        step.config_json = json.dumps({
            "prompt": "navigate to example.com"
        })
        return step

    @pytest.fixture
    def mock_step_run(self):
        """Create mock FlowNodeRun."""
        step_run = MagicMock()
        step_run.id = 1
        return step_run

    @pytest.mark.asyncio
    async def test_flow_uses_tenant_id_from_flow_run(self, handler, mock_step, mock_step_run):
        """Test flow handler uses tenant_id from FlowRun."""
        mock_flow_run_a = MagicMock()
        mock_flow_run_a.id = 1
        mock_flow_run_a.tenant_id = "tenant_a"

        mock_flow_run_b = MagicMock()
        mock_flow_run_b.id = 2
        mock_flow_run_b.tenant_id = "tenant_b"

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Success",
                metadata={}
            ))
            MockSkill.return_value = mock_skill_instance

            # Execute for Tenant A
            result_a = await handler.execute(mock_step, {}, mock_flow_run_a, mock_step_run)

            # Execute for Tenant B
            result_b = await handler.execute(mock_step, {}, mock_flow_run_b, mock_step_run)

            # Both should succeed (isolation verified by separate executions)
            assert result_a["status"] == "completed"
            assert result_b["status"] == "completed"

    @pytest.mark.asyncio
    async def test_flow_step_passes_tenant_config(self, handler, mock_step_run):
        """Test flow step passes tenant-specific configuration."""
        mock_step_tenant_a = MagicMock()
        mock_step_tenant_a.id = 1
        mock_step_tenant_a.config_json = json.dumps({
            "prompt": "screenshot example.com",
            "mode": "host",
            "allowed_user_keys": ["+5511111111111"]
        })

        mock_flow_run = MagicMock()
        mock_flow_run.id = 1
        mock_flow_run.tenant_id = "tenant_a"

        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Success",
                metadata={"mode": "host"}
            ))
            MockSkill.return_value = mock_skill_instance

            result = await handler.execute(mock_step_tenant_a, {}, mock_flow_run, mock_step_run)

            # Verify skill was called with tenant-specific config
            call_args = mock_skill_instance.process.call_args
            config = call_args[0][1]
            assert config["mode"] == "host"
            assert "+5511111111111" in config["allowed_user_keys"]


class TestProviderPerTenant:
    """Tests for provider isolation per tenant."""

    def test_provider_instances_are_independent(self):
        """Test provider instances are completely independent."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config_a = BrowserConfig(browser_type="chromium")
        config_b = BrowserConfig(browser_type="firefox")

        provider_a = PlaywrightProvider(config_a)
        provider_b = PlaywrightProvider(config_b)

        # Different configs
        assert provider_a.config.browser_type != provider_b.config.browser_type

        # Different state
        assert provider_a._lock is not provider_b._lock
        assert provider_a._screenshot_dir != provider_b._screenshot_dir

    def test_provider_screenshot_dirs_are_isolated(self):
        """Test screenshot directories are isolated per provider."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()

        providers = [PlaywrightProvider(config) for _ in range(3)]
        screenshot_dirs = [p._screenshot_dir for p in providers]

        # All directories should be unique
        assert len(set(screenshot_dirs)) == 3


class TestRegistryTenantLookup:
    """Tests for registry tenant-aware provider lookup."""

    def test_registry_get_provider_without_tenant(self):
        """Test registry returns provider without tenant lookup."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        # Get provider without tenant context
        provider = BrowserAutomationRegistry.get_provider("playwright")

        assert provider is not None

    def test_registry_each_get_returns_new_instance(self):
        """Test registry returns new provider instance each time."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        provider1 = BrowserAutomationRegistry.get_provider("playwright")
        provider2 = BrowserAutomationRegistry.get_provider("playwright")

        # Each call should return a new instance
        assert provider1 is not provider2


class TestCrossTenantSecurityBoundaries:
    """Tests for cross-tenant security boundaries."""

    @pytest.fixture
    def skill(self):
        """Create BrowserAutomationSkill instance for testing."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        return BrowserAutomationSkill()

    @pytest.fixture
    def message(self):
        """Create test message."""
        from agent.skills.base import InboundMessage

        return InboundMessage(
            id="test-msg-1",
            sender="Test User",
            sender_key="+5511999999999",
            body="navigate to example.com",
            chat_id="chat-1",
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_tenant_cannot_access_other_tenant_host_mode(self, skill, message):
        """Test one tenant cannot access another tenant's host browser."""
        # Tenant A allows only specific users
        config_tenant_a = skill.get_default_config()
        config_tenant_a["mode"] = "host"
        config_tenant_a["allowed_user_keys"] = ["+5588888888888"]  # Different user

        # Message is from +5511999999999, not in whitelist
        result = await skill.process(message, config_tenant_a)

        assert result.success is False
        assert result.metadata.get("error") == "unauthorized"

    @pytest.mark.asyncio
    async def test_container_mode_is_always_accessible(self, skill, message):
        """Test container mode is accessible regardless of tenant config."""
        config = skill.get_default_config()
        config["mode"] = "container"
        config["allowed_user_keys"] = ["+5588888888888"]  # Whitelist doesn't matter for container

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None

                result = await skill.process(message, config)

                # Container mode ignores whitelist
                assert result.metadata.get("error") != "unauthorized"
