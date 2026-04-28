'use client'

/**
 * DefaultAgentChip
 *
 * Inline-edit chip that displays the trigger's current default agent (the
 * "Routing" target) and lets a user with `hub.write` change it via a
 * popover-driven agent picker.
 *
 * - Read-only mode (no permission): renders a non-clickable badge with a
 *   tooltip explaining the missing permission.
 * - Edit mode: rounded-full chip; clicking opens an inline popover with a
 *   filterable list of active agents and a "Clear default agent" button.
 *
 * The component is optimistic — it reports the predicted next state to the
 * parent immediately via `onUpdate`, then converges on the server's response
 * (or refetches the trigger if the PATCH fails).
 *
 * Wave 1 of the Triggers ↔ Flows unification (release/0.7.0).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useToast } from '@/contexts/ToastContext'
import { api, type Agent } from '@/lib/client'

export type DefaultAgentChipKind = 'jira' | 'email' | 'github' | 'webhook'

interface Props {
  triggerKind: DefaultAgentChipKind
  triggerId: number
  agent: { id: number | null; name: string | null }
  canEdit: boolean
  onUpdate: (next: { default_agent_id: number | null; default_agent_name: string | null }) => void
}

function chipLabel(name: string | null): string {
  return name && name.trim().length > 0 ? name : 'No default agent'
}

export default function DefaultAgentChip({ triggerKind, triggerId, agent, canEdit, onUpdate }: Props) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [agents, setAgents] = useState<Agent[]>([])
  const [loadingAgents, setLoadingAgents] = useState(false)
  const [query, setQuery] = useState('')
  const [saving, setSaving] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Close dropdown on outside click / escape
  useEffect(() => {
    if (!open) return
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  // Lazy-load agents when popover opens.
  //
  // CRITICAL: do NOT put `loadingAgents` in the deps array or the guard.
  // Doing so creates a feedback loop: setLoadingAgents(true) re-runs the
  // effect, the previous run's cleanup flips cancelled=true, the in-flight
  // fetch resolves but its setAgents is dropped, and the next run hits its
  // own guard and never starts a new fetch — the popover stays stuck on
  // "Loading agents..." forever (caught by Wave 1 QA, /api/agents returned
  // 200 but the list never rendered). The `agents.length > 0` guard alone
  // is sufficient to prevent re-fetch once data is loaded; React bails on
  // identical state writes so setLoadingAgents(true) on an already-loading
  // component does not retrigger this effect.
  useEffect(() => {
    if (!open || agents.length > 0) return
    let cancelled = false
    setLoadingAgents(true)
    api.getAgents(true)
      .then((list) => {
        if (cancelled) return
        setAgents(list)
      })
      .catch((err) => {
        if (cancelled) return
        toast.error('Failed to load agents', err instanceof Error ? err.message : undefined)
      })
      .finally(() => {
        if (!cancelled) setLoadingAgents(false)
      })
    return () => { cancelled = true }
  }, [open, agents.length, toast])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return agents
    return agents.filter((a) => {
      const name = (a.contact_name || '').toLowerCase()
      return name.includes(q)
    })
  }, [agents, query])

  const callPatch = useCallback(async (nextAgentId: number | null) => {
    const data = { default_agent_id: nextAgentId } as const
    switch (triggerKind) {
      case 'jira':
        return api.updateJiraTrigger(triggerId, data)
      case 'email':
        return api.updateEmailTrigger(triggerId, data)
      case 'github':
        return api.updateGitHubTrigger(triggerId, data)
      case 'webhook':
        return api.updateWebhookIntegration(triggerId, data)
    }
  }, [triggerKind, triggerId])

  const refetchTrigger = useCallback(async () => {
    switch (triggerKind) {
      case 'jira':
        return api.getJiraTrigger(triggerId)
      case 'email':
        return api.getEmailTrigger(triggerId)
      case 'github':
        return api.getGitHubTrigger(triggerId)
      case 'webhook':
        return api.getWebhookIntegration(triggerId)
    }
  }, [triggerKind, triggerId])

  const handleSelect = useCallback(async (next: { id: number | null; name: string | null }) => {
    if (saving) return
    setOpen(false)
    setSaving(true)

    // Optimistic predicted state
    onUpdate({ default_agent_id: next.id, default_agent_name: next.name })

    try {
      const updated = await callPatch(next.id)
      // Server truth may differ (e.g., agent name resolved server-side)
      onUpdate({
        default_agent_id: updated.default_agent_id ?? null,
        default_agent_name: updated.default_agent_name ?? null,
      })
      const label = updated.default_agent_name || next.name || 'No default agent'
      toast.success(`Routing updated to ${label}`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update routing'
      toast.error('Failed to update routing', message)
      // Converge to server truth on failure
      try {
        const fresh = await refetchTrigger()
        onUpdate({
          default_agent_id: fresh.default_agent_id ?? null,
          default_agent_name: fresh.default_agent_name ?? null,
        })
      } catch {
        // If refetch also fails, leave the optimistic value in place;
        // the user will see the previous value next time the page loads.
      }
    } finally {
      setSaving(false)
    }
  }, [saving, callPatch, refetchTrigger, onUpdate, toast])

  if (!canEdit) {
    return (
      <span
        title="You don't have permission to change routing"
        className="inline-flex max-w-full items-center gap-1.5 truncate rounded-full border border-tsushin-border bg-black/20 px-2.5 py-1 text-xs text-tsushin-fog"
      >
        {chipLabel(agent.name)}
      </span>
    )
  }

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        disabled={saving}
        className={`inline-flex max-w-full items-center gap-1.5 truncate rounded-full border px-2.5 py-1 text-xs transition-colors ${
          agent.id
            ? 'border-cyan-500/40 bg-cyan-500/10 text-cyan-100 hover:border-cyan-400 hover:text-white'
            : 'border-tsushin-border bg-black/20 text-tsushin-fog hover:border-cyan-400 hover:text-white'
        } disabled:opacity-50`}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">{saving ? 'Saving...' : chipLabel(agent.name)}</span>
        <svg className="h-3 w-3 flex-shrink-0 opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div
          className="absolute left-0 z-30 mt-2 w-72 rounded-xl border border-tsushin-border bg-tsushin-surface p-2 shadow-xl shadow-black/50"
          role="listbox"
        >
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search agents..."
            className="mb-2 w-full rounded-lg border border-tsushin-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
          />
          <div className="max-h-64 overflow-y-auto">
            {loadingAgents ? (
              <div className="px-3 py-4 text-center text-xs text-tsushin-slate">Loading agents...</div>
            ) : filtered.length === 0 ? (
              <div className="px-3 py-4 text-center text-xs text-tsushin-slate">
                {query.trim() ? 'No matching agents' : 'No active agents'}
              </div>
            ) : (
              filtered.map((a) => {
                const selected = a.id === agent.id
                return (
                  <button
                    key={a.id}
                    type="button"
                    onClick={() => handleSelect({ id: a.id, name: a.contact_name })}
                    className={`flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                      selected
                        ? 'bg-cyan-500/15 text-cyan-100'
                        : 'text-tsushin-fog hover:bg-tsushin-border/40 hover:text-white'
                    }`}
                  >
                    <span className="truncate">{a.contact_name}</span>
                    {selected && <span className="text-xs text-cyan-300">Current</span>}
                  </button>
                )
              })
            )}
          </div>
          <div className="mt-2 border-t border-tsushin-border pt-2">
            <button
              type="button"
              onClick={() => handleSelect({ id: null, name: null })}
              className="w-full rounded-lg px-3 py-2 text-left text-xs text-red-200 hover:bg-red-500/10 hover:text-red-100"
            >
              Clear default agent
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
