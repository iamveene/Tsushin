'use client'

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import Wizard, { type WizardStep } from '@/components/ui/Wizard'
import {
  AlertCircleIcon,
  ArrowDownIcon,
  ArrowUpIcon,
  BotIcon,
  CheckCircleIcon,
  MailIcon,
  GitHubIcon,
  PlusIcon,
  RefreshIcon,
  TrashIcon,
  UsersIcon,
  WebhookIcon,
} from '@/components/ui/icons'
import { useAgentWizard, useAgentWizardComplete } from '@/contexts/AgentWizardContext'
import { useTeamWizard } from '@/contexts/TeamWizardContext'
import { api, type Agent, type EmailTrigger, type GitHubTrigger, type JiraTrigger, type WebhookIntegration } from '@/lib/client'
import { defaultTeamTriggerEvents, eventTypesFromInput } from '@/lib/team-trigger-defaults'
import {
  TEAM_TEMPLATE_PRESETS,
  type TeamTemplateId,
  type TeamTriggerDraft,
  type TeamTriggerDraftKind,
  type TeamWizardDraft,
  type TeamWizardStep,
} from '@/lib/team-wizard/reducer'

const STEP_META: Record<TeamWizardStep, { label: string; description: string; title: string; body: string }> = {
  template: {
    label: 'Template',
    description: 'Preset',
    title: 'Start mode',
    body: 'Choose a local preset or keep the draft custom.',
  },
  basics: {
    label: 'Basics',
    description: 'Goal',
    title: 'Team basics',
    body: 'Name the team and define the operating goal.',
  },
  topology: {
    label: 'Topology',
    description: 'Limits',
    title: 'Topology and limits',
    body: 'Set the execution shape and run controls.',
  },
  members: {
    label: 'Members',
    description: 'Agents',
    title: 'Members',
    body: 'Choose the agents that will participate in team runs.',
  },
  triggers: {
    label: 'Triggers',
    description: 'Bindings',
    title: 'Trigger bindings',
    body: 'Bind existing active Webhook, GitHub, Jira, or Gmail triggers.',
  },
  review: {
    label: 'Review',
    description: 'Check',
    title: 'Review',
    body: 'Confirm the draft before creation.',
  },
  create: {
    label: 'Create',
    description: 'Save',
    title: 'Create team',
    body: 'Persist the team and optional trigger bindings.',
  },
}

type TriggerOption = {
  kind: TeamTriggerDraftKind
  id: number
  label: string
  detail: string
  defaultEvents: string[]
}

const inputClass = 'input text-sm'
const textareaClass = `${inputClass} min-h-[88px] resize-y`
const cardBase = 'rounded-lg border px-4 py-3 text-left transition-colors'

function formatLabel(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function agentLabel(agent: Agent | undefined, fallbackId: number) {
  return agent?.contact_name || `Agent #${fallbackId}`
}

function triggerKindLabel(kind: TeamTriggerDraftKind) {
  if (kind === 'gmail') return 'Gmail'
  if (kind === 'github') return 'GitHub'
  if (kind === 'jira') return 'Jira'
  return 'Webhook'
}

function triggerKindIcon(kind: TeamTriggerDraftKind) {
  if (kind === 'gmail') return <MailIcon size={18} />
  if (kind === 'github') return <GitHubIcon size={18} />
  return <WebhookIcon size={18} />
}

function parseFilters(text: string): Record<string, unknown> {
  const trimmed = text.trim()
  if (!trimmed) return {}
  const parsed = JSON.parse(trimmed)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Trigger filters must be a JSON object.')
  }
  return parsed as Record<string, unknown>
}

function triggerOptionKey(option: TriggerOption) {
  return `${option.kind}:${option.id}`
}

function makeTriggerDraft(option: TriggerOption): TeamTriggerDraft {
  return {
    uid: `${option.kind}:${option.id}:${Date.now()}`,
    trigger_kind: option.kind,
    trigger_instance_id: option.id,
    event_types: option.defaultEvents,
    filters_text: '{}',
    is_enabled: true,
    label: option.label,
  }
}

function activeWebhookOptions(items: WebhookIntegration[]): TriggerOption[] {
  return items
    .filter((item) => item.is_active && item.status === 'active')
    .map((item) => ({
      kind: 'webhook' as const,
      id: item.id,
      label: item.integration_name || `Webhook #${item.id}`,
      detail: item.slug || item.inbound_url || `Webhook #${item.id}`,
      defaultEvents: defaultTeamTriggerEvents('webhook', item),
    }))
}

function activeGitHubOptions(items: GitHubTrigger[]): TriggerOption[] {
  return items
    .filter((item) => item.is_active && item.status === 'active')
    .map((item) => ({
      kind: 'github' as const,
      id: item.id,
      label: item.integration_name || `${item.repo_owner}/${item.repo_name}`,
      detail: `${item.repo_owner}/${item.repo_name}`,
      defaultEvents: defaultTeamTriggerEvents('github', item),
    }))
}

function activeJiraOptions(items: JiraTrigger[]): TriggerOption[] {
  return items
    .filter((item) => item.is_active && item.status === 'active')
    .map((item) => ({
      kind: 'jira' as const,
      id: item.id,
      label: item.integration_name || item.jira_integration_name || `Jira #${item.id}`,
      detail: item.project_key || item.site_url || item.jql,
      defaultEvents: defaultTeamTriggerEvents('jira', item),
    }))
}

function activeEmailOptions(items: EmailTrigger[]): TriggerOption[] {
  return items
    .filter((item) => item.is_active && item.status === 'active')
    .map((item) => ({
      kind: 'gmail' as const,
      id: item.id,
      label: item.integration_name || `Gmail #${item.id}`,
      detail: item.search_query || item.health_status_reason || 'Gmail trigger',
      defaultEvents: defaultTeamTriggerEvents('gmail', item),
    }))
}

export default function TeamWizard() {
  const router = useRouter()
  const teamWizard = useTeamWizard()
  const agentWizard = useAgentWizard()
  const {
    state,
    steps,
    currentStepNumber,
    totalSteps,
    closeWizard,
    resetWizard,
    nextStep,
    previousStep,
    goToStep,
    patchDraft,
    applyTemplate,
    addMember,
    removeMember,
    patchMember,
    reorderMember,
    addTrigger,
    removeTrigger,
    patchTrigger,
    setProgress,
    setCreatedTeam,
    clearPersistedDraft,
    fireComplete,
  } = teamWizard
  const draft = state.draft

  const [agents, setAgents] = useState<Agent[]>([])
  const [triggerOptions, setTriggerOptions] = useState<TriggerOption[]>([])
  const [loadingResources, setLoadingResources] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [agentSelectValue, setAgentSelectValue] = useState('')
  const [triggerSelectValue, setTriggerSelectValue] = useState('')

  const wizardSteps = useMemo<WizardStep[]>(
    () => steps.map((step) => ({
      id: step,
      label: STEP_META[step].label,
      description: STEP_META[step].description,
    })),
    [steps],
  )

  const loadResources = useCallback(async () => {
    setLoadingResources(true)
    setLoadError(null)
    try {
      const agentRows = await api.getAgents(true)
      setAgents(agentRows)

      const [webhookRows, githubRows, jiraRows, emailRows] = await Promise.all([
        api.listWebhookIntegrations().catch(() => [] as WebhookIntegration[]),
        api.listGitHubTriggers().catch(() => [] as GitHubTrigger[]),
        api.listJiraTriggers().catch(() => [] as JiraTrigger[]),
        api.listEmailTriggers().catch(() => [] as EmailTrigger[]),
      ])
      setTriggerOptions([
        ...activeWebhookOptions(webhookRows),
        ...activeGitHubOptions(githubRows),
        ...activeJiraOptions(jiraRows),
        ...activeEmailOptions(emailRows),
      ])
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Failed to load wizard data')
    } finally {
      setLoadingResources(false)
    }
  }, [])

  useEffect(() => {
    if (state.isOpen) {
      loadResources()
    }
  }, [loadResources, state.isOpen])

  useAgentWizardComplete((agentId) => {
    loadResources()
    addMember({
      agent_id: agentId,
      is_required: true,
      position_x: null,
      position_y: null,
    })
  })

  const selectedAgentIds = useMemo(() => new Set(draft.members.map((member) => member.agent_id)), [draft.members])
  const agentById = useMemo(() => new Map(agents.map((agent) => [agent.id, agent])), [agents])
  const triggerByKey = useMemo(() => new Map(triggerOptions.map((option) => [triggerOptionKey(option), option])), [triggerOptions])

  const availableAgents = useMemo(
    () => agents.filter((agent) => !selectedAgentIds.has(agent.id) && !agent.is_team_member),
    [agents, selectedAgentIds],
  )

  const currentMeta = STEP_META[state.currentStep]
  const isCreating = state.progressStatus === 'running'
  const canAdvance = state.stepsCompleted[state.currentStep]
  const canCreate = state.stepsCompleted.review && !isCreating

  const addSelectedAgent = () => {
    const agentId = Number(agentSelectValue)
    if (!Number.isFinite(agentId) || agentId <= 0) return
    addMember({
      agent_id: agentId,
      is_required: true,
      position_x: null,
      position_y: null,
    })
    setAgentSelectValue('')
  }

  const addSelectedTrigger = () => {
    const option = triggerByKey.get(triggerSelectValue)
    if (!option) return
    addTrigger(makeTriggerDraft(option))
    setTriggerSelectValue('')
  }

  const buildCreatePayload = (teamDraft: TeamWizardDraft) => ({
    name: teamDraft.name.trim(),
    description: teamDraft.description.trim() || null,
    goal_text: teamDraft.goal_text.trim() || null,
    topology: teamDraft.topology,
    status: teamDraft.status,
    max_steps: teamDraft.max_steps,
    max_total_tokens: teamDraft.max_total_tokens,
    max_concurrent_runs: teamDraft.max_concurrent_runs,
    members: teamDraft.members.map((member) => ({
      agent_id: member.agent_id,
      execution_order: member.execution_order,
      is_required: member.is_required,
      position_x: member.position_x,
      position_y: member.position_y,
    })),
  })

  const createTeam = async () => {
    if (!canCreate) return
    setProgress({ status: 'running', message: 'Creating team...' })
    goToStep('create')
    try {
      const triggerPayloads = draft.triggers.map((trigger) => ({
        trigger_kind: trigger.trigger_kind,
        trigger_instance_id: trigger.trigger_instance_id,
        event_types: trigger.event_types,
        filters: parseFilters(trigger.filters_text),
        is_enabled: trigger.is_enabled,
      }))

      const team = await api.createTeam(buildCreatePayload(draft))
      for (const triggerPayload of triggerPayloads) {
        await api.createTeamTrigger(team.id, triggerPayload)
      }

      setCreatedTeam(team.id)
      clearPersistedDraft()
      fireComplete(team.id)
      resetWizard()
      router.push(`/studio/teams/${team.id}`)
    } catch (error) {
      setProgress({
        status: 'error',
        message: error instanceof Error ? error.message : 'Failed to create team',
      })
    }
  }

  const footer = (
    <div className="flex w-full flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-2">
        {currentStepNumber > 1 && (
          <button
            type="button"
            onClick={previousStep}
            disabled={isCreating}
            className="btn-ghost inline-flex items-center gap-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            Back
          </button>
        )}
        <button
          type="button"
          onClick={resetWizard}
          disabled={isCreating}
          className="px-4 py-2 text-sm text-tsushin-slate transition-colors hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
      <div className="flex items-center justify-end gap-2">
        <span className="text-xs text-tsushin-muted">Step {currentStepNumber} of {totalSteps}</span>
        {state.currentStep === 'create' ? (
          <button
            type="button"
            onClick={createTeam}
            disabled={!canCreate}
            className="btn-primary inline-flex items-center gap-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isCreating ? <RefreshIcon size={16} className="animate-spin" /> : <CheckCircleIcon size={16} />}
            {isCreating ? 'Creating' : 'Create Team'}
          </button>
        ) : state.currentStep === 'review' ? (
          <button
            type="button"
            onClick={() => goToStep('create')}
            disabled={!canAdvance}
            className="btn-primary inline-flex items-center gap-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            <CheckCircleIcon size={16} />
            Continue
          </button>
        ) : (
          <button
            type="button"
            onClick={nextStep}
            disabled={!canAdvance}
            className="btn-primary inline-flex items-center gap-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
          >
            Continue
          </button>
        )}
      </div>
    </div>
  )

  return (
    <Wizard
      isOpen={state.isOpen}
      onClose={closeWizard}
      title="Create Agent Team"
      steps={wizardSteps}
      currentStep={currentStepNumber}
      footer={footer}
      size="2xl"
      autoHeight
      showProgress
      stepTitle={currentMeta.title}
      stepDescription={currentMeta.body}
      status={
        state.currentStep === 'create' && state.progressStatus === 'running'
          ? 'loading'
          : state.currentStep === 'create' && state.progressStatus === 'error'
          ? 'error'
          : null
      }
      statusTitle={state.progressStatus === 'error' ? 'Could not create team' : 'Creating team'}
      statusDescription={state.progressMessage}
    >
      {loadError && (
        <div className="rounded-lg border border-tsushin-vermilion/25 bg-tsushin-vermilion/10 px-4 py-3 text-sm text-tsushin-vermilion">
          <div className="flex items-center gap-2">
            <AlertCircleIcon size={16} />
            {loadError}
          </div>
        </div>
      )}
      {loadingResources && (
        <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/40 px-4 py-3 text-sm text-tsushin-slate">
          <RefreshIcon size={16} className="mr-2 inline animate-spin" />
          Loading choices
        </div>
      )}
      {renderStep()}
    </Wizard>
  )

  function renderStep() {
    switch (state.currentStep) {
      case 'template':
        return <TemplateStep selected={draft.template_id} onSelect={applyTemplate} />
      case 'basics':
        return <BasicsStep draft={draft} patchDraft={patchDraft} />
      case 'topology':
        return <TopologyStep draft={draft} patchDraft={patchDraft} />
      case 'members':
        return (
          <MembersStep
            draft={draft}
            agents={agents}
            agentById={agentById}
            availableAgents={availableAgents}
            agentSelectValue={agentSelectValue}
            setAgentSelectValue={setAgentSelectValue}
            addSelectedAgent={addSelectedAgent}
            removeMember={removeMember}
            patchMember={patchMember}
            reorderMember={reorderMember}
            openAgentWizard={() => agentWizard.openWizard()}
          />
        )
      case 'triggers':
        return (
          <TriggersStep
            draft={draft}
            triggerOptions={triggerOptions}
            triggerSelectValue={triggerSelectValue}
            setTriggerSelectValue={setTriggerSelectValue}
            addSelectedTrigger={addSelectedTrigger}
            removeTrigger={removeTrigger}
            patchTrigger={patchTrigger}
          />
        )
      case 'review':
        return (
          <ReviewStep
            draft={draft}
            agents={agentById}
          />
        )
      case 'create':
        return (
          <CreateStep
            draft={draft}
            agents={agentById}
            createTeam={createTeam}
            isCreating={isCreating}
          />
        )
      default:
        return null
    }
  }
}

function TemplateStep({
  selected,
  onSelect,
}: {
  selected: TeamTemplateId
  onSelect: (templateId: TeamTemplateId) => void
}) {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {TEAM_TEMPLATE_PRESETS.map((preset) => {
        const active = selected === preset.id
        return (
          <button
            key={preset.id}
            type="button"
            onClick={() => onSelect(preset.id)}
            aria-pressed={active}
            className={`${cardBase} ${
              active
                ? 'border-tsushin-accent bg-tsushin-accent/10 text-white'
                : 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-slate hover:border-tsushin-muted hover:text-white'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="font-semibold text-white">{preset.name}</div>
                <p className="mt-1 text-sm leading-6 text-tsushin-slate">{preset.description}</p>
              </div>
              {active && <CheckCircleIcon size={18} className="text-tsushin-success" />}
            </div>
          </button>
        )
      })}
    </div>
  )
}

function BasicsStep({
  draft,
  patchDraft,
}: {
  draft: TeamWizardDraft
  patchDraft: (patch: Partial<TeamWizardDraft>) => void
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <label className="space-y-2">
        <span className="text-sm font-medium text-tsushin-fog">Name</span>
        <input
          value={draft.name}
          onChange={(event) => patchDraft({ name: event.target.value })}
          className={inputClass}
          placeholder="Release Review Team"
        />
      </label>
      <label className="space-y-2">
        <span className="text-sm font-medium text-tsushin-fog">Status</span>
        <select
          value={draft.status}
          onChange={(event) => patchDraft({ status: event.target.value as TeamWizardDraft['status'] })}
          className="select text-sm"
        >
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="paused">Paused</option>
        </select>
      </label>
      <label className="space-y-2 md:col-span-2">
        <span className="text-sm font-medium text-tsushin-fog">Description</span>
        <input
          value={draft.description}
          onChange={(event) => patchDraft({ description: event.target.value })}
          className={inputClass}
          placeholder="Short summary that shows in the team listing"
        />
      </label>
      <label className="space-y-2 md:col-span-2">
        <span className="text-sm font-medium text-tsushin-fog">Goal</span>
        <textarea
          value={draft.goal_text}
          onChange={(event) => patchDraft({ goal_text: event.target.value })}
          className={textareaClass}
          placeholder="Review a release candidate and summarize readiness with evidence."
        />
      </label>
    </div>
  )
}

function TopologyStep({
  draft,
  patchDraft,
}: {
  draft: TeamWizardDraft
  patchDraft: (patch: Partial<TeamWizardDraft>) => void
}) {
  return (
    <div className="space-y-5">
      <div className="grid gap-3 md:grid-cols-2">
        {(['line', 'mesh'] as const).map((topology) => {
          const active = draft.topology === topology
          return (
            <button
              key={topology}
              type="button"
              onClick={() => patchDraft({ topology })}
              aria-pressed={active}
              className={`${cardBase} ${
                active
                  ? 'border-tsushin-accent bg-tsushin-accent/10'
                  : 'border-tsushin-border bg-tsushin-surface/40 hover:border-tsushin-muted'
              }`}
            >
              <div className="flex items-center gap-3">
                <UsersIcon size={18} className={active ? 'text-tsushin-accent' : 'text-tsushin-slate'} />
                <div>
                  <div className="font-semibold text-white">{formatLabel(topology)}</div>
                  <div className="mt-1 text-sm text-tsushin-slate">
                    {topology === 'line'
                      ? 'Members run one after another, passing the result down the chain. Best when each step depends on the previous one (e.g. intake → diagnose → summarize).'
                      : 'A coordinator dispatches work to multiple members in parallel and merges their answers. Best for cross-checking or gathering different perspectives.'}
                  </div>
                </div>
              </div>
            </button>
          )
        })}
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <NumberField
          label="Max steps"
          hint="The team stops after this many member turns. Prevents runaway loops."
          value={draft.max_steps}
          min={1}
          max={100}
          onChange={(value) => patchDraft({ max_steps: value })}
        />
        <NumberField
          label="Concurrent runs"
          hint="How many team runs can be in flight at the same time."
          value={draft.max_concurrent_runs}
          min={1}
          max={10}
          onChange={(value) => patchDraft({ max_concurrent_runs: value })}
        />
        <NumberField
          label="Token cap (optional)"
          hint="Run is cut off after this many total tokens are spent. Leave blank for no cap."
          value={draft.max_total_tokens ?? ''}
          min={1}
          max={10000000}
          onChange={(value) => patchDraft({ max_total_tokens: value || null })}
        />
      </div>
    </div>
  )
}

function NumberField({
  label,
  hint,
  value,
  min,
  max,
  onChange,
}: {
  label: string
  hint?: string
  value: number | ''
  min: number
  max: number
  onChange: (value: number | '') => void
}) {
  return (
    <label className="space-y-2">
      <span className="text-sm font-medium text-tsushin-fog">{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => {
          const next = event.target.value
          onChange(next === '' ? '' : Number(next))
        }}
        className={inputClass}
      />
      {hint && <span className="block text-xs text-tsushin-slate">{hint}</span>}
    </label>
  )
}

function MembersStep({
  draft,
  agents,
  agentById,
  availableAgents,
  agentSelectValue,
  setAgentSelectValue,
  addSelectedAgent,
  removeMember,
  patchMember,
  reorderMember,
  openAgentWizard,
}: {
  draft: TeamWizardDraft
  agents: Agent[]
  agentById: Map<number, Agent>
  availableAgents: Agent[]
  agentSelectValue: string
  setAgentSelectValue: (value: string) => void
  addSelectedAgent: () => void
  removeMember: (agentId: number) => void
  patchMember: (agentId: number, patch: Partial<TeamWizardDraft['members'][number]>) => void
  reorderMember: (agentId: number, direction: 'up' | 'down') => void
  openAgentWizard: () => void
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row">
        <select
          value={agentSelectValue}
          onChange={(event) => setAgentSelectValue(event.target.value)}
          className="select text-sm md:flex-1"
        >
          <option value="">Select an available agent</option>
          {availableAgents.map((agent) => (
            <option key={agent.id} value={agent.id}>{agent.contact_name}</option>
          ))}
        </select>
        <button type="button" onClick={addSelectedAgent} disabled={!agentSelectValue} className="btn-primary inline-flex items-center justify-center gap-2 text-sm disabled:opacity-50">
          <PlusIcon size={16} />
          Add
        </button>
        <button type="button" onClick={openAgentWizard} className="btn-secondary inline-flex items-center justify-center gap-2 text-sm">
          <BotIcon size={16} />
          New Agent
        </button>
      </div>

      {draft.members.length === 0 ? (
        <div className="rounded-lg border border-dashed border-tsushin-border px-4 py-8 text-center text-sm text-tsushin-slate">
          No members selected.
        </div>
      ) : (
        <div className="divide-y divide-tsushin-border/40 rounded-lg border border-tsushin-border bg-tsushin-surface/30">
          {draft.members.map((member, index) => (
            <div key={member.agent_id} className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-tsushin-indigo/15 text-sm font-semibold text-tsushin-indigo-glow">
                  {member.execution_order}
                </div>
                <div>
                  <div className="font-medium text-white">{agentLabel(agentById.get(member.agent_id), member.agent_id)}</div>
                  <div className="text-xs text-tsushin-slate">Agent #{member.agent_id}</div>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex items-center gap-2 text-sm text-tsushin-slate">
                  <input
                    type="checkbox"
                    checked={member.is_required}
                    onChange={(event) => patchMember(member.agent_id, { is_required: event.target.checked })}
                  />
                  Required
                </label>
                <button type="button" onClick={() => reorderMember(member.agent_id, 'up')} disabled={index === 0} className="btn-icon disabled:cursor-not-allowed disabled:opacity-40" title="Move up">
                  <ArrowUpIcon size={16} />
                </button>
                <button type="button" onClick={() => reorderMember(member.agent_id, 'down')} disabled={index === draft.members.length - 1} className="btn-icon disabled:cursor-not-allowed disabled:opacity-40" title="Move down">
                  <ArrowDownIcon size={16} />
                </button>
                <button type="button" onClick={() => removeMember(member.agent_id)} className="btn-icon text-tsushin-vermilion hover:text-tsushin-vermilion" title="Remove">
                  <TrashIcon size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {agents.some((agent) => agent.is_team_member && !draft.members.some((member) => member.agent_id === agent.id)) && (
        <div className="rounded-lg border border-tsushin-indigo/25 bg-tsushin-indigo/10 px-4 py-3 text-sm text-tsushin-slate">
          Agents already assigned to another team are hidden from selection.
        </div>
      )}
    </div>
  )
}

function TriggersStep({
  draft,
  triggerOptions,
  triggerSelectValue,
  setTriggerSelectValue,
  addSelectedTrigger,
  removeTrigger,
  patchTrigger,
}: {
  draft: TeamWizardDraft
  triggerOptions: TriggerOption[]
  triggerSelectValue: string
  setTriggerSelectValue: (value: string) => void
  addSelectedTrigger: () => void
  removeTrigger: (uid: string) => void
  patchTrigger: (uid: string, patch: Partial<TeamTriggerDraft>) => void
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row">
        <select
          value={triggerSelectValue}
          onChange={(event) => setTriggerSelectValue(event.target.value)}
          className="select text-sm md:flex-1"
        >
          <option value="">Select an active trigger</option>
          {triggerOptions.map((option) => (
            <option key={triggerOptionKey(option)} value={triggerOptionKey(option)}>
              {triggerKindLabel(option.kind)} - {option.label}
            </option>
          ))}
        </select>
        <button type="button" onClick={addSelectedTrigger} disabled={!triggerSelectValue} className="btn-primary inline-flex items-center justify-center gap-2 text-sm disabled:opacity-50">
          <PlusIcon size={16} />
          Bind
        </button>
      </div>

      {draft.triggers.length === 0 ? (
        <div className="rounded-lg border border-dashed border-tsushin-border px-4 py-8 text-center text-sm text-tsushin-slate">
          No trigger bindings selected.
        </div>
      ) : (
        <div className="space-y-3">
          {draft.triggers.map((trigger) => (
            <div key={trigger.uid} className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex items-center gap-3">
                  {triggerKindIcon(trigger.trigger_kind)}
                  <div>
                    <div className="font-semibold text-white">{triggerKindLabel(trigger.trigger_kind)} - {trigger.label}</div>
                    <div className="text-xs text-tsushin-slate">Instance #{trigger.trigger_instance_id}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <label className="inline-flex items-center gap-2 text-sm text-tsushin-slate">
                    <input
                      type="checkbox"
                      checked={trigger.is_enabled}
                      onChange={(event) => patchTrigger(trigger.uid, { is_enabled: event.target.checked })}
                    />
                    Enabled
                  </label>
                  <button type="button" onClick={() => removeTrigger(trigger.uid)} className="btn-icon text-tsushin-vermilion hover:text-tsushin-vermilion" title="Remove">
                    <TrashIcon size={16} />
                  </button>
                </div>
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                <label className="space-y-2">
                  <span className="text-sm font-medium text-tsushin-fog">Event types</span>
                  <textarea
                    value={trigger.event_types.join(', ')}
                    onChange={(event) => patchTrigger(trigger.uid, { event_types: eventTypesFromInput(event.target.value) })}
                    className={`${inputClass} min-h-[72px] resize-y`}
                    placeholder="message.created, github.pull_request, jira.issue.detected, email.message.received"
                  />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-tsushin-fog">Filters JSON</span>
                  <textarea
                    value={trigger.filters_text}
                    onChange={(event) => patchTrigger(trigger.uid, { filters_text: event.target.value })}
                    className={`${inputClass} min-h-[72px] resize-y font-mono`}
                    placeholder="{}"
                  />
                </label>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ReviewStep({
  draft,
  agents,
}: {
  draft: TeamWizardDraft
  agents: Map<number, Agent>
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <ReviewPanel title="Team">
        <ReviewRow label="Name" value={draft.name || 'Missing'} />
        <ReviewRow label="Status" value={formatLabel(draft.status)} />
        <ReviewRow label="Topology" value={formatLabel(draft.topology)} />
        <ReviewRow label="Run limits" value={`${draft.max_concurrent_runs} concurrent, ${draft.max_steps} steps`} />
        <ReviewRow label="Goal" value={draft.goal_text || 'Missing'} />
      </ReviewPanel>
      <ReviewPanel title="Members">
        {draft.members.length === 0 ? (
          <div className="text-sm text-tsushin-vermilion">No members selected.</div>
        ) : draft.members.map((member) => (
          <ReviewRow
            key={member.agent_id}
            label={`#${member.execution_order}`}
            value={`${agentLabel(agents.get(member.agent_id), member.agent_id)}${member.is_required ? ' - required' : ''}`}
          />
        ))}
      </ReviewPanel>
      <ReviewPanel title="Triggers">
        {draft.triggers.length === 0 ? (
          <div className="text-sm text-tsushin-slate">No trigger bindings selected.</div>
        ) : draft.triggers.map((trigger) => (
          <ReviewRow
            key={trigger.uid}
            label={triggerKindLabel(trigger.trigger_kind)}
            value={`${trigger.label} (${trigger.event_types.join(', ') || 'all events'})`}
          />
        ))}
      </ReviewPanel>
    </div>
  )
}

function CreateStep({
  draft,
  agents,
  createTeam,
  isCreating,
}: {
  draft: TeamWizardDraft
  agents: Map<number, Agent>
  createTeam: () => void
  isCreating: boolean
}) {
  return (
    <div className="space-y-4">
      <ReviewStep draft={draft} agents={agents} />
      <button
        type="button"
        onClick={createTeam}
        disabled={isCreating}
        className="btn-primary inline-flex w-full items-center justify-center gap-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isCreating ? <RefreshIcon size={16} className="animate-spin" /> : <CheckCircleIcon size={16} />}
        {isCreating ? 'Creating Team' : 'Create Team'}
      </button>
    </div>
  )
}

function ReviewPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 p-4">
      <div className="mb-3 text-sm font-semibold text-white">{title}</div>
      <div className="space-y-2">{children}</div>
    </div>
  )
}

function ReviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid grid-cols-[96px_1fr] gap-3 text-sm">
      <div className="text-tsushin-muted">{label}</div>
      <div className="min-w-0 break-words text-tsushin-fog">{value}</div>
    </div>
  )
}
