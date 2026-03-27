'use client'

/**
 * Integrations Settings Page
 * Centralized configuration for third-party integrations:
 * - Google OAuth (SSO, Gmail, Calendar)
 * - AI Provider API Keys (Groq, Grok/xAI, ElevenLabs TTS)
 */

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRequireAuth } from '@/contexts/AuthContext'

interface GoogleCredentials {
  id: number
  tenant_id: string
  client_id: string
  redirect_uri: string | null
  created_at: string
}

interface ApiKeyStatus {
  id?: number
  service: string
  api_key_preview?: string
  is_active: boolean
  exists: boolean
}

interface TestResult {
  success: boolean
  message: string
  provider: string
  details?: Record<string, any>
  error?: string
}

// Provider card configuration
const AI_PROVIDERS = [
  {
    service: 'groq',
    name: 'Groq',
    description: 'Ultra-fast inference for open-source LLMs (LLaMA, Mixtral, Gemma)',
    gradient: 'from-orange-500 to-yellow-500',
    features: ['LLaMA 3.3 70B', 'Mixtral 8x7B', 'Gemma 2 9B', 'Ultra-low latency'],
    placeholder: 'gsk_...',
    icon: (
      <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    service: 'grok',
    name: 'Grok (xAI)',
    description: "xAI's frontier models with real-time knowledge",
    gradient: 'from-gray-700 to-gray-900',
    features: ['Grok 3', 'Grok 3 Mini', 'Grok 2', 'Real-time knowledge'],
    placeholder: 'xai-...',
    icon: (
      <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
      </svg>
    ),
  },
  {
    service: 'elevenlabs',
    name: 'ElevenLabs',
    description: 'Premium AI voice synthesis with neural TTS',
    gradient: 'from-purple-600 to-blue-600',
    features: ['Neural TTS', 'Voice cloning', '25+ languages', 'Emotional control'],
    placeholder: 'sk_...',
    icon: (
      <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
        <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
        <line x1="12" y1="19" x2="12" y2="23" />
        <line x1="8" y1="23" x2="16" y2="23" />
      </svg>
    ),
  },
]

export default function IntegrationsSettingsPage() {
  const { user, loading: authLoading, hasPermission } = useRequireAuth()
  const canEdit = hasPermission('org.settings.write')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // Google OAuth state
  const [googleCredentials, setGoogleCredentials] = useState<GoogleCredentials | null>(null)
  const [showGoogleModal, setShowGoogleModal] = useState(false)
  const [googleClientId, setGoogleClientId] = useState('')
  const [googleClientSecret, setGoogleClientSecret] = useState('')

  // AI Provider API Key state
  const [apiKeyStatuses, setApiKeyStatuses] = useState<Record<string, ApiKeyStatus>>({})
  const [testingProvider, setTestingProvider] = useState<string | null>(null)
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [showApiKeyModal, setShowApiKeyModal] = useState<string | null>(null)
  const [apiKeyInput, setApiKeyInput] = useState('')

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

  const getAuthHeaders = useCallback(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }, [])

  // ---- Google OAuth functions ----

  const fetchGoogleCredentials = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/api/hub/google/credentials`, {
        headers: getAuthHeaders()
      })
      if (response.ok) {
        setGoogleCredentials(await response.json())
      } else if (response.status === 404) {
        setGoogleCredentials(null)
      }
    } catch (err) {
      console.error('Error fetching Google credentials:', err)
    }
  }, [apiUrl, getAuthHeaders])

  const handleSaveGoogleCredentials = async () => {
    if (!googleClientId.trim()) { setError('Client ID is required'); return }
    if (!googleClientSecret.trim() && !googleCredentials) { setError('Client Secret is required for new configuration'); return }

    setSaving(true); setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/hub/google/credentials`, {
        method: 'POST', headers: getAuthHeaders(),
        body: JSON.stringify({ client_id: googleClientId.trim(), client_secret: googleClientSecret.trim() || undefined })
      })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }
      await fetchGoogleCredentials()
      setShowGoogleModal(false); setGoogleClientId(''); setGoogleClientSecret('')
      setSuccess('Google OAuth credentials saved successfully')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(`Failed to save: ${err.message}`)
    } finally { setSaving(false) }
  }

  const handleDeleteGoogleCredentials = async () => {
    if (!confirm('Are you sure you want to remove Google OAuth credentials?\n\nThis will disconnect all Google integrations (Gmail, Calendar) and disable Google SSO.')) return
    setSaving(true); setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/hub/google/credentials`, { method: 'DELETE', headers: getAuthHeaders() })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }
      setGoogleCredentials(null)
      setSuccess('Google OAuth credentials removed')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(`Failed to remove: ${err.message}`)
    } finally { setSaving(false) }
  }

  // ---- AI Provider API Key functions ----

  const fetchApiKeyStatuses = useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/api/api-keys`, { headers: getAuthHeaders() })
      if (response.ok) {
        const keys = await response.json()
        const statuses: Record<string, ApiKeyStatus> = {}
        for (const provider of AI_PROVIDERS) {
          const key = keys.find((k: any) => k.service === provider.service)
          statuses[provider.service] = key
            ? { id: key.id, service: key.service, api_key_preview: key.api_key_preview, is_active: key.is_active, exists: true }
            : { service: provider.service, is_active: false, exists: false }
        }
        setApiKeyStatuses(statuses)
      }
    } catch (err) {
      console.error('Error fetching API key statuses:', err)
    }
  }, [apiUrl, getAuthHeaders])

  const handleSaveApiKey = async (service: string) => {
    if (!apiKeyInput.trim()) { setError('API key is required'); return }
    setSaving(true); setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/api-keys`, {
        method: 'POST', headers: getAuthHeaders(),
        body: JSON.stringify({ service, api_key: apiKeyInput.trim() })
      })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }
      await fetchApiKeyStatuses()
      setShowApiKeyModal(null); setApiKeyInput('')
      const providerName = AI_PROVIDERS.find(p => p.service === service)?.name || service
      setSuccess(`${providerName} API key saved successfully`)
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(`Failed to save: ${err.message}`)
    } finally { setSaving(false) }
  }

  const handleDeleteApiKey = async (service: string) => {
    const providerName = AI_PROVIDERS.find(p => p.service === service)?.name || service
    if (!confirm(`Remove ${providerName} API key? This will disable ${providerName} integration.`)) return
    setSaving(true); setError(null)
    try {
      const response = await fetch(`${apiUrl}/api/api-keys/${service}`, { method: 'DELETE', headers: getAuthHeaders() })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }
      await fetchApiKeyStatuses()
      setTestResults(prev => { const next = { ...prev }; delete next[service]; return next })
      setSuccess(`${providerName} API key removed`)
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(`Failed to remove: ${err.message}`)
    } finally { setSaving(false) }
  }

  const handleTestConnection = async (service: string) => {
    setTestingProvider(service)
    setTestResults(prev => { const next = { ...prev }; delete next[service]; return next })
    try {
      const response = await fetch(`${apiUrl}/api/integrations/${service}/test`, {
        method: 'POST', headers: getAuthHeaders(), body: JSON.stringify({})
      })
      const result = await response.json()
      setTestResults(prev => ({ ...prev, [service]: result }))
      if (result.success) {
        setTimeout(() => setTestResults(prev => { const next = { ...prev }; delete next[service]; return next }), 5000)
      }
    } catch (err: any) {
      setTestResults(prev => ({
        ...prev,
        [service]: { success: false, message: `Connection failed: ${err.message}`, provider: service, error: err.message }
      }))
    } finally { setTestingProvider(null) }
  }

  // ---- Effects ----

  useEffect(() => {
    if (!authLoading && user) {
      setLoading(true)
      Promise.all([fetchGoogleCredentials(), fetchApiKeyStatuses()]).finally(() => setLoading(false))
    }
  }, [authLoading, user, fetchGoogleCredentials, fetchApiKeyStatuses])

  useEffect(() => {
    const handleRefresh = () => {
      if (!authLoading && user) { fetchGoogleCredentials(); fetchApiKeyStatuses() }
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [authLoading, user, fetchGoogleCredentials, fetchApiKeyStatuses])

  if (authLoading || loading) {
    return (
      <div className="p-6 space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-48 mb-6"></div>
          <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded mb-4"></div>
          <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded mb-4"></div>
          <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-display font-bold text-gray-900 dark:text-white">Integrations</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          Configure third-party integrations and API keys for your organization
        </p>
      </div>

      {/* Back to Settings */}
      <Link href="/settings" className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6 transition-colors">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
        Back to Settings
      </Link>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-600 dark:text-red-400">
          {error}
          <button onClick={() => setError(null)} className="ml-2 text-red-400 hover:text-red-300">×</button>
        </div>
      )}
      {success && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4 text-green-600 dark:text-green-400">
          {success}
        </div>
      )}

      {/* ============================================================ */}
      {/* AI Provider API Keys Section */}
      {/* ============================================================ */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">AI Providers</h2>
        <div className="space-y-4">
          {AI_PROVIDERS.map(provider => {
            const status = apiKeyStatuses[provider.service]
            const testResult = testResults[provider.service]
            const isTesting = testingProvider === provider.service

            return (
              <div key={provider.service} className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm overflow-hidden">
                {/* Card Header */}
                <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${provider.gradient} flex items-center justify-center`}>
                      {provider.icon}
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{provider.name}</h3>
                      <p className="text-sm text-gray-500 dark:text-gray-400">{provider.description}</p>
                    </div>
                    {status?.exists && status.is_active && (
                      <span className="px-3 py-1 text-xs font-medium rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800">
                        Connected
                      </span>
                    )}
                  </div>
                </div>

                {/* Card Body */}
                <div className="p-6">
                  {status?.exists ? (
                    <div className="space-y-4">
                      {/* Key preview */}
                      <div>
                        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">
                          API Key
                        </label>
                        <code className="block text-sm text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-900 rounded px-3 py-2 font-mono">
                          {status.api_key_preview || '••••••••••••••••'}
                        </code>
                      </div>

                      {/* Features */}
                      <div className="flex flex-wrap gap-2">
                        {provider.features.map(feature => (
                          <span key={feature} className="inline-flex items-center px-2.5 py-1 bg-gray-100 dark:bg-gray-700/50 text-gray-600 dark:text-gray-300 text-xs rounded-md">
                            {feature}
                          </span>
                        ))}
                      </div>

                      {/* Test result */}
                      {testResult && (
                        <div className={`rounded-lg p-3 text-sm ${
                          testResult.success
                            ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800'
                            : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800'
                        }`}>
                          <div className="flex items-center gap-2">
                            {testResult.success ? (
                              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                            ) : (
                              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                            )}
                            <span>{testResult.message}</span>
                            <button onClick={() => setTestResults(prev => { const next = { ...prev }; delete next[provider.service]; return next })} className="ml-auto text-gray-400 hover:text-gray-300">×</button>
                          </div>
                        </div>
                      )}

                      {/* Actions */}
                      {canEdit && (
                        <div className="flex gap-3 pt-2">
                          <button
                            onClick={() => handleTestConnection(provider.service)}
                            disabled={isTesting || saving}
                            className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-medium text-sm transition-colors disabled:opacity-50"
                          >
                            {isTesting ? (
                              <span className="flex items-center gap-2">
                                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                                Testing...
                              </span>
                            ) : 'Test Connection'}
                          </button>
                          <button
                            onClick={() => { setShowApiKeyModal(provider.service); setApiKeyInput('') }}
                            className="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg font-medium text-sm transition-colors"
                          >
                            Update Key
                          </button>
                          <button
                            onClick={() => handleDeleteApiKey(provider.service)}
                            disabled={saving}
                            className="px-4 py-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg font-medium text-sm transition-colors disabled:opacity-50"
                          >
                            Remove
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-6">
                      <div className="w-12 h-12 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mx-auto mb-3">
                        <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                        </svg>
                      </div>
                      <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-1">
                        Not Configured
                      </h4>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 max-w-sm mx-auto">
                        Add your {provider.name} API key to enable this integration
                      </p>
                      {canEdit && (
                        <button
                          onClick={() => { setShowApiKeyModal(provider.service); setApiKeyInput('') }}
                          className="px-5 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-medium text-sm transition-colors"
                        >
                          Add API Key
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* ============================================================ */}
      {/* Google OAuth Section */}
      {/* ============================================================ */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">OAuth Integrations</h2>
        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-red-500 flex items-center justify-center">
                <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Google Integration</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">OAuth credentials for Google SSO, Gmail, and Calendar</p>
              </div>
              {googleCredentials && (
                <span className="px-3 py-1 text-xs font-medium rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800">
                  Connected
                </span>
              )}
            </div>
          </div>

          <div className="p-6">
            {googleCredentials ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Client ID</label>
                    <code className="block text-sm text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-900 rounded px-3 py-2 font-mono break-all">
                      {googleCredentials.client_id}
                    </code>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-1">Client Secret</label>
                    <code className="block text-sm text-gray-900 dark:text-gray-100 bg-gray-50 dark:bg-gray-900 rounded px-3 py-2 font-mono">
                      ••••••••••••••••
                    </code>
                  </div>
                </div>
                <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                  <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Features enabled:</h4>
                  <div className="flex flex-wrap gap-2">
                    {['Google SSO', 'Gmail', 'Google Calendar'].map(f => (
                      <span key={f} className="inline-flex items-center px-3 py-1.5 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 text-sm rounded-lg">
                        {f}
                      </span>
                    ))}
                  </div>
                </div>
                {canEdit && (
                  <div className="flex gap-3 pt-4">
                    <button onClick={() => { setGoogleClientId(googleCredentials?.client_id || ''); setGoogleClientSecret(''); setShowGoogleModal(true) }}
                      className="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg font-medium transition-colors">
                      Update Credentials
                    </button>
                    <button onClick={handleDeleteGoogleCredentials} disabled={saving}
                      className="px-4 py-2 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg font-medium transition-colors disabled:opacity-50">
                      Remove
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-8">
                <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-700 flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                </div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No Google Integration Configured</h3>
                <p className="text-gray-500 dark:text-gray-400 mb-4 max-w-md mx-auto">
                  Configure your Google Cloud OAuth credentials to enable Google Sign-In (SSO), Gmail integration, and Google Calendar features.
                </p>
                {canEdit && (
                  <button onClick={() => setShowGoogleModal(true)}
                    className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
                    Configure Google Integration
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Setup Instructions */}
          <div className="px-6 py-4 bg-amber-50 dark:bg-amber-900/10 border-t border-amber-100 dark:border-amber-900/30">
            <div className="flex gap-3">
              <svg className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="text-sm text-amber-800 dark:text-amber-200">
                <p className="font-medium mb-1">How to get Google OAuth credentials:</p>
                <ol className="list-decimal list-inside space-y-1 text-amber-700 dark:text-amber-300">
                  <li>Go to <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer" className="underline hover:no-underline">Google Cloud Console</a></li>
                  <li>Create OAuth 2.0 Client ID (Web application)</li>
                  <li>Add redirect URI: <code className="bg-amber-100 dark:bg-amber-900/30 px-1.5 py-0.5 rounded text-xs">{apiUrl}/api/hub/google/oauth/callback</code></li>
                </ol>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Coming Soon */}
      <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-xl p-6">
        <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">Coming Soon</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="flex items-center gap-3 text-gray-400 dark:text-gray-500">
            <div className="w-10 h-10 rounded-xl bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" /></svg>
            </div>
            <div>
              <p className="font-medium">Microsoft 365</p>
              <p className="text-xs">Outlook, Teams, OneDrive</p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-gray-400 dark:text-gray-500">
            <div className="w-10 h-10 rounded-xl bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="7" width="20" height="14" rx="2" ry="2" /><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" /></svg>
            </div>
            <div>
              <p className="font-medium">Slack</p>
              <p className="text-xs">Workspace integration</p>
            </div>
          </div>
        </div>
      </div>

      {/* ============================================================ */}
      {/* Shared API Key Modal */}
      {/* ============================================================ */}
      {showApiKeyModal && (() => {
        const provider = AI_PROVIDERS.find(p => p.service === showApiKeyModal)
        const existingKey = apiKeyStatuses[showApiKeyModal]
        if (!provider) return null
        return (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-lg w-full">
              <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {existingKey?.exists ? `Update ${provider.name} API Key` : `Configure ${provider.name}`}
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    API Key <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="password"
                    value={apiKeyInput}
                    onChange={(e) => setApiKeyInput(e.target.value)}
                    placeholder={provider.placeholder}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-teal-500 focus:border-transparent"
                    onKeyDown={(e) => { if (e.key === 'Enter' && apiKeyInput.trim()) handleSaveApiKey(showApiKeyModal) }}
                  />
                  {existingKey?.exists && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      Current key: {existingKey.api_key_preview} — enter a new key to replace it
                    </p>
                  )}
                </div>
              </div>
              <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
                <button
                  onClick={() => { setShowApiKeyModal(null); setApiKeyInput(''); setError(null) }}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg font-medium transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleSaveApiKey(showApiKeyModal)}
                  disabled={saving || !apiKeyInput.trim()}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? 'Saving...' : 'Save API Key'}
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Google Modal */}
      {showGoogleModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl max-w-lg w-full">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {googleCredentials ? 'Update Google OAuth Credentials' : 'Configure Google Integration'}
              </h3>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Client ID <span className="text-red-500">*</span>
                </label>
                <input type="text" value={googleClientId} onChange={(e) => setGoogleClientId(e.target.value)}
                  placeholder="xxxxx.apps.googleusercontent.com"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Client Secret {!googleCredentials && <span className="text-red-500">*</span>}
                </label>
                <input type="password" value={googleClientSecret} onChange={(e) => setGoogleClientSecret(e.target.value)}
                  placeholder={googleCredentials ? '(leave blank to keep current)' : 'GOCSPX-xxxxx'}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent" />
                {googleCredentials && <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Leave blank to keep the existing secret</p>}
              </div>
            </div>
            <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
              <button onClick={() => { setShowGoogleModal(false); setGoogleClientId(''); setGoogleClientSecret(''); setError(null) }}
                className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg font-medium transition-colors">
                Cancel
              </button>
              <button onClick={handleSaveGoogleCredentials} disabled={saving || !googleClientId.trim()}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
                {saving ? 'Saving...' : 'Save Credentials'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
