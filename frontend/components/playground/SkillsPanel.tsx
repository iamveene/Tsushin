'use client'

/**
 * Skills Panel - Shows enabled skills for the selected agent
 * Part of the playground inspector panel
 */

import React, { useState, useEffect } from 'react'
import {
  MicrophoneIcon,
  VolumeIcon,
  EyeIcon,
  GlobeIcon,
  ComputerIcon,
  FileIcon,
  BookIcon,
  BrainIcon,
  LightningIcon,
  TargetIcon,
  AlertTriangleIcon,
  PlugIcon,
  IconProps
} from '@/components/ui/icons'

interface AgentSkill {
  id: number
  skill_type: string
  is_enabled: boolean
  config: Record<string, any>
  created_at: string | null
  updated_at: string | null
}

interface AvailableSkill {
  skill_type: string
  skill_name: string
  skill_description: string
  config_schema: Record<string, any>
  default_config: Record<string, any>
}

interface SkillsPanelProps {
  agentId: number | null
}

const SKILL_ICON_COMPONENTS: Record<string, React.FC<IconProps>> = {
  'transcript': MicrophoneIcon,
  'tts': VolumeIcon,
  'vision': EyeIcon,
  'web_search': GlobeIcon,
  'code_execution': ComputerIcon,
  'file_analysis': FileIcon,
  'knowledge_base': BookIcon,
  'memory': BrainIcon,
  'default': LightningIcon
}

export default function SkillsPanel({ agentId }: SkillsPanelProps) {
  const [agentSkills, setAgentSkills] = useState<AgentSkill[]>([])
  const [availableSkills, setAvailableSkills] = useState<AvailableSkill[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (agentId) {
      loadSkills()
    } else {
      setAgentSkills([])
    }
  }, [agentId])

  const loadSkills = async () => {
    if (!agentId) return
    setLoading(true)
    setError(null)

    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8081'
      const token = localStorage.getItem('tsushin_auth_token')
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }

      // Fetch both agent skills and available skills
      const [agentRes, availableRes] = await Promise.all([
        fetch(`${baseUrl}/api/agents/${agentId}/skills`, { headers }),
        fetch(`${baseUrl}/api/skills/available`, { headers })
      ])

      if (agentRes.ok) {
        const agentData = await agentRes.json()
        setAgentSkills(agentData.skills || [])
      }

      if (availableRes.ok) {
        const availableData = await availableRes.json()
        setAvailableSkills(availableData.skills || [])
      }
    } catch (err: any) {
      console.error('Failed to load skills:', err)
      setError(err.message || 'Failed to load skills')
    } finally {
      setLoading(false)
    }
  }

  const getSkillIcon = (skillType: string, size: number = 18, className: string = '') => {
    const IconComponent = SKILL_ICON_COMPONENTS[skillType] || SKILL_ICON_COMPONENTS.default
    return <IconComponent size={size} className={className} />
  }

  const getSkillName = (skillType: string) => {
    const available = availableSkills.find(s => s.skill_type === skillType)
    if (available) return available.skill_name
    // Fallback formatting
    return skillType.split('_').map(word =>
      word.charAt(0).toUpperCase() + word.slice(1)
    ).join(' ')
  }

  const getSkillDescription = (skillType: string) => {
    const available = availableSkills.find(s => s.skill_type === skillType)
    return available?.skill_description || ''
  }

  const enabledSkills = agentSkills.filter(s => s.is_enabled)
  const disabledSkills = agentSkills.filter(s => !s.is_enabled)

  if (!agentId) {
    return (
      <div className="h-full flex items-center justify-center text-[var(--pg-text-muted)]">
        <div className="text-center px-4">
          <span className="block mb-2"><TargetIcon size={48} className="mx-auto" /></span>
          <p className="text-sm">Select an agent to view skills</p>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="flex items-center gap-3 text-[var(--pg-text-secondary)]">
          <div className="w-5 h-5 border-2 border-[var(--pg-accent)] border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading skills...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center px-4">
          <span className="block mb-2 text-[var(--pg-error)]"><AlertTriangleIcon size={48} className="mx-auto" /></span>
          <p className="text-sm text-[var(--pg-error)]">{error}</p>
          <button
            onClick={loadSkills}
            className="mt-3 px-3 py-1.5 text-xs bg-[var(--pg-surface)] border border-[var(--pg-border)] rounded-lg hover:bg-[var(--pg-elevated)] transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--pg-border)]">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[var(--pg-text)]">Agent Skills</h3>
          <span className="text-xs bg-[var(--pg-surface)] px-2 py-0.5 rounded text-[var(--pg-text-muted)]">
            {enabledSkills.length} enabled
          </span>
        </div>
      </div>

      {/* Skills List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Enabled Skills */}
        {enabledSkills.length > 0 && (
          <div>
            <h4 className="text-xs uppercase tracking-wider text-[var(--pg-success)] mb-2 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-[var(--pg-success)] rounded-full" />
              Enabled
            </h4>
            <div className="space-y-2">
              {enabledSkills.map(skill => (
                <div
                  key={skill.id}
                  className="p-3 bg-[var(--pg-success)]/5 border border-[var(--pg-success)]/20 rounded-lg"
                >
                  <div className="flex items-start gap-3">
                    <span className="text-[var(--pg-success)]">{getSkillIcon(skill.skill_type)}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-[var(--pg-text)]">
                          {getSkillName(skill.skill_type)}
                        </span>
                        <span className="px-1.5 py-0.5 text-[10px] bg-[var(--pg-success)]/20 text-[var(--pg-success)] rounded">
                          ACTIVE
                        </span>
                      </div>
                      <p className="text-xs text-[var(--pg-text-muted)] mt-0.5">
                        {getSkillDescription(skill.skill_type)}
                      </p>
                      {Object.keys(skill.config || {}).length > 0 && (
                        <div className="mt-2 text-xs text-[var(--pg-text-muted)] font-mono bg-[var(--pg-void)]/30 p-2 rounded">
                          {Object.entries(skill.config).slice(0, 3).map(([key, value]) => (
                            <div key={key} className="truncate">
                              <span className="text-[var(--pg-text-secondary)]">{key}:</span>{' '}
                              <span className="text-[var(--pg-accent)]">
                                {typeof value === 'string' ? value : JSON.stringify(value)}
                              </span>
                            </div>
                          ))}
                          {Object.keys(skill.config).length > 3 && (
                            <div className="text-[var(--pg-text-muted)]">
                              +{Object.keys(skill.config).length - 3} more...
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Disabled Skills */}
        {disabledSkills.length > 0 && (
          <div>
            <h4 className="text-xs uppercase tracking-wider text-[var(--pg-text-muted)] mb-2 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-[var(--pg-text-muted)] rounded-full opacity-50" />
              Disabled
            </h4>
            <div className="space-y-2">
              {disabledSkills.map(skill => (
                <div
                  key={skill.id}
                  className="p-3 bg-[var(--pg-surface)] border border-[var(--pg-border)] rounded-lg opacity-60"
                >
                  <div className="flex items-start gap-3">
                    <span className="text-[var(--pg-text-muted)] grayscale">{getSkillIcon(skill.skill_type)}</span>
                    <div className="flex-1 min-w-0">
                      <span className="text-sm font-medium text-[var(--pg-text-secondary)]">
                        {getSkillName(skill.skill_type)}
                      </span>
                      <p className="text-xs text-[var(--pg-text-muted)] mt-0.5">
                        {getSkillDescription(skill.skill_type)}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Available Skills (not configured) */}
        {availableSkills.length > 0 && (
          <div>
            <h4 className="text-xs uppercase tracking-wider text-[var(--pg-info)] mb-2 flex items-center gap-1.5">
              <span className="w-2 h-2 bg-[var(--pg-info)] rounded-full" />
              Available to Enable
            </h4>
            <div className="space-y-2">
              {availableSkills
                .filter(a => !agentSkills.some(s => s.skill_type === a.skill_type))
                .map(skill => (
                  <div
                    key={skill.skill_type}
                    className="p-3 bg-[var(--pg-surface)]/50 border border-[var(--pg-border)] rounded-lg border-dashed"
                  >
                    <div className="flex items-start gap-3">
                      <span className="text-[var(--pg-text-muted)] opacity-50">{getSkillIcon(skill.skill_type)}</span>
                      <div className="flex-1 min-w-0">
                        <span className="text-sm font-medium text-[var(--pg-text-muted)]">
                          {skill.skill_name}
                        </span>
                        <p className="text-xs text-[var(--pg-text-muted)] mt-0.5 opacity-70">
                          {skill.skill_description}
                        </p>
                        <p className="text-[10px] text-[var(--pg-info)] mt-2 opacity-80">
                          Configure in Agent Settings
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {agentSkills.length === 0 && availableSkills.length === 0 && (
          <div className="text-center py-8">
            <span className="block mb-3 text-[var(--pg-text-muted)]"><PlugIcon size={48} className="mx-auto" /></span>
            <p className="text-sm text-[var(--pg-text-secondary)]">No skills configured</p>
            <p className="text-xs text-[var(--pg-text-muted)] mt-1">
              Configure skills in Agent Settings
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-[var(--pg-border)] text-center">
        <a
          href={agentId ? `/agents/${agentId}?tab=skills` : '#'}
          className="text-xs text-[var(--pg-accent)] hover:underline"
        >
          Manage Skills →
        </a>
      </div>
    </div>
  )
}
