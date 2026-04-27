'use client'

/**
 * EmailSourceCard
 *
 * Source-section card for `email` triggers. Renders the Gmail Inbox Binding
 * (account, integration, provider, integration health) plus a few timing /
 * health hints (poll interval, trigger health). The default agent is owned
 * by the Routing section, so it is intentionally NOT shown here. The
 * created/updated timestamps are shown by the shared accent strip below
 * the KPI grid, so they are not duplicated here either.
 *
 * Wave 3 of the Triggers ↔ Flows unification — extracted from the
 * pre-Wave-3 `frontend/app/hub/triggers/email/[id]/page.tsx` Inbox Binding
 * (lines 568-585) + Routing Detail (lines 587-607) cards.
 */

import type { ReactNode } from 'react'
import type { EmailTrigger } from '@/lib/client'
import { ClockIcon, EnvelopeIcon } from '@/components/ui/icons'

export interface EmailGmailIntegrationSummary {
  id: number
  name: string
  email_address: string
  health_status: string
  health_status_reason?: string | null
  is_active: boolean
  can_send: boolean
  can_draft?: boolean
}

interface Props {
  trigger: EmailTrigger
  gmailIntegration?: EmailGmailIntegrationSummary | null
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-tsushin-slate">{label}</div>
      <div className="mt-1 break-words text-sm text-white">{children}</div>
    </div>
  )
}

function healthClass(healthStatus?: string | null): string {
  if (healthStatus === 'healthy') return 'bg-green-500/10 text-green-300 border-green-500/30'
  if (healthStatus === 'unhealthy') return 'bg-red-500/10 text-red-300 border-red-500/30'
  if (healthStatus === 'disconnected') return 'bg-gray-500/10 text-gray-300 border-gray-500/30'
  return 'bg-cyan-500/10 text-cyan-300 border-cyan-500/30'
}

export default function EmailSourceCard({ trigger, gmailIntegration }: Props) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
        <h3 className="flex items-center gap-2 text-base font-semibold text-white">
          <EnvelopeIcon size={18} /> Inbox Binding
        </h3>
        <div className="mt-4 space-y-4 text-sm">
          <DetailRow label="Gmail account">{trigger.gmail_account_email || 'Not reported'}</DetailRow>
          <DetailRow label="Gmail integration">
            {trigger.gmail_integration_name || trigger.gmail_integration_id || '-'}
          </DetailRow>
          <DetailRow label="Provider">{trigger.provider}</DetailRow>
          <DetailRow label="Integration health">
            <span className={`rounded-full border px-2.5 py-1 text-xs ${healthClass(gmailIntegration?.health_status)}`}>
              {gmailIntegration?.health_status || 'unknown'}
            </span>
            {gmailIntegration?.health_status_reason && (
              <p className="mt-2 text-xs text-yellow-200">{gmailIntegration.health_status_reason}</p>
            )}
          </DetailRow>
        </div>
      </div>

      <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
        <h3 className="flex items-center gap-2 text-base font-semibold text-white">
          <ClockIcon size={18} /> Cadence and Health
        </h3>
        <div className="mt-4 space-y-4 text-sm">
          <DetailRow label="Poll interval">{`${trigger.poll_interval_seconds}s`}</DetailRow>
          <DetailRow label="Trigger health">
            <span>{trigger.health_status || 'unknown'}</span>
            {trigger.health_status_reason && (
              <p className="mt-1 text-xs text-yellow-200">{trigger.health_status_reason}</p>
            )}
          </DetailRow>
          <DetailRow label="Search query">
            {trigger.search_query
              ? <code className="block break-all rounded-lg border border-tsushin-border bg-black/30 p-2 text-xs text-cyan-200">{trigger.search_query}</code>
              : <span className="text-tsushin-slate">No search query saved</span>}
          </DetailRow>
        </div>
      </div>
    </div>
  )
}
