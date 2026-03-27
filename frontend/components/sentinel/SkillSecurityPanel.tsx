'use client'

import React, { useEffect, useState, useCallback } from 'react'
import { api, AgentSkill, SentinelProfileAssignment, SentinelProfile } from '@/lib/client'
import EffectiveSecurityConfig from '@/components/EffectiveSecurityConfig'

interface SkillSecurityPanelProps {
  agentId: number
  profiles: SentinelProfile[]
  canEdit: boolean
  onAssignmentChange?: () => void
}

export default function SkillSecurityPanel({ agentId, profiles, canEdit, onAssignmentChange }: SkillSecurityPanelProps) {
  const [skills, setSkills] = useState<AgentSkill[]>([])
  const [assignments, setAssignments] = useState<SentinelProfileAssignment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingSkill, setEditingSkill] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  const [expandedSkill, setExpandedSkill] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [skillsData, assignmentsData] = await Promise.all([
        api.getAgentSkills(agentId),
        api.getSentinelProfileAssignments(agentId),
      ])
      setSkills(skillsData.filter(s => s.is_enabled))
      setAssignments(assignmentsData)
    } catch (err: any) {
      setError(err.message || 'Failed to load skill data')
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    loadData()
  }, [loadData])

  const getSkillAssignment = (skillType: string): SentinelProfileAssignment | undefined => {
    return assignments.find(a => a.skill_type === skillType)
  }

  const handleAssign = async (skillType: string, profileId: number | null) => {
    setSaving(skillType)
    try {
      const existing = getSkillAssignment(skillType)

      if (profileId === null) {
        // Remove assignment (inherit from agent)
        if (existing) {
          await api.removeSentinelProfileAssignment(existing.id)
        }
      } else {
        // Assign profile
        await api.assignSentinelProfile({
          profile_id: profileId,
          agent_id: agentId,
          skill_type: skillType,
        })
      }

      setEditingSkill(null)
      await loadData()
      onAssignmentChange?.()
    } catch (err: any) {
      setError(err.message || 'Failed to update assignment')
    } finally {
      setSaving(null)
    }
  }

  const formatSkillName = (skillType: string): string => {
    return skillType
      .split('_')
      .map(w => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ')
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4">
        <div className="w-4 h-4 border-2 border-gray-600 border-t-teal-400 rounded-full animate-spin" />
        <span className="text-sm text-tsushin-slate">Loading skills...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 py-4">
        <span className="text-sm text-red-400">{error}</span>
        <button onClick={loadData} className="text-xs text-teal-400 hover:text-teal-300 underline">Retry</button>
      </div>
    )
  }

  if (skills.length === 0) {
    return (
      <div className="py-4 text-center">
        <p className="text-sm text-tsushin-slate">No enabled skills for this agent.</p>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {skills.map((skill) => {
        const assignment = getSkillAssignment(skill.skill_type)
        const isEditing = editingSkill === skill.skill_type
        const isSaving = saving === skill.skill_type
        const isExpanded = expandedSkill === skill.skill_type

        return (
          <div key={skill.skill_type} className="rounded-lg border border-gray-700/50 bg-gray-800/30">
            {/* Skill Row */}
            <div className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-7 h-7 rounded-md bg-purple-500/15 flex items-center justify-center flex-shrink-0">
                  <svg className="w-3.5 h-3.5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white truncate">{formatSkillName(skill.skill_type)}</p>
                  <p className="text-xs text-tsushin-muted truncate">{skill.skill_type}</p>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                {/* Assignment Badge */}
                {assignment ? (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
                    {assignment.profile_name || 'Custom'}
                  </span>
                ) : (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-gray-500/20 text-gray-400 border border-dashed border-gray-500/50">
                    Inherited
                  </span>
                )}

                {/* Expand Config Button */}
                <button
                  onClick={() => setExpandedSkill(isExpanded ? null : skill.skill_type)}
                  className="p-1 rounded hover:bg-gray-700/50 text-tsushin-slate hover:text-white transition-colors"
                  title="View effective config"
                >
                  <svg
                    className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {/* Edit Button */}
                {canEdit && (
                  <button
                    onClick={() => setEditingSkill(isEditing ? null : skill.skill_type)}
                    className={`p-1 rounded transition-colors ${
                      isEditing
                        ? 'bg-teal-500/20 text-teal-400'
                        : 'hover:bg-gray-700/50 text-tsushin-slate hover:text-white'
                    }`}
                    title="Edit assignment"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                    </svg>
                  </button>
                )}
              </div>
            </div>

            {/* Inline Editor */}
            {isEditing && (
              <div className="px-4 pb-3 border-t border-gray-700/50 pt-3">
                <div className="space-y-2">
                  {/* Inherit Option */}
                  <button
                    onClick={() => handleAssign(skill.skill_type, null)}
                    disabled={isSaving}
                    className={`w-full text-left px-3 py-2 rounded-lg border transition-all text-sm ${
                      !assignment
                        ? 'border-teal-500/50 bg-teal-500/10 text-teal-400'
                        : 'border-gray-700 hover:border-gray-600 text-gray-300 hover:text-white'
                    } ${isSaving ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <div className="flex items-center gap-2">
                      <div className={`w-3 h-3 rounded-full border-2 flex items-center justify-center ${
                        !assignment ? 'border-teal-400' : 'border-gray-500'
                      }`}>
                        {!assignment && <div className="w-1.5 h-1.5 rounded-full bg-teal-400" />}
                      </div>
                      Inherit from Agent
                    </div>
                  </button>

                  {/* Profile Options */}
                  {profiles.map((p) => {
                    const isSelected = assignment?.profile_id === p.id
                    return (
                      <button
                        key={p.id}
                        onClick={() => handleAssign(skill.skill_type, p.id)}
                        disabled={isSaving}
                        className={`w-full text-left px-3 py-2 rounded-lg border transition-all text-sm ${
                          isSelected
                            ? 'border-blue-500/50 bg-blue-500/10 text-blue-400'
                            : 'border-gray-700 hover:border-gray-600 text-gray-300 hover:text-white'
                        } ${isSaving ? 'opacity-50 cursor-not-allowed' : ''}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className={`w-3 h-3 rounded-full border-2 flex items-center justify-center ${
                              isSelected ? 'border-blue-400' : 'border-gray-500'
                            }`}>
                              {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-blue-400" />}
                            </div>
                            {p.name}
                          </div>
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs text-gray-500">{p.detection_mode}</span>
                            {p.is_system && (
                              <span className="text-xs px-1.5 py-0.5 rounded bg-orange-500/20 text-orange-400">System</span>
                            )}
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>

                {isSaving && (
                  <div className="flex items-center gap-2 mt-2 text-xs text-tsushin-slate">
                    <div className="w-3 h-3 border-2 border-gray-600 border-t-teal-400 rounded-full animate-spin" />
                    Saving...
                  </div>
                )}
              </div>
            )}

            {/* Expanded Effective Config */}
            {isExpanded && (
              <div className="px-4 pb-3 border-t border-gray-700/50 pt-3">
                <EffectiveSecurityConfig agentId={agentId} skillType={skill.skill_type} compact />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
