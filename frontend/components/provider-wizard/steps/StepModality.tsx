'use client'

import { useEffect } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import type { Modality } from '@/lib/provider-wizard/reducer'
import { BrainIcon, MicrophoneIcon, BeakerIcon, type IconProps } from '@/components/ui/icons'

interface Option {
  id: Modality
  label: string
  description: string
  Icon: React.FC<IconProps>
}

const OPTIONS: Option[] = [
  {
    id: 'llm',
    label: 'Language Model (LLM)',
    description: 'Text generation, chat, reasoning. Used by agents for conversation and tool use.',
    Icon: BrainIcon,
  },
  {
    id: 'tts',
    label: 'Text-to-Speech (Audio out)',
    description: 'Voice synthesis for audio agents. Self-hosted Kokoro or hosted OpenAI / ElevenLabs / Gemini.',
    Icon: MicrophoneIcon,
  },
  {
    id: 'asr',
    label: 'Speech-to-Text (Audio in)',
    description: 'Voice-note transcription. Cloud OpenAI Whisper, or self-hosted Speaches / openai/whisper.',
    Icon: MicrophoneIcon,
  },
  {
    id: 'image',
    label: 'Image Generation',
    description: 'Generate images from prompts with Gemini API Imagen 4 and OpenAI GPT Image 2.',
    Icon: BeakerIcon,
  },
]

/**
 * Step 1 — pick what you're adding. Branching on this choice dictates the
 * hosting options and vendor list in later steps.
 */
export default function StepModality() {
  const { state, patchDraft, markStepComplete } = useProviderWizard()
  const modality = state.draft.modality

  // Step is complete the moment a modality is picked.
  useEffect(() => {
    markStepComplete('modality', modality !== null)
  }, [modality, markStepComplete])

  const handlePick = (m: Modality) => {
    // Auto-pick hosting for modalities where only one option exists today.
    // Image: cloud-only. LLM/TTS: user chooses on next step.
    const hostingPatch = m === 'image' ? { hosting: 'cloud' as const } : {}
    patchDraft({ modality: m, ...hostingPatch })
  }

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h3 className="text-base font-semibold text-white mb-1">What are you adding?</h3>
        <p className="text-xs text-tsushin-slate">Pick the type of provider. Each path walks you through the right configuration.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {OPTIONS.map(opt => {
          const Icon = opt.Icon
          const active = modality === opt.id
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
                <h4 className="text-sm font-semibold text-white pt-1.5">{opt.label}</h4>
              </div>
              <p className="text-xs text-tsushin-slate leading-relaxed">{opt.description}</p>
            </button>
          )
        })}
      </div>
    </div>
  )
}
