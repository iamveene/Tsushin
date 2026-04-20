'use client'

/**
 * System → Global SSO (platform-wide Google OAuth)
 * Global admin only.
 */

import React, { useCallback, useEffect, useState } from 'react'
import { useRequireGlobalAdmin } from '@/contexts/AuthContext'
import { api, GlobalSSOConfig, authenticatedFetch } from '@/lib/client'

export default function SystemSSOPage() {
  const { user, loading: authLoading } = useRequireGlobalAdmin()

  const [ssoConfig, setSsoConfig] = useState<GlobalSSOConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [showModal, setShowModal] = useState(false)
  const [saving, setSaving] = useState(false)

  const [enabled, setEnabled] = useState(false)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [allowedDomainsText, setAllowedDomainsText] = useState('')
  const [autoProvision, setAutoProvision] = useState(false)
  const [defaultRoleId, setDefaultRoleId] = useState<string>('')
  const [roles, setRoles] = useState<{ id: number; name: string; display_name: string }[]>([])

  const [redirectUri, setRedirectUri] = useState<string>('')

  useEffect(() => {
    if (typeof window !== 'undefined') {
      setRedirectUri(`${window.location.origin}/auth/google/callback`)
    }
  }, [])

  const fetchConfig = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const cfg = await api.getGlobalSSOConfig(false)
      setSsoConfig(cfg)
    } catch (err: any) {
      console.error('Failed to fetch global SSO config:', err)
      setError(err.message || 'Failed to load SSO configuration')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchRoles = useCallback(async () => {
    try {
      const res = await authenticatedFetch('/api/settings/sso/roles')
      if (!res.ok) throw new Error('Failed to load roles')
      const data: { id: number; name: string; display_name: string }[] = await res.json()
      setRoles(data)
    } catch (err) {
      console.warn('Could not load roles for SSO config:', err)
      setRoles([])
    }
  }, [])

  useEffect(() => {
    if (!authLoading && user) {
      fetchConfig()
      fetchRoles()
    }
  }, [authLoading, user, fetchConfig, fetchRoles])

  const openConfigureModal = () => {
    setEnabled(ssoConfig?.google_sso_enabled ?? false)
    setClientId(ssoConfig?.google_client_id ?? '')
    setClientSecret('')
    setAllowedDomainsText((ssoConfig?.allowed_domains ?? []).join(', '))
    setAutoProvision(ssoConfig?.auto_provision_users ?? false)
    setDefaultRoleId(ssoConfig?.default_role_id ? String(ssoConfig.default_role_id) : '')
    setError(null)
    setShowModal(true)
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const domains = allowedDomainsText
        .split(',')
        .map((d) => d.trim())
        .filter(Boolean)

      const payload: Parameters<typeof api.updateGlobalSSOConfig>[0] = {
        google_sso_enabled: enabled,
        google_client_id: clientId.trim() || null,
        allowed_domains: domains,
        auto_provision_users: autoProvision,
        default_role_id: defaultRoleId ? Number(defaultRoleId) : null,
      }

      if (clientSecret.trim()) {
        payload.google_client_secret = clientSecret.trim()
      }

      const updated = await api.updateGlobalSSOConfig(payload)
      setSsoConfig(updated)
      setShowModal(false)
      setClientSecret('')
      setSuccess('Google SSO configuration saved')
      setTimeout(() => setSuccess(null), 4000)
    } catch (err: any) {
      setError(err.message || 'Failed to save SSO configuration')
    } finally {
      setSaving(false)
    }
  }

  if (authLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-tsushin-slate">Loading...</div>
      </div>
    )
  }

  if (!user) return null

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-center space-x-3 mb-2">
          <h1 className="text-3xl font-display font-bold text-white">
            Global SSO
          </h1>
          <span className="px-3 py-1 bg-purple-500/20 text-purple-300 text-sm font-semibold rounded-full border border-purple-500/30">
            Global Admin
          </span>
        </div>
        <p className="text-tsushin-slate mb-8">
          Platform-wide Google OAuth. Applies to global-admin sign-in and cross-tenant Google auth.
        </p>

        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-800 dark:text-red-200">
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-2 text-red-500 hover:text-red-700"
            >
              ×
            </button>
          </div>
        )}
        {success && (
          <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4 text-green-800 dark:text-green-200">
            {success}
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-tsushin-border rounded-xl shadow-sm overflow-hidden mb-8">
          <div className="px-6 py-4 border-b border-gray-200 dark:border-tsushin-border bg-gray-50 dark:bg-tsushin-ink/60">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-red-500 flex items-center justify-center">
                <svg className="w-6 h-6 text-white" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Google SSO (Platform)</h3>
                <p className="text-sm text-gray-500 dark:text-tsushin-slate">
                  OAuth credentials used for global-admin and cross-tenant Google sign-in
                </p>
              </div>
              {ssoConfig?.google_sso_enabled ? (
                <span className="px-3 py-1 text-xs font-medium rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-200 dark:border-green-800">
                  Enabled
                </span>
              ) : (
                <span className="px-3 py-1 text-xs font-medium rounded-full bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
                  Disabled
                </span>
              )}
            </div>
          </div>

          <div className="p-6">
            {loading ? (
              <div className="text-center py-8 text-tsushin-slate">Loading configuration...</div>
            ) : ssoConfig ? (
              <div className="space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-tsushin-slate uppercase tracking-wider mb-1">
                      Client ID
                    </label>
                    <code className="block text-sm text-gray-900 dark:text-white bg-gray-50 dark:bg-tsushin-ink rounded px-3 py-2 font-mono break-all">
                      {ssoConfig.google_client_id || <span className="text-gray-400">— not set —</span>}
                    </code>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-tsushin-slate uppercase tracking-wider mb-1">
                      Client Secret
                    </label>
                    <code className="block text-sm text-gray-900 dark:text-white bg-gray-50 dark:bg-tsushin-ink rounded px-3 py-2 font-mono">
                      {ssoConfig.has_client_secret ? '••••••••••••••••' : <span className="text-gray-400">— not set —</span>}
                    </code>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-tsushin-slate uppercase tracking-wider mb-1">
                      Auto-provision users
                    </label>
                    <div className="text-sm text-gray-900 dark:text-white">
                      {ssoConfig.auto_provision_users ? (
                        <span className="inline-flex items-center px-2.5 py-1 bg-amber-100 dark:bg-amber-900/30 text-amber-900 dark:text-amber-300 rounded-md">
                          Enabled
                        </span>
                      ) : (
                        <span className="text-gray-500 dark:text-tsushin-slate">Disabled</span>
                      )}
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-500 dark:text-tsushin-slate uppercase tracking-wider mb-1">
                      Default role (auto-provisioned)
                    </label>
                    <div className="text-sm text-gray-900 dark:text-white">
                      {ssoConfig.default_role_name || <span className="text-gray-500 dark:text-tsushin-slate">—</span>}
                    </div>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 dark:text-tsushin-slate uppercase tracking-wider mb-1">
                    Allowed email domains
                  </label>
                  {ssoConfig.allowed_domains && ssoConfig.allowed_domains.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {ssoConfig.allowed_domains.map((d) => (
                        <span
                          key={d}
                          className="inline-flex items-center px-2.5 py-1 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 text-sm rounded-md"
                        >
                          @{d}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-sm text-gray-500 dark:text-tsushin-slate">
                      No domain restriction (any Google account allowed)
                    </span>
                  )}
                </div>
                <div className="pt-4 border-t border-gray-200 dark:border-tsushin-border">
                  <button
                    onClick={openConfigureModal}
                    className="btn-primary px-4 py-2 rounded-lg font-medium"
                  >
                    Configure
                  </button>
                </div>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500 dark:text-tsushin-slate mb-4">
                  Google SSO has not been configured yet.
                </p>
                <button
                  onClick={openConfigureModal}
                  className="btn-primary px-6 py-2 rounded-lg font-medium"
                >
                  Configure Google SSO
                </button>
              </div>
            )}
          </div>

          <div className="px-6 py-4 bg-amber-50 dark:bg-amber-900/10 border-t border-amber-100 dark:border-amber-900/30">
            <div className="flex gap-3">
              <svg className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="text-sm text-amber-800 dark:text-amber-200">
                <p className="font-medium mb-1">How to configure Google OAuth credentials:</p>
                <ol className="list-decimal list-inside space-y-1 text-amber-700 dark:text-amber-300">
                  <li>
                    Open the{' '}
                    <a
                      href="https://console.cloud.google.com/apis/credentials"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline hover:no-underline"
                    >
                      Google Cloud Console
                    </a>
                  </li>
                  <li>Create an OAuth 2.0 Client ID (Web application)</li>
                  <li>
                    Add authorized redirect URI:{' '}
                    <code className="bg-amber-100 dark:bg-amber-900/30 px-1.5 py-0.5 rounded text-xs">
                      {redirectUri || '<your-origin>/auth/google/callback'}
                    </code>
                  </li>
                  <li>Paste the Client ID and Client Secret into the Configure modal below.</li>
                </ol>
              </div>
            </div>
          </div>
        </div>

        <div className="glass-card rounded-lg p-4 text-sm text-tsushin-slate">
          Signed in as <span className="font-medium text-white">{user.email}</span>{' '}
          with Global Admin privileges.
        </div>

        {showModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto">
            <div className="bg-white dark:bg-tsushin-surface rounded-2xl border border-gray-200 dark:border-tsushin-border shadow-xl max-w-2xl w-full my-8">
              <div className="px-6 py-4 border-b border-gray-200 dark:border-tsushin-border">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Configure Google SSO (Platform-wide)
                </h3>
              </div>

              <div className="p-6 space-y-5">
                <label className="flex items-center justify-between gap-3 p-3 border border-gray-200 dark:border-tsushin-border rounded-lg">
                  <div>
                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                      Google SSO enabled
                    </div>
                    <div className="text-xs text-gray-500 dark:text-tsushin-slate">
                      Turn platform-wide Google sign-in on or off
                    </div>
                  </div>
                  <input
                    type="checkbox"
                    checked={enabled}
                    onChange={(e) => setEnabled(e.target.checked)}
                    className="h-5 w-5"
                  />
                </label>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Client ID
                  </label>
                  <input
                    type="text"
                    value={clientId}
                    onChange={(e) => setClientId(e.target.value)}
                    placeholder="xxxxx.apps.googleusercontent.com"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-tsushin-border rounded-lg bg-white dark:bg-tsushin-elevated text-gray-900 dark:text-white placeholder-gray-400"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Client Secret
                  </label>
                  <input
                    type="password"
                    value={clientSecret}
                    onChange={(e) => setClientSecret(e.target.value)}
                    placeholder={ssoConfig?.has_client_secret ? '••• (unchanged)' : 'GOCSPX-xxxxx'}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-tsushin-border rounded-lg bg-white dark:bg-tsushin-elevated text-gray-900 dark:text-white placeholder-gray-400"
                  />
                  {ssoConfig?.has_client_secret && (
                    <p className="text-xs text-gray-500 dark:text-tsushin-slate mt-1">
                      Leave blank to keep the existing secret.
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Allowed email domains (comma-separated)
                  </label>
                  <input
                    type="text"
                    value={allowedDomainsText}
                    onChange={(e) => setAllowedDomainsText(e.target.value)}
                    placeholder="example.com, partner.com"
                    className="w-full px-3 py-2 border border-gray-300 dark:border-tsushin-border rounded-lg bg-white dark:bg-tsushin-elevated text-gray-900 dark:text-white placeholder-gray-400"
                  />
                  <p className="text-xs text-gray-500 dark:text-tsushin-slate mt-1">
                    Leave empty to allow any Google account. Used as a whitelist for auto-provisioning.
                  </p>
                </div>

                <div className="p-3 border border-amber-300 dark:border-amber-700/50 bg-amber-50 dark:bg-amber-900/10 rounded-lg">
                  <label className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={autoProvision}
                      onChange={(e) => setAutoProvision(e.target.checked)}
                      className="mt-1 h-5 w-5"
                    />
                    <div className="flex-1">
                      <div className="text-sm font-medium text-gray-900 dark:text-white">
                        Auto-provision users
                      </div>
                      <div className="text-xs font-bold text-red-700 dark:text-red-400 mt-1">
                        Auto-provisioning is disabled by default. Enable only with a strict domain whitelist —
                        users matching whitelisted domains will be auto-created.
                      </div>
                    </div>
                  </label>
                </div>

                {autoProvision && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Default role for auto-provisioned users
                    </label>
                    <select
                      value={defaultRoleId}
                      onChange={(e) => setDefaultRoleId(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-tsushin-border rounded-lg bg-white dark:bg-tsushin-elevated text-gray-900 dark:text-white"
                    >
                      <option value="">— Select a role —</option>
                      {roles.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.display_name}
                        </option>
                      ))}
                    </select>
                    {roles.length === 0 && (
                      <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                        Could not load role list. Default role cannot be set until roles are available.
                      </p>
                    )}
                    <p className="text-xs text-gray-500 dark:text-tsushin-slate mt-1">
                      Only used when Auto-provision users is enabled.
                    </p>
                  </div>
                )}
              </div>

              <div className="px-6 py-4 border-t border-gray-200 dark:border-tsushin-border flex justify-end gap-3">
                <button
                  onClick={() => { setShowModal(false); setClientSecret('') }}
                  className="px-4 py-2 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-tsushin-elevated rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="btn-primary px-4 py-2 rounded-lg font-medium disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save Configuration'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
