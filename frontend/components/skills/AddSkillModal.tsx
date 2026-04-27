'use client'

import React, { useState, useMemo } from 'react'
import { SkillDefinition } from '@/lib/client'
import { SearchIcon, WrenchIcon, IconProps } from '@/components/ui/icons'
import {
  SKILL_CATEGORIES, SKILL_DISPLAY_INFO, HIDDEN_SKILLS, COMPOSITE_SKILLS,
  SPECIAL_RENDERED_SKILLS, getSkillDisplay, SkillCategory,
} from './skill-constants'

interface AddSkillModalProps {
  isOpen: boolean
  onClose: () => void
  onAddBuiltinSkill: (skillType: string) => void
  onAddCustomSkill: (customSkillId: number) => void
  availableSkills: SkillDefinition[]
  enabledSkillTypes: Set<string>
  availableCustomSkills: any[]
  assignedCustomSkillIds: Set<number>
}

export default function AddSkillModal({
  isOpen,
  onClose,
  onAddBuiltinSkill,
  onAddCustomSkill,
  availableSkills,
  enabledSkillTypes,
  availableCustomSkills,
  assignedCustomSkillIds,
}: AddSkillModalProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState<SkillCategory | 'all' | 'custom'>('all')

  // Compute available (not yet added) built-in skills
  const unaddedSkills = useMemo(() => {
    // Collect all skill types that are already covered by enabled state
    const coveredSkills = new Set(enabledSkillTypes)

    // Build list of addable skills
    const addable: { skillType: string; displayName: string; description: string; icon: React.FC<IconProps>; category: SkillCategory; isComposite?: boolean }[] = []

    // Check composite skills first (Audio = TTS + Transcript)
    for (const [compositeKey, composite] of Object.entries(COMPOSITE_SKILLS)) {
      const anyEnabled = composite.skillTypes.some(st => enabledSkillTypes.has(st))
      if (!anyEnabled) {
        addable.push({
          skillType: compositeKey,
          displayName: composite.displayName,
          description: composite.description,
          icon: composite.icon,
          category: SKILL_DISPLAY_INFO[composite.skillTypes[0]]?.category || 'audio_media',
          isComposite: true,
        })
      }
      // Mark composite sub-skills as covered so they don't show individually
      composite.skillTypes.forEach(st => coveredSkills.add(st))
    }

    // Check provider skills (flows → Scheduler, gmail → Email, web_search → Web Search)
    const providerSkillTypes = new Set(['flows', 'gmail', 'web_search'])

    for (const skill of availableSkills) {
      if (HIDDEN_SKILLS.has(skill.skill_type)) continue
      if (coveredSkills.has(skill.skill_type)) continue
      if (enabledSkillTypes.has(skill.skill_type)) continue

      const display = getSkillDisplay(skill.skill_type, skill.skill_name, skill.skill_description)

      // Provider skills: check by their provider key mapping
      if (providerSkillTypes.has(skill.skill_type)) {
        addable.push({
          skillType: skill.skill_type,
          displayName: display.displayName,
          description: display.description,
          icon: display.icon,
          category: display.category,
        })
        continue
      }

      // Standard skills not already covered
      // BUG-273: 'shell' is SPECIAL_RENDERED but we still want it addable from the modal
      // so users can enable per-agent shell command execution.
      if (!SPECIAL_RENDERED_SKILLS.has(skill.skill_type) || skill.skill_type === 'shell') {
        addable.push({
          skillType: skill.skill_type,
          displayName: display.displayName,
          description: display.description,
          icon: display.icon,
          category: display.category,
        })
      }
    }

    return addable
  }, [availableSkills, enabledSkillTypes])

  // Compute available (not yet assigned) custom skills
  const unassignedCustomSkills = useMemo(() => {
    return availableCustomSkills.filter(
      (s: any) => !assignedCustomSkillIds.has(s.id) && s.is_enabled
    )
  }, [availableCustomSkills, assignedCustomSkillIds])

  // Filter by search and category
  const filteredSkills = useMemo(() => {
    let skills = unaddedSkills
    if (selectedCategory !== 'all' && selectedCategory !== 'custom') {
      skills = skills.filter(s => s.category === selectedCategory)
    }
    if (selectedCategory === 'custom') {
      skills = [] // Only show custom skills
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      skills = skills.filter(s =>
        s.displayName.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q)
      )
    }
    return skills
  }, [unaddedSkills, selectedCategory, searchQuery])

  const filteredCustomSkills = useMemo(() => {
    if (selectedCategory !== 'all' && selectedCategory !== 'custom') return []
    if (!searchQuery) return unassignedCustomSkills
    const q = searchQuery.toLowerCase()
    return unassignedCustomSkills.filter((s: any) =>
      s.name?.toLowerCase().includes(q) ||
      s.description?.toLowerCase().includes(q)
    )
  }, [unassignedCustomSkills, selectedCategory, searchQuery])

  const totalAvailable = unaddedSkills.length + unassignedCustomSkills.length

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-tsushin-surface rounded-xl max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col shadow-2xl">
        {/* Header */}
        <div className="bg-gradient-to-r from-teal-600 to-cyan-600 px-6 py-4 flex justify-between items-center">
          <div>
            <h3 className="text-lg font-semibold text-white">Add Skill</h3>
            <p className="text-sm text-white/70">{totalAvailable} skill{totalAvailable !== 1 ? 's' : ''} available</p>
          </div>
          <button onClick={onClose} className="text-white/80 hover:text-white text-xl">
            &#x2715;
          </button>
        </div>

        {/* Search */}
        <div className="px-6 pt-4 pb-2">
          <div className="relative">
            <SearchIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-tsushin-muted" />
            <input
              type="text"
              placeholder="Search skills..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 bg-tsushin-ink border border-tsushin-border rounded-lg text-white text-sm focus:border-teal-500 focus:outline-none"
              autoFocus
            />
          </div>
        </div>

        {/* Category tabs */}
        <div className="px-6 pb-3 flex gap-1.5 flex-wrap">
          <button
            onClick={() => setSelectedCategory('all')}
            className={`px-3 py-1 text-xs rounded-full transition-colors ${
              selectedCategory === 'all'
                ? 'bg-teal-600 text-white'
                : 'bg-tsushin-elevated text-tsushin-muted hover:text-white'
            }`}
          >
            All
          </button>
          {Object.entries(SKILL_CATEGORIES).map(([key, cat]) => {
            const count = unaddedSkills.filter(s => s.category === key).length
            if (count === 0) return null
            return (
              <button
                key={key}
                onClick={() => setSelectedCategory(key as SkillCategory)}
                className={`px-3 py-1 text-xs rounded-full transition-colors ${
                  selectedCategory === key
                    ? 'bg-teal-600 text-white'
                    : 'bg-tsushin-elevated text-tsushin-muted hover:text-white'
                }`}
              >
                {cat.label} ({count})
              </button>
            )
          })}
          {unassignedCustomSkills.length > 0 && (
            <button
              onClick={() => setSelectedCategory('custom')}
              className={`px-3 py-1 text-xs rounded-full transition-colors ${
                selectedCategory === 'custom'
                  ? 'bg-teal-600 text-white'
                  : 'bg-tsushin-elevated text-tsushin-muted hover:text-white'
              }`}
            >
              Custom ({unassignedCustomSkills.length})
            </button>
          )}
        </div>

        {/* Skills grid */}
        <div className="overflow-y-auto flex-1 px-6 pb-6">
          {filteredSkills.length === 0 && filteredCustomSkills.length === 0 ? (
            <div className="text-center py-12 text-tsushin-muted text-sm">
              {totalAvailable === 0
                ? 'All skills are already added to this agent.'
                : 'No skills match your search.'}
            </div>
          ) : (
            <div className="space-y-4">
              {/* Built-in skills */}
              {filteredSkills.length > 0 && (
                <div>
                  {selectedCategory === 'all' && filteredCustomSkills.length > 0 && (
                    <h4 className="text-xs font-medium text-tsushin-muted uppercase tracking-wider mb-3">Built-in Skills</h4>
                  )}
                  <div className="grid gap-3 md:grid-cols-2">
                    {filteredSkills.map((skill) => {
                      const Icon = skill.icon
                      return (
                        <button
                          key={skill.skillType}
                          onClick={() => {
                            if (skill.isComposite) {
                              // For composite skills, add the first sub-skill
                              const composite = COMPOSITE_SKILLS[skill.skillType]
                              if (composite) {
                                onAddBuiltinSkill(composite.skillTypes[0])
                              }
                            } else {
                              onAddBuiltinSkill(skill.skillType)
                            }
                          }}
                          className="text-left p-4 rounded-lg border border-tsushin-border hover:border-teal-500 hover:bg-teal-900/10 transition-all group"
                        >
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5 text-tsushin-muted group-hover:text-teal-400 transition-colors">
                              <Icon size={20} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-white text-sm group-hover:text-teal-300 transition-colors">
                                {skill.displayName}
                              </div>
                              <div className="text-xs text-tsushin-muted mt-1 line-clamp-2">
                                {skill.description}
                              </div>
                            </div>
                            <span className="text-xs text-teal-500 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap mt-0.5">
                              + Add
                            </span>
                          </div>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}

              {/* Custom skills */}
              {filteredCustomSkills.length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-tsushin-muted uppercase tracking-wider mb-3 mt-2">Custom Skills</h4>
                  <div className="grid gap-3 md:grid-cols-2">
                    {filteredCustomSkills.map((skill: any) => (
                      <button
                        key={skill.id}
                        onClick={() => onAddCustomSkill(skill.id)}
                        className="text-left p-4 rounded-lg border border-tsushin-border hover:border-teal-500 hover:bg-teal-900/10 transition-all group"
                      >
                        <div className="flex items-start gap-3">
                          <div className="w-8 h-8 rounded-lg bg-violet-500/15 border border-violet-500/20 flex items-center justify-center shrink-0 mt-0.5">
                            <WrenchIcon size={14} className="text-violet-400" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-white text-sm group-hover:text-teal-300 transition-colors">
                              {skill.name}
                            </div>
                            <div className="text-xs text-tsushin-muted mt-0.5">
                              {skill.skill_type_variant} &middot; {skill.execution_mode}
                            </div>
                            {skill.description && (
                              <div className="text-xs text-tsushin-slate mt-1 line-clamp-2">
                                {skill.description}
                              </div>
                            )}
                          </div>
                          <span className="text-xs text-teal-500 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap mt-0.5">
                            + Add
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="bg-tsushin-ink px-6 py-3 border-t border-tsushin-border">
          <button
            onClick={onClose}
            className="w-full px-4 py-2 text-tsushin-slate hover:bg-tsushin-surface rounded-lg text-sm"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
