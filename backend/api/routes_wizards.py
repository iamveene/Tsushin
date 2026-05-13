"""Wizard manifest API.

v0.7.0-fix Phase 5 — exposes the platform's wizard registry over HTTP so
external SDKs / doc generators / integration scripts can discover the
guided creation flows without scraping the frontend `wizard-registry.ts`.

The registry stays small and curated by hand: every entry corresponds to
a top-level "+ Add ..." launcher in the UI. Each manifest declares which
backend catalog endpoint drives its picker step, which catalog module
defines the data, and which sub-wizards / modals it dispatches to. The
drift guard at `backend/tests/test_wizard_drift.py` already enforces the
catalog-vs-fallback parity used by the frontend.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/wizards", tags=["Wizards"])


class WizardKindDependency(BaseModel):
    """Dependency metadata for one creation kind inside a wizard."""

    kind: str
    label: str
    create_endpoint: str
    required_dependency: Optional[str] = None
    dependency_endpoint: Optional[str] = None
    dependency_create_endpoint: Optional[str] = None
    request_field: Optional[str] = None
    notes: Optional[str] = None


class WizardManifest(BaseModel):
    """Stable shape consumed by the frontend registry + future SDKs."""

    id: str
    label: str
    component_path: str
    catalog_endpoint: str
    catalog_module: str
    dispatches_to: List[str]
    # Optional integration dependency — set when a wizard requires an
    # existing Hub integration of a given kind before its dispatch path
    # can complete (e.g. the Jira/GitHub trigger wizards both require
    # their corresponding Hub integration since v0.7.0-fix Phase 3/4).
    integration_required: Optional[str] = None
    kind_dependencies: List[WizardKindDependency] = Field(default_factory=list)


_WIZARD_MANIFESTS: List[WizardManifest] = [
    WizardManifest(
        id="productivity",
        label="+ Add Productivity Integration",
        component_path="frontend/components/integrations/ProductivityWizard.tsx",
        catalog_endpoint="/api/hub/productivity-services",
        catalog_module="backend/hub/productivity_catalog.py",
        dispatches_to=[
            "frontend/components/integrations/GmailSetupWizard.tsx",
            "frontend/components/integrations/GoogleCalendarSetupWizard.tsx",
            "hub.page.tsx#handleAsanaConnect",
        ],
        integration_required=None,
        kind_dependencies=[
            WizardKindDependency(
                kind="gmail",
                label="Gmail",
                create_endpoint="/api/google/gmail/oauth/authorize",
                required_dependency=None,
                dependency_endpoint="/api/google/gmail/integrations",
                notes="Creates the Gmail integration that Email trigger creation later requires.",
            ),
        ],
    ),
    WizardManifest(
        id="channels",
        label="+ Add Channel",
        component_path="frontend/components/integrations/ChannelsWizard.tsx",
        catalog_endpoint="/api/channels",
        catalog_module="backend/channels/catalog.py",
        dispatches_to=[
            "frontend/components/whatsapp-wizard/WhatsAppSetupWizard.tsx",
            "frontend/components/TelegramBotModal.tsx",
            "frontend/components/SlackSetupWizard.tsx",
            "frontend/components/DiscordSetupWizard.tsx",
        ],
        integration_required=None,
    ),
    WizardManifest(
        id="triggers",
        label="+ Add Trigger",
        component_path="frontend/components/triggers/TriggerCreationWizard.tsx",
        catalog_endpoint="/api/triggers",
        catalog_module="backend/channels/catalog.py",
        dispatches_to=[],
        # Jira and GitHub trigger sub-flows REQUIRE a Hub integration as
        # of v0.7.0-fix Phase 3/4. The wizard auto-redirects to Hub →
        # Tool APIs / Developer Tools when the user picks those kinds
        # without one configured.
        integration_required=None,
        kind_dependencies=[
            WizardKindDependency(
                kind="email",
                label="Email",
                create_endpoint="/api/triggers/email",
                required_dependency="gmail_integration",
                dependency_endpoint="/api/google/gmail/integrations",
                dependency_create_endpoint="/api/google/gmail/oauth/authorize",
                request_field="gmail_integration_id",
            ),
            WizardKindDependency(
                kind="webhook",
                label="Webhook",
                create_endpoint="/api/triggers/webhook",
                required_dependency=None,
            ),
            WizardKindDependency(
                kind="jira",
                label="Jira",
                create_endpoint="/api/triggers/jira",
                required_dependency="jira_integration",
                dependency_endpoint="/api/hub/jira-integrations",
                dependency_create_endpoint="/api/hub/jira-integrations",
                request_field="jira_integration_id",
            ),
            WizardKindDependency(
                kind="github",
                label="GitHub",
                create_endpoint="/api/triggers/github",
                required_dependency="github_integration",
                dependency_endpoint="/api/hub/github-integrations",
                dependency_create_endpoint="/api/hub/github-integrations",
                request_field="github_integration_id",
            ),
        ],
    ),
    WizardManifest(
        id="tool-apis",
        label="+ Add Integration",
        component_path="frontend/components/integrations/AddIntegrationWizard.tsx",
        catalog_endpoint="/api/hub/search-providers|/api/hub/travel-providers",
        catalog_module="backend/api/routes_hub_providers.py",
        dispatches_to=[
            "frontend/components/integrations/AddIntegrationWizard.tsx#api_key",
            "frontend/components/integrations/AddIntegrationWizard.tsx#searxng_autoprovision",
            "frontend/components/integrations/AddIntegrationWizard.tsx#amadeus",
        ],
        integration_required=None,
    ),
    WizardManifest(
        id="provider",
        label="+ New Instance",
        component_path="frontend/components/provider-wizard/ProviderWizard.tsx",
        catalog_endpoint="/api/providers/vendors",
        catalog_module="backend/api/routes_provider_instances.py",
        dispatches_to=[
            "frontend/components/provider-wizard/steps/StepVendorSelect.tsx",
            "frontend/components/provider-wizard/steps/StepHosting.tsx",
            "frontend/components/provider-wizard/steps/StepContainerProvision.tsx",
        ],
        integration_required=None,
    ),
    WizardManifest(
        id="flows",
        label="+ Create Flow",
        component_path="frontend/app/flows/page.tsx#CreateFlowModal",
        catalog_endpoint="/api/flows/templates",
        catalog_module="backend/api/routes_flows.py",
        dispatches_to=[
            "frontend/app/flows/page.tsx#CreateFlowModal",
            "frontend/app/flows/page.tsx#SourceStepConfig",
        ],
        integration_required=None,
        kind_dependencies=[
            WizardKindDependency(
                kind="flow",
                label="Flow",
                create_endpoint="/api/flows/create",
                required_dependency=None,
                dependency_endpoint="/api/agents",
                request_field="default_agent_id",
                notes="Agent selection is optional; triggered flows bind to email/webhook/jira/github through /api/flow-trigger-bindings.",
            ),
        ],
    ),
    WizardManifest(
        id="continuous-agents",
        label="+ New Continuous Agent",
        component_path="frontend/components/continuous-agents/ContinuousAgentSetupModal.tsx",
        catalog_endpoint="/api/agents",
        catalog_module="backend/api/routes_continuous.py",
        dispatches_to=[
            "frontend/components/continuous-agents/ContinuousAgentSetupModal.tsx",
        ],
        integration_required=None,
        kind_dependencies=[
            WizardKindDependency(
                kind="continuous_agent",
                label="Continuous Agent",
                create_endpoint="/api/continuous-agents",
                required_dependency="agent",
                dependency_endpoint="/api/agents",
                request_field="agent_id",
                notes="Creation must also provide purpose and action_kind.",
            ),
        ],
    ),
]


@router.get("/manifests", response_model=List[WizardManifest])
def list_wizard_manifests() -> List[WizardManifest]:
    """Return the curated list of guided wizards exposed by the platform.

    Stable across tenants. Used by:
    - frontend `wizard-registry.ts` as the runtime authoritative source
    - external SDKs to render their own onboarding flows
    - drift tests to detect newly-added kinds without manifest coverage
    """
    return list(_WIZARD_MANIFESTS)


def get_wizard_manifests() -> List[WizardManifest]:
    """Module-level accessor used by the parity test."""
    return list(_WIZARD_MANIFESTS)
