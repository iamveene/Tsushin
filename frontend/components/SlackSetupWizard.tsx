'use client'

/**
 * Slack Setup Wizard (v0.6.0 V060-CHN-002).
 *
 * Replaces the bare-form SlackSetupModal with a guided 5-step wizard that
 * walks the user through:
 *   1. Welcome + mode choice (Socket Mode vs HTTP Events)
 *   2. Create Slack app (with the exact manifest JSON to paste — covers all
 *      required scopes + Socket Mode toggle in one step)
 *   3. Get the right tokens (Bot Token, plus App-Level Token for Socket Mode
 *      or App ID + Signing Secret for HTTP mode)
 *   4. Paste credentials + DM policy
 *   5. Done — what to do next (invite the bot, assign an agent)
 *
 * Visual style matches the existing WhatsApp setup wizard (numbered step
 * pills, progress bar, Back/Next/Skip controls).
 */

import { useEffect, useMemo, useState } from 'react'
import Modal from './ui/Modal'
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  EyeIcon,
  EyeOffIcon,
  SlackIcon,
} from '@/components/ui/icons'
import { api, type SlackIntegrationCreate, type PublicIngressSource } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: SlackIntegrationCreate) => Promise<void>
  saving: boolean
}

type Mode = 'socket' | 'http'

const MANIFEST_JSON = JSON.stringify(
  {
    display_information: {
      name: 'Tsushin Bot',
      description: 'Tsushin agent bridge',
      background_color: '#0F172A',
    },
    features: {
      bot_user: { display_name: 'Tsushin Bot', always_online: true },
    },
    oauth_config: {
      scopes: {
        bot: [
          'app_mentions:read',
          'channels:history',
          'channels:read',
          'chat:write',
          'files:write',
          'groups:history',
          'im:history',
          'im:read',
          'im:write',
          'mpim:history',
          'users:read',
        ],
      },
    },
    settings: {
      event_subscriptions: {
        bot_events: [
          'app_mention',
          'message.channels',
          'message.groups',
          'message.im',
          'message.mpim',
        ],
      },
      interactivity: { is_enabled: false },
      org_deploy_enabled: false,
      socket_mode_enabled: true,
      token_rotation_enabled: false,
    },
  },
  null,
  2,
)

function CopyableBlock({ value, label }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="relative">
      <pre className="bg-gray-900 text-purple-200 text-xs font-mono rounded-lg p-3 overflow-x-auto max-h-48 border border-gray-700">
        {value}
      </pre>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard?.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
        className="absolute top-2 right-2 px-2 py-1 text-xs bg-purple-600/30 text-purple-200 border border-purple-500/40 rounded hover:bg-purple-600/50"
      >
        {copied ? 'Copied!' : `Copy${label ? ' ' + label : ''}`}
      </button>
    </div>
  )
}

function StepPill({ idx, current, completed }: { idx: number; current: number; completed: boolean }) {
  return (
    <div
      className={`w-2 h-2 rounded-full transition-colors ${
        idx === current
          ? 'bg-purple-500'
          : completed
          ? 'bg-green-500'
          : idx < current
          ? 'bg-tsushin-slate/60'
          : 'bg-tsushin-slate/20'
      }`}
    />
  )
}

export default function SlackSetupWizard({ isOpen, onClose, onSubmit, saving }: Props) {
  const [step, setStep] = useState(1)
  const [mode, setMode] = useState<Mode>('socket')
  const [botToken, setBotToken] = useState('')
  const [appLevelToken, setAppLevelToken] = useState('')
  const [signingSecret, setSigningSecret] = useState('')
  const [appId, setAppId] = useState('')
  const [dmPolicy, setDmPolicy] = useState<'open' | 'allowlist' | 'disabled'>('allowlist')
  const [showBot, setShowBot] = useState(false)
  const [showApp, setShowApp] = useState(false)
  const [showSec, setShowSec] = useState(false)
  const [publicBaseUrl, setPublicBaseUrl] = useState<string | null>(null)
  const [ingressSource, setIngressSource] = useState<PublicIngressSource>('none')
  const [ingressWarning, setIngressWarning] = useState<string | null>(null)
  const [doneIntegrationId, setDoneIntegrationId] = useState<number | null>(null)

  // Reset when reopened
  useEffect(() => {
    if (isOpen) {
      setStep(1)
      setMode('socket')
      setBotToken('')
      setAppLevelToken('')
      setSigningSecret('')
      setAppId('')
      setDmPolicy('allowlist')
      setDoneIntegrationId(null)
      // v0.6.1 — resolver replaces direct tenant.public_base_url read so the
      // wizard shows the platform tunnel URL when no tenant override is set.
      api.getMyPublicIngress()
        .then(info => {
          setPublicBaseUrl(info.url)
          setIngressSource(info.source)
          setIngressWarning(info.warning)
        })
        .catch(() => {
          setPublicBaseUrl(null)
          setIngressSource('none')
          setIngressWarning(null)
        })
    }
  }, [isOpen])

  const sourceBadge =
    ingressSource === 'tunnel' ? 'via platform tunnel'
    : ingressSource === 'override' ? 'tenant override'
    : ingressSource === 'dev' ? 'dev environment'
    : null

  const totalSteps = 5
  const stepTitles = useMemo(
    () => ['Welcome', 'Create App', 'Get Tokens', 'Paste & Save', 'All Done'],
    [],
  )

  const isBotTokenValid = botToken.startsWith('xoxb-')
  const isAppTokenValid = appLevelToken.startsWith('xapp-')
  const httpReady = mode !== 'http' || (appId.trim() && signingSecret.trim() && publicBaseUrl)
  const socketReady = mode !== 'socket' || isAppTokenValid
  const canSubmit = isBotTokenValid && socketReady && httpReady

  const handleSubmit = async () => {
    const data: SlackIntegrationCreate = {
      bot_token: botToken.trim(),
      mode,
      dm_policy: dmPolicy,
    }
    if (mode === 'socket') data.app_level_token = appLevelToken.trim()
    if (mode === 'http') {
      data.signing_secret = signingSecret.trim()
      data.app_id = appId.trim()
    }
    await onSubmit(data)
    // Best-effort: re-load list to pick up the just-created integration's id
    try {
      const list = await api.getSlackIntegrations()
      const last = list.sort((a, b) => b.id - a.id)[0]
      if (last) setDoneIntegrationId(last.id)
    } catch { /* non-fatal */ }
    setStep(5)
  }

  if (!isOpen) return null

  // ---- Step bodies ----------------------------------------------------------

  const stepWelcome = (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 bg-purple-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <SlackIcon size={36} className="text-purple-400" />
        </div>
        <h3 className="text-xl font-bold text-white mb-2">Connect Slack</h3>
        <p className="text-tsushin-slate max-w-md mx-auto">
          We'll walk you through every click on Slack's side, then collect just the tokens we need. Pick how you want Slack to deliver messages to Tsushin.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={() => setMode('socket')}
          className={`p-4 rounded-lg border text-left transition-all ${
            mode === 'socket'
              ? 'bg-purple-500/15 border-purple-500/50 text-purple-200'
              : 'bg-gray-800/50 border-gray-700 text-gray-300 hover:border-gray-600'
          }`}
        >
          <div className="text-sm font-semibold mb-1">Socket Mode</div>
          <div className="text-xs opacity-80 mb-2">Recommended</div>
          <ul className="text-xs space-y-1 opacity-90">
            <li>• No public URL needed — Tsushin dials out</li>
            <li>• Works for local dev and production</li>
            <li>• Needs an extra App-Level Token (xapp-)</li>
          </ul>
        </button>
        <button
          type="button"
          onClick={() => setMode('http')}
          className={`p-4 rounded-lg border text-left transition-all ${
            mode === 'http'
              ? 'bg-purple-500/15 border-purple-500/50 text-purple-200'
              : 'bg-gray-800/50 border-gray-700 text-gray-300 hover:border-gray-600'
          }`}
        >
          <div className="text-sm font-semibold mb-1">HTTP Events</div>
          <div className="text-xs opacity-80 mb-2">For tightly scoped firewalls</div>
          <ul className="text-xs space-y-1 opacity-90">
            <li>• Slack POSTs events to your backend</li>
            <li>• Requires a publicly-reachable HTTPS URL</li>
            <li>• Needs Signing Secret + App ID</li>
          </ul>
        </button>
      </div>

      {mode === 'http' && !publicBaseUrl && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/40 rounded-lg">
          <p className="text-xs text-amber-200 flex items-start gap-2">
            <AlertTriangleIcon size={14} className="mt-0.5 flex-shrink-0" />
            <span>
              {ingressWarning ? (
                <>Tenant override is set but invalid: {ingressWarning}. Fix it in Hub → Communication, or ask your admin to enable Remote Access.</>
              ) : (
                <>No public ingress configured. Ask a global admin to enable Remote Access for this tenant, or set an <strong>Ingress Override</strong> in Hub → Communication.</>
              )}
            </span>
          </p>
        </div>
      )}
      {mode === 'http' && publicBaseUrl && sourceBadge && (
        <div className="p-2 bg-emerald-500/10 border border-emerald-500/30 rounded text-xs text-emerald-200">
          Using <code className="bg-emerald-900/40 px-1 rounded">{publicBaseUrl}</code> ({sourceBadge})
        </div>
      )}

      <div className="bg-tsushin-deep/50 rounded-xl p-5">
        <h4 className="text-sm font-semibold text-white mb-3">What you'll need:</h4>
        <ol className="text-xs text-tsushin-slate space-y-2 list-decimal list-inside">
          <li>A Slack workspace where you can install apps (you must be an admin or workspace owner).</li>
          <li>About 3 minutes to copy two tokens from <a href="https://api.slack.com/apps" target="_blank" rel="noreferrer" className="text-purple-300 underline">api.slack.com/apps</a>.</li>
          <li>{mode === 'socket' ? 'No public URL — Socket Mode dials out from Tsushin.' : 'A public HTTPS URL pointing at your Tsushin backend (port 8081).'}</li>
        </ol>
      </div>
    </div>
  )

  const stepCreateApp = (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-white mb-1">Create the Slack app</h3>
        <p className="text-sm text-tsushin-slate">
          The fastest path is "From a manifest" — pasting the JSON below sets all required scopes, bot events, and the Socket Mode toggle in one shot.
        </p>
      </div>

      <ol className="space-y-3 text-sm text-tsushin-slate">
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
          <div>
            Open <a href="https://api.slack.com/apps?new_app=1" target="_blank" rel="noreferrer" className="text-purple-300 underline">api.slack.com/apps</a> and click <strong>Create New App</strong>.
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
          <div>
            Choose <strong>From a manifest</strong>, pick your workspace, click <strong>Next</strong>.
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
          <div>
            Switch to the <strong>JSON</strong> tab and replace the contents with this:
            <div className="mt-2"><CopyableBlock value={MANIFEST_JSON} label="manifest" /></div>
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">4</span>
          <div>
            Click <strong>Next</strong> → <strong>Create</strong>. You should land on the app's settings page.
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">5</span>
          <div>
            From the left sidebar open <strong>Install App</strong> → <strong>Install to {`{your workspace}`}</strong> → <strong>Allow</strong>. Slack returns a Bot Token starting with <code className="bg-gray-800 px-1 rounded text-purple-300">xoxb-</code>. Keep this tab open.
          </div>
        </li>
      </ol>

      <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg p-3">
        <p className="text-xs text-purple-200">
          <strong>Why these scopes?</strong> <code className="bg-gray-800 px-1 rounded">chat:write</code> lets the bot reply, <code className="bg-gray-800 px-1 rounded">channels:history</code>/<code className="bg-gray-800 px-1 rounded">im:history</code> let it read context, <code className="bg-gray-800 px-1 rounded">app_mentions:read</code> wakes it on @mention, <code className="bg-gray-800 px-1 rounded">files:write</code> handles attachments, <code className="bg-gray-800 px-1 rounded">users:read</code> resolves usernames. The bot events tell Slack which message types to forward.
        </p>
      </div>
    </div>
  )

  const stepGetTokens = (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-white mb-1">Get the tokens</h3>
        <p className="text-sm text-tsushin-slate">
          {mode === 'socket'
            ? "Socket Mode needs two tokens: the Bot Token (already in your clipboard from the previous step) and an App-Level Token."
            : 'HTTP mode needs the Bot Token plus the Signing Secret and App ID Slack uses to verify and identify requests.'}
        </p>
      </div>

      {mode === 'socket' ? (
        <ol className="space-y-3 text-sm text-tsushin-slate">
          <li className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
            <div>
              Bot Token: from the install step you should already have <code className="bg-gray-800 px-1 rounded text-purple-300">xoxb-...</code>. If not, open <strong>OAuth &amp; Permissions</strong> → copy <strong>Bot User OAuth Token</strong>.
            </div>
          </li>
          <li className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
            <div>
              App-Level Token: open <strong>Basic Information</strong> → scroll to <strong>App-Level Tokens</strong> → click <strong>Generate Token and Scopes</strong>.
            </div>
          </li>
          <li className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
            <div>
              Name it <code className="bg-gray-800 px-1 rounded">tsushin-socket</code>, click <strong>Add Scope</strong> → pick <code className="bg-gray-800 px-1 rounded">connections:write</code>, then <strong>Generate</strong>. Copy the token starting with <code className="bg-gray-800 px-1 rounded text-purple-300">xapp-</code>.
            </div>
          </li>
        </ol>
      ) : (
        <ol className="space-y-3 text-sm text-tsushin-slate">
          <li className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
            <div>
              Bot Token: from <strong>OAuth &amp; Permissions</strong> copy <strong>Bot User OAuth Token</strong> (<code className="bg-gray-800 px-1 rounded">xoxb-...</code>).
            </div>
          </li>
          <li className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
            <div>
              From <strong>Basic Information</strong>: copy <strong>App ID</strong> (looks like <code className="bg-gray-800 px-1 rounded">A0XXXXXXX</code>) and <strong>Signing Secret</strong>.
            </div>
          </li>
          <li className="flex gap-3">
            <span className="w-6 h-6 rounded-full bg-purple-500/20 text-purple-300 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
            <div>
              You'll set the Slack <strong>Event Subscriptions Request URL</strong> after Tsushin creates the integration — we'll show you the exact URL on the next page.
            </div>
          </li>
        </ol>
      )}
    </div>
  )

  const sampleEventsUrl = publicBaseUrl
    ? `${publicBaseUrl}/api/channels/slack/<id>/events`
    : null

  const stepPasteSave = (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-white mb-1">Paste &amp; save</h3>
        <p className="text-sm text-tsushin-slate">All tokens are encrypted at rest with a per-tenant key.</p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Bot Token <span className="text-red-400">*</span>
        </label>
        <div className="relative">
          <input
            type={showBot ? 'text' : 'password'}
            value={botToken}
            onChange={(e) => setBotToken(e.target.value)}
            placeholder="xoxb-…"
            className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-purple-500"
          />
          <button type="button" onClick={() => setShowBot(!showBot)} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white">
            {showBot ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
          </button>
        </div>
        {botToken && !isBotTokenValid && (
          <p className="mt-1 text-xs text-amber-300">Bot tokens start with <code className="bg-gray-800 px-1 rounded">xoxb-</code>.</p>
        )}
      </div>

      {mode === 'socket' && (
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            App-Level Token <span className="text-red-400">*</span>
          </label>
          <div className="relative">
            <input
              type={showApp ? 'text' : 'password'}
              value={appLevelToken}
              onChange={(e) => setAppLevelToken(e.target.value)}
              placeholder="xapp-…"
              className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-purple-500"
            />
            <button type="button" onClick={() => setShowApp(!showApp)} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white">
              {showApp ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
            </button>
          </div>
          {appLevelToken && !isAppTokenValid && (
            <p className="mt-1 text-xs text-amber-300">App-Level tokens start with <code className="bg-gray-800 px-1 rounded">xapp-</code>.</p>
          )}
        </div>
      )}

      {mode === 'http' && (
        <>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">App ID <span className="text-red-400">*</span></label>
            <input
              type="text"
              value={appId}
              onChange={(e) => setAppId(e.target.value)}
              placeholder="A0XXXXXXX"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-purple-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Signing Secret <span className="text-red-400">*</span></label>
            <div className="relative">
              <input
                type={showSec ? 'text' : 'password'}
                value={signingSecret}
                onChange={(e) => setSigningSecret(e.target.value)}
                className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-purple-500"
              />
              <button type="button" onClick={() => setShowSec(!showSec)} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white">
                {showSec ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
              </button>
            </div>
          </div>
          {sampleEventsUrl && (
            <div className="p-3 bg-gray-800/60 border border-gray-700 rounded-lg">
              <h4 className="text-xs font-semibold text-gray-200 mb-1">Events Request URL preview</h4>
              <code className="block px-2 py-1 bg-gray-900 text-purple-200 text-xs font-mono rounded overflow-x-auto">{sampleEventsUrl}</code>
              <p className="mt-1 text-xs text-gray-400">After Save, paste this URL (with the real ID) into Slack → Event Subscriptions → Request URL.</p>
            </div>
          )}
        </>
      )}

      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">DM Policy</label>
        <select
          value={dmPolicy}
          onChange={(e) => setDmPolicy(e.target.value as 'open' | 'allowlist' | 'disabled')}
          className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white text-sm focus:ring-2 focus:ring-purple-500"
        >
          <option value="allowlist">Allowlist — only respond in allowed channels</option>
          <option value="open">Open — respond to all messages</option>
          <option value="disabled">Disabled — ignore DMs</option>
        </select>
      </div>
    </div>
  )

  const stepDone = (
    <div className="space-y-5">
      <div className="text-center">
        <div className="w-16 h-16 bg-green-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <CheckCircleIcon size={36} className="text-green-400" />
        </div>
        <h3 className="text-xl font-bold text-white mb-1">Slack workspace connected!</h3>
        <p className="text-tsushin-slate max-w-md mx-auto">A few last things to make the bot actually reply.</p>
      </div>

      {mode === 'http' && publicBaseUrl && doneIntegrationId && (
        <div className="p-4 bg-amber-500/10 border border-amber-500/40 rounded-lg">
          <h4 className="text-sm font-semibold text-amber-200 mb-2">Paste this Request URL into Slack</h4>
          <CopyableBlock value={`${publicBaseUrl}/api/channels/slack/${doneIntegrationId}/events`} label="URL" />
          <p className="text-xs text-amber-100/80 mt-2">
            In your Slack app → <strong>Event Subscriptions</strong> → toggle ON → paste into <strong>Request URL</strong>. Slack will verify it.
          </p>
        </div>
      )}

      <div className="bg-tsushin-deep/50 rounded-xl p-5">
        <h4 className="text-sm font-semibold text-white mb-3">Next steps:</h4>
        <ol className="text-sm text-tsushin-slate space-y-2 list-decimal list-inside">
          <li>Open the channel where you want the bot. Type <code className="bg-gray-800 px-1 rounded text-purple-300">/invite @{`{your-bot-name}`}</code> and confirm.</li>
          <li>Go to <strong>Agents → {`{your agent}`} → Channels</strong>, enable <strong>Slack</strong>, and pick this workspace.</li>
          <li>Send a message in the channel — the bot will reply (and thread if it was a channel mention).</li>
        </ol>
      </div>
    </div>
  )

  const renderStep = () => {
    switch (step) {
      case 1: return stepWelcome
      case 2: return stepCreateApp
      case 3: return stepGetTokens
      case 4: return stepPasteSave
      case 5: return stepDone
      default: return null
    }
  }

  // Footer logic
  const footer = (
    <div className="flex items-center justify-between w-full">
      {step > 1 && step < 5 ? (
        <button onClick={() => setStep(step - 1)} className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors rounded-lg">
          ← Back
        </button>
      ) : <div />}

      <div className="flex items-center gap-2">
        {stepTitles.map((_, idx) => (
          <StepPill key={idx} idx={idx + 1} current={step} completed={idx + 1 < step} />
        ))}
      </div>

      {step === 4 ? (
        <button
          onClick={handleSubmit}
          disabled={saving || !canSubmit}
          className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
        >
          {saving ? 'Connecting…' : 'Save & Continue'}
        </button>
      ) : step === 5 ? (
        <button onClick={onClose} className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700">
          Done
        </button>
      ) : (
        <button
          onClick={() => setStep(step + 1)}
          className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700"
        >
          {step === 1 ? "Let's go →" : 'Next →'}
        </button>
      )}
    </div>
  )

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`Slack Setup — ${stepTitles[step - 1]}`}
      size="xl"
      footer={footer}
    >
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-tsushin-slate">Step {step} of {totalSteps}</span>
          <span className="text-xs text-tsushin-slate">{Math.round((step / totalSteps) * 100)}%</span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-1">
          <div
            className="bg-gradient-to-r from-purple-500 to-pink-500 h-1 rounded-full transition-all"
            style={{ width: `${(step / totalSteps) * 100}%` }}
          />
        </div>
      </div>
      {renderStep()}
    </Modal>
  )
}
