'use client'

/**
 * Communication Tab - A2A Inter-Agent Messaging Monitor
 *
 * Observability for agent-to-agent communication:
 * - Communication session logs with expandable message details
 * - Permission rules management (CRUD)
 * - Statistics overview (sessions, success rate, response time, blocked)
 */

import { useEffect, useState, useCallback } from 'react'
import { useToast } from '@/contexts/ToastContext'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import {
  api,
  Agent,
  AgentCommPermission,
  AgentCommSession,
  AgentCommMessage,
  AgentCommStats,
} from '@/lib/client'
import { formatDateTimeFull } from '@/lib/dateUtils'

type ViewKey = 'log' | 'permissions' | 'statistics'

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

  // Permissions view
  const [permissions, setPermissions] = useState<AgentCommPermission[]>([])
  const [permissionsLoading, setPermissionsLoading] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [newPermission, setNewPermission] = useState({
    source_agent_id: 0,
    target_agent_id: 0,
    max_depth: 3,
    rate_limit_rpm: 30,
  })
  const [savingPermission, setSavingPermission] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)

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
    else if (activeView === 'permissions') loadPermissions()
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
    else if (activeView === 'permissions') loadPermissions()
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

  const loadPermissions = async () => {
    setPermissionsLoading(true)
    try {
      const data = await api.getAgentCommPermissions()
      setPermissions(data)
    } catch (err: any) {
      toast.error('Load Failed', err.message || 'Failed to load permissions')
    } finally {
      setPermissionsLoading(false)
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

  const handleCreatePermission = async () => {
    if (!newPermission.source_agent_id || !newPermission.target_agent_id) {
      toast.warning('Validation', 'Please select both source and target agents')
      return
    }
    if (newPermission.source_agent_id === newPermission.target_agent_id) {
      toast.warning('Validation', 'Source and target agents must be different')
      return
    }
    setSavingPermission(true)
    try {
      await api.createAgentCommPermission(newPermission)
      toast.success('Permission created successfully')
      setShowAddModal(false)
      setNewPermission({ source_agent_id: 0, target_agent_id: 0, max_depth: 3, rate_limit_rpm: 30 })
      loadPermissions()
    } catch (err: any) {
      toast.error('Create Failed', err.message || 'Failed to create permission')
    } finally {
      setSavingPermission(false)
    }
  }

  const handleTogglePermission = async (perm: AgentCommPermission) => {
    try {
      await api.updateAgentCommPermission(perm.id, { is_enabled: !perm.is_enabled })
      toast.success(`Permission ${perm.is_enabled ? 'disabled' : 'enabled'}`)
      loadPermissions()
    } catch (err: any) {
      toast.error('Update Failed', err.message || 'Failed to update permission')
    }
  }

  const handleDeletePermission = async (id: number) => {
    if (!window.confirm('Are you sure you want to delete this permission? This action cannot be undone.')) return
    setDeletingId(id)
    try {
      await api.deleteAgentCommPermission(id)
      toast.success('Permission deleted')
      loadPermissions()
    } catch (err: any) {
      toast.error('Delete Failed', err.message || 'Failed to delete permission')
    } finally {
      setDeletingId(null)
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
    { key: 'permissions', label: 'Permissions' },
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

      {/* Permissions View */}
      {activeView === 'permissions' && (
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="p-6 border-b border-tsushin-border/50 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-display font-semibold text-white">Permission Rules</h3>
              <p className="text-sm text-tsushin-slate mt-1">Define which agents can communicate with each other</p>
            </div>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 bg-gradient-to-r from-teal-500 to-cyan-400 text-white rounded-lg text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Add Permission
            </button>
          </div>

          {permissionsLoading ? (
            <div className="p-8 text-center">
              <p className="text-tsushin-slate">Loading permissions...</p>
            </div>
          ) : permissions.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-tsushin-slate">No permission rules configured.</p>
              <p className="text-sm text-tsushin-muted mt-1">Add a permission to allow agents to communicate.</p>
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-tsushin-border/30">
                  <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Source Agent</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Target Agent</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Max Depth</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Rate Limit</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-tsushin-slate uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-tsushin-slate uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-tsushin-border/30">
                {permissions.map((perm) => (
                  <tr key={perm.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="px-6 py-4 text-sm text-white">
                      {perm.source_agent_name || `Agent #${perm.source_agent_id}`}
                    </td>
                    <td className="px-6 py-4 text-sm text-white">
                      {perm.target_agent_name || `Agent #${perm.target_agent_id}`}
                    </td>
                    <td className="px-6 py-4 text-sm text-tsushin-slate">{perm.max_depth}</td>
                    <td className="px-6 py-4 text-sm text-tsushin-slate">{perm.rate_limit_rpm} RPM</td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => handleTogglePermission(perm)}
                        className={`relative inline-flex h-5 w-10 items-center rounded-full transition-colors ${
                          perm.is_enabled ? 'bg-teal-500' : 'bg-gray-600'
                        }`}
                      >
                        <span
                          className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                            perm.is_enabled ? 'translate-x-5' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => handleDeletePermission(perm.id)}
                        disabled={deletingId === perm.id}
                        className="text-red-400 hover:text-red-300 text-sm transition-colors disabled:opacity-50"
                      >
                        {deletingId === perm.id ? 'Deleting...' : 'Delete'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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

      {/* Add Permission Modal */}
      {showAddModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowAddModal(false)}
        >
          <div
            className="bg-tsushin-elevated rounded-xl max-w-md w-full shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-tsushin-border/50">
              <h3 className="text-lg font-semibold text-white">Add Communication Permission</h3>
              <p className="text-sm text-tsushin-slate mt-1">
                Allow one agent to send messages to another
              </p>
            </div>

            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Source Agent</label>
                <select
                  value={newPermission.source_agent_id || ''}
                  onChange={(e) => setNewPermission({ ...newPermission, source_agent_id: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                >
                  <option value="">Select source agent...</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>{a.contact_name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Target Agent</label>
                <select
                  value={newPermission.target_agent_id || ''}
                  onChange={(e) => setNewPermission({ ...newPermission, target_agent_id: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                >
                  <option value="">Select target agent...</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>{a.contact_name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Max Depth</label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={newPermission.max_depth}
                  onChange={(e) => setNewPermission({ ...newPermission, max_depth: parseInt(e.target.value) || 3 })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                />
                <p className="text-xs text-tsushin-muted mt-1">Maximum chain depth for recursive agent calls (1-10)</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">Rate Limit (RPM)</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={newPermission.rate_limit_rpm}
                  onChange={(e) => setNewPermission({ ...newPermission, rate_limit_rpm: parseInt(e.target.value) || 10 })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
                />
                <p className="text-xs text-tsushin-muted mt-1">Maximum requests per minute</p>
              </div>
            </div>

            <div className="p-6 border-t border-tsushin-border/50 flex justify-end gap-3">
              <button
                onClick={() => setShowAddModal(false)}
                className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreatePermission}
                disabled={savingPermission}
                className="px-4 py-2 bg-gradient-to-r from-teal-500 to-cyan-400 text-white rounded-lg font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {savingPermission ? 'Creating...' : 'Create Permission'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
