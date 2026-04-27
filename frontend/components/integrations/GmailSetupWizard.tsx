'use client'

import { useState, useEffect, useRef } from 'react'
import Modal from '@/components/ui/Modal'
import { api, authenticatedFetch, Agent } from '@/lib/client'
import GoogleAppCredentialsStep from './GoogleAppCredentialsStep'

interface Props {
  isOpen: boolean
  onClose: () => void
  onComplete?: () => void
}

type Step = 1 | 2 | 3 | 4 | 5 | 6

interface GmailIntegration {
  id: number
  name: string
  email_address: string
  health_status: string
  is_active: boolean
}

interface AssignmentResult {
  agentId: number
  agentName: string
  status: 'pending' | 'ok' | 'error'
  message?: string
}

const POLL_INTERVAL_MS = 3000
const POLL_MAX_TICKS = 120 // 6 minutes

export default function GmailSetupWizard({ isOpen, onClose, onComplete }: Props) {
  const [step, setStep] = useState<Step>(1)

  // Step 3 state
  const [integrations, setIntegrations] = useState<GmailIntegration[]>([])
  const [integrationsLoading, setIntegrationsLoading] = useState(false)
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<number | null>(null)
  const [popupOpen, setPopupOpen] = useState(false)
  const [popupError, setPopupError] = useState<string | null>(null)
  const initialIntegrationIds = useRef<Set<number>>(new Set())
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollTicks = useRef(0)

  // Step 4 state
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set())

  // Step 6 state
  const [assignmentResults, setAssignmentResults] = useState<AssignmentResult[]>([])
  const [assigning, setAssigning] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    setStep(1)
    setIntegrations([])
    setSelectedIntegrationId(null)
    setPopupOpen(false)
    setPopupError(null)
    setAgents([])
    setSelectedAgentIds(new Set())
    setAssignmentResults([])
    setAssigning(false)
    pollTicks.current = 0
  }, [isOpen])

  useEffect(() => {
    return () => {
      if (pollTimer.current) {
        clearInterval(pollTimer.current)
        pollTimer.current = null
      }
    }
  }, [])

  // OAuth popup handoff: the popup posts a message here right before it closes.
  // We react immediately instead of waiting for the 3-second poll tick. Validates
  // origin (same-origin messaging) and the payload source marker.
  useEffect(() => {
    if (!isOpen) return
    const handler = async (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) return
      const data = ev.data
      if (!data || typeof data !== 'object') return
      if (data.source !== 'tsushin-google-oauth' || data.integration !== 'gmail') return
      if (pollTimer.current) { clearInterval(pollTimer.current); pollTimer.current = null }
      setPopupOpen(false)
      setPopupError(null)
      const list = await fetchIntegrations()
      setIntegrations(list)
      const targetId = typeof data.integration_id === 'number' ? data.integration_id : null
      const target = (targetId && list.find((i) => i.id === targetId)) ||
                     list.find((i) => !initialIntegrationIds.current.has(i.id))
      if (target) setSelectedIntegrationId(target.id)
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [isOpen])

  const handleClose = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
    onClose()
  }

  const fetchIntegrations = async (): Promise<GmailIntegration[]> => {
    const res = await authenticatedFetch('/api/hub/google/gmail/integrations')
    if (!res.ok) return []
    const data = await res.json()
    return data.integrations || []
  }

  useEffect(() => {
    if (step !== 3) return
    setIntegrationsLoading(true)
    fetchIntegrations()
      .then((list) => {
        setIntegrations(list)
        initialIntegrationIds.current = new Set(list.map((i) => i.id))
      })
      .finally(() => setIntegrationsLoading(false))
  }, [step])

  useEffect(() => {
    if (step !== 4 || agents.length > 0) return
    setAgentsLoading(true)
    api
      .getAgents(true)
      .then(setAgents)
      .finally(() => setAgentsLoading(false))
  }, [step, agents.length])

  const startNewAccountAuthorization = async () => {
    setPopupError(null)
    try {
      const res = await authenticatedFetch('/api/hub/google/gmail/oauth/authorize', {
        method: 'POST',
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `HTTP ${res.status}`)
      }
      const { authorization_url } = await res.json()
      const popup = window.open(
        authorization_url,
        'gmail-oauth',
        'width=520,height=640,left=200,top=100',
      )
      if (!popup) {
        window.location.href = authorization_url
        return
      }
      setPopupOpen(true)
      pollTicks.current = 0
      pollTimer.current = setInterval(async () => {
        pollTicks.current += 1
        if (pollTicks.current > POLL_MAX_TICKS) {
          if (pollTimer.current) clearInterval(pollTimer.current)
          pollTimer.current = null
          setPopupOpen(false)
          setPopupError(
            "Didn't detect a new Gmail account after 6 minutes. Did you finish the Google consent?",
          )
          return
        }
        const list = await fetchIntegrations()
        const newOne = list.find((i) => !initialIntegrationIds.current.has(i.id))
        if (newOne) {
          if (pollTimer.current) clearInterval(pollTimer.current)
          pollTimer.current = null
          setIntegrations(list)
          setSelectedIntegrationId(newOne.id)
          setPopupOpen(false)
        }
      }, POLL_INTERVAL_MS)
    } catch (err: any) {
      setPopupError(err.message || 'Failed to start authorization')
    }
  }

  const runAssignment = async () => {
    if (!selectedIntegrationId) return
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
        await api.updateAgentSkill(agent.id, 'gmail', { is_enabled: true, config: {} })
        await api.updateSkillIntegration(agent.id, 'gmail', {
          integration_id: selectedIntegrationId,
          config: {},
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
    if (step === 6 && assignmentResults.length === 0 && !assigning) {
      runAssignment()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  if (!isOpen) return null

  const totalSteps = 6
  const stepIndicator = (
    <div className="flex items-center justify-center gap-1.5 mb-5">
      {[1, 2, 3, 4, 5, 6].map((n) => (
        <div key={n} className="flex items-center gap-1.5">
          <div
            className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ${
              n === step
                ? 'bg-red-500 text-white'
                : n < step
                ? 'bg-red-500/20 text-red-400'
                : 'bg-white/5 text-gray-500'
            }`}
          >
            {n < step ? '✓' : n}
          </div>
          {n < totalSteps && (
            <div className={`w-5 h-0.5 ${n < step ? 'bg-red-500/40' : 'bg-white/5'}`} />
          )}
        </div>
      ))}
    </div>
  )

  // ==========================================================================
  // STEP 1 — Welcome
  // ==========================================================================
  if (step === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
          Cancel
        </button>
        <button
          onClick={() => setStep(2)}
          className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg"
        >
          Get started →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Set up Gmail" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">Connect Gmail to your agents</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              This wizard walks you through connecting a Gmail account so your agents can search
              and read email. It's a 6-step guided flow — we'll also enable the{' '}
              <span className="text-red-400">Gmail</span> skill on the agents you pick and link the
              integration automatically.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Scope</div>
              <div className="text-white">Read-only (gmail.readonly)</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Multi-account</div>
              <div className="text-white">Yes — one integration per inbox</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Cost</div>
              <div className="text-white">$0 — uses your Google Cloud app</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">What agents can do</div>
              <div className="text-white">Search, list, and read emails</div>
            </div>
          </div>
          <div className="text-xs text-gray-500 bg-red-500/5 border border-red-500/20 rounded-lg p-3">
            <span className="text-red-400 font-medium">Read-only:</span> this integration cannot send,
            draft, or delete messages.
          </div>
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 2 — Google App Credentials
  // ==========================================================================
  if (step === 2) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(1)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
          ← Back
        </button>
        <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
          Cancel
        </button>
      </div>
    )
    return (
      <Modal
        isOpen={isOpen}
        onClose={handleClose}
        title="Google OAuth app credentials"
        footer={footer}
        size="lg"
      >
        <div className="space-y-5">
          {stepIndicator}
          <p className="text-sm text-gray-300">
            Gmail and Calendar both require a Google Cloud OAuth app. If your tenant already has one
            configured, we'll reuse it.
          </p>
          <GoogleAppCredentialsStep tone="gmail" onReady={() => setStep(3)} />
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 3 — Connect Gmail account
  // ==========================================================================
  if (step === 3) {
    const canProceed = selectedIntegrationId !== null
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(2)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
          ← Back
        </button>
        <button
          onClick={() => setStep(4)}
          disabled={!canProceed}
          className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg disabled:opacity-40"
        >
          Next: Link agents →
        </button>
      </div>
    )
    return (
      <Modal
        isOpen={isOpen}
        onClose={handleClose}
        title="Connect a Gmail account"
        footer={footer}
        size="lg"
      >
        <div className="space-y-5">
          {stepIndicator}

          {integrationsLoading && (
            <div className="py-6 text-center text-sm text-gray-400">Loading Gmail integrations…</div>
          )}

          {!integrationsLoading && integrations.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-white mb-2">Existing Gmail accounts</h4>
              <div className="space-y-2 max-h-56 overflow-y-auto">
                {integrations.map((i) => (
                  <label
                    key={i.id}
                    className="flex items-center gap-3 p-3 rounded-lg border border-white/10 hover:bg-white/[0.03] cursor-pointer"
                  >
                    <input
                      type="radio"
                      name="gmail-integration"
                      checked={selectedIntegrationId === i.id}
                      onChange={() => setSelectedIntegrationId(i.id)}
                      className="text-red-500 focus:ring-red-500 bg-[#0a0a0f] border-white/20"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{i.email_address}</div>
                      <div className="text-xs text-gray-500">{i.name}</div>
                    </div>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded ${
                        i.health_status === 'healthy'
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-gray-500/20 text-gray-400'
                      }`}
                    >
                      {i.health_status}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="pt-3 border-t border-white/5">
            <h4 className="text-sm font-medium text-white mb-2">Or connect a new account</h4>
            {popupError && (
              <div className="mb-3 text-sm text-red-400 bg-red-900/20 border border-red-700/40 rounded px-3 py-2">
                {popupError}
              </div>
            )}
            <button
              type="button"
              onClick={startNewAccountAuthorization}
              disabled={popupOpen}
              className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg disabled:opacity-40"
            >
              {popupOpen ? 'Waiting for Google consent…' : 'Connect new Gmail account'}
            </button>
            {popupOpen && (
              <p className="text-xs text-gray-400 mt-2">
                A popup opened with Google's consent screen. When you finish, this step will
                auto-advance. (If the popup was blocked, we'll redirect you instead.)
              </p>
            )}
          </div>
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 4 — Link to agents
  // ==========================================================================
  if (step === 4) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(3)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
            ← Back
          </button>
          <button
            onClick={() => {
              setSelectedAgentIds(new Set())
              setStep(5)
            }}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white"
          >
            Skip this step
          </button>
        </div>
        <button
          onClick={() => setStep(5)}
          className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg"
        >
          Next: Review →
        </button>
      </div>
    )
    return (
      <Modal
        isOpen={isOpen}
        onClose={handleClose}
        title="Link Gmail to agents"
        footer={footer}
        size="lg"
      >
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <p className="text-sm text-gray-300 leading-relaxed">
              We'll enable the <span className="text-red-400">Gmail</span> skill on each selected agent
              and link it to the account you picked. You can change this later in Agent Studio.
            </p>
          </div>

          {agentsLoading ? (
            <div className="text-center py-8 text-sm text-gray-500">Loading agents…</div>
          ) : agents.length === 0 ? (
            <div className="text-center py-6 text-sm text-gray-500 border border-white/5 rounded-lg bg-white/[0.02]">
              No active agents in this tenant. You can link an agent later.
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">
                  {selectedAgentIds.size} of {agents.length} agent
                  {agents.length !== 1 ? 's' : ''} selected
                </span>
                <button
                  onClick={() => {
                    if (selectedAgentIds.size === agents.length) {
                      setSelectedAgentIds(new Set())
                    } else {
                      setSelectedAgentIds(new Set(agents.map((a) => a.id)))
                    }
                  }}
                  className="text-xs text-red-400 hover:text-red-300"
                >
                  {selectedAgentIds.size === agents.length ? 'Clear all' : 'Select all'}
                </button>
              </div>
              <div className="max-h-64 overflow-y-auto space-y-1 border border-white/10 rounded-lg p-3 bg-white/[0.02]">
                {agents.map((agent) => (
                  <label
                    key={agent.id}
                    className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-white/5 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedAgentIds.has(agent.id)}
                      onChange={(e) => {
                        const next = new Set(selectedAgentIds)
                        if (e.target.checked) next.add(agent.id)
                        else next.delete(agent.id)
                        setSelectedAgentIds(next)
                      }}
                      className="w-4 h-4 rounded border-white/20 text-red-500 focus:ring-red-500 bg-[#0a0a0f]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{agent.contact_name}</div>
                      <div className="text-xs text-gray-500">
                        {agent.model_provider}/{agent.model_name}
                      </div>
                    </div>
                    {agent.is_default && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 shrink-0">
                        Default
                      </span>
                    )}
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 5 — Review
  // ==========================================================================
  if (step === 5) {
    const selectedIntegration = integrations.find((i) => i.id === selectedIntegrationId)
    const selectedAgents = agents.filter((a) => selectedAgentIds.has(a.id))
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(4)} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
          ← Back
        </button>
        <button
          onClick={() => setStep(6)}
          className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg"
        >
          Apply
        </button>
      </div>
    )
    return (
      <Modal
        isOpen={isOpen}
        onClose={handleClose}
        title="Review & apply"
        footer={footer}
        size="lg"
      >
        <div className="space-y-5">
          {stepIndicator}
          <div className="grid gap-3">
            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Gmail account</div>
              <div className="text-sm text-white">{selectedIntegration?.email_address || '—'}</div>
            </div>
            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Scope</div>
              <div className="text-sm text-white">Read-only</div>
            </div>
            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Agents to enable</div>
              {selectedAgents.length === 0 ? (
                <div className="text-sm text-gray-400">No agents selected — you can link later.</div>
              ) : (
                <div className="flex flex-wrap gap-2 mt-1">
                  {selectedAgents.map((a) => (
                    <span
                      key={a.id}
                      className="text-xs px-2 py-1 rounded bg-red-500/15 text-red-300"
                    >
                      {a.contact_name}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </Modal>
    )
  }

  // ==========================================================================
  // STEP 6 — Progress & done
  // ==========================================================================
  const allDone =
    assignmentResults.length > 0 && assignmentResults.every((r) => r.status !== 'pending')
  const hasErrors = assignmentResults.some((r) => r.status === 'error')
  const footer = allDone ? (
    <div className="flex items-center justify-between w-full">
      <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white">
        Close
      </button>
      <div className="flex items-center gap-2">
        {hasErrors && (
          <button
            onClick={() => {
              setAssignmentResults([])
              runAssignment()
            }}
            className="px-4 py-2 text-sm bg-amber-600 hover:bg-amber-500 text-white rounded-lg"
          >
            Retry failed
          </button>
        )}
        <button
          onClick={() => {
            onComplete?.()
            handleClose()
          }}
          className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 text-white rounded-lg"
        >
          Done
        </button>
      </div>
    </div>
  ) : (
    <div className="flex items-center justify-end w-full">
      <button disabled className="px-4 py-2 text-sm bg-red-600/50 text-white/60 rounded-lg">
        Applying…
      </button>
    </div>
  )
  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={allDone ? 'Gmail connected' : 'Applying…'}
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
              <div
                key={r.agentId}
                className="flex items-center gap-3 p-3 rounded-lg border border-white/5 bg-white/[0.02]"
              >
                <span
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-xs ${
                    r.status === 'ok'
                      ? 'bg-green-500/20 text-green-400'
                      : r.status === 'error'
                      ? 'bg-red-500/20 text-red-400'
                      : 'bg-gray-500/20 text-gray-400'
                  }`}
                >
                  {r.status === 'ok' ? '✓' : r.status === 'error' ? '!' : '…'}
                </span>
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
        {allDone && !hasErrors && assignmentResults.length > 0 && (
          <div className="text-sm text-green-400 bg-green-900/20 border border-green-700/40 rounded px-3 py-2">
            Gmail is ready. Your agents can now search and read emails on behalf of users.
          </div>
        )}
      </div>
    </Modal>
  )
}
