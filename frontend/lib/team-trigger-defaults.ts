import type { EmailTrigger, GitHubTrigger, GitLabTrigger, JiraTrigger, TeamTriggerBindingKind, WebhookIntegration } from '@/lib/client'

export type TeamTriggerSource = WebhookIntegration | GitHubTrigger | GitLabTrigger | JiraTrigger | EmailTrigger | null | undefined

export const TEAM_TRIGGER_DEFAULT_EVENTS: Record<TeamTriggerBindingKind, string[]> = {
  webhook: ['message.created'],
  github: ['github.pull_request'],
  gitlab: ['gitlab.merge_request'],
  jira: ['jira.issue.detected'],
  gmail: ['email.message.received'],
}

export function defaultTeamTriggerEvents(kind: TeamTriggerBindingKind, source?: TeamTriggerSource): string[] {
  if (kind === 'github') {
    const events = (source as GitHubTrigger | null | undefined)?.events
    if (Array.isArray(events) && events.length > 0) return dedupeEventTypes(events)
  }
  if (kind === 'gitlab') {
    const events = (source as GitLabTrigger | null | undefined)?.events
    if (Array.isArray(events) && events.length > 0) return dedupeEventTypes(events)
  }
  return [...TEAM_TRIGGER_DEFAULT_EVENTS[kind]]
}

export function dedupeEventTypes(items: Iterable<unknown>): string[] {
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

export function eventTypesToInput(events: Iterable<unknown>): string {
  return dedupeEventTypes(events).join(', ')
}
