'use client'

/**
 * API Clients Management Page
 * Settings > API Clients
 * Manage OAuth2 API clients for programmatic access to the Public API v1.
 */

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api, ApiClientInfo, ApiClientCreateResponse } from '@/lib/client'

const API_ROLES = [
  { value: 'api_agent_only', label: 'Agent Only', description: 'Can list agents and chat (read + execute)' },
  { value: 'api_readonly', label: 'Read Only', description: 'Can view agents, contacts, memory, analytics' },
  { value: 'api_member', label: 'Member', description: 'Can create/update agents, contacts, flows, knowledge' },
  { value: 'api_admin', label: 'Admin', description: 'Full API access except billing and team management' },
  { value: 'api_owner', label: 'Owner', description: 'Full API access including org settings and audit' },
]

function roleBadgeColor(role: string): string {
  switch (role) {
    case 'api_owner': return 'bg-purple-500/20 text-purple-300 border-purple-500/30'
    case 'api_admin': return 'bg-blue-500/20 text-blue-300 border-blue-500/30'
    case 'api_member': return 'bg-green-500/20 text-green-300 border-green-500/30'
    case 'api_readonly': return 'bg-gray-500/20 text-gray-300 border-gray-500/30'
    case 'api_agent_only': return 'bg-teal-500/20 text-teal-300 border-teal-500/30'
    default: return 'bg-gray-500/20 text-gray-300 border-gray-500/30'
  }
}

function roleLabel(role: string): string {
  return API_ROLES.find(r => r.value === role)?.label || role
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 30) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export default function ApiClientsPage() {
  const { hasPermission } = useAuth()

  const [clients, setClients] = useState<ApiClientInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Create modal state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [formName, setFormName] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formRole, setFormRole] = useState('api_agent_only')
  const [formRateLimit, setFormRateLimit] = useState(60)
  const [creating, setCreating] = useState(false)

  // Secret display modal state
  const [showSecretModal, setShowSecretModal] = useState(false)
  const [newClientSecret, setNewClientSecret] = useState<string | null>(null)
  const [newClientId, setNewClientId] = useState<string | null>(null)
  const [secretCopied, setSecretCopied] = useState(false)

  // Confirm action modal state
  const [confirmAction, setConfirmAction] = useState<{ type: 'rotate' | 'revoke'; client: ApiClientInfo } | null>(null)

  const canWrite = hasPermission('org.settings.write')

  const fetchClients = useCallback(async () => {
    try {
      const data = await api.getApiClients()
      setClients(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load API clients')
    }
  }, [])

  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await fetchClients()
      setLoading(false)
    }
    loadData()
  }, [fetchClients])

  useEffect(() => {
    const handleRefresh = () => fetchClients()
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [fetchClients])

  // Auto-clear success messages
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(null), 5000)
      return () => clearTimeout(timer)
    }
  }, [success])

  if (!hasPermission('org.settings.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-100 mb-2">Access Denied</h3>
          <p className="text-sm text-red-200">You do not have permission to view API clients.</p>
        </div>
      </div>
    )
  }

  const handleCreate = async () => {
    if (!formName.trim()) return
    setCreating(true)
    setError(null)
    try {
      const result: ApiClientCreateResponse = await api.createApiClient({
        name: formName.trim(),
        description: formDescription.trim() || undefined,
        role: formRole,
        rate_limit_rpm: formRateLimit,
      })
      setNewClientSecret(result.client_secret)
      setNewClientId(result.client_id)
      setSecretCopied(false)
      setShowCreateModal(false)
      setShowSecretModal(true)
      setFormName('')
      setFormDescription('')
      setFormRole('api_agent_only')
      setFormRateLimit(60)
      await fetchClients()
      setSuccess(`API client "${result.name}" created successfully`)
    } catch (err: any) {
      setError(err.message || 'Failed to create API client')
    } finally {
      setCreating(false)
    }
  }

  const handleRotate = async (client: ApiClientInfo) => {
    setError(null)
    try {
      const result = await api.rotateApiClientSecret(client.client_id)
      setNewClientSecret(result.client_secret)
      setNewClientId(client.client_id)
      setSecretCopied(false)
      setConfirmAction(null)
      setShowSecretModal(true)
      await fetchClients()
      setSuccess(`Secret rotated for "${client.name}"`)
    } catch (err: any) {
      setError(err.message || 'Failed to rotate secret')
    }
  }

  const handleRevoke = async (client: ApiClientInfo) => {
    setError(null)
    try {
      await api.revokeApiClient(client.client_id)
      setConfirmAction(null)
      await fetchClients()
      setSuccess(`API client "${client.name}" revoked`)
    } catch (err: any) {
      setError(err.message || 'Failed to revoke API client')
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      setSecretCopied(true)
    }).catch(() => {
      // Fallback for non-secure contexts
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      setSecretCopied(true)
    })
  }

  const activeClients = clients.filter(c => c.is_active)
  const revokedClients = clients.filter(c => !c.is_active)

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <Link href="/settings" className="text-sm text-tsushin-slate hover:text-teal-400 transition-colors mb-4 inline-block">
            &larr; Back to Settings
          </Link>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-display font-bold text-white">API Clients</h1>
              <p className="text-tsushin-slate mt-1">
                Manage OAuth2 clients for programmatic access to the Public API v1
              </p>
            </div>
            {canWrite && (
              <button
                onClick={() => setShowCreateModal(true)}
                className="btn-primary px-4 py-2 rounded-lg text-sm font-medium bg-teal-600 hover:bg-teal-500 text-white transition-colors"
              >
                + Create API Client
              </button>
            )}
          </div>
        </div>

        {/* Alerts */}
        {error && (
          <div className="mb-4 bg-red-900/20 border border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-200">{error}</p>
            <button onClick={() => setError(null)} className="text-xs text-red-400 mt-1 hover:text-red-300">Dismiss</button>
          </div>
        )}
        {success && (
          <div className="mb-4 bg-green-900/20 border border-green-800 rounded-lg p-4">
            <p className="text-sm text-green-200">{success}</p>
          </div>
        )}

        {/* Loading State */}
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-teal-400"></div>
          </div>
        ) : clients.length === 0 ? (
          /* Empty State */
          <div className="text-center py-16 bg-tsushin-dark-lighter rounded-xl border border-tsushin-border">
            <svg className="w-16 h-16 mx-auto text-tsushin-slate mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
            </svg>
            <h3 className="text-lg font-semibold text-white mb-2">No API Clients</h3>
            <p className="text-tsushin-slate mb-6 max-w-md mx-auto">
              Create an API client to access Tsushin programmatically via the Public API v1.
              Use OAuth2 client credentials or direct API key authentication.
            </p>
            {canWrite && (
              <button
                onClick={() => setShowCreateModal(true)}
                className="btn-primary px-6 py-2 rounded-lg text-sm font-medium bg-teal-600 hover:bg-teal-500 text-white transition-colors"
              >
                Create Your First API Client
              </button>
            )}
          </div>
        ) : (
          /* Client Table */
          <div className="space-y-6">
            {/* Active Clients */}
            <div className="bg-tsushin-dark-lighter rounded-xl border border-tsushin-border overflow-hidden">
              <div className="px-6 py-4 border-b border-tsushin-border">
                <h2 className="text-lg font-semibold text-white">Active Clients ({activeClients.length})</h2>
              </div>
              {activeClients.length === 0 ? (
                <div className="px-6 py-8 text-center text-tsushin-slate">No active API clients</div>
              ) : (
                <div className="divide-y divide-tsushin-border">
                  {activeClients.map((client) => (
                    <div key={client.id} className="px-6 py-4 flex items-center justify-between hover:bg-white/[0.02] transition-colors">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-1">
                          <h3 className="text-sm font-medium text-white truncate">{client.name}</h3>
                          <span className={`text-xs px-2 py-0.5 rounded-full border ${roleBadgeColor(client.role)}`}>
                            {roleLabel(client.role)}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-tsushin-slate">
                          <span className="font-mono">{client.client_id.substring(0, 20)}...</span>
                          <span>RPM: {client.rate_limit_rpm}</span>
                          <span>Last used: {formatRelativeTime(client.last_used_at)}</span>
                          <span>Created: {formatRelativeTime(client.created_at)}</span>
                        </div>
                        {client.description && (
                          <p className="text-xs text-tsushin-slate/70 mt-1 truncate">{client.description}</p>
                        )}
                      </div>
                      {canWrite && (
                        <div className="flex items-center gap-2 ml-4">
                          <button
                            onClick={() => setConfirmAction({ type: 'rotate', client })}
                            className="text-xs px-3 py-1.5 rounded-md bg-yellow-900/20 text-yellow-300 border border-yellow-800/30 hover:bg-yellow-900/40 transition-colors"
                          >
                            Rotate Secret
                          </button>
                          <button
                            onClick={() => setConfirmAction({ type: 'revoke', client })}
                            className="text-xs px-3 py-1.5 rounded-md bg-red-900/20 text-red-300 border border-red-800/30 hover:bg-red-900/40 transition-colors"
                          >
                            Revoke
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Revoked Clients */}
            {revokedClients.length > 0 && (
              <div className="bg-tsushin-dark-lighter rounded-xl border border-tsushin-border overflow-hidden opacity-60">
                <div className="px-6 py-4 border-b border-tsushin-border">
                  <h2 className="text-lg font-semibold text-tsushin-slate">Revoked Clients ({revokedClients.length})</h2>
                </div>
                <div className="divide-y divide-tsushin-border">
                  {revokedClients.map((client) => (
                    <div key={client.id} className="px-6 py-3 flex items-center justify-between">
                      <div>
                        <div className="flex items-center gap-3">
                          <h3 className="text-sm text-tsushin-slate line-through">{client.name}</h3>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-red-900/20 text-red-400 border border-red-800/30">Revoked</span>
                        </div>
                        <span className="text-xs text-tsushin-slate/50 font-mono">{client.client_id.substring(0, 20)}...</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Quick Reference */}
        <div className="mt-8 bg-tsushin-dark-lighter rounded-xl border border-tsushin-border p-6">
          <h3 className="text-sm font-semibold text-white mb-3">Quick Start</h3>
          <div className="space-y-2 text-xs font-mono text-tsushin-slate">
            <p className="text-tsushin-slate/70 font-sans text-sm mb-3">Use your client credentials to authenticate with the API:</p>
            <div className="bg-black/30 rounded-lg p-3 overflow-x-auto">
              <pre>{`# OAuth2 Token Exchange
curl -X POST $API_URL/api/v1/oauth/token \\
  -d "grant_type=client_credentials" \\
  -d "client_id=$CLIENT_ID" \\
  -d "client_secret=$CLIENT_SECRET"

# Direct API Key Mode (skip token exchange)
curl -H "X-API-Key: $CLIENT_SECRET" $API_URL/api/v1/agents`}</pre>
            </div>
          </div>
        </div>
      </div>

      {/* ========== Create Modal ========== */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-tsushin-dark-lighter border border-tsushin-border rounded-xl w-full max-w-lg mx-4 p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Create API Client</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-tsushin-slate mb-1">Name *</label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g., CRM Integration"
                  className="w-full bg-tsushin-dark border border-tsushin-border rounded-lg px-3 py-2 text-sm text-white placeholder-tsushin-slate/50 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-tsushin-slate mb-1">Description</label>
                <textarea
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="What will this client be used for?"
                  rows={2}
                  className="w-full bg-tsushin-dark border border-tsushin-border rounded-lg px-3 py-2 text-sm text-white placeholder-tsushin-slate/50 focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none resize-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-tsushin-slate mb-1">Role</label>
                <select
                  value={formRole}
                  onChange={(e) => setFormRole(e.target.value)}
                  className="w-full bg-tsushin-dark border border-tsushin-border rounded-lg px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none"
                >
                  {API_ROLES.map((role) => (
                    <option key={role.value} value={role.value}>{role.label} — {role.description}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-tsushin-slate mb-1">Rate Limit (requests/minute)</label>
                <input
                  type="number"
                  value={formRateLimit}
                  onChange={(e) => setFormRateLimit(Math.max(1, Math.min(600, parseInt(e.target.value) || 60)))}
                  min={1}
                  max={600}
                  className="w-full bg-tsushin-dark border border-tsushin-border rounded-lg px-3 py-2 text-sm text-white focus:border-teal-500 focus:ring-1 focus:ring-teal-500 outline-none"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-4 py-2 text-sm text-tsushin-slate hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!formName.trim() || creating}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-teal-600 hover:bg-teal-500 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {creating ? 'Creating...' : 'Create Client'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== Secret Display Modal ========== */}
      {showSecretModal && newClientSecret && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-tsushin-dark-lighter border border-tsushin-border rounded-xl w-full max-w-lg mx-4 p-6">
            <div className="flex items-center gap-2 mb-4">
              <svg className="w-5 h-5 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
              </svg>
              <h2 className="text-lg font-semibold text-white">Save Your Secret</h2>
            </div>

            <div className="bg-yellow-900/10 border border-yellow-800/30 rounded-lg p-3 mb-4">
              <p className="text-sm text-yellow-200">
                This is the only time the secret will be shown. Copy it now and store it securely.
              </p>
            </div>

            {newClientId && (
              <div className="mb-3">
                <label className="block text-xs font-medium text-tsushin-slate mb-1">Client ID</label>
                <div className="flex items-center gap-2">
                  <code className="flex-1 bg-black/30 rounded-lg px-3 py-2 text-sm text-teal-300 font-mono select-all break-all">
                    {newClientId}
                  </code>
                  <button
                    onClick={() => copyToClipboard(newClientId)}
                    className="px-2 py-2 text-xs text-tsushin-slate hover:text-white transition-colors"
                    title="Copy Client ID"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                  </button>
                </div>
              </div>
            )}

            <div className="mb-4">
              <label className="block text-xs font-medium text-tsushin-slate mb-1">Client Secret</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-black/30 rounded-lg px-3 py-2 text-sm text-yellow-300 font-mono select-all break-all">
                  {newClientSecret}
                </code>
                <button
                  onClick={() => copyToClipboard(newClientSecret)}
                  className="px-2 py-2 text-xs text-tsushin-slate hover:text-white transition-colors"
                  title="Copy Secret"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </button>
              </div>
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => {
                  setShowSecretModal(false)
                  setNewClientSecret(null)
                  setNewClientId(null)
                }}
                className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  secretCopied
                    ? 'bg-teal-600 hover:bg-teal-500 text-white'
                    : 'bg-tsushin-dark border border-tsushin-border text-tsushin-slate hover:text-white'
                }`}
              >
                {secretCopied ? 'Done' : 'I have saved the secret'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== Confirm Action Modal ========== */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-tsushin-dark-lighter border border-tsushin-border rounded-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold text-white mb-2">
              {confirmAction.type === 'rotate' ? 'Rotate Secret' : 'Revoke API Client'}
            </h2>
            <p className="text-sm text-tsushin-slate mb-4">
              {confirmAction.type === 'rotate'
                ? `This will generate a new secret for "${confirmAction.client.name}". The old secret will stop working immediately.`
                : `This will permanently revoke "${confirmAction.client.name}". All issued tokens will fail on next use.`
              }
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setConfirmAction(null)}
                className="px-4 py-2 text-sm text-tsushin-slate hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (confirmAction.type === 'rotate') handleRotate(confirmAction.client)
                  else handleRevoke(confirmAction.client)
                }}
                className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  confirmAction.type === 'revoke'
                    ? 'bg-red-600 hover:bg-red-500 text-white'
                    : 'bg-yellow-600 hover:bg-yellow-500 text-white'
                }`}
              >
                {confirmAction.type === 'rotate' ? 'Rotate Secret' : 'Revoke Client'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
