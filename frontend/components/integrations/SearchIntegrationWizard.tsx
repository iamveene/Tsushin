'use client'

import { useState, useEffect } from 'react'
import Modal from '@/components/ui/Modal'
import { api, authenticatedFetch, Agent } from '@/lib/client'

interface Props {
  isOpen: boolean
  onClose: () => void
  onComplete?: () => void
}

type Step = 1 | 2 | 3 | 4 | 5

type ProviderChoice = 'brave' | 'tavily' | 'serpapi'

const PROVIDERS: Array<{
  id: ProviderChoice
  label: string
  description: string
  service: 'brave_search' | 'tavily' | 'serpapi'
  skillProvider: 'brave' | 'tavily' | 'google'
  keyUrl: string
  disabled?: boolean
  disabledReason?: string
}> = [
  {
    id: 'brave',
    label: 'Brave Search (recommended)',
    description: 'Privacy-first, generous free tier, no PII in queries.',
    service: 'brave_search',
    skillProvider: 'brave',
    keyUrl: 'https://brave.com/search/api/',
  },
  {
    id: 'tavily',
    label: 'Tavily',
    description: 'AI-optimized answers; paid after free quota.',
    service: 'tavily',
    skillProvider: 'tavily',
    keyUrl: 'https://tavily.com/',
    disabled: true,
    disabledReason: 'Adapter not yet shipped — we can save your key for when it lands.',
  },
  {
    id: 'serpapi',
    label: 'SerpAPI (Google)',
    description: 'Live Google SERP; paid after free quota.',
    service: 'serpapi',
    skillProvider: 'google',
    keyUrl: 'https://serpapi.com/manage-api-key',
  },
]

interface AssignmentResult {
  agentId: number
  agentName: string
  status: 'pending' | 'ok' | 'error'
  message?: string
}

export default function SearchIntegrationWizard({ isOpen, onClose, onComplete }: Props) {
  const [step, setStep] = useState<Step>(1)
  const [provider, setProvider] = useState<ProviderChoice>('brave')
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [keyError, setKeyError] = useState<string | null>(null)
  const [savingKey, setSavingKey] = useState(false)

  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set())

  const [assignmentResults, setAssignmentResults] = useState<AssignmentResult[]>([])
  const [assigning, setAssigning] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    setStep(1)
    setProvider('brave')
    setApiKey('')
    setShowKey(false)
    setKeyError(null)
    setSavingKey(false)
    setAgents([])
    setSelectedAgentIds(new Set())
    setAssignmentResults([])
    setAssigning(false)
  }, [isOpen])

  useEffect(() => {
    if (step !== 4 || agents.length > 0) return
    setAgentsLoading(true)
    api.getAgents(true).then(setAgents).finally(() => setAgentsLoading(false))
  }, [step, agents.length])

  const meta = PROVIDERS.find((p) => p.id === provider)!

  const saveApiKey = async () => {
    if (!apiKey.trim() || apiKey.trim().length < 10) {
      setKeyError('Paste the full API key')
      return false
    }
    setSavingKey(true)
    setKeyError(null)
    try {
      // POST first — 400 "already configured" → retry as PUT
      let res = await authenticatedFetch('/api/api-keys', {
        method: 'POST',
        body: JSON.stringify({
          service: meta.service,
          api_key: apiKey.trim(),
          is_active: true,
        }),
      })
      if (res.status === 400) {
        const body = await res.json().catch(() => ({}))
        if (/already/i.test(body.detail || '')) {
          res = await authenticatedFetch(`/api/api-keys/${meta.service}`, {
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
    } catch (err: any) {
      setKeyError(err.message || 'Failed to save API key')
      return false
    } finally {
      setSavingKey(false)
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
        await api.updateAgentSkill(agent.id, 'web_search', {
          is_enabled: true,
          config: {
            provider: meta.skillProvider,
            max_results: 5,
            language: 'en',
            country: 'US',
            safe_search: true,
          },
        })
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

  const totalSteps = 5
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
          {n < totalSteps && (
            <div className={`w-6 h-0.5 ${n < step ? 'bg-teal-500/40' : 'bg-white/5'}`} />
          )}
        </div>
      ))}
    </div>
  )

  if (step === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={onClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
        <button onClick={() => setStep(2)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Get started →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Give agents web search" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">Let agents browse the web</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              Pick a search provider, paste your API key, and we'll enable the
              <span className="text-teal-400"> web_search</span> skill on the agents you choose.
            </p>
          </div>
          <div className="grid gap-2">
            {PROVIDERS.map((p) => (
              <div key={p.id} className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
                <div className="text-sm text-white">{p.label}</div>
                <div className="text-xs text-gray-500">{p.description}</div>
              </div>
            ))}
          </div>
        </div>
      </Modal>
    )
  }

  if (step === 2) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(1)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
        <button
          onClick={() => setStep(3)}
          disabled={meta.disabled}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg disabled:opacity-40"
        >
          Next: Enter key →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Choose a search provider" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div className="grid gap-2">
            {PROVIDERS.map((p) => (
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

  if (step === 3) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(2)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
        <button
          onClick={async () => { if (await saveApiKey()) setStep(4) }}
          disabled={savingKey || !apiKey.trim()}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg disabled:opacity-40"
        >
          {savingKey ? 'Saving…' : 'Save & continue →'}
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title={`${meta.label} — API key`} footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
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
              Keys are encrypted per-tenant (apikey_{meta.service}_&lt;tenant_id&gt;) and never round-trip in plaintext again.
            </p>
          </div>

          {keyError && (
            <div className="text-sm text-red-400 bg-red-900/20 border border-red-700/40 rounded px-3 py-2">
              {keyError}
            </div>
          )}
        </div>
      </Modal>
    )
  }

  if (step === 4) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(3)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">← Back</button>
          <button onClick={() => { setSelectedAgentIds(new Set()); setStep(5) }} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
            Skip agents
          </button>
        </div>
        <button onClick={() => setStep(5)} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg">
          Next: Review →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={onClose} title="Enable search for agents" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <p className="text-sm text-gray-300">
            We'll turn on the <span className="text-teal-400">web_search</span> skill on each selected agent and
            point it at <span className="text-teal-400">{meta.skillProvider}</span>.
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

  // Step 5
  const allDone = assignmentResults.length > 0 && assignmentResults.every((r) => r.status !== 'pending')
  const footer = allDone ? (
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
      title={allDone ? 'Web search enabled' : 'Applying…'}
      footer={footer}
      size="lg"
    >
      <div className="space-y-5">
        {stepIndicator}
        {assignmentResults.length === 0 ? (
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
        {allDone && (
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
