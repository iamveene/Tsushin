'use client'

import { useEffect } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import type { Hosting } from '@/lib/provider-wizard/reducer'
import { CloudIcon, ServerIcon, type IconProps } from '@/components/ui/icons'

interface Option {
  id: Hosting
  label: string
  description: string
  Icon: React.FC<IconProps>
}

const OPTIONS: Option[] = [
  {
    id: 'cloud',
    label: 'Cloud / API',
    description: 'Use a hosted provider. You bring an API key — Tsushin calls the vendor directly.',
    Icon: CloudIcon,
  },
  {
    id: 'local',
    label: 'Self-hosted container',
    description: 'Tsushin provisions a dedicated container for this tenant. Runs on this server.',
    Icon: ServerIcon,
  },
]

/**
 * Step 2 — Cloud vs Self-hosted. The reducer auto-sets hosting='cloud' when
 * modality='image' so this step is skipped for image. If the only sensible
 * option for the chosen modality is cloud (or local), we still render a
 * one-card confirmation rather than jumping straight to vendor — it helps
 * the user understand the branching.
 */
export default function StepHosting() {
  const { state, patchDraft, markStepComplete, nextStep } = useProviderWizard()
  const { modality, hosting } = state.draft

  // Step is complete once a hosting is picked.
  useEffect(() => {
    markStepComplete('hosting', hosting !== null)
  }, [hosting, markStepComplete])

  // If only one hosting is available for this modality, auto-advance.
  // Currently: image=cloud only (handled in StepModality). We keep this hook
  // for future modalities that lock hosting.
  useEffect(() => {
    if (modality === 'image' && hosting === 'cloud') {
      // Already auto-advanced by modality patch; nothing to do.
    }
  }, [modality, hosting])

  const handlePick = (h: Hosting) => {
    patchDraft({ hosting: h })
  }

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h3 className="text-base font-semibold text-white mb-1">Where does it run?</h3>
        <p className="text-xs text-tsushin-slate">Pick the hosting model. You can add more instances later.</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {OPTIONS.map(opt => {
          const Icon = opt.Icon
          const active = hosting === opt.id
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
