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
  /** Wizard-wide integration requirement, if the whole flow needs one. */
  integrationRequired?: string | null
  /** Per-kind dependencies surfaced by the backend wizard manifest API. */
  kindDependencies?: readonly WizardKindDependencyDescriptor[]
}

export interface WizardKindDependencyDescriptor {
  kind: string
  label: string
  createEndpoint: string
  requiredDependency?: string | null
  dependencyEndpoint?: string | null
  dependencyCreateEndpoint?: string | null
  requestField?: string | null
  notes?: string | null
}

export interface WizardManifestKindDependency {
  kind: string
  label: string
  create_endpoint: string
  required_dependency?: string | null
  dependency_endpoint?: string | null
  dependency_create_endpoint?: string | null
  request_field?: string | null
  notes?: string | null
}

export interface WizardManifest {
  id: string
  label: string
  component_path: string
  catalog_endpoint: string
  catalog_module: string
  dispatches_to: string[]
  integration_required?: string | null
  kind_dependencies?: WizardManifestKindDependency[]
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
    integrationRequired: null,
    kindDependencies: [
      {
        kind: 'gmail',
        label: 'Gmail',
        createEndpoint: '/api/google/gmail/oauth/authorize',
        requiredDependency: null,
        dependencyEndpoint: '/api/google/gmail/integrations',
        notes: 'Creates the Gmail integration that Email trigger creation later requires.',
      },
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
    integrationRequired: null,
  },
  {
    id: 'triggers',
    label: '+ Add Trigger',
    componentPath: 'frontend/components/triggers/TriggerCreationWizard.tsx',
    catalogEndpoint: '/api/triggers',
    catalogModule: 'backend/channels/catalog.py',
    dispatchesTo: [],
    integrationRequired: null,
    kindDependencies: [
      {
        kind: 'email',
        label: 'Email',
        createEndpoint: '/api/triggers/email',
        requiredDependency: 'gmail_integration',
        dependencyEndpoint: '/api/google/gmail/integrations',
        dependencyCreateEndpoint: '/api/google/gmail/oauth/authorize',
        requestField: 'gmail_integration_id',
      },
      {
        kind: 'webhook',
        label: 'Webhook',
        createEndpoint: '/api/triggers/webhook',
        requiredDependency: null,
      },
      {
        kind: 'jira',
        label: 'Jira',
        createEndpoint: '/api/triggers/jira',
        requiredDependency: 'jira_integration',
        dependencyEndpoint: '/api/hub/jira-integrations',
        dependencyCreateEndpoint: '/api/hub/jira-integrations',
        requestField: 'jira_integration_id',
      },
      {
        kind: 'github',
        label: 'GitHub',
        createEndpoint: '/api/triggers/github',
        requiredDependency: 'github_integration',
        dependencyEndpoint: '/api/hub/github-integrations',
        dependencyCreateEndpoint: '/api/hub/github-integrations',
        requestField: 'github_integration_id',
      },
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
    integrationRequired: null,
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
    integrationRequired: null,
  },
  {
    id: 'flows',
    label: '+ Create Flow',
    componentPath: 'frontend/app/flows/page.tsx#CreateFlowModal',
    catalogEndpoint: '/api/flows/templates',
    catalogModule: 'backend/api/routes_flows.py',
    dispatchesTo: [
      'frontend/app/flows/page.tsx#CreateFlowModal',
      'frontend/app/flows/page.tsx#SourceStepConfig',
    ],
    integrationRequired: null,
    kindDependencies: [
      {
        kind: 'flow',
        label: 'Flow',
        createEndpoint: '/api/flows/create',
        requiredDependency: null,
        dependencyEndpoint: '/api/agents',
        requestField: 'default_agent_id',
        notes: 'Agent selection is optional; triggered flows bind to email/webhook/jira/github through /api/flow-trigger-bindings.',
      },
    ],
  },
  {
    id: 'continuous-agents',
    label: '+ New Continuous Agent',
    componentPath: 'frontend/components/continuous-agents/ContinuousAgentSetupModal.tsx',
    catalogEndpoint: '/api/agents',
    catalogModule: 'backend/api/routes_continuous.py',
    dispatchesTo: [
      'frontend/components/continuous-agents/ContinuousAgentSetupModal.tsx',
    ],
    integrationRequired: null,
    kindDependencies: [
      {
        kind: 'continuous_agent',
        label: 'Continuous Agent',
        createEndpoint: '/api/continuous-agents',
        requiredDependency: 'agent',
        dependencyEndpoint: '/api/agents',
        requestField: 'agent_id',
        notes: 'Creation must also provide purpose and action_kind.',
      },
    ],
  },
] as const

export function getWizardById(id: string): WizardDescriptor | undefined {
  return WIZARDS.find(w => w.id === id)
}

export function wizardDescriptorFromManifest(manifest: WizardManifest): WizardDescriptor {
  return {
    id: manifest.id,
    label: manifest.label,
    componentPath: manifest.component_path,
    catalogEndpoint: manifest.catalog_endpoint,
    catalogModule: manifest.catalog_module,
    dispatchesTo: manifest.dispatches_to,
    integrationRequired: manifest.integration_required ?? null,
    kindDependencies: (manifest.kind_dependencies || []).map((dependency) => ({
      kind: dependency.kind,
      label: dependency.label,
      createEndpoint: dependency.create_endpoint,
      requiredDependency: dependency.required_dependency ?? null,
      dependencyEndpoint: dependency.dependency_endpoint ?? null,
      dependencyCreateEndpoint: dependency.dependency_create_endpoint ?? null,
      requestField: dependency.request_field ?? null,
      notes: dependency.notes ?? null,
    })),
  }
}
