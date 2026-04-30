'use client'
/* eslint-disable react-hooks/set-state-in-effect, react/no-unescaped-entities */

/**
 * Discord Setup Wizard (v0.6.0 V060-CHN-002).
 *
 * Replaces the bare-form DiscordSetupModal with a guided 6-step wizard:
 *   1. Welcome + public-URL prereq (Discord requires a public HTTPS endpoint).
 *   2. Create the Discord application (with the exact Dev Portal clicks).
 *   3. Capture credentials (App ID + Public Key + Bot Token + intents +
 *      bot permissions on the Installation page).
 *   4. Paste credentials.
 *   5. Set the Interactions Endpoint URL on the Dev Portal — Tsushin shows
 *      the exact URL with a copy button.
 *   6. Invite the bot (Server install path + User Install fallback for
 *      accounts that lack Manage Server permission).
 *
 * Why the User Install fallback? In ~30% of personal Discord accounts the
 * "Add to Server" dropdown shows "No items to show" because the user has
 * Manage Server in zero guilds. User Install lets the bot work via slash
 * commands and DMs without needing a guild.
 */

import { useEffect, useState } from 'react'
import Wizard, { type WizardStep } from './ui/Wizard'
import {
  AlertTriangleIcon,
  CheckCircleIcon,
  DiscordIcon,
  EyeIcon,
  EyeOffIcon,
} from '@/components/ui/icons'
import { api, type DiscordIntegrationCreate, type PublicIngressSource } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSubmit: (data: DiscordIntegrationCreate) => Promise<void>
  saving: boolean
}

const PUBLIC_KEY_PATTERN = /^[a-fA-F0-9]{64}$/
const APP_ID_PATTERN = /^\d{17,20}$/

const PERMS_LIST = [
  'View Channels',
  'Send Messages',
  'Send Messages in Threads',
  'Read Message History',
  'Embed Links',
  'Attach Files',
  'Add Reactions',
  'Use Slash Commands',
]

const WIZARD_STEPS: WizardStep[] = [
  { id: 'welcome', label: 'Welcome', description: 'Public URL' },
  { id: 'create-app', label: 'Create App', description: 'Dev Portal' },
  { id: 'credentials', label: 'Get Credentials', description: 'Token + keys' },
  { id: 'paste-save', label: 'Paste & Save', description: 'Encrypted token' },
  { id: 'webhook-url', label: 'Webhook URL', description: 'Interactions' },
  { id: 'invite', label: 'Invite Bot', description: 'Install' },
]

function CopyableInline({ value, ariaLabel = 'value' }: { value: string; ariaLabel?: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="flex items-center gap-2">
      <code className="flex-1 px-2 py-1 bg-gray-900 text-indigo-300 text-xs font-mono rounded overflow-x-auto whitespace-nowrap">
        {value}
      </code>
      <button
        type="button"
        onClick={() => {
          navigator.clipboard?.writeText(value)
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        }}
        aria-label={`Copy ${ariaLabel}`}
        className="px-2 py-1 text-xs bg-indigo-600/30 text-indigo-200 border border-indigo-500/40 rounded hover:bg-indigo-600/50 flex-shrink-0"
      >
        {copied ? 'Copied!' : 'Copy'}
      </button>
    </div>
  )
}

export default function DiscordSetupWizard({ isOpen, onClose, onSubmit, saving }: Props) {
  const [step, setStep] = useState(1)
  const [appId, setAppId] = useState('')
  const [publicKey, setPublicKey] = useState('')
  const [botToken, setBotToken] = useState('')
  const [showBot, setShowBot] = useState(false)
  const [publicBaseUrl, setPublicBaseUrl] = useState<string | null>(null)
  const [ingressSource, setIngressSource] = useState<PublicIngressSource>('none')
  const [ingressWarning, setIngressWarning] = useState<string | null>(null)
  const [doneIntegrationId, setDoneIntegrationId] = useState<number | null>(null)

  useEffect(() => {
    if (isOpen) {
      setStep(1)
      setAppId('')
      setPublicKey('')
      setBotToken('')
      setDoneIntegrationId(null)
      // v0.6.1 — resolver replaces direct tenant.public_base_url read.
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

  const sourceLabel =
    ingressSource === 'tunnel' ? 'platform tunnel'
    : ingressSource === 'override' ? 'tenant override'
    : ingressSource === 'dev' ? 'dev environment'
    : null

  const isAppIdValid = APP_ID_PATTERN.test(appId)
  const isPublicKeyValid = PUBLIC_KEY_PATTERN.test(publicKey.trim())
  const canSubmit = !!botToken.trim() && isAppIdValid && isPublicKeyValid

  const handleSubmit = async () => {
    const data: DiscordIntegrationCreate = {
      bot_token: botToken.trim(),
      application_id: appId.trim(),
      public_key: publicKey.trim().toLowerCase(),
    }
    await onSubmit(data)
    try {
      const list = await api.getDiscordIntegrations()
      const last = list.sort((a, b) => b.id - a.id)[0]
      if (last) setDoneIntegrationId(last.id)
    } catch { /* non-fatal */ }
    setStep(5)
  }

  if (!isOpen) return null

  // ---- Steps ----------------------------------------------------------------

  const stepWelcome = (
    <div className="space-y-6">
      <div className="text-center">
        <div className="w-16 h-16 bg-indigo-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <DiscordIcon size={36} className="text-indigo-400" />
        </div>
        <h3 className="text-xl font-bold text-white mb-2">Connect Discord</h3>
        <p className="text-tsushin-slate max-w-md mx-auto">
          Tsushin uses Discord's HTTP Interactions endpoint — Discord POSTs each interaction to your backend, and Tsushin replies via the REST API. This works for both server bots and per-user app installs.
        </p>
      </div>

      {!publicBaseUrl ? (
        <div className="p-4 bg-amber-500/10 border border-amber-500/40 rounded-lg">
          <h4 className="text-sm font-semibold text-amber-200 mb-1 flex items-center gap-2">
            <AlertTriangleIcon size={14} /> Public HTTPS URL required
          </h4>
          <p className="text-xs text-amber-100/80">
            {ingressWarning ? (
              <>Tenant override is stored but invalid: {ingressWarning}. Fix it in Hub → Channels, or ask a global admin to enable Remote Access.</>
            ) : (
              <>Discord can't reach <code className="bg-amber-900/40 px-1 rounded">https://localhost</code>. Ask a global admin to enable <strong>Remote Access</strong> for this tenant, or set an <strong>Ingress Override</strong> in Hub → Channels.</>
            )}
          </p>
        </div>
      ) : (
        <div className="p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
          <p className="text-xs text-emerald-200 flex items-center gap-2">
            <CheckCircleIcon size={14} />
            Public URL: <code className="bg-emerald-900/40 px-1 rounded text-[10px]">{publicBaseUrl}</code>
            {sourceLabel && <span className="text-emerald-300/80">({sourceLabel})</span>}
          </p>
        </div>
      )}

      <div className="bg-tsushin-deep/50 rounded-xl p-5">
        <h4 className="text-sm font-semibold text-white mb-3">What you'll do:</h4>
        <ol className="text-xs text-tsushin-slate space-y-2 list-decimal list-inside">
          <li>Create a Discord application at <a href="https://discord.com/developers/applications" target="_blank" rel="noreferrer" className="text-indigo-300 underline">discord.com/developers/applications</a>.</li>
          <li>Copy three values: <strong>Application ID</strong>, <strong>Public Key</strong>, and <strong>Bot Token</strong>.</li>
          <li>Enable <strong>Message Content Intent</strong> and pick the bot permissions.</li>
          <li>Paste the Interactions URL Tsushin gives you back into Discord.</li>
          <li>Invite the bot — to a server you own, or to your user account.</li>
        </ol>
      </div>
    </div>
  )

  const stepCreateApp = (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-white mb-1">Create the Discord application</h3>
        <p className="text-sm text-tsushin-slate">~1 minute. Discord may ask you to solve a captcha.</p>
      </div>

      <ol className="space-y-3 text-sm text-tsushin-slate">
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
          <div>
            Open <a href="https://discord.com/developers/applications" target="_blank" rel="noreferrer" className="text-indigo-300 underline">discord.com/developers/applications</a> and click <strong>New Application</strong> (top right).
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
          <div>
            Name it (e.g. <em>My Tsushin Bot</em>), check the ToS box, click <strong>Create</strong>. Solve the captcha if shown.
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
          <div>
            You'll land on <strong>General Information</strong>. Keep this tab open — the next step copies values from here.
          </div>
        </li>
      </ol>
    </div>
  )

  const stepGetCreds = (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-white mb-1">Get credentials &amp; configure permissions</h3>
        <p className="text-sm text-tsushin-slate">3 values to copy + 2 portal toggles. We'll paste everything on the next page.</p>
      </div>

      <ol className="space-y-3 text-sm text-tsushin-slate">
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold flex-shrink-0">1</span>
          <div>
            From <strong>General Information</strong>, copy <strong>Application ID</strong> (17–20 digits) and <strong>Public Key</strong> (64 hex chars). The Public Key is how Tsushin verifies that requests really came from Discord (Ed25519 signature).
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold flex-shrink-0">2</span>
          <div>
            Click <strong>Bot</strong> in the left sidebar. Click <strong>Reset Token</strong> → <strong>Yes, do it!</strong> (Discord may ask for your account password to confirm). Copy the bot token. <strong>You'll only see it once</strong> — keep it safe.
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold flex-shrink-0">3</span>
          <div>
            Still on the <strong>Bot</strong> page: scroll to <strong>Privileged Gateway Intents</strong> and toggle ON <strong>Message Content Intent</strong>. Without this, the bot can't read message text.
          </div>
        </li>
        <li className="flex gap-3">
          <span className="w-6 h-6 rounded-full bg-indigo-500/20 text-indigo-300 flex items-center justify-center text-xs font-bold flex-shrink-0">4</span>
          <div>
            Click <strong>Installation</strong> in the left sidebar. Under <strong>Default Install Settings</strong> → <strong>Guild Install</strong>:
            <ul className="mt-1 ml-2 text-xs space-y-0.5 list-disc list-inside">
              <li>In <strong>Scopes</strong>, add <code className="bg-gray-800 px-1 rounded">bot</code> next to the existing <code className="bg-gray-800 px-1 rounded">applications.commands</code>.</li>
              <li>In <strong>Permissions</strong>, add: {PERMS_LIST.map((p, i) => (
                <span key={p}>
                  <code className="bg-gray-800 px-1 rounded">{p}</code>{i < PERMS_LIST.length - 1 ? ', ' : ''}
                </span>
              ))}.</li>
            </ul>
            Click <strong>Save Changes</strong>.
          </div>
        </li>
      </ol>

      <div className="bg-indigo-500/10 border border-indigo-500/30 rounded-lg p-3">
        <p className="text-xs text-indigo-200">
          <strong>Why these permissions?</strong> The bot needs to see channels (<code className="bg-gray-800 px-1 rounded">View Channels</code>), reply (<code className="bg-gray-800 px-1 rounded">Send Messages</code>, <code className="bg-gray-800 px-1 rounded">Send Messages in Threads</code>), read context (<code className="bg-gray-800 px-1 rounded">Read Message History</code>), render rich content (<code className="bg-gray-800 px-1 rounded">Embed Links</code>, <code className="bg-gray-800 px-1 rounded">Attach Files</code>, <code className="bg-gray-800 px-1 rounded">Add Reactions</code>), and respond to slash commands (<code className="bg-gray-800 px-1 rounded">Use Slash Commands</code>).
        </p>
      </div>
    </div>
  )

  const stepPaste = (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-white mb-1">Paste credentials</h3>
        <p className="text-sm text-tsushin-slate">Bot token is encrypted with a per-tenant key. The public key is stored as-is (it's public).</p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Application ID <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={appId}
          onChange={(e) => setAppId(e.target.value)}
          placeholder="123456789012345678"
          className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-indigo-500"
        />
        {appId && !isAppIdValid && <p className="mt-1 text-xs text-amber-300">Must be 17–20 digits.</p>}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Public Key <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={publicKey}
          onChange={(e) => setPublicKey(e.target.value)}
          placeholder="64-character hex Ed25519 key"
          className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono text-xs focus:ring-2 focus:ring-indigo-500"
        />
        {publicKey && !isPublicKeyValid && <p className="mt-1 text-xs text-amber-300">Must be exactly 64 hex characters.</p>}
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
            placeholder="MTIzND…"
            className="w-full px-3 py-2 pr-10 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm focus:ring-2 focus:ring-indigo-500"
          />
          <button type="button" onClick={() => setShowBot(!showBot)} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white">
            {showBot ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
          </button>
        </div>
      </div>
    </div>
  )

  const interactionsUrl = publicBaseUrl && doneIntegrationId
    ? `${publicBaseUrl}/api/channels/discord/${doneIntegrationId}/interactions`
    : null

  const stepWebhook = (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-white mb-1">Set the Interactions Endpoint URL</h3>
        <p className="text-sm text-tsushin-slate">Discord will POST every interaction to this URL. Discord requires it to be public HTTPS — it sends a verification PING which Tsushin replies to automatically using the public key you just saved.</p>
      </div>

      {interactionsUrl ? (
        <div className="p-4 bg-indigo-500/10 border border-indigo-500/40 rounded-lg space-y-3">
          <h4 className="text-sm font-semibold text-indigo-200">Your Interactions Endpoint URL</h4>
          <CopyableInline value={interactionsUrl} ariaLabel="interactions URL" />
          <ol className="text-xs text-indigo-100/90 space-y-1 list-decimal list-inside">
            <li>Go to your Discord app's <strong>General Information</strong> page.</li>
            <li>Scroll to <strong>Interactions Endpoint URL</strong> and paste the URL above.</li>
            <li>Click <strong>Save Changes</strong>. Discord verifies the URL — if you see "All your edits have been carefully recorded" the PING-PONG worked.</li>
          </ol>
        </div>
      ) : (
        <div className="p-3 bg-amber-500/10 border border-amber-500/40 rounded-lg">
          <p className="text-xs text-amber-200">
            URL preview unavailable — set your <strong>Public Base URL</strong> in Hub → Channels and recreate the integration.
          </p>
        </div>
      )}
    </div>
  )

  const inviteUrl = appId
    ? `https://discord.com/oauth2/authorize?client_id=${appId}`
    : ''
  const userInstallUrl = appId
    ? `https://discord.com/oauth2/authorize?client_id=${appId}&integration_type=1&scope=applications.commands`
    : ''

  const stepInvite = (
    <div className="space-y-5">
      <div className="text-center">
        <div className="w-16 h-16 bg-green-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
          <CheckCircleIcon size={36} className="text-green-400" />
        </div>
        <h3 className="text-xl font-bold text-white mb-1">Invite the bot &amp; finish up</h3>
        <p className="text-tsushin-slate max-w-md mx-auto">Pick the option that matches your Discord access.</p>
      </div>

      <div className="space-y-3">
        <a
          href={inviteUrl}
          target="_blank"
          rel="noreferrer"
          className="block p-4 bg-indigo-500/10 border border-indigo-500/30 hover:border-indigo-400 rounded-lg transition-colors"
        >
          <div className="text-sm font-semibold text-indigo-200 mb-1">Add to a server (recommended)</div>
          <div className="text-xs text-indigo-100/80">You'll pick a server you own. Requires <strong>Manage Server</strong> permission. The pre-saved permissions are applied automatically.</div>
        </a>

        <a
          href={userInstallUrl}
          target="_blank"
          rel="noreferrer"
          className="block p-4 bg-purple-500/10 border border-purple-500/30 hover:border-purple-400 rounded-lg transition-colors"
        >
          <div className="text-sm font-semibold text-purple-200 mb-1">Add to my account (fallback)</div>
          <div className="text-xs text-purple-100/80">No server needed. The bot installs to your Discord account and is invokable via slash commands and DMs anywhere. Use this if your account isn't an admin in any server.</div>
        </a>
      </div>

      <div className="bg-tsushin-deep/50 rounded-xl p-5">
        <h4 className="text-sm font-semibold text-white mb-3">Last step:</h4>
        <ol className="text-sm text-tsushin-slate space-y-2 list-decimal list-inside">
          <li>Go to <strong>Agents → {`{your agent}`} → Channels</strong>, enable <strong>Discord</strong>, and pick this bot.</li>
          <li>DM the bot or invoke a slash command — it will reply via your assigned agent.</li>
        </ol>
      </div>
    </div>
  )

  const renderStep = () => {
    switch (step) {
      case 1: return stepWelcome
      case 2: return stepCreateApp
      case 3: return stepGetCreds
      case 4: return stepPaste
      case 5: return stepWebhook
      case 6: return stepInvite
      default: return null
    }
  }

  const footer = (
    <div className="flex items-center justify-between gap-3 w-full">
      {step > 1 && step < 6 ? (
        <button type="button" onClick={() => setStep(step - 1)} className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors rounded-lg">
          ← Back
        </button>
      ) : <div />}

      {step === 4 ? (
        <button
          type="button"
          onClick={handleSubmit}
          disabled={saving || !canSubmit}
          className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? 'Connecting…' : 'Save & Continue'}
        </button>
      ) : step === 5 ? (
        <button type="button" onClick={() => setStep(6)} className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700">
          Done with Discord portal →
        </button>
      ) : step === 6 ? (
        <button type="button" onClick={onClose} className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700">
          Done
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setStep(step + 1)}
          className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700"
        >
          {step === 1 ? "Let's go →" : 'Next →'}
        </button>
      )}
    </div>
  )

  return (
    <Wizard
      isOpen={isOpen}
      onClose={onClose}
      title="Discord Setup"
      steps={WIZARD_STEPS}
      currentStep={step}
      size="xl"
      footer={footer}
      showProgress
      tone="discord"
    >
      {renderStep()}
    </Wizard>
  )
}
