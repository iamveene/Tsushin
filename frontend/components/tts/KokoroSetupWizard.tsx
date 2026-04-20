'use client'

import { useState, useEffect, useRef } from 'react'
import Modal from '@/components/ui/Modal'
import { api, Agent, TTSInstance } from '@/lib/client'

interface KokoroSetupWizardProps {
  isOpen: boolean
  onClose: () => void
  onComplete?: (instance: TTSInstance) => void
}

type Step = 1 | 2 | 3 | 4 | 5  // 5 = provisioning progress

interface WizardConfig {
  instance_name: string
  auto_provision: boolean
  mem_limit: string
  default_voice: string
  default_language: string
  default_speed: number
  default_format: string
  is_default: boolean
}

const DEFAULT_CONFIG: WizardConfig = {
  instance_name: 'Kokoro TTS',
  auto_provision: true,
  mem_limit: '1.5g',
  default_voice: 'pf_dora',
  default_language: 'pt',
  default_speed: 1.0,
  default_format: 'opus',
  is_default: true,
}

// Curated list of Kokoro voices (mirrors backend/hub/providers/kokoro_tts_provider.py)
const KOKORO_VOICES: { id: string; label: string; lang: string; gender: string }[] = [
  { id: 'pf_dora',   label: 'Dora — Brazilian PT (female)',   lang: 'pt', gender: 'female' },
  { id: 'pm_alex',   label: 'Alex — Brazilian PT (male)',     lang: 'pt', gender: 'male' },
  { id: 'pm_santa',  label: 'Santa — Brazilian PT (male)',    lang: 'pt', gender: 'male' },
  { id: 'af_bella',  label: 'Bella — American EN (female)',   lang: 'en', gender: 'female' },
  { id: 'af_sarah',  label: 'Sarah — American EN (female)',   lang: 'en', gender: 'female' },
  { id: 'af_nicole', label: 'Nicole — American EN (female)',  lang: 'en', gender: 'female' },
  { id: 'af_sky',    label: 'Sky — American EN (female)',     lang: 'en', gender: 'female' },
  { id: 'am_adam',   label: 'Adam — American EN (male)',      lang: 'en', gender: 'male' },
  { id: 'am_michael', label: 'Michael — American EN (male)',  lang: 'en', gender: 'male' },
  { id: 'bf_emma',   label: 'Emma — British EN (female)',     lang: 'en', gender: 'female' },
  { id: 'bf_alice',  label: 'Alice — British EN (female)',    lang: 'en', gender: 'female' },
  { id: 'bm_george', label: 'George — British EN (male)',     lang: 'en', gender: 'male' },
  { id: 'bm_daniel', label: 'Daniel — British EN (male)',     lang: 'en', gender: 'male' },
  { id: 'bm_lewis',  label: 'Lewis — British EN (male)',      lang: 'en', gender: 'male' },
]

const LANGUAGES = [
  { value: 'pt', label: 'Portuguese (pt)' },
  { value: 'en', label: 'English (en)' },
]

const FORMATS = [
  { value: 'opus', label: 'Opus (recommended)' },
  { value: 'mp3',  label: 'MP3' },
  { value: 'wav',  label: 'WAV' },
]

const MEM_LIMITS = ['1g', '1.5g', '2g']

export default function KokoroSetupWizard({ isOpen, onClose, onComplete }: KokoroSetupWizardProps) {
  const [step, setStep] = useState<Step>(1)
  const [config, setConfig] = useState<WizardConfig>(DEFAULT_CONFIG)
  const [agents, setAgents] = useState<Agent[]>([])
  const [agentsLoading, setAgentsLoading] = useState(false)
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<number>>(new Set())
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createdInstance, setCreatedInstance] = useState<TTSInstance | null>(null)
  const [provisionStatus, setProvisionStatus] = useState<'provisioning' | 'running' | 'error' | null>(null)
  const [provisionMessage, setProvisionMessage] = useState<string>('Starting container...')
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  // Reset when opened
  useEffect(() => {
    if (!isOpen) return
    setStep(1)
    setConfig(DEFAULT_CONFIG)
    setAgents([])
    setSelectedAgentIds(new Set())
    setCreating(false)
    setError(null)
    setCreatedInstance(null)
    setProvisionStatus(null)
    setProvisionMessage('Starting container...')
  }, [isOpen])

  // Load agents when entering step 3
  useEffect(() => {
    if (step !== 3 || agents.length > 0) return
    setAgentsLoading(true)
    api.getAgents(true)
      .then(setAgents)
      .catch(() => setAgents([]))
      .finally(() => setAgentsLoading(false))
  }, [step])

  // Cleanup poll on unmount / close
  useEffect(() => {
    return () => {
      if (pollTimer.current) {
        clearInterval(pollTimer.current)
        pollTimer.current = null
      }
    }
  }, [])

  // Keyboard: Enter to advance on steps 1-4
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => {
      if (e.key !== 'Enter') return
      // Don't intercept when user is in a textarea/select or shift-enter
      const target = e.target as HTMLElement | null
      if (target && (target.tagName === 'TEXTAREA' || target.tagName === 'SELECT')) return
      if (e.shiftKey) return
      if (step === 1) { e.preventDefault(); setStep(2) }
      else if (step === 2 && config.instance_name.trim()) { e.preventDefault(); setStep(3) }
      else if (step === 3) { e.preventDefault(); setStep(4) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, step, config.instance_name])

  const pollContainerStatus = (instanceId: number) => {
    if (pollTimer.current) clearInterval(pollTimer.current)
    let ticks = 0
    pollTimer.current = setInterval(async () => {
      ticks++
      try {
        const status = await api.getTTSContainerStatus(instanceId)
        const state = (status?.status || '').toLowerCase()
        if (state === 'running') {
          if (pollTimer.current) clearInterval(pollTimer.current)
          pollTimer.current = null
          setProvisionStatus('running')
          setProvisionMessage('Container running — assigning to agents...')
          // Kick off agent assignments
          await assignAgentsAndFinish(instanceId)
        } else if (state === 'error') {
          if (pollTimer.current) clearInterval(pollTimer.current)
          pollTimer.current = null
          setProvisionStatus('error')
          setProvisionMessage('Container failed to start. Check Hub > Local Services logs for details.')
        } else if (state === 'creating' || state === 'provisioning') {
          setProvisionMessage('Pulling image and starting container (30–90s)...')
        } else if (state === 'stopped') {
          setProvisionMessage('Container stopped unexpectedly — retrying status...')
        }
      } catch {
        // Transient, keep polling
      }
      if (ticks > 120) {  // ~6 min cap
        if (pollTimer.current) clearInterval(pollTimer.current)
        pollTimer.current = null
        setProvisionStatus('error')
        setProvisionMessage('Provisioning timed out after 6 minutes. Check Hub > Local Services.')
      }
    }, 3000)
  }

  const assignAgentsAndFinish = async (instanceId: number) => {
    try {
      for (const agentId of Array.from(selectedAgentIds)) {
        await api.assignTTSInstanceToAgent(instanceId, {
          agent_id: agentId,
          voice: config.default_voice,
          speed: config.default_speed,
          language: config.default_language,
          response_format: config.default_format,
        })
      }
      if (onComplete && createdInstance) onComplete(createdInstance)
      handleClose()
    } catch (e: any) {
      setProvisionStatus('error')
      setProvisionMessage(`Assigning to agents failed: ${e?.message || 'unknown error'}`)
    }
  }

  const handleCreate = async () => {
    if (!config.instance_name.trim()) {
      setError('Instance name is required')
      return
    }
    setCreating(true)
    setError(null)
    try {
      const created = await api.createTTSInstance({
        vendor: 'kokoro',
        instance_name: config.instance_name.trim(),
        auto_provision: config.auto_provision,
        mem_limit: config.auto_provision ? config.mem_limit : undefined,
        default_voice: config.default_voice,
        default_language: config.default_language,
        default_speed: config.default_speed,
        default_format: config.default_format,
        is_default: config.is_default,
      })
      setCreatedInstance(created)

      // Apply as default if requested (createTTSInstance accepts is_default, but
      // the backend may only honor it on create — explicit is safer)
      if (config.is_default && created.id) {
        try { await api.setDefaultTTSInstance(created.id) } catch { /* non-fatal */ }
      }

      // If auto-provision, enter progress step and poll
      if (config.auto_provision) {
        setStep(5)
        setProvisionStatus('provisioning')
        setProvisionMessage('Starting Kokoro container...')
        pollContainerStatus(created.id)
      } else {
        // No provisioning — go straight to assigning agents
        setStep(5)
        setProvisionStatus('running')
        setProvisionMessage('Instance ready — assigning to agents...')
        await assignAgentsAndFinish(created.id)
      }
    } catch (e: any) {
      setError(e?.message || 'Failed to create Kokoro instance')
    } finally {
      setCreating(false)
    }
  }

  const handleRetry = () => {
    if (!createdInstance) {
      // Retry from step 4
      setStep(4)
      setProvisionStatus(null)
      setError(null)
      return
    }
    // Re-provision: try starting container again
    setProvisionStatus('provisioning')
    setProvisionMessage('Retrying container start...')
    api.ttsContainerAction(createdInstance.id, 'start')
      .then(() => pollContainerStatus(createdInstance.id))
      .catch((e: any) => {
        setProvisionStatus('error')
        setProvisionMessage(`Retry failed: ${e?.message || 'unknown error'}`)
      })
  }

  const handleClose = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
    onClose()
  }

  const totalSteps = 4
  const displayStep = step === 5 ? 4 : step  // collapse progress into step 4 indicator

  const stepIndicator = (
    <div className="flex items-center justify-center gap-2 mb-5">
      {[1, 2, 3, 4].map(n => (
        <div key={n} className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
            n === displayStep ? 'bg-teal-500 text-white' :
            n < displayStep ? 'bg-teal-500/20 text-teal-400' :
            'bg-white/5 text-gray-500'
          }`}>
            {n < displayStep ? '✓' : n}
          </div>
          {n < totalSteps && (
            <div className={`w-8 h-0.5 ${n < displayStep ? 'bg-teal-500/40' : 'bg-white/5'}`} />
          )}
        </div>
      ))}
    </div>
  )

  // ============================================================
  // STEP 1 — What is Kokoro TTS?
  // ============================================================
  if (step === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
          Cancel
        </button>
        <button
          onClick={() => setStep(2)}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors"
        >
          Next: Configure →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Set up Kokoro TTS" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <div>
            <h3 className="text-lg font-semibold text-white mb-2">What is Kokoro TTS?</h3>
            <p className="text-sm text-gray-300 leading-relaxed">
              Kokoro is an open-source, local text-to-speech engine. It runs inside your
              Tsushin stack as a dedicated Docker container per tenant, so your audio
              stays private (never leaves your infrastructure) and there's no
              per-character cost. Great for voice responses in WhatsApp and phone flows.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Languages</div>
              <div className="text-white">Portuguese, English</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Voices</div>
              <div className="text-white">14+ neural voices</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Cost</div>
              <div className="text-white">$0 (runs on your hardware)</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-1">Image size</div>
              <div className="text-white">~500 MB (pulled on demand)</div>
            </div>
          </div>

          <div className="text-xs text-gray-500 bg-teal-500/5 border border-teal-500/20 rounded-lg p-3">
            <span className="text-teal-400 font-medium">CPU-friendly:</span> no GPU required.
            Kokoro runs comfortably on a single CPU container with 1.5 GB of RAM.
          </div>
        </div>
      </Modal>
    )
  }

  // ============================================================
  // STEP 2 — Configure
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
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg disabled:opacity-40 transition-colors"
        >
          Next: Link Agents →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Configure Kokoro Instance" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">Instance name *</label>
            <input
              type="text"
              value={config.instance_name}
              onChange={e => setConfig({ ...config, instance_name: e.target.value })}
              placeholder="Kokoro TTS"
              className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
              autoFocus
            />
          </div>

          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.auto_provision}
                onChange={e => setConfig({ ...config, auto_provision: e.target.checked })}
                className="rounded bg-[#0a0a0f] border-white/20 text-teal-500 focus:ring-teal-500"
              />
              <span className="text-sm text-white font-medium">Auto-provision container</span>
            </label>
            <p className="text-xs text-gray-500 mt-1 ml-6">
              {config.auto_provision
                ? 'Tsushin will spin up a dedicated Kokoro container for this tenant.'
                : 'You will point at an existing Kokoro endpoint you manage (advanced).'}
            </p>
          </div>

          {config.auto_provision && (
            <div>
              <label className="block text-xs font-medium text-gray-300 mb-1.5">Memory limit</label>
              <select
                value={config.mem_limit}
                onChange={e => setConfig({ ...config, mem_limit: e.target.value })}
                className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
              >
                {MEM_LIMITS.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <p className="text-[11px] text-gray-500 mt-1">1.5g is the sweet spot — raise only if you see OOM kills.</p>
            </div>
          )}

          <div className="pt-3 border-t border-white/5">
            <h4 className="text-xs font-semibold text-gray-300 uppercase tracking-wider mb-3">Voice Defaults</h4>
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-300 mb-1.5">Default voice</label>
                <select
                  value={config.default_voice}
                  onChange={e => {
                    const v = KOKORO_VOICES.find(x => x.id === e.target.value)
                    setConfig({
                      ...config,
                      default_voice: e.target.value,
                      // Auto-sync language based on voice if available
                      default_language: v?.lang || config.default_language,
                    })
                  }}
                  className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none font-mono"
                >
                  {KOKORO_VOICES.map(v => (
                    <option key={v.id} value={v.id}>{v.id} — {v.label}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1.5">
                  Speed: {config.default_speed.toFixed(2)}×
                </label>
                <input
                  type="range"
                  min={0.5}
                  max={2.0}
                  step={0.05}
                  value={config.default_speed}
                  onChange={e => setConfig({ ...config, default_speed: parseFloat(e.target.value) })}
                  className="w-full accent-teal-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-300 mb-1.5">Language</label>
                <select
                  value={config.default_language}
                  onChange={e => setConfig({ ...config, default_language: e.target.value })}
                  className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
                >
                  {LANGUAGES.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
              </div>

              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-300 mb-1.5">Audio format</label>
                <select
                  value={config.default_format}
                  onChange={e => setConfig({ ...config, default_format: e.target.value })}
                  className="w-full px-3 py-2 border border-white/10 rounded-lg text-white bg-[#0a0a0f] text-sm focus:border-teal-500/50 focus:outline-none"
                >
                  {FORMATS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
                </select>
              </div>
            </div>
          </div>

          <div className="pt-3 border-t border-white/5">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.is_default}
                onChange={e => setConfig({ ...config, is_default: e.target.checked })}
                className="rounded bg-[#0a0a0f] border-white/20 text-teal-500 focus:ring-teal-500"
              />
              <span className="text-sm text-white">Set as tenant default TTS</span>
            </label>
            <p className="text-[11px] text-gray-500 mt-1 ml-6">
              All agents without a per-agent override will use this instance.
            </p>
          </div>
        </div>
      </Modal>
    )
  }

  // ============================================================
  // STEP 3 — Link to Agent(s)
  // ============================================================
  if (step === 3) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <div className="flex items-center gap-2">
          <button onClick={() => setStep(2)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            ← Back
          </button>
          <button onClick={() => { setSelectedAgentIds(new Set()); setStep(4) }} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">
            Skip this step
          </button>
        </div>
        <button
          onClick={() => setStep(4)}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors"
        >
          Next: Review →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Link Kokoro to Agents" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          <div>
            <p className="text-sm text-gray-300 leading-relaxed">
              Select agents that should use this Kokoro instance. The <span className="text-teal-400">Audio Response</span> skill
              will be enabled automatically on each selected agent — they'll start replying with audio
              using the voice you picked above.
            </p>
            <p className="text-xs text-gray-500 mt-2">
              Skip this if you just want to create the instance — you can link agents later from Agent Studio.
            </p>
          </div>

          {agentsLoading ? (
            <div className="text-center py-8 text-sm text-gray-500">Loading agents...</div>
          ) : agents.length === 0 ? (
            <div className="text-center py-6 text-sm text-gray-500 border border-white/5 rounded-lg bg-white/[0.02]">
              No active agents in this tenant. You can create one later and come back to wire it up.
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
                  className="text-xs text-teal-400 hover:text-teal-300"
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
                      className="w-4 h-4 rounded border-white/20 text-teal-500 focus:ring-teal-500 bg-[#0a0a0f]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-white truncate">{agent.contact_name}</div>
                      <div className="text-xs text-gray-500">{agent.model_provider}/{agent.model_name}</div>
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
  // STEP 4 — Review & Create
  // ============================================================
  if (step === 4) {
    const selectedVoice = KOKORO_VOICES.find(v => v.id === config.default_voice)
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(3)} disabled={creating} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors disabled:opacity-40">
          ← Back
        </button>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg disabled:opacity-40 transition-colors"
        >
          {creating ? 'Creating...' : (config.auto_provision ? 'Create & Provision' : 'Create Instance')}
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={handleClose} title="Review & Create" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}

          {error && (
            <div className="px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          <div className="space-y-3">
            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Instance</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-gray-400">Name</div>
                <div className="text-white font-medium">{config.instance_name}</div>
                <div className="text-gray-400">Mode</div>
                <div className="text-white">{config.auto_provision ? `Auto-provision (${config.mem_limit})` : 'External endpoint'}</div>
                <div className="text-gray-400">Set as default</div>
                <div className="text-white">{config.is_default ? 'Yes' : 'No'}</div>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Voice Defaults</div>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-gray-400">Voice</div>
                <div className="text-white font-mono">{config.default_voice}{selectedVoice ? ` (${selectedVoice.label})` : ''}</div>
                <div className="text-gray-400">Language</div>
                <div className="text-white">{config.default_language}</div>
                <div className="text-gray-400">Speed</div>
                <div className="text-white">{config.default_speed.toFixed(2)}×</div>
                <div className="text-gray-400">Format</div>
                <div className="text-white">{config.default_format}</div>
              </div>
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
                      <span key={id} className="text-xs px-2 py-1 rounded-full bg-teal-500/10 border border-teal-500/20 text-teal-300">
                        {a?.contact_name || `Agent #${id}`}
                      </span>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          {config.auto_provision && (
            <div className="text-xs text-gray-500 bg-teal-500/5 border border-teal-500/20 rounded-lg p-3">
              <span className="text-teal-400 font-medium">What happens next:</span> we'll create
              the DB record, start pulling the Kokoro image (~500 MB), and launch the container.
              Takes 30–90 seconds on first run; subsequent restarts are instant.
            </div>
          )}
        </div>
      </Modal>
    )
  }

  // ============================================================
  // STEP 5 — Provisioning progress
  // ============================================================
  const progressFooter = (
    <div className="flex items-center justify-between w-full">
      <button
        onClick={handleClose}
        className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
      >
        {provisionStatus === 'error' ? 'Close' : 'Dismiss (continues in background)'}
      </button>
      {provisionStatus === 'error' && (
        <button
          onClick={handleRetry}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  )

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Provisioning Kokoro..." footer={progressFooter} size="lg">
      <div className="space-y-5">
        {stepIndicator}

        <div className="py-6 text-center">
          {provisionStatus === 'provisioning' && (
            <>
              <div className="inline-block animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-teal-400 mb-4" />
              <h3 className="text-lg font-semibold text-white mb-2">Setting up your Kokoro instance</h3>
              <p className="text-sm text-gray-400">{provisionMessage}</p>
            </>
          )}

          {provisionStatus === 'running' && (
            <>
              <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center mx-auto mb-4">
                <svg className="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">Kokoro is running</h3>
              <p className="text-sm text-gray-400">{provisionMessage}</p>
            </>
          )}

          {provisionStatus === 'error' && (
            <>
              <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center mx-auto mb-4">
                <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-white mb-2">Provisioning failed</h3>
              <p className="text-sm text-red-300">{provisionMessage}</p>
            </>
          )}
        </div>
      </div>
    </Modal>
  )
}
