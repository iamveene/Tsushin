'use client'

/**
 * WiredTeamsCard
 *
 * Mirror of WiredFlowsCard for the Agent Team trigger table. Displays every
 * `agent_team_trigger` row whose `config_json.trigger_instance_id` matches
 * the current trigger, with controls to pause/resume the binding or unbind
 * it entirely. Mutations call the existing per-team CRUD routes — the
 * reverse-lookup payload carries `team_id` so each row knows where to write.
 *
 * Permission model:
 *   - read: `agents.read` (silently rendered as null if missing)
 *   - mutate (pause/unbind): `agents.write`
 *
 * Rendered on every trigger kind supported by AgentTeamTrigger.trigger_kind:
 * jira / github / gitlab / webhook / gmail. Email triggers persist with kind='gmail'.
 */

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import {
  api,
  type TeamTriggerWithTeam,
} from '@/lib/client'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import {
  ExternalLinkIcon,
  PauseIcon,
  PlayIcon,
  RefreshIcon,
  TrashIcon,
  UsersIcon,
} from '@/components/ui/icons'

export type WiredTeamsTriggerKind = 'jira' | 'github' | 'gitlab' | 'webhook' | 'gmail'

interface Props {
  triggerKind: WiredTeamsTriggerKind
  triggerId: number
  onBindingsChange?: (bindings: TeamTriggerWithTeam[]) => void
}

function statusPill(b: TeamTriggerWithTeam): { text: string; tone: string } {
  if (!b.is_enabled) {
    return { text: 'Paused', tone: 'border-amber-400/40 bg-amber-500/10 text-amber-200' }
  }
  if (b.team_status === 'archived') {
    return { text: 'Team archived', tone: 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-slate' }
  }
  if (b.team_status === 'draft') {
    return { text: 'Team draft', tone: 'border-tsushin-border bg-tsushin-surface/40 text-tsushin-slate' }
  }
  return { text: 'Active', tone: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-200' }
}

function topologyBadge(t: string): { label: string; tone: string } {
  if (t === 'mesh') {
    return { label: 'MESH', tone: 'border-fuchsia-400/40 bg-fuchsia-500/10 text-fuchsia-200' }
  }
  return { label: 'LINE', tone: 'border-cyan-400/40 bg-cyan-500/10 text-cyan-200' }
}

export default function WiredTeamsCard({ triggerKind, triggerId, onBindingsChange }: Props) {
  const { hasPermission } = useAuth()
  const toast = useToast()
  const canRead = hasPermission('agents.read')
  const canWrite = hasPermission('agents.write')

  const [bindings, setBindings] = useState<TeamTriggerWithTeam[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [unbindTarget, setUnbindTarget] = useState<TeamTriggerWithTeam | null>(null)

  async function refresh() {
    if (!canRead || !triggerId) {
      setBindings([])
      setLoadError(null)
      onBindingsChange?.([])
      setLoading(false)
      return
    }
    setLoading(true)
    setLoadError(null)
    try {
      const items = await api.listTeamTriggersByInstance({
        trigger_kind: triggerKind,
        trigger_instance_id: triggerId,
      })
      setBindings(items)
      onBindingsChange?.(items)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load wired teams'
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
  }, [triggerKind, triggerId, canRead])

  async function handleTogglePause(b: TeamTriggerWithTeam) {
    if (!canWrite) return
    setBusyId(b.id)
    try {
      const updated = await api.updateTeamTrigger(b.team_id, b.id, {
        is_enabled: !b.is_enabled,
      })
      const next = bindings.map((row) =>
        row.id === b.id ? { ...row, ...updated } : row,
      )
      setBindings(next)
      onBindingsChange?.(next)
      toast.success(
        'Binding updated',
        updated.is_enabled
          ? `${b.team_name} will receive new events again.`
          : `${b.team_name} is now paused on this trigger.`,
      )
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update binding'
      toast.error('Update failed', msg)
    } finally {
      setBusyId(null)
    }
  }

  async function performUnbind(b: TeamTriggerWithTeam) {
    setBusyId(b.id)
    try {
      await api.deleteTeamTrigger(b.team_id, b.id)
      const next = bindings.filter((row) => row.id !== b.id)
      setBindings(next)
      onBindingsChange?.(next)
      toast.success('Team unbound', `${b.team_name} no longer wakes on this trigger.`)
      setUnbindTarget(null)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to unbind team'
      toast.error('Unbind failed', msg)
    } finally {
      setBusyId(null)
    }
  }

  const teamsBrowseHref = useMemo(() => '/studio/teams', [])

  if (!canRead) return null

  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-white">
            <UsersIcon size={18} /> Wired Agent Teams
          </h3>
          <p className="mt-1 text-sm text-tsushin-slate">
            Agent Teams that wake when this trigger fires. Manage the binding here or open the team in the Studio for full configuration.
          </p>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {loading && (
          <div className="rounded-lg border border-dashed border-tsushin-border bg-tsushin-surface/40 px-4 py-3 text-sm text-tsushin-slate">
            Loading wired teams...
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
              No agent teams are wired to this trigger yet.
            </p>
            <Link
              href={teamsBrowseHref}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-xs text-cyan-100 hover:text-white"
            >
              <ExternalLinkIcon size={14} /> Browse Agent Teams
            </Link>
          </div>
        )}

        {!loading && !loadError && bindings.map((b) => {
          const pill = statusPill(b)
          const topo = topologyBadge(b.team_topology)
          const editHref = `/studio/teams/${b.team_id}`
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
                    title={b.team_name}
                  >
                    {b.team_name}
                  </Link>
                  <Link
                    href={editHref}
                    className="text-tsushin-slate hover:text-cyan-200"
                    aria-label="Open team"
                  >
                    <ExternalLinkIcon size={12} />
                  </Link>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${topo.tone}`}>
                    {topo.label}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-tsushin-slate">
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] ${pill.tone}`}>
                    {pill.text}
                  </span>
                  <span>{b.member_count} member{b.member_count === 1 ? '' : 's'}</span>
                  {b.event_types.length > 0 && (
                    <span title={b.event_types.join(', ')}>
                      {b.event_types.length} event type{b.event_types.length === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
              </div>

              {canWrite && (
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleTogglePause(b)}
                    disabled={busy}
                    title={b.is_enabled ? 'Pause this binding (events will skip the team)' : 'Resume this binding'}
                    className="inline-flex items-center gap-1 rounded-md border border-tsushin-border bg-tsushin-surface/60 px-2 py-1 text-[11px] text-tsushin-fog hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {b.is_enabled ? <><PauseIcon size={12} /> Pause</> : <><PlayIcon size={12} /> Resume</>}
                  </button>
                  <button
                    type="button"
                    onClick={() => setUnbindTarget(b)}
                    disabled={busy}
                    title="Remove this trigger binding from the team"
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
        title="Unbind this team?"
        message={
          unbindTarget ? (
            <>
              <span className="font-mono text-white">{unbindTarget.team_name}</span>
              {' '}will no longer wake when this trigger fires. The team itself
              is not deleted; you can re-wire it from the team's Triggers tab
              at any time.
            </>
          ) : 'The team will no longer wake when the trigger fires.'
        }
        confirmLabel="Unbind team"
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
