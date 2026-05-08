'use client'

import dynamic from 'next/dynamic'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { useRequireAuth } from '@/contexts/AuthContext'
import StudioTabs from '@/components/studio/StudioTabs'
import DetailShellHeader from '@/components/ui/DetailShell'
import {
  AlertCircleIcon,
  ArchiveIcon,
  BotIcon,
  CheckCircleIcon,
  ClockIcon,
  GitHubIcon,
  PlayIcon,
  RefreshIcon,
  SaveIcon,
  SettingsIcon,
  ShieldIcon,
  TrashIcon,
  UsersIcon,
  WebhookIcon,
  XCircleIcon,
} from '@/components/ui/icons'
import {
  api,
  type Agent,
  type GitHubTrigger,
  type JiraTrigger,
  type SentinelProfile,
  type TeamDetail,
  type TeamMemberResponse,
  type TeamRunDetail,
  type TeamRunListItem,
  type TeamStatus,
  type TeamTriggerBindingKind,
  type TeamTriggerResponse,
  type WebhookIntegration,
} from '@/lib/client'

const TeamCanvas = dynamic(() => import('@/components/watcher/team/TeamCanvas'), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[440px] items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-tsushin-indigo/30 border-t-tsushin-indigo" />
    </div>
  ),
})

type TeamTab = 'topology' | 'triggers' | 'sentinel' | 'runs' | 'settings'

type TriggerOption = {
  key: string
  kind: TeamTriggerBindingKind
  id: number
  label: string
  detail: string
}

const TABS: Array<{ id: TeamTab; label: string; icon: ReactNode }> = [
  { id: 'topology', label: 'Topology', icon: <UsersIcon size={15} /> },
  { id: 'triggers', label: 'Triggers', icon: <WebhookIcon size={15} /> },
  { id: 'sentinel', label: 'Sentinel', icon: <ShieldIcon size={15} /> },
  { id: 'runs', label: 'Runs', icon: <PlayIcon size={15} /> },
  { id: 'settings', label: 'Settings', icon: <SettingsIcon size={15} /> },
]

const ACTIVE_RUN_STATUSES = new Set(['pending', 'running'])
const TERMINAL_RUN_STATUSES = new Set(['completed', 'failed', 'timeout', 'cancelled', 'goal_not_achieved', 'sentinel_blocked'])
const FIELD_BASE = 'rounded-lg border border-tsushin-border bg-tsushin-surface px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-tsushin-muted focus:border-tsushin-indigo disabled:cursor-not-allowed disabled:opacity-60'
const SELECT_BASE = `${FIELD_BASE} appearance-none`
const TEXTAREA_BASE = `${FIELD_BASE} resize-y`

type SettingsForm = {
  name: string
  description: string
  goal_text: string
  status: string
  max_steps: number
  max_total_tokens: string
  max_concurrent_runs: number
}

const STATUS_STYLES: Record<string, string> = {
  active: 'badge-success',
  draft: 'badge-neutral',
  paused: 'badge-warning',
  archived: 'badge-danger',
  pending: 'badge-warning',
  running: 'badge-indigo',
  completed: 'badge-success',
  failed: 'badge-danger',
  timeout: 'badge-danger',
  cancelled: 'badge-neutral',
  goal_not_achieved: 'badge-warning',
  sentinel_blocked: 'badge-danger',
}

function isTeamTab(value: string | null): value is TeamTab {
  return value === 'topology' || value === 'triggers' || value === 'sentinel' || value === 'runs' || value === 'settings'
}

function formatLabel(value?: string | null) {
  if (!value) return 'None'
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function formatDate(value?: string | null) {
  if (!value) return 'Never'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Never'
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function durationLabel(start?: string | null, end?: string | null) {
  if (!start) return 'Not started'
  const startMs = new Date(start).getTime()
  const endMs = end ? new Date(end).getTime() : Date.now()
  if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs < startMs) return 'Unknown'
  const totalSeconds = Math.max(1, Math.round((endMs - startMs) / 1000))
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`
}

function parseFilters(text: string) {
  const trimmed = text.trim()
  if (!trimmed) return {}
  const parsed = JSON.parse(trimmed)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
    throw new Error('Filters must be a JSON object.')
  }
  return parsed as Record<string, unknown>
}

function eventTypesFromInput(value: string) {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function triggerKindLabel(kind: string) {
  if (kind === 'github') return 'GitHub'
  if (kind === 'jira') return 'Jira'
  if (kind === 'webhook') return 'Webhook'
  return formatLabel(kind)
}

function buildTriggerOptions(
  webhooks: WebhookIntegration[],
  github: GitHubTrigger[],
  jira: JiraTrigger[],
): TriggerOption[] {
  const active = (item: { is_active: boolean; status: string }) => item.is_active && item.status === 'active'
  return [
    ...webhooks.filter(active).map((item) => ({
      key: `webhook:${item.id}`,
      kind: 'webhook' as const,
      id: item.id,
      label: item.integration_name || `Webhook #${item.id}`,
      detail: item.health_status_reason || item.health_status || 'Webhook trigger',
    })),
    ...github.filter(active).map((item) => ({
      key: `github:${item.id}`,
      kind: 'github' as const,
      id: item.id,
      label: item.integration_name || `GitHub #${item.id}`,
      detail: item.health_status_reason || item.health_status || 'GitHub trigger',
    })),
    ...jira.filter(active).map((item) => ({
      key: `jira:${item.id}`,
      kind: 'jira' as const,
      id: item.id,
      label: item.integration_name || `Jira #${item.id}`,
      detail: item.jql || item.health_status_reason || 'Jira trigger',
    })),
  ]
}

export default function StudioTeamDetailPage() {
  useRequireAuth()
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const searchParams = useSearchParams()
  const teamId = Number(params.id)
  const activeTab = isTeamTab(searchParams.get('tab')) ? searchParams.get('tab') as TeamTab : 'topology'

  const [team, setTeam] = useState<TeamDetail | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [sentinelProfiles, setSentinelProfiles] = useState<SentinelProfile[]>([])
  const [triggerOptions, setTriggerOptions] = useState<TriggerOption[]>([])
  const [runs, setRuns] = useState<TeamRunListItem[]>([])
  const [selectedRun, setSelectedRun] = useState<TeamRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const [settingsForm, setSettingsForm] = useState({
    name: '',
    description: '',
    goal_text: '',
    status: 'draft',
    max_steps: 10,
    max_total_tokens: '',
    max_concurrent_runs: 1,
  })
  const [sentinelProfileId, setSentinelProfileId] = useState('')
  const [newTriggerKey, setNewTriggerKey] = useState('')
  const [newTriggerEvents, setNewTriggerEvents] = useState('')
  const [newTriggerFilters, setNewTriggerFilters] = useState('{}')
  const [triggerEdits, setTriggerEdits] = useState<Record<number, { eventTypes: string; filters: string; enabled: boolean }>>({})

  const activeRun = useMemo(
    () => runs.find((run) => ACTIVE_RUN_STATUSES.has(run.status)) || (team?.last_run && ACTIVE_RUN_STATUSES.has(team.last_run.status) ? team.last_run : null),
    [runs, team],
  )
  const readOnly = Boolean(activeRun) || team?.status === 'archived'
  const teamMemberIds = useMemo(() => new Set(team?.members.map((member) => member.agent_id) || []), [team])
  const addableAgents = useMemo(
    () => agents.filter((agent) => agent.is_active && !agent.is_team_member && !teamMemberIds.has(agent.id)),
    [agents, teamMemberIds],
  )

  const setTab = (tab: TeamTab) => {
    router.replace(`/studio/teams/${teamId}?tab=${tab}`, { scroll: false })
  }

  const loadRuns = useCallback(async () => {
    if (!Number.isFinite(teamId) || teamId <= 0) return
    const response = await api.getTeamRuns(teamId, { page: 1, pageSize: 20 })
    setRuns(response.items)
    return response.items
  }, [teamId])

  const loadAll = useCallback(async () => {
    if (!Number.isFinite(teamId) || teamId <= 0) {
      setError('Invalid team id')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [teamRow, agentRows, sentinelRows, webhookRows, githubRows, jiraRows, runRows] = await Promise.all([
        api.getTeam(teamId),
        api.getAgents(true),
        api.getSentinelProfiles(true).catch(() => [] as SentinelProfile[]),
        api.listWebhookIntegrations().catch(() => [] as WebhookIntegration[]),
        api.listGitHubTriggers().catch(() => [] as GitHubTrigger[]),
        api.listJiraTriggers().catch(() => [] as JiraTrigger[]),
        api.getTeamRuns(teamId, { page: 1, pageSize: 20 }).catch(() => ({ items: [], total: 0, page: 1, page_size: 20 })),
      ])
      setTeam(teamRow)
      setAgents(agentRows)
      setSentinelProfiles(sentinelRows.filter((profile) => profile.is_enabled))
      setTriggerOptions(buildTriggerOptions(webhookRows, githubRows, jiraRows))
      setRuns(runRows.items)
      setSettingsForm({
        name: teamRow.name,
        description: teamRow.description || '',
        goal_text: teamRow.goal_text || '',
        status: teamRow.status,
        max_steps: teamRow.max_steps,
        max_total_tokens: teamRow.max_total_tokens ? String(teamRow.max_total_tokens) : '',
        max_concurrent_runs: teamRow.max_concurrent_runs,
      })
      setSentinelProfileId(teamRow.sentinel_profile_id ? String(teamRow.sentinel_profile_id) : '')
      setTriggerEdits(Object.fromEntries(teamRow.triggers.map((trigger) => [
        trigger.id,
        {
          eventTypes: trigger.event_types.join(', '),
          filters: JSON.stringify(trigger.filters || {}, null, 2),
          enabled: trigger.is_enabled,
        },
      ])))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load team')
    } finally {
      setLoading(false)
    }
  }, [teamId])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  useEffect(() => {
    const handleRefresh = () => loadAll()
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [loadAll])

  useEffect(() => {
    if (!activeRun || TERMINAL_RUN_STATUSES.has(activeRun.status)) return
    const timer = window.setInterval(async () => {
      try {
        const items = await loadRuns()
        const latestActive = items?.find((run) => ACTIVE_RUN_STATUSES.has(run.status))
        if (!latestActive) await loadAll()
      } catch {
        // Keep polling quiet; explicit refresh still surfaces errors.
      }
    }, 3000)
    return () => window.clearInterval(timer)
  }, [activeRun, loadAll, loadRuns])

  const runAction = async (action: () => Promise<void>, success: string) => {
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      await action()
      setNotice(success)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  const handleAddMember = async (agent: Agent, position: { x: number; y: number }) => {
    await runAction(async () => {
      await api.addTeamMember(teamId, {
        agent_id: agent.id,
        execution_order: team?.members.length ?? 0,
        is_required: true,
        position_x: position.x,
        position_y: position.y,
      })
      await loadAll()
    }, 'Member added.')
  }

  const handleRemoveMember = async (member: TeamMemberResponse) => {
    if (!window.confirm(`Remove ${member.agent_name || `agent #${member.agent_id}`} from this team?`)) return
    await runAction(async () => {
      await api.removeTeamAgentMember(teamId, member.agent_id)
      await loadAll()
    }, 'Member removed and A2A permissions restored.')
  }

  const handleReorderMembers = async (members: TeamMemberResponse[]) => {
    await runAction(async () => {
      await api.reorderTeamMembers(teamId, members.map((member, index) => ({ agent_id: member.agent_id, execution_order: index })))
      await loadAll()
    }, 'Member order saved.')
  }

  const handleUpdateMemberPosition = async (member: TeamMemberResponse, position: { x: number; y: number }) => {
    await api.updateTeamMember(teamId, member.agent_id, { position_x: position.x, position_y: position.y })
  }

  const handleToggleRequired = async (member: TeamMemberResponse) => {
    await runAction(async () => {
      await api.updateTeamMember(teamId, member.agent_id, { is_required: !member.is_required })
      await loadAll()
    }, 'Member requirement updated.')
  }

  const handleResetLayout = async () => {
    if (!team) return
    const targets = team.members.filter((member) => member.role !== 'coordinator')
    if (targets.length === 0) return
    await runAction(async () => {
      await Promise.all(
        targets.map((member) =>
          api.updateTeamMember(teamId, member.agent_id, { position_x: null, position_y: null }),
        ),
      )
      await loadAll()
    }, 'Layout reset to defaults.')
  }

  const handleCreateTrigger = async () => {
    const option = triggerOptions.find((item) => item.key === newTriggerKey)
    if (!option) return
    await runAction(async () => {
      await api.createTeamTrigger(teamId, {
        trigger_kind: option.kind,
        trigger_instance_id: option.id,
        event_types: eventTypesFromInput(newTriggerEvents),
        filters: parseFilters(newTriggerFilters),
        is_enabled: true,
      })
      setNewTriggerKey('')
      setNewTriggerEvents('')
      setNewTriggerFilters('{}')
      await loadAll()
    }, 'Trigger binding saved.')
  }

  const handleUpdateTrigger = async (trigger: TeamTriggerResponse) => {
    const edit = triggerEdits[trigger.id]
    if (!edit) return
    await runAction(async () => {
      await api.updateTeamTrigger(teamId, trigger.id, {
        event_types: eventTypesFromInput(edit.eventTypes),
        filters: parseFilters(edit.filters),
        is_enabled: edit.enabled,
      })
      await loadAll()
    }, 'Trigger binding updated.')
  }

  const handleDeleteTrigger = async (trigger: TeamTriggerResponse) => {
    if (!window.confirm(`Remove ${triggerKindLabel(trigger.trigger_kind)} trigger binding?`)) return
    await runAction(async () => {
      await api.deleteTeamTrigger(teamId, trigger.id)
      await loadAll()
    }, 'Trigger binding removed.')
  }

  const handleSaveSentinel = async () => {
    await runAction(async () => {
      await api.updateTeam(teamId, { sentinel_profile_id: sentinelProfileId ? Number(sentinelProfileId) : null })
      await loadAll()
    }, 'Sentinel profile saved.')
  }

  const handleStartRun = async () => {
    await runAction(async () => {
      const started = await api.startTeamRun(teamId)
      await loadRuns()
      const detail = await api.getTeamRun(teamId, started.run_id)
      setSelectedRun(detail)
      setTab('runs')
    }, 'Team run started.')
  }

  const handleSelectRun = async (run: TeamRunListItem) => {
    await runAction(async () => {
      setSelectedRun(await api.getTeamRun(teamId, run.id))
    }, 'Run detail loaded.')
  }

  const handleCancelRun = async (run: TeamRunListItem) => {
    if (!window.confirm(`Cancel team run #${run.id}?`)) return
    await runAction(async () => {
      setSelectedRun(await api.cancelTeamRun(teamId, run.id))
      await loadRuns()
    }, 'Run cancelled.')
  }

  const handleSaveSettings = async () => {
    await runAction(async () => {
      await api.updateTeam(teamId, {
        name: settingsForm.name,
        description: settingsForm.description || null,
        goal_text: settingsForm.goal_text || null,
        status: settingsForm.status as TeamStatus,
        max_steps: Number(settingsForm.max_steps),
        max_total_tokens: settingsForm.max_total_tokens ? Number(settingsForm.max_total_tokens) : null,
        max_concurrent_runs: Number(settingsForm.max_concurrent_runs),
      })
      await loadAll()
    }, 'Team settings saved.')
  }

  const handleArchive = async () => {
    if (!team || !window.confirm(`Archive ${team.name}? This removes visible members but preserves run history.`)) return
    await runAction(async () => {
      await api.archiveTeam(teamId)
      router.push('/studio/teams')
    }, 'Team archived.')
  }

  const handleDeletePermanently = async () => {
    if (!team) return
    const typed = window.prompt(
      `Permanently delete ${team.name}? This destroys all triggers and run history and cannot be undone.\n\nType the team name to confirm:`,
    )
    if (typed === null) return
    if (typed.trim() !== team.name) {
      window.alert('Team name did not match. Deletion cancelled.')
      return
    }
    await runAction(async () => {
      await api.deleteTeamPermanently(teamId)
      router.push('/studio/teams')
    }, 'Team permanently deleted.')
  }

  return (
    <div className="min-h-screen animate-fade-in">
      <div className="container mx-auto px-4 py-8 sm:px-6 lg:px-8">
        <DetailShellHeader
          breadcrumb={[
            { label: 'Studio', href: '/agents' },
            { label: 'Teams', href: '/studio/teams' },
            { label: team?.name || 'Agent Team' },
          ]}
          title={team?.name || 'Agent Team'}
          badges={
            <>
              {team && <span className={`badge ${STATUS_STYLES[team.status] || 'badge-neutral'}`}>{formatLabel(team.status)}</span>}
              {readOnly && <span className="badge badge-warning">Read only</span>}
            </>
          }
          description={team?.description || 'Build, run, and monitor this team.'}
          actions={
            <>
              <button
                type="button"
                onClick={handleStartRun}
                disabled={busy || readOnly || team?.status !== 'active'}
                className="btn-primary inline-flex items-center justify-center gap-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
              >
                <PlayIcon size={16} />
                Run Now
              </button>
              <button
                type="button"
                onClick={loadAll}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm font-medium text-tsushin-slate transition-colors hover:border-tsushin-muted hover:text-white"
              >
                <RefreshIcon size={16} />
                Refresh
              </button>
            </>
          }
        />

        <div className="space-y-5">
          <StudioTabs />

          {notice && (
            <div className="rounded-xl border border-tsushin-success/25 bg-tsushin-success/10 px-4 py-3 text-sm text-tsushin-success">
              <div className="flex items-center gap-2">
                <CheckCircleIcon size={16} />
                {notice}
              </div>
            </div>
          )}
          {error && (
            <div className="rounded-xl border border-tsushin-vermilion/25 bg-tsushin-vermilion/10 px-4 py-3 text-sm text-tsushin-vermilion">
              <div className="flex items-center gap-2">
                <AlertCircleIcon size={16} />
                {error}
              </div>
            </div>
          )}
          {activeRun && (
            <div className="rounded-xl border border-tsushin-warning/25 bg-tsushin-warning/10 px-4 py-3 text-sm text-tsushin-warning">
              <div className="flex items-center gap-2">
                <ClockIcon size={16} />
                Team run #{activeRun.id} is {formatLabel(activeRun.status)}. Editing is disabled until it finishes.
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2 border-b border-tsushin-border/60">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setTab(tab.id)}
                className={`inline-flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'border-tsushin-indigo text-white'
                    : 'border-transparent text-tsushin-slate hover:text-white'
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="glass-card flex items-center justify-center rounded-xl py-16">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-tsushin-indigo/30 border-t-tsushin-indigo" />
            </div>
          ) : team ? (
            <>
              {activeTab === 'topology' && (
                <section className="glass-card overflow-hidden rounded-xl">
                  <div className="flex flex-col gap-3 border-b border-tsushin-border/50 px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h2 className="text-lg font-display font-semibold text-white">Topology</h2>
                      <p className="text-sm text-tsushin-slate">
                        {formatLabel(team.topology)} team with {team.members.length} visible members.
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2 text-xs text-tsushin-slate">
                      <span className="badge badge-team">{addableAgents.length} addable agents</span>
                    </div>
                  </div>
                  <div className="h-[620px] min-h-[480px]">
                    <TeamCanvas
                      team={team}
                      agents={agents}
                      addableAgents={addableAgents}
                      readOnly={readOnly || busy}
                      onAddMember={handleAddMember}
                      onRemoveMember={handleRemoveMember}
                      onReorderMembers={handleReorderMembers}
                      onUpdateMemberPosition={handleUpdateMemberPosition}
                      onToggleRequired={handleToggleRequired}
                      onResetLayout={handleResetLayout}
                    />
                  </div>
                </section>
              )}

              {activeTab === 'triggers' && (
                <TriggersTab
                  team={team}
                  triggerOptions={triggerOptions}
                  triggerEdits={triggerEdits}
                  setTriggerEdits={setTriggerEdits}
                  newTriggerKey={newTriggerKey}
                  setNewTriggerKey={setNewTriggerKey}
                  newTriggerEvents={newTriggerEvents}
                  setNewTriggerEvents={setNewTriggerEvents}
                  newTriggerFilters={newTriggerFilters}
                  setNewTriggerFilters={setNewTriggerFilters}
                  readOnly={readOnly || busy}
                  onCreate={handleCreateTrigger}
                  onUpdate={handleUpdateTrigger}
                  onDelete={handleDeleteTrigger}
                />
              )}

              {activeTab === 'sentinel' && (
                <SentinelTab
                  team={team}
                  profiles={sentinelProfiles}
                  sentinelProfileId={sentinelProfileId}
                  setSentinelProfileId={setSentinelProfileId}
                  readOnly={readOnly || busy}
                  onSave={handleSaveSentinel}
                />
              )}

              {activeTab === 'runs' && (
                <RunsTab
                  runs={runs}
                  selectedRun={selectedRun}
                  readOnly={busy}
                  onRefresh={loadRuns}
                  onSelect={handleSelectRun}
                  onStart={handleStartRun}
                  onCancel={handleCancelRun}
                />
              )}

              {activeTab === 'settings' && (
                <SettingsTab
                  form={settingsForm}
                  setForm={setSettingsForm}
                  readOnly={readOnly || busy}
                  isArchived={team?.status === 'archived'}
                  busy={busy}
                  onSave={handleSaveSettings}
                  onArchive={handleArchive}
                  onDeletePermanently={handleDeletePermanently}
                />
              )}
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function TriggersTab({
  team,
  triggerOptions,
  triggerEdits,
  setTriggerEdits,
  newTriggerKey,
  setNewTriggerKey,
  newTriggerEvents,
  setNewTriggerEvents,
  newTriggerFilters,
  setNewTriggerFilters,
  readOnly,
  onCreate,
  onUpdate,
  onDelete,
}: {
  team: TeamDetail
  triggerOptions: TriggerOption[]
  triggerEdits: Record<number, { eventTypes: string; filters: string; enabled: boolean }>
  setTriggerEdits: (value: Record<number, { eventTypes: string; filters: string; enabled: boolean }>) => void
  newTriggerKey: string
  setNewTriggerKey: (value: string) => void
  newTriggerEvents: string
  setNewTriggerEvents: (value: string) => void
  newTriggerFilters: string
  setNewTriggerFilters: (value: string) => void
  readOnly: boolean
  onCreate: () => void
  onUpdate: (trigger: TeamTriggerResponse) => void
  onDelete: (trigger: TeamTriggerResponse) => void
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
      <section className="glass-card rounded-xl p-5">
        <h2 className="mb-1 text-lg font-display font-semibold text-white">Add Trigger Binding</h2>
        <p className="mb-5 text-sm text-tsushin-slate">Attach an existing Webhook, GitHub, or Jira trigger to this team.</p>
        <div className="space-y-4">
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Trigger</span>
            <select value={newTriggerKey} onChange={(event) => setNewTriggerKey(event.target.value)} disabled={readOnly} className={`${SELECT_BASE} w-full`}>
              <option value="">Select an active trigger</option>
              {triggerOptions.map((option) => (
                <option key={option.key} value={option.key}>{triggerKindLabel(option.kind)} - {option.label}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Event types</span>
            <input value={newTriggerEvents} onChange={(event) => setNewTriggerEvents(event.target.value)} disabled={readOnly} className={`${FIELD_BASE} w-full`} placeholder="Optional, comma separated" />
          </label>
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Filters JSON</span>
            <textarea value={newTriggerFilters} onChange={(event) => setNewTriggerFilters(event.target.value)} disabled={readOnly} className={`${TEXTAREA_BASE} min-h-[120px] w-full font-mono text-xs`} />
          </label>
          <button type="button" onClick={onCreate} disabled={readOnly || !newTriggerKey} className="btn-primary inline-flex items-center gap-2 text-sm disabled:opacity-50">
            <WebhookIcon size={16} />
            Add Binding
          </button>
        </div>
      </section>

      <section className="glass-card rounded-xl p-5">
        <h2 className="mb-4 text-lg font-display font-semibold text-white">Current Bindings</h2>
        {team.triggers.length === 0 ? (
          <EmptyState icon={<WebhookIcon size={28} />} title="No trigger bindings" body="Wizard failures or skipped trigger setup can be recovered here." />
        ) : (
          <div className="space-y-4">
            {team.triggers.map((trigger) => {
              const edit = triggerEdits[trigger.id] || { eventTypes: '', filters: '{}', enabled: trigger.is_enabled }
              return (
                <div key={trigger.id} className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 p-4">
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      {trigger.trigger_kind === 'github' ? <GitHubIcon size={16} /> : <WebhookIcon size={16} />}
                      <div className="font-medium text-white">{triggerKindLabel(trigger.trigger_kind)} #{trigger.trigger_instance_id}</div>
                    </div>
                    <label className="inline-flex items-center gap-2 text-sm text-tsushin-slate">
                      <input
                        type="checkbox"
                        checked={edit.enabled}
                        disabled={readOnly}
                        onChange={(event) => setTriggerEdits({ ...triggerEdits, [trigger.id]: { ...edit, enabled: event.target.checked } })}
                      />
                      Enabled
                    </label>
                  </div>
                  <div className="grid gap-3 lg:grid-cols-2">
                    <input
                      value={edit.eventTypes}
                      disabled={readOnly}
                      onChange={(event) => setTriggerEdits({ ...triggerEdits, [trigger.id]: { ...edit, eventTypes: event.target.value } })}
                      className={`${FIELD_BASE} w-full`}
                      placeholder="Event types"
                    />
                    <textarea
                      value={edit.filters}
                      disabled={readOnly}
                      onChange={(event) => setTriggerEdits({ ...triggerEdits, [trigger.id]: { ...edit, filters: event.target.value } })}
                      className={`${TEXTAREA_BASE} min-h-[88px] w-full font-mono text-xs`}
                    />
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button type="button" onClick={() => onUpdate(trigger)} disabled={readOnly} className="btn-secondary inline-flex items-center gap-2 text-sm disabled:opacity-50">
                      <SaveIcon size={15} />
                      Save
                    </button>
                    <button type="button" onClick={() => onDelete(trigger)} disabled={readOnly} className="inline-flex items-center gap-2 rounded-lg border border-tsushin-vermilion/30 px-3 py-2 text-sm text-tsushin-vermilion transition-colors hover:bg-tsushin-vermilion/10 disabled:opacity-50">
                      <TrashIcon size={15} />
                      Remove
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}

function SentinelTab({
  team,
  profiles,
  sentinelProfileId,
  setSentinelProfileId,
  readOnly,
  onSave,
}: {
  team: TeamDetail
  profiles: SentinelProfile[]
  sentinelProfileId: string
  setSentinelProfileId: (value: string) => void
  readOnly: boolean
  onSave: () => void
}) {
  const selected = profiles.find((profile) => String(profile.id) === sentinelProfileId)
  return (
    <section className="glass-card rounded-xl p-5">
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-lg font-display font-semibold text-white">Team Sentinel Profile</h2>
          <p className="mt-1 text-sm text-tsushin-slate">
            Team profile overrides member profiles for team run start and handoff checks.
          </p>
        </div>
        <span className={`badge ${team.sentinel_profile_id ? 'badge-indigo' : 'badge-neutral'}`}>
          {team.sentinel_profile_id ? 'Team override' : 'Inherited'}
        </span>
      </div>
      <div className="grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
        <div>
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Profile</span>
            <select value={sentinelProfileId} onChange={(event) => setSentinelProfileId(event.target.value)} disabled={readOnly} className={`${SELECT_BASE} w-full`}>
              <option value="">Inherit tenant/member effective profile</option>
              {profiles.map((profile) => (
                <option key={profile.id} value={profile.id}>{profile.name} ({formatLabel(profile.detection_mode)})</option>
              ))}
            </select>
          </label>
          <button type="button" onClick={onSave} disabled={readOnly} className="btn-primary mt-4 inline-flex items-center gap-2 text-sm disabled:opacity-50">
            <ShieldIcon size={16} />
            Save Sentinel Profile
          </button>
        </div>
        <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 p-4">
          {selected ? (
            <div className="space-y-3 text-sm">
              <Metric label="Mode" value={formatLabel(selected.detection_mode)} />
              <Metric label="Aggressiveness" value={String(selected.aggressiveness_level)} />
              <Metric label="LLM" value={`${selected.llm_provider} / ${selected.llm_model}`} />
              <Metric label="Block on detection" value={selected.block_on_detection ? 'Yes' : 'No'} />
            </div>
          ) : (
            <EmptyState icon={<ShieldIcon size={28} />} title="Inherited profile" body="Runs use the existing Sentinel tenant/member hierarchy unless a team override is selected." />
          )}
        </div>
      </div>
    </section>
  )
}

function RunsTab({
  runs,
  selectedRun,
  readOnly,
  onRefresh,
  onSelect,
  onStart,
  onCancel,
}: {
  runs: TeamRunListItem[]
  selectedRun: TeamRunDetail | null
  readOnly: boolean
  onRefresh: () => void
  onSelect: (run: TeamRunListItem) => void
  onStart: () => void
  onCancel: (run: TeamRunListItem) => void
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
      <section className="glass-card rounded-xl p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-lg font-display font-semibold text-white">Run History</h2>
          <div className="flex gap-2">
            <button type="button" onClick={onStart} disabled={readOnly} className="btn-primary inline-flex items-center gap-2 text-sm disabled:opacity-50">
              <PlayIcon size={15} />
              Run Now
            </button>
            <button type="button" onClick={onRefresh} className="btn-secondary inline-flex items-center gap-2 text-sm">
              <RefreshIcon size={15} />
              Refresh
            </button>
          </div>
        </div>
        {runs.length === 0 ? (
          <EmptyState icon={<PlayIcon size={28} />} title="No runs yet" body="Start this team manually or bind a trigger to create run history." />
        ) : (
          <div className="space-y-3">
            {runs.map((run) => (
              <button
                key={run.id}
                type="button"
                onClick={() => onSelect(run)}
                className={`w-full rounded-lg border p-4 text-left transition-colors ${
                  selectedRun?.id === run.id ? 'border-tsushin-indigo bg-tsushin-indigo/10' : 'border-tsushin-border bg-tsushin-surface/30 hover:border-tsushin-muted'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium text-white">Run #{run.id}</div>
                  <span className={`badge ${STATUS_STYLES[run.status] || 'badge-neutral'}`}>{formatLabel(run.status)}</span>
                </div>
                <div className="mt-2 grid gap-2 text-xs text-tsushin-slate sm:grid-cols-3">
                  <span>{formatDate(run.started_at || run.created_at)}</span>
                  <span>{run.completed_steps}/{run.total_steps} steps</span>
                  <span>{durationLabel(run.started_at, run.completed_at)}</span>
                </div>
                {ACTIVE_RUN_STATUSES.has(run.status) && (
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation()
                      onCancel(run)
                    }}
                    className="mt-3 inline-flex items-center gap-1 text-xs text-tsushin-vermilion hover:text-tsushin-vermilion"
                  >
                    <XCircleIcon size={13} />
                    Cancel
                  </button>
                )}
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="glass-card rounded-xl p-5">
        <h2 className="mb-4 text-lg font-display font-semibold text-white">Run Detail</h2>
        {!selectedRun ? (
          <EmptyState icon={<ClockIcon size={28} />} title="Select a run" body="Member timeline, outputs, token usage, and Sentinel decisions appear here." />
        ) : (
          <div className="space-y-4">
            <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-semibold text-white">Run #{selectedRun.id}</h3>
                <span className={`badge ${STATUS_STYLES[selectedRun.status] || 'badge-neutral'}`}>{formatLabel(selectedRun.status)}</span>
              </div>
              <div className="grid gap-3 text-sm sm:grid-cols-3">
                <Metric label="Duration" value={durationLabel(selectedRun.started_at, selectedRun.completed_at)} />
                <Metric label="Tokens" value={`${selectedRun.total_input_tokens + selectedRun.total_output_tokens}`} />
                <Metric label="Cost" value={`${selectedRun.total_cost_cents} cents`} />
              </div>
              {selectedRun.final_output_summary && <p className="mt-4 whitespace-pre-wrap text-sm text-tsushin-slate">{selectedRun.final_output_summary}</p>}
            </div>
            <div className="space-y-3">
              {selectedRun.member_runs.length === 0 ? (
                <EmptyState icon={<BotIcon size={28} />} title="No member steps yet" body="The run may still be pending." />
              ) : selectedRun.member_runs.map((step) => (
                <div key={step.id} className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="font-medium text-white">Step {step.step_index + 1}: {step.agent_name || `Agent #${step.agent_id || '-'}`}</div>
                      <div className="mt-1 text-xs text-tsushin-slate">{formatDate(step.started_at || step.created_at)} - {durationLabel(step.started_at, step.completed_at)}</div>
                    </div>
                    <span className={`badge ${STATUS_STYLES[step.status] || 'badge-neutral'}`}>{formatLabel(step.status)}</span>
                  </div>
                  {step.output_summary && <p className="mt-3 text-sm text-tsushin-slate">{step.output_summary}</p>}
                  {step.sentinel_decision_json && (
                    <pre className="mt-3 max-h-40 overflow-auto rounded-lg bg-tsushin-deep p-3 text-xs text-tsushin-slate">
                      {JSON.stringify(step.sentinel_decision_json, null, 2)}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}

function SettingsTab({
  form,
  setForm,
  readOnly,
  isArchived,
  busy,
  onSave,
  onArchive,
  onDeletePermanently,
}: {
  form: SettingsForm
  setForm: (value: SettingsForm) => void
  readOnly: boolean
  isArchived: boolean
  busy: boolean
  onSave: () => void
  onArchive: () => void
  onDeletePermanently: () => void
}) {
  return (
    <section className="glass-card rounded-xl p-5">
      <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-lg font-display font-semibold text-white">Settings</h2>
          <p className="text-sm text-tsushin-slate">Update identity, run limits, and lifecycle.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isArchived ? (
            <button
              type="button"
              onClick={onDeletePermanently}
              disabled={busy}
              className="inline-flex items-center gap-2 rounded-lg border border-tsushin-vermilion/60 bg-tsushin-vermilion/10 px-4 py-2 text-sm text-tsushin-vermilion transition-colors hover:bg-tsushin-vermilion/20 disabled:opacity-50"
            >
              <TrashIcon size={16} />
              Delete permanently
            </button>
          ) : (
            <button
              type="button"
              onClick={onArchive}
              disabled={readOnly}
              className="inline-flex items-center gap-2 rounded-lg border border-tsushin-vermilion/30 px-4 py-2 text-sm text-tsushin-vermilion transition-colors hover:bg-tsushin-vermilion/10 disabled:opacity-50"
            >
              <ArchiveIcon size={16} />
              Archive
            </button>
          )}
        </div>
      </div>
      <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="space-y-4">
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Name</span>
            <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} disabled={readOnly} className={`${FIELD_BASE} w-full`} />
          </label>
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Description</span>
            <textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} disabled={readOnly} className={`${TEXTAREA_BASE} min-h-[88px] w-full`} />
          </label>
          <label className="block">
            <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Goal</span>
            <textarea value={form.goal_text} onChange={(event) => setForm({ ...form, goal_text: event.target.value })} disabled={readOnly} className={`${TEXTAREA_BASE} min-h-[120px] w-full`} />
          </label>
        </div>
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Status</span>
              <select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value })} disabled={readOnly} className={`${SELECT_BASE} w-full`}>
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="paused">Paused</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Max steps</span>
              <input type="number" min={1} max={100} value={form.max_steps} onChange={(event) => setForm({ ...form, max_steps: Number(event.target.value) })} disabled={readOnly} className={`${FIELD_BASE} w-full`} />
            </label>
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Token cap</span>
              <input type="number" min={1} value={form.max_total_tokens} onChange={(event) => setForm({ ...form, max_total_tokens: event.target.value })} disabled={readOnly} className={`${FIELD_BASE} w-full`} placeholder="None" />
            </label>
            <label className="block">
              <span className="mb-2 block text-xs font-medium uppercase text-tsushin-muted">Concurrent runs</span>
              <input type="number" min={1} max={10} value={form.max_concurrent_runs} onChange={(event) => setForm({ ...form, max_concurrent_runs: Number(event.target.value) })} disabled={readOnly} className={`${FIELD_BASE} w-full`} />
            </label>
          </div>
          <button type="button" onClick={onSave} disabled={readOnly} className="btn-primary inline-flex items-center gap-2 text-sm disabled:opacity-50">
            <SaveIcon size={16} />
            Save Settings
          </button>
        </div>
      </div>
    </section>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-tsushin-muted">{label}</div>
      <div className="mt-1 font-medium text-white">{value}</div>
    </div>
  )
}

function EmptyState({ icon, title, body }: { icon: ReactNode; title: string; body: string }) {
  return (
    <div className="rounded-lg border border-dashed border-tsushin-border px-4 py-8 text-center">
      <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-tsushin-surface text-tsushin-slate">{icon}</div>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-sm text-tsushin-slate">{body}</p>
    </div>
  )
}
