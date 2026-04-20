'use client'

import { useEffect, useState } from 'react'
import { authenticatedFetch } from '@/lib/client'

interface GoogleCredentials {
  id: number
  tenant_id: string
  client_id: string
  redirect_uri: string | null
  configured?: boolean
}

interface Props {
  /** Called with `configured: true` once the tenant has Google OAuth credentials */
  onReady: () => void
  /** Visual accent used by the parent wizard */
  tone?: 'gmail' | 'calendar'
}

const TONE_CLASSES: Record<NonNullable<Props['tone']>, { button: string; ring: string; badge: string }> = {
  gmail: {
    button: 'bg-red-600 hover:bg-red-700 text-white',
    ring: 'focus:ring-red-500',
    badge: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800',
  },
  calendar: {
    button: 'bg-blue-600 hover:bg-blue-700 text-white',
    ring: 'focus:ring-blue-500',
    badge: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800',
  },
}

/**
 * Reusable wizard step that ensures the tenant has configured Google OAuth
 * application credentials before any downstream Gmail / Calendar OAuth flow
 * can start.
 *
 * - On mount: GET /api/hub/google/credentials. If `configured: true`, shows
 *   the "Using existing credentials" panel and calls onReady() so the parent
 *   wizard can move forward once the user confirms.
 * - If not configured: renders the client_id / client_secret form (mirrors
 *   the form used by the Integrations settings page) and POSTs to the same
 *   endpoint.
 *
 * Credentials are stored per-tenant; the POST and GET are both scoped via
 * the authenticated session (see routes_google.py tenant filter).
 */
export default function GoogleAppCredentialsStep({ onReady, tone = 'gmail' }: Props) {
  const [loading, setLoading] = useState(true)
  const [credentials, setCredentials] = useState<GoogleCredentials | null>(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  const t = TONE_CLASSES[tone]

  const fetchCredentials = async () => {
    setLoading(true)
    try {
      const response = await authenticatedFetch('/api/hub/google/credentials')
      if (response.ok) {
        const data = await response.json()
        const configured = data && data.configured !== false
        setCredentials(configured ? data : null)
      } else {
        setCredentials(null)
      }
    } catch (e: any) {
      setError('Could not load Google credentials')
      setCredentials(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCredentials()
  }, [])

  const save = async () => {
    if (!clientId.trim()) { setError('Client ID is required'); return }
    if (!credentials && !clientSecret.trim()) { setError('Client Secret is required'); return }
    setSaving(true)
    setError(null)
    try {
      const response = await authenticatedFetch('/api/hub/google/credentials', {
        method: 'POST',
        body: JSON.stringify({
          client_id: clientId.trim(),
          client_secret: clientSecret.trim() || undefined,
        }),
      })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }
      setClientSecret('')
      setEditing(false)
      await fetchCredentials()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="py-10 flex items-center justify-center text-gray-400">
        Checking Google OAuth credentials…
      </div>
    )
  }

  if (credentials && !editing) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <span className={`px-2.5 py-1 text-xs font-medium rounded-full border ${t.badge}`}>
            Connected
          </span>
          <span className="text-sm text-gray-300">
            Your tenant already has Google OAuth credentials configured.
          </span>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1">Client ID</label>
          <code className="block text-xs text-gray-100 bg-gray-900 rounded px-3 py-2 font-mono break-all">
            {credentials.client_id}
          </code>
        </div>
        <p className="text-sm text-gray-400">
          We&apos;ll use these credentials to authorize your {tone === 'gmail' ? 'Gmail' : 'Calendar'} account. If you prefer to use a
          different Google Cloud project, you can replace them now.
        </p>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setClientId(credentials.client_id)
              setClientSecret('')
              setEditing(true)
            }}
            className="px-3 py-2 text-sm bg-gray-700 hover:bg-gray-600 text-gray-100 rounded"
          >
            Replace credentials
          </button>
          <button
            type="button"
            onClick={onReady}
            className={`px-4 py-2 text-sm rounded font-medium ${t.button}`}
          >
            Use these credentials
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg p-4 text-sm text-amber-100">
        <p className="font-medium mb-2">How to get Google OAuth credentials</p>
        <ol className="list-decimal list-inside space-y-1 text-amber-200/90">
          <li>Open the <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer" className="underline">Google Cloud Console</a></li>
          <li>Create an OAuth 2.0 Client ID (Web application)</li>
          <li>Add redirect URI: <code className="bg-amber-900/30 px-1 py-0.5 rounded text-xs">/api/hub/google/oauth/callback</code></li>
          <li>Copy the Client ID and Client Secret below</li>
        </ol>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-200 mb-1">
          Client ID <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          placeholder="xxxxx.apps.googleusercontent.com"
          className={`w-full px-3 py-2 border border-gray-600 rounded-lg bg-gray-700 text-white placeholder-gray-400 focus:ring-2 focus:border-transparent ${t.ring}`}
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-200 mb-1">
          Client Secret {!credentials && <span className="text-red-400">*</span>}
        </label>
        <input
          type="password"
          value={clientSecret}
          onChange={(e) => setClientSecret(e.target.value)}
          placeholder={credentials ? '(leave blank to keep current)' : 'GOCSPX-xxxxx'}
          className={`w-full px-3 py-2 border border-gray-600 rounded-lg bg-gray-700 text-white placeholder-gray-400 focus:ring-2 focus:border-transparent ${t.ring}`}
        />
      </div>

      {error && (
        <div className="text-sm text-red-400 bg-red-900/20 border border-red-700/40 rounded px-3 py-2">
          {error}
        </div>
      )}

      <div className="flex items-center gap-3">
        {editing && (
          <button
            type="button"
            onClick={() => { setEditing(false); setError(null) }}
            className="px-3 py-2 text-sm bg-gray-700 hover:bg-gray-600 text-gray-100 rounded"
          >
            Cancel
          </button>
        )}
        <button
          type="button"
          onClick={async () => {
            await save()
            // After a successful save, credentials refreshes; parent advances
            // when the user clicks "Use these credentials" in the confirmed panel.
          }}
          disabled={saving || !clientId.trim()}
          className={`px-4 py-2 text-sm rounded font-medium ${t.button} disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {saving ? 'Saving…' : 'Save credentials'}
        </button>
      </div>
    </div>
  )
}
