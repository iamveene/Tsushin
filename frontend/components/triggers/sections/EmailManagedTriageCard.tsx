'use client'

/**
 * EmailManagedTriageCard
 *
 * Wave 3 of the Triggers ↔ Flows unification — extracted from the email
 * fork's "Managed Email Triage" card (lines 665-695 of the pre-Wave-3
 * `frontend/app/hub/triggers/email/[id]/page.tsx`).
 *
 * Behavior is preserved: the button is disabled if there's no default
 * agent, or if the linked Gmail integration lacks `gmail.compose` (i.e.
 * `can_draft === false`).
 */

import type { EmailTrigger } from '@/lib/client'
import { SparklesIcon } from '@/components/ui/icons'
import type { EmailGmailIntegrationSummary } from './EmailSourceCard'

interface Props {
  trigger: EmailTrigger
  gmailIntegration?: EmailGmailIntegrationSummary | null
  onEnable: () => void
  enabling: boolean
  canWriteHub: boolean
}

export default function EmailManagedTriageCard({
  trigger,
  gmailIntegration,
  onEnable,
  enabling,
  canWriteHub,
}: Props) {
  const missingDraftScope = Boolean(gmailIntegration && !gmailIntegration.can_draft)
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <h3 className="flex items-center gap-2 text-base font-semibold text-white">
        <SparklesIcon size={18} /> Managed Email Triage
      </h3>
      <p className="mt-2 text-sm text-tsushin-slate">
        Link this Gmail trigger to the default agent and create system-owned continuous-agent
        routing for draft-based triage.
      </p>
      {!trigger.default_agent_id && (
        <p className="mt-3 text-sm text-yellow-200">
          Choose a default agent before enabling managed triage.
        </p>
      )}
      {missingDraftScope && (
        <p className="mt-3 text-sm text-yellow-200">
          Re-authorize this Gmail account with{' '}
          <code className="font-mono">gmail.compose</code> before draft creation can run.
        </p>
      )}
      {canWriteHub && (
        <button
          type="button"
          onClick={onEnable}
          disabled={enabling || !trigger.default_agent_id || missingDraftScope}
          className="mt-4 inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          <SparklesIcon size={16} />
          {enabling ? 'Enabling...' : 'Enable Triage'}
        </button>
      )}
    </div>
  )
}
