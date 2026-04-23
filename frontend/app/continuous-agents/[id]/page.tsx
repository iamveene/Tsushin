'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { api, type ContinuousAgent, type ContinuousRun, type PageResponse } from '@/lib/client'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import { ActivityIcon, AlertTriangleIcon, BotIcon, ClockIcon, EyeIcon, RefreshIcon } from '@/components/ui/icons'

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

function statusClass(status: string): string {
  const normalized = status.toLowerCase()
  if (['active', 'running', 'success', 'completed'].includes(normalized)) {
    return 'bg-green-500/10 text-green-300 border-green-500/30'
  }
  if (['queued', 'pending', 'paused'].includes(normalized)) {
    return 'bg-yellow-500/10 text-yellow-300 border-yellow-500/30'
  }
  if (['failed', 'error', 'disabled'].includes(normalized)) {
    return 'bg-red-500/10 text-red-300 border-red-500/30'
  }
  return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
}

function JsonBlock({ value }: { value: unknown }) {
  if (value == null) {
    return <span className="text-tsushin-slate">None</span>
  }
  return (
    <pre className="max-h-64 overflow-auto rounded-lg border border-tsushin-border bg-black/30 p-3 text-xs text-tsushin-fog">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export default function ContinuousAgentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const agentId = Number(params.id)
  const hasValidId = Number.isFinite(agentId) && agentId > 0
  const [agent, setAgent] = useState<ContinuousAgent | null>(null)
  const [runsPage, setRunsPage] = useState<PageResponse<ContinuousRun> | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    if (!hasValidId) return
    setLoading(true)
    setError(null)
    try {
      const [agentData, runData] = await Promise.all([
        api.getContinuousAgent(agentId),
        api.getContinuousRuns({ continuous_agent_id: agentId, limit: 100 }),
      ])
      setAgent(agentData)
      setRunsPage(runData)
      setSelectedRunId(current => current ?? runData.items[0]?.id ?? null)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load continuous agent'))
    } finally {
      setLoading(false)
    }
  }, [agentId, hasValidId])

  useEffect(() => {
    if (!hasValidId) {
      router.replace('/continuous-agents')
      return
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData()
  }, [hasValidId, loadData, router])

  const runs = useMemo(() => runsPage?.items ?? [], [runsPage])
  const selectedRun = useMemo(
    () => runs.find(run => run.id === selectedRunId) || runs[0] || null,
    [runs, selectedRunId],
  )

  if (!hasValidId) return null

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3 text-sm text-tsushin-slate">
            <Link href="/continuous-agents" className="hover:text-white">Continuous Agents</Link>
            <span>/</span>
            <span>#{agentId}</span>
          </div>
          <h1 className="text-3xl font-display font-bold text-white">
            {agent?.name || agent?.agent_name || `Continuous Agent #${agentId}`}
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">
            Read-only A2 detail for the continuous-agent row and its latest continuous runs.
          </p>
        </div>
        <button
          type="button"
          onClick={loadData}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
        >
          <RefreshIcon size={16} />
          Refresh
        </button>
      </div>

      <div className="mb-6 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4 text-sm text-cyan-100">
        Create, edit, pause, and delete actions are intentionally absent until backend write APIs exist for continuous agents.
      </div>

      {error && (
        <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center text-tsushin-slate">
          Loading continuous agent...
        </div>
      ) : !agent ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center">
          <AlertTriangleIcon size={28} className="mx-auto mb-3 text-yellow-300" />
          <div className="text-white">Continuous agent not found</div>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 md:grid-cols-4">
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
                <BotIcon size={14} /> Agent
              </div>
              <div className="mt-2 text-sm font-semibold text-white">#{agent.agent_id}</div>
              <div className="text-xs text-tsushin-slate">{agent.agent_name || 'Unnamed agent'}</div>
            </div>
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
                <ActivityIcon size={14} /> Status
              </div>
              <span className={`mt-2 inline-flex rounded-full border px-2.5 py-1 text-xs ${statusClass(agent.status)}`}>{agent.status}</span>
            </div>
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
                <ClockIcon size={14} /> Subscriptions
              </div>
              <div className="mt-2 text-2xl font-semibold text-white">{agent.subscription_count}</div>
            </div>
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
                <EyeIcon size={14} /> Mode
              </div>
              <div className="mt-2 text-sm font-semibold text-white">{agent.execution_mode}</div>
              <div className="text-xs text-tsushin-slate">{agent.is_system_owned ? 'System-owned' : 'Tenant-owned'}</div>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-white">Continuous Runs</h2>
                  <p className="text-xs text-tsushin-slate">Latest read-only runs for this continuous agent.</p>
                </div>
                <span className="text-sm text-tsushin-slate">{runsPage?.total || 0} total</span>
              </div>
              {runs.length === 0 ? (
                <div className="rounded-lg border border-dashed border-tsushin-border p-8 text-center text-sm text-tsushin-slate">
                  No continuous runs returned yet.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-tsushin-slate">
                      <tr className="border-b border-tsushin-border">
                        <th className="py-3 pr-4">Run</th>
                        <th className="py-3 pr-4">Status</th>
                        <th className="py-3 pr-4">Wake events</th>
                        <th className="py-3 pr-4">Started</th>
                        <th className="py-3">Finished</th>
                      </tr>
                    </thead>
                    <tbody>
                      {runs.map(run => (
                        <tr
                          key={run.id}
                          onClick={() => setSelectedRunId(run.id)}
                          className={`cursor-pointer border-b border-tsushin-border/60 transition-colors hover:bg-white/5 ${
                            selectedRun?.id === run.id ? 'bg-cyan-500/5' : ''
                          }`}
                        >
                          <td className="py-3 pr-4 font-mono text-cyan-200">#{run.id}</td>
                          <td className="py-3 pr-4">
                            <span className={`rounded-full border px-2 py-0.5 text-xs ${statusClass(run.status)}`}>{run.status}</span>
                          </td>
                          <td className="py-3 pr-4 text-tsushin-slate">{run.wake_event_ids.length}</td>
                          <td className="py-3 pr-4 text-tsushin-slate">{run.started_at ? formatRelative(run.started_at) : formatRelative(run.created_at)}</td>
                          <td className="py-3 text-tsushin-slate">{run.finished_at ? formatDateTime(run.finished_at) : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="text-lg font-semibold text-white">Run Detail</h2>
              {selectedRun ? (
                <div className="mt-4 space-y-4">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <div className="text-xs text-tsushin-slate">Run ID</div>
                      <div className="font-mono text-white">#{selectedRun.id}</div>
                    </div>
                    <div>
                      <div className="text-xs text-tsushin-slate">Run type</div>
                      <div className="text-white">{selectedRun.run_type}</div>
                    </div>
                    <div>
                      <div className="text-xs text-tsushin-slate">Watcher ref</div>
                      <div className="text-white">{selectedRun.watcher_run_ref || '-'}</div>
                    </div>
                    <div>
                      <div className="text-xs text-tsushin-slate">Created</div>
                      <div className="text-white">{formatDateTime(selectedRun.created_at)}</div>
                    </div>
                  </div>
                  <div>
                    <div className="mb-2 text-xs text-tsushin-slate">Wake event IDs</div>
                    <div className="flex flex-wrap gap-2">
                      {selectedRun.wake_event_ids.length > 0 ? selectedRun.wake_event_ids.map(id => (
                        <Link
                          key={id}
                          href={`/hub/wake-events?highlight=${id}`}
                          className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-xs text-cyan-200 hover:text-white"
                        >
                          #{id}
                        </Link>
                      )) : <span className="text-sm text-tsushin-slate">None</span>}
                    </div>
                  </div>
                  <div>
                    <div className="mb-2 text-xs text-tsushin-slate">Outcome state</div>
                    <JsonBlock value={selectedRun.outcome_state} />
                  </div>
                  <div>
                    <div className="mb-2 text-xs text-tsushin-slate">Threat signals</div>
                    <JsonBlock value={selectedRun.run_threat_signals} />
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-lg border border-dashed border-tsushin-border p-8 text-center text-sm text-tsushin-slate">
                  Select a run to inspect its read-only detail.
                </div>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
            <h2 className="text-lg font-semibold text-white">Policy References</h2>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div>
                <div className="text-xs text-tsushin-slate">Delivery policy</div>
                <div className="font-mono text-white">{agent.delivery_policy_id ?? '-'}</div>
              </div>
              <div>
                <div className="text-xs text-tsushin-slate">Budget policy</div>
                <div className="font-mono text-white">{agent.budget_policy_id ?? '-'}</div>
              </div>
              <div>
                <div className="text-xs text-tsushin-slate">Approval policy</div>
                <div className="font-mono text-white">{agent.approval_policy_id ?? '-'}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
