'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { CustomSkill, SkillDefinition } from '@/lib/client'
import { BUILT_IN_SKILLS } from '../defaults'
import { SKILL_DISPLAY_INFO, HIDDEN_SKILLS } from '@/components/skills/skill-constants'

// Shape rendered by the wizard — merges backend catalog (skill_type/applies_to/
// auto_enabled_for/wizard_visible/descriptions) with optional frontend decoration
// (display label overrides from skill-constants, or static fallback in BUILT_IN_SKILLS).
interface WizardSkillRow {
  type: string
  label: string
  description: string
  appliesTo: string[]
  autoEnabledFor: string[]
}

// Derive the wizard's skill catalog from the backend's /api/skills/available
// response. This is the single source of truth; the static BUILT_IN_SKILLS list
// is retained ONLY as a fallback when the API is unreachable, and is cross-checked
// against the backend registry by a CI test in backend/tests/test_wizard_drift.py.
function rowsFromBackend(skills: SkillDefinition[]): WizardSkillRow[] {
  return skills
    .filter(s => s.wizard_visible !== false)
    .filter(s => !HIDDEN_SKILLS.has(s.skill_type))
    .map(s => {
      const display = SKILL_DISPLAY_INFO[s.skill_type]
      return {
        type: s.skill_type,
        label: display?.displayName || s.skill_name,
        description: display?.description || s.skill_description,
        appliesTo: s.applies_to || ['text', 'audio', 'hybrid'],
        autoEnabledFor: s.auto_enabled_for || [],
      }
    })
}

function rowsFromFallback(): WizardSkillRow[] {
  return BUILT_IN_SKILLS.map(s => ({
    type: s.type,
    label: s.label,
    description: s.description,
    appliesTo: s.appliesTo,
    autoEnabledFor: s.autoEnabledFor || [],
  }))
}

export default function StepSkills() {
  const { state, patchSkills, markStepComplete } = useAgentWizard()
  const [customSkills, setCustomSkills] = useState<CustomSkill[]>([])
  const [catalog, setCatalog] = useState<WizardSkillRow[]>(() => rowsFromFallback())

  useEffect(() => {
    api.getCustomSkills().then(setCustomSkills).catch(() => setCustomSkills([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    api.getAvailableSkills()
      .then(skills => {
        if (cancelled) return
        const rows = rowsFromBackend(skills)
        // If the backend returned an empty/degraded list, keep the fallback.
        if (rows.length > 0) setCatalog(rows)
      })
      .catch(() => {
        // Network or auth failure — keep the fallback rows already in state.
      })
    return () => { cancelled = true }
  }, [])

  const agentType = state.draft.type
  const available = useMemo(() => {
    if (!agentType) return []
    return catalog.filter(s => s.appliesTo.includes(agentType))
  }, [agentType, catalog])

  // Auto-enable skills that are locked for audio/hybrid
  useEffect(() => {
    if (!agentType) return
    const next = { ...state.draft.skills.builtIns }
    let changed = false
    for (const s of catalog) {
      if (s.autoEnabledFor.includes(agentType) && !next[s.type]?.is_enabled) {
        next[s.type] = { is_enabled: true, config: next[s.type]?.config || {} }
        changed = true
      }
    }
    if (changed) patchSkills({ builtIns: next })
    // Skills step is always valid; mark it complete
    markStepComplete('skills', true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentType, catalog])

  const isLocked = (skillType: string) => {
    const def = catalog.find(s => s.type === skillType)
    return !!def?.autoEnabledFor.includes(agentType!)
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
