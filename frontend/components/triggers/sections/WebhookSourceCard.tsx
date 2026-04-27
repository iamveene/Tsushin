'use client'

/**
 * WebhookSourceCard
 *
 * Source-section card for `webhook` triggers. Renders the prominent
 * Inbound Endpoint URL (full-width) with a Copy affordance, the Security
 * panel (secret preview, IP allowlist, max payload), and the Callback /
 * Health panel.
 *
 * Wave 3 of the Triggers ↔ Flows unification — extracted from the
 * pre-Wave-3 `frontend/app/hub/triggers/webhook/[id]/page.tsx` (lines
 * 268-343).
 */

import type { ReactNode } from 'react'
import type { PublicIngressInfo, WebhookIntegration } from '@/lib/client'
import { ClockIcon, CopyIcon, RefreshIcon, WebhookIcon } from '@/components/ui/icons'
import { formatDateTime, formatRelative } from '@/lib/dateUtils'

interface Props {
  trigger: WebhookIntegration
  publicIngress?: PublicIngressInfo | null
  absoluteInboundUrl: string
  copied: boolean
  onCopy: () => void
  rotating?: boolean
  onRotateSecret?: () => void
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

export default function WebhookSourceCard({
  trigger,
  publicIngress,
  absoluteInboundUrl,
  copied,
  onCopy,
  rotating = false,
  onRotateSecret,
  canWriteHub,
}: Props) {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
        <h3 className="flex items-center gap-2 text-base font-semibold text-white">
          <WebhookIcon size={18} /> Inbound Endpoint
        </h3>
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <code className="min-w-0 flex-1 break-all rounded-lg border border-tsushin-border bg-black/30 p-3 text-xs text-cyan-200">
            {absoluteInboundUrl}
          </code>
          <button
            type="button"
            onClick={onCopy}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/10 px-4 py-2 text-sm text-cyan-200 hover:text-white"
          >
            <CopyIcon size={16} />
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
        {publicIngress?.warning && (
          <p className="mt-2 text-xs text-yellow-200">{publicIngress.warning}</p>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
          <h3 className="text-base font-semibold text-white">Security</h3>
          <div className="mt-4 space-y-4 text-sm">
            <div>
              <div className="flex items-center justify-between gap-3">
                <div className="text-xs text-tsushin-slate">Secret preview</div>
                {canWriteHub && onRotateSecret && (
                  <button
                    type="button"
                    onClick={onRotateSecret}
                    disabled={rotating}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-yellow-500/40 bg-yellow-500/10 px-2.5 py-1 text-xs text-yellow-200 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <RefreshIcon size={12} />
                    {rotating ? 'Rotating...' : 'Rotate'}
                  </button>
                )}
              </div>
              <code className="mt-1 block rounded-lg border border-tsushin-border bg-black/30 p-3 text-xs text-cyan-200">
                {trigger.api_secret_preview}
              </code>
            </div>
            <div>
              <div className="text-xs text-tsushin-slate">IP allowlist</div>
              <div className="mt-1 flex flex-wrap gap-2">
                {(trigger.ip_allowlist || []).length > 0
                  ? trigger.ip_allowlist!.map(cidr => (
                      <span
                        key={cidr}
                        className="rounded-full border border-tsushin-border bg-black/20 px-2.5 py-1 text-xs text-tsushin-fog"
                      >
                        {cidr}
                      </span>
                    ))
                  : <span className="text-tsushin-slate">Any source allowed by upstream network policy</span>}
              </div>
            </div>
            <DetailRow label="Max payload">{`${trigger.max_payload_bytes.toLocaleString()} bytes`}</DetailRow>
            <DetailRow label="Rate limit">{`${trigger.rate_limit_rpm} req/min`}</DetailRow>
          </div>
        </div>

        <div className="rounded-xl border border-tsushin-border bg-tsushin-surface/60 p-5">
          <h3 className="flex items-center gap-2 text-base font-semibold text-white">
            <ClockIcon size={18} /> Callback and Health
          </h3>
          <div className="mt-4 space-y-4 text-sm">
            <DetailRow label="Callback">
              {trigger.callback_enabled
                ? (trigger.callback_url || 'Enabled without URL')
                : 'Disabled'}
            </DetailRow>
            <DetailRow label="Health">
              <div>{trigger.health_status || 'unknown'}</div>
              <div className="text-xs text-tsushin-slate">
                {trigger.last_health_check
                  ? `Checked ${formatRelative(trigger.last_health_check)}`
                  : 'No health check recorded'}
              </div>
            </DetailRow>
            <DetailRow label="Circuit breaker">{trigger.circuit_breaker_state}</DetailRow>
            <div className="grid grid-cols-2 gap-3">
              <DetailRow label="Created">{formatDateTime(trigger.created_at)}</DetailRow>
              <DetailRow label="Updated">{trigger.updated_at ? formatDateTime(trigger.updated_at) : '-'}</DetailRow>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
