'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { Persona, TonePreset } from '@/lib/client'
import type { StepKey } from '@/lib/agent-wizard/reducer'
import { useCreateAgentChain } from '../hooks/useCreateAgentChain'

const SECTION_STEP: Array<{ key: StepKey; label: string }> = [
  { key: 'basics', label: 'Basics' },
  { key: 'personality', label: 'Personality' },
  { key: 'audio', label: 'Voice' },
  { key: 'skills', label: 'Skills' },
  { key: 'memory', label: 'Memory' },
  { key: 'channels', label: 'Channels' },
]

export default function StepReview() {
  const wiz = useAgentWizard()
  const { state, stepOrder, goToStep, markStepComplete } = wiz
  const chain = useCreateAgentChain()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [tones, setTones] = useState<TonePreset[]>([])
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    Promise.all([
      api.getPersonas().catch(() => []),
      api.getTonePresets().catch(() => []),
    ]).then(([p, t]) => { setPersonas(p); setTones(t) })
    markStepComplete('review', true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const personaName = useMemo(() => {
    if (!state.draft.personality.persona_id) return '—'
    return personas.find(p => p.id === state.draft.personality.persona_id)?.name || '—'
  }, [personas, state.draft.personality.persona_id])

  const toneLabel = useMemo(() => {
    if (state.draft.personality.custom_tone) return `Custom: ${state.draft.personality.custom_tone.slice(0, 40)}…`
    if (!state.draft.personality.tone_preset_id) return '—'
    return tones.find(t => t.id === state.draft.personality.tone_preset_id)?.name || '—'
  }, [tones, state.draft.personality.tone_preset_id, state.draft.personality.custom_tone])

  const skillLabels = Object.entries(state.draft.skills.builtIns).filter(([, v]) => v.is_enabled).map(([k]) => k)
  if (state.draft.skills.customIds.length) skillLabels.push(`+${state.draft.skills.customIds.length} custom`)

  const handleCreate = async () => {
    setCreating(true)
    // Advance to progress step immediately so spinner shows
    goToStep('progress')
    await chain.run()
    setCreating(false)
  }

  const sections = SECTION_STEP.filter(s => stepOrder.includes(s.key))

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">Ready to create?</h3>
        <p className="text-sm text-gray-300">Review the selections below. Click any section to jump back and edit.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {sections.map(s => (
          <button
            key={s.key}
            type="button"
            onClick={() => goToStep(s.key)}
            className="text-left p-3 rounded-xl border border-white/10 bg-white/[0.02] hover:border-teal-400/40 transition-colors"
          >
            <div className="flex items-center justify-between">
              <div className="text-xs text-gray-500 uppercase tracking-wider">{s.label}</div>
              <span className="text-xs text-teal-400">Edit</span>
            </div>
            <div className="text-sm text-white mt-1">
              {s.key === 'basics' && (
                <>
                  <div>{state.draft.basics.agent_name || '—'}</div>
                  <div className="text-xs text-gray-400">
                    {state.draft.basics.model_provider || '—'} / {state.draft.basics.model_name || '—'}
                  </div>
                </>
              )}
              {s.key === 'personality' && (
                <>
                  <div>{state.draft.personality.skip_persona ? 'Custom prompt' : `Persona: ${personaName}`}</div>
                  <div className="text-xs text-gray-400">Tone: {toneLabel}</div>
                </>
              )}
              {s.key === 'audio' && state.draft.audio && (
                <>
                  <div className="capitalize">{state.draft.audio.capability} · {state.draft.audio.provider}</div>
                  <div className="text-xs text-gray-400">{state.draft.audio.language} · {state.draft.audio.voice}</div>
                  {state.draft.audio.model && (
                    <div className="text-xs text-gray-400 font-mono">model: {state.draft.audio.model}</div>
                  )}
                </>
              )}
              {s.key === 'skills' && (
                <div className="text-xs">{skillLabels.length ? skillLabels.join(', ') : 'None'}</div>
              )}
              {s.key === 'memory' && (
                <>
                  <div className="capitalize">{state.draft.memory.mode}</div>
                  <div className="text-xs text-gray-400">{state.draft.memory.memory_size} turns{state.draft.memory.enable_semantic_search ? ' · semantic' : ''}</div>
                </>
              )}
              {s.key === 'channels' && (
                <div className="text-xs">{state.draft.channels.join(', ')}</div>
              )}
            </div>
          </button>
        ))}
      </div>

      <div className="flex items-center justify-end pt-2">
        <button
          type="button"
          onClick={handleCreate}
          disabled={creating}
          className="px-5 py-2.5 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors disabled:opacity-50"
        >
          {creating ? 'Creating…' : 'Create Agent'}
        </button>
      </div>
    </div>
  )
}
