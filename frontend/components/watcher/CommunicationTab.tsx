'use client'

/**
 * Communication Tab - A2A Inter-Agent Messaging Monitor (observability only)
 *
 * Read-only views for agent-to-agent communication:
 * - Communication session logs with expandable message details
 * - Statistics overview (sessions, success rate, response time, blocked)
 *
 * Permission-rule CRUD is configuration, not observability — it lives in
 * Studio → A2A Communications (`/agents/communication`).
 */

import { useEffect, useState, useCallback } from 'react'
import { useToast } from '@/contexts/ToastContext'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import {
  api,
  Agent,
  AgentCommSession,
  AgentCommMessage,
  AgentCommStats,
} from '@/lib/client'
import { formatDateTimeFull } from '@/lib/dateUtils'

type ViewKey = 'log' | 'statistics'

export default function CommunicationTab() {
  const toast = useToast()
  const [activeView, setActiveView] = useState<ViewKey>('log')

  // Shared data
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)

  // Communication Log view
  const [sessions, setSessions] = useState<AgentCommSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [expandedSessionId, setExpandedSessionId] = useState<number | null>(null)
  const [sessionMessages, setSessionMessages] = useState<AgentCommMessage[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)

  // Statistics view
  const [stats, setStats] = useState<AgentCommStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(false)

  // Load all data
  const loadData = useCallback(async () => {
    try {
      const agentsData = await api.getAgents()
      setAgents(agentsData)
    } catch (err: any) {
      console.error('Failed to load agents:', err)
    } finally {
      setLoading(false)
    }
    // Reload active view data
    if (activeView === 'log') loadSessions()
    else if (activeView === 'statistics') loadStats()
  }, [activeView, statusFilter])

  // Mount + polling
  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 5000)
    return () => clearInterval(interval)
  }, [])

  // Reload when view or filter changes
  useEffect(() => {
    if (loading) return
    if (activeView === 'log') loadSessions()
    else if (activeView === 'statistics') loadStats()
  }, [activeView, statusFilter])

  useGlobalRefresh(() => loadData())

  const loadSessions = async () => {
    setSessionsLoading(true)
    try {
      const params: { limit: number; status?: string } = { limit: 50 }
      if (statusFilter) params.status = statusFilter
      const result = await api.getAgentCommSessions(params)
      setSessions(result.items)
    } catch (err: any) {
      toast.error('Load Failed', err.message || 'Failed to load sessions')
    } finally {
      setSessionsLoading(false)
    }
  }

  const loadStats = async () => {
    setStatsLoading(true)
    try {
      const data = await api.getAgentCommStats()
      setStats(data)
    } catch (err: any) {
      toast.error('Load Failed', err.message || 'Failed to load stats')
    } finally {
      setStatsLoading(false)
    }
  }

  const handleExpandSession = async (sessionId: number) => {
    if (expandedSessionId === sessionId) {
      setExpandedSessionId(null)
      setSessionMessages([])
      return
    }
    setExpandedSessionId(sessionId)
    setMessagesLoading(true)
    try {
      const detail = await api.getAgentCommSessionDetail(sessionId)
      setSessionMessages(detail.messages || [])
    } catch (err: any) {
      toast.error('Load Failed', err.message || 'Failed to load session detail')
    } finally {
      setMessagesLoading(false)
    }
  }

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      completed: 'bg-green-500/20 text-green-400 border-green-500/30',
      in_progress: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
      blocked: 'bg-red-500/20 text-red-400 border-red-500/30',
      timeout: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
      failed: 'bg-red-500/20 text-red-400 border-red-500/30',
      pending: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
    }
    return (
      <span className={`text-xs px-2 py-0.5 rounded-full border ${styles[status] || styles.pending}`}>
        {status}
      </span>
    )
  }

  const views: { key: ViewKey; label: string }[] = [
    { key: 'log', label: 'Communication Log' },
    { key: 'statistics', label: 'Statistics' },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="relative w-12 h-12 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* View Toggle */}
      <div className="glass-card rounded-xl overflow-hidden">
        <div className="border-b border-tsushin-border/50">
          <nav className="flex">
            {views.map((view) => (
              <button
                key={view.key}
                onClick={() => setActiveView(view.key)}
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  activeView === view.key ? 'text-white' : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10">{view.label}</span>
                {activeView === view.key && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-amber-500 to-orange-400" />
                )}
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Pointer to the new config home (Studio → A2A Communications). */}
      <div className="glass-card rounded-xl px-5 py-3 text-sm text-tsushin-slate flex items-center gap-2">
        <svg className="w-4 h-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>
          Permission rules moved — configure which agents can communicate in{' '}
          <a href="/agents/communication" className="text-teal-400 hover:text-teal-300 underline">
            Studio → A2A Communications
          </a>
          .
        </span>
      </div>

      {/* Communication Log View */}
      {activeView === 'log' && (
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="p-6 border-b border-tsushin-border/50 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-display font-semibold text-white">Communication Sessions</h3>
              <p className="text-sm text-tsushin-slate mt-1">Monitor inter-agent messaging activity</p>
            </div>
            <div className="flex items-center gap-3">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-1.5 bg-tsushin-surface border border-tsushin-border rounded-lg text-sm text-white focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
              >
                <option value="">All Statuses</option>
                <option value="completed">Completed</option>
                <option value="in_progress">In Progress</option>
                <option value="blocked">Blocked</option>
                <option value="failed">Failed</option>
                <option value="timeout">Timeout</option>
              </select>
              <button
                onClick={loadSessions}
                className="px-3 py-1.5 bg-tsushin-surface hover:bg-tsushin-elevated border border-tsushin-border rounded-lg text-sm text-white transition-colors"
              >
                Refresh
              </button>
            </div>
          </div>

          {sessionsLoading ? (
            <div className="p-8 text-center">
              <p className="text-tsushin-slate">Loading sessions...</p>
            </div>
          ) : sessions.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-tsushin-slate">No communication sessions found.</p>
            </div>
          ) : (
            <div className="divide-y divide-tsushin-border/30">
              {sessions.map((session) => (
                <div key={session.id}>
                  <div
                    className="p-4 hover:bg-gray-800/30 transition-colors cursor-pointer"
                    onClick={() => handleExpandSession(session.id)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <svg
                          className={`w-4 h-4 text-tsushin-slate transition-transform ${
                            expandedSessionId === session.id ? 'rotate-90' : ''
                          }`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-white font-medium text-sm">
                              {session.initiator_agent_name || `Agent #${session.initiator_agent_id}`}
                            </span>
                            <svg className="w-4 h-4 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 8l4 4m0 0l-4 4m4-4H3" />
                            </svg>
                            <span className="text-white font-medium text-sm">
                              {session.target_agent_name || `Agent #${session.target_agent_id}`}
                            </span>
                          </div>
                          <p className="text-xs text-tsushin-muted mt-0.5">
                            {formatDateTimeFull(session.started_at)}
                            {session.original_message_preview && (
                              <span className="ml-2 text-tsushin-slate">
                                &mdash; {session.original_message_preview}
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-tsushin-muted">
                          Depth {session.depth}/{session.max_depth}
                        </span>
                        <span className="text-xs text-tsushin-muted">
                          {session.total_messages} msg{session.total_messages !== 1 ? 's' : ''}
                        </span>
                        {getStatusBadge(session.status)}
                      </div>
                    </div>
                  </div>

                  {/* Expanded message list */}
                  {expandedSessionId === session.id && (
                    <div className="bg-tsushin-surface/50 border-t border-tsushin-border/20 px-6 py-4">
                      {messagesLoading ? (
                        <p className="text-tsushin-slate text-sm">Loading messages...</p>
                      ) : sessionMessages.length === 0 ? (
                        <p className="text-tsushin-slate text-sm">No messages in this session.</p>
                      ) : (
                        <div className="space-y-3">
                          {sessionMessages.map((msg) => (
                            <div
                              key={msg.id}
                              className="bg-tsushin-dark-card rounded-lg p-3 border border-tsushin-border/20"
                            >
                              <div className="flex items-center justify-between mb-1">
                                <div className="flex items-center gap-2">
                                  <span className={`text-xs font-medium ${
                                    msg.direction === 'request' ? 'text-amber-400' : 'text-teal-400'
                                  }`}>
                                    {msg.direction === 'request' ? 'REQUEST' : 'RESPONSE'}
                                  </span>
                                  <span className="text-xs text-tsushin-slate">
                                    {msg.from_agent_name || `Agent #${msg.from_agent_id}`}
                                    {' -> '}
                                    {msg.to_agent_name || `Agent #${msg.to_agent_id}`}
                                  </span>
                                </div>
                                <div className="flex items-center gap-2">
                                  {msg.execution_time_ms !== undefined && (
                                    <span className="text-xs text-tsushin-muted">
                                      {msg.execution_time_ms}ms
                                    </span>
                                  )}
                                  {msg.model_used && (
                                    <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700/50 text-tsushin-slate">
                                      {msg.model_used}
                                    </span>
                                  )}
                                  {msg.sentinel_analyzed && (
                                    <span className="text-xs px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/20">
                                      Scanned
                                    </span>
                                  )}
                                </div>
                              </div>
                              <p className="text-sm text-gray-300 whitespace-pre-wrap break-words">
                                {msg.message_content ?? ''}
                              </p>
                              <p className="text-xs text-tsushin-muted mt-1">
                                {formatDateTimeFull(msg.created_at)}
                              </p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Statistics View */}
      {activeView === 'statistics' && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="stat-card stat-card-indigo group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Total Sessions</p>
                <p className="text-3xl font-display font-bold text-white mt-1">
                  {statsLoading ? '...' : (stats?.total_sessions ?? 0)}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-amber-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-success group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Success Rate</p>
                <p className="text-3xl font-display font-bold text-green-400 mt-1">
                  {statsLoading ? '...' : `${(stats?.success_rate ?? 0).toFixed(1)}%`}
                </p>
                <p className="text-xs text-tsushin-muted mt-1">
                  {stats?.completed_sessions ?? 0} completed
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-green-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-warning group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Avg Response Time</p>
                <p className="text-3xl font-display font-bold text-orange-400 mt-1">
                  {statsLoading ? '...' : `${(stats?.avg_response_time_ms ?? 0).toFixed(0)}ms`}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-orange-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-accent group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Blocked</p>
                <p className="text-3xl font-display font-bold text-red-400 mt-1">
                  {statsLoading ? '...' : (stats?.blocked_sessions ?? 0)}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
