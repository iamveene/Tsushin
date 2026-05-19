import type { EmailTrigger, GitHubTrigger, GitLabTrigger, JiraTrigger, TeamTriggerBindingKind, WebhookIntegration } from '@/lib/client'

export type TeamTriggerSource = WebhookIntegration | GitHubTrigger | GitLabTrigger | JiraTrigger | EmailTrigger | null | undefined

export const TEAM_TRIGGER_DEFAULT_EVENTS: Record<TeamTriggerBindingKind, string[]> = {
  webhook: ['message.created'],
  github: ['github.pull_request'],
  gitlab: ['gitlab.merge_request'],
  jira: ['jira.issue.detected'],
  gmail: ['email.message.received'],
}

const REPOSITORY_EVENT_NAMESPACE: Partial<Record<TeamTriggerBindingKind, string>> = {
  github: 'github',
  gitlab: 'gitlab',
}

export function defaultTeamTriggerEvents(kind: TeamTriggerBindingKind, source?: TeamTriggerSource): string[] {
  if (kind === 'github') {
    const events = (source as GitHubTrigger | null | undefined)?.events
    if (Array.isArray(events) && events.length > 0) return canonicalTeamTriggerEvents(kind, events)
  }
  if (kind === 'gitlab') {
    const events = (source as GitLabTrigger | null | undefined)?.events
    if (Array.isArray(events) && events.length > 0) return canonicalTeamTriggerEvents(kind, events)
  }
  return [...TEAM_TRIGGER_DEFAULT_EVENTS[kind]]
}

export function canonicalTeamTriggerEvent(kind: TeamTriggerBindingKind, value: unknown): string {
  const normalized = String(value ?? '').trim()
  if (!normalized) return ''
  const namespace = REPOSITORY_EVENT_NAMESPACE[kind]
  if (!namespace) return normalized
  if (normalized.startsWith(`${namespace}.`)) return normalized
  return `${namespace}.${normalized}`
}

export function canonicalTeamTriggerEvents(kind: TeamTriggerBindingKind, items: readonly unknown[]): string[] {
  return dedupeEventTypes(Array.from(items, (item) => canonicalTeamTriggerEvent(kind, item)))
}

export function dedupeEventTypes(items: readonly unknown[]): string[] {
  const normalized: string[] = []
  for (const item of items) {
    const value = String(item ?? '').trim()
    if (value && !normalized.includes(value)) normalized.push(value)
  }
  return normalized
}

export function eventTypesFromInput(value: string): string[] {
  return dedupeEventTypes(value.split(/[\n,]/))
}

export function eventTypesToInput(events: readonly unknown[]): string {
  return dedupeEventTypes(events).join(', ')
}
