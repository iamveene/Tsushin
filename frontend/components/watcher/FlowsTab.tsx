'use client'

/**
 * Flows Tab - Flow Execution Monitoring
 *
 * Observability for flow executions:
 * - Unified flow runs (conversations, notifications, multi-step workflows)
 * - Performance metrics and status tracking
 * - Execution logs and traces
 * - Active conversation threads
 */

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { api, type FlowRun, type ConversationThread } from '@/lib/client'
import { parseUTCTimestamp } from '@/lib/dateUtils'
import { LightningIcon, MessageIcon } from '@/components/ui/icons'

export default function FlowsTab() {
  const router = useRouter()
  const [flowRuns, setFlowRuns] = useState<FlowRun[]>([])
  const [conversationThreads, setConversationThreads] = useState<ConversationThread[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [activeTab, setActiveTab] = useState<'runs' | 'threads'>('runs')

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 5000) // Poll every 5s

    // Listen for global refresh events
    const handleRefresh = () => {
      console.log('[FlowsTab] Refresh event received')
      loadData()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)

    return () => {
      clearInterval(interval)
      window.removeEventListener('tsushin:refresh', handleRefresh)
    }
  }, [])

  const loadData = async () => {
    try {
      const [runsData, threadsData] = await Promise.all([
        api.getFlowRuns(undefined, 50),
        api.getActiveConversationThreads().catch(() => [])
      ])
      setFlowRuns(runsData)
      setConversationThreads(threadsData)
    } catch (err) {
      console.error('Failed to load flow data:', err)
    } finally {
      setLoading(false)
    }
  }

  function getStatusColor(status: string) {
    const statusLower = status.toLowerCase()
    switch (statusLower) {
      case 'pending':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
      case 'active':
      case 'running':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30'
      case 'completed':
        return 'bg-green-500/20 text-green-400 border-green-500/30'
      case 'failed':
        return 'bg-red-500/20 text-red-400 border-red-500/30'
      case 'cancelled':
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30'
      case 'paused':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30'
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30'
    }
  }

  function formatDate(dateString: string) {
    return parseUTCTimestamp(dateString).toLocaleString('pt-BR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  async function handleCancelRun(runId: number) {
    if (!confirm('Cancel this flow run?')) return
    try {
      await api.cancelFlowRun(runId)
      await loadData()
    } catch (error) {
      console.error('Failed to cancel run:', error)
      alert('Failed to cancel run')
    }
  }

  function calculateDuration(startedAt: string, completedAt: string | null): string {
    if (!completedAt) return 'In progress...'
    const durationMs = new Date(completedAt).getTime() - new Date(startedAt).getTime()
    const seconds = Math.round(durationMs / 1000)
    if (seconds < 60) return `${seconds}s`
    const minutes = Math.floor(seconds / 60)
    const remainingSeconds = seconds % 60
    return `${minutes}m ${remainingSeconds}s`
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-lg text-gray-400">Loading flow data...</div>
      </div>
    )
  }

  const filteredFlowRuns = statusFilter
    ? flowRuns.filter(r => r.status.toLowerCase() === statusFilter.toLowerCase())
    : flowRuns

  // Stats calculation
  const stats = {
    totalRuns: flowRuns.length,
    running: flowRuns.filter(r => r.status === 'running').length,
    completed: flowRuns.filter(r => r.status === 'completed').length,
    failed: flowRuns.filter(r => r.status === 'failed').length,
    activeThreads: conversationThreads.filter(t => t.status === 'active').length,
    successRate: flowRuns.length > 0
      ? Math.round((flowRuns.filter(r => r.status === 'completed').length / flowRuns.length) * 100)
      : 0
  }

  return (
    <div className="space-y-6">
      {/* Tab Switcher and Actions */}
      <div className="flex justify-between items-center">
        <div className="inline-flex rounded-lg bg-gray-800 p-1 border border-gray-700">
          <button
            onClick={() => setActiveTab('runs')}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
              activeTab === 'runs'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span className="inline-flex items-center gap-1"><LightningIcon size={14} /> Flow Runs</span>
          </button>
          <button
            onClick={() => setActiveTab('threads')}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
              activeTab === 'threads'
                ? 'bg-cyan-600 text-white shadow-sm'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <span className="inline-flex items-center gap-1"><MessageIcon size={14} /> Active Conversations</span>
            {conversationThreads.length > 0 && (
              <span className="ml-2 px-1.5 py-0.5 text-xs bg-green-500/20 text-green-400 rounded-full">
                {conversationThreads.length}
              </span>
            )}
          </button>
        </div>

        <div className="flex items-center gap-3">
          {activeTab === 'runs' && (
            <>
              <label className="text-sm text-gray-400">Filter:</label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800
                           focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
              >
                <option value="">All Statuses</option>
                <option value="pending">Pending</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </>
          )}
          <button
            onClick={() => router.push('/flows')}
            className="px-3 py-1.5 text-sm text-cyan-400 hover:text-white transition-colors"
          >
            Manage Flows →
          </button>
        </div>
      </div>

      {/* Flow Runs View */}
      {activeTab === 'runs' && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-800 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-white inline-flex items-center gap-2"><LightningIcon size={18} /> Flow Executions</h2>
            <span className="text-sm text-gray-400">{filteredFlowRuns.length} runs</span>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-800">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Run ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Flow</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Steps</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Started</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Duration</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {filteredFlowRuns.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                      {statusFilter ? `No ${statusFilter} runs found` : 'No flow runs yet'}
                    </td>
                  </tr>
                ) : (
                  filteredFlowRuns.map((run) => (
                    <tr key={run.id} className="hover:bg-gray-800/50 transition-colors">
                      <td className="px-4 py-3 text-sm font-medium text-white">#{run.id}</td>
                      <td className="px-4 py-3 text-sm text-gray-300">
                        Flow #{run.flow_definition_id}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium border ${getStatusColor(run.status)}`}>
                          {run.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {run.completed_steps !== undefined && run.total_steps !== undefined
                          ? `${run.completed_steps}/${run.total_steps}`
                          : '-'}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {formatDate(run.started_at)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {calculateDuration(run.started_at, run.completed_at)}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => router.push('/flows')}
                            className="text-cyan-400 hover:text-white hover:underline transition-colors"
                          >
                            View
                          </button>
                          {(run.status === 'pending' || run.status === 'running') && (
                            <button
                              onClick={() => handleCancelRun(run.id)}
                              className="text-red-400 hover:text-white hover:underline transition-colors"
                              title="Cancel run"
                            >
                              Cancel
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Active Conversation Threads View */}
      {activeTab === 'threads' && (
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-800 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
              Active Conversations
            </h2>
            <span className="text-sm text-gray-400">{conversationThreads.length} active</span>
          </div>

          {conversationThreads.length === 0 ? (
            <div className="px-6 py-12 text-center text-gray-400">
              <MessageIcon size={40} className="mx-auto mb-4 text-gray-500" />
              <p>No active conversations at the moment</p>
              <p className="text-sm text-gray-500 mt-2">
                Conversations will appear here when flows with multi-turn steps are running
              </p>
            </div>
          ) : (
            <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {conversationThreads.map((thread) => (
                <div key={thread.id} className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="font-medium text-white">{thread.recipient}</div>
                      {thread.agent_id && (
                        <div className="text-xs text-gray-400">Agent #{thread.agent_id}</div>
                      )}
                    </div>
                    <span className={`px-2 py-0.5 text-xs rounded-full border ${getStatusColor(thread.status)}`}>
                      {thread.status}
                    </span>
                  </div>

                  {thread.objective && (
                    <p className="text-sm text-gray-300 mb-3 line-clamp-2">{thread.objective}</p>
                  )}

                  <div className="flex items-center justify-between text-xs text-gray-400">
                    <span>Turn {thread.current_turn}/{thread.max_turns}</span>
                    <span>{formatDate(thread.last_activity_at)}</span>
                  </div>

                  {/* Progress bar */}
                  <div className="mt-3 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 transition-all"
                      style={{ width: `${(thread.current_turn / thread.max_turns) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-gradient-to-br from-cyan-500/20 to-cyan-500/5 border border-cyan-500/30 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Total Runs</h3>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">{stats.totalRuns}</span>
          </div>
          <div className="mt-2 text-xs text-gray-400">
            {stats.running} running • {stats.completed} completed • {stats.failed} failed
          </div>
        </div>

        <div className="bg-gradient-to-br from-green-500/20 to-green-500/5 border border-green-500/30 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Active Conversations</h3>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-green-400">{stats.activeThreads}</span>
            <span className="text-sm text-gray-400">threads</span>
          </div>
          <div className="mt-2 text-xs text-gray-400">
            Multi-turn conversations in progress
          </div>
        </div>

        <div className="bg-gradient-to-br from-blue-500/20 to-blue-500/5 border border-blue-500/30 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Running Now</h3>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-blue-400">{stats.running}</span>
            <span className="text-sm text-gray-400">flows</span>
          </div>
          <div className="mt-2 text-xs text-gray-400">
            Currently executing
          </div>
        </div>

        <div className="bg-gradient-to-br from-purple-500/20 to-purple-500/5 border border-purple-500/30 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Success Rate</h3>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-purple-400">{stats.successRate}%</span>
          </div>
          <div className="mt-2 text-xs text-gray-400">
            Flow completion rate
          </div>
        </div>
      </div>
    </div>
  )
}
