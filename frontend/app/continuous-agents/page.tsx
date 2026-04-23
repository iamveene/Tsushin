'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { api, type ContinuousAgent, type ContinuousRun, type PageResponse } from '@/lib/client'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'
import { ActivityIcon, BotIcon, ClockIcon, EyeIcon, LightningIcon, RefreshIcon } from '@/components/ui/icons'

const STATUS_OPTIONS = ['all', 'active', 'paused', 'disabled', 'error']

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

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-tsushin-border p-10 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-cyan-500/10 text-cyan-300">
        <BotIcon size={24} />
      </div>
      <h2 className="text-lg font-semibold text-white">No continuous agents yet</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm text-tsushin-slate">
        The v0.7.0 A2 backend exposes read-only continuous-agent inventory here. Create, edit, and delete flows are intentionally hidden until the write APIs land.
      </p>
    </div>
  )
}

export default function ContinuousAgentsPage() {
  const [agentsPage, setAgentsPage] = useState<PageResponse<ContinuousAgent> | null>(null)
  const [runsPage, setRunsPage] = useState<PageResponse<ContinuousRun> | null>(null)
  const [statusFilter, setStatusFilter] = useState('all')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const pageSize = 50

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [agents, runs] = await Promise.all([
        api.getContinuousAgents({
          limit: pageSize,
          offset,
          status: statusFilter === 'all' ? undefined : statusFilter,
        }),
        api.getContinuousRuns({ limit: 100 }),
      ])
      setAgentsPage(agents)
      setRunsPage(runs)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load continuous agents'))
    } finally {
      setLoading(false)
    }
  }, [offset, statusFilter])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData()
  }, [loadData])

  const runsByAgent = useMemo(() => {
    const map = new Map<number, ContinuousRun[]>()
    for (const run of runsPage?.items || []) {
      const current = map.get(run.continuous_agent_id) || []
      current.push(run)
      map.set(run.continuous_agent_id, current)
    }
    return map
  }, [runsPage])

  const agents = agentsPage?.items || []
  const total = agentsPage?.total || 0
  const canGoBack = offset > 0
  const canGoNext = offset + pageSize < total
  const activeCount = agents.filter(agent => agent.status === 'active').length
  const systemOwnedCount = agents.filter(agent => agent.is_system_owned).length

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-8 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3 text-sm text-tsushin-slate">
            <Link href="/" className="hover:text-white">Watcher</Link>
            <span>/</span>
            <span>Continuous Agents</span>
          </div>
          <h1 className="text-3xl font-display font-bold text-white">Continuous Agents</h1>
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">
            Always-on agent inventory, run history, and subscription readiness from the A2 read contracts.
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
        This screen is read-only because the current backend exposes only <code className="font-mono">GET</code> contracts for continuous agents and runs.
      </div>

      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
            <BotIcon size={14} /> Listed agents
          </div>
          <div className="mt-2 text-2xl font-semibold text-white">{total}</div>
        </div>
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
            <ActivityIcon size={14} /> Active on page
          </div>
          <div className="mt-2 text-2xl font-semibold text-white">{activeCount}</div>
        </div>
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-tsushin-slate">
            <LightningIcon size={14} /> System-owned
          </div>
          <div className="mt-2 text-2xl font-semibold text-white">{systemOwnedCount}</div>
        </div>
      </div>

      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-2">
          {STATUS_OPTIONS.map(option => (
            <button
              key={option}
              type="button"
              onClick={() => {
                setStatusFilter(option)
                setOffset(0)
              }}
              className={`rounded-lg border px-3 py-1.5 text-sm capitalize transition-colors ${
                statusFilter === option
                  ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-200'
                  : 'border-tsushin-border text-tsushin-slate hover:text-white'
              }`}
            >
              {option}
            </button>
          ))}
        </div>
        <div className="text-sm text-tsushin-slate">
          Showing {agents.length} of {total}
        </div>
      </div>

      {error && (
        <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center text-tsushin-slate">
          Loading continuous agents...
        </div>
      ) : agents.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {agents.map(agent => {
            const runs = runsByAgent.get(agent.id) || []
            const lastRun = runs[0]
            return (
              <Link
                key={agent.id}
                href={`/continuous-agents/${agent.id}`}
                className="rounded-xl border border-tsushin-border bg-tsushin-surface/70 p-5 transition-colors hover:border-cyan-500/40 hover:bg-tsushin-surface"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <h2 className="truncate text-lg font-semibold text-white">{agent.name || agent.agent_name || `Continuous Agent #${agent.id}`}</h2>
                    <p className="mt-1 text-xs text-tsushin-slate">
                      Agent #{agent.agent_id}{agent.agent_name ? ` - ${agent.agent_name}` : ''}
                    </p>
                  </div>
                  <span className={`shrink-0 rounded-full border px-2.5 py-1 text-xs ${statusClass(agent.status)}`}>
                    {agent.status}
                  </span>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  <div>
                    <div className="text-xs text-tsushin-slate">Mode</div>
                    <div className="text-sm text-white">{agent.execution_mode}</div>
                  </div>
                  <div>
                    <div className="text-xs text-tsushin-slate">Subscriptions</div>
                    <div className="text-sm text-white">{agent.subscription_count}</div>
                  </div>
                  <div>
                    <div className="text-xs text-tsushin-slate">Created</div>
                    <div className="text-sm text-white">{formatRelative(agent.created_at)}</div>
                  </div>
                </div>

                <div className="mt-4 rounded-lg border border-tsushin-border/70 bg-black/20 p-3 text-xs text-tsushin-slate">
                  {lastRun ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <ClockIcon size={14} />
                      <span>Latest run #{lastRun.id}</span>
                      <span className={`rounded-full border px-2 py-0.5 ${statusClass(lastRun.status)}`}>{lastRun.status}</span>
                      <span>{formatDateTime(lastRun.created_at)}</span>
                    </div>
                  ) : (
                    <span>No runs returned in the latest page.</span>
                  )}
                </div>

                <div className="mt-4 inline-flex items-center gap-2 text-sm text-cyan-300">
                  <EyeIcon size={15} />
                  View read-only detail
                </div>
              </Link>
            )
          })}
        </div>
      )}

      <div className="mt-6 flex items-center justify-between">
        <button
          type="button"
          disabled={!canGoBack || loading}
          onClick={() => setOffset(Math.max(0, offset - pageSize))}
          className="rounded-lg border border-tsushin-border px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-40"
        >
          Previous
        </button>
        <span className="text-sm text-tsushin-slate">Offset {offset}</span>
        <button
          type="button"
          disabled={!canGoNext || loading}
          onClick={() => setOffset(offset + pageSize)}
          className="rounded-lg border border-tsushin-border px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  )
}
