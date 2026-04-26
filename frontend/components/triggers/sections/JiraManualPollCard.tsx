'use client'

/**
 * JiraManualPollCard
 *
 * Lifted from `TriggerDetailShell.renderSourceSummary` (lines 462-495 of the
 * pre-Wave-2 file). "Poll Now" button + last poll result panel for Jira
 * triggers. Behavior is unchanged from Wave 1.
 *
 * Wave 2 of the Triggers ↔ Flows unification.
 */

import type { JiraPollNowResponse, JiraTrigger } from '@/lib/client'
import { PlayIcon, RefreshIcon } from '@/components/ui/icons'
import { formatDateTime } from '@/lib/dateUtils'

interface Props {
  trigger: JiraTrigger
  pollResult: JiraPollNowResponse | null
  onPollNow: () => void
  polling: boolean
  canWriteHub: boolean
}

function pollResultSummary(result: JiraPollNowResponse): string {
  if (result.success === false) return result.error || result.message || result.reason || 'Poll failed'
  const emitted = result.emitted_count ?? result.wake_event_count ?? result.dispatched_count ?? result.matched_count
  const processed = result.processed_count ?? result.issue_count ?? result.fetched_count
  if (processed !== undefined && emitted !== undefined) {
    return `Processed ${processed} issue(s), emitted ${emitted} wake event(s).`
  }
  if (processed !== undefined) return `Processed ${processed} issue(s).`
  return result.message || result.reason || 'Poll completed.'
}

export default function JiraManualPollCard({
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
        Run the saved JQL now and dispatch matching wake events through the managed route.
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
