'use client'

/**
 * EmailManagedNotificationCard
 *
 * Wave 3 of the Triggers ↔ Flows unification — replaces the email fork's
 * "paragraph + pills + buttons" layout with the same 4-cell DetailRow grid
 * Jira uses (`JiraManagedNotificationCard`). This is the visual smell #5 fix
 * called out in the Wave 3 plan: every Outputs card across all kinds now
 * uses the same status / recipient / subscription grid.
 *
 * The "Poll Now" affordance that used to live on this card has moved into
 * the shared `ManualPollCard` rendered next to it in `OutputsSection`.
 */

import type { ChangeEvent, ReactNode } from 'react'
import type { EmailTrigger } from '@/lib/client'
import { SparklesIcon, WhatsAppIcon } from '@/components/ui/icons'

interface Props {
  trigger: EmailTrigger
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

function statusLabel(trigger: EmailTrigger): string {
  if (trigger.notification_subscription_status) return trigger.notification_subscription_status
  return trigger.managed_notification_enabled ? 'active' : 'Not enabled'
}

function recipientPreview(trigger: EmailTrigger): string {
  return (
    trigger.managed_notification_recipient_preview ||
    trigger.notification_recipient_preview ||
    'Not configured'
  )
}

function subscriptionLabel(trigger: EmailTrigger): string {
  return trigger.managed_notification_subscription_id
    ? `#${trigger.managed_notification_subscription_id}`
    : 'Not reported'
}

export default function EmailManagedNotificationCard({
  trigger,
  phoneInput,
  onPhoneChange,
  onEnable,
  enabling,
  canWriteHub,
}: Props) {
  const enabled = Boolean(
    trigger.managed_notification_enabled ||
    trigger.notification_subscription_status ||
    trigger.managed_notification_recipient_preview,
  )
  return (
    <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
      <h3 className="flex items-center gap-2 text-base font-semibold text-white">
        <WhatsAppIcon size={18} /> Managed WhatsApp Notification
      </h3>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <DetailRow label="Status">{statusLabel(trigger)}</DetailRow>
        <DetailRow label="Recipient">{recipientPreview(trigger)}</DetailRow>
        <DetailRow label="Subscription">{subscriptionLabel(trigger)}</DetailRow>
      </div>
      {!enabled && (
        <p className="mt-4 text-sm text-tsushin-slate">
          Notification not configured. Add a recipient phone to enable, or wire a custom Flow.
        </p>
      )}
      {!trigger.default_agent_id && (
        <p className="mt-4 text-sm text-yellow-200">
          No default agent is selected; enabling creates or reuses the managed email agent.
        </p>
      )}
      {canWriteHub && (
        <div className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto]">
          <input
            type="tel"
            value={phoneInput}
            onChange={(event: ChangeEvent<HTMLInputElement>) => onPhoneChange(event.target.value)}
            placeholder="+15551234567"
            className="w-full rounded-lg border border-tsushin-border bg-black/25 px-3 py-2 text-sm text-white placeholder:text-tsushin-slate focus:border-green-500 focus:outline-none focus:ring-2 focus:ring-green-500/30"
          />
          <button
            type="button"
            onClick={onEnable}
            disabled={enabling || !phoneInput.trim()}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-green-400/40 bg-green-500/10 px-4 py-2 text-sm text-green-100 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <SparklesIcon size={16} />
            {enabling ? 'Enabling...' : enabled ? 'Update Notification' : 'Enable Notification'}
          </button>
        </div>
      )}
    </div>
  )
}
