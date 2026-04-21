'use client'

/**
 * AddIntegrationWizard — generic integration setup wizard for the Hub.
 *
 * Replaces the old SearchIntegrationWizard which was locked to the three
 * web-search providers only. This wizard is category-aware:
 *
 *   web_search → Brave / SerpAPI / Tavily (pending) / SearXNG (auto-provisioned)
 *   travel     → Amadeus / Google Flights (SerpAPI key)
 *
 * The SearXNG branch calls the new /api/hub/searxng/instances endpoint which
 * spins up a per-tenant container on tsushin-network (mirrors the Kokoro/Ollama
 * auto-provisioning pattern — no shipped compose service, no secrets in repo).
 *
 * Cosmetically mirrors AgentWizard's stepper + card styling.
 */

import { useState, useEffect } from 'react'
import Modal from '@/components/ui/Modal'
import { api, authenticatedFetch, Agent, SearchProviderInfo, TravelProviderInfo, SearxngInstance } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onComplete?: () => void
  // Allow the Hub to pre-select a category/provider so the per-card
  // "Configure" button can drop the user right at step 3.
  initialCategory?: CategoryId
  initialProviderId?: ProviderId
}

type Step = 1 | 2 | 3 | 4 | 5

type CategoryId = 'web_search' | 'travel'
// Provider ids MUST match the backend registry keys (SearchProviderRegistry /
// FlightProviderRegistry) — the drift test enforces that. 'google' here is
// the SerpAPI-powered Google search provider (skillProvider is also 'google');
// 'google_flights' is a separate travel provider.
type ProviderId = 'brave' | 'tavily' | 'google' | 'searxng' | 'amadeus' | 'google_flights'

interface ProviderMeta {
  id: ProviderId
  label: string
  category: CategoryId
  description: string
  skillType: 'web_search' | 'travel'
  // How to commit credentials in step 3. Values map to the back-end routes.
  credentialMode: 'api_key' | 'searxng_autoprovision' | 'amadeus'
  skillProvider?: string  // what we set in AgentSkill.config.provider (web_search)
  apiKeyService?: string  // service name for /api/api-keys (api_key mode)
  keyUrl?: string
  disabled?: boolean
  disabledReason?: string
}

// -----------------------------------------------------------------------------
// FALLBACK PROVIDER CATALOG.
//
// This array is the STATIC FALLBACK rendered only when the live catalog fetch
// to /api/hub/search-providers + /api/hub/travel-providers fails (e.g., backend
// down, offline install, first-run boot). The source of truth at runtime is
// the backend registries (SearchProviderRegistry + FlightProviderRegistry).
//
// Keep credential-workflow fields (credentialMode / skillProvider /
// apiKeyService / keyUrl) here — they are UI metadata and do NOT live on the
// backend registries. Live backend rows are merged with entries here (matched
// by `id`) at render time.
//
// backend/tests/test_wizard_drift.py asserts every backend-registered provider
// id has a matching row here, so adding a provider to the backend without
// updating this fallback will fail CI.
// -----------------------------------------------------------------------------
const FALLBACK_PROVIDERS: ProviderMeta[] = [
  // --- Web Search ---
  {
    id: 'brave',
    label: 'Brave Search (recommended)',
    category: 'web_search',
    description: 'Privacy-first, generous free tier, no PII in queries.',
    skillType: 'web_search',
    credentialMode: 'api_key',
    skillProvider: 'brave',
    apiKeyService: 'brave_search',
    keyUrl: 'https://brave.com/search/api/',
  },
  {
    id: 'searxng',
    label: 'SearXNG (self-hosted)',
    category: 'web_search',
    description: 'Auto-provisioned per-tenant metasearch container. No API key needed.',
    skillType: 'web_search',
    credentialMode: 'searxng_autoprovision',
    skillProvider: 'searxng',
  },
  {
    id: 'google',
    label: 'SerpAPI (Google)',
    category: 'web_search',
    description: 'Live Google SERP; paid after free quota.',
    skillType: 'web_search',
    credentialMode: 'api_key',
    skillProvider: 'google',
    apiKeyService: 'serpapi',
    keyUrl: 'https://serpapi.com/manage-api-key',
  },
  {
    id: 'tavily',
    label: 'Tavily',
    category: 'web_search',
    description: 'AI-optimized answers with a concise summary; paid after free quota.',
    skillType: 'web_search',
    credentialMode: 'api_key',
    skillProvider: 'tavily',
    apiKeyService: 'tavily',
    keyUrl: 'https://app.tavily.com/home',
  },
  // --- Travel ---
  {
    id: 'amadeus',
    label: 'Amadeus (Flight Search)',
    category: 'travel',
    description: 'Live flight search via Amadeus self-service APIs (test or production).',
    skillType: 'travel',
    credentialMode: 'amadeus',
    skillProvider: 'amadeus',
    keyUrl: 'https://developers.amadeus.com/',
  },
  {
    id: 'google_flights',
    label: 'Google Flights (via SerpAPI)',
    category: 'travel',
    description: 'Uses the same SerpAPI key as Google Search.',
    skillType: 'travel',
    credentialMode: 'api_key',
    skillProvider: 'google_flights',
    apiKeyService: 'serpapi',
    keyUrl: 'https://serpapi.com/manage-api-key',
  },
]

const CATEGORIES: { id: CategoryId; label: string; description: string }[] = [
  {
    id: 'web_search',
    label: 'Web Search',
    description: 'Give agents the ability to search the live web.',
  },
  {
    id: 'travel',
    label: 'Travel & Flights',
    description: 'Flight search, itinerary lookup, and related travel APIs.',
  },
]

interface AssignmentResult {
  agentId: number
  agentName: string
  status: 'pending' | 'ok' | 'error'
  message?: string
}

const PROVIDER_TO_CATEGORY: Record<ProviderId, CategoryId> = FALLBACK_PROVIDERS.reduce(
  (acc, p) => ({ ...acc, [p.id]: p.category }),
  {} as Record<ProviderId, CategoryId>,
)

/**
 * Merge the live backend catalog with FALLBACK_PROVIDERS.
 *
 * Rules:
 *  - FALLBACK_PROVIDERS entry supplies credential-workflow fields
 *    (credentialMode / skillProvider / apiKeyService / keyUrl) — these don't
 *    exist on the backend registry.
 *  - Live row supplies fresh label + description (human-editable server-side).
 *  - Live-only rows (backend adds a new provider before the fallback array
 *    gets updated) are skipped — we can't render credential UI we don't know.
 *    The drift test blocks this case from landing in CI anyway.
 *  - Fallback-only rows (backend disabled / not yet initialized) are kept so
 *    the wizard still renders the familiar options offline.
 */
function mergeCatalog(
  search: SearchProviderInfo[] | null,
  travel: TravelProviderInfo[] | null,
): ProviderMeta[] {
  const liveById = new Map<string, { name: string; description?: string | null; status?: string }>()
  for (const p of search ?? []) liveById.set(p.id, { name: p.name, description: p.description, status: p.status })
  for (const p of travel ?? []) liveById.set(p.id, { name: p.name, description: p.description, status: p.status })

  return FALLBACK_PROVIDERS.map((fb) => {
    const live = liveById.get(fb.id)
    if (!live) return fb
    return {
      ...fb,
      label: live.name || fb.label,
      description: live.description || fb.description,
      disabled: fb.disabled || live.status === 'coming_soon',
    }
  })
}

export default function AddIntegrationWizard({
  isOpen,
  onClose,
  onComplete,
  initialCategory,
  initialProviderId,
}: Props) {
  const startingCategory: CategoryId = initialCategory ?? (initialProviderId ? PROVIDER_TO_CATEGORY[initialProviderId] : 'web_search')
  const startingProvider: ProviderId = initialProviderId ?? (startingCategory === 'travel' ? 'amadeus' : 'brave')
  const startingStep: Step = initialProviderId ? 3 : 1

  const [step, setStep] = useState<Step>(startingStep)
  const [category, setCategory] = useState<CategoryId>(startingCategory)
  const [provider, setProvider] = useState<ProviderId>(startingProvider)

  // api_key mode
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)

  // amadeus mode
  const [amadeusKey, setAmadeusKey] = useState('')
  const [amadeusSecret, setAmadeusSecret] = useState('')
  const [amadeusEnv, setAmadeusEnv] = useState<'test' | 'production'>('test')

  // searxng mode
  const [autoProvision, setAutoProvision] = useState(true)
  const [externalUrl, setExternalUrl] = useState('')
  const [searxngInstanceName, setSearxngInstanceName] = useState('SearXNG')
  const [existingSearxngInstances, setExistingSearxngInstances] = useState<SearxngInstance[]>([])
  const [existingSearxngLoading, setExistingSearxngLoading] = useState(false)
  const [deletingSearxngId, setDeletingSearxngId] = useState<number | null>(null)

  const [credentialError, setCredentialError] = useState<string | null>(null)
  const [credentialErrorInstanceId, setCredentialErrorInstanceId] = useState<number | null>(null)
  const [savingCredentials, setSavingCredentials] = useState(false)
  const [savedSearxngInstanceId, setSavedSearxngInstanceId] = useState<number | null>(null)

  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set())

  const [assignmentResults, setAssignmentResults] = useState<AssignmentResult[]>([])
  const [assigning, setAssigning] = useState(false)

  // Live catalog — mirrors StepSkills.tsx. Falls back to FALLBACK_PROVIDERS if
  // either endpoint fails so the wizard still works offline / pre-boot.
  const [providers, setProviders] = useState<ProviderMeta[]>(FALLBACK_PROVIDERS)

  useEffect(() => {
    if (!isOpen) return
    let cancelled = false
    Promise.all([
      api.getSearchProviders().catch(() => null),
      api.getTravelProviders().catch(() => null),
    ])
      .then(([search, travel]) => {
        if (cancelled) return
        // If BOTH fetches failed, stay on the static fallback.
        if (search === null && travel === null) return
        setProviders(mergeCatalog(search, travel))
      })
      .catch(() => { /* swallow — fallback already set */ })
    return () => { cancelled = true }
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return
    setStep(startingStep)
    setCategory(startingCategory)
    setProvider(startingProvider)
    setApiKey('')
    setShowKey(false)
    setAmadeusKey('')
    setAmadeusSecret('')
    setAmadeusEnv('test')
    setAutoProvision(true)
    setExternalUrl('')
    setSearxngInstanceName('SearXNG')
    setExistingSearxngInstances([])
    setDeletingSearxngId(null)
    setCredentialError(null)
    setCredentialErrorInstanceId(null)
    setSavingCredentials(false)
    setSavedSearxngInstanceId(null)
    setAgents([])
    setSelectedAgentIds(new Set())
    setAssignmentResults([])
    setAssigning(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  useEffect(() => {
    if (step !== 4 || agents.length > 0) return
    setAgentsLoading(true)
    api.getAgents(true).then(setAgents).finally(() => setAgentsLoading(false))
  }, [step, agents.length])

  // Fetch existing SearXNG instances when entering step 3 for searxng_autoprovision
  useEffect(() => {
    if (step !== 3 || provider !== 'searxng') return
    let cancelled = false
    setExistingSearxngLoading(true)
    api.listSearxngInstances()
      .then((list) => {
        if (cancelled) return
        setExistingSearxngInstances(list || [])
        // Suggest a unique name when the default 'SearXNG' is already taken.
        const taken = new Set((list || []).map((i) => i.instance_name))
        if (taken.has('SearXNG')) {
          let n = 2
          while (taken.has(`SearXNG (${n})`)) n++
          setSearxngInstanceName(`SearXNG (${n})`)
        }
      })
      .catch(() => { /* non-fatal; user can still proceed */ })
      .finally(() => { if (!cancelled) setExistingSearxngLoading(false) })
    return () => { cancelled = true }
  }, [step, provider])

  const meta = (providers.find((p) => p.id === provider) ?? FALLBACK_PROVIDERS.find((p) => p.id === provider))!
  const categoryProviders = providers.filter((p) => p.category === category)

  const saveCredentials = async (): Promise<boolean> => {
    setSavingCredentials(true)
    setCredentialError(null)
    try {
      if (meta.credentialMode === 'api_key') {
        if (!apiKey.trim() || apiKey.trim().length < 10) {
          setCredentialError('Paste the full API key')
          return false
        }
        let res = await authenticatedFetch('/api/api-keys', {
          method: 'POST',
          body: JSON.stringify({
            service: meta.apiKeyService,
            api_key: apiKey.trim(),
            is_active: true,
          }),
        })
        if (res.status === 400) {
          const body = await res.json().catch(() => ({}))
          if (/already/i.test(body.detail || '')) {
            res = await authenticatedFetch(`/api/api-keys/${meta.apiKeyService}`, {
              method: 'PUT',
              body: JSON.stringify({ api_key: apiKey.trim(), is_active: true }),
            })
          }
        }
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail || `HTTP ${res.status}`)
        }
        return true
      }

      if (meta.credentialMode === 'searxng_autoprovision') {
        const name = (searxngInstanceName || '').trim() || 'SearXNG'
        const payload: any = {
          instance_name: name,
          auto_provision: autoProvision,
        }
        if (!autoProvision) {
          if (!externalUrl.trim()) {
            setCredentialError('Enter the SearXNG base URL (or enable auto-provision).')
            return false
          }
          payload.base_url = externalUrl.trim().replace(/\/$/, '')
        }
        const res = await authenticatedFetch('/api/hub/searxng/instances', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        if (!res.ok && res.status !== 202) {
          const body = await res.json().catch(() => ({}))
          const detail = body?.detail
          if (detail && typeof detail === 'object' && detail.code === 'searxng_instance_exists') {
            setCredentialError(detail.message || `Instance '${name}' already exists.`)
            setCredentialErrorInstanceId(detail.existing_instance_id ?? null)
            return false
          }
          throw new Error(typeof detail === 'string' ? detail : `HTTP ${res.status}`)
        }
        const body = await res.json().catch(() => ({}))
        if (body?.id) setSavedSearxngInstanceId(body.id)
        return true
      }

      if (meta.credentialMode === 'amadeus') {
        if (!amadeusKey.trim() || !amadeusSecret.trim()) {
          setCredentialError('Both API key and secret are required.')
          return false
        }
        const res = await authenticatedFetch('/api/flight-providers/amadeus/configure', {
          method: 'POST',
          body: JSON.stringify({
            name: 'Amadeus',
            api_key: amadeusKey.trim(),
            api_secret: amadeusSecret.trim(),
            environment: amadeusEnv,
            default_currency: 'USD',
            max_results: 5,
          }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          // If it already exists, treat as OK — the user is re-running the wizard.
          if (res.status === 400 && /already/i.test(body.detail || '')) return true
          throw new Error(body.detail || `HTTP ${res.status}`)
        }
        return true
      }

      return false
    } catch (err: any) {
      setCredentialError(err.message || 'Failed to save credentials')
      return false
    } finally {
      setSavingCredentials(false)
    }
  }

  const runAssignment = async () => {
    setAssigning(true)
    const selectedAgents = agents.filter((a) => selectedAgentIds.has(a.id))
    const results: AssignmentResult[] = selectedAgents.map((a) => ({
      agentId: a.id,
      agentName: a.contact_name,
      status: 'pending',
    }))
    setAssignmentResults(results)

    for (let i = 0; i < selectedAgents.length; i += 1) {
      const agent = selectedAgents[i]
      try {
        if (meta.skillType === 'web_search') {
          const cfg: Record<string, any> = {
            provider: meta.skillProvider,
            max_results: 5,
            language: 'en',
            country: 'US',
            safe_search: true,
          }
          if (meta.id === 'searxng' && savedSearxngInstanceId) {
            cfg.searxng_instance_id = savedSearxngInstanceId
          }
          await api.updateAgentSkill(agent.id, 'web_search', {
            is_enabled: true,
            config: cfg,
          })
        } else {
          // travel — flight provider per-agent config
          const res = await authenticatedFetch(
            `/api/flight-providers/agents/${agent.id}/provider`,
            {
              method: 'PUT',
              body: JSON.stringify({ provider: meta.skillProvider, settings: {} }),
            },
          )
          if (!res.ok) {
            const body = await res.json().catch(() => ({}))
            throw new Error(body.detail || `HTTP ${res.status}`)
          }
        }
        setAssignmentResults((prev) =>
          prev.map((r, idx) => (idx === i ? { ...r, status: 'ok' } : r)),
        )
      } catch (err: any) {
        setAssignmentResults((prev) =>
          prev.map((r, idx) =>
            idx === i ? { ...r, status: 'error', message: err?.message || 'Failed' } : r,
          ),
        )
      }
    }
    setAssigning(false)
  }

  useEffect(() => {
    if (step === 5 && assignmentResults.length === 0 && !assigning) {
      runAssignment()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  if (!isOpen) return null

  const stepIndicator = (
    <div className="flex items-center justify-center gap-2 mb-5">
      {[1, 2, 3, 4, 5].map((n) => (
        <div key={n} className="flex items-center gap-2">
          <div
            className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
              n === step ? 'bg-teal-500 text-white' :
              n < step ? 'bg-teal-500/20 text-teal-400' :
              'bg-white/5 text-gray-500'
            }`}
          >
            {n < step ? '✓' : n}
          </div>
          {n < 5 && (
            <div className={`w-6 h-0.5 ${n < step ? 'bg-teal-500/40' : 'bg-white/5'}`} />
          )}
        </div>
      ))}
    </div>
  )

  // STEP 1 — Pick category
  if (step === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
        <button
          onClick={() => {
            // Reset to first provider of chosen category when stepping forward.
            const first = providers.find((p) => p.category === category && !p.disabled)
            if (first) setProvider(first.id)
            setStep(2)
          }}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg"
        >
          Next: Pick provider →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Add Integration" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">What kind of integration?</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              We'll walk you through the credentials and, at the end, let you wire it up to one
              or more agents in a single click.
            </p>
          </div>
          <div className="grid gap-2">
            {CATEGORIES.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setCategory(c.id)}
                className={`p-3 text-left rounded-lg border transition-colors ${
                  category === c.id
                    ? 'border-teal-500/60 bg-teal-500/10'
                    : 'border-white/10 hover:bg-white/[0.03]'
                }`}
              >
                <div className="text-sm text-white">{c.label}</div>
                <div className="text-xs text-gray-500">{c.description}</div>
              </button>
            ))}
          </div>
        </div>
      </Modal>
    )
  }

  // STEP 2 — Pick provider within category
  if (step === 2) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(1)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
        <button
          onClick={() => setStep(3)}
          disabled={meta.disabled}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg disabled:opacity-40"
        >
          Next: Credentials →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Choose a provider" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div className="grid gap-2">
            {categoryProviders.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => !p.disabled && setProvider(p.id)}
                disabled={p.disabled}
                title={p.disabledReason}
                className={`p-3 text-left rounded-lg border transition-colors ${
                  provider === p.id
                    ? 'border-teal-500/60 bg-teal-500/10'
                    : p.disabled
                    ? 'border-white/5 bg-white/[0.02] opacity-50 cursor-not-allowed'
                    : 'border-white/10 hover:bg-white/[0.03]'
                }`}
              >
                <div className="text-sm text-white flex items-center gap-2">
                  {p.label}
                  {p.disabled && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-500/20 text-gray-400">
                      Coming soon
                    </span>
                  )}
                </div>
                <div className="text-xs text-gray-500">{p.description}</div>
                {p.disabled && p.disabledReason && (
                  <div className="text-[11px] text-gray-500 mt-1">{p.disabledReason}</div>
                )}
              </button>
            ))}
          </div>
        </div>
      </Modal>
    )
  }

  // STEP 3 — Credentials (mode-dependent)
  if (step === 3) {
    const canProceed =
      meta.credentialMode === 'api_key'
        ? !!apiKey.trim()
        : meta.credentialMode === 'searxng_autoprovision'
        ? (!!searxngInstanceName.trim() && (autoProvision || !!externalUrl.trim()))
        : meta.credentialMode === 'amadeus'
        ? !!amadeusKey.trim() && !!amadeusSecret.trim()
        : false

    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(initialProviderId ? 1 : 2)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
        <button
          onClick={async () => { if (await saveCredentials()) setStep(4) }}
          disabled={savingCredentials || !canProceed}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg disabled:opacity-40"
        >
          {savingCredentials ? 'Saving…' : 'Save & continue →'}
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title={`${meta.label}`} footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          {meta.credentialMode === 'api_key' && (
            <>
              {meta.keyUrl && (
                <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg p-4 text-sm text-amber-100">
                  <p className="font-medium mb-1">How to get your {meta.label} API key</p>
                  <p className="text-amber-200/90">
                    Open{' '}
                    <a href={meta.keyUrl} target="_blank" rel="noopener noreferrer" className="underline">
                      {meta.keyUrl}
                    </a>
                    , sign in, and copy your API key.
                  </p>
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1.5">API key *</label>
                <div className="relative">
                  <input
                    type={showKey ? 'text' : 'password'}
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="Paste your key here"
                    className="w-full px-3 py-2 pr-20 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm font-mono focus:border-teal-500/50 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey(!showKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-white"
                  >
                    {showKey ? 'Hide' : 'Show'}
                  </button>
                </div>
                <p className="text-[11px] text-gray-500 mt-1">
                  Keys are encrypted per-tenant and never round-trip in plaintext again.
                </p>
              </div>
            </>
          )}

          {meta.credentialMode === 'searxng_autoprovision' && (
            <>
              <div className="bg-teal-900/20 border border-teal-700/40 rounded-lg p-4 text-sm text-teal-100">
                <p className="font-medium mb-1">Self-hosted — no API key</p>
                <p className="text-teal-200/90">
                  Tsushin can spin up a private SearXNG container for your tenant automatically
                  (like Ollama and Kokoro). No compose files, no shared keys — a fresh
                  <code className="px-1 text-teal-200"> secret_key</code> is generated per instance.
                </p>
              </div>

              {(existingSearxngLoading || existingSearxngInstances.length > 0) && (
                <div className="border border-white/10 rounded-lg bg-white/[0.02] p-3 space-y-2">
                  <div className="text-xs font-medium text-gray-300">Existing SearXNG instances</div>
                  {existingSearxngLoading ? (
                    <div className="text-xs text-gray-500">Loading…</div>
                  ) : (
                    <ul className="space-y-1">
                      {existingSearxngInstances.map((inst) => (
                        <li key={inst.id} className="flex items-center justify-between gap-2 p-2 rounded bg-white/[0.03] border border-white/5">
                          <div className="min-w-0">
                            <div className="text-sm text-white truncate">{inst.instance_name}</div>
                            <div className="text-[11px] text-gray-500 truncate">
                              {inst.container_status || 'unknown'}
                              {inst.container_port ? ` · port ${inst.container_port}` : ''}
                            </div>
                          </div>
                          <button
                            type="button"
                            disabled={deletingSearxngId === inst.id}
                            onClick={async () => {
                              if (!confirm(`Delete SearXNG instance '${inst.instance_name}'? Its container will be removed.`)) return
                              setDeletingSearxngId(inst.id)
                              try {
                                await api.deleteSearxngInstance(inst.id)
                                const fresh = await api.listSearxngInstances().catch(() => [] as SearxngInstance[])
                                setExistingSearxngInstances(fresh)
                                setCredentialError(null)
                                setCredentialErrorInstanceId(null)
                              } catch (e: any) {
                                setCredentialError(e?.message || 'Failed to delete instance')
                              } finally {
                                setDeletingSearxngId(null)
                              }
                            }}
                            className="text-[11px] px-2 py-1 rounded bg-red-500/15 hover:bg-red-500/25 text-red-300 disabled:opacity-50"
                          >
                            {deletingSearxngId === inst.id ? 'Deleting…' : 'Delete'}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="text-[11px] text-gray-500">
                    Tip: pick a fresh name below, or delete an existing instance to free up its name.
                  </div>
                </div>
              )}

              <div className="space-y-3">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="radio"
                    checked={autoProvision}
                    onChange={() => setAutoProvision(true)}
                    className="mt-1"
                  />
                  <div>
                    <div className="text-sm text-white">Auto-provision a SearXNG container (recommended)</div>
                    <div className="text-xs text-gray-500">
                      We'll allocate a port in 6500-6599, pull ghcr.io/searxng/searxng, and wire it on tsushin-network.
                    </div>
                  </div>
                </label>
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="radio"
                    checked={!autoProvision}
                    onChange={() => setAutoProvision(false)}
                    className="mt-1"
                  />
                  <div className="flex-1">
                    <div className="text-sm text-white">Use an existing SearXNG instance</div>
                    <input
                      type="text"
                      value={externalUrl}
                      onChange={(e) => setExternalUrl(e.target.value)}
                      placeholder="https://searxng.example.com"
                      disabled={autoProvision}
                      className="mt-2 w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm font-mono disabled:opacity-40"
                    />
                  </div>
                </label>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1.5">Instance name</label>
                <input
                  type="text"
                  value={searxngInstanceName}
                  onChange={(e) => { setSearxngInstanceName(e.target.value); setCredentialError(null); setCredentialErrorInstanceId(null) }}
                  placeholder="SearXNG"
                  className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
                />
                <p className="text-[11px] text-gray-500 mt-1">
                  Must be unique per tenant. We pre-filled a fresh name based on your existing instances.
                </p>
              </div>
            </>
          )}

          {meta.credentialMode === 'amadeus' && (
            <>
              {meta.keyUrl && (
                <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg p-4 text-sm text-amber-100">
                  <p className="font-medium mb-1">Get your Amadeus credentials</p>
                  <p className="text-amber-200/90">
                    Register at{' '}
                    <a href={meta.keyUrl} target="_blank" rel="noopener noreferrer" className="underline">
                      {meta.keyUrl}
                    </a>
                    , create a new Self-Service app, and copy both the API Key and API Secret.
                  </p>
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1.5">API key *</label>
                <input
                  type="text"
                  value={amadeusKey}
                  onChange={(e) => setAmadeusKey(e.target.value)}
                  placeholder="Amadeus API Key"
                  className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1.5">API secret *</label>
                <input
                  type="password"
                  value={amadeusSecret}
                  onChange={(e) => setAmadeusSecret(e.target.value)}
                  placeholder="Amadeus API Secret"
                  className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm font-mono"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1.5">Environment</label>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setAmadeusEnv('test')}
                    className={`px-3 py-1.5 text-sm rounded-lg border ${amadeusEnv === 'test' ? 'border-teal-500/60 bg-teal-500/10 text-white' : 'border-white/10 text-gray-400'}`}
                  >
                    Test
                  </button>
                  <button
                    type="button"
                    onClick={() => setAmadeusEnv('production')}
                    className={`px-3 py-1.5 text-sm rounded-lg border ${amadeusEnv === 'production' ? 'border-teal-500/60 bg-teal-500/10 text-white' : 'border-white/10 text-gray-400'}`}
                  >
                    Production
                  </button>
                </div>
              </div>
            </>
          )}

          {credentialError && (
            <div className="text-sm text-red-400 bg-red-900/20 border border-red-700/40 rounded px-3 py-2 space-y-1">
              <div>{credentialError}</div>
              {credentialErrorInstanceId != null && (
                <div className="text-xs text-red-300/90">
                  Tip: delete the existing instance in the list above, or change the name below and try again.
                </div>
              )}
            </div>
          )}
        </div>
      </Modal>
    )
  }

  // STEP 4 — Agent linking
  if (step === 4) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(3)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
          <button
            onClick={() => { setSelectedAgentIds(new Set()); setStep(5) }}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white"
          >
            Skip agents
          </button>
        </div>
        <button onClick={() => setStep(5)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Next: Apply →
        </button>
      </div>
    )
    const skillLabel = meta.skillType === 'web_search' ? 'web_search' : 'flight_search'
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Link this integration to agents" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <p className="text-sm text-gray-300">
            We'll turn on the <span className="text-teal-400">{skillLabel}</span> capability on each selected agent and point it
            at <span className="text-teal-400">{meta.skillProvider}</span>.
          </p>

          {agentsLoading ? (
            <div className="text-center py-8 text-sm text-gray-500">Loading agents…</div>
          ) : agents.length === 0 ? (
            <div className="text-center py-6 text-sm text-gray-500 border border-white/5 rounded-lg bg-white/[0.02]">
              No active agents. You can link an agent later.
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">
                  {selectedAgentIds.size} of {agents.length} agent{agents.length !== 1 ? 's' : ''} selected
                </span>
                <button
                  onClick={() => {
                    if (selectedAgentIds.size === agents.length) setSelectedAgentIds(new Set())
                    else setSelectedAgentIds(new Set(agents.map((a) => a.id)))
                  }}
                  className="text-xs text-teal-400 hover:text-teal-300"
                >
                  {selectedAgentIds.size === agents.length ? 'Clear all' : 'Select all'}
                </button>
              </div>
              <div className="max-h-64 overflow-y-auto space-y-1 border border-white/10 rounded-lg p-3 bg-white/[0.02]">
                {agents.map((agent) => (
                  <label key={agent.id} className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-white/5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedAgentIds.has(agent.id)}
                      onChange={(e) => {
                        const next = new Set(selectedAgentIds)
                        if (e.target.checked) next.add(agent.id)
                        else next.delete(agent.id)
                        setSelectedAgentIds(next)
                      }}
                      className="w-4 h-4 rounded border-white/20 text-teal-500 focus:ring-teal-500 bg-[#0a0a0f]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{agent.contact_name}</div>
                      <div className="text-xs text-gray-500">{agent.model_provider}/{agent.model_name}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      </Modal>
    )
  }

  // STEP 5 — Apply + review
  const allDone = assignmentResults.length > 0 && assignmentResults.every((r) => r.status !== 'pending')
  const noAssignmentsNeeded = assignmentResults.length === 0 && !assigning && selectedAgentIds.size === 0
  const footer = allDone || noAssignmentsNeeded ? (
    <div className="flex items-center justify-between w-full">
      <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Close</button>
      <button
        onClick={() => { onComplete?.(); onClose() }}
        className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg"
      >
        Done
      </button>
    </div>
  ) : (
    <div className="flex items-center justify-end w-full">
      <button disabled className="px-4 py-2 text-sm bg-teal-500/50 text-white/60 rounded-lg">Applying…</button>
    </div>
  )
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={noAssignmentsNeeded ? 'Integration saved' : allDone ? `${meta.label} enabled` : 'Applying…'}
      footer={footer}
      size="lg"
    >
      <div className="space-y-5">
        {stepIndicator}
        {noAssignmentsNeeded ? (
          <div className="py-6 text-sm text-gray-300 text-center">
            Credentials saved. You can link agents to this integration any time from Agent Studio.
          </div>
        ) : assignmentResults.length === 0 ? (
          <div className="py-10 text-center text-sm text-gray-400">Starting…</div>
        ) : (
          <div className="space-y-2">
            {assignmentResults.map((r) => (
              <div key={r.agentId} className="flex items-center gap-3 p-3 rounded-lg border border-white/5 bg-white/[0.02]">
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                  r.status === 'ok' ? 'bg-green-500/20 text-green-400' :
                  r.status === 'error' ? 'bg-red-500/20 text-red-400' :
                  'bg-gray-500/20 text-gray-400'
                }`}>{r.status === 'ok' ? '✓' : r.status === 'error' ? '!' : '…'}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-white truncate">{r.agentName}</div>
                  {r.status === 'error' && r.message && (
                    <div className="text-xs text-red-400 truncate">{r.message}</div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {allDone && meta.skillType === 'web_search' && (
          <div className="pt-3 border-t border-white/5">
            <h4 className="text-sm font-medium text-white mb-2">Try it out</h4>
            <div className="space-y-2">
              {[
                "What's the latest news about Anthropic?",
                'Search for reviews of the Framework laptop 13',
                'Find the best open-source TTS models in 2026',
              ].map((q) => (
                <div key={q} className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.02] border border-white/5">
                  <span className="text-sm text-teal-300 flex-1">{q}</span>
                  <button
                    onClick={() => navigator.clipboard?.writeText(q)}
                    className="text-xs px-2 py-1 bg-white/5 hover:bg-white/10 text-gray-300 rounded"
                  >
                    Copy
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  )
}
