'use client'

import { useEffect, useRef, useState } from 'react'
import Modal from './ui/Modal'
import { AlertTriangleIcon, CheckCircleIcon, XCircleIcon } from '@/components/ui/icons'
import { api, type TriggerCriteria, type WebhookIntegration, type WebhookIntegrationUpdate } from '@/lib/client'
import CriteriaBuilder, { formatCriteriaText, parseCriteriaText } from '@/components/triggers/CriteriaBuilder'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSaved: () => void
  integration: WebhookIntegration | null
  apiBase: string
}

const RESERVED_SLUGS = 'inbound, rotate-secret, health, status, test, callback, docs, openapi, api, webhooks, admin, v1'

export default function WebhookEditModal({ isOpen, onClose, onSaved, integration, apiBase }: Props) {
  const [integrationName, setIntegrationName] = useState('')
  const [slug, setSlug] = useState('')
  const [callbackEnabled, setCallbackEnabled] = useState(false)
  const [callbackUrl, setCallbackUrl] = useState('')
  const [rateLimitRpm, setRateLimitRpm] = useState(30)
  const [ipAllowlistText, setIpAllowlistText] = useState('')
  const [criteriaText, setCriteriaText] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [slugStatus, setSlugStatus] = useState<
    | { state: 'idle' }
    | { state: 'checking' }
    | { state: 'ok' }
    | { state: 'error'; reason: string }
  >({ state: 'idle' })
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [originalSlug, setOriginalSlug] = useState('')

  useEffect(() => {
    if (!isOpen || !integration) return
    setIntegrationName(integration.integration_name || '')
    setSlug(integration.slug || '')
    setOriginalSlug(integration.slug || '')
    setCallbackEnabled(Boolean(integration.callback_enabled))
    setCallbackUrl(integration.callback_url || '')
    setRateLimitRpm(integration.rate_limit_rpm || 30)
    setIpAllowlistText((integration.ip_allowlist || []).join('\n'))
    setCriteriaText(formatCriteriaText(integration.trigger_criteria))
    setSlugStatus({ state: 'idle' })
    setError(null)
  }, [isOpen, integration])

  useEffect(() => {
    if (!isOpen || !integration) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const trimmed = slug.trim()
    if (!trimmed) {
      setSlugStatus({ state: 'error', reason: 'Slug required' })
      return
    }
    if (trimmed === originalSlug) {
      setSlugStatus({ state: 'idle' })
      return
    }
    setSlugStatus({ state: 'checking' })
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.checkWebhookSlugAvailable(trimmed, integration.id)
        if (res.available) setSlugStatus({ state: 'ok' })
        else setSlugStatus({ state: 'error', reason: res.reason || 'Unavailable' })
      } catch {
        setSlugStatus({ state: 'error', reason: 'Unable to check availability' })
      }
    }, 400)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [slug, isOpen, integration, originalSlug])

  const canSave = (() => {
    if (!integration || saving) return false
    if (!integrationName.trim()) return false
    if (slugStatus.state === 'checking' || slugStatus.state === 'error') return false
    return true
  })()

  const handleSave = async () => {
    if (!integration || !canSave) return
    setSaving(true)
    setError(null)
    try {
      const ipAllowlist = ipAllowlistText
        .split(/[\n,]/)
        .map(s => s.trim())
        .filter(Boolean)
      let triggerCriteria: TriggerCriteria | null
      try {
        triggerCriteria = parseCriteriaText(criteriaText)
      } catch (parseError: unknown) {
        setError(parseError instanceof Error ? parseError.message : 'Invalid criteria JSON')
        setSaving(false)
        return
      }
      const patch: WebhookIntegrationUpdate = {
        integration_name: integrationName.trim(),
        slug: slug.trim(),
        callback_enabled: callbackEnabled,
        callback_url: callbackUrl.trim() || null,
        rate_limit_rpm: rateLimitRpm,
        ip_allowlist: ipAllowlist.length > 0 ? ipAllowlist : null,
        trigger_criteria: triggerCriteria,
      }
      await api.updateWebhookIntegration(integration.id, patch)
      onSaved()
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to save webhook')
    } finally {
      setSaving(false)
    }
  }

  if (!integration) return null

  const slugPreview = slug.trim()
    ? `${apiBase}/api/webhooks/${slug.trim()}/inbound`
    : ''
  const slugChanged = slug.trim() !== originalSlug

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Edit Webhook — ${integration.integration_name}`}
      size="lg"
      footer={
        <div className="flex justify-between items-center gap-3">
          <div className="text-xs text-gray-500">
            Secret is not shown here. Use <strong className="text-gray-300">Rotate Secret</strong> on the card to issue a new one.
          </div>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="px-4 py-2 bg-cyan-500 text-white rounded hover:bg-cyan-600 disabled:opacity-50"
              disabled={!canSave}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/40 rounded text-sm text-red-300">
            {error}
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Integration Name *
          </label>
          <input
            type="text"
            value={integrationName}
            onChange={(e) => setIntegrationName(e.target.value)}
            maxLength={100}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:ring-2 focus:ring-cyan-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Inbound URI slug
          </label>
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 font-mono">/api/webhooks/</span>
            <div className="relative flex-1">
              <input
                type="text"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                maxLength={64}
                autoComplete="off"
                data-testid="webhook-edit-slug"
                className={`w-full px-3 py-2 pr-10 bg-gray-800 border rounded text-white font-mono text-sm focus:ring-2 focus:ring-cyan-500 ${
                  slugStatus.state === 'error' ? 'border-red-500/60' : slugStatus.state === 'ok' ? 'border-green-500/60' : 'border-gray-700'
                }`}
              />
              <span className="absolute right-2 top-1/2 -translate-y-1/2">
                {slugStatus.state === 'checking' && <span className="text-xs text-gray-500">…</span>}
                {slugStatus.state === 'ok' && <span className="text-green-400"><CheckCircleIcon size={16} /></span>}
                {slugStatus.state === 'error' && <span className="text-red-400"><XCircleIcon size={16} /></span>}
              </span>
            </div>
            <span className="text-xs text-gray-500 font-mono">/inbound</span>
          </div>

          {slugStatus.state === 'error' && (
            <p className="text-xs text-red-400 mt-2 flex items-center gap-1">
              <AlertTriangleIcon size={12} /> {slugStatus.reason}
            </p>
          )}
          {slugStatus.state === 'ok' && slugChanged && (
            <p className="text-xs text-green-400 mt-2">Available</p>
          )}
          {!slugChanged && (
            <p className="text-xs text-gray-500 mt-2">
              Current slug. Renaming will break any external system still pointing at <code className="text-gray-400">{originalSlug}</code>.
            </p>
          )}

          <p className="text-xs text-gray-500 mt-2">
            Lowercase letters, digits, and single hyphens; 3–64 chars; must start with a letter.
            Reserved: <code className="text-gray-400">{RESERVED_SLUGS}</code>.
          </p>

          {slugPreview && (
            <p className="mt-2 text-xs text-gray-400">
              Full URL preview: <code className="bg-gray-900 px-1 rounded text-cyan-300">{slugPreview}</code>
            </p>
          )}
        </div>

        <div className="flex items-start gap-3 p-3 bg-gray-800 border border-gray-700 rounded-lg">
          <input
            id="webhook-edit-callback-enabled"
            type="checkbox"
            checked={callbackEnabled}
            onChange={(e) => setCallbackEnabled(e.target.checked)}
            className="mt-0.5 accent-cyan-500"
          />
          <label htmlFor="webhook-edit-callback-enabled" className="flex-1 cursor-pointer">
            <div className="text-sm font-medium text-gray-300">Enable outbound callback</div>
            <div className="text-xs text-gray-500">
              When enabled, the agent&apos;s reply is POSTed back to a customer URL (HMAC-signed).
              When disabled, replies are only retrievable via the queue-polling API.
            </div>
          </label>
        </div>

        {callbackEnabled && (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Callback URL</label>
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
          <label className="block text-sm font-medium text-gray-300 mb-2">Rate limit (requests per minute)</label>
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

        <CriteriaBuilder value={criteriaText} onChange={setCriteriaText} disabled={saving} />
      </div>
    </Modal>
  )
}
