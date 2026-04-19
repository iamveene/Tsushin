'use client'

import { useEffect, useState } from 'react'
import Modal from './ui/Modal'
import { AlertTriangleIcon, CopyIcon, CheckCircleIcon } from '@/components/ui/icons'

interface Props {
  isOpen: boolean
  onClose: () => void
  secret: string
  inboundUrl: string
  apiBase: string
  title?: string
  rotatedNotice?: boolean
}

export default function WebhookSecretRevealModal({
  isOpen,
  onClose,
  secret,
  inboundUrl,
  apiBase,
  title,
  rotatedNotice = false,
}: Props) {
  const [copied, setCopied] = useState<'secret' | 'url' | null>(null)
  const [autoCopied, setAutoCopied] = useState(false)

  const fullInboundUrl = inboundUrl.startsWith('http') ? inboundUrl : `${apiBase}${inboundUrl}`

  useEffect(() => {
    if (!isOpen || !secret || autoCopied) return
    navigator.clipboard.writeText(secret).then(
      () => setAutoCopied(true),
      () => setAutoCopied(false),
    )
  }, [isOpen, secret, autoCopied])

  useEffect(() => {
    if (!isOpen) setAutoCopied(false)
  }, [isOpen])

  const copy = async (text: string, kind: 'secret' | 'url') => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(kind)
      setTimeout(() => setCopied(null), 2000)
    } catch {
      // no-op
    }
  }

  const headingText =
    title ?? (rotatedNotice ? 'Secret Rotated — Save Your New Secret' : 'Webhook Created — Save Your Secret')

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={headingText}
      size="lg"
      footer={
        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-cyan-500 text-white rounded hover:bg-cyan-600"
          >
            I&apos;ve saved the secret
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="p-4 bg-amber-500/10 border border-amber-500/40 rounded-lg">
          <div className="flex items-start gap-2">
            <span className="text-amber-400 mt-0.5"><AlertTriangleIcon size={16} /></span>
            <div>
              <h3 className="text-sm font-semibold text-amber-300 mb-1">
                {rotatedNotice ? 'Previous secret is now invalid' : 'Save this secret now'}
              </h3>
              <p className="text-xs text-gray-400">
                This secret will <strong>never be shown again</strong>.{' '}
                {rotatedNotice
                  ? 'Update your external system before the next webhook request, or inbound calls will start failing with 403.'
                  : 'You can rotate it later, but you cannot view the existing secret. Store it in your external system\u2019s secrets manager.'}
              </p>
              {autoCopied && (
                <p className="text-xs text-green-400 mt-2">
                  Copied to clipboard automatically. Paste it into your secrets manager now.
                </p>
              )}
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
              value={secret}
              readOnly
              className="w-full px-3 py-2 pr-12 bg-gray-900 border border-cyan-500/40 rounded text-cyan-300 font-mono text-sm"
            />
            <button
              type="button"
              onClick={() => copy(secret, 'secret')}
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
              onClick={() => copy(fullInboundUrl, 'url')}
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
    </Modal>
  )
}
