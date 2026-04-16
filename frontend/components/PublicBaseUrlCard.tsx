'use client'

/**
 * v0.6.0 V060-CHN-002: Public Base URL settings card.
 *
 * Slack HTTP Events mode and Discord Interactions endpoint both require a
 * publicly-reachable HTTPS URL pointing at the Tsushin backend (port 8081).
 * This card lets a tenant admin configure that URL once so the Slack/Discord
 * setup modals can render the exact webhook URL the user must paste back into
 * the third-party portal.
 *
 * Slack Socket Mode does NOT need this — the bot dials out to Slack instead.
 */

import { useEffect, useState } from 'react'
import { api } from '@/lib/client'

interface Props {
  canEdit: boolean
}

export default function PublicBaseUrlCard({ canEdit }: Props) {
  const [value, setValue] = useState('')
  const [savedValue, setSavedValue] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .getMyTenantSettings()
      .then(s => {
        if (cancelled) return
        setSavedValue(s.public_base_url)
        setValue(s.public_base_url || '')
      })
      .catch(err => {
        if (!cancelled) setError(err?.message || 'Failed to load tenant settings')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const trimmed = value.trim()
  const isHttp = trimmed === '' || trimmed.startsWith('http://') || trimmed.startsWith('https://')

  const handleSave = async () => {
    if (!isHttp) return
    setSaving(true)
    setError(null)
    setStatusMessage(null)
    try {
      const next = trimmed === '' ? null : trimmed.replace(/\/+$/, '')
      const updated = await api.updateMyTenantSettings({ public_base_url: next })
      setSavedValue(updated.public_base_url)
      setValue(updated.public_base_url || '')
      setStatusMessage(updated.public_base_url ? 'Public base URL saved' : 'Public base URL cleared')
    } catch (err: any) {
      setError(err?.message || 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card p-4 border border-tsushin-border/60">
      <div className="flex flex-col gap-3">
        <div>
          <h4 className="text-sm font-semibold text-white">Public Base URL</h4>
          <p className="text-xs text-tsushin-slate">
            HTTPS URL where Slack (HTTP Events mode) and Discord (Interactions endpoint) can reach this
            Tsushin backend. Used by the setup modals to show you the exact webhook URL to paste back.
            Slack Socket Mode does <strong>not</strong> need this. For local dev:{' '}
            <code className="px-1 bg-tsushin-elevated rounded text-amber-300">cloudflared tunnel --url http://localhost:8081</code>.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="text"
              value={value}
              placeholder="https://your-tunnel.trycloudflare.com"
              onChange={(e) => { setValue(e.target.value); setStatusMessage(null) }}
              className="input flex-1 min-w-[280px] text-sm font-mono"
              disabled={!canEdit || saving || loading}
            />
            <button
              onClick={handleSave}
              className="px-4 py-2 bg-teal-600/20 text-teal-300 border border-teal-600/50 rounded text-xs disabled:opacity-50"
              disabled={!canEdit || saving || loading || !isHttp || trimmed === (savedValue || '')}
            >
              {saving ? 'Saving...' : 'Save URL'}
            </button>
          </div>

          {!isHttp && (
            <p className="text-xs text-amber-300">
              Must start with <code className="px-1 bg-tsushin-elevated rounded">https://</code> (or{' '}
              <code className="px-1 bg-tsushin-elevated rounded">http://</code> for local-only testing).
            </p>
          )}

          {error && <p className="text-xs text-red-400">{error}</p>}
          {statusMessage && <p className="text-xs text-emerald-300">{statusMessage}</p>}

          {!canEdit && (
            <p className="text-xs text-amber-300">
              You need <code className="px-1 bg-tsushin-elevated rounded">org.settings.write</code> permission to edit this value.
            </p>
          )}

          {savedValue && (
            <p className="text-xs text-tsushin-slate">
              Currently saved:{' '}
              <code className="px-1 bg-tsushin-elevated rounded text-tsushin-fog">{savedValue}</code>
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
