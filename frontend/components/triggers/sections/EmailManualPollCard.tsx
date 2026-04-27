'use client'

/**
 * EmailManualPollCard
 *
 * Wave 3 of the Triggers ↔ Flows unification — extracted from the email
 * fork's "Poll Now" affordance (previously folded into the Notification
 * card at lines 651-659 of `frontend/app/hub/triggers/email/[id]/page.tsx`
 * pre-Wave-3). Now rendered as its own card next to the Notification card,
 * matching the Jira layout for visual parity (visual smell #5 fix).
 */

import type { EmailPollNowResponse, EmailTrigger } from '@/lib/client'
import { PlayIcon, RefreshIcon } from '@/components/ui/icons'
import { formatDateTime } from '@/lib/dateUtils'

interface Props {
  trigger: EmailTrigger
  pollResult: EmailPollNowResponse | null
  onPollNow: () => void
  polling: boolean
  canWriteHub: boolean
}

function pollResultSummary(result: EmailPollNowResponse): string {
  if (result.success === false) {
    return result.error || result.message || result.reason || 'Poll failed'
  }
  const fetched = result.fetched_count ?? result.message_count ?? 0
  const dispatched = result.dispatched_count ?? result.emitted_count ?? result.wake_event_count ?? 0
  const processed = result.processed_count ?? 0
  const duplicates = result.duplicate_count ?? 0
  const failed = result.failed_count ?? 0
  return `Poll ${result.status || 'finished'}: ${fetched} fetched, ${dispatched} dispatched, ${processed} processed, ${duplicates} duplicate, ${failed} failed.`
}

export default function EmailManualPollCard({
  trigger,
  pollResult,
  onPollNow,
  polling,
  canWriteHub,
}: Props) {
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <h3 className="flex items-center gap-2 text-base font-semibold text-white">
        <RefreshIcon size={18} /> Manual Poll
      </h3>
      <p className="mt-2 text-sm text-tsushin-slate">
        Run the saved Gmail query now and dispatch matching wake events through the managed route.
      </p>
      {canWriteHub && (
        <button
          type="button"
          onClick={onPollNow}
          disabled={polling || !trigger.is_active}
          className="mt-4 inline-flex items-center gap-2 rounded-lg border border-blue-400/40 bg-blue-500/10 px-4 py-2 text-sm text-blue-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          <PlayIcon size={16} />
          {polling ? 'Polling...' : 'Poll Now'}
        </button>
      )}
      {pollResult && (
        <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
          pollResult.success !== false
            ? 'border-green-500/30 bg-green-500/10 text-green-200'
            : 'border-red-500/30 bg-red-500/10 text-red-200'
        }`}>
          {pollResultSummary(pollResult)}
          {(pollResult.completed_at || pollResult.status) && (
            <div className="mt-1 text-xs opacity-80">
              {pollResult.status ? `Status: ${pollResult.status}` : ''}
              {pollResult.completed_at ? ` Completed: ${formatDateTime(pollResult.completed_at)}` : ''}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
