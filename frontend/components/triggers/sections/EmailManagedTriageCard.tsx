'use client'

/**
 * EmailManagedTriageCard
 *
 * Wave 3 of the Triggers ↔ Flows unification — extracted from the email
 * fork's "Managed Email Triage" card (lines 665-695 of the pre-Wave-3
 * `frontend/app/hub/triggers/email/[id]/page.tsx`).
 *
 * The card makes prerequisites explicit: users see the missing default
 * agent, Gmail binding, draft scope, or write permission before the primary
 * enable action becomes available.
 */

import type { ReactNode } from 'react'
import type { EmailTrigger } from '@/lib/client'
import {
  CheckCircleIcon,
  ExternalLinkIcon,
  SparklesIcon,
  XCircleIcon,
} from '@/components/ui/icons'
import type { EmailGmailIntegrationSummary } from './EmailSourceCard'

interface Props {
  trigger: EmailTrigger
  gmailIntegration?: EmailGmailIntegrationSummary | null
  onEnable: () => void
  onChooseDefaultAgent?: () => void
  onReconnectGmail?: () => void
  enabling: boolean
  reconnectingGmail?: boolean
  canWriteHub: boolean
}

function RequirementRow({
  ready,
  title,
  detail,
  action,
}: {
  ready: boolean
  title: string
  detail: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-tsushin-border/80 bg-black/15 p-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex gap-3">
        {ready ? (
          <CheckCircleIcon size={16} className="mt-0.5 shrink-0 text-green-300" />
        ) : (
          <XCircleIcon size={16} className="mt-0.5 shrink-0 text-yellow-200" />
        )}
        <div>
          <div className="text-sm font-medium text-white">{title}</div>
          <div className="mt-1 text-xs leading-relaxed text-tsushin-slate">{detail}</div>
        </div>
      </div>
      {!ready && action ? <div className="shrink-0 sm:pt-0.5">{action}</div> : null}
    </div>
  )
}

export default function EmailManagedTriageCard({
  trigger,
  gmailIntegration,
  onEnable,
  onChooseDefaultAgent,
  onReconnectGmail,
  enabling,
  reconnectingGmail = false,
  canWriteHub,
}: Props) {
  const gmailScopeUnknown = !gmailIntegration
  const missingDraftScope = Boolean(gmailIntegration && !gmailIntegration.can_draft)
  const triageUnavailable = !trigger.default_agent_id || gmailScopeUnknown || missingDraftScope
  const canEnable = canWriteHub && !triageUnavailable
  const readyCount = [
    Boolean(trigger.default_agent_id),
    Boolean(gmailIntegration),
    Boolean(gmailIntegration?.can_draft),
    canWriteHub,
  ].filter(Boolean).length
  const totalRequirements = 4

  const actionButtonClass = 'inline-flex items-center justify-center gap-1.5 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-3 py-1.5 text-xs font-medium text-cyan-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50'

  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-white">
            <SparklesIcon size={18} /> Managed Email Triage
          </h3>
          <p className="mt-2 text-sm leading-relaxed text-tsushin-slate">
            Creates a system-owned continuous-agent route for matching Gmail messages. When this
            trigger fires, Tsushin creates a Gmail draft reply for review; it does not send email.
          </p>
        </div>
        <span className={`w-fit rounded-full border px-2.5 py-1 text-xs ${
          canEnable
            ? 'border-green-500/30 bg-green-500/10 text-green-300'
            : 'border-yellow-500/30 bg-yellow-500/10 text-yellow-200'
        }`}>
          {canEnable ? 'Ready' : `Setup needed ${readyCount}/${totalRequirements}`}
        </span>
      </div>

      <div className="mt-4 space-y-2">
        <RequirementRow
          ready={Boolean(trigger.default_agent_id)}
          title="Default agent"
          detail={
            trigger.default_agent_name || trigger.default_agent_id
              ? `${trigger.default_agent_name || `Agent #${trigger.default_agent_id}`} will own triage drafts.`
              : 'Required so Tsushin knows which agent should write the draft response.'
          }
          action={
            canWriteHub && onChooseDefaultAgent ? (
              <button type="button" onClick={onChooseDefaultAgent} className={actionButtonClass}>
                Choose agent
              </button>
            ) : null
          }
        />
        <RequirementRow
          ready={Boolean(gmailIntegration)}
          title="Gmail account"
          detail={
            gmailIntegration
              ? `${gmailIntegration.email_address || gmailIntegration.name} is linked to this trigger.`
              : 'Required so the trigger can verify the Gmail account behind this inbox.'
          }
          action={
            <a href="/hub?tab=productivity" className={actionButtonClass}>
              Review Gmail <ExternalLinkIcon size={12} />
            </a>
          }
        />
        <RequirementRow
          ready={Boolean(gmailIntegration?.can_draft)}
          title="Draft permission"
          detail={
            gmailIntegration?.can_draft
              ? <span><code className="font-mono">gmail.compose</code> is authorized for draft creation.</span>
              : <span>Required before Tsushin can create Gmail drafts. Reconnect this account with <code className="font-mono">gmail.compose</code>.</span>
          }
          action={
            canWriteHub && onReconnectGmail && gmailIntegration ? (
              <button
                type="button"
                onClick={onReconnectGmail}
                disabled={reconnectingGmail}
                className={actionButtonClass}
              >
                {reconnectingGmail ? 'Preparing...' : 'Reconnect for drafts'}
              </button>
            ) : null
          }
        />
        <RequirementRow
          ready={canWriteHub}
          title="Write access"
          detail={
            canWriteHub
              ? 'Your role can create the managed continuous-agent routing.'
              : <span>Your role needs <code className="font-mono">hub.write</code> before this action can be enabled.</span>
          }
        />
      </div>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={onEnable}
          disabled={enabling || !canEnable}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          <SparklesIcon size={16} />
          {enabling ? 'Enabling...' : canEnable ? 'Enable Triage' : 'Complete requirements to enable'}
        </button>
        {!canEnable && (
          <p className="text-xs leading-relaxed text-tsushin-slate">
            Complete each required item above, then enable triage from this card.
          </p>
        )}
      </div>
    </div>
  )
}
