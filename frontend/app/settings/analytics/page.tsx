'use client'

/**
 * Analytics Dashboard — v0.7.0
 * Tenant-scoped token-usage and cost overview backed by /api/analytics/token-usage/*.
 */

import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useAuth } from '@/contexts/AuthContext'
import {
  api,
  type AgentTokenUsageDetail,
  type AgentUsageSummary,
  type RecentTokenUsageRecord,
  type TokenUsageSummary,
} from '@/lib/client'

const DAYS_OPTIONS: Array<{ label: string; value: number }> = [
  { label: 'Last 7 days', value: 7 },
  { label: 'Last 30 days', value: 30 },
  { label: 'Last 90 days', value: 90 },
  { label: 'Last 365 days', value: 365 },
]

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'operation', label: 'By Operation' },
  { id: 'model', label: 'By Model' },
  { id: 'agent', label: 'By Agent' },
  { id: 'recent', label: 'Recent' },
] as const

type TabId = (typeof TABS)[number]['id']

function formatNumber(value: number | undefined | null): string {
  if (value == null) return '—'
  return new Intl.NumberFormat().format(Math.round(value))
}

function formatCost(value: number | undefined | null): string {
  if (value == null) return '—'
  if (value === 0) return '$0.00'
  if (value >= 1) return `$${value.toFixed(2)}`
  return `$${value.toFixed(5)}`
}

function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

export default function AnalyticsPage() {
  const { hasPermission } = useAuth()
  const canRead = hasPermission('analytics.read')

  const [days, setDays] = useState(30)
  const [activeTab, setActiveTab] = useState<TabId>('overview')

  const [summary, setSummary] = useState<TokenUsageSummary | null>(null)
  const [byAgent, setByAgent] = useState<AgentUsageSummary[]>([])
  const [recent, setRecent] = useState<RecentTokenUsageRecord[]>([])
  const [agentDetail, setAgentDetail] = useState<AgentTokenUsageDetail | null>(null)
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)

  const [loading, setLoading] = useState(true)
  const [agentDetailLoading, setAgentDetailLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadAll = useCallback(async () => {
    if (!canRead) return
    setLoading(true)
    setError(null)
    try {
      const [summaryData, agentsData, recentData] = await Promise.all([
        api.getTokenUsageSummary(days),
        api.getTokenUsageByAgent(days),
        api.getRecentTokenUsage(100),
      ])
      setSummary(summaryData)
      setByAgent(agentsData.agents)
      setRecent(recentData.records)
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to load analytics'))
    } finally {
      setLoading(false)
    }
  }, [days, canRead])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const loadAgentDetail = useCallback(
    async (agentId: number) => {
      setAgentDetailLoading(true)
      try {
        const detail = await api.getTokenUsageForAgent(agentId, days)
        setAgentDetail(detail)
      } catch (err: unknown) {
        setError(getErrorMessage(err, 'Failed to load agent detail'))
      } finally {
        setAgentDetailLoading(false)
      }
    },
    [days],
  )

  useEffect(() => {
    if (selectedAgentId !== null) {
      loadAgentDetail(selectedAgentId)
    }
  }, [selectedAgentId, loadAgentDetail])

  const trendData = useMemo(() => {
    return (summary?.daily_trend || []).map((item) => ({
      date: item.date,
      tokens: item.tokens,
      cost: Number(item.cost.toFixed(5)),
    }))
  }, [summary])

  if (!canRead) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-sm text-red-200">
          You do not have permission to view analytics.
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-6 flex items-center gap-3 text-sm text-tsushin-slate">
        <Link href="/settings" className="hover:text-white">
          Settings
        </Link>
        <span>/</span>
        <span>Analytics</span>
      </div>

      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-3xl font-display font-bold text-white">Analytics</h1>
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">
            Token consumption, estimated cost, and per-agent usage trends across this tenant.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {DAYS_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setDays(option.value)}
              className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                days === option.value
                  ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-200'
                  : 'border-tsushin-border text-tsushin-slate hover:text-white'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="mb-6 grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="text-xs uppercase tracking-wide text-tsushin-slate">Total tokens</div>
          <div className="mt-2 text-2xl font-semibold text-white">{formatNumber(summary?.total_tokens)}</div>
        </div>
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="text-xs uppercase tracking-wide text-tsushin-slate">Estimated cost</div>
          <div className="mt-2 text-2xl font-semibold text-white">{formatCost(summary?.total_cost)}</div>
        </div>
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4">
          <div className="text-xs uppercase tracking-wide text-tsushin-slate">Total requests</div>
          <div className="mt-2 text-2xl font-semibold text-white">{formatNumber(summary?.total_requests)}</div>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
              activeTab === tab.id
                ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-200'
                : 'border-tsushin-border text-tsushin-slate hover:text-white'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center text-tsushin-slate">
          Loading analytics…
        </div>
      ) : (
        <>
          {activeTab === 'overview' && (
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="mb-4 text-lg font-semibold text-white">Daily trend</h2>
              {trendData.length === 0 ? (
                <div className="rounded-lg border border-dashed border-tsushin-border p-8 text-center text-sm text-tsushin-slate">
                  No usage in the selected window.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={trendData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
                    <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} />
                    <YAxis yAxisId="tokens" stroke="#22d3ee" fontSize={11} />
                    <YAxis yAxisId="cost" orientation="right" stroke="#a78bfa" fontSize={11} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1f2937' }} />
                    <Legend />
                    <Area
                      yAxisId="tokens"
                      type="monotone"
                      dataKey="tokens"
                      stroke="#22d3ee"
                      fill="#22d3ee33"
                      name="Tokens"
                    />
                    <Area
                      yAxisId="cost"
                      type="monotone"
                      dataKey="cost"
                      stroke="#a78bfa"
                      fill="#a78bfa33"
                      name="Cost ($)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </div>
          )}

          {activeTab === 'operation' && summary && (
            <BreakdownPanel
              title="By operation"
              data={summary.operation_breakdown.map((row) => ({
                label: row.operation,
                tokens: row.tokens,
                cost: row.cost,
                count: row.count,
              }))}
            />
          )}

          {activeTab === 'model' && summary && (
            <BreakdownPanel
              title="By model"
              data={summary.model_breakdown.map((row) => ({
                label: row.model,
                tokens: row.tokens,
                cost: row.cost,
                count: row.count,
              }))}
            />
          )}

          {activeTab === 'agent' && (
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="mb-4 text-lg font-semibold text-white">By agent</h2>
              {byAgent.length === 0 ? (
                <div className="rounded-lg border border-dashed border-tsushin-border p-8 text-center text-sm text-tsushin-slate">
                  No agent usage in the selected window.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs uppercase text-tsushin-slate">
                        <th className="px-3 py-2">Agent</th>
                        <th className="px-3 py-2 text-right">Requests</th>
                        <th className="px-3 py-2 text-right">Tokens</th>
                        <th className="px-3 py-2 text-right">Cost</th>
                        <th className="px-3 py-2"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {byAgent.map((row) => {
                        const isSelected = selectedAgentId === row.agent_id
                        return (
                          <Fragment key={row.agent_id}>
                            <tr className="text-tsushin-fog">
                              <td className="px-3 py-2">
                                <div className="font-medium text-white">{row.agent_name}</div>
                                <div className="text-xs text-tsushin-slate">#{row.agent_id}</div>
                              </td>
                              <td className="px-3 py-2 text-right">{formatNumber(row.total_requests)}</td>
                              <td className="px-3 py-2 text-right">{formatNumber(row.total_tokens)}</td>
                              <td className="px-3 py-2 text-right">{formatCost(row.total_cost)}</td>
                              <td className="px-3 py-2 text-right">
                                <button
                                  type="button"
                                  onClick={() =>
                                    setSelectedAgentId(isSelected ? null : row.agent_id)
                                  }
                                  className="rounded-md border border-tsushin-border px-2 py-1 text-xs text-tsushin-fog hover:text-white"
                                >
                                  {isSelected ? 'Hide detail' : 'Show detail'}
                                </button>
                              </td>
                            </tr>
                            {isSelected && (
                              <tr className="bg-black/20">
                                <td colSpan={5} className="px-3 py-3">
                                  {agentDetailLoading ? (
                                    <div className="text-sm text-tsushin-slate">Loading detail…</div>
                                  ) : agentDetail && agentDetail.agent_id === row.agent_id ? (
                                    <div className="grid gap-4 lg:grid-cols-2">
                                      <BreakdownMini
                                        title="Skills"
                                        data={agentDetail.skill_breakdown.map((b) => ({
                                          label: b.skill,
                                          tokens: b.tokens,
                                          cost: b.cost,
                                          count: b.count,
                                        }))}
                                      />
                                      <BreakdownMini
                                        title="Models"
                                        data={agentDetail.model_breakdown.map((b) => ({
                                          label: b.model,
                                          tokens: b.tokens,
                                          cost: b.cost,
                                          count: b.count,
                                        }))}
                                      />
                                    </div>
                                  ) : (
                                    <div className="text-sm text-tsushin-slate">No detail available.</div>
                                  )}
                                </td>
                              </tr>
                            )}
                          </Fragment>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === 'recent' && (
            <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
              <h2 className="mb-4 text-lg font-semibold text-white">Recent transactions</h2>
              {recent.length === 0 ? (
                <div className="rounded-lg border border-dashed border-tsushin-border p-8 text-center text-sm text-tsushin-slate">
                  No recent token usage.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs uppercase text-tsushin-slate">
                        <th className="px-3 py-2">Time</th>
                        <th className="px-3 py-2">Agent</th>
                        <th className="px-3 py-2">Operation</th>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2 text-right">Tokens</th>
                        <th className="px-3 py-2 text-right">Cost</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      {recent.map((row, index) => {
                        const ts = row.timestamp || row.created_at || ''
                        const model = row.model || (
                          row.model_provider && row.model_name
                            ? `${row.model_provider}/${row.model_name}`
                            : '—'
                        )
                        return (
                          <tr key={row.id ?? index} className="text-tsushin-fog">
                            <td className="px-3 py-2 text-xs">{ts || '—'}</td>
                            <td className="px-3 py-2">{row.agent_name || `#${row.agent_id ?? '—'}`}</td>
                            <td className="px-3 py-2">{row.operation_type || '—'}</td>
                            <td className="px-3 py-2 font-mono text-xs">{model}</td>
                            <td className="px-3 py-2 text-right">{formatNumber(row.total_tokens)}</td>
                            <td className="px-3 py-2 text-right">{formatCost(row.estimated_cost)}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

interface BreakdownRow {
  label: string
  tokens: number
  cost: number
  count: number
}

function BreakdownPanel({ title, data }: { title: string; data: BreakdownRow[] }) {
  if (data.length === 0) {
    return (
      <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
        <h2 className="mb-4 text-lg font-semibold text-white">{title}</h2>
        <div className="rounded-lg border border-dashed border-tsushin-border p-8 text-center text-sm text-tsushin-slate">
          No usage in the selected window.
        </div>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <h2 className="mb-4 text-lg font-semibold text-white">{title}</h2>
      <ResponsiveContainer width="100%" height={Math.max(220, data.length * 32)}>
        <BarChart data={data} layout="vertical" margin={{ top: 5, right: 20, left: 100, bottom: 5 }}>
          <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
          <XAxis type="number" stroke="#94a3b8" fontSize={11} />
          <YAxis type="category" dataKey="label" stroke="#94a3b8" fontSize={11} width={120} />
          <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #1f2937' }} />
          <Bar dataKey="tokens" fill="#22d3ee" name="Tokens" />
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-4 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-tsushin-slate">
              <th className="px-3 py-2">Label</th>
              <th className="px-3 py-2 text-right">Tokens</th>
              <th className="px-3 py-2 text-right">Cost</th>
              <th className="px-3 py-2 text-right">Count</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data.map((row) => (
              <tr key={row.label} className="text-tsushin-fog">
                <td className="px-3 py-2">{row.label}</td>
                <td className="px-3 py-2 text-right">{formatNumber(row.tokens)}</td>
                <td className="px-3 py-2 text-right">{formatCost(row.cost)}</td>
                <td className="px-3 py-2 text-right">{formatNumber(row.count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BreakdownMini({ title, data }: { title: string; data: BreakdownRow[] }) {
  return (
    <div className="rounded-lg border border-tsushin-border/70 bg-black/20 p-3">
      <div className="mb-2 text-xs uppercase tracking-wide text-tsushin-slate">{title}</div>
      {data.length === 0 ? (
        <div className="text-sm text-tsushin-slate">No data.</div>
      ) : (
        <table className="min-w-full text-xs">
          <tbody>
            {data.map((row) => (
              <tr key={row.label} className="text-tsushin-fog">
                <td className="py-1 pr-3">{row.label}</td>
                <td className="py-1 px-3 text-right">{formatNumber(row.tokens)}</td>
                <td className="py-1 pl-3 text-right">{formatCost(row.cost)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
