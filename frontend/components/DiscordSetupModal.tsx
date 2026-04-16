'use client'

import { useEffect, useState } from 'react'
import Modal from './ui/Modal'
import { EyeIcon, EyeOffIcon, AlertTriangleIcon, DiscordIcon } from '@/components/ui/icons'
import { api, type DiscordIntegrationCreate } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: DiscordIntegrationCreate) => Promise<void>
  saving: boolean
}

const PUBLIC_KEY_PATTERN = /^[a-fA-F0-9]{64}$/

export default function DiscordSetupModal({ isOpen, onClose, onSubmit, saving }: Props) {
  const [botToken, setBotToken] = useState('')
  const [applicationId, setApplicationId] = useState('')
  const [publicKey, setPublicKey] = useState('')
  const [showBotToken, setShowBotToken] = useState(false)
  const [publicBaseUrl, setPublicBaseUrl] = useState<string | null>(null)
  const [loadingSettings, setLoadingSettings] = useState(false)

  // V060-CHN-002: Discord Interactions Endpoint requires a publicly-reachable
  // HTTPS URL. We surface the tenant's configured public_base_url so the user
  // can see exactly what to paste into Discord Dev Portal once the integration
  // is created (and warn early if it's missing).
  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    setLoadingSettings(true)
    api
      .getMyTenantSettings()
      .then(s => { if (!cancelled) setPublicBaseUrl(s.public_base_url) })
      .catch(() => { if (!cancelled) setPublicBaseUrl(null) })
      .finally(() => { if (!cancelled) setLoadingSettings(false) })
    return () => { cancelled = true }
  }, [isOpen])

  const handleSubmit = async () => {
    if (!botToken.trim() || !applicationId.trim() || !publicKey.trim()) return
    const data: DiscordIntegrationCreate = {
      bot_token: botToken.trim(),
      application_id: applicationId.trim(),
      public_key: publicKey.trim().toLowerCase(),
    }
    await onSubmit(data)
    setBotToken('')
    setApplicationId('')
    setPublicKey('')
  }

  const isApplicationIdValid = /^\d{17,20}$/.test(applicationId) || applicationId.length === 0
  const isPublicKeyValid = PUBLIC_KEY_PATTERN.test(publicKey) || publicKey.length === 0

  // OAuth2 invite URL (Send Messages, Read Messages, Read History, Attach Files, Manage Messages)
  const inviteUrl = applicationId && isApplicationIdValid
    ? `https://discord.com/api/oauth2/authorize?client_id=${applicationId}&permissions=274877975552&scope=bot%20applications.commands`
    : ''

  // Show what the Interactions Endpoint URL will look like once saved (the
  // actual id is only known after creation, so we use a placeholder).
  const sampleInteractionsUrl = publicBaseUrl
    ? `${publicBaseUrl}/api/channels/discord/<id>/interactions`
    : null

  const canSubmit = !!botToken.trim() && isApplicationIdValid && PUBLIC_KEY_PATTERN.test(publicKey)

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Connect Discord Bot"
      size="lg"
      footer={
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
            disabled={saving || !canSubmit}
          >
            {saving ? 'Connecting...' : 'Connect Bot'}
          </button>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Public URL prerequisite */}
        {!loadingSettings && !publicBaseUrl && (
          <div className="p-4 bg-amber-500/10 border border-amber-500/40 rounded-lg">
            <h3 className="text-sm font-semibold text-amber-300 mb-1 flex items-center gap-2">
              <AlertTriangleIcon size={14} /> Public HTTPS URL required
            </h3>
            <p className="text-xs text-amber-100/80">
              Discord Interactions need a publicly-reachable HTTPS URL pointing at your Tsushin
              backend (port 8081). Set your <strong>Public Base URL</strong> in Hub → Settings before
              continuing — otherwise Discord can&apos;t deliver messages to the bot. For local dev,
              run <code className="bg-amber-900/40 px-1 rounded">cloudflared tunnel --url http://localhost:8081</code>{' '}
              and paste the resulting <code className="bg-amber-900/40 px-1 rounded">https://*.trycloudflare.com</code> URL.
            </p>
          </div>
        )}

        {/* Instructions */}
        <div className="p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-lg">
          <h3 className="text-sm font-semibold text-indigo-300 mb-2 flex items-center gap-2">
            <DiscordIcon size={16} className="text-indigo-400" /> How to set up a Discord Bot
          </h3>
          <ol className="text-xs text-gray-400 space-y-1 list-decimal list-inside">
            <li>Go to <code className="bg-gray-800 px-1 rounded">discord.com/developers/applications</code> and create a new application</li>
            <li>On <strong>General Information</strong>, copy the <strong>Application ID</strong> and the <strong>Public Key</strong> (64 hex chars)</li>
            <li>Under <strong>Bot</strong>, click &quot;Reset Token&quot; to generate a <strong>Bot Token</strong></li>
            <li>Enable <strong>Message Content Intent</strong> under Bot &gt; Privileged Gateway Intents</li>
            <li>Save below — Tsushin will show you the exact <strong>Interactions Endpoint URL</strong> to paste back into Discord</li>
            <li>Use the invite link below to add the bot to your server</li>
          </ol>
        </div>

        {/* Application ID */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Application ID <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={applicationId}
            onChange={(e) => setApplicationId(e.target.value)}
            placeholder="123456789012345678"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-indigo-500"
          />
          {applicationId && !isApplicationIdValid && (
            <p className="mt-1 text-xs text-amber-400 flex items-center gap-1">
              <AlertTriangleIcon size={12} /> Application ID must be a 17-20 digit number
            </p>
          )}
          <p className="mt-1 text-xs text-gray-500">Found on the General Information page of your Discord application</p>
        </div>

        {/* Public Key (NEW — was missing, blocked all Discord setup) */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Public Key <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={publicKey}
            onChange={(e) => setPublicKey(e.target.value)}
            placeholder="64-character hex Ed25519 public key"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono text-xs focus:ring-2 focus:ring-indigo-500"
          />
          {publicKey && !isPublicKeyValid && (
            <p className="mt-1 text-xs text-amber-400 flex items-center gap-1">
              <AlertTriangleIcon size={12} /> Public Key must be exactly 64 hex characters (Ed25519)
            </p>
          )}
          <p className="mt-1 text-xs text-gray-500">
            On Discord Dev Portal → General Information, copy the <strong>Public Key</strong>. Used to
            verify Ed25519 signatures on every interaction Discord sends to your endpoint.
          </p>
        </div>

        {/* Bot Token */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Bot Token <span className="text-red-400">*</span>
          </label>
          <div className="relative">
            <input
              type={showBotToken ? 'text' : 'password'}
              value={botToken}
              onChange={(e) => setBotToken(e.target.value)}
              placeholder="MTIzNDU2Nzg5MDEyMzQ1Njc4OQ.AbCdEf.GhIjKlMnOpQrStUvWxYz"
              className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-indigo-500"
            />
            <button
              type="button"
              onClick={() => setShowBotToken(!showBotToken)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
            >
              {showBotToken ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-500">Found under Bot settings. Click &quot;Reset Token&quot; to generate a new one.</p>
        </div>

        {/* Interactions Endpoint URL preview */}
        {sampleInteractionsUrl && (
          <div className="p-4 bg-gray-800/60 border border-gray-700 rounded-lg">
            <h3 className="text-sm font-semibold text-gray-200 mb-1">Interactions Endpoint URL (after save)</h3>
            <p className="text-xs text-gray-400 mb-2">
              Once saved, paste this URL into Discord Dev Portal → General Information → Interactions Endpoint URL.
              Discord will send a verification PING — Tsushin handles it automatically.
            </p>
            <code className="block px-2 py-1 bg-gray-900 text-indigo-300 text-xs font-mono rounded overflow-x-auto">
              {sampleInteractionsUrl}
            </code>
            <p className="mt-1 text-xs text-gray-500">
              <code>&lt;id&gt;</code> will be replaced by the integration ID returned after save.
            </p>
          </div>
        )}

        {/* Add to Server */}
        {applicationId && isApplicationIdValid && (
          <div className="p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-lg">
            <h3 className="text-sm font-semibold text-indigo-300 mb-2">Add Bot to Server</h3>
            <p className="text-xs text-gray-400 mb-3">
              Click the link below to invite the bot to your Discord server with the required permissions.
            </p>
            <a
              href={inviteUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600/20 text-indigo-400 border border-indigo-600/50 rounded hover:bg-indigo-600/30 text-sm transition-colors"
            >
              <DiscordIcon size={14} /> Add to Server
            </a>
          </div>
        )}

        {/* Security note */}
        <div className="p-3 bg-gray-800 rounded-lg border border-gray-700">
          <p className="text-xs text-gray-400">
            <strong className="text-gray-300">Security:</strong> The bot token is encrypted at rest. The
            public key is used to verify Ed25519 signatures on every inbound interaction (per-tenant, no
            shared secrets). Never share your bot token publicly.
          </p>
        </div>
      </div>
    </Modal>
  )
}
