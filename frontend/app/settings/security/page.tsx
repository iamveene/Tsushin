'use client'

/**
 * Security Settings Page
 * Configure SSO policies and authentication settings for the tenant
 *
 * Google OAuth credentials are configured centrally in Settings/Integrations.
 * This page manages SSO-specific policies (enable/disable, domain restrictions, auto-provisioning).
 */

import { useState, useEffect, useCallback } from 'react'
import { useRequireAuth } from '@/contexts/AuthContext'
import { api, SSOConfig, PlatformSSOStatus, SSOConfigUpdate } from '@/lib/client'
import Link from 'next/link'

// Type for Google credentials from Hub API
interface GoogleCredentials {
  id: number
  tenant_id: string
  client_id: string
  redirect_uri: string | null
  created_at: string
}

export default function SecuritySettingsPage() {
  const { user, loading: authLoading, hasPermission } = useRequireAuth()
  const canEdit = hasPermission('org.settings.write')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [platformStatus, setPlatformStatus] = useState<PlatformSSOStatus | null>(null)
  const [ssoConfig, setSSOConfig] = useState<SSOConfig | null>(null)
  const [googleCredentials, setGoogleCredentials] = useState<GoogleCredentials | null>(null)
  const [availableRoles, setAvailableRoles] = useState<Array<{
    id: number
    name: string
    display_name: string
    description: string | null
  }>>([])

  // Form state (SSO policies only - credentials are in Settings/Integrations)
  const [googleEnabled, setGoogleEnabled] = useState(false)
  const [allowedDomains, setAllowedDomains] = useState('')
  const [autoProvision, setAutoProvision] = useState(false)
  const [defaultRoleId, setDefaultRoleId] = useState<number | null>(null)

  // Encryption keys state
  const [googleEncryptionKey, setGoogleEncryptionKey] = useState('')
  const [asanaEncryptionKey, setAsanaEncryptionKey] = useState('')
  const [showGoogleKey, setShowGoogleKey] = useState(false)
  const [showAsanaKey, setShowAsanaKey] = useState(false)
  const [encryptionKeySaving, setEncryptionKeySaving] = useState(false)
  const [encryptionKeySuccess, setEncryptionKeySuccess] = useState<string | null>(null)
  const [encryptionKeyError, setEncryptionKeyError] = useState<string | null>(null)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

  // Fetch Google credentials from centralized location
  const fetchGoogleCredentials = useCallback(async () => {
    try {
      const token = localStorage.getItem('tsushin_auth_token')
      const response = await fetch(`${apiUrl}/api/hub/google/credentials`, {
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        }
      })

      if (response.ok) {
        const data = await response.json()
        setGoogleCredentials(data)
      } else if (response.status === 404) {
        setGoogleCredentials(null)
      }
    } catch (err) {
      console.error('Error fetching Google credentials:', err)
    }
  }, [apiUrl])

  // Fetch encryption keys from config
  const fetchEncryptionKeys = useCallback(async () => {
    try {
      const token = localStorage.getItem('tsushin_auth_token')
      const response = await fetch(`${apiUrl}/api/config`, {
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        }
      })

      if (response.ok) {
        const config = await response.json()
        setGoogleEncryptionKey(config.google_encryption_key || '')
        setAsanaEncryptionKey(config.asana_encryption_key || '')
      }
    } catch (err) {
      console.error('Error fetching encryption keys:', err)
    }
  }, [apiUrl])

  // Fetch SSO config
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [status, config, roles] = await Promise.all([
        api.getPlatformSSOStatus(),
        api.getSSOConfig(),
        api.getSSOAvailableRoles(),
      ])

      setPlatformStatus(status)
      setSSOConfig(config)
      setAvailableRoles(roles)

      // Initialize form state
      setGoogleEnabled(config.google_sso_enabled)
      setAllowedDomains(config.allowed_domains.join(', '))
      setAutoProvision(config.auto_provision_users)
      setDefaultRoleId(config.default_role_id)
    } catch (err: any) {
      console.error('Failed to fetch SSO config:', err)
      setError(err.message || 'Failed to load security settings')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!authLoading && user) {
      Promise.all([fetchData(), fetchGoogleCredentials(), fetchEncryptionKeys()])
    }
  }, [fetchData, fetchGoogleCredentials, fetchEncryptionKeys, authLoading, user])

  // Handle save encryption keys
  const handleSaveEncryptionKeys = async () => {
    setEncryptionKeySaving(true)
    setEncryptionKeyError(null)
    setEncryptionKeySuccess(null)

    try {
      const token = localStorage.getItem('tsushin_auth_token')
      const updateData: any = {}

      if (googleEncryptionKey) updateData.google_encryption_key = googleEncryptionKey
      if (asanaEncryptionKey) updateData.asana_encryption_key = asanaEncryptionKey

      const response = await fetch(`${apiUrl}/api/config`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: JSON.stringify(updateData)
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || 'Failed to save encryption keys')
      }

      setEncryptionKeySuccess('Encryption keys saved successfully')

      // Note: After changing encryption keys, OAuth tokens will need re-authentication
      if (googleEncryptionKey) {
        setEncryptionKeySuccess('Encryption keys saved. Note: Existing OAuth tokens will need re-authentication.')
      }
    } catch (err: any) {
      setEncryptionKeyError(err.message || 'Failed to save encryption keys')
    } finally {
      setEncryptionKeySaving(false)
    }
  }

  // Handle save
  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const updateData: SSOConfigUpdate = {
        google_sso_enabled: googleEnabled,
        allowed_domains: allowedDomains
          .split(',')
          .map(d => d.trim().toLowerCase())
          .filter(d => d),
        auto_provision_users: autoProvision,
        default_role_id: defaultRoleId,
      }

      const updated = await api.updateSSOConfig(updateData)
      setSSOConfig(updated)
      setSuccess('Security settings saved successfully')
    } catch (err: any) {
      setError(err.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
      </div>
    )
  }

  // SSO can be used if either Google credentials are configured OR platform-wide SSO is available
  const hasGoogleCredentials = !!googleCredentials
  const canUseSSO = hasGoogleCredentials || platformStatus?.platform_sso_available

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Security Settings
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            Configure authentication and single sign-on policies for your organization
          </p>
        </div>

        {/* Back to Settings */}
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Settings
        </Link>

        {/* Error/Success Messages */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
          </div>
        )}

        {success && (
          <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
            <p className="text-sm text-green-800 dark:text-green-200">{success}</p>
          </div>
        )}

        {/* Google OAuth Status Banner */}
        <div className={`rounded-lg shadow-md p-6 mb-6 ${
          hasGoogleCredentials
            ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
            : 'bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800'
        }`}>
          <div className="flex items-start gap-4">
            <div className={`w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0 ${
              hasGoogleCredentials
                ? 'bg-green-100 dark:bg-green-900/50'
                : 'bg-amber-100 dark:bg-amber-900/50'
            }`}>
              {hasGoogleCredentials ? (
                <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-6 h-6 text-amber-600 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              )}
            </div>
            <div className="flex-1">
              <h2 className={`text-lg font-semibold mb-1 ${
                hasGoogleCredentials
                  ? 'text-green-900 dark:text-green-100'
                  : 'text-amber-900 dark:text-amber-100'
              }`}>
                Google OAuth {hasGoogleCredentials ? 'Configured' : 'Not Configured'}
              </h2>
              {hasGoogleCredentials ? (
                <p className="text-sm text-green-700 dark:text-green-300 mb-3">
                  Google OAuth credentials are configured. You can enable Google Sign-In below.
                </p>
              ) : (
                <p className="text-sm text-amber-700 dark:text-amber-300 mb-3">
                  Google OAuth credentials are required to enable Google Sign-In.
                  Configure them in the Integrations settings.
                </p>
              )}
              <Link
                href="/settings/integrations"
                className={`inline-flex items-center gap-2 text-sm font-medium ${
                  hasGoogleCredentials
                    ? 'text-green-700 hover:text-green-800 dark:text-green-300 dark:hover:text-green-200'
                    : 'text-amber-700 hover:text-amber-800 dark:text-amber-300 dark:hover:text-amber-200'
                }`}
              >
                {hasGoogleCredentials ? 'Manage Google Integration' : 'Configure Google Integration'}
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            </div>
          </div>
        </div>

        {/* Google SSO Configuration */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-3">
              <svg className="w-6 h-6" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
              </svg>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Google Sign-In Policy
              </h3>
            </div>
          </div>

          <div className="p-6 space-y-6">
            {/* Enable/Disable Toggle */}
            <div className="flex items-center justify-between">
              <div>
                <label className="font-medium text-gray-900 dark:text-gray-100">
                  Enable Google Sign-In
                </label>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Allow users to sign in using their Google account
                </p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={googleEnabled}
                  onChange={(e) => setGoogleEnabled(e.target.checked)}
                  disabled={!canEdit || !canUseSSO}
                  className="sr-only peer"
                />
                <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600 peer-disabled:opacity-50 peer-disabled:cursor-not-allowed"></div>
              </label>
            </div>

            {!canUseSSO && (
              <div className="p-3 bg-gray-100 dark:bg-gray-700 rounded-lg">
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  Google Sign-In cannot be enabled until Google OAuth credentials are configured.
                </p>
              </div>
            )}

            {/* Domain Restrictions */}
            <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
              <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
                Domain Restrictions
              </h4>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Allowed Email Domains
                </label>
                <input
                  type="text"
                  value={allowedDomains}
                  onChange={(e) => setAllowedDomains(e.target.value)}
                  disabled={!canEdit}
                  placeholder="example.com, company.org"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 disabled:opacity-50"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  Comma-separated list of allowed email domains. Leave empty to allow all domains.
                </p>
              </div>
            </div>

            {/* Auto-provisioning */}
            <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
              <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-4">
                User Provisioning
              </h4>

              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <label className="font-medium text-gray-900 dark:text-gray-100">
                      Auto-provision new users
                    </label>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Automatically create accounts for users who sign in with Google
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoProvision}
                      onChange={(e) => setAutoProvision(e.target.checked)}
                      disabled={!canEdit}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600 peer-disabled:opacity-50 peer-disabled:cursor-not-allowed"></div>
                  </label>
                </div>

                {autoProvision && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Default Role for New Users
                    </label>
                    <select
                      value={defaultRoleId || ''}
                      onChange={(e) => setDefaultRoleId(e.target.value ? parseInt(e.target.value) : null)}
                      disabled={!canEdit}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 disabled:opacity-50"
                    >
                      <option value="">Select a role...</option>
                      {availableRoles.map((role) => (
                        <option key={role.id} value={role.id}>
                          {role.display_name}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      New users will be assigned this role automatically
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Save Button */}
          {canEdit && (
            <div className="px-6 py-4 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700">
              <div className="flex justify-end">
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md disabled:opacity-50 transition-colors"
                >
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Encryption Keys Configuration */}
        <div className="mt-6 bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-3">
              <svg className="w-6 h-6 text-gray-700 dark:text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Encryption Keys
              </h3>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
              Fernet encryption keys for OAuth token storage. Generate new keys with: <code className="text-xs bg-gray-100 dark:bg-gray-700 px-1 py-0.5 rounded">python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"</code>
            </p>
          </div>

          {/* Error/Success Messages */}
          {encryptionKeyError && (
            <div className="mx-6 mt-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
              <p className="text-sm text-red-800 dark:text-red-200">{encryptionKeyError}</p>
            </div>
          )}

          {encryptionKeySuccess && (
            <div className="mx-6 mt-4 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
              <p className="text-sm text-green-800 dark:text-green-200">{encryptionKeySuccess}</p>
            </div>
          )}

          <div className="p-6 space-y-6">
            {/* Google Encryption Key */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Google Encryption Key
              </label>
              <div className="relative">
                <input
                  type={showGoogleKey ? "text" : "password"}
                  value={googleEncryptionKey}
                  onChange={(e) => setGoogleEncryptionKey(e.target.value)}
                  disabled={!canEdit}
                  placeholder="Enter Fernet encryption key"
                  className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 disabled:opacity-50 font-mono text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowGoogleKey(!showGoogleKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                >
                  {showGoogleKey ? (
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Used for encrypting Google OAuth tokens (Gmail, Calendar)
              </p>
            </div>

            {/* Asana Encryption Key */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Hub Encryption Key
              </label>
              <div className="relative">
                <input
                  type={showAsanaKey ? "text" : "password"}
                  value={asanaEncryptionKey}
                  onChange={(e) => setAsanaEncryptionKey(e.target.value)}
                  disabled={!canEdit}
                  placeholder="Enter Fernet encryption key"
                  className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 disabled:opacity-50 font-mono text-sm"
                />
                <button
                  type="button"
                  onClick={() => setShowAsanaKey(!showAsanaKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                >
                  {showAsanaKey ? (
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Used for encrypting Asana, Amadeus, and Telegram OAuth tokens
              </p>
            </div>

            {/* Warning */}
            <div className="p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
              <div className="flex gap-3">
                <svg className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div>
                  <p className="text-sm font-medium text-amber-900 dark:text-amber-100">Warning</p>
                  <p className="text-sm text-amber-800 dark:text-amber-200 mt-1">
                    Changing encryption keys will invalidate all existing encrypted OAuth tokens.
                    Users will need to re-authenticate their integrations (Gmail, Calendar, Asana, etc.).
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Save Button */}
          {canEdit && (
            <div className="px-6 py-4 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700">
              <div className="flex justify-end">
                <button
                  onClick={handleSaveEncryptionKeys}
                  disabled={encryptionKeySaving || (!googleEncryptionKey && !asanaEncryptionKey)}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md disabled:opacity-50 transition-colors"
                >
                  {encryptionKeySaving ? 'Saving...' : 'Save Encryption Keys'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Additional Info */}
        <div className="mt-6 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-100 mb-2">
            How Google Sign-In Works
          </h4>
          <ul className="text-sm text-blue-800 dark:text-blue-200 space-y-1 list-disc list-inside">
            <li>Users can sign in with their Google account from the login page</li>
            <li>If a user's email is already registered, their accounts will be linked</li>
            <li>With auto-provisioning, new users are created automatically</li>
            <li>Domain restrictions limit which email addresses can sign in</li>
          </ul>
        </div>
      </div>
    </div>
  )
}
