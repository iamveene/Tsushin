'use client'

/**
 * Shared audio-wizard UI fragments. Two exports:
 * - AudioProviderPicker: three provider cards (Kokoro / OpenAI / ElevenLabs)
 * - AudioVoiceFields: language + voice + speed + format + Kokoro container opts
 *
 * Both AudioAgentsWizard and the newer AgentWizard audio step consume these so
 * there's a single source of truth for the voice UX.
 */

import { useMemo } from 'react'
import type { TTSInstance } from '@/lib/client'
import {
  KOKORO_VOICES,
  OPENAI_VOICES,
  GEMINI_VOICES,
  LANGUAGES,
  MEM_LIMITS,
  type AudioProvider,
} from './defaults'

type ProviderStatus = 'configured' | 'available' | 'missing'

function providerStatus(
  p: AudioProvider,
  kokoroRunning: TTSInstance | undefined,
  hasOpenAIKey: boolean,
  hasElevenLabsKey: boolean,
  hasGeminiKey: boolean,
): ProviderStatus {
  if (p === 'kokoro') return kokoroRunning ? 'configured' : 'available'
  if (p === 'openai') return hasOpenAIKey ? 'configured' : 'missing'
  if (p === 'gemini') return hasGeminiKey ? 'configured' : 'missing'
  return hasElevenLabsKey ? 'configured' : 'missing'
}

export interface AudioProviderPickerProps {
  provider: AudioProvider
  onChange: (provider: AudioProvider, defaultVoice: string) => void
  allowChoice?: boolean
  kokoroRunning: TTSInstance | undefined
  hasOpenAIKey: boolean
  hasElevenLabsKey: boolean
  hasGeminiKey?: boolean
}

export function AudioProviderPicker({
  provider,
  onChange,
  allowChoice = true,
  kokoroRunning,
  hasOpenAIKey,
  hasElevenLabsKey,
  hasGeminiKey = false,
}: AudioProviderPickerProps) {
  const opts: { id: AudioProvider; title: string; desc: string; cost: string }[] = [
    { id: 'kokoro', title: 'Kokoro TTS', desc: 'Free, open-source, runs locally in a Docker container. Portuguese + English voices.', cost: 'Free' },
    { id: 'openai', title: 'OpenAI TTS', desc: 'High-quality cloud TTS. Requires an OpenAI API key (configured in Hub → AI Providers).', cost: 'Paid' },
    { id: 'elevenlabs', title: 'ElevenLabs', desc: 'Premium voice cloning and expressive TTS. Requires an ElevenLabs API key.', cost: 'Paid' },
    { id: 'gemini', title: 'Google Gemini TTS (Preview)', desc: '30 prebuilt voices from gemini-3.1-flash-tts-preview. WAV output, no speed control. Reuses your Gemini API key.', cost: 'Preview' },
  ]

  const defaultVoiceFor = (id: AudioProvider): string => {
    if (id === 'kokoro') return 'pf_dora'
    if (id === 'openai') return 'nova'
    if (id === 'gemini') return 'Zephyr'
    return 'nova'
  }

  return (
    <div className="space-y-2">
      {opts.map(opt => {
        const status = providerStatus(opt.id, kokoroRunning, hasOpenAIKey, hasElevenLabsKey, hasGeminiKey)
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id, defaultVoiceFor(opt.id))}
            disabled={!allowChoice}
            className={`w-full text-left p-4 rounded-xl border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              provider === opt.id
                ? 'border-teal-400 bg-teal-500/10'
                : 'border-white/10 bg-white/[0.02] hover:border-white/20'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="text-white font-medium">{opt.title}</div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 text-xs rounded-full bg-white/10 text-gray-300">{opt.cost}</span>
                {status === 'configured' && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Detected</span>
                )}
                {status === 'missing' && (
                  <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-200 border border-amber-500/30">Needs API key</span>
                )}
              </div>
            </div>
            <div className="text-xs text-gray-400 mt-1">{opt.desc}</div>
          </button>
        )
      })}
    </div>
  )
}

export interface AudioVoiceFieldsValue {
  provider: AudioProvider
  voice: string
  language: string
  speed: number
  format: string
  memLimit: string
  setAsDefaultTTS: boolean
}

export interface AudioVoiceFieldsProps {
  value: AudioVoiceFieldsValue
  onChange: (patch: Partial<AudioVoiceFieldsValue>) => void
  wantsTTS: boolean
  kokoroRunning: TTSInstance | undefined
  hasOpenAIKey: boolean
  hasElevenLabsKey: boolean
  hasGeminiKey?: boolean
  /** Hide the "set as default TTS" checkbox when embedded in agent wizard (single-agent flow). */
  hideDefaultTTSOption?: boolean
}

export function AudioVoiceFields({
  value,
  onChange,
  wantsTTS,
  kokoroRunning,
  hasOpenAIKey,
  hasElevenLabsKey,
  hasGeminiKey = false,
  hideDefaultTTSOption,
}: AudioVoiceFieldsProps) {
  const availableVoices = useMemo(() => {
    if (value.provider === 'kokoro') return KOKORO_VOICES.filter(v => v.lang === value.language)
    if (value.provider === 'gemini') return GEMINI_VOICES.map(v => ({ id: v.id, label: v.label, lang: value.language }))
    return OPENAI_VOICES.map(v => ({ id: v.id, label: v.label, lang: value.language }))
  }, [value.provider, value.language])

  return (
    <div className="space-y-5">
      <div>
        <label className="block text-xs text-gray-400 mb-1">Language</label>
        <select
          value={value.language}
          onChange={(e) => onChange({ language: e.target.value })}
          className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
        >
          {LANGUAGES.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
        </select>
      </div>

      {wantsTTS && (
        <>
          <div>
            <label className="block text-xs text-gray-400 mb-1">Voice</label>
            <select
              value={value.voice}
              onChange={(e) => onChange({ voice: e.target.value })}
              className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
            >
              {availableVoices.length === 0 && <option value="">(no voices available for this language)</option>}
              {availableVoices.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          </div>

          {value.provider === 'gemini' ? (
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 text-xs text-gray-400">
              Gemini TTS preview outputs WAV at 24 kHz / 16-bit / mono. Speed control is not supported by this model.
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Speed</label>
                <input
                  type="number" min={0.5} max={2.0} step={0.1}
                  value={value.speed}
                  onChange={(e) => onChange({ speed: parseFloat(e.target.value) || 1.0 })}
                  className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Format</label>
                <select
                  value={value.format}
                  onChange={(e) => onChange({ format: e.target.value })}
                  className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
                >
                  <option value="opus">Opus (recommended)</option>
                  <option value="mp3">MP3</option>
                  <option value="wav">WAV</option>
                </select>
              </div>
            </div>
          )}

          {value.provider === 'kokoro' && !kokoroRunning && (
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 space-y-3">
              <div className="text-sm text-white font-medium">Kokoro container</div>
              <div className="text-xs text-gray-400">A Docker container will be auto-provisioned for this tenant. Takes ~30–90 seconds.</div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Memory limit</label>
                <select
                  value={value.memLimit}
                  onChange={(e) => onChange({ memLimit: e.target.value })}
                  className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
                >
                  {MEM_LIMITS.map(m => <option key={m} value={m}>{m}</option>)}
                </select>
              </div>
              {!hideDefaultTTSOption && (
                <label className="flex items-center gap-2 text-xs text-gray-300">
                  <input
                    type="checkbox"
                    checked={value.setAsDefaultTTS}
                    onChange={(e) => onChange({ setAsDefaultTTS: e.target.checked })}
                  />
                  Set as tenant-default TTS instance
                </label>
              )}
            </div>
          )}

          {value.provider === 'kokoro' && kokoroRunning && (
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-sm text-emerald-200">
              Reusing existing Kokoro instance: <span className="font-mono">{kokoroRunning.instance_name}</span>. No container provisioning needed.
            </div>
          )}

          {value.provider === 'openai' && !hasOpenAIKey && (
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-sm text-amber-200">
              No OpenAI API key detected. Add one at <a href="/hub?tab=ai-providers" className="underline">Hub → AI Providers</a>, then re-open this wizard.
            </div>
          )}

          {value.provider === 'elevenlabs' && !hasElevenLabsKey && (
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-sm text-amber-200">
              No ElevenLabs API key detected. Add one at <a href="/hub?tab=ai-providers" className="underline">Hub → AI Providers</a>, then re-open this wizard.
            </div>
          )}

          {value.provider === 'gemini' && !hasGeminiKey && (
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-sm text-amber-200">
              No Gemini API key detected. Add one at <a href="/hub?tab=ai-providers" className="underline">Hub → AI Providers</a>, then re-open this wizard.
            </div>
          )}
        </>
      )}

      {!wantsTTS && (
        <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 text-sm text-gray-300">
          Transcription uses OpenAI Whisper. Ensure an OpenAI API key is configured in Hub → AI Providers.
          {!hasOpenAIKey && (
            <div className="mt-2 text-amber-200">⚠ No OpenAI API key detected.</div>
          )}
        </div>
      )}
    </div>
  )
}
