/**
 * Billing Tab - Watcher Module
 * Displays token consumption, costs, and billing analytics
 */

"use client"

import { useEffect, useState } from "react"

interface TokenStats {
  total_tokens: number
  total_cost: number
  total_requests: number
  operation_breakdown: Array<{
    operation: string
    tokens: number
    cost: number
    count: number
  }>
  model_breakdown: Array<{
    model: string
    tokens: number
    cost: number
    count: number
  }>
  daily_trend: Array<{
    date: string
    tokens: number
    cost: number
    count: number
  }>
}

interface AgentSummary {
  agent_id: number
  agent_name: string
  total_tokens: number
  total_cost: number
  total_requests: number
}

export default function BillingTab() {
  const [stats, setStats] = useState<TokenStats | null>(null)
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAnalytics()
  }, [days])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      console.log('[BillingTab] Refresh event received')
      loadAnalytics()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)

    // Cleanup on unmount
    return () => {
      window.removeEventListener('tsushin:refresh', handleRefresh)
    }
  }, [days]) // Re-subscribe when days changes to capture current value

  const loadAnalytics = async () => {
    setLoading(true)
    try {
      console.log('[BillingTab] Loading analytics data...')
      const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const authHeaders = {
        'Authorization': `Bearer ${localStorage.getItem('tsushin_auth_token')}`
      }
      const [statsRes, agentsRes] = await Promise.all([
        fetch(`${API_URL}/api/analytics/token-usage/summary?days=${days}`, { headers: authHeaders }).then(r => r.json()),
        fetch(`${API_URL}/api/analytics/token-usage/by-agent?days=${days}`, { headers: authHeaders }).then(r => r.json())
      ])
      console.log('[BillingTab] Stats response:', statsRes)
      console.log('[BillingTab] Agents response:', agentsRes)
      // Ensure stats has all required properties with default values
      const normalizedStats: TokenStats = {
        total_tokens: statsRes.total_tokens ?? 0,
        total_cost: statsRes.total_cost ?? 0,
        total_requests: statsRes.total_requests ?? 0,
        operation_breakdown: statsRes.operation_breakdown ?? [],
        model_breakdown: statsRes.model_breakdown ?? [],
        daily_trend: statsRes.daily_trend ?? []
      }
      setStats(normalizedStats)
      setAgents(agentsRes.agents || [])
    } catch (error) {
      console.error("[BillingTab] Failed to load analytics:", error)
      // Set empty data so UI doesn't show "loading" forever
      setStats({
        total_tokens: 0,
        total_cost: 0,
        total_requests: 0,
        operation_breakdown: [],
        model_breakdown: [],
        daily_trend: []
      })
    } finally {
      setLoading(false)
    }
  }

  const formatCost = (cost: number | undefined | null) => {
    if (cost === undefined || cost === null) {
      return "$0.00"
    }
    if (cost === 0) {
      return "$0.00 (FREE)"
    }
    return `$${cost.toFixed(4)}`
  }

  const formatTokens = (tokens: number | undefined | null) => {
    if (tokens === undefined || tokens === null) {
      return "0"
    }
    return tokens.toLocaleString()
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white mb-1">Billing & Usage</h2>
          <p className="text-sm text-gray-400">Track AI usage, costs, and optimize spending</p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="px-4 py-2 border dark:border-gray-700 rounded-md bg-gray-800 text-gray-100"
        >
          <option value={7}>Last 7 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {loading ? (
        <div className="text-center py-12">
          <div className="text-gray-500 dark:text-gray-400">Loading analytics...</div>
        </div>
      ) : stats ? (
        <div className="space-y-6">
          {/* Summary Cards */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg border dark:border-gray-700">
              <div className="text-sm text-gray-500 dark:text-gray-400">Total Tokens</div>
              <div className="text-3xl font-bold text-gray-900 dark:text-white">
                {formatTokens(stats.total_tokens)}
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg border dark:border-gray-700">
              <div className="text-sm text-gray-500 dark:text-gray-400">Total Cost</div>
              <div className="text-3xl font-bold text-gray-900 dark:text-white">
                {formatCost(stats.total_cost)}
              </div>
            </div>
            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg border dark:border-gray-700">
              <div className="text-sm text-gray-500 dark:text-gray-400">Requests</div>
              <div className="text-3xl font-bold text-gray-900 dark:text-white">
                {(stats.total_requests ?? 0).toLocaleString()}
              </div>
            </div>
          </div>

          {/* Agent Summary */}
          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg border dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Usage by Agent
            </h2>
            {agents.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b dark:border-gray-700">
                      <th className="text-left p-2 text-gray-900 dark:text-gray-100">Agent</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Tokens</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Cost</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Requests</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agents.map((agent) => (
                      <tr key={agent.agent_id} className="border-b dark:border-gray-700">
                        <td className="p-2 text-gray-900 dark:text-gray-100">
                          {agent.agent_name}
                          {agent.total_cost === 0 && agent.total_tokens > 0 && (
                            <span className="ml-2 px-2 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                              FREE
                            </span>
                          )}
                        </td>
                        <td className="p-2 text-right text-gray-900 dark:text-gray-100">
                          {formatTokens(agent.total_tokens)}
                        </td>
                        <td className={`p-2 text-right ${agent.total_cost === 0 ? 'text-green-600 dark:text-green-400 font-semibold' : 'text-gray-900 dark:text-gray-100'}`}>
                          {formatCost(agent.total_cost)}
                        </td>
                        <td className="p-2 text-right text-gray-900 dark:text-gray-100">
                          {agent.total_requests}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">
                No agent usage data yet. Usage will appear here once agents process requests.
              </p>
            )}
          </div>

          {/* Model Breakdown */}
          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg border dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Usage by Model
            </h2>
            {stats.model_breakdown.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b dark:border-gray-700">
                      <th className="text-left p-2 text-gray-900 dark:text-gray-100">Model</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Tokens</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Cost</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Requests</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.model_breakdown.map((model, idx) => (
                      <tr key={idx} className="border-b dark:border-gray-700">
                        <td className="p-2 text-gray-900 dark:text-gray-100">
                          {model.model}
                          {model.cost === 0 && model.tokens > 0 && (
                            <span className="ml-2 px-2 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                              FREE
                            </span>
                          )}
                        </td>
                        <td className="p-2 text-right text-gray-900 dark:text-gray-100">
                          {formatTokens(model.tokens)}
                        </td>
                        <td className={`p-2 text-right ${model.cost === 0 ? 'text-green-600 dark:text-green-400 font-semibold' : 'text-gray-900 dark:text-gray-100'}`}>
                          {formatCost(model.cost)}
                        </td>
                        <td className="p-2 text-right text-gray-900 dark:text-gray-100">
                          {model.count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">
                No model usage data yet. Usage will appear here once AI models are called.
              </p>
            )}
          </div>

          {/* Operation Breakdown */}
          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg border dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Usage by Operation
            </h2>
            {stats.operation_breakdown.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b dark:border-gray-700">
                      <th className="text-left p-2 text-gray-900 dark:text-gray-100">Operation</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Tokens</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Cost</th>
                      <th className="text-right p-2 text-gray-900 dark:text-gray-100">Requests</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stats.operation_breakdown.map((op, idx) => (
                      <tr key={idx} className="border-b dark:border-gray-700">
                        <td className="p-2 text-gray-900 dark:text-gray-100">
                          {op.operation}
                          {op.cost === 0 && op.tokens > 0 && (
                            <span className="ml-2 px-2 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                              FREE
                            </span>
                          )}
                        </td>
                        <td className="p-2 text-right text-gray-900 dark:text-gray-100">
                          {formatTokens(op.tokens)}
                        </td>
                        <td className={`p-2 text-right ${op.cost === 0 ? 'text-green-600 dark:text-green-400 font-semibold' : 'text-gray-900 dark:text-gray-100'}`}>
                          {formatCost(op.cost)}
                        </td>
                        <td className="p-2 text-right text-gray-900 dark:text-gray-100">
                          {op.count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">
                No operation usage data yet. Usage will appear here once operations are performed.
              </p>
            )}
          </div>
        </div>
      ) : (
        <div className="text-center py-12">
          <div className="text-gray-500 dark:text-gray-400">No analytics data available</div>
        </div>
      )}
    </div>
  )
}
