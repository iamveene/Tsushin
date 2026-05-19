'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import Wizard, { type WizardStep } from '@/components/ui/Wizard'
import {
  AlertCircleIcon,
  BotIcon,
  CheckCircleIcon,
  CodeIcon,
  GitHubIcon,
  LightningIcon,
  RefreshIcon,
  UsersIcon,
} from '@/components/ui/icons'
import {
  api,
  type GitHubIntegration,
  type GitHubTrigger,
  type GitLabIntegration,
  type GitLabTrigger,
  type RepositoryAutomationResponse,
} from '@/lib/client'
import {
  REPOSITORY_AUTOMATION_TEMPLATES,
  defaultRepositoryAutomationDraft,
  integrationLabel,
  isActiveRepositoryIntegration,
  parseRepositoryLabel,
  repositoryLabelFromDraft,
  repositoryLabelFromIntegration,
  triggerDisplayName,
  triggerRepositoryLabel,
  type RepositoryAutomationDraft,
  type RepositoryAutomationIntegration,
  type RepositoryAutomationOpenOptions,
  type RepositoryAutomationProvider,
  type RepositoryAutomationTemplateId,
  type RepositoryAutomationTrigger,
} from '@/lib/repository-automation'

const STEPS: WizardStep[] = [
  { id: 'model', label: 'Model', description: 'Objects' },
  { id: 'template', label: 'Template', description: 'Team or agent' },
  { id: 'source', label: 'Source', description: 'Integration' },
  { id: 'review', label: 'Review', description: 'Create or reuse' },
]

interface Props {
  isOpen: boolean
  options: RepositoryAutomationOpenOptions | null
  onClose: () => void
}

type LoadState = {
  githubIntegrations: GitHubIntegration[]
  gitlabIntegrations: GitLabIntegration[]
  githubTriggers: GitHubTrigger[]
  gitlabTriggers: GitLabTrigger[]
  loading: boolean
  error: string | null
}

const initialLoadState: LoadState = {
  githubIntegrations: [],
  gitlabIntegrations: [],
  githubTriggers: [],
  gitlabTriggers: [],
  loading: false,
  error: null,
}

function providerLabel(provider: RepositoryAutomationProvider): string {
  return provider === 'gitlab' ? 'GitLab' : 'GitHub'
}

function providerIcon(provider: RepositoryAutomationProvider) {
  return provider === 'gitlab' ? <CodeIcon size={18} /> : <GitHubIcon size={18} />
}

function statusTone(value?: string | null): string {
  const normalized = (value || '').toLowerCase()
  if (['healthy', 'success', 'ok', 'active', 'connected'].includes(normalized)) return 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200'
  if (['unhealthy', 'error', 'failed'].includes(normalized)) return 'border-rose-400/40 bg-rose-500/10 text-rose-200'
  if (['warning', 'degraded'].includes(normalized)) return 'border-amber-400/40 bg-amber-500/10 text-amber-200'
  return 'border-tsushin-border bg-tsushin-surface/60 text-tsushin-slate'
}

function activeTriggers(provider: RepositoryAutomationProvider, loadState: LoadState): RepositoryAutomationTrigger[] {
  const rows = provider === 'gitlab' ? loadState.gitlabTriggers : loadState.githubTriggers
  return rows.filter((trigger) => trigger.is_active && trigger.status === 'active')
}

function defaultEvent(provider: RepositoryAutomationProvider): string {
  return provider === 'gitlab' ? 'merge_request' : 'pull_request'
}

function splitPathFilters(value: string): string[] | null {
  const filters = value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
  return filters.length > 0 ? filters : null
}

export default function RepositoryAutomationWizard({ isOpen, options, onClose }: Props) {
  const [step, setStep] = useState(1)
  const [draft, setDraft] = useState<RepositoryAutomationDraft>(() => defaultRepositoryAutomationDraft())
  const [loadState, setLoadState] = useState<LoadState>(initialLoadState)
  const [saving, setSaving] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [result, setResult] = useState<RepositoryAutomationResponse | null>(null)

  useEffect(() => {
    if (!isOpen) return
    const next = defaultRepositoryAutomationDraft(options || {})
    setDraft(next)
    setStep(1)
    setSaving(false)
    setSubmitError(null)
    setResult(null)
  }, [isOpen, options])

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setLoadState((current) => ({ ...current, loading: true, error: null }))
    Promise.all([
      api.listGitHubIntegrations().catch(() => [] as GitHubIntegration[]),
      api.listGitLabIntegrations().catch(() => [] as GitLabIntegration[]),
      api.listGitHubTriggers().catch(() => [] as GitHubTrigger[]),
      api.listGitLabTriggers().catch(() => [] as GitLabTrigger[]),
    ])
      .then(([githubIntegrations, gitlabIntegrations, githubTriggers, gitlabTriggers]) => {
        if (cancelled) return
        setLoadState({
          githubIntegrations,
          gitlabIntegrations,
          githubTriggers,
          gitlabTriggers,
          loading: false,
          error: null,
        })
        setDraft((current) => {
          const selectedList = current.provider === 'gitlab' ? gitlabIntegrations : githubIntegrations
          const active = selectedList.find((item) => item.id === current.integrationId)
            || selectedList.find(isActiveRepositoryIntegration)
          if (!active) return current
          const defaultRepo = repositoryLabelFromIntegration(current.provider, active)
          const parsed = parseRepositoryLabel(current.provider, defaultRepo)
          return {
            ...current,
            integrationId: current.integrationId ?? active.id,
            repositoryOwner: current.repositoryOwner || parsed.owner,
            repositoryName: current.repositoryName || parsed.repo,
            projectPath: current.projectPath || parsed.projectPath,
          }
        })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setLoadState({
          ...initialLoadState,
          loading: false,
          error: error instanceof Error ? error.message : 'Failed to load repository automation data',
        })
      })
    return () => {
      cancelled = true
    }
  }, [isOpen])

  const integrations = useMemo<RepositoryAutomationIntegration[]>(
    () => (draft.provider === 'gitlab' ? loadState.gitlabIntegrations : loadState.githubIntegrations),
    [draft.provider, loadState.githubIntegrations, loadState.gitlabIntegrations],
  )
  const activeIntegrations = useMemo(
    () => integrations.filter(isActiveRepositoryIntegration),
    [integrations],
  )
  const selectedIntegration = useMemo(
    () => integrations.find((integration) => integration.id === draft.integrationId) || null,
    [draft.integrationId, integrations],
  )
  const triggers = useMemo(() => activeTriggers(draft.provider, loadState), [draft.provider, loadState])
  const selectedTrigger = useMemo(
    () => triggers.find((trigger) => trigger.id === draft.triggerId) || null,
    [draft.triggerId, triggers],
  )

  useEffect(() => {
    if (!selectedTrigger) return
    setDraft((current) => {
      const label = triggerRepositoryLabel(current.provider, selectedTrigger)
      const parsed = parseRepositoryLabel(current.provider, label)
      const triggerIntegrationId = current.provider === 'gitlab'
        ? (selectedTrigger as GitLabTrigger).gitlab_integration_id
        : (selectedTrigger as GitHubTrigger).github_integration_id
      return {
        ...current,
        integrationId: triggerIntegrationId || current.integrationId,
        triggerName: triggerDisplayName(current.provider, selectedTrigger),
        eventType: selectedTrigger.events?.[0] || current.eventType || defaultEvent(current.provider),
        repositoryOwner: parsed.owner || current.repositoryOwner,
        repositoryName: parsed.repo || current.repositoryName,
        projectPath: parsed.projectPath || current.projectPath,
      }
    })
  }, [selectedTrigger])

  const template = REPOSITORY_AUTOMATION_TEMPLATES.find((item) => item.id === draft.templateId) || REPOSITORY_AUTOMATION_TEMPLATES[0]
  const repoLabel = repositoryLabelFromDraft(draft)
  const repositoryReady = draft.provider === 'gitlab'
    ? Boolean(draft.projectPath.trim())
    : Boolean(draft.repositoryOwner.trim() && draft.repositoryName.trim())
  const sourceReady = Boolean(selectedIntegration && repositoryReady && draft.eventType)
  const canContinue = step === 1
    ? true
    : step === 2
      ? Boolean(draft.templateId)
      : step === 3
        ? sourceReady
        : true

  function patchDraft(patch: Partial<RepositoryAutomationDraft>) {
    setDraft((current) => ({ ...current, ...patch }))
  }

  function selectProvider(provider: RepositoryAutomationProvider) {
    setDraft((current) => {
      const nextIntegration = provider === 'gitlab'
        ? loadState.gitlabIntegrations.find(isActiveRepositoryIntegration)
        : loadState.githubIntegrations.find(isActiveRepositoryIntegration)
      const repository = nextIntegration ? repositoryLabelFromIntegration(provider, nextIntegration) : ''
      const parsed = parseRepositoryLabel(provider, repository)
      return {
        ...current,
        provider,
        integrationId: nextIntegration?.id ?? null,
        repositoryOwner: parsed.owner,
        repositoryName: parsed.repo,
        projectPath: parsed.projectPath,
        triggerId: null,
        triggerName: '',
        eventType: defaultEvent(provider),
        branchFilter: '',
        pathFiltersText: '',
        authorFilter: '',
      }
    })
  }

  function selectTemplate(templateId: RepositoryAutomationTemplateId) {
    patchDraft({
      templateId,
      routingMode: templateId === 'repository_pr_agent' ? 'agent_flow' : 'team_primary',
    })
  }

  async function handleLaunch() {
    if (!draft.integrationId || saving) return
    setSaving(true)
    setSubmitError(null)
    setResult(null)
    try {
      const response = await api.createRepositoryAutomation({
        provider: draft.provider,
        integration_id: draft.integrationId,
        template_id: draft.templateId,
        repo_owner: draft.provider === 'github' ? draft.repositoryOwner : undefined,
        repo_name: draft.provider === 'github' ? draft.repositoryName : undefined,
        project_path: draft.provider === 'gitlab' ? draft.projectPath : undefined,
        existing_trigger_id: draft.triggerId ?? undefined,
        events: [draft.eventType || defaultEvent(draft.provider)],
        branch_filter: draft.branchFilter.trim() || null,
        path_filters: splitPathFilters(draft.pathFiltersText),
        author_filter: draft.authorFilter.trim() || null,
        routing_mode: draft.routingMode,
      })
      setResult(response)
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to create repository automation')
    } finally {
      setSaving(false)
    }
  }

  const footer = (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <button
        type="button"
        onClick={step === 1 ? onClose : () => setStep((current) => Math.max(1, current - 1))}
        className="rounded-lg border border-tsushin-border/70 bg-transparent px-4 py-2 text-sm text-tsushin-slate transition-colors hover:border-tsushin-border hover:text-white"
      >
        {step === 1 ? 'Cancel' : 'Back'}
      </button>
      <div className="flex items-center gap-2">
        {step < STEPS.length ? (
          <button
            type="button"
            onClick={() => setStep((current) => Math.min(STEPS.length, current + 1))}
            disabled={!canContinue}
            className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            Continue
          </button>
        ) : (
          <button
            type="button"
            onClick={handleLaunch}
            disabled={!sourceReady || saving}
            className="btn-primary inline-flex items-center gap-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? <RefreshIcon size={16} className="animate-spin" /> : <CheckCircleIcon size={16} />}
            {result ? 'Create again' : 'Create automation'}
          </button>
        )}
      </div>
    </div>
  )

  return (
    <Wizard
      isOpen={isOpen}
      onClose={onClose}
      title="Repository Automation Wizard"
      steps={STEPS}
      currentStep={step}
      footer={footer}
      size="2xl"
      autoHeight
      showProgress
      stepTitle={stepTitle(step)}
      stepDescription={stepDescription(step)}
    >
      {loadState.error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          <AlertCircleIcon size={16} className="mr-2 inline" />
          {loadState.error}
        </div>
      )}
      {submitError && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          <AlertCircleIcon size={16} className="mr-2 inline" />
          {submitError}
        </div>
      )}
      {loadState.loading && (
        <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/40 px-4 py-3 text-sm text-tsushin-slate">
          <RefreshIcon size={16} className="mr-2 inline animate-spin" />
          Loading repository integrations and triggers
        </div>
      )}

      {step === 1 && <ObjectModelStep />}
      {step === 2 && (
        <TemplateStep
          selected={draft.templateId}
          onSelect={selectTemplate}
        />
      )}
      {step === 3 && (
        <SourceStep
          draft={draft}
          activeIntegrations={activeIntegrations}
          selectedIntegration={selectedIntegration}
          triggers={triggers}
          selectedTrigger={selectedTrigger}
          onProviderChange={selectProvider}
          onPatch={patchDraft}
        />
      )}
      {step === 4 && (
        <ReviewStep
          draft={draft}
          templateName={template.name}
          selectedIntegration={selectedIntegration}
          selectedTrigger={selectedTrigger}
          repoLabel={repoLabel}
          result={result}
        />
      )}
    </Wizard>
  )
}

function stepTitle(step: number): string {
  if (step === 1) return 'How repository automation is assembled'
  if (step === 2) return 'Choose the automation shape'
  if (step === 3) return 'Select the repository source'
  return 'Review and create'
}

function stepDescription(step: number): string {
  if (step === 1) return 'The wizard coordinates existing Tsushin objects instead of hiding them.'
  if (step === 2) return 'Use a coordinated team for review depth, or a single agent for lightweight PR/MR feedback.'
  if (step === 3) return 'Reuse active repository connections and optional existing triggers. Missing connections stay linked to Hub.'
  return 'Confirm exactly which objects will be created or reused before saving the automation.'
}

function ObjectModelStep() {
  const items = [
    ['Repository Integration credentials', 'Shared GitHub/GitLab token and default repository or project used by triggers and Code Repository skills.'],
    ['Trigger listens', 'Webhook source that receives push, pull request, or merge request events and emits wake events.'],
    ['Flow deterministic steps', 'Optional triggered flow that runs repeatable steps after the Source step.'],
    ['Agent actor with tools', 'Single LLM actor with Code Repository read tools and A2A handoff enabled.'],
    ['Team coordinated actors', 'Coordinator, Reviewer, and Merge Readiness roles organized through the Team Wizard.'],
  ]
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {items.map(([title, body]) => (
        <div key={title} className="rounded-lg border border-tsushin-border bg-tsushin-surface/50 p-4">
          <div className="text-sm font-semibold text-white">{title}</div>
          <p className="mt-2 text-sm leading-6 text-tsushin-slate">{body}</p>
        </div>
      ))}
    </div>
  )
}

function TemplateStep({
  selected,
  onSelect,
}: {
  selected: RepositoryAutomationTemplateId
  onSelect: (templateId: RepositoryAutomationTemplateId) => void
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {REPOSITORY_AUTOMATION_TEMPLATES.map((template) => {
        const active = selected === template.id
        const Icon = template.id === 'repository_pr_agent' ? BotIcon : UsersIcon
        return (
          <button
            key={template.id}
            type="button"
            onClick={() => onSelect(template.id)}
            aria-pressed={active}
            className={`rounded-lg border p-4 text-left transition-colors ${
              active
                ? 'border-tsushin-accent bg-tsushin-accent/10 text-white'
                : 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-slate hover:border-tsushin-muted hover:text-white'
            }`}
          >
            <div className="flex items-start gap-3">
              <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/70 p-2 text-tsushin-accent">
                <Icon size={18} />
              </div>
              <div>
                <div className="font-semibold text-white">{template.name}</div>
                <div className="mt-1 text-xs text-tsushin-fog">{template.subtitle}</div>
                <p className="mt-3 text-sm leading-6 text-tsushin-slate">{template.summary}</p>
              </div>
            </div>
          </button>
        )
      })}
    </div>
  )
}

function SourceStep({
  draft,
  activeIntegrations,
  selectedIntegration,
  triggers,
  selectedTrigger,
  onProviderChange,
  onPatch,
}: {
  draft: RepositoryAutomationDraft
  activeIntegrations: RepositoryAutomationIntegration[]
  selectedIntegration: RepositoryAutomationIntegration | null
  triggers: RepositoryAutomationTrigger[]
  selectedTrigger: RepositoryAutomationTrigger | null
  onProviderChange: (provider: RepositoryAutomationProvider) => void
  onPatch: (patch: Partial<RepositoryAutomationDraft>) => void
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2">
        {(['github', 'gitlab'] as const).map((provider) => {
          const active = draft.provider === provider
          return (
            <button
              key={provider}
              type="button"
              onClick={() => onProviderChange(provider)}
              className={`rounded-lg border p-3 text-left transition-colors ${
                active
                  ? 'border-cyan-400 bg-cyan-500/10 text-white'
                  : 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-slate hover:border-tsushin-muted'
              }`}
            >
              <div className="flex items-center gap-2 text-sm font-semibold">
                {providerIcon(provider)}
                {providerLabel(provider)}
              </div>
              <p className="mt-1 text-xs text-tsushin-slate">
                {provider === 'gitlab' ? 'Merge request and project webhooks.' : 'Pull request and repository webhooks.'}
              </p>
            </button>
          )
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-white">{providerLabel(draft.provider)} integration</div>
            <Link href="/hub?tab=developer" className="text-xs text-cyan-200 hover:text-white">
              Developer Tools
            </Link>
          </div>
          {activeIntegrations.length === 0 ? (
            <div className="rounded-lg border border-amber-400/30 bg-amber-500/10 p-4 text-sm text-amber-100">
              No active {providerLabel(draft.provider)} connection is available. Create or enable one in Hub Developer Tools, then return to select it here.
            </div>
          ) : (
            <select
              value={draft.integrationId ?? ''}
              onChange={(event) => {
                const integrationId = event.target.value ? Number(event.target.value) : null
                const integration = activeIntegrations.find((item) => item.id === integrationId) || null
                const parsed = parseRepositoryLabel(draft.provider, integration ? repositoryLabelFromIntegration(draft.provider, integration) : '')
                onPatch({
                  integrationId,
                  repositoryOwner: parsed.owner,
                  repositoryName: parsed.repo,
                  projectPath: parsed.projectPath,
                })
              }}
              className="select text-sm"
            >
              <option value="">Select an active integration</option>
              {activeIntegrations.map((integration) => (
                <option key={integration.id} value={integration.id}>
                  {integrationLabel(draft.provider, integration)}
                </option>
              ))}
            </select>
          )}
          {selectedIntegration && (
            <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/40 p-3 text-xs text-tsushin-slate">
              <span className={`mr-2 rounded-full border px-2 py-0.5 ${statusTone(selectedIntegration.health_status || selectedIntegration.last_test_status || (selectedIntegration.is_active ? 'active' : 'inactive'))}`}>
                {selectedIntegration.health_status || selectedIntegration.last_test_status || (selectedIntegration.is_active ? 'active' : 'inactive')}
              </span>
              Default target: <span className="font-mono text-tsushin-fog">{repositoryLabelFromIntegration(draft.provider, selectedIntegration) || 'none'}</span>
            </div>
          )}
        </div>

        <div className="space-y-3">
          <div className="text-sm font-semibold text-white">
            {draft.provider === 'gitlab' ? 'Project' : 'Repository'}
          </div>
          {draft.provider === 'gitlab' ? (
            <input
              value={draft.projectPath}
              onChange={(event) => onPatch({ projectPath: event.target.value })}
              className="input text-sm"
              placeholder="group/subgroup/project"
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <input
                value={draft.repositoryOwner}
                onChange={(event) => onPatch({ repositoryOwner: event.target.value })}
                className="input text-sm"
                placeholder="owner"
              />
              <input
                value={draft.repositoryName}
                onChange={(event) => onPatch({ repositoryName: event.target.value })}
                className="input text-sm"
                placeholder="repo"
              />
            </div>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/40 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-white">Existing trigger</div>
            <p className="text-xs text-tsushin-slate">Optional. Reuse an active trigger now, or let the wizard create one from the repository target.</p>
          </div>
          <Link href="/hub?tab=triggers" className="text-xs text-cyan-200 hover:text-white">Manage triggers</Link>
        </div>
        <select
          value={draft.triggerId ?? ''}
          onChange={(event) => {
            const triggerId = event.target.value ? Number(event.target.value) : null
            const trigger = triggers.find((item) => item.id === triggerId) || null
            onPatch({
              triggerId: trigger ? trigger.id : null,
              triggerName: trigger ? triggerDisplayName(draft.provider, trigger) : '',
            })
          }}
          className="select text-sm"
        >
          <option value="">No trigger selected yet</option>
          {triggers.map((trigger) => (
            <option key={trigger.id} value={trigger.id}>
              {triggerDisplayName(draft.provider, trigger)} · {triggerRepositoryLabel(draft.provider, trigger)}
            </option>
          ))}
        </select>
        {selectedTrigger && (
          <div className="mt-3 rounded-lg border border-cyan-400/30 bg-cyan-500/10 p-3 text-xs text-cyan-100">
            This wizard will reuse trigger #{selectedTrigger.id} and bind downstream objects to its wake events.
          </div>
        )}
      </div>

      <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/40 p-4">
        <div className="mb-4">
          <div className="text-sm font-semibold text-white">Repository event and filters</div>
          <p className="mt-1 text-xs text-tsushin-slate">
            Defaults are read-only PR/MR review events. Filters are applied to the trigger before any Flow or Team routing starts.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs text-tsushin-slate">
            Event
            <select
              value={draft.eventType}
              onChange={(event) => onPatch({ eventType: event.target.value })}
              className="select text-sm"
            >
              {draft.provider === 'gitlab' ? (
                <>
                  <option value="merge_request">Merge request</option>
                  <option value="push">Push</option>
                  <option value="pipeline">Pipeline</option>
                </>
              ) : (
                <>
                  <option value="pull_request">Pull request</option>
                  <option value="push">Push</option>
                  <option value="workflow_run">Workflow run</option>
                </>
              )}
            </select>
          </label>
          <label className="space-y-1 text-xs text-tsushin-slate">
            Branch filter
            <input
              value={draft.branchFilter}
              onChange={(event) => onPatch({ branchFilter: event.target.value })}
              className="input text-sm"
              placeholder="main, release/*, or blank"
            />
          </label>
          <label className="space-y-1 text-xs text-tsushin-slate">
            Path filters
            <textarea
              value={draft.pathFiltersText}
              onChange={(event) => onPatch({ pathFiltersText: event.target.value })}
              className="input min-h-[92px] resize-y text-sm"
              placeholder={'backend/**\nfrontend/**'}
            />
          </label>
          <label className="space-y-1 text-xs text-tsushin-slate">
            Author filter
            <input
              value={draft.authorFilter}
              onChange={(event) => onPatch({ authorFilter: event.target.value })}
              className="input text-sm"
              placeholder="dependabot, release-bot, or blank"
            />
          </label>
        </div>
      </div>
    </div>
  )
}

function ReviewStep({
  draft,
  templateName,
  selectedIntegration,
  selectedTrigger,
  repoLabel,
  result,
}: {
  draft: RepositoryAutomationDraft
  templateName: string
  selectedIntegration: RepositoryAutomationIntegration | null
  selectedTrigger: RepositoryAutomationTrigger | null
  repoLabel: string
  result: RepositoryAutomationResponse | null
}) {
  const rows = [
    ['Template', templateName],
    ['Repository Integration credentials', selectedIntegration ? `Reuse ${integrationLabel(draft.provider, selectedIntegration)} (#${selectedIntegration.id})` : 'Missing integration'],
    ['Trigger listens', selectedTrigger ? `Reuse ${triggerDisplayName(draft.provider, selectedTrigger)} (#${selectedTrigger.id})` : `Create a ${providerLabel(draft.provider)} trigger in Hub Triggers`],
    ['Event and filters', `${draft.eventType || defaultEvent(draft.provider)}${draft.branchFilter.trim() ? ` on ${draft.branchFilter.trim()}` : ''}`],
    ['Flow deterministic steps', 'Create or reuse a generated triggered Flow as the editable output surface'],
    ['Agent actor with tools', draft.templateId === 'repository_pr_agent' ? 'Create standalone reviewer agent with Code Repository read tools and A2A enabled' : 'Create read-only team member agents for repository review'],
    ['Team coordinated actors', draft.templateId === 'repository_review_team' ? 'Create Coordinator, Reviewer, and Merge Readiness in a line topology' : 'Not created for standalone agent template'],
    ['Routing mode', draft.routingMode === 'team_primary' ? 'Team binding runs first; Flow binding is linked but inactive' : 'Active generated Flow routes to the reviewer agent'],
  ]
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/50 p-4">
        <div className="flex flex-wrap items-center gap-2 text-sm text-tsushin-slate">
          <LightningIcon size={16} className="text-cyan-300" />
          Target: <span className="font-mono text-white">{repoLabel || 'not set'}</span>
        </div>
      </div>
      <div className="overflow-hidden rounded-lg border border-tsushin-border">
        {rows.map(([label, value]) => (
          <div key={label} className="grid gap-2 border-b border-tsushin-border/70 bg-tsushin-surface/40 px-4 py-3 text-sm last:border-b-0 md:grid-cols-[220px_minmax(0,1fr)]">
            <div className="text-xs uppercase tracking-wide text-tsushin-slate">{label}</div>
            <div className="text-white">{value}</div>
          </div>
        ))}
      </div>
      {result && (
        <div className="rounded-lg border border-emerald-400/30 bg-emerald-500/10 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-100">
            <CheckCircleIcon size={16} />
            Repository automation is ready
          </div>
          <div className="mt-3 grid gap-2 text-sm text-emerald-50 md:grid-cols-2">
            <Link href={result.links.trigger} className="rounded-lg border border-emerald-300/25 px-3 py-2 hover:bg-emerald-400/10">
              Trigger #{result.trigger.id}
            </Link>
            <Link href={result.links.flow} className="rounded-lg border border-emerald-300/25 px-3 py-2 hover:bg-emerald-400/10">
              Flow #{result.flow.id}
            </Link>
            {result.team && result.links.team && (
              <Link href={result.links.team} className="rounded-lg border border-emerald-300/25 px-3 py-2 hover:bg-emerald-400/10">
                Team #{result.team.id}
              </Link>
            )}
            {result.agents[0] && result.links.agent && (
              <Link href={result.links.agent} className="rounded-lg border border-emerald-300/25 px-3 py-2 hover:bg-emerald-400/10">
                Agent #{result.agents[0].id}
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
