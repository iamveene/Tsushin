'use client'

/**
 * WiredFlowsCard
 *
 * Wave 4 of the Triggers ↔ Flows unification.
 *
 * Renders the list of FlowDefinitions bound to a given trigger via the
 * `flow_trigger_binding` table, plus the "Create flow from this trigger"
 * CTA that deep-links into the Flows editor with the trigger pre-wired
 * as a Source step.
 *
 * Lives inside `OutputsSection`, directly below the Managed Notification
 * card (when present) and above the Manual Poll card. For kinds that
 * have no managed outputs (github / webhook), this card
 * carries the empty-state messaging.
 *
 * Permission model:
 *   - read: `flows.read` (silently rendered as empty if missing)
 *   - mutate (toggle suppress, unbind): `flows.write`
 *   - the Create CTA additionally requires `flows.write`
 *
 * System-managed bindings (auto-created by the backend when a trigger
 * is created) are surfaced with a non-removable badge — operators can
 * still toggle suppress-default-agent on them, but cannot unbind them
 * here (deletion happens via deleting the underlying flow).
 */

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import {
  api,
  type FlowTriggerBinding,
  type TriggerKind,
} from '@/lib/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import {
  ExternalLinkIcon,
  LightningIcon,
  PlusIcon,
  TrashIcon,
} from '@/components/ui/icons'

interface Props {
  triggerKind: TriggerKind
  triggerId: number
  /**
   * Optional callback fired after the bindings list mutates (toggle /
   * unbind / refresh). The parent uses this so the suppress-default
   * banner on the Managed Notification card stays in sync.
   */
  onBindingsChange?: (bindings: FlowTriggerBinding[]) => void
}

function statusPill(binding: FlowTriggerBinding): { text: string; tone: string } {
  const status = (binding.last_run_status || '').toLowerCase()
  if (!status) return { text: 'Never run', tone: 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-slate' }
  if (status === 'success' || status === 'completed' || status === 'goal_achieved') {
    return { text: 'Last: success', tone: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200' }
  }
  if (status === 'failed' || status === 'error' || status === 'timeout') {
    return { text: `Last: ${status}`, tone: 'border-rose-400/40 bg-rose-500/10 text-rose-200' }
  }
  if (status === 'running' || status === 'pending' || status === 'active') {
    return { text: `Last: ${status}`, tone: 'border-cyan-400/40 bg-cyan-500/10 text-cyan-200' }
  }
  return { text: `Last: ${status}`, tone: 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-fog' }
}

function formatRelative(ts?: string | null): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ''
    const diff = Date.now() - d.getTime()
    if (diff < 60_000) return 'just now'
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
    return `${Math.floor(diff / 86_400_000)}d ago`
  } catch {
    return ''
  }
}

export default function WiredFlowsCard({ triggerKind, triggerId, onBindingsChange }: Props) {
  const { hasPermission } = useAuth()
  const toast = useToast()
  const canRead = hasPermission('flows.read')
  const canWrite = hasPermission('flows.write')

  const [bindings, setBindings] = useState<FlowTriggerBinding[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<number | null>(null)

  const createHref = useMemo(
    () => `/flows?source_trigger_kind=${encodeURIComponent(triggerKind)}&source_trigger_id=${triggerId}`,
    [triggerKind, triggerId],
  )

  async function refresh() {
    if (!canRead || !triggerId) {
      setBindings([])
      onBindingsChange?.([])
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const items = await api.listFlowTriggerBindings({
        trigger_kind: triggerKind,
        trigger_id: triggerId,
      })
      setBindings(items)
      onBindingsChange?.(items)
    } catch (err) {
      // Backend endpoint may not be merged yet — stay quiet, just empty.
      setBindings([])
      onBindingsChange?.([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerKind, triggerId, canRead])

  async function handleToggleSuppress(b: FlowTriggerBinding) {
    if (!canWrite) return
    setBusyId(b.id)
    try {
      const updated = await api.updateFlowTriggerBinding(b.id, {
        suppress_default_agent: !b.suppress_default_agent,
      })
      const next = bindings.map((row) => (row.id === b.id ? { ...row, ...updated } : row))
      setBindings(next)
      onBindingsChange?.(next)
      toast.success(
        'Binding updated',
        updated.suppress_default_agent
          ? `${b.flow_name || 'Flow'} now suppresses the default agent.`
          : `${b.flow_name || 'Flow'} no longer suppresses the default agent.`,
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update binding'
      toast.error('Update failed', msg)
    } finally {
      setBusyId(null)
    }
  }

  // v0.7.0 release-finishing UX fix — replace native window.confirm()
  // with the styled in-app ConfirmDialog.
  const [unbindTarget, setUnbindTarget] = useState<FlowTriggerBinding | null>(null)

  async function performUnbind(b: FlowTriggerBinding) {
    setBusyId(b.id)
    try {
      await api.deleteFlowTriggerBinding(b.id)
      const next = bindings.filter((row) => row.id !== b.id)
      setBindings(next)
      onBindingsChange?.(next)
      toast.success('Flow unbound', `${b.flow_name || 'Flow'} is no longer wired to this trigger.`)
      setUnbindTarget(null)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to unbind flow'
      toast.error('Unbind failed', msg)
    } finally {
      setBusyId(null)
    }
  }

  function handleUnbind(b: FlowTriggerBinding) {
    if (!canWrite) return
    if (b.is_system_managed) return
    setUnbindTarget(b)
  }

  if (!canRead) {
    return null
  }

  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-white">
            <LightningIcon size={18} /> Wired Flows
          </h3>
          <p className="mt-1 text-sm text-tsushin-slate">
            Custom Flows that wake when this trigger fires.
          </p>
        </div>
        {canWrite && (
          <Link
            href={createHref}
            className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-100 hover:text-white"
          >
            <PlusIcon size={14} /> Create flow from this trigger
          </Link>
        )}
      </div>

      <div className="mt-4 space-y-2">
        {loading && (
          <div className="rounded-lg border border-dashed border-tsushin-border bg-tsushin-surface/40 px-4 py-3 text-sm text-tsushin-slate">
            Loading wired flows...
          </div>
        )}

        {!loading && bindings.length === 0 && (
          <div className="rounded-lg border border-dashed border-tsushin-border bg-tsushin-surface/40 px-4 py-6 text-center">
            <p className="text-sm text-tsushin-slate">
              No custom flows are wired to this trigger yet.
            </p>
            {canWrite && (
              <Link
                href={createHref}
                className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-100 hover:text-white"
              >
                <PlusIcon size={14} /> Create flow from this trigger
              </Link>
            )}
          </div>
        )}

        {!loading && bindings.map((b) => {
          const pill = statusPill(b)
          const lastWhen = formatRelative(b.last_run_at)
          const editHref = `/flows?edit=${b.flow_definition_id}`
          const busy = busyId === b.id
          return (
            <div
              key={b.id}
              className="flex flex-wrap items-center gap-3 rounded-lg border border-tsushin-border bg-tsushin-surface/40 px-3 py-2.5"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Link
                    href={editHref}
                    className="truncate text-sm font-medium text-white hover:text-cyan-200"
                    title={b.flow_name || `Flow #${b.flow_definition_id}`}
                  >
                    {b.flow_name || `Flow #${b.flow_definition_id}`}
                  </Link>
                  <Link
                    href={editHref}
                    className="text-tsushin-slate hover:text-cyan-200"
                    aria-label="Open flow"
                  >
                    <ExternalLinkIcon size={12} />
                  </Link>
                  {b.is_system_managed && (
                    <span className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-cyan-200">
                      System-managed
                    </span>
                  )}
                  {!b.is_active && (
                    <span className="rounded-full border border-tsushin-border bg-tsushin-surface/60 px-2 py-0.5 text-[10px] uppercase tracking-wide text-tsushin-slate">
                      Inactive
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-tsushin-slate">
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] ${pill.tone}`}>
                    {pill.text}
                  </span>
                  {lastWhen && <span>{lastWhen}</span>}
                </div>
              </div>

              {canWrite && (
                <div className="flex items-center gap-2">
                  <label className="flex cursor-pointer items-center gap-2 text-xs text-tsushin-fog">
                    <input
                      type="checkbox"
                      checked={b.suppress_default_agent}
                      disabled={busy}
                      onChange={() => handleToggleSuppress(b)}
                      className="h-3.5 w-3.5 rounded border-tsushin-border bg-tsushin-surface text-cyan-500 focus:ring-cyan-500/40"
                    />
                    Suppress default agent
                  </label>
                  <button
                    type="button"
                    onClick={() => handleUnbind(b)}
                    disabled={busy || b.is_system_managed}
                    title={b.is_system_managed
                      ? 'System-managed bindings cannot be unbound here. Delete the flow to remove this binding.'
                      : 'Unbind this flow from the trigger'}
                    className="inline-flex items-center gap-1 rounded-md border border-rose-400/30 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-200 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <TrashIcon size={12} /> Unbind
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      <ConfirmDialog
        isOpen={unbindTarget !== null}
        title="Unbind this flow?"
        message={
          unbindTarget ? (
            <>
              <span className="font-mono text-white">"{unbindTarget.flow_name || 'this flow'}"</span>
              {' '}will no longer wake when this trigger fires. The flow itself
              is not deleted — you can re-wire it from the Flows editor at any
              time.
            </>
          ) : 'The flow will no longer wake when the trigger fires.'
        }
        confirmLabel="Unbind flow"
        danger
        isBusy={unbindTarget !== null && busyId === unbindTarget.id}
        onConfirm={() => unbindTarget && performUnbind(unbindTarget)}
        onCancel={() => setUnbindTarget(null)}
      />
    </div>
  )
}
