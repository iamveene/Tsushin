'use client'

/**
 * Shared audio-wizard UI fragments:
 * - AudioProviderPicker: provider cards (fetched live from /api/tts-providers,
 *   with static fallback — see below).
 * - AudioVoiceFields: language + voice + speed + format + Kokoro container opts
 *   (voice dropdown fetched live from /api/tts-providers/{provider}/voices).
 *
 * Both AudioAgentsWizard and the AgentWizard audio step consume these.
 *
 * **Drift protection.** The provider card list and per-provider voice list are
 * both fetched at runtime from the backend so that adding a new TTS provider /
 * voice in `TTSProviderRegistry` (backend/hub/providers/tts_registry.py) or in
 * a provider's `get_available_voices()` method surfaces here without any frontend
 * code change. Static fallback arrays in `defaults.ts` remain as offline / degraded-
 * mode fallback ONLY — `backend/tests/test_wizard_drift.py` asserts the fallback
 * stays in sync with the backend registry.
 */

import { useEffect, useMemo, useState } from 'react'
import { api } from '@/lib/client'
import type { ASRInstance, TTSInstance, TTSModelInfo, TTSProviderInfo, TTSVoice } from '@/lib/client'
import {
  KOKORO_VOICES,
  OPENAI_VOICES,
  GEMINI_VOICES,
  GEMINI_TTS_MODELS,
  GEMINI_TTS_DEFAULT_MODEL,
  LANGUAGES,
  MEM_LIMITS,
  type AudioProvider,
} from './defaults'

type ProviderStatus = 'configured' | 'available' | 'missing'

interface ProviderCardData {
  id: AudioProvider
  title: string
  desc: string
  cost: string
  status: ProviderStatus
  defaultVoice: string
}

const FALLBACK_PROVIDER_CARDS: ProviderCardData[] = [
  { id: 'kokoro', title: 'Kokoro TTS', desc: 'Free, open-source, runs locally in a Docker container. Portuguese + English voices.', cost: 'Free', status: 'available', defaultVoice: 'pf_dora' },
  { id: 'openai', title: 'OpenAI TTS', desc: 'High-quality cloud TTS. Requires an OpenAI API key (configured in Hub → AI Providers).', cost: 'Paid', status: 'missing', defaultVoice: 'nova' },
  { id: 'elevenlabs', title: 'ElevenLabs', desc: 'Premium voice cloning and expressive TTS. Requires an ElevenLabs API key.', cost: 'Paid', status: 'missing', defaultVoice: 'nova' },
  { id: 'gemini', title: 'Google Gemini TTS (Preview)', desc: '30 prebuilt voices from gemini-3.1-flash-tts-preview. WAV output, no speed control. Reuses your Gemini API key.', cost: 'Preview', status: 'missing', defaultVoice: 'Zephyr' },
]

// Copy descriptions / cost labels per provider id. The backend supplies id,
// display name, default voice, requires_api_key, is_free, status, and
// tenant_has_configured — but not the curated marketing copy rendered in the
// card, which lives here. If a new provider lands backend-side without a copy
// row, we fall back to the backend's display name + description.
const PROVIDER_COPY: Partial<Record<string, { desc: string; cost: string }>> = {
  kokoro: { desc: 'Free, open-source, runs locally in a Docker container. Portuguese + English voices.', cost: 'Free' },
  openai: { desc: 'High-quality cloud TTS. Requires an OpenAI API key (configured in Hub → AI Providers).', cost: 'Paid' },
  elevenlabs: { desc: 'Premium voice cloning and expressive TTS. Requires an ElevenLabs API key.', cost: 'Paid' },
  gemini: { desc: '30 prebuilt voices from gemini-3.1-flash-tts-preview. WAV output, no speed control. Reuses your Gemini API key.', cost: 'Preview' },
}

function backendProviderToCard(
  p: TTSProviderInfo,
  kokoroRunning: TTSInstance | undefined,
): ProviderCardData {
  const copy = PROVIDER_COPY[p.id]
  let status: ProviderStatus
  if (p.id === 'kokoro') status = kokoroRunning ? 'configured' : 'available'
  else if (p.is_free) status = 'configured'
  else status = p.tenant_has_configured ? 'configured' : 'missing'

  return {
    id: p.id as AudioProvider,
    title: p.name || p.id,
    desc: copy?.desc || p.pricing?.cost_per_1k_chars !== undefined
      ? copy?.desc || `${p.voice_count} voice${p.voice_count === 1 ? '' : 's'}.`
      : copy?.desc || '',
    cost: copy?.cost || (p.is_free ? 'Free' : p.status === 'preview' ? 'Preview' : 'Paid'),
    status,
    defaultVoice: p.default_voice || 'default',
  }
}

export interface AudioProviderPickerProps {
  provider: AudioProvider
  onChange: (provider: AudioProvider, defaultVoice: string) => void
  allowChoice?: boolean
  kokoroRunning: TTSInstance | undefined
  /** @deprecated Backend now resolves per-tenant via tenant_has_configured. Retained for backward compat. */
  hasOpenAIKey?: boolean
  /** @deprecated */
  hasElevenLabsKey?: boolean
  /** @deprecated */
  hasGeminiKey?: boolean
}

export function AudioProviderPicker({
  provider,
  onChange,
  allowChoice = true,
  kokoroRunning,
}: AudioProviderPickerProps) {
  const [cards, setCards] = useState<ProviderCardData[]>(FALLBACK_PROVIDER_CARDS)

  useEffect(() => {
    let cancelled = false
    api.getTTSProviders()
      .then(providers => {
        if (cancelled) return
        const mapped = providers
          .filter(p => p.status !== 'coming_soon')
          .map(p => backendProviderToCard(p, kokoroRunning))
        if (mapped.length > 0) setCards(mapped)
      })
      .catch(() => { /* keep fallback */ })
    return () => { cancelled = true }
  }, [kokoroRunning])

  return (
    <div className="space-y-2">
      {cards.map(opt => (
        <button
          key={opt.id}
          type="button"
          onClick={() => onChange(opt.id, opt.defaultVoice)}
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
              {opt.status === 'configured' && (
                <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">Detected</span>
              )}
              {opt.status === 'missing' && (
                <span className="px-2 py-0.5 text-xs rounded-full bg-amber-500/20 text-amber-200 border border-amber-500/30">Needs API key</span>
              )}
            </div>
          </div>
          <div className="text-xs text-gray-400 mt-1">{opt.desc}</div>
        </button>
      ))}
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
  /** Provider-specific model id. Today only Gemini exposes a model picker; for
   *  other providers this is `undefined` and the dropdown stays hidden. */
  model?: string
}

export interface AudioVoiceFieldsProps {
  value: AudioVoiceFieldsValue
  onChange: (patch: Partial<AudioVoiceFieldsValue>) => void
  wantsTTS: boolean
  kokoroRunning: TTSInstance | undefined
  /** @deprecated — Backend `tenant_has_configured` now drives this; kept for compat. */
  hasOpenAIKey?: boolean
  /** @deprecated */
  hasElevenLabsKey?: boolean
  /** @deprecated */
  hasGeminiKey?: boolean
  /** Hide the "set as default TTS" checkbox when embedded in agent wizard (single-agent flow). */
  hideDefaultTTSOption?: boolean
}

// Fallback voice list per provider — used when /api/tts-providers/{p}/voices
// is unreachable. Kept in sync with backend registries by CI test
// backend/tests/test_wizard_drift.py.
function fallbackVoicesFor(provider: AudioProvider, language: string): { id: string; label: string; lang: string }[] {
  if (provider === 'kokoro') return KOKORO_VOICES.filter(v => v.lang === language)
  if (provider === 'gemini') return GEMINI_VOICES.map(v => ({ id: v.id, label: v.label, lang: language }))
  return OPENAI_VOICES.map(v => ({ id: v.id, label: v.label, lang: language }))
}

export function AudioVoiceFields({
  value,
  onChange,
  wantsTTS,
  kokoroRunning,
  hideDefaultTTSOption,
}: AudioVoiceFieldsProps) {
  const [liveVoices, setLiveVoices] = useState<Record<string, TTSVoice[]>>({})
  const [liveModels, setLiveModels] = useState<Record<string, TTSModelInfo[]>>({})
  const [keyStatusByProvider, setKeyStatusByProvider] = useState<Record<string, boolean>>({})

  // One-shot load of the provider list so we know per-tenant credential status
  // for the "needs API key" inline warnings.
  useEffect(() => {
    let cancelled = false
    api.getTTSProviders()
      .then(providers => {
        if (cancelled) return
        const map: Record<string, boolean> = {}
        for (const p of providers) map[p.id] = !!p.tenant_has_configured
        setKeyStatusByProvider(map)
      })
      .catch(() => { /* keep empty; warnings will not render */ })
    return () => { cancelled = true }
  }, [])

  // Fetch voices for the currently-selected provider on change.
  useEffect(() => {
    if (!wantsTTS) return
    if (liveVoices[value.provider]) return
    let cancelled = false
    api.getTTSProviderVoices(value.provider)
      .then(voices => {
        if (cancelled) return
        setLiveVoices(prev => ({ ...prev, [value.provider]: voices }))
      })
      .catch(() => { /* fall through to static fallback */ })
    return () => { cancelled = true }
  }, [value.provider, wantsTTS, liveVoices])

  // Fetch the provider's model catalog (empty for providers without
  // SUPPORTED_MODELS). When the call fails for Gemini, fall back to the
  // static GEMINI_TTS_MODELS list so the picker still works offline.
  useEffect(() => {
    if (!wantsTTS) return
    if (liveModels[value.provider]) return
    let cancelled = false
    api.getTTSProviderModels(value.provider)
      .then(models => {
        if (cancelled) return
        setLiveModels(prev => ({ ...prev, [value.provider]: models }))
      })
      .catch(() => {
        if (cancelled) return
        if (value.provider === 'gemini') {
          const fallback: TTSModelInfo[] = GEMINI_TTS_MODELS.map(m => ({
            model_id: m.id,
            label: m.label,
            is_default: m.id === GEMINI_TTS_DEFAULT_MODEL,
          }))
          setLiveModels(prev => ({ ...prev, [value.provider]: fallback }))
        } else {
          setLiveModels(prev => ({ ...prev, [value.provider]: [] }))
        }
      })
    return () => { cancelled = true }
  }, [value.provider, wantsTTS, liveModels])

  // When the provider exposes models and no model is selected yet, default to
  // the provider's `is_default` entry (or the first one). Clears `model` when
  // the provider doesn't expose any.
  useEffect(() => {
    if (!wantsTTS) return
    const models = liveModels[value.provider]
    if (!models) return
    if (models.length === 0) {
      if (value.model !== undefined) onChange({ model: undefined })
      return
    }
    const ids = models.map(m => m.model_id)
    if (!value.model || !ids.includes(value.model)) {
      const def = models.find(m => m.is_default)?.model_id || models[0].model_id
      onChange({ model: def })
    }
    // We intentionally leave `value` and `onChange` out of the deps to avoid
    // re-running on every parent re-render — only when the model catalog or
    // provider changes do we want to reconcile.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value.provider, wantsTTS, liveModels])

  const availableVoices = useMemo(() => {
    const live = liveVoices[value.provider]
    if (live && live.length > 0) {
      // Kokoro voices have language metadata — filter. Other providers treat language as auto.
      if (value.provider === 'kokoro') {
        return live
          .filter(v => !v.language || v.language === value.language)
          .map(v => ({ id: v.voice_id, label: `${v.name}${v.description ? ` — ${v.description}` : ''}`, lang: v.language || value.language }))
      }
      return live.map(v => ({ id: v.voice_id, label: `${v.name}${v.description ? ` — ${v.description}` : ''}`, lang: value.language }))
    }
    return fallbackVoicesFor(value.provider, value.language)
  }, [value.provider, value.language, liveVoices])

  const hasOpenAIKey = keyStatusByProvider['openai'] ?? false
  const hasElevenLabsKey = keyStatusByProvider['elevenlabs'] ?? false
  const hasGeminiKey = keyStatusByProvider['gemini'] ?? false

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
          {(liveModels[value.provider] || []).length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Model</label>
              <select
                value={value.model || ''}
                onChange={(e) => onChange({ model: e.target.value })}
                className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
              >
                {(liveModels[value.provider] || []).map(m => (
                  <option key={m.model_id} value={m.model_id}>{m.label}</option>
                ))}
              </select>
            </div>
          )}

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

export type ASRUsageMode = 'openai' | 'instance'

export interface AudioTranscriptFieldsValue {
  responseMode?: 'conversational' | 'transcript_only'
  language: string
  model: string
  asrMode: ASRUsageMode
  asrInstanceId: number | null
}

export interface AudioTranscriptFieldsProps {
  value: AudioTranscriptFieldsValue
  onChange: (patch: Partial<AudioTranscriptFieldsValue>) => void
  showResponseMode?: boolean
}

export function AudioTranscriptFields({
  value,
  onChange,
  showResponseMode = true,
}: AudioTranscriptFieldsProps) {
  const [instances, setInstances] = useState<ASRInstance[]>([])

  useEffect(() => {
    let cancelled = false
    api.getASRInstances().catch(() => [] as ASRInstance[]).then(loadedInstances => {
      if (cancelled) return
      setInstances(loadedInstances)
    })
    return () => { cancelled = true }
  }, [])

  const selectedInstance = useMemo(
    () => instances.find(inst => inst.id === value.asrInstanceId) || null,
    [instances, value.asrInstanceId],
  )

  const chooseMode = (mode: ASRUsageMode) => {
    if (mode === 'instance') {
      const nextId = value.asrInstanceId ?? instances[0]?.id ?? null
      onChange({ asrMode: mode, asrInstanceId: nextId })
      return
    }
    onChange({ asrMode: mode, asrInstanceId: null })
  }

  return (
    <div className="space-y-4">
      {showResponseMode && (
        <div>
          <label className="block text-sm font-medium mb-3">Response mode</label>
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => onChange({ responseMode: 'conversational' })}
              className={`w-full text-left p-4 rounded-xl border transition-colors ${
                (value.responseMode || 'conversational') === 'conversational'
                  ? 'border-teal-400 bg-teal-500/10'
                  : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              }`}
            >
              <div className="text-white font-medium text-sm">Conversational</div>
              <div className="text-xs text-gray-400 mt-1">Transcribe audio, then let the agent respond normally.</div>
            </button>
            <button
              type="button"
              onClick={() => onChange({ responseMode: 'transcript_only' })}
              className={`w-full text-left p-4 rounded-xl border transition-colors ${
                value.responseMode === 'transcript_only'
                  ? 'border-teal-400 bg-teal-500/10'
                  : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              }`}
            >
              <div className="text-white font-medium text-sm">Transcript only</div>
              <div className="text-xs text-gray-400 mt-1">Return the raw transcript without generating an AI reply.</div>
            </button>
          </div>
        </div>
      )}

      <div>
        <label className="block text-sm font-medium mb-3">ASR backend</label>
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => chooseMode('openai')}
            className={`w-full text-left p-4 rounded-xl border transition-colors ${
              value.asrMode === 'openai'
                ? 'border-teal-400 bg-teal-500/10'
                : 'border-white/10 bg-white/[0.02] hover:border-white/20'
            }`}
          >
            <div className="text-white font-medium text-sm">OpenAI Whisper (cloud)</div>
            <div className="text-xs text-gray-400 mt-1">Cloud transcription path. Requires OpenAI credentials in Hub.</div>
          </button>

          <button
            type="button"
            onClick={() => chooseMode('instance')}
            disabled={instances.length === 0}
            className={`w-full text-left p-4 rounded-xl border transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              value.asrMode === 'instance'
                ? 'border-teal-400 bg-teal-500/10'
                : 'border-white/10 bg-white/[0.02] hover:border-white/20'
            }`}
          >
            <div className="text-white font-medium text-sm">Pin a local instance</div>
            <div className="text-xs text-gray-400 mt-1">
              {instances.length > 0
                ? 'Pin this agent to one tenant-owned ASR container (Speaches or openai_whisper).'
                : 'No local ASR instances available yet.'}
            </div>
          </button>
          {instances.length === 0 && (
            // Separate sibling: the disabled button above blocks click events
            // on its children (HTML disabled-button semantics), so this CTA
            // lives outside the button. Dispatching a custom DOM event keeps
            // the wizard orchestration in hub/page.tsx — no context coupling.
            <div className="mt-2 px-4 py-3 rounded-xl border border-teal-500/20 bg-teal-500/5 text-xs text-gray-300">
              <button
                type="button"
                onClick={() => {
                  if (typeof window !== 'undefined') {
                    window.dispatchEvent(new CustomEvent('tsushin:open-provider-wizard', {
                      detail: { modality: 'asr', hosting: 'local' }
                    }))
                  }
                }}
                className="text-teal-400 hover:text-teal-300 underline font-medium"
              >
                + Create an ASR instance now
              </button>
              <span className="text-gray-400">{' '}or go to Hub → Add Provider → Speech-to-Text → Local.</span>
            </div>
          )}
        </div>
      </div>

      {value.asrMode === 'instance' && instances.length > 0 && (
        <div>
          <label className="block text-sm font-medium mb-2">Local instance</label>
          <select
            value={value.asrInstanceId ?? ''}
            onChange={(e) => onChange({ asrInstanceId: e.target.value ? Number(e.target.value) : null })}
            className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
          >
            {instances.map(inst => (
              <option key={inst.id} value={inst.id}>
                {inst.instance_name} — {inst.vendor || 'unknown'} ({inst.container_status || 'none'})
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-2">Language detection</label>
          <select
            value={value.language || 'auto'}
            onChange={(e) => onChange({ language: e.target.value })}
            className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
          >
            <option value="auto">Auto-detect</option>
            <option value="pt">Portuguese</option>
            <option value="en">English</option>
            <option value="es">Spanish</option>
            <option value="fr">French</option>
            <option value="de">German</option>
            <option value="it">Italian</option>
            <option value="ja">Japanese</option>
            <option value="ko">Korean</option>
            <option value="zh">Chinese</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">OpenAI model</label>
          <select
            value={value.model || 'whisper-1'}
            onChange={(e) => onChange({ model: e.target.value })}
            className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
          >
            <option value="whisper-1">whisper-1</option>
          </select>
        </div>
      </div>

      <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 text-sm text-gray-300">
        {value.asrMode === 'openai' && (
          <div>Uses the cloud OpenAI Whisper API. Requires the OpenAI API key configured under Hub → AI Providers → OpenAI.</div>
        )}
        {value.asrMode === 'instance' && (
          <div>
            {selectedInstance
              ? `Pins this agent to ${selectedInstance.instance_name} (${selectedInstance.vendor}). Voice notes never leave the tenant — they're transcribed locally inside the auto-provisioned container.`
              : 'Select a local ASR instance to pin this agent.'}
          </div>
        )}
      </div>
    </div>
  )
}
