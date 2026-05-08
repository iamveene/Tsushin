'use client'

import { useEffect, useState } from 'react'
import Modal from '@/components/ui/Modal'
import { GlobeIcon, PlayIcon } from '@/components/ui/icons'
import type {
  BrowserSessionProfile,
  BrowserSessionProfileCreateRequest,
  BrowserSessionProfileUpdateRequest,
  BrowserSessionProfileTestResponse,
} from '@/lib/client'

type BrowserSessionDraft = {
  integration_name: string
  profile_name: string
  provider_type: string
  mode: string
  browser_type: string
  headless: boolean
  timeout_seconds: number
  viewport_width: number
  viewport_height: number
  session_ttl_seconds: number
  cdp_url: string
  storage_state_json: string
  clear_storage_state: boolean
  is_active: boolean
}

export type BrowserSessionSaveDraft =
  | BrowserSessionProfileCreateRequest
  | BrowserSessionProfileUpdateRequest

function statusClasses(status?: string | null): string {
  const normalized = (status || '').toLowerCase()
  if (['healthy', 'success', 'ok', 'active', 'connected'].includes(normalized)) return 'border-green-500/30 bg-green-500/10 text-green-300'
  if (['unhealthy', 'error', 'failed', 'disconnected'].includes(normalized)) return 'border-red-500/30 bg-red-500/10 text-red-300'
  if (['degraded', 'warning'].includes(normalized)) return 'border-yellow-500/30 bg-yellow-500/10 text-yellow-300'
  return 'border-tsushin-border bg-tsushin-slate/10 text-tsushin-slate'
}

function draftFromTarget(target: BrowserSessionProfile | null): BrowserSessionDraft {
  return {
    // Pre-fix the create-form defaults included an operator-specific
    // example value ("EDP browser session", "edp") leaking a real
    // customer name into the public UI. Replaced with neutral
    // placeholders.
    integration_name: target?.integration_name || 'My saved login',
    profile_name: target?.profile_name || 'my_login',
    provider_type: target?.provider_type || 'playwright',
    mode: target?.mode || 'container',
    browser_type: target?.browser_type || 'chromium',
    headless: target?.headless ?? true,
    timeout_seconds: target?.timeout_seconds || 45,
    viewport_width: target?.viewport_width || 1280,
    viewport_height: target?.viewport_height || 720,
    session_ttl_seconds: target?.session_ttl_seconds || 900,
    cdp_url: target?.cdp_url || 'http://host.docker.internal:9222',
    storage_state_json: '',
    clear_storage_state: false,
    is_active: target?.is_active ?? true,
  }
}

export function BrowserSessionProfileModal({
  isOpen,
  target,
  saving,
  onClose,
  onSave,
}: {
  isOpen: boolean
  target: BrowserSessionProfile | null
  saving: boolean
  onClose: () => void
  onSave: (draft: BrowserSessionDraft) => void
}) {
  const [draft, setDraft] = useState<BrowserSessionDraft>(() => draftFromTarget(target))
  const [jsonError, setJsonError] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen) {
      setDraft(draftFromTarget(target))
      setJsonError(null)
    }
  }, [isOpen, target])

  const canSave = Boolean(draft.integration_name.trim() && draft.profile_name.trim() && !saving && !jsonError)

  function updateStorageState(value: string) {
    setDraft((current) => ({ ...current, storage_state_json: value }))
    if (!value.trim()) {
      setJsonError(null)
      return
    }
    try {
      const parsed = JSON.parse(value)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('JSON must be an object')
      setJsonError(null)
    } catch (error: any) {
      setJsonError(error?.message || 'Invalid JSON')
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={target ? 'Edit Browser Session Profile' : 'Add Browser Session Profile'}
      footer={(
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="rounded-lg border border-tsushin-border px-4 py-2 text-sm text-tsushin-slate hover:text-white disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onSave(draft)}
            disabled={!canSave}
            className="rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      )}
      size="xl"
    >
      <div className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Profile name</label>
            <input
              type="text"
              value={draft.profile_name}
              onChange={(event) => setDraft((current) => ({ ...current, profile_name: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 font-mono text-white"
              placeholder="edp"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Display name</label>
            <input
              type="text"
              value={draft.integration_name}
              onChange={(event) => setDraft((current) => ({ ...current, integration_name: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
              placeholder="My saved login"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Provider</label>
            <select
              value={draft.provider_type}
              onChange={(event) => setDraft((current) => ({ ...current, provider_type: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
            >
              <option value="playwright">Playwright container</option>
              <option value="cdp">Chrome CDP host</option>
            </select>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Mode</label>
            <select
              value={draft.mode}
              onChange={(event) => setDraft((current) => ({ ...current, mode: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
            >
              <option value="container">Container</option>
              <option value="cdp">CDP</option>
            </select>
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Timeout seconds</label>
            <input
              type="number"
              min={1}
              max={180}
              value={draft.timeout_seconds}
              onChange={(event) => setDraft((current) => ({ ...current, timeout_seconds: Number(event.target.value) || 45 }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Session TTL seconds</label>
            <input
              type="number"
              min={0}
              max={86400}
              value={draft.session_ttl_seconds}
              onChange={(event) => setDraft((current) => ({ ...current, session_ttl_seconds: Number(event.target.value) || 900 }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Viewport width</label>
            <input
              type="number"
              min={320}
              value={draft.viewport_width}
              onChange={(event) => setDraft((current) => ({ ...current, viewport_width: Number(event.target.value) || 1280 }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
            />
          </div>
          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">Viewport height</label>
            <input
              type="number"
              min={240}
              value={draft.viewport_height}
              onChange={(event) => setDraft((current) => ({ ...current, viewport_height: Number(event.target.value) || 720 }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-white"
            />
          </div>
          <div className="md:col-span-2">
            <label className="mb-2 block text-sm font-medium text-gray-300">CDP URL</label>
            <input
              type="url"
              value={draft.cdp_url}
              onChange={(event) => setDraft((current) => ({ ...current, cdp_url: event.target.value }))}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 font-mono text-white"
              placeholder="http://host.docker.internal:9222"
            />
          </div>
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-gray-300">
            Storage state JSON <span className="text-xs text-tsushin-slate">(optional; leave blank to keep current)</span>
          </label>
          <textarea
            value={draft.storage_state_json}
            onChange={(event) => updateStorageState(event.target.value)}
            className="min-h-[180px] w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 font-mono text-xs text-white"
            placeholder='{"cookies":[],"origins":[]}'
            spellCheck={false}
          />
          {jsonError ? <p className="mt-1 text-xs text-red-300">{jsonError}</p> : null}
        </div>

        {target?.has_storage_state ? (
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={draft.clear_storage_state}
              onChange={(event) => setDraft((current) => ({ ...current, clear_storage_state: event.target.checked }))}
            />
            Clear the imported storage state
          </label>
        ) : null}

        <div className="grid gap-2 text-sm text-gray-300 md:grid-cols-2">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.headless}
              onChange={(event) => setDraft((current) => ({ ...current, headless: event.target.checked }))}
            />
            Headless browser
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draft.is_active}
              onChange={(event) => setDraft((current) => ({ ...current, is_active: event.target.checked }))}
            />
            Enable this profile
          </label>
        </div>
      </div>
    </Modal>
  )
}

export function BrowserSessionProfilesPanel({
  profiles,
  loading,
  saving,
  testingId,
  testResults,
  canWriteHub,
  onAdd,
  onEdit,
  onDelete,
  onTest,
}: {
  profiles: BrowserSessionProfile[]
  loading: boolean
  saving: boolean
  testingId: number | null
  testResults: Record<number, BrowserSessionProfileTestResponse>
  canWriteHub: boolean
  onAdd: () => void
  onEdit: (profile: BrowserSessionProfile) => void
  onDelete: (profile: BrowserSessionProfile) => void
  onTest: (profile: BrowserSessionProfile) => void
}) {
  return (
    <div className="card p-5 hover-glow group border-cyan-700/30">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10">
            <GlobeIcon size={20} className="text-cyan-300" />
          </div>
          <div>
            <h3 className="font-semibold text-white">Saved Browser Logins</h3>
            <p className="text-xs text-tsushin-slate">
              Capture a logged-in browser session once, reuse it from any Browser Automation flow step — so the flow doesn&apos;t need to log in every run.
            </p>
          </div>
        </div>
        {canWriteHub ? (
          <button type="button" onClick={onAdd} className="rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-cyan-500">
            + Add
          </button>
        ) : null}
      </div>

      {loading ? (
        <div className="rounded-lg border border-white/5 bg-tsushin-ink/40 p-4 text-center text-xs text-tsushin-slate">Loading...</div>
      ) : profiles.length === 0 ? (
        <div className="rounded-lg border border-dashed border-tsushin-border/60 bg-tsushin-ink/30 p-4 text-sm text-tsushin-slate">
          Click <strong className="text-white">+ Add</strong> to capture a browser session you&apos;re already logged into, then pick this saved login by name from any Browser Automation flow step.
        </div>
      ) : (
        <div className="space-y-3">
          {profiles.map((profile) => {
            const summary = profile.storage_state_summary || {}
            const result = testResults[profile.id]
            return (
              <div key={profile.id} className="rounded-lg border border-tsushin-border bg-tsushin-ink/40 p-3">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-white">{profile.integration_name}</span>
                      <span className="rounded bg-cyan-500/10 px-2 py-0.5 font-mono text-[11px] text-cyan-200">{profile.profile_name}</span>
                      <span className={`rounded-full border px-2 py-0.5 text-[11px] ${statusClasses(profile.health_status)}`}>
                        {profile.health_status || 'unknown'}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-tsushin-slate">
                      {profile.provider_type} · {profile.browser_type} · cookies {summary.cookie_count || 0} · origins {summary.origin_count || 0}
                    </div>
                    {Array.isArray(summary.domains) && summary.domains.length > 0 ? (
                      <div className="mt-1 truncate text-[11px] text-gray-500">{summary.domains.join(', ')}</div>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => onTest(profile)}
                      disabled={testingId === profile.id || saving}
                      className="rounded-lg border border-cyan-500/30 px-2.5 py-1.5 text-xs text-cyan-200 hover:bg-cyan-500/10 disabled:opacity-50"
                    >
                      <PlayIcon size={14} className="mr-1 inline-block align-text-bottom" />
                      {testingId === profile.id ? 'Testing...' : 'Test'}
                    </button>
                    {canWriteHub ? (
                      <>
                        <button type="button" onClick={() => onEdit(profile)} className="rounded-lg border border-tsushin-border px-2.5 py-1.5 text-xs text-tsushin-slate hover:text-white">Edit</button>
                        <button type="button" onClick={() => onDelete(profile)} className="rounded-lg border border-red-500/30 px-2.5 py-1.5 text-xs text-red-300 hover:bg-red-500/10">Disable</button>
                      </>
                    ) : null}
                  </div>
                </div>
                {result ? (
                  <div className={`mt-2 rounded border px-3 py-2 text-xs ${result.ok ? 'border-green-500/20 bg-green-500/10 text-green-200' : 'border-yellow-500/20 bg-yellow-500/10 text-yellow-200'}`}>
                    {result.ok ? 'Profile test passed.' : (result.errors || []).join('; ') || `Status: ${result.status}`}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
