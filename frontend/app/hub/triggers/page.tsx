'use client'

/**
 * /hub/triggers — unified triggers index page
 *
 * Wave 1 of the Triggers ↔ Flows unification (release/0.7.0). Closes the
 * 404 + redirect-loop bug where visiting /hub/triggers had no destination
 * page. Lists all 5 trigger kinds (jira, email, github, schedule, webhook)
 * in a single table with kind / status / search filters.
 *
 * Wave 2-3 will likely embed source/routing/outputs sections per trigger,
 * but the index itself stays a flat list of channels.
 */

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { api, type EmailTrigger, type GitHubTrigger, type JiraTrigger, type WebhookIntegration } from '@/lib/client'
import { formatRelative } from '@/lib/dateUtils'
import { AlertTriangleIcon, BellIcon, CodeIcon, EnvelopeIcon, GitHubIcon, RefreshIcon, WebhookIcon } from '@/components/ui/icons'

type TriggerKindFilter = '' | 'jira' | 'email' | 'github' | 'webhook'

interface TriggerRow {
  kind: 'jira' | 'email' | 'github' | 'webhook'
  id: number
  name: string
  status: string
  health: string
  is_active: boolean
  default_agent_id: number | null
  default_agent_name: string | null
  last_activity_at: string | null
  href: string
}

const KIND_LABEL: Record<TriggerRow['kind'], string> = {
  jira: 'Jira',
  email: 'Email',
  github: 'GitHub',
  webhook: 'Webhook',
}

const KIND_ICON_CLASS: Record<TriggerRow['kind'], string> = {
  jira: 'text-blue-300',
  email: 'text-emerald-300',
  github: 'text-violet-300',
  webhook: 'text-cyan-300',
}

function KindIcon({ kind, className }: { kind: TriggerRow['kind']; className?: string }) {
  const merged = `${KIND_ICON_CLASS[kind]} ${className ?? ''}`.trim()
  switch (kind) {
    case 'jira':
      return <CodeIcon size={16} className={merged} />
    case 'email':
      return <EnvelopeIcon size={16} className={merged} />
    case 'github':
      return <GitHubIcon size={16} className={merged} />
    case 'webhook':
      return <WebhookIcon size={16} className={merged} />
  }
}

function statusClass(row: TriggerRow): string {
  if (!row.is_active || row.status === 'paused') return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  if (row.status === 'error' || row.health === 'unhealthy') return 'bg-red-500/10 text-red-300 border-red-500/30'
  if (row.health === 'healthy') return 'bg-green-500/10 text-green-300 border-green-500/30'
  return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
}

function statusLabel(row: TriggerRow): string {
  if (!row.is_active || row.status === 'paused') return 'paused'
  return row.status || 'unknown'
}

function jiraToRow(t: JiraTrigger): TriggerRow {
  return {
    kind: 'jira',
    id: t.id,
    name: t.integration_name,
    status: t.status,
    health: t.health_status,
    is_active: t.is_active,
    default_agent_id: t.default_agent_id ?? null,
    default_agent_name: t.default_agent_name ?? null,
    last_activity_at: t.last_activity_at ?? null,
    href: `/hub/triggers/jira/${t.id}`,
  }
}

function emailToRow(t: EmailTrigger): TriggerRow {
  return {
    kind: 'email',
    id: t.id,
    name: t.integration_name,
    status: t.status,
    health: t.health_status,
    is_active: t.is_active,
    default_agent_id: t.default_agent_id ?? null,
    default_agent_name: t.default_agent_name ?? null,
    last_activity_at: t.last_activity_at ?? null,
    href: `/hub/triggers/email/${t.id}`,
  }
}

function githubToRow(t: GitHubTrigger): TriggerRow {
  return {
    kind: 'github',
    id: t.id,
    name: t.integration_name,
    status: t.status,
    health: t.health_status,
    is_active: t.is_active,
    default_agent_id: t.default_agent_id ?? null,
    default_agent_name: t.default_agent_name ?? null,
    last_activity_at: t.last_activity_at ?? null,
    href: `/hub/triggers/github/${t.id}`,
  }
}

function webhookToRow(t: WebhookIntegration): TriggerRow {
  return {
    kind: 'webhook',
    id: t.id,
    name: t.integration_name,
    status: t.status,
    health: t.health_status,
    is_active: t.is_active,
    default_agent_id: t.default_agent_id ?? null,
    default_agent_name: t.default_agent_name ?? null,
    last_activity_at: t.last_activity_at ?? null,
    href: `/hub/triggers/webhook/${t.id}`,
  }
}

export default function HubTriggersIndexPage() {
  const { hasPermission } = useAuth()
  const canRead = hasPermission('hub.read')

  const [rows, setRows] = useState<TriggerRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [kindFilter, setKindFilter] = useState<TriggerKindFilter>('')
  const [statusFilter, setStatusFilter] = useState<'' | 'active' | 'paused' | 'error' | 'unhealthy'>('')
  const [search, setSearch] = useState('')

  async function loadAll() {
    setLoading(true)
    setError(null)
    try {
      const [jira, email, github, webhook] = await Promise.all([
        api.listJiraTriggers().catch(() => []),
        api.listEmailTriggers().catch(() => []),
        api.listGitHubTriggers().catch(() => []),
        api.listWebhookIntegrations().catch(() => []),
      ])
      const next: TriggerRow[] = [
        ...jira.map(jiraToRow),
        ...email.map(emailToRow),
        ...github.map(githubToRow),
        ...webhook.map(webhookToRow),
      ]
      setRows(next)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load triggers')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!canRead) {
      setLoading(false)
      return
    }
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canRead])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return rows.filter((row) => {
      if (kindFilter && row.kind !== kindFilter) return false
      if (statusFilter) {
        if (statusFilter === 'active' && (!row.is_active || row.status === 'paused')) return false
        if (statusFilter === 'paused' && row.is_active && row.status !== 'paused') return false
        if (statusFilter === 'error' && row.status !== 'error') return false
        if (statusFilter === 'unhealthy' && row.health !== 'unhealthy') return false
      }
      if (q && !row.name.toLowerCase().includes(q)) return false
      return true
    })
  }, [rows, kindFilter, statusFilter, search])

  if (!canRead) {
    return (
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
        <div className="mb-6 flex items-center gap-3 text-sm text-tsushin-slate">
          <Link href="/hub" className="hover:text-white">Hub</Link>
          <span>/</span>
          <span>Triggers</span>
        </div>
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-8 text-center text-yellow-100">
          <AlertTriangleIcon size={28} className="mx-auto mb-3 text-yellow-300" />
          <div className="text-lg font-semibold text-white">You don&apos;t have permission to view triggers</div>
          <p className="mt-2 text-sm text-yellow-100/80">
            Your role does not have <code className="font-mono">hub.read</code>. Ask an admin to grant access.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8 animate-fade-in">
      <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3 text-sm text-tsushin-slate">
            <Link href="/hub" className="hover:text-white">Hub</Link>
            <span>/</span>
            <span>Triggers</span>
          </div>
          <h1 className="flex items-center gap-3 text-3xl font-display font-bold text-white">
            <BellIcon size={26} className="text-cyan-300" />
            Triggers
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-tsushin-slate">
            All inbound channels that can wake an agent. Jira, Email, GitHub, and Webhook in one place.
          </p>
        </div>
        <button
          type="button"
          onClick={loadAll}
          disabled={loading}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-border bg-tsushin-surface px-4 py-2 text-sm text-tsushin-fog hover:text-white disabled:opacity-50"
        >
          <RefreshIcon size={16} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-5 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="mb-5 grid gap-3 rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-4 md:grid-cols-[minmax(0,1fr)_180px_180px]">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by name..."
          className="w-full rounded-lg border border-tsushin-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
        />
        <select
          value={kindFilter}
          onChange={(e) => setKindFilter(e.target.value as TriggerKindFilter)}
          className="rounded-lg border border-tsushin-border bg-black/30 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
        >
          <option value="">All kinds</option>
          <option value="jira">Jira</option>
          <option value="email">Email</option>
          <option value="github">GitHub</option>
          <option value="webhook">Webhook</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          className="rounded-lg border border-tsushin-border bg-black/30 px-3 py-2 text-sm text-white focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/30"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="paused">Paused</option>
          <option value="error">Error</option>
          <option value="unhealthy">Unhealthy</option>
        </select>
      </div>

      {loading ? (
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/50 p-10 text-center text-tsushin-slate">
          Loading triggers...
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-tsushin-border p-10 text-center">
          <BellIcon size={28} className="mx-auto mb-3 text-tsushin-slate" />
          <div className="text-white">
            {rows.length === 0 ? 'No triggers configured.' : 'No triggers match the current filters.'}
          </div>
          {rows.length === 0 && (
            <p className="mt-2 text-sm text-tsushin-slate">
              Configure a new trigger from the{' '}
              <Link href="/hub?tab=communication" className="text-cyan-300 hover:text-white">
                Hub
              </Link>{' '}
              communication tab.
            </p>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-tsushin-border bg-tsushin-surface/60">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-tsushin-slate">
              <tr className="border-b border-tsushin-border">
                <th className="px-4 py-3">Kind</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Default agent</th>
                <th className="px-4 py-3">Last activity</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((row) => (
                <tr
                  key={`${row.kind}-${row.id}`}
                  className="border-b border-tsushin-border/60 transition-colors hover:bg-black/20"
                >
                  <td className="px-4 py-3">
                    <Link href={row.href} className="inline-flex items-center gap-2 text-tsushin-fog hover:text-white">
                      <KindIcon kind={row.kind} />
                      {KIND_LABEL[row.kind]}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <Link href={row.href} className="font-medium text-cyan-200 hover:text-white">
                      {row.name}
                    </Link>
                    <div className="text-xs text-tsushin-slate">#{row.id}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full border px-2.5 py-1 text-xs ${statusClass(row)}`}>
                      {statusLabel(row)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-tsushin-fog">
                    {row.default_agent_name || (row.default_agent_id ? `Agent #${row.default_agent_id}` : <span className="text-tsushin-slate">None</span>)}
                  </td>
                  <td className="px-4 py-3 text-tsushin-slate">
                    {row.last_activity_at ? formatRelative(row.last_activity_at) : 'No activity'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
