'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import { useWatcherActivity } from '@/hooks/useWatcherActivity'
import {
  api,
  type TeamRunMemberStep,
  type WatcherTeamRunDetail,
  type WatcherTeamRunListItem,
} from '@/lib/client'
import { formatDateTimeFull } from '@/lib/dateUtils'
import {
  AlertTriangleIcon,
  BotIcon,
  BrainIcon,
  CheckCircleIcon,
  ClockIcon,
  EyeIcon,
  FilterIcon,
  RefreshIcon,
  ShieldIcon,
  UsersIcon,
  XCircleIcon,
  ZapIcon,
} from '@/components/ui/icons'

const STATUS_OPTIONS = [
  'pending',
  'running',
  'completed',
  'failed',
  'goal_not_achieved',
  'timeout',
  'sentinel_blocked',
  'cancelled',
]

const TERMINAL_STATUSES = new Set(['completed', 'failed', 'goal_not_achieved', 'timeout', 'sentinel_blocked', 'cancelled'])

function label(value?: string | null): string {
  if (!value) return '-'
  return value.split('_').join(' ').replace(/\b\w/g, char => char.toUpperCase())
}

function formatMaybeDate(value?: string | null): string {
  return value ? formatDateTimeFull(value) : '-'
}

function statusClass(status: string): string {
  switch (status) {
    case 'completed':
      return 'border-green-500/30 bg-green-500/10 text-green-300'
    case 'running':
      return 'border-cyan-500/35 bg-cyan-500/10 text-cyan-200'
    case 'pending':
      return 'border-amber-500/35 bg-amber-500/10 text-amber-200'
    case 'sentinel_blocked':
      return 'border-orange-500/35 bg-orange-500/10 text-orange-200'
    case 'failed':
    case 'timeout':
      return 'border-red-500/40 bg-red-500/10 text-red-200'
    case 'cancelled':
      return 'border-gray-500/35 bg-gray-500/10 text-gray-300'
    default:
      return 'border-tsushin-border bg-tsushin-surface/60 text-tsushin-slate'
  }
}

function durationLabel(start?: string | null, end?: string | null): string {
  if (!start) return '-'
  const startMs = new Date(start).getTime()
  const endMs = end ? new Date(end).getTime() : Date.now()
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) return '-'
  const seconds = Math.round((endMs - startMs) / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rem = seconds % 60
  return `${minutes}m ${rem}s`
}

function dateParam(value: string, endOfDay = false): string | undefined {
  if (!value) return undefined
  return `${value}T${endOfDay ? '23:59:59' : '00:00:00'}Z`
}

function JsonBlock({ value }: { value: unknown }) {
  if (value == null) return null
  return (
    <pre className="max-h-56 overflow-auto rounded-lg bg-tsushin-deep p-3 text-xs text-tsushin-slate">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

function Metric({ label: metricLabel, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-tsushin-border/60 bg-tsushin-surface/40 p-3">
      <div className="text-xs uppercase text-tsushin-muted">{metricLabel}</div>
      <div className="mt-1 text-sm font-medium text-white">{value}</div>
    </div>
  )
}

function StepRow({ step }: { step: TeamRunMemberStep }) {
  return (
    <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/35 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-medium text-white">
            Step {step.step_index + 1}: {step.agent_name || `Agent #${step.agent_id || '-'}`}
          </div>
          <div className="mt-1 text-xs text-tsushin-slate">
            {formatMaybeDate(step.started_at || step.created_at)} · {durationLabel(step.started_at, step.completed_at)}
          </div>
        </div>
        <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusClass(step.status)}`}>
          {label(step.status)}
        </span>
      </div>
      {step.output_summary && <p className="mt-3 whitespace-pre-wrap text-sm text-tsushin-slate">{step.output_summary}</p>}
      {step.output_text && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs font-medium text-tsushin-muted hover:text-white">Output</summary>
          <p className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap rounded-lg bg-tsushin-deep p-3 text-xs text-tsushin-slate">
            {step.output_text}
          </p>
        </details>
      )}
      {step.sentinel_decision_json && (
        <details className="mt-3">
          <summary className="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-orange-200 hover:text-orange-100">
            <ShieldIcon size={13} />
            Sentinel
          </summary>
          <div className="mt-2">
            <JsonBlock value={step.sentinel_decision_json} />
          </div>
        </details>
      )}
      {step.error_json && (
        <details className="mt-3">
          <summary className="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-red-200 hover:text-red-100">
            <AlertTriangleIcon size={13} />
            Error
          </summary>
          <div className="mt-2">
            <JsonBlock value={step.error_json} />
          </div>
        </details>
      )}
    </div>
  )
}

export default function TeamRunsTab() {
  const [runs, setRuns] = useState<WatcherTeamRunListItem[]>([])
  const [total, setTotal] = useState(0)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [selectedRun, setSelectedRun] = useState<WatcherTeamRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [teamFilter, setTeamFilter] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const latestEventRef = useRef<string | null>(null)

  const {
    isConnected,
    activeTeamRuns,
    recentTeamRunActivity,
  } = useWatcherActivity({ enabled: true })

  const loadRuns = useCallback(async () => {
    setError(null)
    try {
      const response = await api.getWatcherTeamRuns({
        limit: 50,
        offset: 0,
        teamId: teamFilter ? Number(teamFilter) : null,
        status: statusFilter || undefined,
        createdAfter: dateParam(dateFrom),
        createdBefore: dateParam(dateTo, true),
      })
      setRuns(response.items)
      setTotal(response.total)
      if (selectedRunId && !response.items.some(run => run.id === selectedRunId)) {
        setSelectedRunId(null)
        setSelectedRun(null)
      }
    } catch (err) {
      console.error('Failed to load watcher team runs:', err)
      setError(err instanceof Error ? err.message : 'Failed to load team runs')
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, selectedRunId, statusFilter, teamFilter])

  const loadDetail = useCallback(async (runId: number) => {
    setDetailLoading(true)
    try {
      const detail = await api.getWatcherTeamRun(runId)
      setSelectedRun(detail)
      setSelectedRunId(runId)
    } catch (err) {
      console.error('Failed to load watcher team run detail:', err)
      setError(err instanceof Error ? err.message : 'Failed to load run detail')
    } finally {
      setDetailLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRuns()
  }, [loadRuns])

  useGlobalRefresh(() => loadRuns())

  useEffect(() => {
    const latest = recentTeamRunActivity[0]
    if (!latest) return
    const key = `${latest.team_run_id}:${latest.event}:${latest.status}:${latest.timestamp}`
    if (latestEventRef.current === key) return
    latestEventRef.current = key
    loadRuns()
    if (selectedRunId === latest.team_run_id) {
      loadDetail(latest.team_run_id)
    }
  }, [loadDetail, loadRuns, recentTeamRunActivity, selectedRunId])

  const teamOptions = useMemo(() => {
    const map = new Map<number, string>()
    runs.forEach(run => map.set(run.team_id, run.team_name || `Team #${run.team_id}`))
    return Array.from(map.entries()).sort((a, b) => a[1].localeCompare(b[1]))
  }, [runs])

  const summary = useMemo(() => {
    const running = runs.filter(run => !TERMINAL_STATUSES.has(run.status)).length
    const failed = runs.filter(run => ['failed', 'timeout', 'sentinel_blocked', 'goal_not_achieved'].includes(run.status)).length
    return { running, failed }
  }, [runs])

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-4">
        <Metric label="Visible Runs" value={String(runs.length)} />
        <Metric label="Total Matches" value={String(total)} />
        <Metric label="Active" value={String(summary.running)} />
        <Metric label="Needs Review" value={String(summary.failed)} />
      </div>

      <section className="glass-card rounded-xl p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <h2 className="inline-flex items-center gap-2 text-lg font-display font-semibold text-white">
              <UsersIcon size={18} />
              Team Runs
            </h2>
            <div className="mt-2 inline-flex items-center gap-2 text-xs text-tsushin-slate">
              <span className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-gray-500'}`} />
              Watcher WS {isConnected ? 'connected' : 'disconnected'}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[180px_180px_150px_150px_auto]">
            <label className="block">
              <span className="mb-1 block text-xs font-medium uppercase text-tsushin-muted">
                <FilterIcon size={12} className="mr-1 inline" />
                Team
              </span>
              <select
                value={teamFilter}
                onChange={(event) => setTeamFilter(event.target.value)}
                className="w-full rounded-lg border border-tsushin-border bg-tsushin-surface px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
              >
                <option value="">All teams</option>
                {teamOptions.map(([teamId, teamName]) => (
                  <option key={teamId} value={teamId}>{teamName}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium uppercase text-tsushin-muted">Status</span>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                className="w-full rounded-lg border border-tsushin-border bg-tsushin-surface px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
              >
                <option value="">All statuses</option>
                {STATUS_OPTIONS.map(status => (
                  <option key={status} value={status}>{label(status)}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium uppercase text-tsushin-muted">From</span>
              <input
                type="date"
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
                className="w-full rounded-lg border border-tsushin-border bg-tsushin-surface px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium uppercase text-tsushin-muted">To</span>
              <input
                type="date"
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
                className="w-full rounded-lg border border-tsushin-border bg-tsushin-surface px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/20"
              />
            </label>
            <button
              type="button"
              onClick={loadRuns}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-white transition-colors hover:bg-tsushin-elevated"
            >
              <RefreshIcon size={15} />
              Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
            {error}
          </div>
        )}

        <div className="mt-5 overflow-x-auto">
          <table className="min-w-full divide-y divide-tsushin-border/60">
            <thead className="bg-tsushin-surface/40">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-tsushin-muted">Run</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-tsushin-muted">Team</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-tsushin-muted">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-tsushin-muted">Progress</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-tsushin-muted">Started</th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-tsushin-muted">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-tsushin-border/40">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-tsushin-slate">Loading team runs...</td>
                </tr>
              ) : runs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-tsushin-slate">No team runs found.</td>
                </tr>
              ) : runs.map(run => {
                const live = activeTeamRuns.get(run.id)
                return (
                  <tr
                    key={run.id}
                    onClick={() => loadDetail(run.id)}
                    className={`cursor-pointer transition-colors hover:bg-tsushin-surface/50 ${
                      selectedRunId === run.id ? 'bg-tsushin-indigo/10' : ''
                    }`}
                  >
                    <td className="px-4 py-3 text-sm font-medium text-white">
                      <span className="inline-flex items-center gap-2">
                        <EyeIcon size={14} className="text-tsushin-muted" />
                        #{run.id}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-sm font-medium text-white">{run.team_name}</div>
                      <div className="text-xs text-tsushin-slate">{label(run.topology_snapshot)} · {run.member_count} members</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium ${statusClass(run.status)}`}>
                        {live && <ZapIcon size={12} />}
                        {label(run.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-tsushin-slate">
                      {run.completed_steps}/{run.total_steps || run.member_count} steps
                    </td>
                    <td className="px-4 py-3 text-sm text-tsushin-slate">
                      {formatMaybeDate(run.started_at || run.created_at)}
                    </td>
                    <td className="px-4 py-3 text-sm text-tsushin-slate">
                      {run.total_cost_cents} cents
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section className="glass-card rounded-xl p-5">
        <h2 className="mb-4 inline-flex items-center gap-2 text-lg font-display font-semibold text-white">
          <ClockIcon size={18} />
          Run Detail
        </h2>
        {detailLoading ? (
          <div className="py-8 text-center text-tsushin-slate">Loading run detail...</div>
        ) : !selectedRun ? (
          <div className="py-8 text-center text-tsushin-slate">Select a run to inspect its member timeline.</div>
        ) : (
          <div className="space-y-5">
            <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/35 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-base font-semibold text-white">{selectedRun.team_name} · Run #{selectedRun.id}</h3>
                    <p className="mt-1 text-sm text-tsushin-slate">{selectedRun.goal_text_snapshot || 'No goal snapshot'}</p>
                  </div>
                  <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusClass(selectedRun.status)}`}>
                    {label(selectedRun.status)}
                  </span>
                </div>
                {selectedRun.final_output_summary && (
                  <p className="mt-4 whitespace-pre-wrap text-sm text-tsushin-slate">{selectedRun.final_output_summary}</p>
                )}
                {selectedRun.error_json && (
                  <details className="mt-4">
                    <summary className="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-red-200 hover:text-red-100">
                      <XCircleIcon size={13} />
                      Run error
                    </summary>
                    <div className="mt-2">
                      <JsonBlock value={selectedRun.error_json} />
                    </div>
                  </details>
                )}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Metric label="Duration" value={durationLabel(selectedRun.started_at, selectedRun.completed_at)} />
                <Metric label="Progress" value={`${selectedRun.completed_steps}/${selectedRun.total_steps} steps`} />
                <Metric label="Tokens" value={`${selectedRun.total_input_tokens + selectedRun.total_output_tokens}`} />
                <Metric label="Cost" value={`${selectedRun.total_cost_cents} cents`} />
              </div>
            </div>

            {selectedRun.coordinator_commands.length > 0 && (
              <div>
                <h3 className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-white">
                  <BrainIcon size={16} />
                  Coordinator Dispatch
                </h3>
                <div className="space-y-3">
                  {selectedRun.coordinator_commands.map(command => (
                    <div key={command.member_run_id} className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-4">
                      <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-sm">
                        <span className="font-medium text-amber-100">Step {command.step_index + 1}: {command.agent_name || 'Coordinator'}</span>
                        <span className="text-xs text-tsushin-slate">{command.created_at ? formatDateTimeFull(command.created_at) : '-'}</span>
                      </div>
                      <JsonBlock value={command.command} />
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <h3 className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-white">
                <BotIcon size={16} />
                Member Timeline
              </h3>
              {selectedRun.member_runs.length === 0 ? (
                <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/35 p-6 text-center text-sm text-tsushin-slate">
                  No member steps recorded yet.
                </div>
              ) : (
                <div className="space-y-3">
                  {selectedRun.member_runs.map(step => <StepRow key={step.id} step={step} />)}
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {recentTeamRunActivity.length > 0 && (
        <section className="glass-card rounded-xl p-5">
          <h2 className="mb-4 inline-flex items-center gap-2 text-lg font-display font-semibold text-white">
            <CheckCircleIcon size={18} />
            Live Events
          </h2>
          <div className="space-y-2">
            {recentTeamRunActivity.slice(0, 6).map(event => (
              <div key={`${event.team_run_id}-${event.event}-${event.timestamp}`} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-tsushin-border bg-tsushin-surface/35 px-4 py-3 text-sm">
                <span className="text-white">Run #{event.team_run_id} · {label(event.event)}</span>
                <span className="text-xs text-tsushin-slate">{formatDateTimeFull(event.timestamp)}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
