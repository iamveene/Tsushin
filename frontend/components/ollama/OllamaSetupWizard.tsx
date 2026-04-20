'use client'

import { useState, useEffect, useRef } from 'react'
import Modal from '@/components/ui/Modal'
import { api, Agent, ProviderInstance } from '@/lib/client'
import { OLLAMA_CURATED_MODELS } from '@/lib/ollama-curated-models'

interface OllamaSetupWizardProps {
  isOpen: boolean
  onClose: () => void
  onComplete?: (instance: ProviderInstance) => void
}

type Step = 1 | 2 | 3 | 4 | 5 | 6  // 6 = provisioning/pull progress

interface WizardConfig {
  instance_name: string
  gpu_enabled: boolean
  mem_limit: string
  model_choice: string  // id from OLLAMA_CURATED_MODELS or 'custom'
  custom_model: string
}

const DEFAULT_CONFIG: WizardConfig = {
  instance_name: 'Ollama Local',
  gpu_enabled: false,
  mem_limit: '4g',
  model_choice: 'llama3.2:3b',
  custom_model: '',
}

// Curated model list — single source of truth in lib/ollama-curated-models.
// The Hub Ollama panel imports the same list so the two surfaces never drift.

const MEM_LIMITS = [
  { value: '2g',  label: '2 GB — minimal' },
  { value: '4g',  label: '4 GB — recommended' },
  { value: '8g',  label: '8 GB — larger models' },
  { value: '16g', label: '16 GB — big models / many concurrent' },
]

export default function OllamaSetupWizard({ isOpen, onClose, onComplete }: OllamaSetupWizardProps) {
  const [step, setStep] = useState<Step>(1)
  const [config, setConfig] = useState<WizardConfig>(DEFAULT_CONFIG)
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set())
  const [error, setError] = useState<string | null>(null)

  // Progress state
  const [instance, setInstance] = useState<ProviderInstance | null>(null)
  const [phase, setPhase] = useState<'idle' | 'provision' | 'pull' | 'assign' | 'done' | 'error'>('idle')
  const [phaseMessage, setPhaseMessage] = useState<string>('')
  const [pullPercent, setPullPercent] = useState<number>(0)

  const provisionPoller = useRef<ReturnType<typeof setInterval> | null>(null)
  const pullPoller = useRef<ReturnType<typeof setInterval> | null>(null)

  // Reset on open
  useEffect(() => {
    if (!isOpen) return
    setStep(1)
    setConfig(DEFAULT_CONFIG)
    setAgents([])
    setSelectedAgentIds(new Set())
    setError(null)
    setInstance(null)
    setPhase('idle')
    setPhaseMessage('')
    setPullPercent(0)
  }, [isOpen])

  // Fetch agents when entering step 4
  useEffect(() => {
    if (step !== 4 || agents.length > 0) return
    setAgentsLoading(true)
    api.getAgents(true)
      .then(setAgents)
      .catch(() => setAgents([]))
      .finally(() => setAgentsLoading(false))
  }, [step])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (provisionPoller.current) clearInterval(provisionPoller.current)
      if (pullPoller.current) clearInterval(pullPoller.current)
    }
  }, [])

  // Enter key navigation for steps 1-5
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Enter') return
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) return
      if (e.shiftKey) return
      if (step === 1) { e.preventDefault(); setStep(2) }
      else if (step === 2 && config.instance_name.trim()) { e.preventDefault(); setStep(3) }
      else if (step === 3 && isModelValid()) { e.preventDefault(); setStep(4) }
      else if (step === 4) { e.preventDefault(); setStep(5) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, step, config])

  const isModelValid = () => {
    if (config.model_choice === 'custom') return config.custom_model.trim().length > 0
    return !!config.model_choice
  }

  const resolvedModelName = () =>
    config.model_choice === 'custom' ? config.custom_model.trim() : config.model_choice

  // ============================================================
  // Orchestration — ensure → provision → pull → assign
  // ============================================================

  const startProvision = async () => {
    setError(null)
    setStep(6)
    setPhase('provision')
    setPhaseMessage('Creating Ollama provider instance...')
    try {
      // 1) Ensure Ollama instance exists (reuses or creates)
      const inst = await api.ensureOllamaInstance()
      setInstance(inst)

      setPhaseMessage('Provisioning Ollama container (may take 1–2 min to pull image)...')
      await api.provisionOllamaContainer(inst.id, config.gpu_enabled, config.mem_limit)
      pollContainerStatus(inst.id)
    } catch (e: any) {
      setPhase('error')
      setPhaseMessage(`Provisioning failed: ${e?.message || 'unknown error'}`)
    }
  }

  const pollContainerStatus = (instId: number) => {
    if (provisionPoller.current) clearInterval(provisionPoller.current)
    let ticks = 0
    provisionPoller.current = setInterval(async () => {
      ticks++
      try {
        const status = await api.getOllamaContainerStatus(instId)
        const state = (status?.status || '').toLowerCase()
        if (state === 'running') {
          if (provisionPoller.current) clearInterval(provisionPoller.current)
          provisionPoller.current = null
          await startPull(instId)
        } else if (state === 'error') {
          if (provisionPoller.current) clearInterval(provisionPoller.current)
          provisionPoller.current = null
          setPhase('error')
          setPhaseMessage('Container failed to start. Check Hub > Local Services > Ollama for details.')
        }
      } catch {
        // transient — keep polling
      }
      if (ticks > 120) {  // ~6 min cap
        if (provisionPoller.current) clearInterval(provisionPoller.current)
        provisionPoller.current = null
        setPhase('error')
        setPhaseMessage('Container provisioning timed out after 6 minutes.')
      }
    }, 3000)
  }

  const startPull = async (instId: number) => {
    setPhase('pull')
    setPullPercent(0)
    const modelName = resolvedModelName()
    setPhaseMessage(`Pulling ${modelName}...`)
    try {
      const job = await api.pullOllamaModel(instId, modelName)
      pollPullStatus(instId, job.job_id)
    } catch (e: any) {
      setPhase('error')
      setPhaseMessage(`Model pull failed to start: ${e?.message || 'unknown error'}`)
    }
  }

  const pollPullStatus = (instId: number, jobId: string) => {
    if (pullPoller.current) clearInterval(pullPoller.current)
    let ticks = 0
    pullPoller.current = setInterval(async () => {
      ticks++
      try {
        const status = await api.getPullJobStatus(instId, jobId)
        if (typeof status.percent === 'number') setPullPercent(status.percent)
        if (status.status === 'done') {
          if (pullPoller.current) clearInterval(pullPoller.current)
          pullPoller.current = null
          setPullPercent(100)
          await assignAgentsAndFinish(instId)
        } else if (status.status === 'error') {
          if (pullPoller.current) clearInterval(pullPoller.current)
          pullPoller.current = null
          setPhase('error')
          setPhaseMessage(`Model pull failed: ${status.error || 'unknown error'}`)
        } else {
          setPhaseMessage(`Pulling ${resolvedModelName()} — ${status.percent ?? 0}%`)
        }
      } catch {
        // transient
      }
      if (ticks > 600) {  // ~20 min cap
        if (pullPoller.current) clearInterval(pullPoller.current)
        pullPoller.current = null
        setPhase('error')
        setPhaseMessage('Model pull timed out after 20 minutes.')
      }
    }, 2000)
  }

  const assignAgentsAndFinish = async (instId: number) => {
    setPhase('assign')
    setPhaseMessage('Wiring agents to the new Ollama provider...')
    try {
      const modelName = resolvedModelName()
      for (const agentId of Array.from(selectedAgentIds)) {
        await api.assignOllamaInstanceToAgent(instId, { agent_id: agentId, model_name: modelName })
      }
      setPhase('done')
      setPhaseMessage('Setup complete!')
      if (instance && onComplete) onComplete(instance)
      // Auto-close after short delay
      setTimeout(() => handleClose(), 1200)
    } catch (e: any) {
      setPhase('error')
      setPhaseMessage(`Assigning to agents failed: ${e?.message || 'unknown error'}`)
    }
  }

  const handleRetry = () => {
    // Decide retry action based on what failed
    if (!instance) {
      // Retry from the top
      setPhase('idle')
      setStep(5)
      return
    }
    if (phase === 'error') {
      // Check container state first
      api.getOllamaContainerStatus(instance.id).then(s => {
        const state = (s?.status || '').toLowerCase()
        if (state === 'running') {
          startPull(instance.id)
        } else {
          setPhase('provision')
          setPhaseMessage('Retrying container provision...')
          api.provisionOllamaContainer(instance.id, config.gpu_enabled, config.mem_limit)
            .then(() => pollContainerStatus(instance.id))
            .catch((e: any) => {
              setPhase('error')
              setPhaseMessage(`Retry failed: ${e?.message || 'unknown error'}`)
            })
        }
      }).catch(() => {
        setPhase('provision')
        setPhaseMessage('Retrying container provision...')
        api.provisionOllamaContainer(instance.id, config.gpu_enabled, config.mem_limit)
          .then(() => pollContainerStatus(instance.id))
          .catch((e: any) => {
            setPhase('error')
            setPhaseMessage(`Retry failed: ${e?.message || 'unknown error'}`)
          })
      })
    }
  }

  const handleClose = () => {
    if (provisionPoller.current) { clearInterval(provisionPoller.current); provisionPoller.current = null }
    if (pullPoller.current) { clearInterval(pullPoller.current); pullPoller.current = null }
    onClose()
  }

  const totalSteps = 5
  const displayStep = step === 6 ? 5 : step

  const stepIndicator = (
    <div className="flex items-center justify-center gap-2 mb-5">
      {[1, 2, 3, 4, 5].map(n => (
        <div key={n} className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
            n === displayStep ? 'bg-purple-500 text-white' :
            n < displayStep ? 'bg-purple-500/20 text-purple-400' :
            'bg-white/5 text-gray-500'
          }`}>
            {n < displayStep ? '✓' : n}
          </div>
          {n < totalSteps && (
            <div className={`w-6 h-0.5 ${n < displayStep ? 'bg-purple-500/40' : 'bg-white/5'}`} />
          )}
        </div>
      ))}
    </div>
  )

  // ============================================================
  // STEP 1 — What is Ollama?
  // ============================================================
  if (step === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
          Cancel
        </button>
        <button
          onClick={() => setStep(2)}
          className="px-4 py-2 text-sm bg-purple-500 hover:bg-purple-400 text-white rounded-lg transition-colors"
        >
          Next: Configure Container →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Set up Ollama (Local LLM)" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">What is Ollama?</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              Ollama runs open-source LLMs (Llama 3.2, Qwen 2.5, DeepSeek R1, Phi, Mistral)
              locally in a Docker container. Your prompts and responses stay private
              (nothing sent to OpenAI/Anthropic/Google), and inference cost is $0
              beyond your electricity.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Cost</div>
              <div className="text-white">$0 per token</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">GPU</div>
              <div className="text-white">Optional (5–20× speedup)</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Image</div>
              <div className="text-white">~4 GB, pulled on demand</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Model size</div>
              <div className="text-white">1–7 GB each</div>
            </div>
          </div>

          <div className="text-xs text-gray-500 bg-purple-500/5 border border-purple-500/20 rounded-lg p-3">
            <span className="text-purple-400 font-medium">Best for:</span> private data,
            regulated industries (healthcare, legal, finance), offline/air-gapped deployments,
            and local dev/prototyping where you don't want to burn through API credits.
          </div>
        </div>
      </Modal>
    )
  }

  // ============================================================
  // STEP 2 — Configure container
  // ============================================================
  if (step === 2) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(1)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            ← Back
          </button>
          <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            Cancel
          </button>
        </div>
        <button
          onClick={() => setStep(3)}
          disabled={!config.instance_name.trim()}
          className="px-4 py-2 text-sm bg-purple-500 hover:bg-purple-400 text-white rounded-lg disabled:opacity-40 transition-colors"
        >
          Next: Choose Model →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Configure Container" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Instance name *</label>
            <input
              type="text"
              value={config.instance_name}
              onChange={e => setConfig({ ...config, instance_name: e.target.value })}
              placeholder="Ollama Local"
              className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-purple-500/50 focus:outline-none"
              autoFocus
            />
            <p className="text-[11px] text-gray-500 mt-1">
              Displayed in Hub and Agent Studio. You can rename it later.
            </p>
          </div>

          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.gpu_enabled}
                onChange={e => setConfig({ ...config, gpu_enabled: e.target.checked })}
                className="mt-0.5 rounded bg-[#0a0a0f] border-white/20 text-purple-500 focus:ring-purple-500"
              />
              <div>
                <span className="text-sm text-white font-medium">Enable GPU</span>
                <p className="text-[11px] text-gray-500 mt-0.5">
                  Requires NVIDIA Container Toolkit on the host. If unsupported, Ollama
                  will silently fall back to CPU — it just won't be as fast.
                </p>
              </div>
            </label>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Memory limit</label>
            <select
              value={config.mem_limit}
              onChange={e => setConfig({ ...config, mem_limit: e.target.value })}
              className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-purple-500/50 focus:outline-none"
            >
              {MEM_LIMITS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <p className="text-[11px] text-gray-500 mt-1">
              4 GB fits most 3B models comfortably. Bump up to 8 GB for 7B models.
            </p>
          </div>
        </div>
      </Modal>
    )
  }

  // ============================================================
  // STEP 3 — Choose model
  // ============================================================
  if (step === 3) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(2)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            ← Back
          </button>
          <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            Cancel
          </button>
        </div>
        <button
          onClick={() => setStep(4)}
          disabled={!isModelValid()}
          className="px-4 py-2 text-sm bg-purple-500 hover:bg-purple-400 text-white rounded-lg disabled:opacity-40 transition-colors"
        >
          Next: Link Agents →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Choose a Model" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <p className="text-sm text-gray-400">
            Pick the model you'll use most often. We'll pull it during setup; you can
            add more models later from the Ollama panel in Hub.
          </p>

          <div className="space-y-1.5 max-h-80 overflow-y-auto pr-1">
            {OLLAMA_CURATED_MODELS.map(m => (
              <label
                key={m.id}
                className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-colors border ${
                  config.model_choice === m.id
                    ? 'bg-purple-500/10 border-purple-500/40'
                    : 'bg-white/[0.02] border-white/5 hover:bg-white/5'
                }`}
              >
                <input
                  type="radio"
                  name="ollama-model"
                  checked={config.model_choice === m.id}
                  onChange={() => setConfig({ ...config, model_choice: m.id })}
                  className="mt-1 accent-purple-500"
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm text-white font-mono">{m.id}</div>
                    <div className="text-[11px] text-gray-500 shrink-0">{m.params} · {m.disk}</div>
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5">{m.summary}</div>
                </div>
              </label>
            ))}

            <label
              className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-colors border ${
                config.model_choice === 'custom'
                  ? 'bg-purple-500/10 border-purple-500/40'
                  : 'bg-white/[0.02] border-white/5 hover:bg-white/5'
              }`}
            >
              <input
                type="radio"
                name="ollama-model"
                checked={config.model_choice === 'custom'}
                onChange={() => setConfig({ ...config, model_choice: 'custom' })}
                className="mt-1 accent-purple-500"
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-white">Custom model</div>
                <div className="text-xs text-gray-400 mt-0.5">
                  Enter any Ollama tag (e.g. <span className="font-mono">namespace/model:tag</span>)
                </div>
                {config.model_choice === 'custom' && (
                  <input
                    type="text"
                    value={config.custom_model}
                    onChange={e => setConfig({ ...config, custom_model: e.target.value })}
                    placeholder="e.g. llama3.2:8b-instruct-q4_K_M"
                    className="w-full mt-2 px-2.5 py-1.5 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-xs font-mono focus:border-purple-500/50 focus:outline-none"
                    onClick={e => e.stopPropagation()}
                  />
                )}
              </div>
            </label>
          </div>
        </div>
      </Modal>
    )
  }

  // ============================================================
  // STEP 4 — Link to Agent(s)
  // ============================================================
  if (step === 4) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(3)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            ← Back
          </button>
          <button onClick={() => { setSelectedAgentIds(new Set()); setStep(5) }} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            Skip this step
          </button>
        </div>
        <button
          onClick={() => setStep(5)}
          className="px-4 py-2 text-sm bg-purple-500 hover:bg-purple-400 text-white rounded-lg transition-colors"
        >
          Next: Review →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Link Ollama to Agents" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <div>
            <p className="text-sm text-gray-300 leading-relaxed">
              Select agents that should use this Ollama instance. Their LLM backend will
              switch to Ollama with the model <span className="font-mono text-purple-300">{resolvedModelName() || '—'}</span>.
            </p>
            <p className="text-xs text-gray-500 mt-2">
              Skip to just provision the container — agents can be rewired later from Agent Studio.
            </p>
          </div>

          {agentsLoading ? (
            <div className="text-center py-8 text-sm text-gray-500">Loading agents...</div>
          ) : agents.length === 0 ? (
            <div className="text-center py-6 text-sm text-gray-500 border border-white/5 rounded-lg bg-white/[0.02]">
              No active agents in this tenant. You can create one later and rewire it.
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">
                  {selectedAgentIds.size} of {agents.length} agent{agents.length !== 1 ? 's' : ''} selected
                </span>
                <button
                  onClick={() => {
                    if (selectedAgentIds.size === agents.length) {
                      setSelectedAgentIds(new Set())
                    } else {
                      setSelectedAgentIds(new Set(agents.map(a => a.id)))
                    }
                  }}
                  className="text-xs text-purple-400 hover:text-purple-300"
                >
                  {selectedAgentIds.size === agents.length ? 'Clear all' : 'Select all'}
                </button>
              </div>
              <div className="max-h-64 overflow-y-auto space-y-1 border border-white/10 rounded-lg p-3 bg-white/[0.02]">
                {agents.map(agent => (
                  <label
                    key={agent.id}
                    className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-white/5 cursor-pointer transition-colors"
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
                      className="w-4 h-4 rounded border-white/20 text-purple-500 focus:ring-purple-500 bg-[#0a0a0f]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{agent.contact_name}</div>
                      <div className="text-xs text-gray-500">
                        Current: {agent.model_provider}/{agent.model_name}
                      </div>
                    </div>
                    {agent.is_default && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-500/20 text-teal-400 shrink-0">
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

  // ============================================================
  // STEP 5 — Review & Provision
  // ============================================================
  if (step === 5) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(4)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
          ← Back
        </button>
        <button
          onClick={startProvision}
          className="px-4 py-2 text-sm bg-purple-500 hover:bg-purple-400 text-white rounded-lg transition-colors"
        >
          Provision & Pull →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Review & Provision" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          {error && (
            <div className="px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-3">
            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Container</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-gray-400">Name</div>
                <div className="text-white font-medium">{config.instance_name}</div>
                <div className="text-gray-400">GPU</div>
                <div className="text-white">{config.gpu_enabled ? 'Enabled' : 'CPU only'}</div>
                <div className="text-gray-400">Memory</div>
                <div className="text-white">{config.mem_limit}</div>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Model</div>
              <div className="text-sm text-white font-mono">{resolvedModelName()}</div>
            </div>

            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Agent Assignments</div>
              {selectedAgentIds.size === 0 ? (
                <div className="text-sm text-gray-400">None — you'll wire up agents later.</div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {Array.from(selectedAgentIds).map(id => {
                    const a = agents.find(x => x.id === id)
                    return (
                      <span key={id} className="text-xs px-2 py-1 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-300">
                        {a?.contact_name || `Agent #${id}`}
                      </span>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="text-xs text-gray-500 bg-purple-500/5 border border-purple-500/20 rounded-lg p-3">
            <span className="text-purple-400 font-medium">What happens next:</span>{' '}
            (1) create/reuse the Ollama provider instance, (2) pull the Ollama image (~4 GB
            on first run), (3) pull the model (takes a few minutes), (4) rewire selected agents.
            You can safely close this dialog — provisioning continues in the background.
          </div>
        </div>
      </Modal>
    )
  }

  // ============================================================
  // STEP 6 — Progress
  // ============================================================
  const provisionDone = phase !== 'provision' && phase !== 'idle'
  const pullDone = phase === 'assign' || phase === 'done'
  const assignDone = phase === 'done'

  const progressFooter = (
    <div className="flex items-center justify-between w-full">
      <button
        onClick={handleClose}
        className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
      >
        {phase === 'error' || phase === 'done' ? 'Close' : 'Dismiss (continues in background)'}
      </button>
      {phase === 'error' && (
        <button
          onClick={handleRetry}
          className="px-4 py-2 text-sm bg-purple-500 hover:bg-purple-400 text-white rounded-lg transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  )

  const Stage = ({ done, active, label }: { done: boolean; active: boolean; label: string }) => (
    <div className="flex items-center gap-3 py-2">
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium shrink-0 ${
        done ? 'bg-emerald-500/20 text-emerald-400' :
        active ? 'bg-purple-500 text-white' :
        'bg-white/5 text-gray-500'
      }`}>
        {done ? '✓' : active ? <span className="animate-pulse">●</span> : '○'}
      </div>
      <span className={`text-sm ${done ? 'text-emerald-300' : active ? 'text-white' : 'text-gray-500'}`}>
        {label}
      </span>
    </div>
  )

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Provisioning Ollama..." footer={progressFooter} size="lg">
      <div className="space-y-5">
        {stepIndicator}

        <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
          <Stage done={provisionDone} active={phase === 'provision'} label="Provisioning container" />
          <Stage done={pullDone} active={phase === 'pull'} label={`Pulling model ${resolvedModelName()}`} />
          <Stage done={assignDone} active={phase === 'assign'} label="Assigning to agents" />
        </div>

        {phase === 'pull' && (
          <div>
            <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden">
              <div
                className="h-full bg-purple-400 transition-all"
                style={{ width: `${pullPercent}%` }}
              />
            </div>
            <div className="text-[11px] text-gray-500 mt-1 text-right">{pullPercent}%</div>
          </div>
        )}

        <div className="text-center py-4">
          {phase === 'error' ? (
            <>
              <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center mx-auto mb-3">
                <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <p className="text-sm text-red-300">{phaseMessage}</p>
            </>
          ) : phase === 'done' ? (
            <>
              <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center mx-auto mb-3">
                <svg className="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-sm text-emerald-300">{phaseMessage}</p>
            </>
          ) : (
            <p className="text-sm text-gray-400">{phaseMessage}</p>
          )}
        </div>
      </div>
    </Modal>
  )
}
