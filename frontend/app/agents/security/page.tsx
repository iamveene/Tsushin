'use client'

/**
 * Studio Security Page - Phase 20
 *
 * Agent-level Sentinel Security configuration:
 * - Global Sentinel status overview
 * - Per-agent security overrides
 * - Recent security events
 */

import { useEffect, useState, useCallback } from 'react'
import { useRequireAuth } from '@/contexts/AuthContext'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { api, Agent, SentinelConfig, SentinelAgentConfig, SentinelAgentConfigUpdate, SentinelLog, SentinelStats } from '@/lib/client'
import { formatDateTimeFull } from '@/lib/dateUtils'

interface AgentWithSecurity extends Agent {
  sentinelConfig?: SentinelAgentConfig | null
}

export default function SecurityPage() {
  const pathname = usePathname()
  const { user, loading: authLoading, hasPermission } = useRequireAuth()
  const canEdit = hasPermission('org.settings.write')

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Data state
  const [sentinelConfig, setSentinelConfig] = useState<SentinelConfig | null>(null)
  const [agents, setAgents] = useState<AgentWithSecurity[]>([])
  const [stats, setStats] = useState<SentinelStats | null>(null)
  const [recentLogs, setRecentLogs] = useState<SentinelLog[]>([])

  // Modal state
  const [selectedAgent, setSelectedAgent] = useState<AgentWithSecurity | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [saving, setSaving] = useState(false)

  // Form state for agent override
  const [useCustomSettings, setUseCustomSettings] = useState(false)
  const [formData, setFormData] = useState<SentinelAgentConfigUpdate>({
    is_enabled: null,
    enable_prompt_analysis: null,
    enable_tool_analysis: null,
    enable_shell_analysis: null,
    aggressiveness_level: null,
  })

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [configData, agentsData, statsData, logsData] = await Promise.all([
        api.getSentinelConfig(),
        api.getAgents(),
        api.getSentinelStats(7),
        api.getSentinelLogs({ limit: 10, threat_only: true }),
      ])

      setSentinelConfig(configData)
      setStats(statsData)
      setRecentLogs(logsData)

      // Load sentinel config for each agent
      const agentsWithSecurity: AgentWithSecurity[] = await Promise.all(
        agentsData.map(async (agent: Agent) => {
          try {
            const sentinelConfig = await api.getSentinelAgentConfig(agent.id)
            return { ...agent, sentinelConfig }
          } catch {
            return { ...agent, sentinelConfig: null }
          }
        })
      )
      setAgents(agentsWithSecurity)
    } catch (err: any) {
      console.error('Failed to load security data:', err)
      setError(err.message || 'Failed to load security data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!authLoading && user) {
      loadData()
    }
  }, [loadData, authLoading, user])

  const openAgentModal = (agent: AgentWithSecurity) => {
    setSelectedAgent(agent)
    if (agent.sentinelConfig) {
      setUseCustomSettings(true)
      setFormData({
        is_enabled: agent.sentinelConfig.is_enabled,
        enable_prompt_analysis: agent.sentinelConfig.enable_prompt_analysis,
        enable_tool_analysis: agent.sentinelConfig.enable_tool_analysis,
        enable_shell_analysis: agent.sentinelConfig.enable_shell_analysis,
        aggressiveness_level: agent.sentinelConfig.aggressiveness_level,
      })
    } else {
      setUseCustomSettings(false)
      setFormData({
        is_enabled: null,
        enable_prompt_analysis: null,
        enable_tool_analysis: null,
        enable_shell_analysis: null,
        aggressiveness_level: null,
      })
    }
    setShowModal(true)
  }

  const handleSave = async () => {
    if (!selectedAgent) return
    setSaving(true)
    setError(null)
    try {
      if (useCustomSettings) {
        await api.updateSentinelAgentConfig(selectedAgent.id, formData)
        setSuccess(`Security settings saved for ${selectedAgent.contact_name}`)
      } else {
        // Delete custom config to use defaults
        await api.deleteSentinelAgentConfig(selectedAgent.id)
        setSuccess(`${selectedAgent.contact_name} now uses tenant defaults`)
      }
      setShowModal(false)
      loadData()
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const aggressivenessLabels = ['Off', 'Moderate', 'Aggressive', 'Extra Aggressive']

  const getProtectionBadge = (agent: AgentWithSecurity) => {
    if (!sentinelConfig?.is_enabled) {
      return <span className="text-xs px-2 py-0.5 rounded-full bg-gray-500/20 text-gray-400">Disabled</span>
    }
    if (agent.sentinelConfig) {
      if (agent.sentinelConfig.is_enabled === false) {
        return <span className="text-xs px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400">Custom (Disabled)</span>
      }
      return <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400">Custom Settings</span>
    }
    return <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400">Using Defaults</span>
  }

  const formatDate = (dateStr: string) => formatDateTimeFull(dateStr)

  const getSeverityColor = (detectionType: string) => {
    switch (detectionType) {
      case 'shell_malicious':
        return 'bg-red-500/20 text-red-400 border-red-500/50'
      case 'prompt_injection':
      case 'agent_takeover':
        return 'bg-orange-500/20 text-orange-400 border-orange-500/50'
      case 'poisoning':
        return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50'
      default:
        return 'bg-gray-500/20 text-gray-400 border-gray-500/50'
    }
  }

  if (authLoading || loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="relative w-12 h-12 mx-auto mb-4">
              <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
              <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
            </div>
            <p className="text-tsushin-slate font-medium">Loading security configuration...</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-red-900/20 via-orange-900/10 to-transparent"></div>
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 pt-8 pb-6 relative">
          <div className="flex items-center gap-4 mb-2">
            <div className="w-12 h-12 rounded-xl bg-red-500/20 flex items-center justify-center">
              <svg className="w-6 h-6 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-3xl font-display font-bold text-white">Security Configuration</h1>
              <p className="text-tsushin-slate">Configure Sentinel protection for your agents</p>
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        {/* Sub Navigation */}
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="border-b border-tsushin-border/50">
            <nav className="flex">
              <Link
                href="/agents"
                className="relative px-6 py-3.5 font-medium text-sm transition-all duration-200 text-tsushin-slate hover:text-white"
              >
                <span className="relative z-10">Agents</span>
              </Link>
              <Link
                href="/agents/contacts"
                className="relative px-6 py-3.5 font-medium text-sm transition-all duration-200 text-tsushin-slate hover:text-white"
              >
                <span className="relative z-10">Contacts</span>
              </Link>
              <Link
                href="/agents/personas"
                className="relative px-6 py-3.5 font-medium text-sm transition-all duration-200 text-tsushin-slate hover:text-white"
              >
                <span className="relative z-10">Personas</span>
              </Link>
              <Link
                href="/agents/projects"
                className="relative px-6 py-3.5 font-medium text-sm transition-all duration-200 text-tsushin-slate hover:text-white"
              >
                <span className="relative z-10">Projects</span>
              </Link>
              <Link
                href="/agents/security"
                className={`relative px-6 py-3.5 font-medium text-sm transition-all duration-200 ${
                  pathname?.startsWith('/agents/security')
                    ? 'text-white'
                    : 'text-tsushin-slate hover:text-white'
                }`}
              >
                <span className="relative z-10 flex items-center gap-1.5">
                  <svg className="w-4 h-4 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                  Security
                </span>
                {pathname?.startsWith('/agents/security') && (
                  <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-red-500 to-orange-400" />
                )}
              </Link>
            </nav>
          </div>
        </div>

        {/* Messages */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-4">
            <p className="text-red-400">{error}</p>
          </div>
        )}
        {success && (
          <div className="bg-green-500/10 border border-green-500/50 rounded-lg p-4">
            <p className="text-green-400">{success}</p>
          </div>
        )}

        {/* Stats Overview */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-stagger">
          <div className="stat-card stat-card-indigo group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Total Agents</p>
                <p className="text-3xl font-display font-bold text-white mt-1">{agents.length}</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-teal-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-success group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Protected</p>
                <p className="text-3xl font-display font-bold text-green-400 mt-1">
                  {sentinelConfig?.is_enabled ? agents.filter(a => !a.sentinelConfig || a.sentinelConfig.is_enabled !== false).length : 0}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-green-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-warning group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Threats Blocked</p>
                <p className="text-3xl font-display font-bold text-orange-400 mt-1">{stats?.threats_blocked || 0}</p>
                <p className="text-xs text-tsushin-muted mt-1">Last 7 days</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-orange-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></svg>
              </div>
            </div>
          </div>

          <div className="stat-card stat-card-accent group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Custom Configs</p>
                <p className="text-3xl font-display font-bold text-purple-400 mt-1">
                  {agents.filter(a => a.sentinelConfig).length}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
            </div>
          </div>
        </div>

        {/* Global Sentinel Status */}
        <div className="glass-card rounded-xl p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className={`w-3 h-3 rounded-full ${sentinelConfig?.is_enabled ? 'bg-green-500' : 'bg-gray-500'}`}></div>
              <div>
                <h3 className="text-lg font-semibold text-white">
                  Sentinel {sentinelConfig?.is_enabled ? 'Active' : 'Disabled'}
                </h3>
                <p className="text-sm text-tsushin-slate">
                  {sentinelConfig?.is_enabled
                    ? `Aggressiveness: ${aggressivenessLabels[sentinelConfig?.aggressiveness_level || 0]}`
                    : 'Enable Sentinel to protect your agents'}
                </p>
              </div>
            </div>
            <Link
              href="/settings/sentinel"
              className="px-4 py-2 bg-tsushin-surface hover:bg-tsushin-elevated border border-tsushin-border rounded-lg text-sm font-medium text-white transition-colors"
            >
              Configure Sentinel
            </Link>
          </div>
        </div>

        {/* Agents Grid */}
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="p-6 border-b border-tsushin-border/50">
            <h3 className="text-lg font-display font-semibold text-white">Agent Security Configuration</h3>
            <p className="text-sm text-tsushin-slate mt-1">Configure per-agent Sentinel overrides or use tenant defaults</p>
          </div>

          <div className="divide-y divide-tsushin-border/50">
            {agents.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-tsushin-slate">No agents configured yet.</p>
                <Link href="/agents" className="text-teal-400 hover:text-teal-300 text-sm mt-2 inline-block">
                  Create your first agent
                </Link>
              </div>
            ) : (
              agents.map((agent) => (
                <div
                  key={agent.id}
                  className="p-4 hover:bg-gray-800/30 transition-colors cursor-pointer"
                  onClick={() => canEdit && openAgentModal(agent)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-teal-500 to-cyan-400 flex items-center justify-center text-white font-bold">
                        {agent.contact_name?.charAt(0).toUpperCase() || 'A'}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-white">{agent.contact_name}</p>
                          {getProtectionBadge(agent)}
                        </div>
                        <p className="text-xs text-tsushin-slate">
                          {agent.sentinelConfig
                            ? `Custom: ${agent.sentinelConfig.aggressiveness_level !== null ? aggressivenessLabels[agent.sentinelConfig.aggressiveness_level] : 'Inherited'}`
                            : 'Using tenant defaults'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      {/* Protection icons */}
                      <div className="flex items-center gap-2 text-xs">
                        <span className={`px-2 py-1 rounded ${
                          agent.sentinelConfig?.enable_prompt_analysis === false
                            ? 'bg-gray-500/20 text-gray-400'
                            : sentinelConfig?.enable_prompt_analysis
                              ? 'bg-green-500/20 text-green-400'
                              : 'bg-gray-500/20 text-gray-400'
                        }`}>
                          Prompt
                        </span>
                        <span className={`px-2 py-1 rounded ${
                          agent.sentinelConfig?.enable_tool_analysis === false
                            ? 'bg-gray-500/20 text-gray-400'
                            : sentinelConfig?.enable_tool_analysis
                              ? 'bg-green-500/20 text-green-400'
                              : 'bg-gray-500/20 text-gray-400'
                        }`}>
                          Tool
                        </span>
                        <span className={`px-2 py-1 rounded ${
                          agent.sentinelConfig?.enable_shell_analysis === false
                            ? 'bg-gray-500/20 text-gray-400'
                            : sentinelConfig?.enable_shell_analysis
                              ? 'bg-green-500/20 text-green-400'
                              : 'bg-gray-500/20 text-gray-400'
                        }`}>
                          Shell
                        </span>
                      </div>
                      {canEdit && (
                        <svg className="w-5 h-5 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Recent Security Events */}
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="p-6 border-b border-tsushin-border/50 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-display font-semibold text-white">Recent Security Events</h3>
              <p className="text-sm text-tsushin-slate mt-1">Latest threats detected across all agents</p>
            </div>
            <Link
              href="/"
              className="text-sm text-teal-400 hover:text-teal-300"
            >
              View all in Watcher
            </Link>
          </div>

          {recentLogs.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-tsushin-slate">No threats detected recently. Your agents are secure!</p>
            </div>
          ) : (
            <div className="divide-y divide-tsushin-border/50">
              {recentLogs.map((log) => (
                <div key={log.id} className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-0.5 text-xs rounded-full border ${getSeverityColor(log.detection_type)}`}>
                        {log.detection_type.replace('_', ' ')}
                      </span>
                      <span className="text-sm text-white truncate max-w-md">{log.input_content}</span>
                    </div>
                    <div className="text-xs text-tsushin-slate">
                      {formatDate(log.created_at)}
                    </div>
                  </div>
                  {log.threat_reason && (
                    <p className="text-xs text-orange-400 mt-2 truncate">{log.threat_reason}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Agent Override Modal */}
      {showModal && selectedAgent && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setShowModal(false)}
        >
          <div
            className="bg-tsushin-elevated rounded-xl max-w-lg w-full shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-tsushin-border/50">
              <h3 className="text-lg font-semibold text-white">
                Security Settings - {selectedAgent.contact_name}
              </h3>
              <p className="text-sm text-tsushin-slate mt-1">
                Configure Sentinel protection for this agent
              </p>
            </div>

            <div className="p-6 space-y-6">
              {/* Use Custom Settings Toggle */}
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-white">Use Custom Settings</p>
                  <p className="text-sm text-tsushin-slate">Override tenant defaults for this agent</p>
                </div>
                <button
                  type="button"
                  onClick={() => setUseCustomSettings(!useCustomSettings)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    useCustomSettings ? 'bg-teal-500' : 'bg-gray-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      useCustomSettings ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              {useCustomSettings && (
                <>
                  {/* Enable Sentinel */}
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-medium text-white">Enable Sentinel</p>
                      <p className="text-sm text-tsushin-slate">Turn on/off security for this agent</p>
                    </div>
                    <select
                      value={formData.is_enabled === null ? 'inherit' : formData.is_enabled ? 'true' : 'false'}
                      onChange={(e) => setFormData({
                        ...formData,
                        is_enabled: e.target.value === 'inherit' ? null : e.target.value === 'true'
                      })}
                      className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm"
                    >
                      <option value="inherit">Inherit from tenant</option>
                      <option value="true">Enabled</option>
                      <option value="false">Disabled</option>
                    </select>
                  </div>

                  {/* Component Toggles */}
                  <div className="space-y-3">
                    <p className="font-medium text-white">Analysis Components</p>

                    <div className="flex items-center justify-between">
                      <span className="text-sm text-tsushin-slate">Prompt Analysis</span>
                      <select
                        value={formData.enable_prompt_analysis === null ? 'inherit' : formData.enable_prompt_analysis ? 'true' : 'false'}
                        onChange={(e) => setFormData({
                          ...formData,
                          enable_prompt_analysis: e.target.value === 'inherit' ? null : e.target.value === 'true'
                        })}
                        className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                      >
                        <option value="inherit">Inherit</option>
                        <option value="true">Enabled</option>
                        <option value="false">Disabled</option>
                      </select>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-sm text-tsushin-slate">Tool Analysis</span>
                      <select
                        value={formData.enable_tool_analysis === null ? 'inherit' : formData.enable_tool_analysis ? 'true' : 'false'}
                        onChange={(e) => setFormData({
                          ...formData,
                          enable_tool_analysis: e.target.value === 'inherit' ? null : e.target.value === 'true'
                        })}
                        className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                      >
                        <option value="inherit">Inherit</option>
                        <option value="true">Enabled</option>
                        <option value="false">Disabled</option>
                      </select>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-sm text-tsushin-slate">Shell Analysis</span>
                      <select
                        value={formData.enable_shell_analysis === null ? 'inherit' : formData.enable_shell_analysis ? 'true' : 'false'}
                        onChange={(e) => setFormData({
                          ...formData,
                          enable_shell_analysis: e.target.value === 'inherit' ? null : e.target.value === 'true'
                        })}
                        className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded text-white text-sm"
                      >
                        <option value="inherit">Inherit</option>
                        <option value="true">Enabled</option>
                        <option value="false">Disabled</option>
                      </select>
                    </div>
                  </div>

                  {/* Aggressiveness */}
                  <div>
                    <p className="font-medium text-white mb-2">Aggressiveness Level</p>
                    <select
                      value={formData.aggressiveness_level === null ? 'inherit' : formData.aggressiveness_level.toString()}
                      onChange={(e) => setFormData({
                        ...formData,
                        aggressiveness_level: e.target.value === 'inherit' ? null : parseInt(e.target.value)
                      })}
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm"
                    >
                      <option value="inherit">Inherit from tenant</option>
                      <option value="0">Off</option>
                      <option value="1">Moderate</option>
                      <option value="2">Aggressive</option>
                      <option value="3">Extra Aggressive</option>
                    </select>
                  </div>
                </>
              )}
            </div>

            <div className="p-6 border-t border-tsushin-border/50 flex justify-end gap-3">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="px-4 py-2 bg-teal-600 hover:bg-teal-500 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Settings'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
