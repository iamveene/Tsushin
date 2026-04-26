'use client'

/**
 * JiraManagedNotificationCard
 *
 * Lifted from `TriggerDetailShell.renderSourceSummary` (lines 427-461 of the
 * pre-Wave-2 file). Renders the Managed WhatsApp Notification status panel
 * plus the recipient phone input + Enable/Update CTA.
 *
 * Behavior is unchanged from Wave 1. The "Agent" row was removed because
 * the Routing section is now the canonical home for the default agent
 * (Wave 2 wording normalization).
 *
 * Wave 2 of the Triggers ↔ Flows unification.
 */

import type { ChangeEvent, ReactNode } from 'react'
import type { JiraManagedNotificationStatus, JiraTrigger } from '@/lib/client'
import { SparklesIcon, WhatsAppIcon } from '@/components/ui/icons'

interface Props {
  trigger: JiraTrigger
  notificationStatus: JiraManagedNotificationStatus | null
  phoneInput: string
  onPhoneChange: (value: string) => void
  onEnable: () => void
  enabling: boolean
  canWriteHub: boolean
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-tsushin-slate">{label}</div>
      <div className="mt-1 break-words text-sm text-white">{children}</div>
    </div>
  )
}

function statusLabel(status: JiraManagedNotificationStatus | null): string {
  return status?.status || 'Not enabled'
}

function recipientPreview(status: JiraManagedNotificationStatus | null): string {
  return status?.recipient_preview || 'Not configured'
}

export default function JiraManagedNotificationCard({
  trigger,
  notificationStatus,
  phoneInput,
  onPhoneChange,
  onEnable,
  enabling,
  canWriteHub,
}: Props) {
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <h3 className="flex items-center gap-2 text-base font-semibold text-white">
        <WhatsAppIcon size={18} /> Managed WhatsApp Notification
      </h3>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <DetailRow label="Status">{statusLabel(notificationStatus)}</DetailRow>
        <DetailRow label="Recipient">{recipientPreview(notificationStatus)}</DetailRow>
        <DetailRow label="Subscription">
          {notificationStatus?.continuous_subscription_id ? `#${notificationStatus.continuous_subscription_id}` : 'Not reported'}
        </DetailRow>
      </div>
      {!notificationStatus?.status && (
        <p className="mt-4 text-sm text-tsushin-slate">
          Notification not configured. Add a recipient phone to enable, or wire a custom Flow.
        </p>
      )}
      {!trigger.default_agent_id && (
        <p className="mt-4 text-sm text-yellow-200">
          No default agent is selected; enabling creates or reuses the managed Jira agent.
        </p>
      )}
      {canWriteHub && (
        <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <input
            type="tel"
            value={phoneInput}
            onChange={(event: ChangeEvent<HTMLInputElement>) => onPhoneChange(event.target.value)}
            placeholder="+15551234567"
            className="w-full rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-cyan-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/30"
          />
          <button
            type="button"
            onClick={onEnable}
            disabled={enabling || !phoneInput.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <SparklesIcon size={16} />
            {enabling ? 'Enabling...' : notificationStatus?.status ? 'Update Notification' : 'Enable Notification'}
          </button>
        </div>
      )}
    </div>
  )
}
