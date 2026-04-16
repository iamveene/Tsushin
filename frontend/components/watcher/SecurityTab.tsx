'use client'

/**
 * Security Tab - Sentinel Security Events Dashboard
 * Phase 20: Centralized security monitoring for the Watcher
 *
 * Displays:
 * - Real-time security event feed
 * - Filter by event type, severity, agent, time range
 * - Statistics dashboard
 * - Event details modal
 */

import { useEffect, useState, useCallback } from 'react'
import { api, SentinelLog, SentinelStats } from '@/lib/client'
import { formatDateTimeFull } from '@/lib/dateUtils'
import { SearchIcon, AlertTriangleIcon, ShieldIcon, CheckCircleIcon, ChartBarIcon, LockIcon, UnlockIcon, EyeIcon, BrainIcon, TerminalIcon, SyringeIcon, BotIcon } from '@/components/ui/icons'

interface Agent {
  id: number
  name: string
}

export default function SecurityTab() {
  const [logs, setLogs] = useState<SentinelLog[]>([])
  const [stats, setStats] = useState<SentinelStats | null>(null)
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [threatOnly, setThreatOnly] = useState(true)
  const [detectionType, setDetectionType] = useState<string>('')
  const [agentId, setAgentId] = useState<number | undefined>(undefined)
  const [actionFilter, setActionFilter] = useState<string>('') // 'blocked', 'detected', ''
  const [limit, setLimit] = useState(50)

  // Selected log for details modal
  const [selectedLog, setSelectedLog] = useState<SentinelLog | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [logsData, statsData, agentsData] = await Promise.all([
        api.getSentinelLogs({
          limit,
          threat_only: threatOnly,
          detection_type: detectionType || undefined,
          agent_id: agentId,
        }),
        api.getSentinelStats(7),
        api.getAgents(),
      ])

      setLogs(logsData)
      setStats(statsData)
      setAgents(agentsData.map((a: any) => ({ id: a.id, name: a.contact_name || `Agent ${a.id}` })))
    } catch (err: any) {
      console.error('Failed to load security data:', err)
      setError(err.message || 'Failed to load security events')
    } finally {
      setLoading(false)
    }
  }, [limit, threatOnly, detectionType, agentId])

  useEffect(() => {
    loadData()

    // Polling every 5 seconds for real-time updates
    const interval = setInterval(loadData, 5000)

    // Listen for global refresh events
    const handleRefresh = () => {
      console.log('[SecurityTab] Refresh event received')
      loadData()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)

    return () => {
      clearInterval(interval)
      window.removeEventListener('tsushin:refresh', handleRefresh)
    }
  }, [loadData])

  const getSeverityColor = (detectionType: string) => {
    switch (detectionType) {
      case 'shell_malicious':
        return 'bg-red-500/20 text-red-400 border-red-500/50'
      case 'memory_poisoning':
      case 'prompt_injection':
      case 'agent_takeover':
        return 'bg-orange-500/20 text-orange-400 border-orange-500/50'
      case 'poisoning':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50'
      default:
        return 'bg-gray-500/20 text-gray-400 border-gray-500/50'
    }
  }

  const getThreatTypeIcon = (type: string) => {
    switch (type) {
      case 'shell_malicious':
        return <TerminalIcon size={14} />
      case 'memory_poisoning':
        return <BrainIcon size={14} />
      case 'prompt_injection':
        return <SyringeIcon size={14} />
      case 'agent_takeover':
        return <BotIcon size={14} />
      case 'poisoning':
        return <AlertTriangleIcon size={14} />
      default:
        return <ShieldIcon size={14} />
    }
  }

  const getThreatTypeLabel = (type: string): string => {
    switch (type) {
      case 'shell_malicious':
        return 'Shell'
      case 'memory_poisoning':
        return 'MemGuard'
      case 'prompt_injection':
        return 'Injection'
      case 'agent_takeover':
        return 'Takeover'
      case 'poisoning':
        return 'Poisoning'
      default:
        return type.replace('_', ' ')
    }
  }

  // EDR-style action badges
  const getActionBadge = (log: SentinelLog) => {
    const action = log.action_taken
    const isThreat = log.is_threat_detected
    const detectionMode = log.detection_mode_used
    const exceptionApplied = log.exception_applied

    // Exception was applied - show as bypassed
    if (exceptionApplied) {
      return {
        label: 'BYPASSED',
        className: 'bg-blue-600 text-white border-blue-400',
        icon: <UnlockIcon size={12} />
      }
    }

    // Blocked - red badge (EDR style)
    if (action === 'blocked') {
      return {
        label: 'BLOCKED',
        className: 'bg-red-600 text-white border-red-400 font-bold',
        icon: <ShieldIcon size={12} />
      }
    }

    // Detected but allowed (detect_only mode) - orange badge
    if (isThreat && action === 'allowed') {
      return {
        label: 'DETECTED',
        className: 'bg-orange-500 text-white border-orange-400 font-bold',
        icon: <EyeIcon size={12} />
      }
    }

    // Warned
    if (action === 'warned') {
      return {
        label: 'WARNED',
        className: 'bg-yellow-600 text-black border-yellow-400',
        icon: <AlertTriangleIcon size={12} />
      }
    }

    // Allowed (no threat)
    if (action === 'allowed') {
      return {
        label: 'ALLOWED',
        className: 'bg-green-600 text-white border-green-400',
        icon: <CheckCircleIcon size={12} />
      }
    }

    return {
      label: action?.toUpperCase() || 'UNKNOWN',
      className: 'bg-gray-600 text-white border-gray-400',
      icon: <span>?</span>
    }
  }

  // Legacy function for backwards compatibility
  const getActionColor = (action: string) => {
    switch (action) {
      case 'blocked':
        return 'bg-red-600 text-white'
      case 'warned':
        return 'bg-yellow-600 text-white'
      case 'allowed':
        return 'bg-green-600 text-white'
      default:
        return 'bg-gray-600 text-white'
    }
  }

  const formatDate = (dateStr: string) => formatDateTimeFull(dateStr)

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="relative w-12 h-12 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading security events...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <p className="text-red-800 dark:text-red-200">{error}</p>
          <button
            onClick={loadData}
            className="mt-2 text-sm text-red-600 hover:text-red-500 underline"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Stats Overview */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-stagger">
          <div className="stat-card stat-card-indigo group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Total Analyses</p>
                <p className="text-3xl font-display font-bold text-white mt-1">{stats.total_analyses.toLocaleString()}</p>
                <p className="text-xs text-tsushin-muted mt-1">Last 7 days</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-teal-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <SearchIcon size={24} className="text-teal-400" />
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-warning group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Threats Detected</p>
                <p className="text-3xl font-display font-bold text-orange-400 mt-1">{stats.threats_detected}</p>
                <p className="text-xs text-tsushin-muted mt-1">{stats.detection_rate}% detection rate</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-orange-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <AlertTriangleIcon size={24} className="text-orange-400" />
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-error group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Blocked</p>
                <p className="text-3xl font-display font-bold text-red-400 mt-1">{stats.threats_blocked}</p>
                <p className="text-xs text-tsushin-muted mt-1">Messages blocked</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <ShieldIcon size={24} className="text-red-400" />
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-success group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Protection Rate</p>
                <p className="text-3xl font-display font-bold text-green-400 mt-1">
                  {stats.threats_detected > 0
                    ? Math.round((stats.threats_blocked / stats.threats_detected) * 100)
                    : 100}%
                </p>
                <p className="text-xs text-tsushin-muted mt-1">Threats mitigated</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-green-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <CheckCircleIcon size={24} className="text-green-400" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Detection Type Breakdown */}
      {stats && Object.keys(stats.by_detection_type).length > 0 && (
        <div className="glass-card rounded-xl px-6 py-4">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="text-sm font-display font-semibold text-tsushin-slate flex items-center gap-1.5 mr-1">
              <ChartBarIcon size={16} className="text-tsushin-indigo" /> Threats by Type
            </h3>
            {Object.entries(stats.by_detection_type).map(([type, count]) => (
              <div
                key={type}
                className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 ${
                  type === 'memory_poisoning'
                    ? 'bg-purple-500/20 text-purple-400 border-purple-500/50'
                    : getSeverityColor(type)
                }`}
              >
                {getThreatTypeIcon(type)}
                <span className="text-xs font-medium">{getThreatTypeLabel(type)}</span>
                <span className="text-sm font-bold">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="glass-card rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <label className="text-sm text-tsushin-slate">Show:</label>
            <select
              value={threatOnly ? 'threats' : 'all'}
              onChange={(e) => setThreatOnly(e.target.value === 'threats')}
              className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
            >
              <option value="threats">Threats Only</option>
              <option value="all">All Events</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-sm text-tsushin-slate">Type:</label>
            <select
              value={detectionType}
              onChange={(e) => setDetectionType(e.target.value)}
              className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
            >
              <option value="">All Types</option>
              <option value="prompt_injection">Prompt Injection</option>
              <option value="agent_takeover">Agent Takeover</option>
              <option value="poisoning">Poisoning</option>
              <option value="shell_malicious">Shell Malicious</option>
              <option value="memory_poisoning">Memory Poisoning</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-sm text-tsushin-slate">Agent:</label>
            <select
              value={agentId || ''}
              onChange={(e) => setAgentId(e.target.value ? parseInt(e.target.value) : undefined)}
              className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
            >
              <option value="">All Agents</option>
              {agents.map((agent) => (
                <option key={agent.id} value={agent.id}>{agent.name}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-sm text-tsushin-slate">Action:</label>
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
            >
              <option value="">All Actions</option>
              <option value="blocked">Blocked Only</option>
              <option value="detected">Detected Only</option>
              <option value="bypassed">Bypassed (Exception)</option>
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-sm text-tsushin-slate">Limit:</label>
            <select
              value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value))}
              className="px-3 py-1.5 border border-gray-700 rounded-md text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>
        </div>
      </div>

      {/* Events List */}
      {(() => {
        // Apply action filter to logs
        const filteredLogs = logs.filter(log => {
          if (!actionFilter) return true
          if (actionFilter === 'blocked') return log.action_taken === 'blocked'
          if (actionFilter === 'detected') return log.is_threat_detected && log.action_taken === 'allowed' && !log.exception_applied
          if (actionFilter === 'bypassed') return log.exception_applied
          return true
        })

        return (
      <div className="glass-card rounded-xl overflow-hidden">
        <div className="p-4 border-b border-tsushin-surface">
          <h3 className="text-lg font-display font-semibold text-white flex items-center gap-2">
            <LockIcon size={20} className="text-tsushin-indigo" /> Security Events
            <span className="text-sm font-normal text-tsushin-slate">({filteredLogs.length} events)</span>
          </h3>
        </div>

        {filteredLogs.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-tsushin-slate">
              {threatOnly ? 'No threats detected. Your system is secure!' : 'No security events to display.'}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-tsushin-surface">
            {filteredLogs.map((log) => (
              <div
                key={log.id}
                onClick={() => setSelectedLog(log)}
                className="p-4 hover:bg-gray-800/50 cursor-pointer transition-colors"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      {/* Detection Type Badge */}
                      <span className={`px-2 py-0.5 text-xs rounded-full border ${getSeverityColor(log.detection_type)}`}>
                        {log.detection_type.replace('_', ' ')}
                      </span>
                      {/* EDR-style Action Badge */}
                      {(() => {
                        const badge = getActionBadge(log)
                        return (
                          <span className={`px-2 py-0.5 text-xs rounded-full border ${badge.className} flex items-center gap-1`}>
                            <span>{badge.icon}</span>
                            <span>{badge.label}</span>
                          </span>
                        )
                      })()}
                      {/* MemGuard Badge */}
                      {log.detection_type === 'memory_poisoning' && (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 flex items-center gap-1">
                          <BrainIcon size={10} />
                          <span>MemGuard</span>
                        </span>
                      )}
                      {/* Detection Mode indicator */}
                      {log.detection_mode_used && log.detection_mode_used !== 'block' && (
                        <span className="px-2 py-0.5 text-xs rounded-full bg-purple-600/30 text-purple-300 border border-purple-500/50">
                          {log.detection_mode_used}
                        </span>
                      )}
                      <span className="text-xs text-tsushin-slate">
                        {log.analysis_type}
                      </span>
                    </div>
                    <p className="text-sm text-white truncate">{log.input_content}</p>
                    {log.threat_reason && (
                      <p className="text-xs text-orange-400 mt-1 truncate">
                        {log.threat_reason}
                      </p>
                    )}
                    <div className="flex items-center gap-4 mt-2 text-xs text-tsushin-muted">
                      {log.sender_key && <span>Sender: {log.sender_key}</span>}
                      {log.agent_id && (
                        <span>Agent: {agents.find(a => a.id === log.agent_id)?.name || log.agent_id}</span>
                      )}
                      {log.llm_provider && log.llm_model && (
                        <span className="text-cyan-400">Model: {log.llm_provider}/{log.llm_model}</span>
                      )}
                      {log.llm_response_time_ms && <span>{log.llm_response_time_ms}ms</span>}
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-xs text-tsushin-slate">{formatDate(log.created_at)}</p>
                    {log.threat_score && (
                      <p className="text-sm font-medium text-orange-400 mt-1">
                        {Math.round(log.threat_score * 100)}% confidence
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
        )
      })()}

      {/* Event Details Modal */}
      {selectedLog && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="bg-tsushin-elevated rounded-xl max-w-2xl w-full max-h-[90vh] overflow-auto shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-tsushin-surface flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Security Event Details</h3>
              <button
                onClick={() => setSelectedLog(null)}
                className="text-tsushin-slate hover:text-white"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 space-y-4">
              {/* EDR-style badges */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`px-3 py-1 text-sm rounded-full border ${getSeverityColor(selectedLog.detection_type)}`}>
                  {selectedLog.detection_type.replace('_', ' ')}
                </span>
                {(() => {
                  const badge = getActionBadge(selectedLog)
                  return (
                    <span className={`px-3 py-1 text-sm rounded-full border ${badge.className} flex items-center gap-1`}>
                      <span>{badge.icon}</span>
                      <span>{badge.label}</span>
                    </span>
                  )
                })()}
                {selectedLog.detection_type === 'memory_poisoning' && (
                  <span className="px-3 py-1 text-sm rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 flex items-center gap-1">
                    <BrainIcon size={12} />
                    <span>MemGuard</span>
                  </span>
                )}
                {selectedLog.detection_mode_used && (
                  <span className="px-3 py-1 text-sm rounded-full bg-purple-600/30 text-purple-300 border border-purple-500/50">
                    Mode: {selectedLog.detection_mode_used}
                  </span>
                )}
                {selectedLog.exception_applied && (
                  <span className="px-3 py-1 text-sm rounded-full bg-blue-600/30 text-blue-300 border border-blue-500/50">
                    Exception: {selectedLog.exception_name || `#${selectedLog.exception_id}`}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-tsushin-slate">Analysis Type</p>
                  <p className="text-white">{selectedLog.analysis_type}</p>
                </div>
                <div>
                  <p className="text-tsushin-slate">Timestamp</p>
                  <p className="text-white">{formatDate(selectedLog.created_at)}</p>
                </div>
                {selectedLog.threat_score && (
                  <div>
                    <p className="text-tsushin-slate">Confidence Score</p>
                    <p className="text-orange-400 font-medium">{Math.round(selectedLog.threat_score * 100)}%</p>
                  </div>
                )}
                {selectedLog.sender_key && (
                  <div>
                    <p className="text-tsushin-slate">Sender</p>
                    <p className="text-white">{selectedLog.sender_key}</p>
                  </div>
                )}
                {selectedLog.agent_id && (
                  <div>
                    <p className="text-tsushin-slate">Agent</p>
                    <p className="text-white">{agents.find(a => a.id === selectedLog.agent_id)?.name || selectedLog.agent_id}</p>
                  </div>
                )}
                {selectedLog.llm_provider && (
                  <div>
                    <p className="text-tsushin-slate">LLM Provider</p>
                    <p className="text-white">{selectedLog.llm_provider} / {selectedLog.llm_model}</p>
                  </div>
                )}
                {selectedLog.llm_response_time_ms && (
                  <div>
                    <p className="text-tsushin-slate">Response Time</p>
                    <p className="text-white">{selectedLog.llm_response_time_ms}ms</p>
                  </div>
                )}
              </div>

              {selectedLog.threat_reason && (
                <div>
                  <p className="text-tsushin-slate text-sm mb-1">Threat Reason</p>
                  <p className="text-orange-400 bg-orange-500/10 border border-orange-500/30 rounded-lg p-3">
                    {selectedLog.threat_reason}
                  </p>
                </div>
              )}

              <div>
                <p className="text-tsushin-slate text-sm mb-1">Input Content</p>
                <pre className="text-white bg-tsushin-surface rounded-lg p-3 text-sm overflow-x-auto whitespace-pre-wrap">
                  {selectedLog.input_content}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
