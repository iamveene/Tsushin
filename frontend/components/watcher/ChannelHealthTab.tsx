'use client'

/**
 * Channel Health Tab - Instance & Circuit Breaker Monitoring
 * Item 38: Channel health monitoring for the Watcher module.
 *
 * Displays:
 * - Summary bar with aggregate health stats
 * - Instance cards grid with status, circuit breaker state, probe/reset actions
 * - Expandable event history per instance
 * - Alert configuration panel
 */

import { useEffect, useState, useCallback } from 'react'
import { api } from '@/lib/client'
import { formatDateTimeFull } from '@/lib/dateUtils'
import {
  ActivityIcon,
  CheckCircleIcon,
  XCircleIcon,
  AlertTriangleIcon,
  RefreshIcon,
  WifiIcon,
  ShieldIcon,
  ServerIcon,
  SettingsIcon,
  ZapIcon,
  SaveIcon,
} from '@/components/ui/icons'

// ============================================================================
// Types
// ============================================================================

interface CircuitBreaker {
  state: string
  failure_count: number
  success_count: number
  last_failure_at: string | null
  opened_at: string | null
}

interface ChannelInstance {
  channel_type: string
  instance_id: number
  instance_name: string | null
  status: string | null
  circuit_breaker: CircuitBreaker
}

interface HealthSummary {
  total_instances: number
  healthy: number
  unhealthy: number
  circuit_open: number
  circuit_closed: number
  circuit_half_open: number
  by_channel: Record<string, { total: number; healthy: number; unhealthy: number }>
}

interface HealthEvent {
  id: number
  channel_type: string
  instance_id: number
  event_type: string
  old_state: string
  new_state: string
  reason: string | null
  health_status: string | null
  latency_ms: number | null
  created_at: string
}

interface AlertConfig {
  enabled: boolean
  webhook_url: string | null
  email_recipients: string[] | null
  cooldown_seconds: number
}

// ============================================================================
// Helpers
// ============================================================================

function getChannelIcon(channelType: string): string {
  switch (channelType) {
    case 'whatsapp': return '\u{1F4F1}'
    case 'telegram': return '\u2708\uFE0F'
    case 'slack': return '\u{1F4AC}'
    case 'discord': return '\u{1F3AE}'
    default: return '\u{1F310}'
  }
}

function getChannelLabel(channelType: string): string {
  switch (channelType) {
    case 'whatsapp': return 'WhatsApp'
    case 'telegram': return 'Telegram'
    case 'slack': return 'Slack'
    case 'discord': return 'Discord'
    default: return channelType
  }
}

function getStatusColor(status: string | null): string {
  switch (status) {
    case 'healthy': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50'
    case 'unhealthy': return 'bg-red-500/20 text-red-400 border-red-500/50'
    case 'degraded': return 'bg-amber-500/20 text-amber-400 border-amber-500/50'
    default: return 'bg-gray-500/20 text-gray-400 border-gray-500/50'
  }
}

function getCircuitColor(state: string): string {
  switch (state.toLowerCase()) {
    case 'closed': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50'
    case 'open': return 'bg-red-500/20 text-red-400 border-red-500/50'
    case 'half_open': return 'bg-amber-500/20 text-amber-400 border-amber-500/50'
    default: return 'bg-gray-500/20 text-gray-400 border-gray-500/50'
  }
}

function getCircuitLabel(state: string): string {
  switch (state.toLowerCase()) {
    case 'closed': return 'CLOSED'
    case 'open': return 'OPEN'
    case 'half_open': return 'HALF OPEN'
    default: return state.toUpperCase()
  }
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const now = new Date()
  const d = new Date(dateStr.endsWith('Z') ? dateStr : dateStr + 'Z')
  const seconds = Math.floor((now.getTime() - d.getTime()) / 1000)
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

// ============================================================================
// Component
// ============================================================================

export default function ChannelHealthTab() {
  const [summary, setSummary] = useState<HealthSummary | null>(null)
  const [instances, setInstances] = useState<ChannelInstance[]>([])
  const [alertConfig, setAlertConfig] = useState<AlertConfig>({ enabled: false, webhook_url: null, email_recipients: null, cooldown_seconds: 300 })
  const [expandedInstance, setExpandedInstance] = useState<string | null>(null)
  const [eventHistory, setEventHistory] = useState<Record<string, HealthEvent[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [probingInstance, setProbingInstance] = useState<string | null>(null)
  const [resettingInstance, setResettingInstance] = useState<string | null>(null)
  const [alertsExpanded, setAlertsExpanded] = useState(false)
  const [alertSaving, setAlertSaving] = useState(false)
  const [alertDraft, setAlertDraft] = useState<AlertConfig | null>(null)

  const instanceKey = (inst: ChannelInstance) => `${inst.channel_type}:${inst.instance_id}`

  // ---- Data fetching ----

  const loadData = useCallback(async () => {
    try {
      const [healthData, summaryData, alertData] = await Promise.all([
        api.getChannelHealth(),
        api.getChannelHealthSummary(),
        api.getAlertConfig(),
      ])
      setInstances(healthData.instances || [])
      setSummary(summaryData)
      setAlertConfig({
        enabled: alertData.enabled ?? false,
        webhook_url: alertData.webhook_url ?? null,
        email_recipients: alertData.email_recipients ?? null,
        cooldown_seconds: alertData.cooldown_seconds ?? 300,
      })
      setError(null)
    } catch (err: any) {
      console.error('Failed to load channel health data:', err)
      setError(err.message || 'Failed to load channel health')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000)
    const handleRefresh = () => loadData()
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => {
      clearInterval(interval)
      window.removeEventListener('tsushin:refresh', handleRefresh)
    }
  }, [loadData])

  // ---- Toggle event history ----

  const toggleHistory = useCallback(async (inst: ChannelInstance) => {
    const key = instanceKey(inst)
    if (expandedInstance === key) {
      setExpandedInstance(null)
      return
    }
    setExpandedInstance(key)
    if (!eventHistory[key]) {
      try {
        const data = await api.getChannelHealthHistory(inst.channel_type, String(inst.instance_id), 20, 0)
        setEventHistory(prev => ({ ...prev, [key]: data.events || [] }))
      } catch (err) {
        console.error('Failed to load event history:', err)
        setEventHistory(prev => ({ ...prev, [key]: [] }))
      }
    }
  }, [expandedInstance, eventHistory])

  // ---- Probe ----

  const handleProbe = useCallback(async (inst: ChannelInstance) => {
    const key = instanceKey(inst)
    setProbingInstance(key)
    try {
      await api.probeChannelHealth(inst.channel_type, String(inst.instance_id))
      await loadData()
    } catch (err: any) {
      console.error('Probe failed:', err)
    } finally {
      setProbingInstance(null)
    }
  }, [loadData])

  // ---- Reset circuit breaker ----

  const handleReset = useCallback(async (inst: ChannelInstance) => {
    const key = instanceKey(inst)
    setResettingInstance(key)
    try {
      await api.resetCircuitBreaker(inst.channel_type, String(inst.instance_id))
      await loadData()
    } catch (err: any) {
      console.error('Reset failed:', err)
    } finally {
      setResettingInstance(null)
    }
  }, [loadData])

  // ---- Alert config save ----

  const handleSaveAlerts = useCallback(async () => {
    if (!alertDraft) return
    setAlertSaving(true)
    try {
      const result = await api.updateAlertConfig({
        enabled: alertDraft.enabled,
        webhook_url: alertDraft.webhook_url || null,
        email_recipients: alertDraft.email_recipients,
        cooldown_seconds: alertDraft.cooldown_seconds,
      })
      setAlertConfig({
        enabled: result.enabled ?? false,
        webhook_url: result.webhook_url ?? null,
        email_recipients: result.email_recipients ?? null,
        cooldown_seconds: result.cooldown_seconds ?? 300,
      })
      setAlertDraft(null)
    } catch (err: any) {
      console.error('Failed to save alert config:', err)
    } finally {
      setAlertSaving(false)
    }
  }, [alertDraft])

  // ---- Loading state ----

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="relative w-12 h-12 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading channel health...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
          <p className="text-red-200">{error}</p>
          <button onClick={loadData} className="mt-2 text-sm text-red-400 hover:text-red-300 underline">
            Retry
          </button>
        </div>
      </div>
    )
  }

  const currentAlertDraft = alertDraft || alertConfig

  return (
    <div className="space-y-8 animate-fade-in">

      {/* ================================================================ */}
      {/* Summary Bar */}
      {/* ================================================================ */}
      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-stagger">
          {/* Total Instances */}
          <div className="stat-card stat-card-indigo group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Total Instances</p>
                <p className="text-3xl font-display font-bold text-white mt-1">{summary.total_instances}</p>
                <p className="text-xs text-tsushin-muted mt-1">
                  {Object.keys(summary.by_channel).map(ch =>
                    `${getChannelLabel(ch)}: ${summary.by_channel[ch].total}`
                  ).join(', ') || 'No channels'}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-indigo-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <ServerIcon size={24} className="text-indigo-400" />
              </div>
            </div>
          </div>

          {/* Healthy */}
          <div className="stat-card stat-card-success group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Healthy</p>
                <p className="text-3xl font-display font-bold text-emerald-400 mt-1">{summary.healthy}</p>
                <p className="text-xs text-tsushin-muted mt-1">Circuit closed</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <CheckCircleIcon size={24} className="text-emerald-400" />
              </div>
            </div>
          </div>

          {/* Unhealthy */}
          <div className="stat-card stat-card-error group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Unhealthy</p>
                <p className="text-3xl font-display font-bold text-red-400 mt-1">{summary.unhealthy}</p>
                <p className="text-xs text-tsushin-muted mt-1">Needs attention</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-red-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <XCircleIcon size={24} className="text-red-400" />
              </div>
            </div>
          </div>

          {/* Open Circuits */}
          <div className="stat-card stat-card-warning group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Open Circuits</p>
                <p className="text-3xl font-display font-bold text-amber-400 mt-1">{summary.circuit_open}</p>
                <p className="text-xs text-tsushin-muted mt-1">
                  {summary.circuit_half_open > 0 ? `${summary.circuit_half_open} recovering` : 'Circuit breakers tripped'}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-amber-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <ZapIcon size={24} className="text-amber-400" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ================================================================ */}
      {/* Instance Cards Grid */}
      {/* ================================================================ */}
      {instances.length === 0 ? (
        <div className="glass-card rounded-xl p-12 text-center">
          <WifiIcon size={48} className="text-tsushin-slate mx-auto mb-4" />
          <h3 className="text-xl font-medium text-white mb-2">No Channel Instances</h3>
          <p className="text-tsushin-slate max-w-md mx-auto">
            No channel instances are configured for this tenant. Set up a WhatsApp, Telegram, Slack, or Discord integration to start monitoring.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {instances.map((inst) => {
            const key = instanceKey(inst)
            const isExpanded = expandedInstance === key
            const isProbing = probingInstance === key
            const isResetting = resettingInstance === key
            const cbState = inst.circuit_breaker.state.toLowerCase()
            const events = eventHistory[key] || []

            return (
              <div key={key} className="glass-card rounded-xl overflow-hidden">
                {/* Card Header */}
                <div className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">{getChannelIcon(inst.channel_type)}</span>
                      <div>
                        <h4 className="text-sm font-display font-semibold text-white">
                          {inst.instance_name || `Instance #${inst.instance_id}`}
                        </h4>
                        <p className="text-xs text-tsushin-muted">{getChannelLabel(inst.channel_type)}</p>
                      </div>
                    </div>
                    {/* Status Badge */}
                    <span className={`px-2.5 py-0.5 text-xs font-medium rounded-full border ${getStatusColor(inst.status)}`}>
                      {(inst.status || 'unknown').toUpperCase()}
                    </span>
                  </div>

                  {/* Circuit Breaker State */}
                  <div className="flex items-center gap-2 mb-3">
                    <span className="text-xs text-tsushin-slate">Circuit:</span>
                    <span className={`px-2 py-0.5 text-xs font-medium rounded-full border ${getCircuitColor(cbState)}`}>
                      {getCircuitLabel(cbState)}
                    </span>
                    {inst.circuit_breaker.failure_count > 0 && (
                      <span className="text-xs text-red-400">
                        {inst.circuit_breaker.failure_count} failures
                      </span>
                    )}
                    {inst.circuit_breaker.success_count > 0 && cbState === 'half_open' && (
                      <span className="text-xs text-emerald-400">
                        {inst.circuit_breaker.success_count} successes
                      </span>
                    )}
                  </div>

                  {/* Last failure / opened at */}
                  {inst.circuit_breaker.last_failure_at && (
                    <p className="text-xs text-tsushin-muted mb-1">
                      Last failure: {timeAgo(inst.circuit_breaker.last_failure_at)}
                    </p>
                  )}
                  {inst.circuit_breaker.opened_at && cbState !== 'closed' && (
                    <p className="text-xs text-tsushin-muted mb-3">
                      Opened: {timeAgo(inst.circuit_breaker.opened_at)}
                    </p>
                  )}

                  {/* Action Buttons */}
                  <div className="flex items-center gap-2 mt-3">
                    <button
                      onClick={() => handleProbe(inst)}
                      disabled={isProbing}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-tsushin-surface border border-tsushin-border/50 text-tsushin-slate hover:text-white hover:border-tsushin-indigo/50 transition-all disabled:opacity-50"
                    >
                      <RefreshIcon size={12} className={isProbing ? 'animate-spin' : ''} />
                      {isProbing ? 'Probing...' : 'Probe'}
                    </button>
                    {cbState === 'open' && (
                      <button
                        onClick={() => handleReset(inst)}
                        disabled={isResetting}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20 transition-all disabled:opacity-50"
                      >
                        <ShieldIcon size={12} />
                        {isResetting ? 'Resetting...' : 'Reset Circuit'}
                      </button>
                    )}
                    <button
                      onClick={() => toggleHistory(inst)}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-tsushin-surface border border-tsushin-border/50 text-tsushin-slate hover:text-white hover:border-tsushin-indigo/50 transition-all ml-auto"
                    >
                      <ActivityIcon size={12} />
                      {isExpanded ? 'Hide History' : 'History'}
                    </button>
                  </div>
                </div>

                {/* Expandable Event History */}
                {isExpanded && (
                  <div className="border-t border-tsushin-surface bg-[#0d0d1a]/40">
                    <div className="p-4">
                      <h5 className="text-xs font-display font-semibold text-tsushin-slate mb-3">Event History</h5>
                      {events.length === 0 ? (
                        <p className="text-xs text-tsushin-muted py-2">No events recorded yet.</p>
                      ) : (
                        <div className="space-y-2 max-h-64 overflow-y-auto">
                          {events.map((evt) => (
                            <div key={evt.id} className="flex items-start gap-3 text-xs">
                              {/* Timeline dot */}
                              <div className="mt-1.5 flex-shrink-0">
                                <div className={`w-2 h-2 rounded-full ${
                                  evt.new_state === 'open' ? 'bg-red-400' :
                                  evt.new_state === 'closed' ? 'bg-emerald-400' :
                                  evt.new_state === 'half_open' ? 'bg-amber-400' : 'bg-gray-400'
                                }`} />
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-white font-medium">{evt.event_type}</span>
                                  <span className="text-tsushin-muted">
                                    {evt.old_state} &rarr; {evt.new_state}
                                  </span>
                                  {evt.latency_ms != null && (
                                    <span className="text-tsushin-muted">{Math.round(evt.latency_ms)}ms</span>
                                  )}
                                </div>
                                {evt.reason && (
                                  <p className="text-tsushin-muted truncate mt-0.5">{evt.reason}</p>
                                )}
                                <p className="text-tsushin-muted mt-0.5">{formatDateTimeFull(evt.created_at)}</p>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ================================================================ */}
      {/* Alert Configuration Panel */}
      {/* ================================================================ */}
      <div className="glass-card rounded-xl overflow-hidden">
        <button
          onClick={() => {
            setAlertsExpanded(!alertsExpanded)
            if (!alertsExpanded && !alertDraft) {
              setAlertDraft({ ...alertConfig })
            }
          }}
          className="w-full p-4 flex items-center justify-between hover:bg-white/[0.02] transition-colors"
        >
          <div className="flex items-center gap-2">
            <SettingsIcon size={18} className="text-tsushin-indigo" />
            <h3 className="text-sm font-display font-semibold text-white">Alert Configuration</h3>
            <span className={`px-2 py-0.5 text-xs rounded-full border ${
              alertConfig.enabled
                ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50'
                : 'bg-gray-500/20 text-gray-400 border-gray-500/50'
            }`}>
              {alertConfig.enabled ? 'ENABLED' : 'DISABLED'}
            </span>
          </div>
          <svg
            className={`w-5 h-5 text-tsushin-slate transition-transform ${alertsExpanded ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {alertsExpanded && (
          <div className="border-t border-tsushin-surface p-5 space-y-4">
            {/* Enable / Disable */}
            <div className="flex items-center gap-3">
              <label className="text-sm text-tsushin-slate">Alerts Enabled</label>
              <button
                onClick={() => setAlertDraft(prev => prev ? { ...prev, enabled: !prev.enabled } : null)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  currentAlertDraft.enabled ? 'bg-emerald-500' : 'bg-gray-600'
                }`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  currentAlertDraft.enabled ? 'translate-x-6' : 'translate-x-1'
                }`} />
              </button>
            </div>

            {/* Webhook URL */}
            <div>
              <label className="block text-sm text-tsushin-slate mb-1">Webhook URL</label>
              <input
                type="url"
                value={currentAlertDraft.webhook_url || ''}
                onChange={(e) => setAlertDraft(prev => prev ? { ...prev, webhook_url: e.target.value || null } : null)}
                placeholder="https://hooks.slack.com/services/..."
                className="w-full px-3 py-2 border border-gray-700 rounded-lg text-sm text-white bg-gray-800 placeholder-gray-500 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
              />
            </div>

            {/* Email Recipients */}
            <div>
              <label className="block text-sm text-tsushin-slate mb-1">Email Recipients (comma-separated)</label>
              <input
                type="text"
                value={(currentAlertDraft.email_recipients || []).join(', ')}
                onChange={(e) => {
                  const emails = e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                  setAlertDraft(prev => prev ? { ...prev, email_recipients: emails.length > 0 ? emails : null } : null)
                }}
                placeholder="admin@example.com, ops@example.com"
                className="w-full px-3 py-2 border border-gray-700 rounded-lg text-sm text-white bg-gray-800 placeholder-gray-500 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
              />
            </div>

            {/* Cooldown Seconds */}
            <div>
              <label className="block text-sm text-tsushin-slate mb-1">Cooldown (seconds)</label>
              <input
                type="number"
                min={60}
                max={3600}
                value={currentAlertDraft.cooldown_seconds}
                onChange={(e) => setAlertDraft(prev => prev ? { ...prev, cooldown_seconds: parseInt(e.target.value) || 300 } : null)}
                className="w-32 px-3 py-2 border border-gray-700 rounded-lg text-sm text-white bg-gray-800 focus:ring-2 focus:ring-tsushin-indigo focus:border-transparent"
              />
              <p className="text-xs text-tsushin-muted mt-1">Minimum time between repeated alerts for the same instance.</p>
            </div>

            {/* Save Button */}
            <div className="pt-2">
              <button
                onClick={handleSaveAlerts}
                disabled={alertSaving || !alertDraft}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-tsushin-indigo text-white hover:bg-tsushin-indigo/80 transition-all disabled:opacity-50"
              >
                <SaveIcon size={14} />
                {alertSaving ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
