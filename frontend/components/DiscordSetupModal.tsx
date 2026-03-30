'use client'

import { useState } from 'react'
import Modal from './ui/Modal'
import { EyeIcon, EyeOffIcon, AlertTriangleIcon, DiscordIcon } from '@/components/ui/icons'
import type { DiscordIntegrationCreate } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: DiscordIntegrationCreate) => Promise<void>
  saving: boolean
}

export default function DiscordSetupModal({ isOpen, onClose, onSubmit, saving }: Props) {
  const [botToken, setBotToken] = useState('')
  const [applicationId, setApplicationId] = useState('')
  const [dmPolicy, setDmPolicy] = useState<'open' | 'allowlist' | 'disabled'>('allowlist')
  const [showBotToken, setShowBotToken] = useState(false)

  const handleSubmit = async () => {
    if (!botToken.trim() || !applicationId.trim()) return
    const data: DiscordIntegrationCreate = {
      bot_token: botToken.trim(),
      application_id: applicationId.trim(),
      dm_policy: dmPolicy,
    }
    await onSubmit(data)
    // Reset form on success
    setBotToken('')
    setApplicationId('')
    setDmPolicy('allowlist')
  }

  const isApplicationIdValid = /^\d{17,20}$/.test(applicationId) || applicationId.length === 0

  // Generate OAuth2 invite URL for adding the bot to a server
  const inviteUrl = applicationId
    ? `https://discord.com/api/oauth2/authorize?client_id=${applicationId}&permissions=274877975552&scope=bot%20applications.commands`
    : ''

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
            disabled={saving || !botToken.trim() || !applicationId.trim()}
          >
            {saving ? 'Connecting...' : 'Connect Bot'}
          </button>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Instructions */}
        <div className="p-4 bg-indigo-500/10 border border-indigo-500/30 rounded-lg">
          <h3 className="text-sm font-semibold text-indigo-300 mb-2 flex items-center gap-2">
            <DiscordIcon size={16} className="text-indigo-400" /> How to set up a Discord Bot
          </h3>
          <ol className="text-xs text-gray-400 space-y-1 list-decimal list-inside">
            <li>Go to <code className="bg-gray-800 px-1 rounded">discord.com/developers/applications</code> and create a new application</li>
            <li>Copy the <strong>Application ID</strong> from the General Information page</li>
            <li>Under <strong>Bot</strong>, click &quot;Reset Token&quot; to generate a <strong>Bot Token</strong></li>
            <li>Enable <strong>Message Content Intent</strong> under Bot &gt; Privileged Gateway Intents</li>
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

        {/* DM Policy */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">DM Policy</label>
          <select
            value={dmPolicy}
            onChange={(e) => setDmPolicy(e.target.value as 'open' | 'allowlist' | 'disabled')}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:ring-2 focus:ring-indigo-500"
          >
            <option value="allowlist">Allowlist -- Only respond in allowed servers/channels</option>
            <option value="open">Open -- Respond to all messages</option>
            <option value="disabled">Disabled -- Do not respond to DMs</option>
          </select>
          <p className="mt-1 text-xs text-gray-500">Controls how the bot handles direct messages and server messages</p>
        </div>

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
            <strong className="text-gray-300">Security:</strong> The bot token is encrypted at rest. It is used to authenticate with the Discord API for sending and receiving messages. Never share your bot token publicly.
          </p>
        </div>
      </div>
    </Modal>
  )
}
