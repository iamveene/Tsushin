'use client'

import { useState } from 'react'
import Modal from './ui/Modal'
import { EyeIcon, EyeOffIcon, AlertTriangleIcon, SlackIcon } from '@/components/ui/icons'
import type { SlackIntegrationCreate } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: SlackIntegrationCreate) => Promise<void>
  saving: boolean
}

export default function SlackSetupModal({ isOpen, onClose, onSubmit, saving }: Props) {
  const [botToken, setBotToken] = useState('')
  const [appToken, setAppToken] = useState('')
  const [signingSecret, setSigningSecret] = useState('')
  const [mode, setMode] = useState<'socket' | 'http'>('socket')
  const [dmPolicy, setDmPolicy] = useState<'open' | 'allowlist' | 'disabled'>('allowlist')
  const [showBotToken, setShowBotToken] = useState(false)
  const [showAppToken, setShowAppToken] = useState(false)
  const [showSigningSecret, setShowSigningSecret] = useState(false)

  const handleSubmit = async () => {
    if (!botToken.trim()) return
    const data: SlackIntegrationCreate = {
      bot_token: botToken.trim(),
      mode,
      dm_policy: dmPolicy,
    }
    if (mode === 'socket' && appToken.trim()) {
      data.app_token = appToken.trim()
    }
    if (mode === 'http' && signingSecret.trim()) {
      data.signing_secret = signingSecret.trim()
    }
    await onSubmit(data)
    // Reset form on success
    setBotToken('')
    setAppToken('')
    setSigningSecret('')
    setMode('socket')
    setDmPolicy('allowlist')
  }

  const isBotTokenValid = botToken.startsWith('xoxb-') || botToken.length === 0
  const isAppTokenValid = appToken.startsWith('xapp-') || appToken.length === 0

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Connect Slack Workspace"
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
            className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
            disabled={saving || !botToken.trim() || (mode === 'socket' && !appToken.trim())}
          >
            {saving ? 'Connecting...' : 'Connect Workspace'}
          </button>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Instructions */}
        <div className="p-4 bg-purple-500/10 border border-purple-500/30 rounded-lg">
          <h3 className="text-sm font-semibold text-purple-300 mb-2 flex items-center gap-2">
            <SlackIcon size={16} className="text-purple-400" /> How to set up a Slack App
          </h3>
          <ol className="text-xs text-gray-400 space-y-1 list-decimal list-inside">
            <li>Go to <code className="bg-gray-800 px-1 rounded">api.slack.com/apps</code> and create a new app</li>
            <li>Under <strong>OAuth & Permissions</strong>, add bot scopes: <code className="bg-gray-800 px-1 rounded">chat:write</code>, <code className="bg-gray-800 px-1 rounded">channels:read</code>, <code className="bg-gray-800 px-1 rounded">im:history</code></li>
            <li>Install the app to your workspace and copy the <strong>Bot Token</strong> (<code className="bg-gray-800 px-1 rounded">xoxb-...</code>)</li>
            <li>For Socket Mode: enable it under <strong>Socket Mode</strong> and generate an <strong>App Token</strong> (<code className="bg-gray-800 px-1 rounded">xapp-...</code>)</li>
          </ol>
        </div>

        {/* Connection Mode */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">Connection Mode</label>
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setMode('socket')}
              className={`p-3 rounded-lg border text-left transition-all ${
                mode === 'socket'
                  ? 'bg-purple-500/15 border-purple-500/50 text-purple-300'
                  : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:border-gray-600'
              }`}
            >
              <div className="text-sm font-medium">Socket Mode</div>
              <div className="text-xs mt-1 opacity-70">Recommended. No public URL needed.</div>
            </button>
            <button
              type="button"
              onClick={() => setMode('http')}
              className={`p-3 rounded-lg border text-left transition-all ${
                mode === 'http'
                  ? 'bg-purple-500/15 border-purple-500/50 text-purple-300'
                  : 'bg-gray-800/50 border-gray-700 text-gray-400 hover:border-gray-600'
              }`}
            >
              <div className="text-sm font-medium">HTTP Events</div>
              <div className="text-xs mt-1 opacity-70">Requires public endpoint URL.</div>
            </button>
          </div>
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
              placeholder="xoxb-your-bot-token"
              className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-purple-500"
            />
            <button
              type="button"
              onClick={() => setShowBotToken(!showBotToken)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
            >
              {showBotToken ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
            </button>
          </div>
          {botToken && !isBotTokenValid && (
            <p className="mt-1 text-xs text-amber-400 flex items-center gap-1">
              <AlertTriangleIcon size={12} /> Bot tokens typically start with <code className="bg-gray-800 px-1 rounded">xoxb-</code>
            </p>
          )}
          <p className="mt-1 text-xs text-gray-500">Found in OAuth & Permissions after installing to workspace</p>
        </div>

        {/* App Token (Socket Mode only) */}
        {mode === 'socket' && (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              App-Level Token <span className="text-red-400">*</span>
            </label>
            <div className="relative">
              <input
                type={showAppToken ? 'text' : 'password'}
                value={appToken}
                onChange={(e) => setAppToken(e.target.value)}
                placeholder="xapp-your-app-token"
                className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-purple-500"
              />
              <button
                type="button"
                onClick={() => setShowAppToken(!showAppToken)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
              >
                {showAppToken ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
              </button>
            </div>
            {appToken && !isAppTokenValid && (
              <p className="mt-1 text-xs text-amber-400 flex items-center gap-1">
                <AlertTriangleIcon size={12} /> App tokens typically start with <code className="bg-gray-800 px-1 rounded">xapp-</code>
              </p>
            )}
            <p className="mt-1 text-xs text-gray-500">Required for Socket Mode. Found under Basic Information &gt; App-Level Tokens.</p>
          </div>
        )}

        {/* Signing Secret (HTTP Mode only) */}
        {mode === 'http' && (
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Signing Secret
            </label>
            <div className="relative">
              <input
                type={showSigningSecret ? 'text' : 'password'}
                value={signingSecret}
                onChange={(e) => setSigningSecret(e.target.value)}
                placeholder="Your signing secret"
                className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-purple-500"
              />
              <button
                type="button"
                onClick={() => setShowSigningSecret(!showSigningSecret)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
              >
                {showSigningSecret ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
              </button>
            </div>
            <p className="mt-1 text-xs text-gray-500">Found under Basic Information. Used to verify incoming requests.</p>
          </div>
        )}

        {/* DM Policy */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">DM Policy</label>
          <select
            value={dmPolicy}
            onChange={(e) => setDmPolicy(e.target.value as 'open' | 'allowlist' | 'disabled')}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:ring-2 focus:ring-purple-500"
          >
            <option value="allowlist">Allowlist -- Only respond in allowed channels</option>
            <option value="open">Open -- Respond to all messages</option>
            <option value="disabled">Disabled -- Do not respond to DMs</option>
          </select>
          <p className="mt-1 text-xs text-gray-500">Controls how the bot handles direct messages</p>
        </div>

        {/* Security note */}
        <div className="p-3 bg-gray-800 rounded-lg border border-gray-700">
          <p className="text-xs text-gray-400">
            <strong className="text-gray-300">Security:</strong> All tokens are encrypted at rest. The bot token is used to authenticate with the Slack API, while the app token enables real-time event delivery via Socket Mode.
          </p>
        </div>
      </div>
    </Modal>
  )
}
