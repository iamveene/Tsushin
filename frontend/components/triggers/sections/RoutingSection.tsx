'use client'

/**
 * RoutingSection
 *
 * Single card that explains where events go when no Flow is wired below.
 * Renders the inline `<DefaultAgentChip>` so operators can change the
 * default agent without leaving the Overview tab.
 *
 * The outer div carries `id="routing-card"` so the KPI Routing slot (or
 * future deep-links) can scroll to it via
 * `document.getElementById('routing-card')?.scrollIntoView(...)`.
 *
 * Wave 2 of the Triggers ↔ Flows unification.
 */

import DefaultAgentChip from '@/components/triggers/DefaultAgentChip'
import type { EmailTrigger, GitHubTrigger, JiraTrigger, WebhookIntegration } from '@/lib/client'

type RoutingKind = 'jira' | 'github' | 'email' | 'webhook'
type RoutingTrigger = JiraTrigger | GitHubTrigger | EmailTrigger | WebhookIntegration

interface Props {
  kind: RoutingKind
  trigger: RoutingTrigger
  canEdit: boolean
  onUpdate: (next: { default_agent_id: number | null; default_agent_name: string | null }) => void
}

export default function RoutingSection({ kind, trigger, canEdit, onUpdate }: Props) {
  return (
    <div
      id="routing-card"
      className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5"
    >
      <div className="text-sm leading-relaxed text-tsushin-fog">
        <span>Events go to </span>
        <DefaultAgentChip
          triggerKind={kind}
          triggerId={trigger.id}
          agent={{ id: trigger.default_agent_id ?? null, name: trigger.default_agent_name ?? null }}
          canEdit={canEdit}
          onUpdate={onUpdate}
        />
        <span> when no Flow is wired below.</span>
      </div>
      <p className="mt-3 text-xs text-tsushin-slate">
        Default agent. Change it inline; updates apply immediately.
      </p>
    </div>
  )
}
