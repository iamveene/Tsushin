'use client'

/**
 * WiredContinuousCard
 *
 * Mirror of WiredFlowsCard for the `continuous_subscription` table. Lists
 * every continuous-agent subscription wired to the current trigger and
 * exposes pause/resume + unbind controls. Mutations call the existing
 * per-agent CRUD routes — the reverse-lookup payload carries
 * `continuous_agent_id` so each row knows where to write.
 *
 * Permission model:
 *   - read: `agents.read` (silently rendered as null if missing)
 *   - mutate (pause/unbind): `agents.write`
 *
 * The dispatcher stores email triggers under `channel_type='gmail'`, so the
 * trigger detail page passes `channel_type='gmail'` for email kinds — see
 * the call site in OutputsSection.
 *
 * System-owned subscriptions (auto-created by the platform) cannot be
 * paused or unbound: the backend rejects the call. We mirror that by
 * disabling the buttons and surfacing the rule via tooltip.
 */

import { useEffect, useState } from 'react'
import Link from 'next/link'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import {
  api,
  type ContinuousSubscriptionWithAgent,
} from '@/lib/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import {
  BotIcon,
  ExternalLinkIcon,
  PauseIcon,
  PlayIcon,
  RefreshIcon,
  TrashIcon,
} from '@/components/ui/icons'

interface Props {
  channelType: string
  channelInstanceId: number
  onBindingsChange?: (bindings: ContinuousSubscriptionWithAgent[]) => void
}

type StatusTone = { text: string; tone: string }

function statusPill(b: ContinuousSubscriptionWithAgent): StatusTone {
  const status = (b.status || '').toLowerCase()
  if (status === 'active') {
    if (b.continuous_agent_status === 'disabled' || b.continuous_agent_status === 'error') {
      return {
        text: `Agent ${b.continuous_agent_status}`,
        tone: 'border-rose-400/40 bg-rose-500/10 text-rose-200',
      }
    }
    if (b.continuous_agent_status === 'paused') {
      return {
        text: 'Agent paused',
        tone: 'border-amber-400/40 bg-amber-500/10 text-amber-200',
      }
    }
    return { text: 'Active', tone: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200' }
  }
  if (status === 'paused') {
    return { text: 'Paused', tone: 'border-amber-400/40 bg-amber-500/10 text-amber-200' }
  }
  if (status === 'disabled') {
    return { text: 'Disabled', tone: 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-slate' }
  }
  if (status === 'error') {
    return { text: 'Error', tone: 'border-rose-400/40 bg-rose-500/10 text-rose-200' }
  }
  return { text: status || 'Unknown', tone: 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-fog' }
}

export default function WiredContinuousCard({ channelType, channelInstanceId, onBindingsChange }: Props) {
  const { hasPermission } = useAuth()
  const toast = useToast()
  const canRead = hasPermission('agents.read')
  const canWrite = hasPermission('agents.write')

  const [bindings, setBindings] = useState<ContinuousSubscriptionWithAgent[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [unbindTarget, setUnbindTarget] = useState<ContinuousSubscriptionWithAgent | null>(null)

  async function refresh() {
    if (!canRead || !channelInstanceId) {
      setBindings([])
      setLoadError(null)
      onBindingsChange?.([])
      setLoading(false)
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const items = await api.listContinuousSubscriptionsByInstance({
        channel_type: channelType,
        channel_instance_id: channelInstanceId,
      })
      setBindings(items)
      onBindingsChange?.(items)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load wired continuous agents'
      setLoadError(msg)
      setBindings([])
      onBindingsChange?.([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelType, channelInstanceId, canRead])

  async function handleTogglePause(b: ContinuousSubscriptionWithAgent) {
    if (!canWrite) return
    if (b.is_system_owned) return
    setBusyId(b.id)
    const nextStatus = b.status === 'active' ? 'paused' : 'active'
    try {
      const updated = await api.updateContinuousSubscription(b.continuous_agent_id, b.id, {
        status: nextStatus,
      })
      const next = bindings.map((row) =>
        row.id === b.id ? { ...row, ...updated } : row,
      )
      setBindings(next)
      onBindingsChange?.(next)
      toast.success(
        'Subscription updated',
        nextStatus === 'paused'
          ? `${b.continuous_agent_name ?? 'Continuous agent'} is paused on this trigger.`
          : `${b.continuous_agent_name ?? 'Continuous agent'} is active again.`,
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update subscription'
      toast.error('Update failed', msg)
    } finally {
      setBusyId(null)
    }
  }

  async function performUnbind(b: ContinuousSubscriptionWithAgent) {
    setBusyId(b.id)
    try {
      await api.deleteContinuousSubscription(b.continuous_agent_id, b.id)
      const next = bindings.filter((row) => row.id !== b.id)
      setBindings(next)
      onBindingsChange?.(next)
      toast.success(
        'Subscription unbound',
        `${b.continuous_agent_name ?? 'Continuous agent'} no longer subscribes to this trigger.`,
      )
      setUnbindTarget(null)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to unbind subscription'
      toast.error('Unbind failed', msg)
    } finally {
      setBusyId(null)
    }
  }

  if (!canRead) return null

  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-white">
            <BotIcon size={18} /> Wired Continuous Agents
          </h3>
          <p className="mt-1 text-sm text-tsushin-slate">
            Continuous agents subscribed to this trigger. Pause to stop new events without removing the binding.
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {loading && (
          <div className="rounded-lg border border-dashed border-tsushin-border bg-tsushin-surface/40 px-4 py-3 text-sm text-tsushin-slate">
            Loading wired continuous agents...
          </div>
        )}

        {!loading && loadError && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span>{loadError}</span>
              <button
                type="button"
                onClick={refresh}
                className="inline-flex items-center gap-1.5 rounded-md border border-red-300/40 bg-red-500/10 px-2.5 py-1 text-xs text-red-100 hover:text-white"
              >
                <RefreshIcon size={12} /> Retry
              </button>
            </div>
          </div>
        )}

        {!loading && !loadError && bindings.length === 0 && (
          <div className="rounded-lg border border-dashed border-tsushin-border bg-tsushin-surface/40 px-4 py-6 text-center">
            <p className="text-sm text-tsushin-slate">
              No continuous agents are subscribed to this trigger yet.
            </p>
            <Link
              href="/continuous-agents"
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-100 hover:text-white"
            >
              <ExternalLinkIcon size={14} /> Browse Continuous Agents
            </Link>
          </div>
        )}

        {!loading && !loadError && bindings.map((b) => {
          const pill = statusPill(b)
          const editHref = `/continuous-agents/${b.continuous_agent_id}`
          const busy = busyId === b.id
          const isPaused = b.status !== 'active'
          const lockReason = b.is_system_owned
            ? 'System-owned subscriptions cannot be paused or unbound here.'
            : null
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
                    title={b.continuous_agent_name ?? `Continuous agent #${b.continuous_agent_id}`}
                  >
                    {b.continuous_agent_name ?? `Continuous agent #${b.continuous_agent_id}`}
                  </Link>
                  <Link
                    href={editHref}
                    className="text-tsushin-slate hover:text-cyan-200"
                    aria-label="Open continuous agent"
                  >
                    <ExternalLinkIcon size={12} />
                  </Link>
                  {b.is_system_owned && (
                    <span className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-cyan-200">
                      System-owned
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-tsushin-slate">
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] ${pill.tone}`}>
                    {pill.text}
                  </span>
                  {b.event_type && <span>event: {b.event_type}</span>}
                </div>
              </div>

              {canWrite && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleTogglePause(b)}
                    disabled={busy || b.is_system_owned}
                    title={lockReason ?? (isPaused ? 'Resume this subscription' : 'Pause this subscription')}
                    className="inline-flex items-center gap-1 rounded-md border border-tsushin-border bg-tsushin-surface/60 px-2 py-1 text-[11px] text-tsushin-fog hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {isPaused ? <><PlayIcon size={12} /> Resume</> : <><PauseIcon size={12} /> Pause</>}
                  </button>
                  <button
                    type="button"
                    onClick={() => setUnbindTarget(b)}
                    disabled={busy || b.is_system_owned}
                    title={lockReason ?? 'Remove this subscription from the trigger'}
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
        title="Unbind this subscription?"
        message={
          unbindTarget ? (
            <>
              <span className="font-mono text-white">{unbindTarget.continuous_agent_name ?? `Continuous agent #${unbindTarget.continuous_agent_id}`}</span>
              {' '}will no longer subscribe to this trigger. The continuous
              agent itself is not deleted; you can re-subscribe from its
              configuration page.
            </>
          ) : 'The continuous agent will no longer subscribe to this trigger.'
        }
        confirmLabel="Unbind subscription"
        danger
        isBusy={unbindTarget !== null && busyId === unbindTarget.id}
        onConfirm={() => {
          if (unbindTarget) {
            return performUnbind(unbindTarget)
          }
        }}
        onCancel={() => setUnbindTarget(null)}
      />
    </div>
  )
}
