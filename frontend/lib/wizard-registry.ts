/**
 * Wizard registry — the single place the frontend tracks every guided
 * wizard the platform exposes and the backend catalog each one depends on.
 *
 * Why this exists
 * ---------------
 * Tsushin now ships a handful of "+ Add …" launchers that all follow the
 * same pattern: pick a service/channel/provider from a backend-driven
 * catalog, then delegate to a per-target setup flow. Without a central
 * index, it's easy for related wizards to drift — e.g. someone adds a new
 * productivity service to the backend catalog but forgets to add a
 * fallback row to ProductivityWizard.tsx.
 *
 * backend/tests/test_wizard_drift.py already asserts each wizard's
 * fallback array matches its backend catalog (Guards 5, 8, 9). The drift
 * tests use regex to locate the fallback arrays; this registry makes the
 * coupling explicit at runtime so future wizards can be wired up in one
 * place and the drift guard extended alongside.
 *
 * Nothing here is imported by the wizards themselves — they own their
 * fallback arrays so offline mode still works if the registry import
 * tree ever breaks. This module is intentionally pure metadata.
 */

export interface WizardDescriptor {
  /** Short id used in analytics / drift tests. */
  id: string
  /** Human-readable label shown in the "+ Add …" button. */
  label: string
  /** Relative path (from repo root) to the wizard component. */
  componentPath: string
  /** Backend catalog endpoint that drives the picker step. */
  catalogEndpoint: string
  /** Backend catalog module (Python path, for drift-guard reference). */
  catalogModule: string
  /** The sub-wizards / modals this wizard dispatches to after step 1. */
  dispatchesTo: readonly string[]
}

export const WIZARDS: readonly WizardDescriptor[] = [
  {
    id: 'productivity',
    label: '+ Add Productivity Integration',
    componentPath: 'frontend/components/integrations/ProductivityWizard.tsx',
    catalogEndpoint: '/api/hub/productivity-services',
    catalogModule: 'backend/hub/productivity_catalog.py',
    dispatchesTo: [
      'frontend/components/integrations/GmailSetupWizard.tsx',
      'frontend/components/integrations/GoogleCalendarSetupWizard.tsx',
      'hub.page.tsx#handleAsanaConnect',
    ],
  },
  {
    id: 'channels',
    label: '+ Add Channel',
    componentPath: 'frontend/components/integrations/ChannelsWizard.tsx',
    catalogEndpoint: '/api/channels',
    catalogModule: 'backend/channels/catalog.py',
    dispatchesTo: [
      'frontend/components/whatsapp-wizard/WhatsAppSetupWizard.tsx',
      'frontend/components/TelegramBotModal.tsx',
      'frontend/components/SlackSetupWizard.tsx',
      'frontend/components/DiscordSetupWizard.tsx',
    ],
  },
  {
    id: 'triggers',
    label: '+ Add Trigger',
    componentPath: 'frontend/components/triggers/TriggerCreationWizard.tsx',
    catalogEndpoint: '/api/triggers',
    catalogModule: 'backend/channels/catalog.py',
    dispatchesTo: [
      'frontend/components/triggers/EmailTriggerWizard.tsx',
    ],
  },
  {
    id: 'tool-apis',
    label: '+ Add Integration',
    componentPath: 'frontend/components/integrations/AddIntegrationWizard.tsx',
    catalogEndpoint: '/api/hub/search-providers|/api/hub/travel-providers',
    catalogModule: 'backend/api/routes_hub_providers.py',
    dispatchesTo: [
      'frontend/components/integrations/AddIntegrationWizard.tsx#api_key',
      'frontend/components/integrations/AddIntegrationWizard.tsx#searxng_autoprovision',
      'frontend/components/integrations/AddIntegrationWizard.tsx#amadeus',
    ],
  },
  {
    id: 'provider',
    label: '+ New Instance',
    componentPath: 'frontend/components/provider-wizard/ProviderWizard.tsx',
    catalogEndpoint: '/api/providers/vendors',
    catalogModule: 'backend/api/routes_provider_instances.py',
    dispatchesTo: [
      'frontend/components/provider-wizard/steps/StepVendorSelect.tsx',
      'frontend/components/provider-wizard/steps/StepHosting.tsx',
      'frontend/components/provider-wizard/steps/StepContainerProvision.tsx',
    ],
  },
] as const

export function getWizardById(id: string): WizardDescriptor | undefined {
  return WIZARDS.find(w => w.id === id)
}
