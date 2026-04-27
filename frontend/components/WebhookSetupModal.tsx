'use client'

import { useEffect, useRef, useState } from 'react'
import Modal from './ui/Modal'
import { AlertTriangleIcon, CheckCircleIcon, XCircleIcon } from '@/components/ui/icons'
import WebhookSecretRevealModal from './WebhookSecretRevealModal'
import { api, WebhookIntegrationCreate } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: WebhookIntegrationCreate) => Promise<{ api_secret: string; inbound_url: string } | null>
  saving: boolean
  apiBase: string  // e.g., "https://localhost" — used to show absolute inbound URL
}

type Phase = 'form' | 'secret'
type UriMode = 'auto' | 'custom'

const RESERVED_SLUGS = 'inbound, rotate-secret, health, status, test, callback, docs, openapi, api, webhooks, admin, v1'

export default function WebhookSetupModal({ isOpen, onClose, onSubmit, saving, apiBase }: Props) {
  const [phase, setPhase] = useState<Phase>('form')
  const [integrationName, setIntegrationName] = useState('')
  const [uriMode, setUriMode] = useState<UriMode>('auto')
  const [customSlug, setCustomSlug] = useState('')
  const [slugStatus, setSlugStatus] = useState<
    | { state: 'idle' }
    | { state: 'checking' }
    | { state: 'ok' }
    | { state: 'error'; reason: string }
  >({ state: 'idle' })
  const [callbackEnabled, setCallbackEnabled] = useState(false)
  const [callbackUrl, setCallbackUrl] = useState('')
  const [rateLimitRpm, setRateLimitRpm] = useState(30)
  const [ipAllowlistText, setIpAllowlistText] = useState('')
  const [plaintextSecret, setPlaintextSecret] = useState('')
  const [createdInboundUrl, setCreatedInboundUrl] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const resetForm = () => {
    setPhase('form')
    setIntegrationName('')
    setUriMode('auto')
    setCustomSlug('')
    setSlugStatus({ state: 'idle' })
    setCallbackEnabled(false)
    setCallbackUrl('')
    setRateLimitRpm(30)
    setIpAllowlistText('')
    setPlaintextSecret('')
    setCreatedInboundUrl('')
  }

  const handleClose = () => {
    resetForm()
    onClose()
  }

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (uriMode !== 'custom') {
      setSlugStatus({ state: 'idle' })
      return
    }
    const trimmed = customSlug.trim()
    if (!trimmed) {
      setSlugStatus({ state: 'idle' })
      return
    }
    setSlugStatus({ state: 'checking' })
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.checkWebhookSlugAvailable(trimmed)
        if (res.available) {
          setSlugStatus({ state: 'ok' })
        } else {
          setSlugStatus({ state: 'error', reason: res.reason || 'Unavailable' })
        }
      } catch {
        setSlugStatus({ state: 'error', reason: 'Unable to check availability' })
      }
    }, 400)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [customSlug, uriMode])

  const canSubmit = (() => {
    if (!integrationName.trim() || saving) return false
    if (uriMode === 'custom') {
      if (slugStatus.state !== 'ok') return false
    }
    return true
  })()

  const handleCreate = async () => {
    if (!canSubmit) return
    const ipAllowlist = ipAllowlistText
      .split(/[\n,]/)
      .map(s => s.trim())
      .filter(Boolean)
    const payload: WebhookIntegrationCreate = {
      integration_name: integrationName.trim(),
      callback_enabled: callbackEnabled,
      callback_url: callbackUrl.trim() || null,
      rate_limit_rpm: rateLimitRpm,
      ip_allowlist: ipAllowlist.length > 0 ? ipAllowlist : null,
    }
    if (uriMode === 'custom') {
      payload.slug = customSlug.trim()
    }
    const result = await onSubmit(payload)
    if (result) {
      setPlaintextSecret(result.api_secret)
      setCreatedInboundUrl(result.inbound_url)
      setPhase('secret')
    }
  }

  const slugPreview =
    uriMode === 'custom' && customSlug.trim()
      ? `${apiBase}/api/webhooks/${customSlug.trim()}/inbound`
      : uriMode === 'auto'
        ? `${apiBase}/api/webhooks/wh-xxxxxx/inbound`
        : ''

  if (phase === 'secret') {
    return (
      <WebhookSecretRevealModal
        isOpen={isOpen}
        onClose={handleClose}
        secret={plaintextSecret}
        inboundUrl={createdInboundUrl}
        apiBase={apiBase}
      />
    )
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="Create Webhook Integration"
      size="lg"
      footer={
        <div className="flex justify-end gap-3">
          <button
            onClick={handleClose}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            className="px-4 py-2 bg-cyan-500 text-white rounded hover:bg-cyan-600 disabled:opacity-50"
            disabled={!canSubmit}
          >
            {saving ? 'Creating...' : 'Create Webhook'}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="p-4 bg-cyan-500/10 border border-cyan-500/30 rounded-lg">
          <h3 className="text-sm font-semibold text-cyan-300 mb-2">
            HTTP Webhook Integration
          </h3>
          <p className="text-xs text-gray-400">
            External systems POST HMAC-signed events to an inbound URL; your agent&apos;s reply can POST back
            to a callback URL. Signature is verified with HMAC-SHA256 + timestamp replay protection (±5 min).
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Integration Name *
          </label>
          <input
            type="text"
            value={integrationName}
            onChange={(e) => setIntegrationName(e.target.value)}
            placeholder="e.g. Acme CRM, Zapier, Internal App"
            maxLength={100}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:ring-2 focus:ring-cyan-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Inbound URI
          </label>
          <div className="flex gap-4 text-sm text-gray-300 mb-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="webhook-uri-mode"
                value="auto"
                checked={uriMode === 'auto'}
                onChange={() => setUriMode('auto')}
                className="accent-cyan-500"
              />
              <span>Auto</span>
              <span className="text-xs text-gray-500">(generated)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="webhook-uri-mode"
                value="custom"
                checked={uriMode === 'custom'}
                onChange={() => setUriMode('custom')}
                className="accent-cyan-500"
              />
              <span>Custom</span>
              <span className="text-xs text-gray-500">(human-readable slug)</span>
            </label>
          </div>

          {uriMode === 'custom' && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 font-mono">/api/webhooks/</span>
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={customSlug}
                    onChange={(e) => setCustomSlug(e.target.value)}
                    placeholder="acme-crm"
                    maxLength={64}
                    autoComplete="off"
                    data-testid="webhook-custom-slug"
                    className={`w-full px-3 py-2 pr-10 bg-gray-800 border rounded text-white font-mono text-sm focus:ring-2 focus:ring-cyan-500 ${
                      slugStatus.state === 'error' ? 'border-red-500/60' : slugStatus.state === 'ok' ? 'border-green-500/60' : 'border-gray-700'
                    }`}
                  />
                  <span className="absolute right-2 top-1/2 -translate-y-1/2">
                    {slugStatus.state === 'checking' && (
                      <span className="text-xs text-gray-500">…</span>
                    )}
                    {slugStatus.state === 'ok' && (
                      <span className="text-green-400"><CheckCircleIcon size={16} /></span>
                    )}
                    {slugStatus.state === 'error' && (
                      <span className="text-red-400"><XCircleIcon size={16} /></span>
                    )}
                  </span>
                </div>
                <span className="text-xs text-gray-500 font-mono">/inbound</span>
              </div>

              {slugStatus.state === 'error' && (
                <p className="text-xs text-red-400 flex items-center gap-1">
                  <AlertTriangleIcon size={12} /> {slugStatus.reason}
                </p>
              )}
              {slugStatus.state === 'ok' && (
                <p className="text-xs text-green-400">Available</p>
              )}

              <p className="text-xs text-gray-500">
                Lowercase letters, digits, and single hyphens; 3–64 chars; must start with a letter.
                Reserved: <code className="text-gray-400">{RESERVED_SLUGS}</code>.
              </p>
            </div>
          )}

          {slugPreview && (
            <p className="mt-2 text-xs text-gray-400">
              Full URL preview:{' '}
              <code className="bg-gray-900 px-1 rounded text-cyan-300">{slugPreview}</code>
            </p>
          )}
        </div>

        <div className="flex items-start gap-3 p-3 bg-gray-800 border border-gray-700 rounded-lg">
          <input
            id="webhook-callback-enabled"
            type="checkbox"
            checked={callbackEnabled}
            onChange={(e) => setCallbackEnabled(e.target.checked)}
            className="mt-0.5 accent-cyan-500"
          />
          <label htmlFor="webhook-callback-enabled" className="flex-1 cursor-pointer">
            <div className="text-sm font-medium text-gray-300">Enable outbound callback</div>
            <div className="text-xs text-gray-500">
              When enabled, the agent&apos;s reply is POSTed back to a customer URL (HMAC-signed).
              When disabled, replies are only retrievable via the queue-polling API.
            </div>
          </label>
        </div>

        {callbackEnabled && (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Callback URL
            </label>
            <input
              type="url"
              value={callbackUrl}
              onChange={(e) => setCallbackUrl(e.target.value)}
              placeholder="https://your-system.example.com/tsushin-webhook"
              maxLength={500}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-cyan-500"
            />
            <p className="mt-1 text-xs text-gray-500">
              SSRF-validated. Private IPs, loopback, and cloud metadata addresses are blocked.
            </p>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Rate limit (requests per minute)
          </label>
          <input
            type="number"
            value={rateLimitRpm}
            onChange={(e) => setRateLimitRpm(Math.max(1, Math.min(600, parseInt(e.target.value) || 30)))}
            min={1}
            max={600}
            className="w-32 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:ring-2 focus:ring-cyan-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            IP allowlist (optional, one CIDR per line)
          </label>
          <textarea
            value={ipAllowlistText}
            onChange={(e) => setIpAllowlistText(e.target.value)}
            placeholder="10.0.0.0/8&#10;203.0.113.0/24"
            rows={3}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono text-xs focus:ring-2 focus:ring-cyan-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            If set, inbound requests from IPs outside the allowlist are rejected.
          </p>
        </div>
      </div>
    </Modal>
  )
}
