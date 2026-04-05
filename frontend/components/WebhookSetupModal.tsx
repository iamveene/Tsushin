'use client'

import { useState } from 'react'
import Modal from './ui/Modal'
import { AlertTriangleIcon, CopyIcon, CheckCircleIcon } from '@/components/ui/icons'
import { WebhookIntegrationCreate } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: WebhookIntegrationCreate) => Promise<{ api_secret: string; inbound_url: string } | null>
  saving: boolean
  apiBase: string  // e.g., "https://localhost" — used to show absolute inbound URL
}

type Phase = 'form' | 'secret'

export default function WebhookSetupModal({ isOpen, onClose, onSubmit, saving, apiBase }: Props) {
  const [phase, setPhase] = useState<Phase>('form')
  const [integrationName, setIntegrationName] = useState('')
  const [callbackEnabled, setCallbackEnabled] = useState(false)
  const [callbackUrl, setCallbackUrl] = useState('')
  const [rateLimitRpm, setRateLimitRpm] = useState(30)
  const [ipAllowlistText, setIpAllowlistText] = useState('')
  const [plaintextSecret, setPlaintextSecret] = useState('')
  const [createdInboundUrl, setCreatedInboundUrl] = useState('')
  const [copied, setCopied] = useState<'secret' | 'url' | null>(null)

  const resetForm = () => {
    setPhase('form')
    setIntegrationName('')
    setCallbackEnabled(false)
    setCallbackUrl('')
    setRateLimitRpm(30)
    setIpAllowlistText('')
    setPlaintextSecret('')
    setCreatedInboundUrl('')
    setCopied(null)
  }

  const handleClose = () => {
    resetForm()
    onClose()
  }

  const handleCreate = async () => {
    if (!integrationName.trim()) return
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
    const result = await onSubmit(payload)
    if (result) {
      setPlaintextSecret(result.api_secret)
      setCreatedInboundUrl(result.inbound_url)
      setPhase('secret')
    }
  }

  const copyToClipboard = async (text: string, kind: 'secret' | 'url') => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(kind)
      setTimeout(() => setCopied(null), 2000)
    } catch {
      // no-op
    }
  }

  const fullInboundUrl = createdInboundUrl.startsWith('http')
    ? createdInboundUrl
    : `${apiBase}${createdInboundUrl}`

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={phase === 'form' ? 'Create Webhook Integration' : 'Webhook Created — Save Your Secret'}
      size="lg"
      footer={
        phase === 'form' ? (
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
              disabled={saving || !integrationName.trim()}
            >
              {saving ? 'Creating...' : 'Create Webhook'}
            </button>
          </div>
        ) : (
          <div className="flex justify-end">
            <button
              onClick={handleClose}
              className="px-4 py-2 bg-cyan-500 text-white rounded hover:bg-cyan-600"
            >
              I&apos;ve saved the secret
            </button>
          </div>
        )
      }
    >
      {phase === 'form' ? (
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
      ) : (
        <div className="space-y-4">
          <div className="p-4 bg-amber-500/10 border border-amber-500/40 rounded-lg">
            <div className="flex items-start gap-2">
              <span className="text-amber-400 mt-0.5"><AlertTriangleIcon size={16} /></span>
              <div>
                <h3 className="text-sm font-semibold text-amber-300 mb-1">Save this secret now</h3>
                <p className="text-xs text-gray-400">
                  This secret will <strong>never be shown again</strong>. You can rotate it later, but you cannot
                  view the existing secret. Store it in your external system&apos;s secrets manager.
                </p>
              </div>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              HMAC Signing Secret
            </label>
            <div className="relative">
              <input
                type="text"
                value={plaintextSecret}
                readOnly
                className="w-full px-3 py-2 pr-12 bg-gray-900 border border-cyan-500/40 rounded text-cyan-300 font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => copyToClipboard(plaintextSecret, 'secret')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-gray-400 hover:text-white"
                title="Copy secret"
              >
                {copied === 'secret' ? <CheckCircleIcon size={16} /> : <CopyIcon size={16} />}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Inbound URL
            </label>
            <div className="relative">
              <input
                type="text"
                value={fullInboundUrl}
                readOnly
                className="w-full px-3 py-2 pr-12 bg-gray-900 border border-gray-700 rounded text-gray-300 font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => copyToClipboard(fullInboundUrl, 'url')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-gray-400 hover:text-white"
                title="Copy URL"
              >
                {copied === 'url' ? <CheckCircleIcon size={16} /> : <CopyIcon size={16} />}
              </button>
            </div>
          </div>

          <div className="p-3 bg-gray-800 rounded-lg border border-gray-700">
            <p className="text-xs text-gray-400 mb-2">
              <strong className="text-gray-300">Signing instructions:</strong> For each request, compute
              <code className="bg-gray-900 px-1 mx-1 rounded text-cyan-300">HMAC-SHA256(secret, timestamp + &quot;.&quot; + body)</code>
              and send as
              <code className="bg-gray-900 px-1 mx-1 rounded text-cyan-300">X-Tsushin-Signature: sha256=&lt;hex&gt;</code>
              with
              <code className="bg-gray-900 px-1 mx-1 rounded text-cyan-300">X-Tsushin-Timestamp: &lt;unix_seconds&gt;</code>
              (±5 min from server time).
            </p>
          </div>
        </div>
      )}
    </Modal>
  )
}
