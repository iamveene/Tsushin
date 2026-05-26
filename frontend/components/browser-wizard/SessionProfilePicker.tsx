'use client'

/**
 * Dropdown of named browser session profiles. Replaces the legacy free-text
 * input that had a real customer name as its placeholder. When the API is
 * unavailable, falls back to a plain text input so the field still works.
 *
 * Selecting a profile writes BOTH the profile name AND its integration ID
 * back, so the Advanced panel doesn't need to be opened to wire the link.
 */

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { api, type BrowserSessionProfile } from '@/lib/client'

interface Props {
  profileName: string | null | undefined
  integrationId: number | null | undefined
  onChange: (next: { profileName: string; integrationId: number | null }) => void
  className?: string
}

export default function SessionProfilePicker({
  profileName,
  integrationId,
  onChange,
  className,
}: Props) {
  const [profiles, setProfiles] = useState<BrowserSessionProfile[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [fallbackText, setFallbackText] = useState<boolean>(false)

  useEffect(() => {
    let cancelled = false
    api
      .listBrowserSessionProfiles()
      .then((list) => {
        if (!cancelled) setProfiles(list)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof Error ? err.message : 'Unable to load profiles')
          setProfiles([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const selectedName = (profileName || '').trim()
  // If the current draft references a name the API didn't return, surface
  // it as a "(missing)" option so the user knows the link is dangling
  // rather than silently swapping their selection back to "no profile".
  const knownNames = new Set((profiles || []).map((p) => p.profile_name))
  const showMissingOption = selectedName.length > 0 && !knownNames.has(selectedName)

  if (fallbackText || loadError) {
    return (
      <div className={className}>
        <input
          type="text"
          value={selectedName}
          onChange={(e) => onChange({ profileName: e.target.value, integrationId: integrationId ?? null })}
          placeholder="my_login_profile"
          className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
        />
        <p className="mt-1 text-xs text-slate-500">
          {loadError ? `Couldn't fetch profiles (${loadError}). Typing a name still works.` : 'Type a profile name instead.'}{' '}
          <button
            type="button"
            onClick={() => { setFallbackText(false); setLoadError(null) }}
            className="text-cyan-400 hover:text-cyan-300"
          >
            Switch back to dropdown
          </button>
        </p>
      </div>
    )
  }

  return (
    <div className={className}>
      <select
        value={selectedName}
        onChange={(e) => {
          const next = e.target.value
          if (next === '__manual__') {
            setFallbackText(true)
            return
          }
          const profile = (profiles || []).find((p) => p.profile_name === next)
          onChange({
            profileName: next,
            integrationId: profile ? profile.id : null,
          })
        }}
        className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
      >
        <option value="">— No profile (fresh isolated context) —</option>
        {(profiles || []).map((p) => (
          <option key={p.id} value={p.profile_name}>
            {p.name} ({p.integration_name})
          </option>
        ))}
        {showMissingOption && (
          <option value={selectedName}>{selectedName} (missing — profile no longer exists)</option>
        )}
        <option value="__manual__">Type a profile name instead…</option>
      </select>
      <p className="mt-1 text-xs text-slate-500">
        Pick a saved login profile from <Link href="/hub" className="text-cyan-400 hover:text-cyan-300">Hub</Link>, or leave blank for a fresh isolated context.
      </p>
    </div>
  )
}
