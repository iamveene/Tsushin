'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { CustomSkill } from '@/lib/client'
import { BUILT_IN_SKILLS } from '../defaults'

export default function StepSkills() {
  const { state, patchSkills, markStepComplete } = useAgentWizard()
  const [customSkills, setCustomSkills] = useState<CustomSkill[]>([])

  useEffect(() => {
    api.getCustomSkills().then(setCustomSkills).catch(() => setCustomSkills([]))
  }, [])

  const agentType = state.draft.type
  const available = useMemo(() => {
    if (!agentType) return []
    return BUILT_IN_SKILLS.filter(s => s.appliesTo.includes(agentType))
  }, [agentType])

  // Auto-enable skills that are locked for audio/hybrid
  useEffect(() => {
    if (!agentType) return
    const next = { ...state.draft.skills.builtIns }
    let changed = false
    for (const s of BUILT_IN_SKILLS) {
      if (s.autoEnabledFor?.includes(agentType) && !next[s.type]?.is_enabled) {
        next[s.type] = { is_enabled: true, config: next[s.type]?.config || {} }
        changed = true
      }
    }
    if (changed) patchSkills({ builtIns: next })
    // Skills step is always valid; mark it complete
    markStepComplete('skills', true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentType])

  const isLocked = (skillType: string) => {
    const def = BUILT_IN_SKILLS.find(s => s.type === skillType)
    return !!def?.autoEnabledFor?.includes(agentType!)
  }

  const toggleBuiltin = (skillType: string) => {
    if (isLocked(skillType)) return
    const current = state.draft.skills.builtIns[skillType]
    const nextEnabled = !(current?.is_enabled ?? false)
    patchSkills({
      builtIns: {
        ...state.draft.skills.builtIns,
        [skillType]: { is_enabled: nextEnabled, config: current?.config || {} },
      },
    })
  }

  const toggleCustom = (id: number) => {
    const ids = new Set(state.draft.skills.customIds)
    if (ids.has(id)) ids.delete(id)
    else ids.add(id)
    patchSkills({ customIds: Array.from(ids) })
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">Pick the skills it can use</h3>
        <p className="text-sm text-gray-300">You can always change these later from the agent's page.</p>
      </div>

      <div className="space-y-2">
        <div className="text-xs text-gray-500 uppercase tracking-wider">Built-in</div>
        {available.map(s => {
          const enabled = state.draft.skills.builtIns[s.type]?.is_enabled ?? false
          const locked = isLocked(s.type)
          return (
            <label
              key={s.type}
              className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                enabled ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              } ${locked ? 'opacity-80' : ''}`}
            >
              <input
                type="checkbox"
                checked={enabled}
                disabled={locked}
                onChange={() => toggleBuiltin(s.type)}
                className="mt-0.5"
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <div className="text-white text-sm font-medium">{s.label}</div>
                  {locked && <span className="px-2 py-0.5 text-xs rounded-full bg-white/10 text-gray-300">Required for this type</span>}
                </div>
                <div className="text-xs text-gray-400 mt-0.5">{s.description}</div>
              </div>
            </label>
          )
        })}
      </div>

      {customSkills.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs text-gray-500 uppercase tracking-wider">Custom</div>
          {customSkills.map(cs => {
            const selected = state.draft.skills.customIds.includes(cs.id)
            return (
              <label
                key={cs.id}
                className={`flex items-start gap-3 p-3 rounded-xl border cursor-pointer transition-colors ${
                  selected ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
                }`}
              >
                <input type="checkbox" checked={selected} onChange={() => toggleCustom(cs.id)} className="mt-0.5" />
                <div className="flex-1">
                  <div className="text-white text-sm font-medium">{cs.name}</div>
                  {cs.description && <div className="text-xs text-gray-400 mt-0.5">{cs.description}</div>}
                </div>
              </label>
            )
          })}
        </div>
      )}

      <div className="text-xs text-gray-500">
        Selecting zero skills is fine — you can add them later.
      </div>
    </div>
  )
}
