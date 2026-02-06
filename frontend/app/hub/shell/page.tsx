'use client'

import { useEffect, useState, useCallback, useMemo, FormEvent } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import Link from 'next/link'
import api, { SecurityPattern, SecurityPatternCreate, SecurityPatternUpdate, PatternTestResult, SentinelConfig, SentinelLog, SentinelStats, SentinelConfigUpdate } from '@/lib/client'
import { copyToClipboard } from '@/lib/clipboard'
import {
  TerminalIcon,
  RadioIcon,
  ClipboardIcon,
  LockIcon,
  ShieldIcon,
  RefreshIcon,
  BanIcon,
  StopIcon,
  TrashIcon,
  EditIcon,
  CheckCircleIcon,
  ShieldCheckIcon,
  BeakerIcon,
  LightbulbIcon,
} from '@/components/ui/icons'

interface ShellIntegration {
  id: number
  name: string
  display_name: string | null
  is_active: boolean
  health_status: string
  poll_interval: number
  mode: string
  hostname: string | null
  remote_ip: string | null
  os_info: Record<string, unknown> | null
  last_checkin: string | null
  is_online: boolean
  allowed_commands: string[]
  allowed_paths: string[]
  yolo_mode: boolean  // CRIT-005: Auto-approve high-risk commands
}

interface ShellCommand {
  id: string
  shell_id: number
  commands: string[]
  initiated_by: string
  status: string
  queued_at: string
  completed_at: string | null
  exit_code: number | null
  stdout: string | null
  stderr: string | null
}

interface PendingApproval {
  command_id: string
  shell_id: number
  commands: string[]
  initiated_by: string
  queued_at: string
  expires_at: string
  time_remaining_seconds: number
  risk_level: string
  security_warnings: string[]
}

interface ApprovalStats {
  pending_count: number
  approved_today: number
  rejected_today: number
  expired_today: number
}

// Pattern form data interface
interface PatternFormData {
  pattern: string
  pattern_type: 'blocked' | 'high_risk'
  risk_level: string
  description: string
  category: string
  is_active: boolean
}

const DEFAULT_PATTERN_FORM: PatternFormData = {
  pattern: '',
  pattern_type: 'high_risk',
  risk_level: 'high',
  description: '',
  category: '',
  is_active: true
}

const PATTERN_CATEGORIES = [
  'filesystem', 'network', 'system', 'database', 'container',
  'permissions', 'security', 'package', 'disk', 'other'
]

const RISK_LEVELS = ['low', 'medium', 'high', 'critical']

export default function ShellDashboardPage() {
  const { hasPermission } = useAuth()
  const [activeTab, setActiveTab] = useState<'beacons' | 'commands' | 'approvals' | 'patterns' | 'security'>('beacons')
  const [integrations, setIntegrations] = useState<ShellIntegration[]>([])
  const [commands, setCommands] = useState<ShellCommand[]>([])
  const [pendingApprovals, setPendingApprovals] = useState<PendingApproval[]>([])
  const [approvalStats, setApprovalStats] = useState<ApprovalStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newBeaconName, setNewBeaconName] = useState('')
  const [creating, setCreating] = useState(false)
  const [newApiKey, setNewApiKey] = useState<string | null>(null)

  // Phase 19: Security Patterns State
  const [patterns, setPatterns] = useState<SecurityPattern[]>([])
  const [patternsLoading, setPatternsLoading] = useState(false)
  const [showPatternModal, setShowPatternModal] = useState(false)
  const [editingPattern, setEditingPattern] = useState<SecurityPattern | null>(null)
  const [patternForm, setPatternForm] = useState<PatternFormData>(DEFAULT_PATTERN_FORM)
  const [patternError, setPatternError] = useState<string | null>(null)
  const [savingPattern, setSavingPattern] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState<{id: number, description: string} | null>(null)
  const [patternSearchQuery, setPatternSearchQuery] = useState('')
  const [patternTypeFilter, setPatternTypeFilter] = useState<string>('')
  const [patternCategoryFilter, setPatternCategoryFilter] = useState<string>('')
  const [showInactivePatterns, setShowInactivePatterns] = useState(false)
  // Pattern tester state
  const [showPatternTester, setShowPatternTester] = useState(false)
  const [testPattern, setTestPattern] = useState('')
  const [testCommands, setTestCommands] = useState<string[]>([''])
  const [testResults, setTestResults] = useState<PatternTestResult | null>(null)
  const [testingPattern, setTestingPattern] = useState(false)

  // Phase 20: Sentinel Security State
  const [sentinelConfig, setSentinelConfig] = useState<SentinelConfig | null>(null)
  const [shellSecurityLogs, setShellSecurityLogs] = useState<SentinelLog[]>([])
  const [shellSecurityStats, setShellSecurityStats] = useState<SentinelStats | null>(null)
  const [sentinelLoading, setSentinelLoading] = useState(false)
  const [savingSentinel, setSavingSentinel] = useState(false)

  const getAuthHeaders = () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

  const loadIntegrations = useCallback(async () => {
    try {
      const resp = await fetch(`${apiUrl}/api/shell/integrations?active_only=false`, { headers: getAuthHeaders() })
      if (resp.ok) setIntegrations(await resp.json())
    } catch (e) { console.error('Failed to load integrations:', e) }
  }, [apiUrl])

  const loadCommands = useCallback(async () => {
    try {
      const resp = await fetch(`${apiUrl}/api/shell/commands?limit=50`, { headers: getAuthHeaders() })
      if (resp.ok) setCommands(await resp.json())
    } catch (e) { console.error('Failed to load commands:', e) }
  }, [apiUrl])

  const loadApprovals = useCallback(async () => {
    try {
      const [pendingResp, statsResp] = await Promise.all([
        fetch(`${apiUrl}/api/shell/approvals/pending`, { headers: getAuthHeaders() }),
        fetch(`${apiUrl}/api/shell/approvals/stats`, { headers: getAuthHeaders() })
      ])
      if (pendingResp.ok) setPendingApprovals(await pendingResp.json())
      if (statsResp.ok) setApprovalStats(await statsResp.json())
    } catch (e) { console.error('Failed to load approvals:', e) }
  }, [apiUrl])

  // Phase 19: Load security patterns
  const loadPatterns = useCallback(async () => {
    setPatternsLoading(true)
    try {
      const data = await api.getSecurityPatterns(showInactivePatterns)
      setPatterns(data)
    } catch (e) {
      console.error('Failed to load security patterns:', e)
    } finally {
      setPatternsLoading(false)
    }
  }, [showInactivePatterns])

  // Phase 20: Load Sentinel security data for shell
  const loadSentinelData = useCallback(async () => {
    setSentinelLoading(true)
    try {
      const [configData, logsData, statsData] = await Promise.all([
        api.getSentinelConfig(),
        api.getSentinelLogs({ limit: 20, analysis_type: 'shell' }),
        api.getSentinelStats(7),
      ])
      setSentinelConfig(configData)
      setShellSecurityLogs(logsData)
      setShellSecurityStats(statsData)
    } catch (e) {
      console.error('Failed to load Sentinel data:', e)
    } finally {
      setSentinelLoading(false)
    }
  }, [])

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true)
      await Promise.all([loadIntegrations(), loadCommands(), loadApprovals(), loadPatterns(), loadSentinelData()])
      setLoading(false)
    }
    loadAll()
    const interval = setInterval(() => {
      loadIntegrations()
      loadCommands()
      loadApprovals()
    }, 10000)
    return () => clearInterval(interval)
  }, [loadIntegrations, loadCommands, loadApprovals, loadPatterns, loadSentinelData])

  // Reload patterns when inactive filter changes
  useEffect(() => {
    if (activeTab === 'patterns') {
      loadPatterns()
    }
  }, [showInactivePatterns, activeTab, loadPatterns])

  // Phase 19: Filtered patterns
  const filteredPatterns = useMemo(() => {
    return patterns.filter(p => {
      const matchesSearch = !patternSearchQuery ||
        p.pattern.toLowerCase().includes(patternSearchQuery.toLowerCase()) ||
        p.description.toLowerCase().includes(patternSearchQuery.toLowerCase())
      const matchesType = !patternTypeFilter || p.pattern_type === patternTypeFilter
      const matchesCategory = !patternCategoryFilter || p.category === patternCategoryFilter
      return matchesSearch && matchesType && matchesCategory
    })
  }, [patterns, patternSearchQuery, patternTypeFilter, patternCategoryFilter])

  // Phase 19: Pattern validation
  const validatePatternRegex = (pattern: string): boolean => {
    try {
      new RegExp(pattern)
      setPatternError(null)
      return true
    } catch (e) {
      setPatternError((e as Error).message)
      return false
    }
  }

  // Phase 19: Pattern CRUD handlers
  const handleSavePattern = async (e: FormEvent) => {
    e.preventDefault()
    if (!validatePatternRegex(patternForm.pattern)) {
      setError('Invalid regex pattern')
      return
    }

    setSavingPattern(true)
    try {
      if (editingPattern) {
        // Update existing pattern
        const updateData: SecurityPatternUpdate = {
          pattern: patternForm.pattern,
          pattern_type: patternForm.pattern_type,
          risk_level: patternForm.risk_level,
          description: patternForm.description,
          category: patternForm.category || undefined,
          is_active: patternForm.is_active
        }
        await api.updateSecurityPattern(editingPattern.id, updateData)
        setSuccess('Pattern updated successfully')
      } else {
        // Create new pattern
        const createData: SecurityPatternCreate = {
          pattern: patternForm.pattern,
          pattern_type: patternForm.pattern_type,
          risk_level: patternForm.risk_level,
          description: patternForm.description,
          category: patternForm.category || undefined,
          is_active: patternForm.is_active
        }
        await api.createSecurityPattern(createData)
        setSuccess('Pattern created successfully')
      }
      setShowPatternModal(false)
      setEditingPattern(null)
      setPatternForm(DEFAULT_PATTERN_FORM)
      await loadPatterns()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSavingPattern(false)
    }
  }

  const handleDeletePattern = async () => {
    if (!deleteConfirm) return
    try {
      await api.deleteSecurityPattern(deleteConfirm.id)
      setSuccess('Pattern deleted successfully')
      setDeleteConfirm(null)
      await loadPatterns()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleTogglePatternActive = async (pattern: SecurityPattern) => {
    try {
      await api.updateSecurityPattern(pattern.id, { is_active: !pattern.is_active })
      setSuccess(`Pattern ${pattern.is_active ? 'deactivated' : 'activated'}`)
      await loadPatterns()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleTestPattern = async () => {
    const commandsToTest = testCommands.filter(c => c.trim())
    if (!testPattern || commandsToTest.length === 0) return

    setTestingPattern(true)
    try {
      const result = await api.testSecurityPattern(testPattern, commandsToTest)
      setTestResults(result)
      if (!result.is_valid) {
        setError(`Invalid pattern: ${result.error}`)
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setTestingPattern(false)
    }
  }

  const openEditPattern = (pattern: SecurityPattern) => {
    setEditingPattern(pattern)
    setPatternForm({
      pattern: pattern.pattern,
      pattern_type: pattern.pattern_type,
      risk_level: pattern.risk_level || 'high',
      description: pattern.description,
      category: pattern.category || '',
      is_active: pattern.is_active
    })
    setPatternError(null)
    setShowPatternModal(true)
  }

  const openCreatePattern = () => {
    setEditingPattern(null)
    setPatternForm(DEFAULT_PATTERN_FORM)
    setPatternError(null)
    setShowPatternModal(true)
  }

  const handleCreateBeacon = async () => {
    if (!newBeaconName.trim()) return
    setCreating(true)
    try {
      const resp = await fetch(`${apiUrl}/api/shell/integrations`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ name: newBeaconName.trim(), poll_interval: 5, mode: 'beacon' })
      })
      if (resp.ok) {
        const data = await resp.json()
        setNewApiKey(data.api_key)
        setSuccess(`Beacon "${data.name}" created! Save the API key - it won't be shown again.`)
        loadIntegrations()
      } else {
        const err = await resp.json()
        setError(err.detail || 'Failed to create beacon')
      }
    } catch (e) {
      setError('Failed to create beacon')
    } finally {
      setCreating(false)
    }
  }

  const handleApprove = async (commandId: string) => {
    try {
      const resp = await fetch(`${apiUrl}/api/shell/approvals/${commandId}/approve`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({})
      })
      if (resp.ok) {
        setSuccess('Command approved')
        loadApprovals()
        loadCommands()
      } else {
        const err = await resp.json()
        setError(err.detail || 'Failed to approve')
      }
    } catch (e) { setError('Failed to approve command') }
    setTimeout(() => setSuccess(null), 3000)
  }

  const handleReject = async (commandId: string) => {
    const reason = prompt('Rejection reason:')
    if (!reason) return
    try {
      const resp = await fetch(`${apiUrl}/api/shell/approvals/${commandId}/reject`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ reason })
      })
      if (resp.ok) {
        setSuccess('Command rejected')
        loadApprovals()
        loadCommands()
      } else {
        const err = await resp.json()
        setError(err.detail || 'Failed to reject')
      }
    } catch (e) { setError('Failed to reject command') }
    setTimeout(() => setSuccess(null), 3000)
  }

  const handleDeleteBeacon = async (beaconId: number, beaconName: string, isOnline: boolean) => {
    const message = isOnline
      ? `Are you sure you want to delete beacon "${beaconName}"?\n\nThis will:\n• Send a shutdown command to stop the beacon\n• Remove auto-start persistence\n• Delete all command history`
      : `Are you sure you want to delete beacon "${beaconName}"?\n\nThis will delete all command history for this beacon.`

    if (!confirm(message)) {
      return
    }
    try {
      const resp = await fetch(`${apiUrl}/api/shell/integrations/${beaconId}?graceful=true`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      })
      if (resp.ok) {
        const data = await resp.json()
        setSuccess(data.message || `Beacon "${beaconName}" deleted successfully`)
        loadIntegrations()
        loadCommands()
      } else {
        const err = await resp.json()
        setError(err.detail || 'Failed to delete beacon')
      }
    } catch (e) {
      setError('Failed to delete beacon')
    }
    setTimeout(() => { setSuccess(null); setError(null) }, 3000)
  }

  const handlePersistenceToggle = async (beaconId: number, action: 'install' | 'uninstall') => {
    try {
      const resp = await fetch(`${apiUrl}/api/shell/integrations/${beaconId}/persistence?action=${action}`, {
        method: 'POST',
        headers: getAuthHeaders()
      })
      if (resp.ok) {
        setSuccess(`Persistence ${action} command sent to beacon`)
        loadCommands()
      } else {
        const err = await resp.json()
        setError(err.detail || `Failed to ${action} persistence`)
      }
    } catch (e) {
      setError(`Failed to ${action} persistence`)
    }
    setTimeout(() => { setSuccess(null); setError(null) }, 3000)
  }

  const handleShutdownBeacon = async (beaconId: number, beaconName: string) => {
    if (!confirm(`Send shutdown command to "${beaconName}"?\n\nThe beacon will stop its process. If persistence is installed, it will restart on next login/reboot.`)) {
      return
    }
    try {
      const resp = await fetch(`${apiUrl}/api/shell/integrations/${beaconId}/shutdown`, {
        method: 'POST',
        headers: getAuthHeaders()
      })
      if (resp.ok) {
        setSuccess('Shutdown command sent - beacon will stop on next check-in')
        loadIntegrations()
      } else {
        const err = await resp.json()
        setError(err.detail || 'Failed to send shutdown command')
      }
    } catch (e) {
      setError('Failed to send shutdown command')
    }
    setTimeout(() => { setSuccess(null); setError(null) }, 3000)
  }

  const handleYoloModeToggle = async (beaconId: number, beaconName: string, enabled: boolean) => {
    // If enabling YOLO mode, require confirmation
    if (enabled) {
      const confirmed = confirm(
        `Enable YOLO Mode for "${beaconName}"?\n\n` +
        `WARNING: This will auto-approve HIGH-RISK commands without manual review!\n\n` +
        `- Dangerous commands (rm -rf, chmod 777, etc.) will execute immediately\n` +
        `- Only BLOCKED commands (fork bombs, system destruction) will still be rejected\n` +
        `- Recommended only for trusted development environments\n\n` +
        `Are you sure you want to enable YOLO mode?`
      )
      if (!confirmed) return
    }

    try {
      const resp = await fetch(`${apiUrl}/api/shell/integrations/${beaconId}`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        body: JSON.stringify({ yolo_mode: enabled })
      })
      if (resp.ok) {
        setSuccess(`YOLO mode ${enabled ? 'enabled' : 'disabled'} for "${beaconName}"`)
        loadIntegrations()
      } else {
        const err = await resp.json()
        setError(err.detail || 'Failed to update YOLO mode')
      }
    } catch (e) {
      setError('Failed to update YOLO mode')
    }
    setTimeout(() => { setSuccess(null); setError(null) }, 3000)
  }

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      queued: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50',
      sent: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
      completed: 'bg-green-500/20 text-green-400 border-green-500/50',
      failed: 'bg-red-500/20 text-red-400 border-red-500/50',
      pending_approval: 'bg-orange-500/20 text-orange-400 border-orange-500/50',
      rejected: 'bg-red-500/20 text-red-400 border-red-500/50',
      expired: 'bg-gray-500/20 text-gray-400 border-gray-500/50',
    }
    return `px-2 py-1 text-xs font-medium border rounded-full ${colors[status] || colors.queued}`
  }

  const getRiskBadge = (level: string) => {
    const colors: Record<string, string> = {
      low: 'bg-green-500/20 text-green-400 border-green-500/50',
      medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50',
      high: 'bg-orange-500/20 text-orange-400 border-orange-500/50',
      critical: 'bg-red-500/20 text-red-400 border-red-500/50',
    }
    return `px-2 py-1 text-xs font-medium border rounded-full ${colors[level] || colors.low}`
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-gray-800"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-teal-500 animate-spin"></div>
          </div>
          <p className="text-gray-400">Loading Shell Dashboard...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex justify-between items-center mb-8">
          <div>
            <div className="flex items-center gap-4 mb-2">
              <a href="/hub" className="text-gray-400 hover:text-white transition-colors flex items-center gap-2">
                <span>←</span>
                <span className="text-sm">Back to Hub</span>
              </a>
            </div>
            <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
              <TerminalIcon size={36} className="text-teal-400" /> Shell Command Center
            </h1>
            <p className="text-gray-400">Manage remote shell beacons and command execution</p>
          </div>
          <button onClick={() => setShowCreateModal(true)} className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-medium transition-colors">
            + Register Beacon
          </button>
        </div>

        {success && (
          <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-xl text-green-400 flex justify-between items-center">
            <span>{success}</span>
            <button onClick={() => setSuccess(null)} className="text-green-400 hover:text-green-300">×</button>
          </div>
        )}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 flex justify-between items-center">
            <span>{error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">×</button>
          </div>
        )}

        {approvalStats && approvalStats.pending_count > 0 && (
          <div className="mb-6 p-4 bg-orange-500/10 border border-orange-500/30 rounded-xl flex items-center gap-4">
            <span className="text-2xl">⚠️</span>
            <div>
              <p className="text-orange-400 font-semibold">{approvalStats.pending_count} command(s) awaiting approval</p>
              <p className="text-sm text-gray-400">High-risk commands require manual review</p>
            </div>
            <button onClick={() => setActiveTab('approvals')} className="ml-auto px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg">
              Review Now
            </button>
          </div>
        )}

        <div className="bg-gray-900/50 border border-gray-800 rounded-xl overflow-hidden">
          <div className="border-b border-gray-800">
            <nav className="flex">
              {[
                { key: 'beacons', label: 'Beacons', Icon: RadioIcon, count: integrations.length },
                { key: 'commands', label: 'Command History', Icon: ClipboardIcon, count: commands.length },
                { key: 'approvals', label: 'Approvals', Icon: LockIcon, count: approvalStats?.pending_count || 0 },
                { key: 'patterns', label: 'Patterns', Icon: ShieldIcon, count: patterns.filter(p => !p.is_active).length },
                { key: 'security', label: 'Sentinel', Icon: LockIcon, count: shellSecurityStats?.threats_blocked || 0 }
              ].map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key as typeof activeTab)}
                  className={`relative px-6 py-4 font-medium text-sm transition-all flex items-center gap-2 ${
                    activeTab === tab.key ? 'text-white bg-gray-800/50' : 'text-gray-400 hover:text-white'
                  }`}
                >
                  <tab.Icon size={16} />
                  <span>{tab.label}</span>
                  {tab.count > 0 && (
                    <span className={`px-2 py-0.5 rounded-full text-xs ${
                      tab.key === 'approvals' && tab.count > 0 ? 'bg-orange-500 text-white' : 'bg-gray-700 text-gray-300'
                    }`}>
                      {tab.count}
                    </span>
                  )}
                  {activeTab === tab.key && (
                    <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-teal-500" />
                  )}
                </button>
              ))}
            </nav>
          </div>

          <div className="p-6">
            {activeTab === 'beacons' && (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {integrations.length === 0 ? (
                  <div className="col-span-full text-center py-12">
                    <RadioIcon size={64} className="mx-auto mb-4 text-teal-400" />
                    <h3 className="text-xl font-semibold text-white mb-2">No Beacons Registered</h3>
                    <p className="text-gray-400 mb-4">Register a beacon to start executing remote commands</p>
                    <button onClick={() => setShowCreateModal(true)} className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg">
                      + Register First Beacon
                    </button>
                  </div>
                ) : integrations.map(beacon => (
                  <div key={beacon.id} className={`bg-gray-800/50 border rounded-xl p-5 hover:border-teal-500/50 transition-colors group relative ${beacon.yolo_mode ? 'border-yellow-500/50' : 'border-gray-700'}`}>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className={`w-3 h-3 rounded-full ${beacon.is_online ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
                        <h3 className="font-semibold text-white">{beacon.display_name || beacon.name}</h3>
                      </div>
                      <div className="flex items-center gap-2">
                        {beacon.yolo_mode && (
                          <span className="px-2 py-1 text-xs rounded-full bg-yellow-500/20 text-yellow-400 border border-yellow-500/50" title="YOLO Mode: High-risk commands auto-approved">
                            YOLO
                          </span>
                        )}
                        <span className={`px-2 py-1 text-xs rounded-full ${beacon.is_online ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                          {beacon.is_online ? 'Online' : 'Offline'}
                        </span>
                      </div>
                    </div>
                    <div className="space-y-2 text-sm text-gray-400">
                      {beacon.hostname && <p>Host: <span className="text-white font-mono">{beacon.hostname}</span></p>}
                      {beacon.remote_ip && <p>IP: <span className="text-white font-mono">{beacon.remote_ip}</span></p>}
                      <p>Mode: <span className="text-teal-400">{beacon.mode}</span> | Poll: {beacon.poll_interval}s</p>
                      {beacon.last_checkin && <p>Last seen: {new Date(beacon.last_checkin).toLocaleString()}</p>}
                    </div>

                    {/* YOLO Mode Toggle */}
                    <div className="mt-3 pt-3 border-t border-gray-700">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-400">YOLO Mode</span>
                          <span className="text-xs text-gray-500" title="Auto-approve high-risk commands without manual review">(?)</span>
                        </div>
                        <button
                          onClick={() => handleYoloModeToggle(beacon.id, beacon.name, !beacon.yolo_mode)}
                          className={`relative w-11 h-6 rounded-full transition-colors ${
                            beacon.yolo_mode
                              ? 'bg-yellow-500'
                              : 'bg-gray-600'
                          }`}
                          title={beacon.yolo_mode
                            ? 'YOLO Mode ON: High-risk commands auto-approved'
                            : 'YOLO Mode OFF: High-risk commands require approval'}
                        >
                          <span className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
                            beacon.yolo_mode ? 'left-6' : 'left-1'
                          }`} />
                        </button>
                      </div>
                      {beacon.yolo_mode && (
                        <p className="mt-2 text-xs text-yellow-400/80">
                          High-risk commands will execute without approval
                        </p>
                      )}
                    </div>

                    {/* Action buttons - always visible for better UX */}
                    <div className="mt-3 pt-3 border-t border-gray-700 flex flex-wrap gap-2">
                      {beacon.is_online && (
                        <>
                          <button
                            onClick={() => handlePersistenceToggle(beacon.id, 'install')}
                            className="px-2 py-1 text-xs bg-teal-600/20 hover:bg-teal-600/40 text-teal-400 border border-teal-600/50 rounded flex items-center gap-1"
                            title="Enable auto-start on reboot"
                          >
                            <RefreshIcon size={12} /> Enable Persistence
                          </button>
                          <button
                            onClick={() => handlePersistenceToggle(beacon.id, 'uninstall')}
                            className="px-2 py-1 text-xs bg-gray-600/20 hover:bg-gray-600/40 text-gray-400 border border-gray-600/50 rounded flex items-center gap-1"
                            title="Disable auto-start on reboot"
                          >
                            <BanIcon size={12} /> Disable Persistence
                          </button>
                          <button
                            onClick={() => handleShutdownBeacon(beacon.id, beacon.name)}
                            className="px-2 py-1 text-xs bg-orange-600/20 hover:bg-orange-600/40 text-orange-400 border border-orange-600/50 rounded flex items-center gap-1"
                            title="Stop the beacon process"
                          >
                            <StopIcon size={12} /> Shutdown
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => handleDeleteBeacon(beacon.id, beacon.name, beacon.is_online)}
                        className="px-2 py-1 text-xs bg-red-600/20 hover:bg-red-600/40 text-red-400 border border-red-600/50 rounded flex items-center gap-1"
                        title="Delete beacon and all command history"
                      >
                        <TrashIcon size={12} /> Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'commands' && (
              <div className="space-y-4">
                {commands.length === 0 ? (
                  <div className="text-center py-12">
                    <ClipboardIcon size={64} className="mx-auto mb-4 text-teal-400" />
                    <h3 className="text-xl font-semibold text-white mb-2">No Commands Yet</h3>
                    <p className="text-gray-400">Commands executed via beacons will appear here</p>
                  </div>
                ) : commands.map(cmd => (
                  <div key={cmd.id} className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-3">
                        <span className={getStatusBadge(cmd.status)}>{cmd.status}</span>
                        <span className="text-sm text-gray-400">Shell #{cmd.shell_id}</span>
                      </div>
                      <span className="text-sm text-gray-500">{new Date(cmd.queued_at).toLocaleString()}</span>
                    </div>
                    <pre className="bg-gray-900 p-3 rounded text-sm font-mono text-green-400 overflow-x-auto">
                      {cmd.commands.join('\n')}
                    </pre>
                    {cmd.stdout && (
                      <details className="mt-2">
                        <summary className="text-sm text-gray-400 cursor-pointer hover:text-white">Output</summary>
                        <pre className="mt-2 bg-gray-900 p-3 rounded text-xs font-mono text-gray-300 max-h-40 overflow-auto">
                          {cmd.stdout}
                        </pre>
                      </details>
                    )}
                    {cmd.stderr && (
                      <details className="mt-2">
                        <summary className="text-sm text-red-400 cursor-pointer hover:text-red-300">Errors</summary>
                        <pre className="mt-2 bg-gray-900 p-3 rounded text-xs font-mono text-red-400 max-h-40 overflow-auto">
                          {cmd.stderr}
                        </pre>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            )}

            {activeTab === 'approvals' && (
              <div className="space-y-4">
                {approvalStats && (
                  <div className="grid grid-cols-4 gap-4 mb-6">
                    <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4 text-center">
                      <p className="text-3xl font-bold text-orange-400">{approvalStats.pending_count}</p>
                      <p className="text-sm text-gray-400">Pending</p>
                    </div>
                    <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 text-center">
                      <p className="text-3xl font-bold text-green-400">{approvalStats.approved_today}</p>
                      <p className="text-sm text-gray-400">Approved Today</p>
                    </div>
                    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-center">
                      <p className="text-3xl font-bold text-red-400">{approvalStats.rejected_today}</p>
                      <p className="text-sm text-gray-400">Rejected Today</p>
                    </div>
                    <div className="bg-gray-500/10 border border-gray-500/30 rounded-lg p-4 text-center">
                      <p className="text-3xl font-bold text-gray-400">{approvalStats.expired_today}</p>
                      <p className="text-sm text-gray-400">Expired Today</p>
                    </div>
                  </div>
                )}
                {pendingApprovals.length === 0 ? (
                  <div className="text-center py-12">
                    <span className="text-6xl mb-4 block">✅</span>
                    <h3 className="text-xl font-semibold text-white mb-2">No Pending Approvals</h3>
                    <p className="text-gray-400">All clear! High-risk commands will appear here for review.</p>
                  </div>
                ) : pendingApprovals.map(approval => (
                  <div key={approval.command_id} className="bg-gray-800/50 border border-orange-500/30 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl">🔐</span>
                        <div>
                          <span className={getRiskBadge(approval.risk_level)}>{approval.risk_level.toUpperCase()}</span>
                          <span className="ml-2 text-sm text-gray-400">Shell #{approval.shell_id}</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-sm text-gray-400">{approval.initiated_by}</p>
                        <p className="text-xs text-orange-400">Expires in {Math.floor(approval.time_remaining_seconds / 60)}m</p>
                      </div>
                    </div>
                    <pre className="bg-gray-900 p-3 rounded text-sm font-mono text-yellow-400 mb-3">
                      {approval.commands.join('\n')}
                    </pre>
                    {approval.security_warnings.length > 0 && (
                      <div className="mb-3 p-3 bg-red-500/10 border border-red-500/30 rounded">
                        <p className="text-sm font-semibold text-red-400 mb-1">⚠️ Security Warnings:</p>
                        <ul className="text-xs text-red-300 space-y-1">
                          {approval.security_warnings.map((w, i) => <li key={i}>{w}</li>)}
                        </ul>
                      </div>
                    )}
                    <div className="flex gap-3">
                      <button
                        onClick={() => handleApprove(approval.command_id)}
                        className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium"
                      >
                        ✓ Approve
                      </button>
                      <button
                        onClick={() => handleReject(approval.command_id)}
                        className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium"
                      >
                        ✗ Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Phase 19: Security Patterns Tab */}
            {activeTab === 'patterns' && (
              <div>
                {/* Filter Bar */}
                <div className="flex flex-wrap gap-4 mb-6">
                  <input
                    type="text"
                    value={patternSearchQuery}
                    onChange={(e) => setPatternSearchQuery(e.target.value)}
                    placeholder="Search patterns..."
                    className="flex-1 min-w-[200px] px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500"
                  />
                  <select
                    value={patternTypeFilter}
                    onChange={(e) => setPatternTypeFilter(e.target.value)}
                    className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
                  >
                    <option value="">All Types</option>
                    <option value="blocked">Blocked</option>
                    <option value="high_risk">High Risk</option>
                  </select>
                  <select
                    value={patternCategoryFilter}
                    onChange={(e) => setPatternCategoryFilter(e.target.value)}
                    className="px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
                  >
                    <option value="">All Categories</option>
                    {PATTERN_CATEGORIES.map(cat => (
                      <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>
                    ))}
                  </select>
                  <label className="flex items-center gap-2 text-gray-400">
                    <input
                      type="checkbox"
                      checked={showInactivePatterns}
                      onChange={(e) => setShowInactivePatterns(e.target.checked)}
                      className="w-4 h-4 rounded border-gray-600 text-teal-500 focus:ring-teal-500"
                    />
                    Show Inactive
                  </label>
                  <button
                    onClick={() => setShowPatternTester(true)}
                    className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                  >
                    🧪 Test Pattern
                  </button>
                  <button
                    onClick={openCreatePattern}
                    className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg"
                  >
                    + Add Pattern
                  </button>
                </div>

                {/* Patterns Table */}
                {patternsLoading ? (
                  <div className="text-center py-12">
                    <span className="text-gray-400">Loading patterns...</span>
                  </div>
                ) : filteredPatterns.length === 0 ? (
                  <div className="text-center py-12">
                    <span className="text-6xl mb-4 block">🛡️</span>
                    <h3 className="text-xl font-semibold text-white mb-2">No Patterns Found</h3>
                    <p className="text-gray-400 mb-4">
                      {patterns.length === 0 ? 'Security patterns will be seeded on first load' : 'No patterns match your filters'}
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-gray-700 text-left text-sm text-gray-400">
                          <th className="pb-3 pr-4">Pattern</th>
                          <th className="pb-3 pr-4">Type</th>
                          <th className="pb-3 pr-4">Risk</th>
                          <th className="pb-3 pr-4">Category</th>
                          <th className="pb-3 pr-4">Description</th>
                          <th className="pb-3 pr-4">Status</th>
                          <th className="pb-3">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredPatterns.map(pattern => (
                          <tr key={pattern.id} className={`border-b border-gray-800 hover:bg-gray-800/50 ${!pattern.is_active ? 'opacity-50' : ''}`}>
                            <td className="py-3 pr-4">
                              <code className="text-xs font-mono text-teal-400 bg-gray-800 px-2 py-1 rounded max-w-[200px] truncate block" title={pattern.pattern}>
                                {pattern.pattern.length > 30 ? pattern.pattern.slice(0, 30) + '...' : pattern.pattern}
                              </code>
                            </td>
                            <td className="py-3 pr-4">
                              <span className={`px-2 py-1 text-xs rounded-full ${
                                pattern.pattern_type === 'blocked'
                                  ? 'bg-red-500/20 text-red-400 border border-red-500/50'
                                  : 'bg-orange-500/20 text-orange-400 border border-orange-500/50'
                              }`}>
                                {pattern.pattern_type === 'blocked' ? 'BLOCKED' : 'HIGH RISK'}
                              </span>
                            </td>
                            <td className="py-3 pr-4">
                              {pattern.pattern_type === 'high_risk' && pattern.risk_level && (
                                <span className={`px-2 py-1 text-xs rounded ${
                                  pattern.risk_level === 'critical' ? 'bg-red-500/20 text-red-300' :
                                  pattern.risk_level === 'high' ? 'bg-orange-500/20 text-orange-300' :
                                  pattern.risk_level === 'medium' ? 'bg-yellow-500/20 text-yellow-300' :
                                  'bg-green-500/20 text-green-300'
                                }`}>
                                  {pattern.risk_level}
                                </span>
                              )}
                            </td>
                            <td className="py-3 pr-4 text-sm text-gray-400">
                              {pattern.category || '-'}
                            </td>
                            <td className="py-3 pr-4 text-sm text-gray-300 max-w-[250px] truncate" title={pattern.description}>
                              {pattern.description}
                            </td>
                            <td className="py-3 pr-4">
                              <button
                                onClick={() => handleTogglePatternActive(pattern)}
                                className={`relative w-10 h-5 rounded-full transition-colors ${
                                  pattern.is_active ? 'bg-teal-500' : 'bg-gray-600'
                                }`}
                                title={pattern.is_active ? 'Click to deactivate' : 'Click to activate'}
                              >
                                <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                                  pattern.is_active ? 'left-5' : 'left-0.5'
                                }`} />
                              </button>
                            </td>
                            <td className="py-3">
                              <div className="flex items-center gap-2">
                                {pattern.is_system_default ? (
                                  <span className="text-gray-500" title="System default (cannot edit/delete)"><LockIcon size={14} /></span>
                                ) : (
                                  <>
                                    <button
                                      onClick={() => openEditPattern(pattern)}
                                      className="p-1 text-gray-400 hover:text-white transition-colors"
                                      title="Edit"
                                    >
                                      <EditIcon size={14} />
                                    </button>
                                    <button
                                      onClick={() => setDeleteConfirm({ id: pattern.id, description: pattern.description })}
                                      className="p-1 text-gray-400 hover:text-red-400 transition-colors"
                                      title="Delete"
                                    >
                                      <TrashIcon size={14} />
                                    </button>
                                  </>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="mt-4 text-sm text-gray-500 flex items-center gap-2">
                  <LockIcon size={14} /> = System default pattern (cannot be deleted, only deactivated)
                </div>
              </div>
            )}

            {/* Phase 20: Sentinel Security Tab */}
            {activeTab === 'security' && (
              <div className="space-y-6">
                {/* Sentinel Status Card */}
                <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${
                        sentinelConfig?.is_enabled && sentinelConfig?.enable_shell_analysis
                          ? 'bg-green-500/20'
                          : 'bg-gray-500/20'
                      }`}>
                        <svg className={`w-6 h-6 ${
                          sentinelConfig?.is_enabled && sentinelConfig?.enable_shell_analysis
                            ? 'text-green-400'
                            : 'text-gray-400'
                        }`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold text-white">
                          Sentinel Shell Protection
                        </h3>
                        <p className="text-sm text-gray-400">
                          {sentinelConfig?.is_enabled && sentinelConfig?.enable_shell_analysis
                            ? 'AI-powered intent analysis is active for shell commands'
                            : 'Enable Sentinel to analyze shell command intent'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                        sentinelConfig?.is_enabled && sentinelConfig?.enable_shell_analysis
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-gray-500/20 text-gray-400'
                      }`}>
                        {sentinelConfig?.is_enabled && sentinelConfig?.enable_shell_analysis ? 'Active' : 'Inactive'}
                      </span>
                      <Link
                        href="/settings/sentinel"
                        className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg transition-colors"
                      >
                        Configure
                      </Link>
                    </div>
                  </div>

                  {/* Quick Settings */}
                  {sentinelConfig && (
                    <div className="mt-4 pt-4 border-t border-gray-700">
                      <div className="grid grid-cols-3 gap-4 text-sm">
                        <div>
                          <span className="text-gray-400">Aggressiveness:</span>
                          <span className="ml-2 text-white">
                            {['Off', 'Moderate', 'Aggressive', 'Extra Aggressive'][sentinelConfig.aggressiveness_level]}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-400">Action:</span>
                          <span className="ml-2 text-white">
                            {sentinelConfig.block_on_detection ? 'Block threats' : 'Warn only'}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-400">LLM:</span>
                          <span className="ml-2 text-white">
                            {sentinelConfig.llm_provider}/{sentinelConfig.llm_model?.split('/').pop() || sentinelConfig.llm_model}
                          </span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Shell Security Stats */}
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4">
                    <p className="text-sm text-gray-400">Commands Analyzed</p>
                    <p className="text-2xl font-bold text-white mt-1">
                      {shellSecurityStats?.total_analyses || 0}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">Last 7 days</p>
                  </div>
                  <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4">
                    <p className="text-sm text-gray-400">Threats Detected</p>
                    <p className="text-2xl font-bold text-orange-400 mt-1">
                      {shellSecurityStats?.threats_detected || 0}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">{shellSecurityStats?.detection_rate || 0}% detection rate</p>
                  </div>
                  <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4">
                    <p className="text-sm text-gray-400">Blocked</p>
                    <p className="text-2xl font-bold text-red-400 mt-1">
                      {shellSecurityStats?.threats_blocked || 0}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">Malicious commands stopped</p>
                  </div>
                  <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-4">
                    <p className="text-sm text-gray-400">Protection Rate</p>
                    <p className="text-2xl font-bold text-green-400 mt-1">
                      {shellSecurityStats && shellSecurityStats.threats_detected > 0
                        ? Math.round((shellSecurityStats.threats_blocked / shellSecurityStats.threats_detected) * 100)
                        : 100}%
                    </p>
                    <p className="text-xs text-gray-500 mt-1">Threats mitigated</p>
                  </div>
                </div>

                {/* Recent Shell Security Events */}
                <div className="bg-gray-800/50 border border-gray-700 rounded-xl overflow-hidden">
                  <div className="p-4 border-b border-gray-700 flex items-center justify-between">
                    <h4 className="font-semibold text-white">Recent Shell Security Events</h4>
                    <Link
                      href="/"
                      className="text-sm text-teal-400 hover:text-teal-300"
                    >
                      View all in Watcher
                    </Link>
                  </div>

                  {sentinelLoading ? (
                    <div className="p-8 text-center">
                      <div className="text-gray-400">Loading security events...</div>
                    </div>
                  ) : shellSecurityLogs.length === 0 ? (
                    <div className="p-8 text-center">
                      <p className="text-gray-400">No shell security events recorded.</p>
                      <p className="text-sm text-gray-500 mt-2">
                        {sentinelConfig?.is_enabled && sentinelConfig?.enable_shell_analysis
                          ? 'Commands are being analyzed but no threats detected yet.'
                          : 'Enable Sentinel shell analysis to monitor commands.'}
                      </p>
                    </div>
                  ) : (
                    <div className="divide-y divide-gray-700">
                      {shellSecurityLogs.map((log) => (
                        <div key={log.id} className="p-4 hover:bg-gray-800/30 transition-colors">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <span className={`px-2 py-0.5 text-xs rounded-full border ${
                                log.is_threat_detected
                                  ? 'bg-red-500/20 text-red-400 border-red-500/50'
                                  : 'bg-green-500/20 text-green-400 border-green-500/50'
                              }`}>
                                {log.is_threat_detected ? 'Threat' : 'Safe'}
                              </span>
                              <span className={`px-2 py-0.5 text-xs rounded-full ${
                                log.action_taken === 'blocked'
                                  ? 'bg-red-600 text-white'
                                  : log.action_taken === 'warned'
                                    ? 'bg-yellow-600 text-white'
                                    : 'bg-green-600 text-white'
                              }`}>
                                {log.action_taken}
                              </span>
                              <code className="text-sm text-white font-mono truncate max-w-md">
                                {log.input_content}
                              </code>
                            </div>
                            <div className="text-xs text-gray-500">
                              {new Date(log.created_at).toLocaleString()}
                            </div>
                          </div>
                          <div className="flex items-center gap-4 mt-2 ml-24 text-xs text-gray-500">
                            {log.threat_reason && (
                              <span className="text-orange-400 truncate max-w-md">
                                {log.threat_reason}
                              </span>
                            )}
                            {log.llm_provider && log.llm_model && (
                              <span className="text-cyan-400">
                                Model: {log.llm_provider}/{log.llm_model}
                              </span>
                            )}
                            {log.llm_response_time_ms && (
                              <span>{log.llm_response_time_ms}ms</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Info Box */}
                <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
                  <div className="flex items-start gap-3">
                    <span className="text-xl">💡</span>
                    <div>
                      <h4 className="font-medium text-white">About Sentinel Shell Protection</h4>
                      <p className="text-sm text-gray-400 mt-1">
                        Sentinel uses AI to analyze the <strong>intent</strong> behind shell commands, detecting malicious
                        patterns like data exfiltration, backdoor installation, privilege escalation, and cryptominers.
                        This complements pattern-based blocking with semantic understanding.
                      </p>
                      <p className="text-sm text-gray-400 mt-2">
                        Pattern matching (Patterns tab) catches known dangerous commands instantly, while Sentinel catches
                        novel attack techniques that patterns miss.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Pattern Create/Edit Modal */}
      {showPatternModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowPatternModal(false)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-xl font-bold text-white mb-4">
              {editingPattern ? 'Edit Pattern' : 'Create New Pattern'}
            </h2>
            <form onSubmit={handleSavePattern}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Pattern (Regex)</label>
                  <input
                    type="text"
                    value={patternForm.pattern}
                    onChange={(e) => { setPatternForm({ ...patternForm, pattern: e.target.value }); validatePatternRegex(e.target.value) }}
                    className={`w-full px-4 py-2 bg-gray-800 border rounded-lg text-white font-mono text-sm ${
                      patternError ? 'border-red-500' : 'border-gray-700'
                    }`}
                    placeholder="rm\s+-rf\s+/"
                    required
                    disabled={editingPattern?.is_system_default}
                  />
                  {patternError && <p className="text-xs text-red-400 mt-1">{patternError}</p>}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Type</label>
                    <select
                      value={patternForm.pattern_type}
                      onChange={(e) => setPatternForm({ ...patternForm, pattern_type: e.target.value as 'blocked' | 'high_risk' })}
                      className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
                      disabled={editingPattern?.is_system_default}
                    >
                      <option value="high_risk">High Risk</option>
                      <option value="blocked">Blocked</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Risk Level</label>
                    <select
                      value={patternForm.risk_level}
                      onChange={(e) => setPatternForm({ ...patternForm, risk_level: e.target.value })}
                      className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
                      disabled={editingPattern?.is_system_default || patternForm.pattern_type === 'blocked'}
                    >
                      {RISK_LEVELS.map(level => (
                        <option key={level} value={level}>{level.charAt(0).toUpperCase() + level.slice(1)}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Category</label>
                  <select
                    value={patternForm.category}
                    onChange={(e) => setPatternForm({ ...patternForm, category: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
                    disabled={editingPattern?.is_system_default}
                  >
                    <option value="">Select category...</option>
                    {PATTERN_CATEGORIES.map(cat => (
                      <option key={cat} value={cat}>{cat.charAt(0).toUpperCase() + cat.slice(1)}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm text-gray-400 mb-1">Description</label>
                  <input
                    type="text"
                    value={patternForm.description}
                    onChange={(e) => setPatternForm({ ...patternForm, description: e.target.value })}
                    className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
                    placeholder="Brief description of what this pattern blocks"
                    required
                    disabled={editingPattern?.is_system_default}
                  />
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="patternActive"
                    checked={patternForm.is_active}
                    onChange={(e) => setPatternForm({ ...patternForm, is_active: e.target.checked })}
                    className="w-4 h-4 rounded border-gray-600 text-teal-500 focus:ring-teal-500"
                  />
                  <label htmlFor="patternActive" className="text-sm text-gray-300">Active</label>
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  type="button"
                  onClick={() => { setShowPatternModal(false); setEditingPattern(null) }}
                  className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingPattern || !!patternError || (editingPattern?.is_system_default && !patternForm.is_active !== editingPattern.is_active)}
                  className="flex-1 px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white rounded-lg"
                >
                  {savingPattern ? 'Saving...' : editingPattern ? 'Update' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Pattern Delete Confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setDeleteConfirm(null)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-xl font-bold text-white mb-4">Delete Pattern?</h2>
            <p className="text-gray-400 mb-4">Are you sure you want to delete this pattern?</p>
            <p className="text-sm text-gray-300 bg-gray-800 p-3 rounded mb-6">{deleteConfirm.description}</p>
            <div className="flex gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleDeletePattern}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Pattern Tester Modal */}
      {showPatternTester && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => { setShowPatternTester(false); setTestResults(null) }}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-xl font-bold text-white mb-4 inline-flex items-center gap-2"><BeakerIcon size={20} /> Pattern Tester</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Pattern (Regex)</label>
                <input
                  type="text"
                  value={testPattern}
                  onChange={(e) => setTestPattern(e.target.value)}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white font-mono text-sm"
                  placeholder="rm\s+-rf\s+/"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Test Commands (one per line)</label>
                <textarea
                  value={testCommands.join('\n')}
                  onChange={(e) => setTestCommands(e.target.value.split('\n'))}
                  className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white font-mono text-sm h-32"
                  placeholder="rm -rf /tmp/test&#10;ls -la&#10;chmod 777 /var/www"
                />
              </div>

              <button
                onClick={handleTestPattern}
                disabled={testingPattern || !testPattern}
                className="w-full px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white rounded-lg"
              >
                {testingPattern ? 'Testing...' : 'Test Pattern'}
              </button>

              {testResults && (
                <div className="mt-4">
                  <h3 className="text-lg font-semibold text-white mb-2">Results</h3>
                  {!testResults.is_valid ? (
                    <div className="p-3 bg-red-500/10 border border-red-500/30 rounded text-red-400">
                      Invalid pattern: {testResults.error}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {testResults.matches.map((match, i) => (
                        <div key={i} className={`p-3 rounded ${match.matched ? 'bg-red-500/10 border border-red-500/30' : 'bg-green-500/10 border border-green-500/30'}`}>
                          <code className="font-mono text-sm">{match.command}</code>
                          <span className={`ml-2 text-xs ${match.matched ? 'text-red-400' : 'text-green-400'}`}>
                            {match.matched ? `✗ Matched: "${match.match_text}"` : '✓ No match'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="mt-6">
              <button
                onClick={() => { setShowPatternTester(false); setTestResults(null) }}
                className="w-full px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-bold text-white mb-4">Register New Beacon</h2>
            {newApiKey ? (
              <div>
                <p className="text-green-400 mb-4">✅ Beacon "{newBeaconName}" created successfully!</p>

                {/* API Key Section */}
                <div className="bg-gray-800 p-4 rounded-lg mb-4">
                  <div className="flex justify-between items-center mb-2">
                    <p className="text-sm text-gray-400">API Key (save this - shown only once!):</p>
                    <button
                      onClick={() => { copyToClipboard(newApiKey); setSuccess('API key copied!'); setTimeout(() => setSuccess(null), 2000) }}
                      className="text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded"
                    >
                      📋 Copy
                    </button>
                  </div>
                  <code className="text-teal-400 font-mono text-sm break-all select-all">{newApiKey}</code>
                </div>

                {/* Installation Instructions */}
                <div className="border border-gray-700 rounded-lg p-4 mb-4">
                  <h3 className="text-lg font-semibold text-white mb-3">📥 Installation Instructions</h3>

                  {/* Option 1: Download & Run */}
                  <div className="mb-4">
                    <p className="text-sm text-gray-400 mb-2">Option 1: Download beacon package</p>
                    <a
                      href={`${apiUrl}/api/shell/beacon/download`}
                      className="inline-flex items-center gap-2 px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm"
                    >
                      ⬇️ Download Beacon Package
                    </a>
                  </div>

                  {/* Option 2: One-liner install */}
                  <div className="mb-4">
                    <p className="text-sm text-gray-400 mb-2">Option 2: Quick install (copy & paste in target terminal):</p>
                    <div className="relative">
                      <pre className="bg-gray-950 p-3 rounded text-xs font-mono text-green-400 overflow-x-auto whitespace-pre-wrap">
{`# Download and install beacon
curl -L "${apiUrl}/api/shell/beacon/download" -o beacon.zip && \\
unzip beacon.zip && \\
cd shell_beacon && \\
pip install -r requirements.txt

# Run beacon with auto-start persistence (survives reboots)
python run.py \\
  --server "${apiUrl}/api/shell" \\
  --api-key "${newApiKey}" \\
  --persistence install`}
                      </pre>
                      <button
                        onClick={() => {
                          const cmd = `# Download and install beacon
curl -L "${apiUrl}/api/shell/beacon/download" -o beacon.zip && \\
unzip beacon.zip && \\
cd shell_beacon && \\
pip install -r requirements.txt

# Run beacon with auto-start persistence (survives reboots)
python run.py \\
  --server "${apiUrl}/api/shell" \\
  --api-key "${newApiKey}" \\
  --persistence install`;
                          copyToClipboard(cmd);
                          setSuccess('Install script copied!');
                          setTimeout(() => setSuccess(null), 2000);
                        }}
                        className="absolute top-2 right-2 text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded"
                      >
                        📋 Copy
                      </button>
                    </div>
                  </div>

                  {/* Option 3: Run command only */}
                  <div className="mb-4">
                    <p className="text-sm text-gray-400 mb-2">Option 3: If beacon is already installed:</p>
                    <div className="relative">
                      <pre className="bg-gray-950 p-3 rounded text-xs font-mono text-green-400 overflow-x-auto">
{`# From INSIDE shell_beacon/ directory (with persistence)
cd shell_beacon
python run.py --server "${apiUrl}/api/shell" --api-key "${newApiKey}" --persistence install

# OR without persistence (manual start required after reboot)
python run.py --server "${apiUrl}/api/shell" --api-key "${newApiKey}"

# Persistence management commands:
python run.py --persistence status    # Check if persistence is installed
python run.py --persistence uninstall # Remove auto-start`}
                      </pre>
                      <button
                        onClick={() => {
                          copyToClipboard(`cd shell_beacon && python run.py --server "${apiUrl}/api/shell" --api-key "${newApiKey}" --persistence install`);
                          setSuccess('Run command copied!');
                          setTimeout(() => setSuccess(null), 2000);
                        }}
                        className="absolute top-2 right-2 text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded"
                      >
                        📋 Copy
                      </button>
                    </div>
                    <p className="text-xs text-teal-400 mt-2">💡 <code>--persistence install</code> auto-starts the beacon on login/reboot (Linux: systemd, macOS: LaunchAgent, Windows: Task Scheduler)</p>
                  </div>
                </div>

                {/* Config file option */}
                <details className="border border-gray-700 rounded-lg p-4 mb-4">
                  <summary className="text-sm font-medium text-gray-300 cursor-pointer hover:text-white">
                    📄 Advanced: Use config file (beacon.yaml)
                  </summary>
                  <div className="mt-3">
                    <p className="text-xs text-gray-400 mb-2">Save this as <code className="text-teal-400">~/.tsushin/beacon.yaml</code>:</p>
                    <div className="relative">
                      <pre className="bg-gray-950 p-3 rounded text-xs font-mono text-yellow-400 overflow-x-auto">
{`# Tsushin Beacon Configuration
server:
  url: "${apiUrl}/api/shell"
  api_key: "${newApiKey}"

connection:
  poll_interval: 5
  reconnect_delay: 5
  max_reconnect_delay: 300

execution:
  shell: "/bin/bash"
  timeout: 300

logging:
  level: "INFO"
  file: "~/.tsushin/beacon.log"`}
                      </pre>
                      <button
                        onClick={() => {
                          const cfg = `# Tsushin Beacon Configuration
server:
  url: "${apiUrl}/api/shell"
  api_key: "${newApiKey}"

connection:
  poll_interval: 5
  reconnect_delay: 5
  max_reconnect_delay: 300

execution:
  shell: "/bin/bash"
  timeout: 300

logging:
  level: "INFO"
  file: "~/.tsushin/beacon.log"`;
                          copyToClipboard(cfg);
                          setSuccess('Config copied!');
                          setTimeout(() => setSuccess(null), 2000);
                        }}
                        className="absolute top-2 right-2 text-xs px-2 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded"
                      >
                        📋 Copy
                      </button>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">Then run: <code className="text-teal-400">python -m shell_beacon</code></p>
                  </div>
                </details>

                <button
                  onClick={() => { setShowCreateModal(false); setNewApiKey(null); setNewBeaconName('') }}
                  className="w-full px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-medium"
                >
                  Done
                </button>
              </div>
            ) : (
              <div>
                <input
                  type="text"
                  value={newBeaconName}
                  onChange={(e) => setNewBeaconName(e.target.value)}
                  placeholder="Beacon name (e.g., production-server)"
                  className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white mb-4"
                />
                <div className="flex gap-3">
                  <button
                    onClick={() => { setShowCreateModal(false); setNewBeaconName('') }}
                    className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreateBeacon}
                    disabled={creating || !newBeaconName.trim()}
                    className="flex-1 px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white rounded-lg"
                  >
                    {creating ? 'Creating...' : 'Create'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
