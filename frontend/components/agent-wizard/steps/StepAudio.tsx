'use client'

import { useEffect, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { TTSInstance, ProviderInstance } from '@/lib/client'
import { AudioProviderPicker, AudioTranscriptFields, AudioVoiceFields } from '@/components/audio-wizard/AudioProviderFields'
import type { AudioCapability, AudioConfig } from '@/lib/agent-wizard/reducer'
import { isAudioValid, DEFAULT_AUDIO_CONFIG } from '@/lib/agent-wizard/reducer'

export default function StepAudio() {
  const { state, patchAudio, markStepComplete } = useAgentWizard()
  const [ttsInstances, setTtsInstances] = useState<TTSInstance[]>([])
  const [providerInstances, setProviderInstances] = useState<ProviderInstance[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    Promise.all([
      api.getTTSInstances().catch(() => []),
      api.getProviderInstances().catch(() => []),
    ]).then(([tts, pi]) => {
      setTtsInstances(tts)
      setProviderInstances(pi)
      setLoaded(true)
    })
  }, [])

  // Initialize audio config lazily for hybrid — hybrid defaults to `hybrid` capability
  useEffect(() => {
    if (!state.draft.audio && (state.draft.type === 'audio' || state.draft.type === 'hybrid')) {
      patchAudio({ ...DEFAULT_AUDIO_CONFIG, capability: state.draft.type === 'hybrid' ? 'hybrid' : 'voice' })
    }
  }, [state.draft.type, state.draft.audio, patchAudio])

  const audio = state.draft.audio
  const kokoroRunning = ttsInstances.find(t => t.vendor === 'kokoro' && t.is_active)
  const hasOpenAIKey = providerInstances.some(p => p.vendor === 'openai' && p.api_key_configured)
  const hasElevenLabsKey = providerInstances.some(p => p.vendor === 'elevenlabs' && p.api_key_configured)
  const hasGeminiKey = providerInstances.some(p => p.vendor === 'gemini' && p.api_key_configured)

  const wantsTTS = audio ? (audio.capability === 'voice' || audio.capability === 'hybrid') : false
  const wantsTranscript = audio ? (audio.capability === 'transcript' || audio.capability === 'hybrid') : false
  const providerOK = !wantsTTS
    || audio?.provider === 'kokoro'
    || (audio?.provider === 'openai' && hasOpenAIKey)
    || (audio?.provider === 'elevenlabs' && hasElevenLabsKey)
    || (audio?.provider === 'gemini' && hasGeminiKey)

  useEffect(() => {
    markStepComplete('audio', isAudioValid(audio ?? null) && providerOK)
  }, [audio, providerOK, markStepComplete])

  if (!loaded || !audio) {
    return <div className="py-6 text-center text-sm text-gray-400">Loading audio options…</div>
  }

  const capabilityOptions: { id: AudioCapability; title: string; desc: string }[] = [
    { id: 'voice', title: 'Voice responses (TTS)', desc: 'Agent replies with synthesized audio.' },
    { id: 'transcript', title: 'Audio transcription only', desc: 'Agent transcribes voice to text. No audio out.' },
    { id: 'hybrid', title: 'Both — transcribe and speak', desc: 'Transcribe voice input AND reply with audio.' },
  ]

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">Voice capability</h3>
        <p className="text-sm text-gray-300">How should this agent use audio?</p>
      </div>

      <div className="space-y-2">
        {capabilityOptions.map(opt => (
          <button
            key={opt.id}
            type="button"
            onClick={() => patchAudio({ capability: opt.id })}
            className={`w-full text-left p-3 rounded-xl border transition-colors ${
              audio.capability === opt.id ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
            }`}
          >
            <div className="text-white font-medium text-sm">{opt.title}</div>
            <div className="text-xs text-gray-400 mt-0.5">{opt.desc}</div>
          </button>
        ))}
      </div>

      {wantsTTS && (
        <div className="space-y-3 pt-2 border-t border-white/5">
          <h4 className="text-sm font-semibold text-white">TTS provider</h4>
          <AudioProviderPicker
            provider={audio.provider}
            onChange={(provider, defaultVoice) => patchAudio({ provider, voice: defaultVoice })}
            allowChoice={true}
            kokoroRunning={kokoroRunning}
            hasOpenAIKey={hasOpenAIKey}
            hasElevenLabsKey={hasElevenLabsKey}
            hasGeminiKey={hasGeminiKey}
          />
        </div>
      )}

      <div className="pt-2 border-t border-white/5">
        <AudioVoiceFields
          value={{
            provider: audio.provider,
            voice: audio.voice,
            language: audio.language,
            speed: audio.speed,
            format: audio.format,
            memLimit: audio.memLimit,
            setAsDefaultTTS: audio.setAsDefaultTTS,
            model: audio.model,
          }}
          onChange={patch => patchAudio(patch)}
          wantsTTS={wantsTTS}
          kokoroRunning={kokoroRunning}
          hasOpenAIKey={hasOpenAIKey}
          hasElevenLabsKey={hasElevenLabsKey}
          hasGeminiKey={hasGeminiKey}
          hideDefaultTTSOption={false}
        />
      </div>

      {wantsTranscript && (
        <div className="pt-2 border-t border-white/5">
          <h4 className="text-sm font-semibold text-white mb-3">Transcription backend</h4>
          <AudioTranscriptFields
            value={{
              language: audio.language,
              model: audio.transcriptModel,
              asrMode: audio.asrMode,
              asrInstanceId: audio.asrInstanceId,
            }}
            onChange={(patch) => {
              const next: Partial<AudioConfig> = {}
              if (patch.language !== undefined) next.language = patch.language
              if (patch.model !== undefined) next.transcriptModel = patch.model
              if (patch.asrMode !== undefined) next.asrMode = patch.asrMode
              if (patch.asrInstanceId !== undefined) next.asrInstanceId = patch.asrInstanceId
              patchAudio(next)
            }}
            showResponseMode={false}
          />
        </div>
      )}

      {!providerOK && wantsTTS && (
        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-sm text-amber-200">
          <div className="mb-2">Selected provider needs an API key. You can switch to Kokoro (free, local) to proceed.</div>
          <button
            type="button"
            onClick={() => patchAudio({ provider: 'kokoro', voice: 'pf_dora' })}
            className="px-3 py-1.5 text-xs bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors"
          >
            Use Kokoro instead
          </button>
        </div>
      )}
    </div>
  )
}
