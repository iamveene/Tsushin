'use client'

/**
 * Sandboxed Tools Management Page
 *
 * Full management interface for sandboxed tools:
 * - Toolbox container status and controls
 * - Create/edit/delete sandboxed tools
 * - Package installation
 * - Execution history
 * - Commit to image
 */

import { useEffect, useState, useCallback } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import Modal from '@/components/ui/Modal'
import Link from 'next/link'
import {
  StopIcon,
  RefreshIcon,
  SaveIcon,
  WrenchIcon,
  PackageIcon,
  LightningIcon,
} from '@/components/ui/icons'

type SubTabType = 'tools' | 'packages' | 'executions'

interface ContainerStatus {
  tenant_id: string
  container_name: string
  status: string
  container_id: string | null
  image: string | null
  created_at: string | null
  started_at: string | null
  health: string
  error: string | null
}

// Local interfaces for sandboxed tools (formerly CustomTool - Skills-as-Tools Phase 6)
interface SandboxedTool {
  id: number
  tenant_id: string
  name: string
  tool_type: string
  system_prompt: string
  workspace_dir: string | null
  execution_mode: string
  is_enabled: boolean
  created_at: string
  updated_at: string
  commands?: SandboxedToolCommand[]
}

interface SandboxedToolCommand {
  id: number
  tool_id: number
  command_name: string
  command_template: string
  is_long_running: boolean
  timeout_seconds: number
}

// Backward compatibility aliases
type CustomTool = SandboxedTool
type CustomToolCommand = SandboxedToolCommand

interface InstalledPackage {
  id: number
  package_name: string
  package_type: string
  version: string | null
  installed_at: string | null
  is_committed: boolean
}

interface AvailableTool {
  name: string
  description: string
  commands: string[]
}

const PRE_INSTALLED_TOOLS: AvailableTool[] = [
  {
    name: "nmap",
    description: "Network exploration and security auditing",
    commands: ["nmap -sV <target>", "nmap -sn <network>", "nmap -A <target>"]
  },
  {
    name: "nuclei",
    description: "Fast vulnerability scanner based on templates",
    commands: ["nuclei -u <url>", "nuclei -l urls.txt", "nuclei -u <url> -t cves/"]
  },
  {
    name: "katana",
    description: "Fast web crawler for gathering endpoints",
    commands: ["katana -u <url>", "katana -u <url> -d 3"]
  },
  {
    name: "httpx",
    description: "HTTP toolkit for probing web servers",
    commands: ["httpx -u <url>", "httpx -l urls.txt -sc"]
  },
  {
    name: "subfinder",
    description: "Subdomain discovery tool",
    commands: ["subfinder -d <domain>", "subfinder -dL domains.txt"]
  },
  {
    name: "python",
    description: "Python 3.11 interpreter with common packages",
    commands: ["python script.py", "python -c '<code>'"]
  }
]

export default function CustomToolsPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<SubTabType>('tools')

  // Container state
  const [containerStatus, setContainerStatus] = useState<ContainerStatus | null>(null)
  const [containerLoading, setContainerLoading] = useState(false)

  // Tools state
  const [tools, setTools] = useState<CustomTool[]>([])
  const [toolsLoading, setToolsLoading] = useState(true)

  // Packages state
  const [packages, setPackages] = useState<InstalledPackage[]>([])
  const [packagesLoading, setPackagesLoading] = useState(false)

  // UI state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showInstallModal, setShowInstallModal] = useState(false)
  const [editingTool, setEditingTool] = useState<CustomTool | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [isPolling, setIsPolling] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  // Form state
  interface CommandForm {
    command_name: string
    command_template: string
    timeout_seconds: number
    is_long_running: boolean
    parameters: {
      parameter_name: string
      is_mandatory: boolean
      default_value: string
      description: string
    }[]
  }

  const [toolForm, setToolForm] = useState<{
    name: string
    tool_type: string
    system_prompt: string
    execution_mode: string
    is_enabled: boolean
    commands: CommandForm[]
  }>({
    name: '',
    tool_type: 'command',
    system_prompt: '',
    execution_mode: 'container',
    is_enabled: true,
    commands: []
  })
  const [packageForm, setPackageForm] = useState({
    package_name: '',
    package_type: 'pip'
  })

  // Helper functions for managing commands in toolForm
  const addCommand = () => {
    setToolForm({
      ...toolForm,
      commands: [
        ...toolForm.commands,
        {
          command_name: '',
          command_template: '',
          timeout_seconds: 60,
          is_long_running: false,
          parameters: []
        }
      ]
    })
  }

  const removeCommand = (index: number) => {
    setToolForm({
      ...toolForm,
      commands: toolForm.commands.filter((_, i) => i !== index)
    })
  }

  const updateCommand = (index: number, field: string, value: any) => {
    const updatedCommands = [...toolForm.commands]
    updatedCommands[index] = { ...updatedCommands[index], [field]: value }
    setToolForm({ ...toolForm, commands: updatedCommands })
  }

  const addParameter = (commandIndex: number) => {
    const updatedCommands = [...toolForm.commands]
    updatedCommands[commandIndex].parameters.push({
      parameter_name: '',
      is_mandatory: false,
      default_value: '',
      description: ''
    })
    setToolForm({ ...toolForm, commands: updatedCommands })
  }

  const removeParameter = (commandIndex: number, paramIndex: number) => {
    const updatedCommands = [...toolForm.commands]
    updatedCommands[commandIndex].parameters = updatedCommands[commandIndex].parameters.filter((_, i) => i !== paramIndex)
    setToolForm({ ...toolForm, commands: updatedCommands })
  }

  const updateParameter = (commandIndex: number, paramIndex: number, field: string, value: any) => {
    const updatedCommands = [...toolForm.commands]
    updatedCommands[commandIndex].parameters[paramIndex] = {
      ...updatedCommands[commandIndex].parameters[paramIndex],
      [field]: value
    }
    setToolForm({ ...toolForm, commands: updatedCommands })
  }

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

  // Auto-refresh container status every 15 seconds when page is visible
  useEffect(() => {
    loadContainerStatus()
    loadTools()
    loadPackages()

    // Set up periodic polling for container status
    const pollInterval = setInterval(() => {
      // Only poll if not already polling and document is visible
      if (!isPolling && document.visibilityState === 'visible') {
        loadContainerStatus()
      }
    }, 15000) // Poll every 15 seconds

    // Refresh when page becomes visible again
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        loadContainerStatus()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      clearInterval(pollInterval)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [isPolling])

  // Listen for global refresh events
  useEffect(() => {
    const handleRefresh = () => {
      loadContainerStatus()
      loadTools()
      loadPackages()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [])

  const loadContainerStatus = async (showRefreshing = false) => {
    if (showRefreshing) setIsRefreshing(true)
    try {
      const response = await fetch(`${apiUrl}/api/toolbox/status`, {
        headers: getAuthHeaders()
      })
      if (response.ok) {
        const data = await response.json()
        setContainerStatus(data)
        setLastRefresh(new Date())
      }
    } catch (err) {
      console.error('Failed to load container status:', err)
    } finally {
      if (showRefreshing) setIsRefreshing(false)
    }
  }

  // Poll container status after actions to wait for state to stabilize
  // Uses faster polling (1s) for first attempts, then slows down
  const pollContainerStatus = async (pollCount = 10, fastPollCount = 5) => {
    setIsPolling(true)
    for (let i = 0; i < pollCount; i++) {
      // Fast polling for first attempts (1s), then slow down (3s)
      const intervalMs = i < fastPollCount ? 1000 : 3000
      await new Promise(r => setTimeout(r, intervalMs))
      await loadContainerStatus()
    }
    setIsPolling(false)
  }

  // Manual refresh handler
  const handleManualRefresh = async () => {
    await loadContainerStatus(true)
  }

  const loadTools = async () => {
    setToolsLoading(true)
    try {
      const response = await fetch(`${apiUrl}/api/custom-tools/`, {
        headers: getAuthHeaders()
      })
      if (response.ok) {
        const data = await response.json()
        // Fetch commands for each tool
        const toolsWithCommands = await Promise.all(
          data.map(async (tool: CustomTool) => {
            try {
              const cmdResponse = await fetch(`${apiUrl}/api/custom-tools/${tool.id}/commands`, {
                headers: getAuthHeaders()
              })
              if (cmdResponse.ok) {
                const commands = await cmdResponse.json()
                return { ...tool, commands }
              }
            } catch (err) {
              console.error(`Failed to load commands for tool ${tool.id}:`, err)
            }
            return tool
          })
        )
        setTools(toolsWithCommands)
      }
    } catch (err) {
      console.error('Failed to load tools:', err)
    } finally {
      setToolsLoading(false)
    }
  }

  const loadPackages = async () => {
    setPackagesLoading(true)
    try {
      const response = await fetch(`${apiUrl}/api/toolbox/packages`, {
        headers: getAuthHeaders()
      })
      if (response.ok) {
        const data = await response.json()
        setPackages(data)
      }
    } catch (err) {
      console.error('Failed to load packages:', err)
    } finally {
      setPackagesLoading(false)
    }
  }

  const getAuthHeaders = () => {
    const token = localStorage.getItem('tsushin_auth_token')
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }

  // Container actions
  const handleContainerAction = async (action: 'start' | 'stop' | 'restart') => {
    setContainerLoading(true)
    setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/toolbox/${action}`, {
        method: 'POST',
        headers: getAuthHeaders()
      })
      if (response.ok) {
        const data = await response.json()
        setContainerStatus(data)
        setSuccess(`Container ${action}ed successfully`)
        setTimeout(() => setSuccess(null), 3000)
        // Poll to ensure status stabilizes after action
        // Fast polling for 5 attempts, then slower for 5 more
        pollContainerStatus(10, 5)
      } else {
        const error = await response.json()
        setError(error.detail || `Failed to ${action} container`)
      }
    } catch (err: any) {
      setError(err.message || `Failed to ${action} container`)
    } finally {
      setContainerLoading(false)
    }
  }

  const handleCommit = async () => {
    if (!confirm('Commit current container state to image? This will persist all installed packages.')) return

    setContainerLoading(true)
    setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/toolbox/commit`, {
        method: 'POST',
        headers: getAuthHeaders()
      })
      if (response.ok) {
        setSuccess('Container committed to image successfully')
        loadContainerStatus()
        loadPackages()
        setTimeout(() => setSuccess(null), 3000)
      } else {
        const error = await response.json()
        setError(error.detail || 'Failed to commit container')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to commit container')
    } finally {
      setContainerLoading(false)
    }
  }

  const handleReset = async () => {
    if (!confirm('Reset container to base image? This will remove all installed packages.')) return

    setContainerLoading(true)
    setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/toolbox/reset`, {
        method: 'POST',
        headers: getAuthHeaders()
      })
      if (response.ok) {
        setSuccess('Container reset to base image')
        loadContainerStatus()
        loadPackages()
        setTimeout(() => setSuccess(null), 3000)
      } else {
        const error = await response.json()
        setError(error.detail || 'Failed to reset container')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to reset container')
    } finally {
      setContainerLoading(false)
    }
  }

  // Package installation
  const handleInstallPackage = async () => {
    if (!packageForm.package_name.trim()) {
      setError('Package name is required')
      return
    }

    setSaving(true)
    setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/toolbox/packages/install`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(packageForm)
      })
      if (response.ok) {
        setSuccess(`Package '${packageForm.package_name}' installed successfully`)
        setShowInstallModal(false)
        setPackageForm({ package_name: '', package_type: 'pip' })
        loadPackages()
        setTimeout(() => setSuccess(null), 3000)
      } else {
        const error = await response.json()
        setError(error.detail || 'Failed to install package')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to install package')
    } finally {
      setSaving(false)
    }
  }

  // Tool CRUD
  const handleCreateTool = async () => {
    if (!toolForm.name.trim() || !toolForm.system_prompt.trim()) {
      setError('Name and system prompt are required')
      return
    }

    setSaving(true)
    setError(null)
    try {
      // Step 1: Create the tool
      const response = await fetch(`${apiUrl}/api/custom-tools/`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          name: toolForm.name,
          tool_type: toolForm.tool_type,
          system_prompt: toolForm.system_prompt,
          execution_mode: toolForm.execution_mode,
          is_enabled: toolForm.is_enabled
        })
      })

      if (!response.ok) {
        const error = await response.json()
        setError(error.detail || 'Failed to create tool')
        return
      }

      const createdTool = await response.json()

      // Step 2: Create commands and parameters
      for (const cmd of toolForm.commands) {
        const cmdResponse = await fetch(`${apiUrl}/api/custom-tools/commands/`, {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            tool_id: createdTool.id,
            command_name: cmd.command_name,
            command_template: cmd.command_template,
            is_long_running: cmd.is_long_running,
            timeout_seconds: cmd.timeout_seconds
          })
        })

        if (cmdResponse.ok) {
          const createdCommand = await cmdResponse.json()

          // Create parameters for this command
          for (const param of cmd.parameters) {
            await fetch(`${apiUrl}/api/custom-tools/parameters/`, {
              method: 'POST',
              headers: getAuthHeaders(),
              body: JSON.stringify({
                command_id: createdCommand.id,
                parameter_name: param.parameter_name,
                is_mandatory: param.is_mandatory,
                default_value: param.default_value || null,
                description: param.description || null
              })
            })
          }
        }
      }

      setSuccess('Tool created successfully')
      setShowCreateModal(false)
      setToolForm({ name: '', tool_type: 'command', system_prompt: '', execution_mode: 'container', is_enabled: true, commands: [] })
      loadTools()
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to create tool')
    } finally {
      setSaving(false)
    }
  }

  const handleToggleTool = async (tool: CustomTool) => {
    try {
      const response = await fetch(`${apiUrl}/api/custom-tools/${tool.id}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({ ...tool, is_enabled: !tool.is_enabled })
      })
      if (response.ok) {
        loadTools()
      }
    } catch (err) {
      console.error('Failed to toggle tool:', err)
    }
  }

  const handleDeleteTool = async (toolId: number) => {
    if (!confirm('Delete this tool?')) return

    try {
      const response = await fetch(`${apiUrl}/api/custom-tools/${toolId}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      })
      if (response.ok) {
        setSuccess('Tool deleted')
        loadTools()
        setTimeout(() => setSuccess(null), 3000)
      }
    } catch (err) {
      console.error('Failed to delete tool:', err)
    }
  }

  const handleEditTool = async () => {
    if (!editingTool) return

    setSaving(true)
    setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/custom-tools/${editingTool.id}`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          name: editingTool.name,
          tool_type: editingTool.tool_type,
          system_prompt: editingTool.system_prompt,
          is_enabled: editingTool.is_enabled
        })
      })
      if (response.ok) {
        setSuccess('Tool updated successfully')
        setEditingTool(null)
        loadTools()
        setTimeout(() => setSuccess(null), 3000)
      } else {
        const error = await response.json()
        setError(error.detail || 'Failed to update tool')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to update tool')
    } finally {
      setSaving(false)
    }
  }

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      running: 'bg-green-500/20 text-green-400 border-green-500/50',
      stopped: 'bg-gray-500/20 text-gray-400 border-gray-500/50',
      not_created: 'bg-gray-500/20 text-gray-400 border-gray-500/50',
      error: 'bg-red-500/20 text-red-400 border-red-500/50',
    }
    return `px-2 py-1 text-xs font-medium border rounded-full ${colors[status] || colors.stopped}`
  }

  return (
    <div className="min-h-screen animate-fade-in">
      {/* Header */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6 flex items-center gap-4">
          <Link href="/hub" className="text-tsushin-slate hover:text-white transition-colors">
            ← Back to Hub
          </Link>
        </div>
        <div className="flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-display font-bold text-white mb-2">Sandboxed Tools</h1>
            <p className="text-tsushin-slate">Manage command-based tools and toolbox container</p>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
        {/* Alerts */}
        {success && (
          <div className="p-4 bg-tsushin-success/10 border border-tsushin-success/30 rounded-xl text-tsushin-success flex justify-between items-center animate-fade-in-down">
            <span className="flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              {success}
            </span>
            <button onClick={() => setSuccess(null)} className="text-tsushin-success/80 hover:text-tsushin-success">×</button>
          </div>
        )}
        {error && (
          <div className="p-4 bg-tsushin-vermilion/10 border border-tsushin-vermilion/30 rounded-xl text-tsushin-vermilion flex justify-between items-center animate-fade-in-down">
            <span className="flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {error}
            </span>
            <button onClick={() => setError(null)} className="text-tsushin-vermilion/80 hover:text-tsushin-vermilion">×</button>
          </div>
        )}

        {/* Toolbox Container Status */}
        <div className="glass-card rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-xl bg-purple-500/10 flex items-center justify-center">
                <svg className="w-8 h-8 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></svg>
              </div>
              <div>
                <h2 className="text-xl font-display font-semibold text-white">Toolbox Container</h2>
                <p className="text-sm text-tsushin-slate">
                  {containerStatus?.container_name || 'Not created'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className={getStatusBadge(containerStatus?.status || 'not_created')}>
                {isPolling ? 'Updating...' : (containerStatus?.status || 'Not Created')}
              </span>
              {lastRefresh && !isPolling && (
                <span className="text-xs text-tsushin-slate" title={lastRefresh.toLocaleString()}>
                  Updated {lastRefresh.toLocaleTimeString()}
                </span>
              )}
              <button
                onClick={handleManualRefresh}
                disabled={isRefreshing || isPolling}
                className="p-2 text-tsushin-slate hover:text-white rounded-lg transition-colors disabled:opacity-50"
                title="Refresh status"
              >
                <svg
                  className={`w-5 h-5 ${(isRefreshing || isPolling) ? 'animate-spin' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-tsushin-deep/50 px-4 py-3 rounded-lg">
              <p className="text-xs text-tsushin-slate mb-1">Image</p>
              <p className="text-sm text-white font-mono">{containerStatus?.image || '-'}</p>
            </div>
            <div className="bg-tsushin-deep/50 px-4 py-3 rounded-lg">
              <p className="text-xs text-tsushin-slate mb-1">Health</p>
              <p className="text-sm text-white">{containerStatus?.health || '-'}</p>
            </div>
            <div className="bg-tsushin-deep/50 px-4 py-3 rounded-lg">
              <p className="text-xs text-tsushin-slate mb-1">Started At</p>
              <p className="text-sm text-white">
                {containerStatus?.started_at ? new Date(containerStatus.started_at).toLocaleString() : '-'}
              </p>
            </div>
            <div className="bg-tsushin-deep/50 px-4 py-3 rounded-lg">
              <p className="text-xs text-tsushin-slate mb-1">Container ID</p>
              <p className="text-sm text-white font-mono">{containerStatus?.container_id?.slice(0, 12) || '-'}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {containerStatus?.status === 'running' ? (
              <>
                <button
                  onClick={() => handleContainerAction('stop')}
                  disabled={containerLoading || isPolling}
                  className="btn-ghost py-2 px-4 text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/10 disabled:opacity-50 flex items-center gap-1.5"
                >
                  <StopIcon size={14} /> Stop
                </button>
                <button
                  onClick={() => handleContainerAction('restart')}
                  disabled={containerLoading || isPolling}
                  className="btn-ghost py-2 px-4 text-blue-400 border-blue-500/30 hover:bg-blue-500/10 disabled:opacity-50 flex items-center gap-1.5"
                >
                  <RefreshIcon size={14} /> Restart
                </button>
              </>
            ) : (
              <button
                onClick={() => handleContainerAction('start')}
                disabled={containerLoading || isPolling}
                className="btn-primary py-2 px-4 disabled:opacity-50"
              >
                {isPolling ? 'Starting...' : 'Start Container'}
              </button>
            )}
            <button
              onClick={handleCommit}
              disabled={containerLoading || isPolling || containerStatus?.status !== 'running'}
              className="btn-ghost py-2 px-4 text-purple-400 border-purple-500/30 hover:bg-purple-500/10 disabled:opacity-50 flex items-center gap-1.5"
            >
              <SaveIcon size={14} /> Commit to Image
            </button>
            <button
              onClick={handleReset}
              disabled={containerLoading || isPolling}
              className="btn-ghost py-2 px-4 text-red-400 border-red-500/30 hover:bg-red-500/10 disabled:opacity-50 flex items-center gap-1.5"
            >
              <RefreshIcon size={14} /> Reset to Base
            </button>
          </div>
        </div>

        {/* Sub-Tabs */}
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="border-b border-tsushin-border/50">
            <nav className="flex">
              {[
                { key: 'tools', label: 'Tools', Icon: WrenchIcon },
                { key: 'packages', label: 'Packages', Icon: PackageIcon },
                { key: 'executions', label: 'Pre-installed', Icon: LightningIcon },
              ].map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key as SubTabType)}
                  className={`relative px-6 py-4 font-medium text-sm transition-all duration-200 flex items-center gap-2 ${activeTab === tab.key
                      ? 'text-white'
                      : 'text-tsushin-slate hover:text-white'
                    }`}
                >
                  <tab.Icon size={16} />
                  <span>{tab.label}</span>
                  {activeTab === tab.key && (
                    <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-purple-500 to-pink-400" />
                  )}
                </button>
              ))}
            </nav>
          </div>

          <div className="p-6">
            {/* Tools Tab */}
            {activeTab === 'tools' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="text-lg font-semibold text-white">Sandboxed Tools</h3>
                    <p className="text-sm text-tsushin-slate">Tools agents can use for command execution</p>
                  </div>
                  <button
                    onClick={() => setShowCreateModal(true)}
                    className="btn-primary"
                  >
                    + Create Tool
                  </button>
                </div>

                {toolsLoading ? (
                  <div className="text-center py-8">
                    <div className="w-8 h-8 border-4 border-tsushin-indigo border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                    <p className="text-tsushin-slate">Loading tools...</p>
                  </div>
                ) : tools.length === 0 ? (
                  <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                    <WrenchIcon size={48} className="mx-auto mb-4 text-teal-400" />
                    <h3 className="text-lg font-semibold text-white mb-2">No Sandboxed Tools</h3>
                    <p className="text-tsushin-slate mb-4">Create your first tool to get started</p>
                    <button
                      onClick={() => setShowCreateModal(true)}
                      className="btn-primary"
                    >
                      Create Tool
                    </button>
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {tools.map(tool => (
                      <div key={tool.id} className="card p-5 hover-glow group">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-teal-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                              <WrenchIcon size={20} className="text-teal-400" />
                            </div>
                            <h4 className="font-semibold text-white">{tool.name}</h4>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer">
                            <input
                              type="checkbox"
                              checked={tool.is_enabled}
                              onChange={() => handleToggleTool(tool)}
                              className="sr-only peer"
                            />
                            <div className="w-9 h-5 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-teal-500"></div>
                          </label>
                        </div>
                        <p className="text-xs text-tsushin-slate mb-3 line-clamp-2">{tool.system_prompt}</p>
                        <div className="flex gap-2">
                          <span className="px-2 py-1 text-xs bg-tsushin-deep rounded">{tool.tool_type}</span>
                          <span className="px-2 py-1 text-xs bg-blue-900/50 text-blue-400 rounded">Isolated</span>
                        </div>
                        <div className="flex gap-2 mt-3">
                          <button
                            onClick={() => setEditingTool(tool)}
                            className="flex-1 btn-ghost py-1.5 text-xs"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeleteTool(tool.id)}
                            className="flex-1 py-1.5 text-xs rounded-lg bg-red-500/10 text-red-400 border border-red-500/30 hover:bg-red-500/20"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Packages Tab */}
            {activeTab === 'packages' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="text-lg font-semibold text-white">Installed Packages</h3>
                    <p className="text-sm text-tsushin-slate">Additional packages installed in your toolbox</p>
                  </div>
                  <button
                    onClick={() => setShowInstallModal(true)}
                    className="btn-primary"
                  >
                    + Install Package
                  </button>
                </div>

                {packagesLoading ? (
                  <div className="text-center py-8">
                    <div className="w-8 h-8 border-4 border-tsushin-indigo border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                    <p className="text-tsushin-slate">Loading packages...</p>
                  </div>
                ) : packages.length === 0 ? (
                  <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                    <PackageIcon size={48} className="mx-auto mb-4 text-teal-400" />
                    <h3 className="text-lg font-semibold text-white mb-2">No Additional Packages</h3>
                    <p className="text-tsushin-slate mb-4">Install pip or apt packages to extend your toolbox</p>
                    <button
                      onClick={() => setShowInstallModal(true)}
                      className="btn-primary"
                    >
                      Install Package
                    </button>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="text-left text-xs text-tsushin-slate border-b border-tsushin-border">
                          <th className="pb-3 font-medium">Package</th>
                          <th className="pb-3 font-medium">Type</th>
                          <th className="pb-3 font-medium">Installed</th>
                          <th className="pb-3 font-medium">Committed</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-tsushin-border/50">
                        {packages.map(pkg => (
                          <tr key={pkg.id} className="text-sm">
                            <td className="py-3 text-white font-medium">{pkg.package_name}</td>
                            <td className="py-3">
                              <span className={`px-2 py-1 text-xs rounded ${pkg.package_type === 'pip' ? 'bg-blue-500/10 text-blue-400' : 'bg-orange-500/10 text-orange-400'
                                }`}>
                                {pkg.package_type}
                              </span>
                            </td>
                            <td className="py-3 text-tsushin-slate">
                              {pkg.installed_at ? new Date(pkg.installed_at).toLocaleDateString() : '-'}
                            </td>
                            <td className="py-3">
                              {pkg.is_committed ? (
                                <span className="text-green-400 inline-flex items-center gap-1"><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><polyline points="20 6 9 17 4 12" /></svg> Yes</span>
                              ) : (
                                <span className="text-yellow-400 inline-flex items-center gap-1"><svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg> Pending</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="bg-purple-500/5 border border-purple-500/20 rounded-xl p-4">
                  <p className="text-xs text-tsushin-slate">
                    <strong className="text-purple-300">Tip:</strong> Packages marked "Pending" will be lost when the container restarts.
                    Click "Commit to Image" above to persist all installed packages.
                  </p>
                </div>
              </div>
            )}

            {/* Pre-installed Tools Tab */}
            {activeTab === 'executions' && (
              <div className="space-y-6 animate-fade-in">
                <div>
                  <h3 className="text-lg font-semibold text-white">Pre-installed Tools</h3>
                  <p className="text-sm text-tsushin-slate">Tools available in the base toolbox image</p>
                </div>

                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {PRE_INSTALLED_TOOLS.map(tool => (
                    <div key={tool.name} className="card p-5 hover-glow group">
                      <div className="flex items-center gap-3 mb-3">
                        <div className="w-10 h-10 rounded-xl bg-teal-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                          <LightningIcon size={20} className="text-teal-400" />
                        </div>
                        <h4 className="font-semibold text-white">{tool.name}</h4>
                      </div>
                      <p className="text-xs text-tsushin-slate mb-3">{tool.description}</p>
                      <div className="space-y-1">
                        {tool.commands.map((cmd, i) => (
                          <code key={i} className="block text-xs bg-tsushin-deep px-2 py-1 rounded font-mono text-tsushin-accent">
                            {cmd}
                          </code>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Create Tool Modal */}
      <Modal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Custom Tool"
        size="lg"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowCreateModal(false)}
              className="btn-ghost"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              onClick={handleCreateTool}
              className="btn-primary"
              disabled={saving}
            >
              {saving ? 'Creating...' : 'Create Tool'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Tool Name</label>
            <input
              type="text"
              value={toolForm.name}
              onChange={(e) => setToolForm({ ...toolForm, name: e.target.value })}
              placeholder="e.g., my_scanner"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Tool Type</label>
            <select
              value={toolForm.tool_type}
              onChange={(e) => setToolForm({ ...toolForm, tool_type: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
            >
              <option value="command">Command (shell)</option>
            </select>
          </div>
          <div className="bg-blue-900/20 border border-blue-800 rounded-lg p-3">
            <div className="flex items-center gap-2 text-blue-400 text-sm">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>All tools execute in isolated containers for security</span>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">System Prompt</label>
            <textarea
              value={toolForm.system_prompt}
              onChange={(e) => setToolForm({ ...toolForm, system_prompt: e.target.value })}
              placeholder="Describe what this tool does and when to use it..."
              rows={4}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white resize-none"
            />
          </div>
          <label className="flex items-center">
            <input
              type="checkbox"
              checked={toolForm.is_enabled}
              onChange={(e) => setToolForm({ ...toolForm, is_enabled: e.target.checked })}
              className="mr-2"
            />
            <span className="text-sm text-gray-300">Enable this tool</span>
          </label>

          {/* Commands Section */}
          <div className="border-t border-gray-700 pt-4 mt-4">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-medium text-gray-300">Commands</h4>
              <button
                type="button"
                onClick={addCommand}
                className="text-xs px-2 py-1 bg-teal-500/20 text-teal-400 rounded hover:bg-teal-500/30"
              >
                + Add Command
              </button>
            </div>

            {toolForm.commands.length === 0 ? (
              <p className="text-xs text-gray-500 text-center py-4 border border-dashed border-gray-700 rounded">
                No commands added yet. Add a command to define what this tool can do.
              </p>
            ) : (
              <div className="space-y-4">
                {toolForm.commands.map((cmd, cmdIndex) => (
                  <div key={cmdIndex} className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <span className="text-sm font-medium text-white">Command {cmdIndex + 1}</span>
                      <button
                        type="button"
                        onClick={() => removeCommand(cmdIndex)}
                        className="text-xs text-red-400 hover:text-red-300"
                      >
                        Remove
                      </button>
                    </div>

                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">Command Name</label>
                        <input
                          type="text"
                          value={cmd.command_name}
                          onChange={(e) => updateCommand(cmdIndex, 'command_name', e.target.value)}
                          placeholder="e.g., scan_url"
                          className="w-full px-2 py-1.5 text-sm bg-gray-900 border border-gray-600 rounded text-white"
                        />
                      </div>

                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Command Template <span className="text-gray-500">(use {'{param}'} for parameters)</span>
                        </label>
                        <input
                          type="text"
                          value={cmd.command_template}
                          onChange={(e) => updateCommand(cmdIndex, 'command_template', e.target.value)}
                          placeholder="e.g., nmap -sV {target}"
                          className="w-full px-2 py-1.5 text-sm bg-gray-900 border border-gray-600 rounded text-white font-mono"
                        />
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block text-xs text-gray-400 mb-1">Timeout (seconds)</label>
                          <input
                            type="number"
                            value={cmd.timeout_seconds}
                            onChange={(e) => updateCommand(cmdIndex, 'timeout_seconds', parseInt(e.target.value) || 60)}
                            className="w-full px-2 py-1.5 text-sm bg-gray-900 border border-gray-600 rounded text-white"
                          />
                        </div>
                        <div className="flex items-center">
                          <label className="flex items-center text-xs text-gray-400 mt-4">
                            <input
                              type="checkbox"
                              checked={cmd.is_long_running}
                              onChange={(e) => updateCommand(cmdIndex, 'is_long_running', e.target.checked)}
                              className="mr-2"
                            />
                            Long-running command
                          </label>
                        </div>
                      </div>

                      {/* Parameters */}
                      <div className="border-t border-gray-700 pt-3 mt-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-xs font-medium text-gray-400">Parameters</span>
                          <button
                            type="button"
                            onClick={() => addParameter(cmdIndex)}
                            className="text-xs px-2 py-0.5 bg-blue-500/20 text-blue-400 rounded hover:bg-blue-500/30"
                          >
                            + Add
                          </button>
                        </div>

                        {cmd.parameters.length === 0 ? (
                          <p className="text-xs text-gray-600 text-center py-2">No parameters</p>
                        ) : (
                          <div className="space-y-2">
                            {cmd.parameters.map((param, paramIndex) => (
                              <div key={paramIndex} className="bg-gray-900 rounded p-2 space-y-2">
                                <div className="flex items-center justify-between">
                                  <input
                                    type="text"
                                    value={param.parameter_name}
                                    onChange={(e) => updateParameter(cmdIndex, paramIndex, 'parameter_name', e.target.value)}
                                    placeholder="Parameter name"
                                    className="flex-1 px-2 py-1 text-xs bg-transparent border border-gray-700 rounded text-white"
                                  />
                                  <button
                                    type="button"
                                    onClick={() => removeParameter(cmdIndex, paramIndex)}
                                    className="ml-2 text-xs text-red-400 hover:text-red-300"
                                  >
                                    ×
                                  </button>
                                </div>
                                <div className="grid grid-cols-2 gap-2">
                                  <input
                                    type="text"
                                    value={param.default_value}
                                    onChange={(e) => updateParameter(cmdIndex, paramIndex, 'default_value', e.target.value)}
                                    placeholder="Default value"
                                    className="px-2 py-1 text-xs bg-transparent border border-gray-700 rounded text-white"
                                  />
                                  <label className="flex items-center text-xs text-gray-400">
                                    <input
                                      type="checkbox"
                                      checked={param.is_mandatory}
                                      onChange={(e) => updateParameter(cmdIndex, paramIndex, 'is_mandatory', e.target.checked)}
                                      className="mr-1"
                                    />
                                    Required
                                  </label>
                                </div>
                                <input
                                  type="text"
                                  value={param.description}
                                  onChange={(e) => updateParameter(cmdIndex, paramIndex, 'description', e.target.value)}
                                  placeholder="Description"
                                  className="w-full px-2 py-1 text-xs bg-transparent border border-gray-700 rounded text-white"
                                />
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Install Package Modal */}
      <Modal
        isOpen={showInstallModal}
        onClose={() => setShowInstallModal(false)}
        title="Install Package"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowInstallModal(false)}
              className="btn-ghost"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              onClick={handleInstallPackage}
              className="btn-primary"
              disabled={saving}
            >
              {saving ? 'Installing...' : 'Install'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Package Type</label>
            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setPackageForm({ ...packageForm, package_type: 'pip' })}
                className={`p-4 rounded-lg border-2 transition-all ${packageForm.package_type === 'pip'
                    ? 'border-blue-500 bg-blue-500/10'
                    : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                  }`}
              >
                <svg className="w-6 h-6 mx-auto mb-2 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></svg>
                <div className="font-semibold text-white">pip</div>
                <div className="text-xs text-gray-400">Python packages</div>
              </button>
              <button
                type="button"
                onClick={() => setPackageForm({ ...packageForm, package_type: 'apt' })}
                className={`p-4 rounded-lg border-2 transition-all ${packageForm.package_type === 'apt'
                    ? 'border-orange-500 bg-orange-500/10'
                    : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                  }`}
              >
                <PackageIcon size={24} className="mx-auto mb-2 text-orange-400" />
                <div className="font-semibold text-white">apt</div>
                <div className="text-xs text-gray-400">System packages</div>
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Package Name</label>
            <input
              type="text"
              value={packageForm.package_name}
              onChange={(e) => setPackageForm({ ...packageForm, package_name: e.target.value })}
              placeholder={packageForm.package_type === 'pip' ? 'e.g., requests' : 'e.g., jq'}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
            />
          </div>
          <div className="bg-yellow-500/5 border border-yellow-500/20 rounded-lg p-3">
            <p className="text-xs text-yellow-300">
              Note: apt packages require root privileges. Some packages may not install correctly.
            </p>
          </div>
        </div>
      </Modal>

      {/* Edit Tool Modal */}
      <Modal
        isOpen={!!editingTool}
        onClose={() => setEditingTool(null)}
        title="Edit Tool"
        size="lg"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setEditingTool(null)}
              className="btn-ghost"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              onClick={handleEditTool}
              className="btn-primary"
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        }
      >
        {editingTool && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Tool Name</label>
              <input
                type="text"
                value={editingTool.name}
                onChange={(e) => setEditingTool({ ...editingTool, name: e.target.value })}
                placeholder="e.g., my_scanner"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Tool Type</label>
              <input
                type="text"
                value={editingTool.tool_type}
                disabled
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-400 cursor-not-allowed"
              />
              <p className="text-xs text-gray-500 mt-1">Tool type cannot be changed after creation</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">System Prompt</label>
              <textarea
                value={editingTool.system_prompt}
                onChange={(e) => setEditingTool({ ...editingTool, system_prompt: e.target.value })}
                placeholder="Describe what this tool does and when to use it..."
                rows={6}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white resize-none"
              />
            </div>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={editingTool.is_enabled}
                onChange={(e) => setEditingTool({ ...editingTool, is_enabled: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm text-gray-300">Enable this tool</span>
            </label>

            {/* Commands Section (Read-only) */}
            {editingTool.commands && editingTool.commands.length > 0 && (
              <div className="border-t border-gray-700 pt-4 mt-4">
                <h4 className="text-sm font-medium text-gray-300 mb-3">Commands</h4>
                <div className="space-y-2">
                  {editingTool.commands.map((cmd, index) => (
                    <div key={index} className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-white">{cmd.command_name}</span>
                        <span className="text-xs text-gray-500">
                          {cmd.is_long_running ? 'Long-running' : `${cmd.timeout_seconds}s timeout`}
                        </span>
                      </div>
                      <code className="block text-xs bg-gray-900 px-2 py-1 rounded text-green-400 font-mono overflow-x-auto">
                        {cmd.command_template}
                      </code>
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  To modify commands, delete and recreate the tool
                </p>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
