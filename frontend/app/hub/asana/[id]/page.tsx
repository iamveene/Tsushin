'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'

interface Integration {
  id: number
  type: string
  name: string
  is_active: boolean
  workspace_gid: string
  workspace_name: string
  default_assignee_name?: string
  default_assignee_gid?: string
}

interface HealthStatus {
  status: string
  last_check: string
  details: {
    token_valid: boolean
    workspace: string
    tools_available: number
  }
  errors: string[]
}

interface Tool {
  name: string
  description: string
  input_schema: any
}

export default function AsanaManagePage() {
  const params = useParams()
  const router = useRouter()
  const integrationId = params.id as string

  const [integration, setIntegration] = useState<Integration | null>(null)
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)
  const [assigneeName, setAssigneeName] = useState('')
  const [savingAssignee, setSavingAssignee] = useState(false)
  const [assigneeMessage, setAssigneeMessage] = useState('')

  // Helper function to get authentication headers
  const getAuthHeaders = () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }

  useEffect(() => {
    fetchIntegration()
    fetchHealth()
    fetchTools()
  }, [integrationId])

  useEffect(() => {
    if (integration?.default_assignee_name) {
      setAssigneeName(integration.default_assignee_name)
    }
  }, [integration])

  const fetchIntegration = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/hub/integrations`, {
        headers: getAuthHeaders()
      })
      if (!response.ok) throw new Error('Failed to fetch')

      const data = await response.json()
      const found = data.find((i: any) => i.id === parseInt(integrationId))
      setIntegration(found || null)
    } catch (error) {
      console.error('Failed to fetch integration:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchHealth = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/hub/asana/${integrationId}/health`, {
        headers: getAuthHeaders()
      })
      if (!response.ok) throw new Error('Failed to fetch health')

      const data = await response.json()
      setHealth(data)
    } catch (error) {
      console.error('Failed to fetch health:', error)
    }
  }

  const fetchTools = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/hub/asana/${integrationId}/tools`, {
        headers: getAuthHeaders()
      })
      if (!response.ok) throw new Error('Failed to fetch tools')

      const data = await response.json()
      setTools(data)
    } catch (error) {
      console.error('Failed to fetch tools:', error)
    }
  }

  const handleDisconnect = async () => {
    if (!confirm('Disconnect this Asana integration?')) return

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      await fetch(`${apiUrl}/api/hub/asana/oauth/disconnect/${integrationId}`, {
        method: 'POST',
        headers: getAuthHeaders()
      })
      router.push('/hub')
    } catch (error) {
      console.error('Failed to disconnect:', error)
      alert('Failed to disconnect integration')
    }
  }

  const handleUpdateAssignee = async () => {
    setSavingAssignee(true)
    setAssigneeMessage('')

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/hub/asana/${integrationId}/default-assignee`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          assignee_name: assigneeName.trim() || null
        })
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to update assignee')
      }

      const data = await response.json()
      setAssigneeMessage(`✓ ${data.message}`)

      // Refresh integration to get updated values
      await fetchIntegration()
    } catch (error: any) {
      console.error('Failed to update assignee:', error)
      setAssigneeMessage(`✗ ${error.message}`)
    } finally {
      setSavingAssignee(false)
      // Clear message after 5 seconds
      setTimeout(() => setAssigneeMessage(''), 5000)
    }
  }

  const handleClearAssignee = async () => {
    setAssigneeName('')
    setSavingAssignee(true)
    setAssigneeMessage('')

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/hub/asana/${integrationId}/default-assignee`, {
        method: 'PATCH',
        headers: getAuthHeaders(),
        body: JSON.stringify({ assignee_name: null })
      })

      if (!response.ok) {
        throw new Error('Failed to clear assignee')
      }

      const data = await response.json()
      setAssigneeMessage(`✓ ${data.message}`)
      await fetchIntegration()
    } catch (error: any) {
      console.error('Failed to clear assignee:', error)
      setAssigneeMessage(`✗ ${error.message}`)
    } finally {
      setSavingAssignee(false)
      setTimeout(() => setAssigneeMessage(''), 5000)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <div className="text-center py-16 text-tsushin-slate">Loading...</div>
        </div>
      </div>
    )
  }

  if (!integration) {
    return (
      <div className="min-h-screen bg-gray-950 text-white">
        <div className="max-w-6xl mx-auto px-4 py-8">
          <div className="text-center py-16">
            <h2 className="text-2xl font-bold mb-4 text-red-400">Integration Not Found</h2>
            <button
              onClick={() => router.push('/hub')}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
            >
              Back to Hub
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => router.push('/hub')}
            className="text-tsushin-slate hover:text-white mb-4 flex items-center gap-2"
          >
            ← Back to Hub
          </button>
          <h1 className="text-3xl font-bold mb-2">{integration.name}</h1>
          <p className="text-tsushin-slate">
            Manage your Asana integration and available tools
          </p>
        </div>

        {/* Status Card */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold">Connection Status</h2>
            <span
              className={`px-3 py-1 text-sm font-medium rounded-full ${
                health?.status === 'healthy'
                  ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                  : health?.status === 'degraded'
                  ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                  : 'bg-gray-500/10 text-gray-400 border border-gray-500/20'
              }`}
            >
              {health?.status || 'unknown'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-tsushin-slate mb-1">Workspace</div>
              <div className="font-mono text-orange-400">{integration.workspace_name}</div>
            </div>
            <div>
              <div className="text-tsushin-slate mb-1">Workspace GID</div>
              <div className="font-mono text-gray-400 text-xs">{integration.workspace_gid}</div>
            </div>
            <div>
              <div className="text-tsushin-slate mb-1">Token Status</div>
              <div className={health?.details?.token_valid ? 'text-green-400' : 'text-red-400'}>
                {health?.details?.token_valid ? 'Valid' : 'Invalid'}
              </div>
            </div>
            <div>
              <div className="text-tsushin-slate mb-1">Available Tools</div>
              <div className="text-white">{health?.details?.tools_available || tools.length || 0}</div>
            </div>
          </div>

          <div className="mt-6 flex gap-3">
            <button
              onClick={fetchHealth}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
            >
              Refresh Status
            </button>
            <button
              onClick={handleDisconnect}
              className="px-4 py-2 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded-lg transition-colors border border-red-900/50"
            >
              Disconnect
            </button>
          </div>
        </div>

        {/* Default Assignee Configuration */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-2">Default Assignee</h2>
          <p className="text-sm text-tsushin-slate mb-4">
            Configure a default assignee for all Asana tasks created by agents. Enter the user's name (e.g., "John Smith") and the system will automatically resolve it to the correct user.
          </p>

          {integration.default_assignee_name && (
            <div className="mb-4 p-3 bg-gray-800/50 border border-gray-700 rounded-lg">
              <div className="text-sm text-tsushin-slate mb-1">Current Default Assignee</div>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-white">{integration.default_assignee_name}</div>
                  <div className="text-xs font-mono text-gray-400">GID: {integration.default_assignee_gid}</div>
                </div>
                <button
                  onClick={handleClearAssignee}
                  disabled={savingAssignee}
                  className="px-3 py-1 text-sm bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded border border-red-900/50 disabled:opacity-50"
                >
                  Clear
                </button>
              </div>
            </div>
          )}

          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium mb-2 text-tsushin-slate">
                Assignee Name
              </label>
              <input
                type="text"
                value={assigneeName}
                onChange={(e) => setAssigneeName(e.target.value)}
                placeholder="e.g., John Smith"
                disabled={savingAssignee}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-orange-500 disabled:opacity-50"
              />
              <p className="mt-1 text-xs text-tsushin-slate">
                Enter the full name or partial name of the Asana user. The system will search and match automatically.
              </p>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={handleUpdateAssignee}
                disabled={savingAssignee || !assigneeName.trim()}
                className="px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {savingAssignee ? 'Saving...' : 'Save Assignee'}
              </button>

              {assigneeMessage && (
                <span className={`text-sm ${assigneeMessage.startsWith('✓') ? 'text-green-400' : 'text-red-400'}`}>
                  {assigneeMessage}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Tools Card */}
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-800">
            <h2 className="text-xl font-semibold">Available Tools</h2>
            <p className="text-sm text-tsushin-slate mt-1">
              {tools.length} Asana tools ready to use via agents
            </p>
          </div>

          <div className="p-6">
            {tools.length === 0 ? (
              <div className="text-center py-8 text-tsushin-slate">
                No tools available. Check connection status.
              </div>
            ) : (
              <div className="grid gap-3">
                {tools.map((tool) => (
                  <div
                    key={tool.name}
                    className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 hover:border-orange-500 transition-colors"
                  >
                    <div className="flex items-start justify-between mb-2">
                      <h3 className="font-semibold text-white font-mono text-sm">{tool.name}</h3>
                      <span className="px-2 py-0.5 text-xs bg-orange-900/30 text-orange-400 rounded border border-orange-900/50">
                        MCP Tool
                      </span>
                    </div>
                    <p className="text-sm text-tsushin-slate">{tool.description}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
