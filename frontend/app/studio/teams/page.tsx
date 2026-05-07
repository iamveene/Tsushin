'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useRequireAuth } from '@/contexts/AuthContext'
import { useTeamWizard, useTeamWizardComplete } from '@/contexts/TeamWizardContext'
import StudioTabs from '@/components/studio/StudioTabs'
import { api, type TeamListItem } from '@/lib/client'
import {
  AlertCircleIcon,
  ClockIcon,
  PlayIcon,
  PlusIcon,
  RefreshIcon,
  UsersIcon,
} from '@/components/ui/icons'

const STATUS_STYLES: Record<string, string> = {
  active: 'badge-success',
  draft: 'badge-neutral',
  paused: 'badge-warning',
  archived: 'badge-danger',
}

function formatDate(value?: string | null) {
  if (!value) return 'Not run'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Not run'
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatLabel(value: string) {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

function statusBadge(status: string) {
  return STATUS_STYLES[status] || 'badge-neutral'
}

export default function StudioTeamsPage() {
  useRequireAuth()
  const router = useRouter()
  const searchParams = useSearchParams()
  const newTeamRequested = searchParams.get('new') === '1'
  const newRequestHandledRef = useRef(false)
  const teamWizard = useTeamWizard()
  const [teams, setTeams] = useState<TeamListItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [includeArchived, setIncludeArchived] = useState(false)

  const loadTeams = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.getTeams({ page: 1, pageSize: 50, includeArchived })
      setTeams(response.items)
      setTotal(response.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load teams')
    } finally {
      setLoading(false)
    }
  }, [includeArchived])

  useEffect(() => {
    loadTeams()
  }, [loadTeams])

  useEffect(() => {
    if (!newTeamRequested || newRequestHandledRef.current) return
    newRequestHandledRef.current = true
    teamWizard.openWizard()
  }, [newTeamRequested, teamWizard])

  useTeamWizardComplete(() => {
    loadTeams()
  })

  useEffect(() => {
    const handleRefresh = () => loadTeams()
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [loadTeams])

  return (
    <div className="min-h-screen animate-fade-in" data-new-team-requested={newTeamRequested ? 'true' : undefined}>
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-3xl font-display font-bold text-white mb-2">Agent Teams</h1>
            <p className="text-tsushin-slate">Coordinate multi-agent runs from one Studio surface.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-3 py-2 text-sm font-medium text-tsushin-slate transition-colors hover:border-tsushin-muted hover:text-white">
              <input
                type="checkbox"
                checked={includeArchived}
                onChange={(event) => setIncludeArchived(event.target.checked)}
                className="h-4 w-4 cursor-pointer accent-tsushin-vermilion"
              />
              Include archived
            </label>
            <button
              type="button"
              onClick={() => teamWizard.openWizard()}
              className="btn-primary inline-flex items-center justify-center gap-2 text-sm"
            >
              <PlusIcon size={16} />
              Create Team
            </button>
            <button
              type="button"
              onClick={loadTeams}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm font-medium text-tsushin-slate transition-colors hover:border-tsushin-muted hover:text-white"
            >
              <RefreshIcon size={16} />
              Refresh
            </button>
          </div>
        </div>

        <div className="space-y-6">
          <StudioTabs />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="stat-card stat-card-indigo">
              <p className="text-sm font-medium text-tsushin-slate">Total Teams</p>
              <p className="mt-1 text-3xl font-display font-bold text-white">{total}</p>
            </div>
            <div className="stat-card stat-card-success">
              <p className="text-sm font-medium text-tsushin-slate">Shown Active</p>
              <p className="mt-1 text-3xl font-display font-bold text-white">
                {teams.filter((team) => team.status === 'active').length}
              </p>
            </div>
            <div className="stat-card stat-card-accent">
              <p className="text-sm font-medium text-tsushin-slate">Shown Members</p>
              <p className="mt-1 text-3xl font-display font-bold text-white">
                {teams.reduce((sum, team) => sum + team.member_count, 0)}
              </p>
            </div>
          </div>

          {error && (
            <div className="rounded-xl border border-tsushin-vermilion/25 bg-tsushin-vermilion/10 px-4 py-3 text-sm text-tsushin-vermilion">
              <div className="flex items-center gap-2">
                <AlertCircleIcon size={16} />
                {error}
              </div>
            </div>
          )}

          <div className="glass-card rounded-xl overflow-hidden">
            <div className="flex items-center justify-between border-b border-tsushin-border/50 px-6 py-4">
              <h2 className="text-lg font-display font-semibold text-white">Teams</h2>
              <span className="badge badge-indigo">{teams.length} shown</span>
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-16">
                <div className="h-8 w-8 animate-spin rounded-full border-2 border-tsushin-indigo/30 border-t-tsushin-indigo"></div>
              </div>
            ) : error ? (
              <div className="px-6 py-16 text-center">
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-tsushin-vermilion/10">
                  <AlertCircleIcon size={32} className="text-tsushin-vermilion" />
                </div>
                <h3 className="mb-2 text-lg font-medium text-tsushin-pearl">Teams did not load</h3>
                <p className="mx-auto max-w-md text-sm text-tsushin-slate">{error}</p>
                <button
                  type="button"
                  onClick={loadTeams}
                  className="btn-secondary mt-5 inline-flex items-center justify-center gap-2 text-sm"
                >
                  <RefreshIcon size={16} />
                  Retry
                </button>
              </div>
            ) : teams.length === 0 ? (
              <div className="px-6 py-16 text-center">
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-tsushin-surface">
                  <UsersIcon size={32} className="text-tsushin-indigo-glow" />
                </div>
                <h3 className="mb-2 text-lg font-medium text-tsushin-pearl">No teams yet</h3>
                <p className="mx-auto max-w-md text-sm text-tsushin-slate">
                  Created teams will appear here.
                </p>
              </div>
            ) : (
              <div className="divide-y divide-tsushin-border/30">
                {teams.map((team) => (
                  <div
                    key={team.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => router.push(`/studio/teams/${team.id}`)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        router.push(`/studio/teams/${team.id}`)
                      }
                    }}
                    className="cursor-pointer px-6 py-5 transition-colors hover:bg-tsushin-surface/30"
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <h3 className="text-lg font-semibold text-white">{team.name}</h3>
                          <span className={`badge ${statusBadge(team.status)}`}>{formatLabel(team.status)}</span>
                          <span className="badge badge-team flex items-center gap-1">
                            <UsersIcon size={12} /> {team.member_count} members
                          </span>
                        </div>
                        {team.description && (
                          <p className="mb-3 max-w-3xl text-sm leading-6 text-tsushin-slate">{team.description}</p>
                        )}
                        <div className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-tsushin-slate">
                          <span className="inline-flex items-center gap-1.5">
                            <PlayIcon size={14} className="opacity-70" />
                            {formatLabel(team.topology)}
                          </span>
                          <span className="inline-flex items-center gap-1.5">
                            <ClockIcon size={14} className="opacity-70" />
                            Last run: {team.last_run_status ? formatLabel(team.last_run_status) : 'None'}
                          </span>
                          <span>Max runs: {team.max_concurrent_runs}</span>
                          <span>Max steps: {team.max_steps}</span>
                        </div>
                      </div>
                      <div className="text-sm text-tsushin-muted lg:text-right">
                        Updated {formatDate(team.updated_at || team.created_at)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
