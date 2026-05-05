'use client'

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useRequireAuth } from '@/contexts/AuthContext'
import StudioTabs from '@/components/studio/StudioTabs'
import { api, type TeamDetail } from '@/lib/client'
import {
  AlertCircleIcon,
  ChevronLeftIcon,
  ClockIcon,
  RefreshIcon,
  UsersIcon,
  WebhookIcon,
  WrenchIcon,
} from '@/components/ui/icons'

const STATUS_STYLES: Record<string, string> = {
  active: 'badge-success',
  draft: 'badge-neutral',
  paused: 'badge-warning',
  archived: 'badge-danger',
}

function formatLabel(value?: string | null) {
  if (!value) return 'None'
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function formatDate(value?: string | null) {
  if (!value) return 'Never'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Never'
  return date.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export default function StudioTeamDetailPage() {
  useRequireAuth()
  const router = useRouter()
  const params = useParams<{ id: string }>()
  const teamId = Number(params.id)
  const [team, setTeam] = useState<TeamDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadTeam = useCallback(async () => {
    if (!Number.isFinite(teamId) || teamId <= 0) {
      setError('Invalid team id')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      setTeam(await api.getTeam(teamId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load team')
    } finally {
      setLoading(false)
    }
  }, [teamId])

  useEffect(() => {
    loadTeam()
  }, [loadTeam])

  return (
    <div className="min-h-screen animate-fade-in">
      <div className="container mx-auto px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <button
              type="button"
              onClick={() => router.push('/studio/teams')}
              className="mb-3 inline-flex items-center gap-2 text-sm text-tsushin-slate transition-colors hover:text-white"
            >
              <ChevronLeftIcon size={16} />
              Teams
            </button>
            <h1 className="text-3xl font-display font-bold text-white">{team?.name || 'Agent Team'}</h1>
            <p className="mt-2 text-tsushin-slate">{team?.description || 'Team details and current bindings.'}</p>
          </div>
          <button
            type="button"
            onClick={loadTeam}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm font-medium text-tsushin-slate transition-colors hover:border-tsushin-muted hover:text-white"
          >
            <RefreshIcon size={16} />
            Refresh
          </button>
        </div>

        <div className="space-y-6">
          <StudioTabs />

          {loading ? (
            <div className="glass-card flex items-center justify-center rounded-xl py-16">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-tsushin-indigo/30 border-t-tsushin-indigo"></div>
            </div>
          ) : error ? (
            <div className="rounded-xl border border-tsushin-vermilion/25 bg-tsushin-vermilion/10 px-4 py-3 text-sm text-tsushin-vermilion">
              <div className="flex items-center gap-2">
                <AlertCircleIcon size={16} />
                {error}
              </div>
            </div>
          ) : team ? (
            <>
              <div className="grid gap-4 md:grid-cols-4">
                <div className="stat-card stat-card-indigo">
                  <p className="text-sm font-medium text-tsushin-slate">Status</p>
                  <p className={`badge mt-2 ${STATUS_STYLES[team.status] || 'badge-neutral'}`}>{formatLabel(team.status)}</p>
                </div>
                <div className="stat-card stat-card-success">
                  <p className="text-sm font-medium text-tsushin-slate">Members</p>
                  <p className="mt-1 text-3xl font-display font-bold text-white">{team.members.length}</p>
                </div>
                <div className="stat-card stat-card-accent">
                  <p className="text-sm font-medium text-tsushin-slate">Topology</p>
                  <p className="mt-1 text-3xl font-display font-bold text-white">{formatLabel(team.topology)}</p>
                </div>
                <div className="stat-card stat-card-warning">
                  <p className="text-sm font-medium text-tsushin-slate">Last Run</p>
                  <p className="mt-1 text-lg font-semibold text-white">{formatLabel(team.last_run_status)}</p>
                </div>
              </div>

              <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
                <section className="glass-card rounded-xl p-6">
                  <h2 className="mb-4 text-lg font-display font-semibold text-white">Goal</h2>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-tsushin-slate">{team.goal_text || 'No goal configured.'}</p>
                  <div className="mt-5 grid gap-3 md:grid-cols-3">
                    <MiniMetric label="Max steps" value={String(team.max_steps)} />
                    <MiniMetric label="Concurrent runs" value={String(team.max_concurrent_runs)} />
                    <MiniMetric label="Token cap" value={team.max_total_tokens ? String(team.max_total_tokens) : 'None'} />
                  </div>
                </section>

                <section className="glass-card rounded-xl p-6">
                  <h2 className="mb-4 text-lg font-display font-semibold text-white">Last Run</h2>
                  {team.last_run ? (
                    <div className="space-y-3 text-sm">
                      <MiniMetric label="Status" value={formatLabel(team.last_run.status)} />
                      <MiniMetric label="Started" value={formatDate(team.last_run.started_at || team.last_run.created_at)} />
                      <MiniMetric label="Steps" value={`${team.last_run.completed_steps}/${team.last_run.total_steps}`} />
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 text-sm text-tsushin-slate">
                      <ClockIcon size={16} />
                      No runs yet.
                    </div>
                  )}
                </section>
              </div>

              <div className="grid gap-6 xl:grid-cols-3">
                <DetailPanel title="Members" icon={<UsersIcon size={18} />}>
                  {team.members.length === 0 ? (
                    <EmptyLine>No members.</EmptyLine>
                  ) : team.members.map((member) => (
                    <div key={member.id} className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 px-4 py-3">
                      <div className="font-medium text-white">{member.agent_name || `Agent #${member.agent_id}`}</div>
                      <div className="mt-1 text-xs text-tsushin-slate">
                        Order {member.execution_order ?? '-'} - {member.is_required ? 'Required' : 'Optional'}
                      </div>
                    </div>
                  ))}
                </DetailPanel>

                <DetailPanel title="Tools" icon={<WrenchIcon size={18} />}>
                  {team.tools.sandboxed_tool_ids.length === 0 ? (
                    <EmptyLine>No tools.</EmptyLine>
                  ) : team.tools.sandboxed_tool_ids.map((toolId) => (
                    <div key={toolId} className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 px-4 py-3 text-sm text-tsushin-fog">
                      Sandboxed tool #{toolId}
                    </div>
                  ))}
                </DetailPanel>

                <DetailPanel title="Triggers" icon={<WebhookIcon size={18} />}>
                  {team.triggers.length === 0 ? (
                    <EmptyLine>No trigger bindings.</EmptyLine>
                  ) : team.triggers.map((trigger) => (
                    <div key={trigger.id} className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 px-4 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium text-white">{formatLabel(trigger.trigger_kind)}</div>
                        <span className={`badge ${trigger.is_enabled ? 'badge-success' : 'badge-neutral'}`}>
                          {trigger.is_enabled ? 'Enabled' : 'Disabled'}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-tsushin-slate">
                        Instance #{trigger.trigger_instance_id} - {trigger.event_types.join(', ') || 'All events'}
                      </div>
                    </div>
                  ))}
                </DetailPanel>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  )
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-tsushin-border bg-tsushin-surface/30 px-4 py-3">
      <div className="text-xs text-tsushin-muted">{label}</div>
      <div className="mt-1 font-semibold text-white">{value}</div>
    </div>
  )
}

function DetailPanel({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-card rounded-xl p-6">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-display font-semibold text-white">
        {icon}
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  )
}

function EmptyLine({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-dashed border-tsushin-border px-4 py-8 text-center text-sm text-tsushin-slate">{children}</div>
}
