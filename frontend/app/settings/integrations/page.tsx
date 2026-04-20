'use client'

/**
 * Integrations Settings Page
 * Centralized configuration for third-party integrations:
 * - Google OAuth (SSO, Gmail, Calendar)
 */

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRequireAuth } from '@/contexts/AuthContext'
import { authenticatedFetch } from '@/lib/client'
import { useGoogleWizard, useGoogleWizardComplete } from '@/contexts/GoogleWizardContext'

interface GoogleCredentials {
  id: number
  tenant_id: string
  client_id: string
  redirect_uri: string | null
  created_at: string
  configured?: boolean
}


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

  // Guided setup wizards live in a global context so Hub can reuse them
  const { openWizard } = useGoogleWizard()

  const apiUrl = ''

  // ---- Google OAuth functions ----

  const fetchGoogleCredentials = useCallback(async () => {
    try {
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/credentials`)
      if (response.ok) {
        const data = await response.json()
        // BUG-343 fix: backend returns 200 with configured=false on fresh install
        setGoogleCredentials(data && data.configured === false ? null : data)
      } else if (response.status === 404) {
        // Legacy fallback: old backend versions still return 404
        setGoogleCredentials(null)
      }
    } catch (err) {
      console.error('Error fetching Google credentials:', err)
    }
  }, [apiUrl])

  const refreshAfterWizard = useCallback(() => {
    fetchGoogleCredentials()
    setSuccess('Integration connected')
    setTimeout(() => setSuccess(null), 3000)
  }, [fetchGoogleCredentials])
  useGoogleWizardComplete('gmail', refreshAfterWizard)
  useGoogleWizardComplete('calendar', refreshAfterWizard)

  const handleSaveGoogleCredentials = async () => {
    if (!googleClientId.trim()) { setError('Client ID is required'); return }
    if (!googleClientSecret.trim() && !googleCredentials) { setError('Client Secret is required for new configuration'); return }

    setSaving(true); setError(null)
    try {
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/credentials`, {
        method: 'POST',
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
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/credentials`, { method: 'DELETE' })
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

  // ---- Effects ----

  useEffect(() => {
    if (!authLoading && user) {
      setLoading(true)
      fetchGoogleCredentials().finally(() => setLoading(false))
    }
  }, [authLoading, user, fetchGoogleCredentials])

  useEffect(() => {
    const handleRefresh = () => {
      if (!authLoading && user) { fetchGoogleCredentials() }
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [authLoading, user, fetchGoogleCredentials])

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

  if (!hasPermission('org.settings.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-100 mb-2">Access Denied</h3>
          <p className="text-sm text-red-200">You do not have permission to view integrations.</p>
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
                  <div className="flex flex-wrap gap-3 pt-4">
                    <button onClick={() => openWizard('gmail')}
                      className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-colors">
                      Set up Gmail →
                    </button>
                    <button onClick={() => openWizard('calendar')}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
                      Set up Google Calendar →
                    </button>
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
                  <>
                    <button onClick={() => setShowGoogleModal(true)}
                      className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
                      Configure Google Integration
                    </button>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-3">
                      Or jump straight into a guided setup:{' '}
                      <button onClick={() => openWizard('gmail')} className="text-red-500 hover:text-red-600 underline">
                        Gmail
                      </button>{' '}·{' '}
                      <button onClick={() => openWizard('calendar')} className="text-blue-500 hover:text-blue-600 underline">
                        Google Calendar
                      </button>
                    </p>
                  </>
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
