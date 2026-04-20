'use client'

import { useEffect, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { Persona, TonePreset } from '@/lib/client'
import { isPersonalityValid } from '@/lib/agent-wizard/reducer'
import { STARTER_ROLE_PRESETS, DEFAULT_SYSTEM_PROMPT } from '../defaults'

export default function StepPersonality() {
  const { state, patchPersonality, markStepComplete } = useAgentWizard()
  const [personas, setPersonas] = useState<Persona[]>([])
  const [tonePresets, setTonePresets] = useState<TonePreset[]>([])
  const [loaded, setLoaded] = useState(false)

  // Seed the default system prompt synchronously on mount so the Next button
  // is enabled as soon as this step renders (previously the seed happened inside
  // the Promise.then below, leaving the step invalid until the API resolved and
  // forcing users to re-click the already-selected "Use persona + tone" pill to
  // trigger a re-render after the seed had landed).
  useEffect(() => {
    if (!state.draft.personality.system_prompt && state.draft.type) {
      patchPersonality({ system_prompt: DEFAULT_SYSTEM_PROMPT[state.draft.type] })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    Promise.all([
      api.getPersonas().catch(() => []),
      api.getTonePresets().catch(() => []),
    ]).then(([p, t]) => {
      setPersonas(p)
      setTonePresets(t)
      setLoaded(true)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    markStepComplete('personality', isPersonalityValid(state.draft.personality))
  }, [state.draft.personality, markStepComplete])

  const presets = state.draft.type ? STARTER_ROLE_PRESETS[state.draft.type] : []

  const toggleSkipPersona = (skip: boolean) => {
    patchPersonality({ skip_persona: skip, persona_id: skip ? null : state.draft.personality.persona_id })
  }

  const [useCustomTone, setUseCustomTone] = useState<boolean>(!!state.draft.personality.custom_tone)

  useEffect(() => {
    // Keep the custom/preset tone fields mutually exclusive
    if (useCustomTone) patchPersonality({ tone_preset_id: null })
    else patchPersonality({ custom_tone: '' })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [useCustomTone])

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">Give your agent a personality</h3>
        <p className="text-sm text-gray-300">Pick a persona and tone, or skip and write your own prompt.</p>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => toggleSkipPersona(false)}
          className={`px-3 py-1.5 text-xs rounded-full transition-colors ${!state.draft.personality.skip_persona ? 'bg-teal-500 text-white' : 'bg-white/5 text-gray-400 hover:bg-white/10'}`}
        >
          Use persona + tone
        </button>
        <button
          type="button"
          onClick={() => toggleSkipPersona(true)}
          className={`px-3 py-1.5 text-xs rounded-full transition-colors ${state.draft.personality.skip_persona ? 'bg-teal-500 text-white' : 'bg-white/5 text-gray-400 hover:bg-white/10'}`}
        >
          Skip — write my own prompt
        </button>
      </div>

      {!state.draft.personality.skip_persona && (
        <>
          {!loaded && <div className="text-xs text-gray-500">Loading personas…</div>}
          {loaded && personas.length === 0 && (
            <div className="p-3 rounded-lg bg-white/[0.02] border border-white/5 text-sm text-gray-300">
              No personas seeded yet. You can still set a tone and system prompt below.
            </div>
          )}
          {loaded && personas.length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Persona</label>
              <select
                value={state.draft.personality.persona_id ?? ''}
                onChange={e => patchPersonality({ persona_id: e.target.value ? Number(e.target.value) : null })}
                className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
              >
                <option value="">No persona</option>
                {personas.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs text-gray-400">Tone</label>
              <label className="flex items-center gap-2 text-xs text-gray-400">
                <input type="checkbox" checked={useCustomTone} onChange={e => setUseCustomTone(e.target.checked)} />
                Use custom tone
              </label>
            </div>
            {useCustomTone ? (
              <textarea
                value={state.draft.personality.custom_tone}
                onChange={e => patchPersonality({ custom_tone: e.target.value })}
                placeholder="e.g., Warm, slightly formal, never uses slang."
                rows={2}
                className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
              />
            ) : (
              <select
                value={state.draft.personality.tone_preset_id ?? ''}
                onChange={e => patchPersonality({ tone_preset_id: e.target.value ? Number(e.target.value) : null })}
                className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
              >
                <option value="">No tone preset</option>
                {tonePresets.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            )}
          </div>
        </>
      )}

      <div>
        <label className="block text-xs text-gray-400 mb-1">System prompt {state.draft.personality.skip_persona ? '*' : '(optional)'}</label>
        {presets.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-2">
            {presets.map(preset => (
              <button
                key={preset.label}
                type="button"
                onClick={() => patchPersonality({ system_prompt: preset.prompt })}
                className="px-2.5 py-1 text-xs rounded-full bg-white/5 hover:bg-teal-500/20 hover:text-teal-200 text-gray-300 transition-colors"
              >
                {preset.label}
              </button>
            ))}
          </div>
        )}
        <textarea
          value={state.draft.personality.system_prompt}
          onChange={e => patchPersonality({ system_prompt: e.target.value })}
          rows={5}
          placeholder="You are a helpful assistant…"
          className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400 font-mono text-xs leading-relaxed"
        />
        <div className="text-xs text-gray-500 mt-1">
          {state.draft.personality.system_prompt.trim().length} chars · needs at least 20 when no persona is selected
        </div>
      </div>
    </div>
  )
}
