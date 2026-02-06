'use client'

import { useState } from 'react'
import Modal from './ui/Modal'
import { EyeIcon, EyeOffIcon, AlertTriangleIcon } from '@/components/ui/icons'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSubmit: (token: string) => Promise<void>
  saving: boolean
}

export default function TelegramBotModal({ isOpen, onClose, onSubmit, saving }: Props) {
  const [token, setToken] = useState('')
  const [showToken, setShowToken] = useState(false)

  const handleSubmit = async () => {
    if (!token.trim()) return
    await onSubmit(token.trim())
    setToken('')
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create Telegram Bot"
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
            className="px-4 py-2 bg-teal-500 text-white rounded hover:bg-teal-600 disabled:opacity-50"
            disabled={saving || !token.trim()}
          >
            {saving ? 'Creating...' : 'Create Bot'}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        {/* Instructions */}
        <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
          <h3 className="text-sm font-semibold text-blue-300 mb-2">
            How to get a Bot Token
          </h3>
          <ol className="text-xs text-gray-400 space-y-1 list-decimal list-inside">
            <li>Open Telegram and search for <code className="bg-gray-800 px-1 rounded">@BotFather</code></li>
            <li>Send <code className="bg-gray-800 px-1 rounded">/newbot</code> and follow the prompts</li>
            <li>Copy the token (looks like: <code className="bg-gray-800 px-1 rounded text-xs">123456789:ABCdefGHI...</code>)</li>
            <li>Paste it below</li>
          </ol>
        </div>

        {/* Token Input */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Bot Token *
          </label>
          <div className="relative">
            <input
              type={showToken ? 'text' : 'password'}
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
              className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-teal-500"
            />
            <button
              type="button"
              onClick={() => setShowToken(!showToken)}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
            >
              {showToken ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-500">
            The token will be encrypted before storage
          </p>
        </div>

        {/* Validation hint */}
        {token && !token.includes(':') && (
          <p className="text-xs text-amber-400">
            <span className="inline-flex items-center gap-1"><AlertTriangleIcon size={12} /> Token should contain a colon (:) - make sure you copied the full token</span>
          </p>
        )}

        {/* Info box */}
        <div className="p-3 bg-gray-800 rounded-lg border border-gray-700">
          <p className="text-xs text-gray-400">
            <strong className="text-gray-300">Note:</strong> Unlike WhatsApp, Telegram bots don't require QR code authentication or Docker containers.
            Simply paste your bot token and start messaging!
          </p>
        </div>
      </div>
    </Modal>
  )
}
