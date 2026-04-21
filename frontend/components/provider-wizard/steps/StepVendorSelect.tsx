'use client'

import { useEffect, useMemo } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import {
  OpenAIIcon,
  AnthropicIcon,
  GeminiIcon,
  CloudIcon,
  LightningIcon,
  BrainIcon,
  GlobeIcon,
  BeakerIcon,
  BotIcon,
  MicrophoneIcon,
  type IconProps,
} from '@/components/ui/icons'

interface VendorOption {
  id: string
  label: string
  description: string
  Icon: React.FC<IconProps>
  /** Optional tag surfaced above the card (e.g. "Uses Nano Banana"). */
  tag?: string
}

const LLM_CLOUD: VendorOption[] = [
  { id: 'openai',     label: 'OpenAI',            description: 'GPT-4, GPT-4o, o1, o3 and OpenAI-compatible endpoints.', Icon: OpenAIIcon },
  { id: 'anthropic',  label: 'Anthropic',         description: 'Claude Opus, Sonnet, Haiku.',                              Icon: AnthropicIcon },
  { id: 'gemini',     label: 'Google Gemini',     description: 'Gemini 2.5 Flash, Gemini 3 Pro — multimodal text.',        Icon: GeminiIcon },
  { id: 'vertex_ai',  label: 'Vertex AI',         description: 'Google Cloud Model Garden — Claude on Vertex, etc.',       Icon: CloudIcon },
  { id: 'groq',       label: 'Groq',              description: 'Ultra-low-latency hosted inference.',                      Icon: LightningIcon },
  { id: 'grok',       label: 'Grok (xAI)',        description: 'xAI Grok models.',                                         Icon: BrainIcon },
  { id: 'deepseek',   label: 'DeepSeek',          description: 'DeepSeek chat and reasoning endpoints.',                   Icon: BrainIcon },
  { id: 'openrouter', label: 'OpenRouter',        description: 'Many hosted models behind one API.',                       Icon: GlobeIcon },
  { id: 'custom',     label: 'Custom',            description: 'Bring-your-own OpenAI-compatible endpoint.',               Icon: BeakerIcon },
]

const LLM_LOCAL: VendorOption[] = [
  { id: 'ollama', label: 'Ollama', description: 'Self-hosted, tenant-scoped container. GPU-aware; pulls any Ollama model.', Icon: BotIcon },
]

const TTS_CLOUD: VendorOption[] = [
  { id: 'elevenlabs', label: 'ElevenLabs', description: 'Hosted high-fidelity voice generation. Requires an API key.', Icon: MicrophoneIcon },
]

const TTS_LOCAL: VendorOption[] = [
  { id: 'kokoro', label: 'Kokoro', description: 'Self-hosted multilingual TTS container. Per-tenant instance.', Icon: MicrophoneIcon },
]

const IMAGE_CLOUD: VendorOption[] = [
  {
    id: 'gemini',
    label: 'Google Gemini',
    description: 'Image generation via gemini-2.5-flash-image ("Nano Banana") and gemini-3-pro-image-preview ("Nano Banana Pro").',
    Icon: GeminiIcon,
    tag: 'Uses Nano Banana / Nano Banana Pro',
  },
]

/**
 * Step 3 — vendor picker, filtered by (modality, hosting) so the user only
 * sees relevant options. This is where the guided flow replaces the old
 * flat category picker.
 */
export default function StepVendorSelect() {
  const { state, patchDraft, markStepComplete } = useProviderWizard()
  const { modality, hosting, vendor } = state.draft

  const options = useMemo<VendorOption[]>(() => {
    if (modality === 'llm' && hosting === 'cloud') return LLM_CLOUD
    if (modality === 'llm' && hosting === 'local') return LLM_LOCAL
    if (modality === 'tts' && hosting === 'cloud') return TTS_CLOUD
    if (modality === 'tts' && hosting === 'local') return TTS_LOCAL
    if (modality === 'image') return IMAGE_CLOUD
    return []
  }, [modality, hosting])

  // Auto-select when only one vendor is available and bump the user forward.
  useEffect(() => {
    if (options.length === 1 && vendor !== options[0].id) {
      patchDraft({ vendor: options[0].id })
    }
  }, [options, vendor, patchDraft])

  useEffect(() => {
    markStepComplete('vendor', !!vendor && options.some(o => o.id === vendor))
  }, [vendor, options, markStepComplete])

  const handlePick = (id: string) => {
    // Pre-seed a helpful instance name from the vendor id.
    const existing = state.draft.instance_name.trim()
    const autoName = existing || `${id}-1`
    patchDraft({ vendor: id, instance_name: autoName })
  }

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h3 className="text-base font-semibold text-white mb-1">Choose a provider</h3>
        <p className="text-xs text-tsushin-slate">
          {modality === 'image'
            ? 'Image generation runs on Gemini. You can add more providers later when available.'
            : options.length === 1
              ? 'Only one provider fits your choices — click to continue.'
              : 'Pick which vendor this instance will use.'}
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {options.map(opt => {
          const Icon = opt.Icon
          const active = vendor === opt.id
          return (
            <button
              key={opt.id}
              onClick={() => handlePick(opt.id)}
              className={`text-left rounded-xl border p-4 transition-all ${
                active
                  ? 'border-teal-500 bg-teal-500/10'
                  : 'border-tsushin-border bg-tsushin-ink/40 hover:border-tsushin-accent/50'
              }`}
            >
              <div className="flex items-start gap-3 mb-2">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                  active ? 'bg-teal-500/20 text-teal-400' : 'bg-white/5 text-tsushin-slate'
                }`}>
                  <Icon size={18} />
                </div>
                <div className="min-w-0 flex-1">
                  <h4 className="text-sm font-semibold text-white">{opt.label}</h4>
                  {opt.tag && (
                    <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-400 border border-teal-500/20">
                      {opt.tag}
                    </span>
                  )}
                </div>
              </div>
              <p className="text-xs text-tsushin-slate leading-relaxed">{opt.description}</p>
            </button>
          )
        })}
        {options.length === 0 && (
          <div className="col-span-full rounded-lg border border-dashed border-tsushin-border p-4 text-center">
            <p className="text-xs text-tsushin-slate">
              No providers match this combination. Go back and change the modality or hosting.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
