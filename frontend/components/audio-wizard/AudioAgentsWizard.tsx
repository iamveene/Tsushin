'use client'

import { useState, useEffect } from 'react'
import Modal from '@/components/ui/Modal'
import { api } from '@/lib/client'
import type { Agent, TTSInstance, TTSProviderInfo, ProviderInstance } from '@/lib/client'
import type { AudioWizardOpenOptions, AudioAgentType } from '@/contexts/AudioWizardContext'
import {
  VOICE_AGENT_DEFAULTS,
  TRANSCRIPT_AGENT_DEFAULTS,
  type AudioProvider,
} from './defaults'
import { AudioProviderPicker, AudioVoiceFields } from './AudioProviderFields'
import { useKokoroPolling } from '@/components/agent-wizard/hooks/useKokoroPolling'

interface AudioAgentsWizardProps {
  isOpen: boolean
  onClose: () => void
  onComplete: () => void
  options: AudioWizardOpenOptions
}

type Step = 1 | 2 | 3 | 4 | 5 | 6  // 6 = provisioning progress

interface WizardState {
  agentType: AudioAgentType
  provider: AudioProvider
  // provider config
  voice: string
  language: string
  speed: number
  format: string
  // Kokoro-only
  memLimit: string
  autoProvision: boolean
  // OpenAI/ElevenLabs
  providerInstanceId: number | null
  // agent target
  mode: 'new' | 'existing'
  existingAgentId: number | null
  newAgentName: string
  setAsDefaultTTS: boolean
}

function makeInitialState(opts: AudioWizardOpenOptions): WizardState {
  const provider: AudioProvider = opts.presetProvider || 'kokoro'
  return {
    agentType: opts.presetAgentType || 'voice',
    provider,
    voice: provider === 'kokoro' ? 'pf_dora' : 'nova',
    language: 'pt',
    speed: 1.0,
    format: 'opus',
    memLimit: '1.5g',
    autoProvision: true,
    providerInstanceId: null,
    mode: opts.presetMode || 'new',
    existingAgentId: opts.presetAgentId ?? null,
    newAgentName: opts.presetNewAgentName || VOICE_AGENT_DEFAULTS.kokoro.name,
    setAsDefaultTTS: false,
  }
}

export default function AudioAgentsWizard({ isOpen, onClose, onComplete, options }: AudioAgentsWizardProps) {
  const [step, setStep] = useState<Step>(1)
  const [state, setState] = useState<WizardState>(() => makeInitialState(options))
  const [providers, setProviders] = useState<TTSProviderInfo[]>([])
  const [existingTTSInstances, setExistingTTSInstances] = useState<TTSInstance[]>([])
  const [providerInstances, setProviderInstances] = useState<ProviderInstance[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [createdInstance, setCreatedInstance] = useState<TTSInstance | null>(null)
  const [createdAgentId, setCreatedAgentId] = useState<number | null>(null)
  const [progressStatus, setProgressStatus] = useState<'provisioning' | 'running' | 'error' | 'done' | null>(null)
  const [progressMessage, setProgressMessage] = useState('Starting...')
  const { poll: pollKokoro, cancel: cancelKokoroPolling } = useKokoroPolling()

  // Reset on open
  useEffect(() => {
    if (!isOpen) return
    setStep(1)
    setState(makeInitialState(options))
    setError(null)
    setCreatedInstance(null)
    setCreatedAgentId(null)
    setProgressStatus(null)
    setProgressMessage('Starting...')
  }, [isOpen, options])

  // Load provider + agent metadata once open
  useEffect(() => {
    if (!isOpen) return
    Promise.all([
      api.getTTSProviders().catch(() => []),
      api.getTTSInstances().catch(() => []),
      api.getProviderInstances().catch(() => []),
      api.getAgents(true).catch(() => []),
    ]).then(([p, tts, provInst, ag]) => {
      setProviders(p)
      setExistingTTSInstances(tts)
      setProviderInstances(provInst)
      setAgents(ag)
      // Prefill providerInstanceId when entering with preset provider
      if (options.presetProvider === 'openai' || options.presetProvider === 'elevenlabs') {
        const match = provInst.find(i => i.vendor === options.presetProvider && i.api_key_configured)
        if (match) setState(s => ({ ...s, providerInstanceId: match.id }))
      }
    })
  }, [isOpen, options.presetProvider])

  const close = () => {
    cancelKokoroPolling()
    onClose()
  }

  // -------------------- Detection helpers --------------------
  const kokoroRunning = existingTTSInstances.find(t => t.vendor === 'kokoro' && t.is_active)
  const hasOpenAIKey = providerInstances.some(p => p.vendor === 'openai' && p.api_key_configured)
  const hasElevenLabsKey = providerInstances.some(p => p.vendor === 'elevenlabs' && p.api_key_configured)
  const hasGeminiKey = providerInstances.some(p => p.vendor === 'gemini' && p.api_key_configured)

  // -------------------- Step indicator --------------------
  const totalSteps = 5
  const displayStep = step === 6 ? 5 : step

  const stepIndicator = (
    <div className="flex items-center justify-center gap-2 mb-5">
      {[1, 2, 3, 4, 5].map(n => (
        <div key={n} className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
            n === displayStep ? 'bg-teal-500 text-white' :
            n < displayStep ? 'bg-teal-500/20 text-teal-400' :
            'bg-white/5 text-gray-500'
          }`}>
            {n < displayStep ? '✓' : n}
          </div>
          {n < totalSteps && <div className={`w-8 h-0.5 ${n < displayStep ? 'bg-teal-500/40' : 'bg-white/5'}`} />}
        </div>
      ))}
    </div>
  )

  // -------------------- Provisioning orchestration --------------------
  const finish = (message = 'All set! Your audio agent is ready.') => {
    setProgressStatus('done')
    setProgressMessage(message)
    onComplete()
  }

  const wireAudioSkills = async (agentId: number, ttsInstanceId: number | null) => {
    const wantsTTS = state.agentType === 'voice' || state.agentType === 'hybrid'
    const wantsTranscript = state.agentType === 'transcript' || state.agentType === 'hybrid'

    if (wantsTTS) {
      // Kokoro path: use assign-to-agent endpoint (handles skill + instance link)
      if (state.provider === 'kokoro' && ttsInstanceId) {
        await api.assignTTSInstanceToAgent(ttsInstanceId, {
          agent_id: agentId,
          voice: state.voice,
          speed: state.speed,
          language: state.language,
          response_format: state.format,
        })
      } else {
        // OpenAI / ElevenLabs / Gemini: set skill config directly (no TTSInstance)
        await api.updateAgentSkill(agentId, 'audio_tts', {
          is_enabled: true,
          config: {
            provider: state.provider,
            voice: state.voice,
            language: state.language,
            speed: state.speed,
            response_format: state.format,
          },
        })
      }
    }

    if (wantsTranscript) {
      await api.updateAgentSkill(agentId, 'audio_transcript', {
        is_enabled: true,
        config: {
          response_mode: state.agentType === 'transcript' ? 'transcript_only' : 'conversational',
          language: state.language,
        },
      })
    }
  }

  const createNewVoiceAgent = async (): Promise<number> => {
    const defaults = state.agentType === 'transcript'
      ? TRANSCRIPT_AGENT_DEFAULTS
      : VOICE_AGENT_DEFAULTS[state.provider]
    const name = state.newAgentName.trim() || defaults.name

    // 1. Create Contact (role=agent)
    const contact = await api.createContact({
      friendly_name: name,
      role: 'agent',
      is_active: true,
      notes: defaults.description,
    })

    // 2. Create Agent — pick a sensible model vendor from configured provider instances
    const defaultVendorInstance = providerInstances.find(p => p.is_default) || providerInstances[0]
    if (!defaultVendorInstance) {
      throw new Error('No AI provider configured. Set up a provider in Hub → AI Providers first.')
    }
    const agent = await api.createAgent({
      contact_id: contact.id,
      system_prompt: defaults.system_prompt,
      keywords: defaults.keywords,
      model_provider: defaultVendorInstance.vendor,
      model_name: defaultVendorInstance.available_models[0] || 'gemini-2.5-flash',
      is_active: true,
    })

    // 3. Update agent with channel/memory/response_template defaults
    try {
      await api.updateAgent(agent.id, {
        memory_size: defaults.memory_size,
        response_template: defaults.response_template,
        enabled_channels: defaults.channels,
      })
    } catch { /* non-fatal */ }

    return agent.id
  }

  const pollKokoroContainer = (instanceId: number, onReady: () => void) => {
    pollKokoro(instanceId, {
      onReady,
      onError: (msg) => {
        setProgressStatus('error')
        setProgressMessage(msg)
      },
      onProgress: (msg) => setProgressMessage(msg),
    })
  }

  const handleFinalize = async () => {
    setLoading(true)
    setError(null)
    setStep(6)
    setProgressStatus('provisioning')
    setProgressMessage('Preparing your audio agent...')

    try {
      // 1. Ensure TTS infrastructure
      let ttsInstanceId: number | null = null
      const wantsTTS = state.agentType === 'voice' || state.agentType === 'hybrid'

      if (wantsTTS && state.provider === 'kokoro') {
        setProgressMessage('Creating Kokoro TTS instance...')
        // Reuse existing if present, else create new
        if (kokoroRunning) {
          ttsInstanceId = kokoroRunning.id
        } else {
          const inst = await api.createTTSInstance({
            vendor: 'kokoro',
            instance_name: 'Kokoro TTS',
            auto_provision: state.autoProvision,
            mem_limit: state.autoProvision ? state.memLimit : undefined,
            default_voice: state.voice,
            default_language: state.language,
            default_speed: state.speed,
            default_format: state.format,
            is_default: state.setAsDefaultTTS,
          })
          setCreatedInstance(inst)
          ttsInstanceId = inst.id
          if (state.setAsDefaultTTS) {
            try { await api.setDefaultTTSInstance(inst.id) } catch { /* non-fatal */ }
          }
        }
      }

      // 2. Resolve target agent
      const getTargetAgentId = async (): Promise<number> => {
        if (state.mode === 'existing' && state.existingAgentId) return state.existingAgentId
        setProgressMessage('Creating new voice agent...')
        return await createNewVoiceAgent()
      }

      // 3. Kokoro: wait for container before wiring skills
      if (wantsTTS && state.provider === 'kokoro' && ttsInstanceId && !kokoroRunning && state.autoProvision) {
        setProgressMessage('Starting Kokoro container (this may take 30–90s)...')
        await new Promise<void>((resolve, reject) => {
          pollKokoroContainer(ttsInstanceId!, () => {
            setProgressMessage('Container running — wiring audio skills...')
            resolve()
          })
          // Safety timeout in case status reporting breaks
          setTimeout(() => reject(new Error('Kokoro container did not report ready in time.')), 7 * 60 * 1000)
        }).catch(err => { throw err })
      }

      // 4. Target agent + skills
      const agentId = await getTargetAgentId()
      setCreatedAgentId(agentId)
      setProgressMessage('Attaching audio skills to agent...')
      await wireAudioSkills(agentId, ttsInstanceId)

      finish()
    } catch (e: any) {
      setProgressStatus('error')
      setProgressMessage(e?.message || 'Unexpected error during provisioning.')
      setError(e?.message || 'Failed')
    } finally {
      setLoading(false)
    }
  }

  // -------------------- Step 1: Intent --------------------
  if (step === 1) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={close} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">Cancel</button>
        <button
          onClick={() => setStep(2)}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors"
        >
          Next: Choose provider →
        </button>
      </div>
    )
    const options: { id: AudioAgentType; title: string; desc: string }[] = [
      { id: 'voice', title: 'Voice responses (TTS)', desc: 'Agent replies with synthesized audio. Pick this to give your agent a voice.' },
      { id: 'transcript', title: 'Audio transcription only', desc: 'Agent transcribes incoming voice messages to text. No audio out.' },
      { id: 'hybrid', title: 'Hybrid — both', desc: 'Transcribe voice input AND reply with synthesized audio.' },
    ]
    return (
      <Modal isOpen={isOpen} onClose={close} title="Set up an Audio Agent" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">What kind of audio agent do you need?</h3>
            <p className="text-sm text-gray-300">Pick a capability. You can change it later by editing the agent's skills.</p>
          </div>
          <div className="space-y-2">
            {options.map(opt => (
              <button
                key={opt.id}
                onClick={() => setState(s => ({ ...s, agentType: opt.id }))}
                className={`w-full text-left p-4 rounded-xl border transition-colors ${
                  state.agentType === opt.id
                    ? 'border-teal-400 bg-teal-500/10'
                    : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                }`}
              >
                <div className="text-white font-medium">{opt.title}</div>
                <div className="text-xs text-gray-400 mt-1">{opt.desc}</div>
              </button>
            ))}
          </div>
        </div>
      </Modal>
    )
  }

  // -------------------- Step 2: Provider --------------------
  if (step === 2) {
    const allowsProviderChoice = state.agentType !== 'transcript'
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(1)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">← Back</button>
        <button
          onClick={() => setStep(3)}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors"
        >
          Next: Configure voice →
        </button>
      </div>
    )
    return (
      <Modal isOpen={isOpen} onClose={close} title="Set up an Audio Agent" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          {!allowsProviderChoice && (
            <div className="p-3 rounded-lg bg-sky-500/10 border border-sky-500/30 text-sm text-sky-200">
              Transcription-only agents use OpenAI Whisper. You just need an OpenAI API key configured in Hub.
            </div>
          )}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">Choose a TTS provider</h3>
            <p className="text-sm text-gray-300">This determines where the audio is synthesized.</p>
          </div>
          <AudioProviderPicker
            provider={state.provider}
            onChange={(provider, defaultVoice) => setState(s => ({ ...s, provider, voice: defaultVoice }))}
            allowChoice={allowsProviderChoice}
            kokoroRunning={kokoroRunning}
            hasOpenAIKey={hasOpenAIKey}
            hasElevenLabsKey={hasElevenLabsKey}
            hasGeminiKey={hasGeminiKey}
          />
        </div>
      </Modal>
    )
  }

  // -------------------- Step 3: Voice & credentials --------------------
  if (step === 3) {
    const wantsTTS = state.agentType === 'voice' || state.agentType === 'hybrid'
    const providerOK = !wantsTTS
      || state.provider === 'kokoro'
      || (state.provider === 'openai' && hasOpenAIKey)
      || (state.provider === 'elevenlabs' && hasElevenLabsKey)
      || (state.provider === 'gemini' && hasGeminiKey)

    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(2)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">← Back</button>
        <button
          onClick={() => setStep(4)}
          disabled={!providerOK}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next: Agent target →
        </button>
      </div>
    )

    return (
      <Modal isOpen={isOpen} onClose={close} title="Set up an Audio Agent" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">
              {wantsTTS ? 'Voice & provider configuration' : 'Transcription settings'}
            </h3>
          </div>

          <AudioVoiceFields
            value={{
              provider: state.provider,
              voice: state.voice,
              language: state.language,
              speed: state.speed,
              format: state.format,
              memLimit: state.memLimit,
              setAsDefaultTTS: state.setAsDefaultTTS,
            }}
            onChange={(patch) => setState(s => ({ ...s, ...patch }))}
            wantsTTS={wantsTTS}
            kokoroRunning={kokoroRunning}
            hasOpenAIKey={hasOpenAIKey}
            hasElevenLabsKey={hasElevenLabsKey}
            hasGeminiKey={hasGeminiKey}
          />
        </div>
      </Modal>
    )
  }

  // -------------------- Step 4: Agent target --------------------
  if (step === 4) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(3)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">← Back</button>
        <button
          onClick={() => setStep(5)}
          disabled={state.mode === 'existing' && !state.existingAgentId}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next: Review →
        </button>
      </div>
    )
    const hasAgents = agents.length > 0
    return (
      <Modal isOpen={isOpen} onClose={close} title="Set up an Audio Agent" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <div>
            <h3 className="text-lg font-semibold text-white mb-2">Attach audio to which agent?</h3>
          </div>
          <div className="space-y-2">
            <button
              onClick={() => setState(s => ({ ...s, mode: 'new' }))}
              className={`w-full text-left p-4 rounded-xl border transition-colors ${
                state.mode === 'new' ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              }`}
            >
              <div className="text-white font-medium">Create a new Voice Assistant agent</div>
              <div className="text-xs text-gray-400 mt-1">Scaffolds a fresh agent with a short-response system prompt, pre-wired for audio.</div>
            </button>
            <button
              onClick={() => setState(s => ({ ...s, mode: 'existing' }))}
              disabled={!hasAgents}
              className={`w-full text-left p-4 rounded-xl border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                state.mode === 'existing' ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              }`}
            >
              <div className="text-white font-medium">Attach audio to an existing agent</div>
              <div className="text-xs text-gray-400 mt-1">
                {hasAgents
                  ? 'Adds audio_tts / audio_transcript skills to a chosen agent. Other skills preserved.'
                  : 'No agents yet — choose "Create new" above.'}
              </div>
            </button>
          </div>

          {state.mode === 'new' && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Agent name</label>
              <input
                type="text"
                value={state.newAgentName}
                onChange={(e) => setState(s => ({ ...s, newAgentName: e.target.value }))}
                className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
                placeholder="Voice Assistant"
              />
            </div>
          )}

          {state.mode === 'existing' && hasAgents && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Target agent</label>
              <select
                value={state.existingAgentId ?? ''}
                onChange={(e) => setState(s => ({ ...s, existingAgentId: e.target.value ? Number(e.target.value) : null }))}
                className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
              >
                <option value="">Select an agent...</option>
                {agents.map(a => (
                  <option key={a.id} value={a.id}>{a.contact_name}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      </Modal>
    )
  }

  // -------------------- Step 5: Review --------------------
  if (step === 5) {
    const footer = (
      <div className="flex items-center justify-between w-full">
        <button onClick={() => setStep(4)} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">← Back</button>
        <button
          onClick={handleFinalize}
          disabled={loading}
          className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors disabled:opacity-50"
        >
          {loading ? 'Provisioning...' : 'Create & Provision'}
        </button>
      </div>
    )
    const targetAgentName = state.mode === 'existing'
      ? (agents.find(a => a.id === state.existingAgentId)?.contact_name || '—')
      : state.newAgentName
    const skillDiff: string[] = []
    if (state.agentType === 'voice' || state.agentType === 'hybrid') skillDiff.push('audio_tts')
    if (state.agentType === 'transcript' || state.agentType === 'hybrid') skillDiff.push('audio_transcript')

    return (
      <Modal isOpen={isOpen} onClose={close} title="Set up an Audio Agent" footer={footer} size="lg">
        <div className="space-y-5">
          {stepIndicator}
          <h3 className="text-lg font-semibold text-white">Review and confirm</h3>

          <div className="grid grid-cols-2 gap-3">
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500">Capability</div>
              <div className="text-white capitalize">{state.agentType}</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500">Provider</div>
              <div className="text-white capitalize">{state.provider}</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500">Voice</div>
              <div className="text-white">{state.voice}</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-xs text-gray-500">Language</div>
              <div className="text-white">{state.language}</div>
            </div>
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 col-span-2">
              <div className="text-xs text-gray-500">Target agent</div>
              <div className="text-white">
                {state.mode === 'new' ? 'New — ' : 'Existing — '}{targetAgentName}
              </div>
              <div className="text-xs text-gray-400 mt-1">Skills to add: {skillDiff.join(', ') || 'none'}</div>
            </div>
          </div>

          {state.provider === 'kokoro' && !kokoroRunning && (
            <div className="p-3 rounded-lg bg-sky-500/10 border border-sky-500/30 text-xs text-sky-200">
              A Kokoro Docker container will be provisioned for this tenant (~30–90s).
            </div>
          )}
          {error && <div className="text-sm text-red-300">{error}</div>}
        </div>
      </Modal>
    )
  }

  // -------------------- Step 6: Progress --------------------
  const progressFooter = (
    <div className="flex items-center justify-end w-full">
      {progressStatus === 'done' && (
        <button onClick={close} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors">
          Done
        </button>
      )}
      {progressStatus === 'error' && (
        <>
          <button onClick={() => { setStep(5); setProgressStatus(null) }} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">← Back</button>
          <button onClick={close} className="px-4 py-2 text-sm bg-red-500/20 hover:bg-red-500/30 text-red-200 rounded-lg transition-colors">Close</button>
        </>
      )}
    </div>
  )
  return (
    <Modal isOpen={isOpen} onClose={close} title="Set up an Audio Agent" footer={progressFooter} size="lg" showCloseButton={progressStatus === 'done' || progressStatus === 'error'}>
      <div className="space-y-5">
        {stepIndicator}
        <div className="flex items-center gap-4 py-4">
          {progressStatus === 'provisioning' && (
            <svg className="animate-spin h-10 w-10 text-teal-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
          )}
          {progressStatus === 'done' && (
            <div className="w-10 h-10 rounded-full bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center text-emerald-300 text-xl">✓</div>
          )}
          {progressStatus === 'error' && (
            <div className="w-10 h-10 rounded-full bg-red-500/20 border border-red-500/50 flex items-center justify-center text-red-300 text-xl">×</div>
          )}
          <div>
            <div className="text-white font-medium">
              {progressStatus === 'provisioning' && 'Setting up your audio agent...'}
              {progressStatus === 'done' && 'All set!'}
              {progressStatus === 'error' && 'Something went wrong'}
            </div>
            <div className="text-xs text-gray-400 mt-1">{progressMessage}</div>
          </div>
        </div>

        {progressStatus === 'done' && createdAgentId && (
          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5">
            <div className="text-sm text-white mb-2">Your audio agent is ready.</div>
            <a
              href={`/playground?agentId=${createdAgentId}`}
              className="inline-block px-3 py-1.5 text-xs bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors"
            >
              Open in Playground →
            </a>
          </div>
        )}
      </div>
    </Modal>
  )
}
