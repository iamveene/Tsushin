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

type CopyKind = 'secret' | 'url' | 'curl'

export default function WebhookSecretRevealModal({
  isOpen,
  onClose,
  secret,
  inboundUrl,
  apiBase,
  title,
  rotatedNotice = false,
}: Props) {
  const [copied, setCopied] = useState<CopyKind | null>(null)
  const [autoCopied, setAutoCopied] = useState(false)

  const fullInboundUrl = inboundUrl.startsWith('http') ? inboundUrl : `${apiBase}${inboundUrl}`
  const isLocalhostUrl = /^https:\/\/localhost(?::\d+)?\b/.test(fullInboundUrl)
  const curlFlag = isLocalhostUrl ? '-sk' : '-s'

  const apiBaseForPoll = apiBase || (typeof window !== 'undefined' ? window.location.origin : '')
  const testCommand = [
    `# Paste in a terminal with openssl + curl installed.`,
    `# Signs a test payload and POSTs it to the inbound URL. Prints the enqueue response`,
    `# (with queue_id) plus the agent's reply after a short delay.`,
    `SECRET='${secret}'`,
    `URL='${fullInboundUrl}'`,
    `TS=$(date +%s)`,
    `BODY='{"message":"Hello from Tsushin webhook test","sender_id":"curl-test","sender_name":"Curl"}'`,
    `SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | awk '{print $2}')`,
    ``,
    `# 1) Send the signed payload — returns {status:"queued",queue_id,poll_url}`,
    `RESP=$(curl ${curlFlag} -X POST "$URL" \\`,
    `  -H "X-Tsushin-Signature: sha256=$SIG" \\`,
    `  -H "X-Tsushin-Timestamp: $TS" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d "$BODY")`,
    `echo "$RESP"`,
    ``,
    `# 2) Poll the agent's reply. The poll endpoint is under the Public API v1 and`,
    `#    needs an API key with the \`agents.execute\` scope — create one in`,
    `#    Hub \u2192 API Keys, then uncomment:`,
    `# API_KEY='<paste-your-api-key>'`,
    `# QID=$(echo "$RESP" | python3 -c "import sys,json;print(json.load(sys.stdin)['queue_id'])")`,
    `# sleep 3 && curl ${curlFlag} -H "X-API-Key: $API_KEY" "${apiBaseForPoll}/api/v1/queue/$QID"`,
  ].join('\n')

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

  const copy = async (text: string, kind: CopyKind) => {
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

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block text-sm font-medium text-gray-300">
              Test it now (copy &amp; paste into your terminal)
            </label>
            <button
              type="button"
              onClick={() => copy(testCommand, 'curl')}
              className="flex items-center gap-1 px-2 py-1 text-xs bg-cyan-600/20 text-cyan-300 border border-cyan-600/50 rounded hover:bg-cyan-600/30"
              title="Copy test command"
            >
              {copied === 'curl' ? <CheckCircleIcon size={14} /> : <CopyIcon size={14} />}
              {copied === 'curl' ? 'Copied' : 'Copy command'}
            </button>
          </div>
          <pre
            data-testid="webhook-test-curl"
            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-gray-200 font-mono text-xs overflow-x-auto whitespace-pre"
          >
{testCommand}
          </pre>
          <p className="mt-2 text-xs text-gray-500">
            Needs <code className="text-gray-300">openssl</code> and <code className="text-gray-300">curl</code>. Step 1 returns
            <code className="bg-gray-900 px-1 mx-1 rounded text-cyan-300">{`{"status":"queued","queue_id":…,"poll_url":"/api/v1/queue/…"}`}</code>
            once the signature + timestamp are accepted. Step 2 retrieves the agent&apos;s reply once processing completes.
            Open <strong className="text-gray-300">{'Watcher \u2192 Graph View'}</strong> in another tab to watch the channel node glow while the agent processes.
            {isLocalhostUrl && (
              <> The snippet uses <code className="text-gray-300">-k</code> because <code className="text-gray-300">localhost</code> is served with a self-signed cert; drop it in production.</>
            )}
          </p>
        </div>

        <div className="p-3 bg-gray-800 rounded-lg border border-gray-700">
          <p className="text-xs text-gray-400 mb-2">
            <strong className="text-gray-300">Signing scheme:</strong>
            <code className="bg-gray-900 px-1 mx-1 rounded text-cyan-300">HMAC-SHA256(secret, timestamp + &quot;.&quot; + body)</code>
            sent as
            <code className="bg-gray-900 px-1 mx-1 rounded text-cyan-300">X-Tsushin-Signature: sha256=&lt;hex&gt;</code>
            with
            <code className="bg-gray-900 px-1 mx-1 rounded text-cyan-300">X-Tsushin-Timestamp: &lt;unix_seconds&gt;</code>
            (±5 min window).
          </p>
        </div>
      </div>
    </Modal>
  )
}
