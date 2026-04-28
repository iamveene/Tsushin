'use client'

import { useState } from 'react'
import type { ComponentType, ReactNode } from 'react'
import Link from 'next/link'
import { api, type GitHubTrigger, type JiraTrigger, type TriggerKind } from '@/lib/client'
import { formatRelative } from '@/lib/dateUtils'
import { CodeIcon, GitHubIcon, type IconProps } from '@/components/ui/icons'

type BreadthTriggerKind = Extract<TriggerKind, 'jira' | 'github'>
type BreadthTrigger = JiraTrigger | GitHubTrigger

interface Props {
  jiraTriggers: JiraTrigger[]
  githubTriggers: GitHubTrigger[]
  canWrite: boolean
  onCreate: (kind: BreadthTriggerKind) => void
  onChanged: () => Promise<void> | void
  onError?: (message: string) => void
  onSuccess?: (message: string) => void
}

interface GroupConfig<T extends BreadthTrigger> {
  kind: BreadthTriggerKind
  title: string
  description: string
  emptyTitle: string
  emptyBody: string
  createLabel: string
  Icon: ComponentType<IconProps>
  iconClass: string
  borderClass: string
  actionClass: string
  detailBase: string
  items: T[]
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function statusClass(trigger: BreadthTrigger): string {
  if (!trigger.is_active || trigger.status === 'paused') return 'bg-gray-500/20 text-gray-300 border-gray-500/50'
  if (trigger.status === 'error' || trigger.health_status === 'unhealthy') return 'bg-red-500/20 text-red-300 border-red-500/50'
  if (trigger.health_status === 'healthy') return 'bg-green-500/20 text-green-300 border-green-500/50'
  return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
}

function statusLabel(trigger: BreadthTrigger): string {
  if (!trigger.is_active || trigger.status === 'paused') return 'Paused'
  if (trigger.status === 'error') return 'Error'
  if (trigger.health_status === 'healthy') return 'Active'
  return trigger.status || 'Unknown'
}

function safeRelative(value?: string | null): string {
  return value ? formatRelative(value) : 'No activity'
}

function DetailLine({ label, children }: { label: string; children: ReactNode }) {
  return (
    <p>
      {label}: <span className="text-white">{children}</span>
    </p>
  )
}

export default function TriggerBreadthCards({
  jiraTriggers,
  githubTriggers,
  canWrite,
  onCreate,
  onChanged,
  onError,
  onSuccess,
}: Props) {
  const [updatingKey, setUpdatingKey] = useState<string | null>(null)

  const groups: Array<GroupConfig<BreadthTrigger>> = [
    {
      kind: 'jira',
      title: 'Jira Triggers',
      description: 'JQL polling for matching issues and service desk handoffs.',
      emptyTitle: 'No Jira triggers',
      emptyBody: 'Watch issues by JQL and route matching issues to an agent.',
      createLabel: 'Create Jira Trigger',
      Icon: CodeIcon,
      iconClass: 'text-blue-300',
      borderClass: 'border-blue-700/30',
      actionClass: 'bg-blue-600/20 text-blue-300 border-blue-600/50 hover:bg-blue-600/30',
      detailBase: '/hub/triggers/jira',
      items: jiraTriggers,
    },
    {
      kind: 'github',
      title: 'GitHub Triggers',
      description: 'Repository activity from pushes, pull requests, issues, and releases.',
      emptyTitle: 'No GitHub triggers',
      emptyBody: 'Connect a repository and route selected events into wake events.',
      createLabel: 'Create GitHub Trigger',
      Icon: GitHubIcon,
      iconClass: 'text-violet-300',
      borderClass: 'border-violet-700/30',
      actionClass: 'bg-violet-600/20 text-violet-300 border-violet-600/50 hover:bg-violet-600/30',
      detailBase: '/hub/triggers/github',
      items: githubTriggers,
    },
  ]

  const handleToggle = async (kind: BreadthTriggerKind, trigger: BreadthTrigger) => {
    const key = `${kind}:${trigger.id}`
    setUpdatingKey(key)
    try {
      const next = !trigger.is_active
      if (kind === 'jira') {
        await api.updateJiraTrigger(trigger.id, { is_active: next })
      } else {
        await api.updateGitHubTrigger(trigger.id, { is_active: next })
      }
      await onChanged()
      onSuccess?.(next ? `${trigger.integration_name} resumed` : `${trigger.integration_name} paused`)
    } catch (error: unknown) {
      onError?.(getErrorMessage(error, `Failed to update ${kind} trigger`))
    } finally {
      setUpdatingKey(null)
    }
  }

  const renderDetails = (kind: BreadthTriggerKind, trigger: BreadthTrigger) => {
    if (kind === 'jira') {
      const jira = trigger as JiraTrigger
      return (
        <>
          <DetailLine label="Site">{jira.site_url}</DetailLine>
          <DetailLine label="JQL">{jira.jql}</DetailLine>
          <DetailLine label="Poll">{jira.poll_interval_seconds}s</DetailLine>
        </>
      )
    }
    const github = trigger as GitHubTrigger
    return (
      <>
        <DetailLine label="Repository">{github.repo_owner}/{github.repo_name}</DetailLine>
        <DetailLine label="Events">{(github.events || []).length > 0 ? github.events!.join(', ') : 'Default'}</DetailLine>
        <DetailLine label="Branch">{github.branch_filter || 'Any branch'}</DetailLine>
      </>
    )
  }

  return (
    <div className="space-y-5">
      {groups.map((group) => {
        const Icon = group.Icon
        return (
          <div key={group.kind} className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="flex items-center gap-2 text-md font-semibold text-white">
                  <Icon size={18} className={group.iconClass} /> {group.title}
                </h3>
                <p className="mt-1 text-xs text-tsushin-slate">{group.description}</p>
              </div>
              {canWrite && (
                <button
                  type="button"
                  onClick={() => onCreate(group.kind)}
                  className={`rounded px-3 py-1.5 text-xs border ${group.actionClass}`}
                >
                  {group.createLabel}
                </button>
              )}
            </div>

            {group.items.length === 0 ? (
              <div className="rounded-xl border border-dashed border-tsushin-border p-5">
                <div className="text-sm font-medium text-white">{group.emptyTitle}</div>
                <p className="mt-1 text-sm text-tsushin-slate">{group.emptyBody}</p>
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {group.items.map((trigger) => {
                  const key = `${group.kind}:${trigger.id}`
                  return (
                    <div key={key} className={`card p-5 hover-glow ${group.borderClass}`}>
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h4 className="truncate font-semibold text-white">{trigger.integration_name}</h4>
                          <p className="text-xs text-tsushin-slate">Last activity: {safeRelative(trigger.last_activity_at)}</p>
                        </div>
                        <span className={`shrink-0 rounded-full border px-2 py-1 text-xs font-medium ${statusClass(trigger)}`}>
                          {statusLabel(trigger)}
                        </span>
                      </div>

                      <div className="mb-4 space-y-1 text-xs text-tsushin-slate">
                        {renderDetails(group.kind, trigger)}
                        <DetailLine label="Default agent">{trigger.default_agent_name || (trigger.default_agent_id ? `Agent #${trigger.default_agent_id}` : 'None')}</DetailLine>
                      </div>

                      <div className="grid grid-cols-2 gap-2">
                        <Link
                          href={`${group.detailBase}/${trigger.id}`}
                          className="rounded border border-gray-600 bg-gray-700 px-3 py-1.5 text-center text-xs text-gray-200 hover:bg-gray-600"
                        >
                          Details
                        </Link>
                        {canWrite && (
                          <button
                            type="button"
                            onClick={() => handleToggle(group.kind, trigger)}
                            disabled={updatingKey === key}
                            className="rounded border border-gray-600 bg-gray-700 px-3 py-1.5 text-xs text-gray-200 hover:bg-gray-600 disabled:opacity-50"
                          >
                            {updatingKey === key ? 'Saving...' : trigger.is_active ? 'Pause' : 'Resume'}
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
