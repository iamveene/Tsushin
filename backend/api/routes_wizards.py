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
from pydantic import BaseModel


router = APIRouter(prefix="/api/wizards", tags=["Wizards"])


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
        dispatches_to=[
            "frontend/components/triggers/EmailTriggerWizard.tsx",
        ],
        # Jira and GitHub trigger sub-flows REQUIRE a Hub integration as
        # of v0.7.0-fix Phase 3/4. The wizard auto-redirects to Hub →
        # Tool APIs / Developer Tools when the user picks those kinds
        # without one configured.
        integration_required=None,
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
