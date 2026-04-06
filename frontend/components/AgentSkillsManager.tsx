'use client'

import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { api, AgentSkill, SkillDefinition, SkillIntegration, SkillProvider, TTSProviderInfo, TTSVoice, AgentTTSConfig, SentinelProfile, SentinelProfileAssignment, AgentSandboxedTool, SandboxedTool } from '@/lib/client'
import { ArrayConfigInput } from './ArrayConfigInput'
import {
  PlugIcon, SettingsIcon, MicrophoneIcon, SpeakerIcon, TerminalIcon, BotIcon,
  WrenchIcon, ClockIcon, RocketIcon, RadioIcon, CalendarIcon, MailIcon,
  SearchIcon, AlertTriangleIcon, CheckIcon, MessageIcon, FileTextIcon,
  IconProps,
} from '@/components/ui/icons'
import AddSkillModal from './skills/AddSkillModal'
import ToggleSwitch from './ui/ToggleSwitch'
import { HIDDEN_SKILLS, SPECIAL_RENDERED_SKILLS, SKILL_DISPLAY_INFO, getSkillDisplay } from './skills/skill-constants'

interface Props {
  agentId: number
}

// Skills that have provider selection
const PROVIDER_SKILLS = {
  'scheduler': { displayName: 'Scheduler', skillType: 'flows', providerKey: 'scheduler' },
  'email': { displayName: 'Email', skillType: 'gmail', providerKey: 'email' },
  'web_search': { displayName: 'Web Search', skillType: 'web_search', providerKey: 'web_search' },
}

// Audio sub-skill tabs
type AudioTab = 'tts' | 'transcript'

export default function AgentSkillsManager({ agentId }: Props) {
  const [availableSkills, setAvailableSkills] = useState<SkillDefinition[]>([])
  const [agentSkills, setAgentSkills] = useState<AgentSkill[]>([])
  const [skillIntegrations, setSkillIntegrations] = useState<SkillIntegration[]>([])
  const [loading, setLoading] = useState(true)
  const [configuring, setConfiguring] = useState<string | null>(null)
  const [configuringProvider, setConfiguringProvider] = useState<string | null>(null)
  const [configData, setConfigData] = useState<Record<string, any>>({})

  // Provider configuration state
  const [schedulerProviders, setSchedulerProviders] = useState<SkillProvider[]>([])
  const [emailProviders, setEmailProviders] = useState<SkillProvider[]>([])
  const [webSearchProviders, setWebSearchProviders] = useState<SkillProvider[]>([])
  const [selectedProvider, setSelectedProvider] = useState<string>('')
  const [selectedIntegration, setSelectedIntegration] = useState<number | null>(null)
  const [providerLoading, setProviderLoading] = useState(false)

  // Permission configuration state (for Google Calendar)
  const [providerPermissions, setProviderPermissions] = useState<{ read: boolean; write: boolean }>({
    read: true,
    write: false
  })

  // Unified Audio skill state
  const [configuringAudio, setConfiguringAudio] = useState(false)
  const [audioTab, setAudioTab] = useState<AudioTab>('tts')

  // TTS Provider state
  const [ttsProviders, setTTSProviders] = useState<TTSProviderInfo[]>([])
  const [ttsVoices, setTTSVoices] = useState<TTSVoice[]>([])
  const [ttsConfig, setTTSConfig] = useState<AgentTTSConfig>({ provider: 'kokoro', voice: 'pf_dora', language: 'pt', speed: 1.0 })

  // Transcript config state
  const [transcriptConfig, setTranscriptConfig] = useState<Record<string, any>>({ language: 'auto', model: 'whisper-1', response_mode: 'conversational' })

  // Shell skill state
  const [configuringShell, setConfiguringShell] = useState(false)
  const [shellConfig, setShellConfig] = useState<Record<string, any>>({ wait_for_result: false, default_timeout: 60 })
  const [shellBeacons, setShellBeacons] = useState<any[]>([])

  // Skill-level security profile state (v1.6.0 Phase E)
  const [securityProfiles, setSecurityProfiles] = useState<SentinelProfile[]>([])
  const [skillSecurityAssignments, setSkillSecurityAssignments] = useState<Map<string, SentinelProfileAssignment | null>>(new Map())
  const [skillSecurityPopover, setSkillSecurityPopover] = useState<string | null>(null)
  const securityPopoverRef = useRef<HTMLDivElement>(null)

  // Phase 24: Custom Skills state
  const [customSkillAssignments, setCustomSkillAssignments] = useState<any[]>([])
  const [availableCustomSkills, setAvailableCustomSkills] = useState<any[]>([])
  const [showCustomSkillPicker, setShowCustomSkillPicker] = useState(false)

  // Add Skill modal state
  const [showAddSkillModal, setShowAddSkillModal] = useState(false)

  // Sandboxed Tools config (embedded in skill config modal)
  const [sandboxedTools, setSandboxedTools] = useState<SandboxedTool[]>([])
  const [agentSandboxedTools, setAgentSandboxedTools] = useState<AgentSandboxedTool[]>([])
  const [sandboxedToolsLoading, setSandboxedToolsLoading] = useState(false)
  const [sandboxedToolUpdating, setSandboxedToolUpdating] = useState<number | null>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [available, agent, integrations, profiles, secAssignments, customAssignments, allCustomSkills] = await Promise.all([
        api.getAvailableSkills(),
        api.getAgentSkills(agentId),
        api.getAgentSkillIntegrations(agentId),
        api.getSentinelProfiles(true).catch(() => [] as SentinelProfile[]),
        api.getSentinelProfileAssignments(agentId).catch(() => [] as SentinelProfileAssignment[]),
        api.getAgentCustomSkills(agentId).catch(() => []),
        api.getCustomSkills().catch(() => []),
      ])
      setAvailableSkills(available)
      setAgentSkills(agent)
      setSkillIntegrations(integrations)
      setCustomSkillAssignments(customAssignments)
      setAvailableCustomSkills(allCustomSkills)
      setSecurityProfiles(profiles)

      // Build skill-level assignment map
      const skillMap = new Map<string, SentinelProfileAssignment | null>()
      for (const skillType of ['shell', 'web_search']) {
        const assignment = secAssignments.find(
          (a: SentinelProfileAssignment) => a.skill_type === skillType
        )
        skillMap.set(skillType, assignment || null)
      }
      setSkillSecurityAssignments(skillMap)
    } catch (err) {
      console.error('Failed to load skills:', err)
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Close security popover on click outside
  useEffect(() => {
    if (!skillSecurityPopover) return
    const handleClick = (e: MouseEvent) => {
      if (securityPopoverRef.current && !securityPopoverRef.current.contains(e.target as Node)) {
        setSkillSecurityPopover(null)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [skillSecurityPopover])

  const isSkillEnabled = (skillType: string): boolean => {
    return agentSkills.some(s => s.skill_type === skillType && s.is_enabled)
  }

  const buildDefaultSkillConfig = (skillDef?: SkillDefinition | null): Record<string, any> => {
    if (!skillDef) return {}

    const schemaDefaults: Record<string, any> = {}
    const schemaProperties = skillDef.config_schema?.properties || {}

    Object.entries(schemaProperties).forEach(([key, schema]) => {
      if ((schema as any).default !== undefined) {
        schemaDefaults[key] = (schema as any).default
      }
    })

    return {
      ...schemaDefaults,
      ...(skillDef.default_config || {}),
    }
  }

  const getSkillConfig = (skillType: string): Record<string, any> => {
    const skill = agentSkills.find(s => s.skill_type === skillType)
    const skillDef = availableSkills.find(s => s.skill_type === skillType)
    return {
      ...buildDefaultSkillConfig(skillDef),
      ...(skill?.config || {}),
    }
  }

  const getSkillIntegration = (skillType: string): SkillIntegration | undefined => {
    return skillIntegrations.find(si => si.skill_type === skillType)
  }

  const toggleSkill = async (skillType: string, enabled: boolean) => {
    try {
      if (enabled) {
        const skillDef = availableSkills.find(s => s.skill_type === skillType)
        const defaultConfig = buildDefaultSkillConfig(skillDef)
        await api.updateAgentSkill(agentId, skillType, { is_enabled: true, config: defaultConfig })
      } else {
        await api.disableAgentSkill(agentId, skillType)
      }
      loadData()
    } catch (err) {
      console.error('Failed to toggle skill:', err)
      alert('Failed to toggle skill')
    }
  }

  // Add a built-in skill and open its config modal
  const addBuiltinSkill = async (skillType: string) => {
    try {
      const skillDef = availableSkills.find(s => s.skill_type === skillType)
      const defaultConfig = buildDefaultSkillConfig(skillDef)
      await api.updateAgentSkill(agentId, skillType, { is_enabled: true, config: defaultConfig })
      setShowAddSkillModal(false)
      await loadData()

      // Open the appropriate config modal
      const info = SKILL_DISPLAY_INFO[skillType]
      if (info?.configType === 'provider' && info.providerKey) {
        openProviderConfig(info.providerKey as 'scheduler' | 'email' | 'web_search')
      } else if (info?.configType === 'audio') {
        openAudioConfig(skillType === 'audio_transcript' ? 'transcript' : 'tts')
      } else if (info?.configType === 'shell') {
        openShellConfig()
      } else {
        openConfig(skillType)
      }
    } catch (err) {
      console.error('Failed to add skill:', err)
      alert('Failed to add skill')
    }
  }

  // Add a custom skill to the agent
  const addCustomSkill = async (customSkillId: number) => {
    try {
      await api.assignCustomSkillToAgent(agentId, customSkillId)
      setShowAddSkillModal(false)
      loadData()
    } catch (err) {
      console.error('Failed to assign custom skill:', err)
      alert('Failed to assign skill')
    }
  }

  // Remove (disable) a built-in skill
  const removeSkill = async (skillType: string, displayName: string) => {
    if (!confirm(`Remove "${displayName}" from this agent?`)) return
    try {
      await api.disableAgentSkill(agentId, skillType)
      loadData()
    } catch (err) {
      console.error('Failed to remove skill:', err)
      alert('Failed to remove skill')
    }
  }

  const openConfig = (skillType: string) => {
    setConfiguring(skillType)
    setConfigData(getSkillConfig(skillType))
    if (skillType === 'sandboxed_tools') {
      loadSandboxedTools()
    }
  }

  const loadSandboxedTools = async () => {
    setSandboxedToolsLoading(true)
    try {
      const [tools, assignments] = await Promise.all([
        api.getSandboxedTools(),
        api.getAgentSandboxedTools(agentId),
      ])
      setSandboxedTools(tools.filter(t => t.is_enabled))
      setAgentSandboxedTools(assignments)
    } catch (err) {
      console.error('Failed to load sandboxed tools:', err)
    } finally {
      setSandboxedToolsLoading(false)
    }
  }

  const isSandboxedToolEnabled = (toolId: number): boolean => {
    return agentSandboxedTools.some(at => at.sandboxed_tool_id === toolId && at.is_enabled)
  }

  const getSandboxedToolMapping = (toolId: number): AgentSandboxedTool | undefined => {
    return agentSandboxedTools.find(at => at.sandboxed_tool_id === toolId)
  }

  const toggleSandboxedTool = async (tool: SandboxedTool, enabled: boolean) => {
    setSandboxedToolUpdating(tool.id)
    try {
      const mapping = getSandboxedToolMapping(tool.id)
      if (enabled) {
        if (mapping) {
          await api.updateAgentSandboxedTool(agentId, mapping.id, { is_enabled: true })
        } else {
          await api.addAgentSandboxedTool(agentId, { sandboxed_tool_id: tool.id, is_enabled: true })
        }
      } else {
        if (mapping) {
          await api.updateAgentSandboxedTool(agentId, mapping.id, { is_enabled: false })
        }
      }
      await loadSandboxedTools()
    } catch (err) {
      console.error('Failed to toggle sandboxed tool:', err)
    } finally {
      setSandboxedToolUpdating(null)
    }
  }

  const openProviderConfig = async (providerKey: 'scheduler' | 'email' | 'web_search') => {
    setProviderLoading(true)
    setConfiguringProvider(providerKey)

    try {
      const providers = await api.getSkillProviders(providerKey)
      if (providerKey === 'scheduler') {
        setSchedulerProviders(providers)
      } else if (providerKey === 'email') {
        setEmailProviders(providers)
      } else if (providerKey === 'web_search') {
        setWebSearchProviders(providers)
      }

      // Load current integration for this skill
      const skillType = PROVIDER_SKILLS[providerKey].skillType
      const integration = getSkillIntegration(skillType)

      if (integration) {
        setSelectedProvider(integration.scheduler_provider || (providerKey === 'web_search' ? 'brave' : (providerKey === 'scheduler' ? 'flows' : 'gmail')))
        setSelectedIntegration(integration.integration_id)

        // Load permissions from config if available
        const permissions = integration.config?.permissions || { read: true, write: true }
        setProviderPermissions(permissions)
      } else {
        // Set default provider
        if (providerKey === 'web_search') {
          setSelectedProvider('brave')
        } else if (providerKey === 'scheduler') {
          setSelectedProvider('flows')
        } else {
          setSelectedProvider('gmail')
        }
        setSelectedIntegration(null)
        // Default permissions: read-only for safety
        setProviderPermissions({ read: true, write: false })
      }
    } catch (err) {
      console.error('Failed to load providers:', err)
      alert('Failed to load providers')
      setConfiguringProvider(null)
    } finally {
      setProviderLoading(false)
    }
  }

  const saveProviderConfig = async () => {
    if (!configuringProvider) return

    try {
      const skillType = PROVIDER_SKILLS[configuringProvider as 'scheduler' | 'email' | 'web_search'].skillType

      // Build config with permissions (for Google Calendar)
      const config: Record<string, any> = {}
      if (configuringProvider === 'scheduler' && selectedProvider === 'google_calendar') {
        config.permissions = providerPermissions
      }

      // For web_search, we need to update the skill config with the provider
      if (configuringProvider === 'web_search') {
        const currentConfig = getSkillConfig(skillType)
        config.provider = selectedProvider

        // Merge with existing config
        Object.assign(config, currentConfig)

        // Update the skill config directly
        await api.updateAgentSkill(agentId, skillType, {
          is_enabled: true,
          config: config
        })
      } else {
        // Save skill integration for scheduler/email
        await api.updateSkillIntegration(agentId, skillType, {
          scheduler_provider: configuringProvider === 'scheduler' ? selectedProvider : null,
          integration_id: selectedIntegration,
          config: Object.keys(config).length > 0 ? config : undefined,
        })

        // Make sure the skill is enabled
        if (!isSkillEnabled(skillType)) {
          const skillDef = availableSkills.find(s => s.skill_type === skillType)
          const defaultConfig: Record<string, any> = {}
          if (skillDef) {
            Object.entries(skillDef.config_schema || {}).forEach(([key, schema]) => {
              defaultConfig[key] = (schema as any).default
            })
          }
          await api.updateAgentSkill(agentId, skillType, { is_enabled: true, config: defaultConfig })
        }
      }

      setConfiguringProvider(null)
      loadData()
    } catch (err) {
      console.error('Failed to save provider config:', err)
      alert('Failed to save provider configuration')
    }
  }

  // Unified Audio Config Functions
  const openAudioConfig = async (initialTab: AudioTab = 'tts') => {
    setProviderLoading(true)
    setConfiguringAudio(true)
    setAudioTab(initialTab)

    try {
      // Load available TTS providers
      const providers = await api.getTTSProviders()
      setTTSProviders(providers.filter(p => p.status === 'available'))

      // Load current agent TTS config
      const currentTTSConfig = await api.getAgentTTSProvider(agentId)
      const provider = currentTTSConfig.provider || 'kokoro'
      setTTSConfig({
        provider,
        voice: currentTTSConfig.voice || 'pf_dora',
        language: currentTTSConfig.language || 'pt',
        speed: currentTTSConfig.speed || 1.0,
        response_format: currentTTSConfig.response_format || 'opus',
      })

      // Load voices for current provider
      try {
        const voices = await api.getTTSProviderVoices(provider)
        setTTSVoices(voices)
      } catch {
        setTTSVoices([])
      }

      // Load current transcript config
      const transcriptSkill = agentSkills.find(s => s.skill_type === 'audio_transcript')
      if (transcriptSkill?.config) {
        setTranscriptConfig(transcriptSkill.config)
      } else {
        setTranscriptConfig({ language: 'auto', model: 'whisper-1', response_mode: 'conversational' })
      }
    } catch (err) {
      console.error('Failed to load audio config:', err)
      alert('Failed to load audio configuration')
      setConfiguringAudio(false)
    } finally {
      setProviderLoading(false)
    }
  }

  const handleTTSProviderChange = async (newProvider: string) => {
    setTTSConfig(prev => ({ ...prev, provider: newProvider }))

    // Load voices for new provider
    try {
      const voices = await api.getTTSProviderVoices(newProvider)
      setTTSVoices(voices)

      // Set default voice for new provider
      const providerInfo = ttsProviders.find(p => p.id === newProvider)
      if (providerInfo) {
        setTTSConfig(prev => ({ ...prev, voice: providerInfo.default_voice }))
      }
    } catch {
      setTTSVoices([])
    }
  }

  const saveAudioConfig = async () => {
    try {
      // Save TTS config if enabled
      const ttsEnabled = isSkillEnabled('audio_tts')
      if (ttsEnabled || audioTab === 'tts') {
        await api.updateAgentTTSProvider(agentId, ttsConfig)
        await api.updateAgentSkill(agentId, 'audio_tts', {
          is_enabled: true,
          config: ttsConfig,
        })
      }

      // Save transcript config if enabled
      const transcriptEnabled = isSkillEnabled('audio_transcript')
      if (transcriptEnabled || audioTab === 'transcript') {
        await api.updateAgentSkill(agentId, 'audio_transcript', {
          is_enabled: true,
          config: transcriptConfig,
        })
      }

      setConfiguringAudio(false)
      loadData()
    } catch (err) {
      console.error('Failed to save audio config:', err)
      alert('Failed to save audio configuration')
    }
  }

  const toggleAudioSubSkill = async (subSkill: 'audio_tts' | 'audio_transcript', enabled: boolean) => {
    try {
      if (enabled) {
        const config = subSkill === 'audio_tts' ? ttsConfig : transcriptConfig
        await api.updateAgentSkill(agentId, subSkill, { is_enabled: true, config })
      } else {
        await api.disableAgentSkill(agentId, subSkill)
      }
      loadData()
    } catch (err) {
      console.error('Failed to toggle audio sub-skill:', err)
      alert('Failed to update audio skill')
    }
  }

  const saveConfig = async () => {
    if (!configuring) return

    try {
      await api.updateAgentSkill(agentId, configuring, { config: configData })
      setConfiguring(null)
      loadData()
    } catch (err) {
      console.error('Failed to save config:', err)
      alert('Failed to save configuration')
    }
  }

  const renderCapabilitiesConfig = (capabilities: Record<string, any>) => {
    return (
      <div className="space-y-3">
        {Object.entries(capabilities).map(([capKey, capValue]: [string, any]) => {
          const capEnabled = capValue?.enabled ?? true
          const capLabel = capValue?.label || capKey.replace(/_/g, ' ')
          const capDesc = capValue?.description || ''

          return (
            <div
              key={capKey}
              className="flex items-start space-x-3 p-3 border border-tsushin-border rounded-md bg-tsushin-surface"
            >
              <input
                type="checkbox"
                checked={capEnabled}
                onChange={(e) => {
                  const newConfig = { ...configData }
                  if (!newConfig.capabilities) newConfig.capabilities = {}
                  if (!newConfig.capabilities[capKey]) {
                    newConfig.capabilities[capKey] = { ...capValue }
                  }
                  newConfig.capabilities[capKey].enabled = e.target.checked
                  setConfigData(newConfig)
                }}
                className="mt-1 w-5 h-5"
              />
              <div className="flex-1">
                <label className="font-medium text-white cursor-pointer">
                  {capLabel}
                </label>
                {capDesc && (
                  <p className="text-sm text-tsushin-muted mt-1">
                    {capDesc}
                  </p>
                )}
              </div>
            </div>
          )
        })}
      </div>
    )
  }

  const renderConfigInput = (key: string, schema: any, value: any) => {
    const inputClasses = "w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"

    if (key === 'capabilities' && schema.type === 'object' && value) {
      return renderCapabilitiesConfig(value)
    }

    if (schema.type === 'boolean') {
      return (
        <label className="flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={value !== undefined ? value : schema.default}
            onChange={(e) => setConfigData({ ...configData, [key]: e.target.checked })}
            className="mr-2 w-5 h-5"
          />
          <span className="text-sm">
            {value !== undefined ? (value ? 'Enabled' : 'Disabled') : (schema.default ? 'Enabled' : 'Disabled')}
          </span>
        </label>
      )
    }

    if (schema.type === 'array') {
      const arrayValue = value || schema.default || []
      return (
        <ArrayConfigInput
          value={arrayValue}
          onChange={(newValue) => setConfigData({ ...configData, [key]: newValue })}
          placeholder="Type and press Enter to add"
        />
      )
    }

    if (schema.type === 'string' && (schema.options || schema.enum)) {
      const options = schema.options || schema.enum || []
      return (
        <select
          value={value || schema.default}
          onChange={(e) => setConfigData({ ...configData, [key]: e.target.value })}
          className={inputClasses}
        >
          {options.map((opt: string) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      )
    }

    if (schema.type === 'number') {
      return (
        <input
          type="number"
          value={value !== undefined ? value : (schema.default || 0)}
          onChange={(e) => setConfigData({ ...configData, [key]: parseFloat(e.target.value) })}
          className={inputClasses}
          min={schema.min}
          max={schema.max}
          step={schema.step}
        />
      )
    }

    return (
      <input
        type="text"
        value={value || schema.default || ''}
        onChange={(e) => setConfigData({ ...configData, [key]: e.target.value })}
        className={inputClasses}
      />
    )
  }

  // Skill-level Security Profile Indicator (v1.6.0 Phase E)
  const handleSkillSecurityAssignment = async (skillType: string, profileId: number | null) => {
    try {
      if (profileId) {
        await api.assignSentinelProfile({
          profile_id: profileId,
          agent_id: agentId,
          skill_type: skillType,
        })
      } else {
        const existing = skillSecurityAssignments.get(skillType)
        if (existing) {
          await api.removeSentinelProfileAssignment(existing.id)
        }
      }
      setSkillSecurityPopover(null)
      loadData()
    } catch (err: any) {
      console.error('Failed to update skill security:', err)
    }
  }

  const SecurityIndicator = ({ skillType }: { skillType: string }) => {
    const assignment = skillSecurityAssignments.get(skillType)
    const isInherited = !assignment
    const isOpen = skillSecurityPopover === skillType

    return (
      <div className="relative" ref={isOpen ? securityPopoverRef : undefined}>
        <button
          onClick={(e) => {
            e.stopPropagation()
            setSkillSecurityPopover(isOpen ? null : skillType)
          }}
          className={`flex items-center gap-1 px-2 py-0.5 text-xs rounded-full transition-colors ${
            isInherited
              ? 'bg-tsushin-elevated text-tsushin-muted hover:bg-tsushin-surface'
              : 'bg-teal-100 dark:bg-teal-800/30 text-teal-700 dark:text-teal-300 hover:bg-teal-200 dark:hover:bg-teal-700/30'
          }`}
          title="Security Profile"
        >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          {isInherited ? 'Inherited' : assignment?.profile_name}
        </button>

        {isOpen && (
          <div
            className="absolute right-0 top-full mt-1 w-52 bg-tsushin-surface border border-tsushin-border rounded-lg shadow-xl z-50"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-3 py-2 border-b border-tsushin-border">
              <p className="text-xs font-medium text-tsushin-muted">Security Profile</p>
            </div>
            <div className="p-1 max-h-60 overflow-y-auto">
              <button
                onClick={() => handleSkillSecurityAssignment(skillType, null)}
                className={`w-full px-3 py-2 text-left text-sm rounded hover:bg-tsushin-surface transition-colors ${
                  isInherited ? 'text-teal-600 dark:text-teal-400 font-medium' : 'text-tsushin-fog'
                }`}
              >
                Inherit from Agent
              </button>
              {securityProfiles.map((p) => (
                <button
                  key={p.id}
                  onClick={() => handleSkillSecurityAssignment(skillType, p.id)}
                  className={`w-full px-3 py-2 text-left text-sm rounded hover:bg-tsushin-surface transition-colors ${
                    assignment?.profile_id === p.id ? 'text-teal-600 dark:text-teal-400 font-medium' : 'text-tsushin-fog'
                  }`}
                >
                  {p.name}
                  {p.is_system && <span className="text-xs text-gray-400 ml-1">[System]</span>}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  // Render provider-based skill card (Scheduler, Email, Web Search)
  const renderProviderSkillCard = (
    displayName: string,
    providerKey: 'scheduler' | 'email' | 'web_search',
    SkillIcon: React.FC<IconProps>,
    description: string
  ) => {
    const skillType = PROVIDER_SKILLS[providerKey].skillType
    const enabled = isSkillEnabled(skillType)
    const integration = getSkillIntegration(skillType)
    const config = getSkillConfig(skillType)

    // Get provider display name
    let providerDisplay = 'Not configured'
    let integrationDisplay = ''

    if (providerKey === 'web_search') {
      // For web search, provider is in config
      const provider = config.provider || 'brave'
      providerDisplay = provider === 'brave' ? 'Brave Search' : provider === 'google' ? 'Google Search (SerpAPI)' : provider
    } else if (integration) {
      if (providerKey === 'scheduler') {
        switch (integration.scheduler_provider) {
          case 'flows':
            providerDisplay = 'Flows (Built-in)'
            break
          case 'google_calendar':
            providerDisplay = 'Google Calendar'
            integrationDisplay = integration.integration_email || ''
            break
          case 'asana':
            providerDisplay = 'Asana'
            integrationDisplay = integration.integration_name || ''
            break
          default:
            providerDisplay = integration.scheduler_provider || 'Flows (Built-in)'
        }
      } else {
        providerDisplay = 'Gmail'
        integrationDisplay = integration.integration_email || ''
      }
    }

    return (
      <div
        className={`border border-tsushin-border rounded-lg p-6 ${
          enabled
            ? 'bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20 border-teal-300 dark:border-teal-600'
            : 'bg-tsushin-ink'
        }`}
      >
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <SkillIcon size={24} />
              <h3 className="text-lg font-semibold">{displayName}</h3>
              {enabled && (
                <span className="px-2 py-0.5 text-xs font-medium bg-green-100 dark:bg-green-800/30 text-green-700 dark:text-green-300 rounded-full">
                  Active
                </span>
              )}
              {enabled && providerKey === 'web_search' && <SecurityIndicator skillType="web_search" />}
            </div>
            <p className="text-sm text-tsushin-slate">{description}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => openProviderConfig(providerKey)}
              className="px-4 py-2 bg-teal-600 text-white text-sm rounded-lg hover:bg-teal-700 transition-colors inline-flex items-center gap-1.5"
            >
              {enabled ? <><SettingsIcon size={14} /> Configure</> : <><PlugIcon size={14} /> Setup</>}
            </button>
          </div>
        </div>

        {enabled && (
          <div className="mt-4 pt-4 border-t border-teal-200 dark:border-teal-700">
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                <div className="text-xs text-tsushin-muted mb-1">Provider</div>
                <div className="font-medium text-teal-700 dark:text-teal-300">{providerDisplay}</div>
              </div>
              {integrationDisplay && (
                <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                  <div className="text-xs text-tsushin-muted mb-1">Account</div>
                  <div className="font-medium text-white truncate">{integrationDisplay}</div>
                </div>
              )}
              {integration?.integration_health && (
                <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                  <div className="text-xs text-tsushin-muted mb-1">Status</div>
                  <div className={`font-medium ${
                    integration.integration_health === 'connected'
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-yellow-600 dark:text-yellow-400'
                  }`}>
                    {integration.integration_health === 'connected' ? <span className="inline-flex items-center gap-1"><CheckIcon size={12} /> Connected</span> : <span className="inline-flex items-center gap-1"><AlertTriangleIcon size={12} /> {integration.integration_health}</span>}
                  </div>
                </div>
              )}
            </div>

            {/* Show keywords if configured */}
            {config.keywords && config.keywords.length > 0 && (
              <div className="mt-3">
                <div className="text-xs text-tsushin-muted mb-1">Trigger Keywords</div>
                <div className="flex flex-wrap gap-1">
                  {config.keywords.slice(0, 8).map((kw: string, i: number) => (
                    <span key={i} className="px-2 py-0.5 text-xs bg-teal-100 dark:bg-teal-800/30 text-teal-700 dark:text-teal-300 rounded">
                      {kw}
                    </span>
                  ))}
                  {config.keywords.length > 8 && (
                    <span className="px-2 py-0.5 text-xs bg-tsushin-elevated text-tsushin-muted rounded">
                      +{config.keywords.length - 8} more
                    </span>
                  )}
                </div>
              </div>
            )}

            <div className="mt-3 flex gap-2">
              <button
                onClick={() => openConfig(skillType)}
                className="px-3 py-1 text-sm text-teal-600 dark:text-teal-400 hover:bg-teal-100 dark:hover:bg-teal-900/30 rounded"
              >
                Edit Keywords & Options
              </button>
              <button
                onClick={() => removeSkill(skillType, displayName)}
                className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
              >
                Remove
              </button>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Render Unified Audio Skill Card (TTS + Transcript)
  const renderUnifiedAudioCard = () => {
    const ttsEnabled = isSkillEnabled('audio_tts')
    const transcriptEnabled = isSkillEnabled('audio_transcript')
    const anyEnabled = ttsEnabled || transcriptEnabled

    const ttsConfigData = getSkillConfig('audio_tts')
    const transcriptConfigData = getSkillConfig('audio_transcript')
    const currentProvider = ttsConfigData.provider || 'kokoro'

    // Count active sub-skills
    const activeCount = (ttsEnabled ? 1 : 0) + (transcriptEnabled ? 1 : 0)

    return (
      <div
        className={`border border-tsushin-border rounded-lg p-6 ${
          anyEnabled
            ? 'bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20 border-teal-300 dark:border-teal-600'
            : 'bg-tsushin-ink'
        }`}
      >
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <MicrophoneIcon size={24} />
              <h3 className="text-lg font-semibold">Audio</h3>
              {anyEnabled && (
                <span className="px-2 py-0.5 text-xs font-medium bg-teal-100 dark:bg-teal-800/30 text-teal-700 dark:text-teal-300 rounded-full">
                  {activeCount}/2 Active
                </span>
              )}
            </div>
            <p className="text-sm text-tsushin-slate">
              Audio processing: Text-to-Speech responses and Speech-to-Text transcription.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => openAudioConfig('tts')}
              className="px-4 py-2 bg-teal-600 text-white text-sm rounded-lg hover:bg-teal-700 transition-colors inline-flex items-center gap-1.5"
            >
              {anyEnabled ? <><SettingsIcon size={14} /> Configure</> : <><PlugIcon size={14} /> Setup</>}
            </button>
          </div>
        </div>

        {/* Sub-skills status */}
        <div className="grid grid-cols-2 gap-3 mb-4">
          {/* TTS Sub-skill */}
          <div
            className={`p-3 rounded-lg border cursor-pointer transition-all ${
              ttsEnabled
                ? 'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-600'
                : 'bg-tsushin-elevated border-tsushin-border'
            }`}
            onClick={() => openAudioConfig('tts')}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium flex items-center gap-1.5">
                <SpeakerIcon size={14} /> TTS Response
              </span>
              {ttsEnabled ? (
                <span className="w-2 h-2 rounded-full bg-green-500" />
              ) : (
                <span className="text-xs text-gray-400">Off</span>
              )}
            </div>
            {ttsEnabled && (
              <div className="text-xs text-tsushin-muted">
                <span className="inline-flex items-center gap-1">{currentProvider === 'kokoro' ? <><MicrophoneIcon size={10} /> Kokoro (FREE)</> : <>OpenAI</>}</span> • {ttsConfigData.voice || 'pf_dora'}
              </div>
            )}
          </div>

          {/* Transcript Sub-skill */}
          <div
            className={`p-3 rounded-lg border cursor-pointer transition-all ${
              transcriptEnabled
                ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-600'
                : 'bg-tsushin-elevated border-tsushin-border'
            }`}
            onClick={() => openAudioConfig('transcript')}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium flex items-center gap-1.5">
                <MicrophoneIcon size={14} /> Transcript
              </span>
              {transcriptEnabled ? (
                <span className="w-2 h-2 rounded-full bg-blue-500" />
              ) : (
                <span className="text-xs text-gray-400">Off</span>
              )}
            </div>
            {transcriptEnabled && (
              <div className="text-xs text-tsushin-muted">
                Whisper • {transcriptConfigData.response_mode === 'transcript_only' ? 'Transcript only' : 'Conversational'}
              </div>
            )}
          </div>
        </div>

        {anyEnabled && (
          <div className="pt-4 border-t border-teal-200 dark:border-teal-700">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {ttsEnabled && (
                <>
                  <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                    <div className="text-xs text-tsushin-muted mb-1">TTS Provider</div>
                    <div className={`font-medium text-sm ${currentProvider === 'kokoro' ? 'text-green-600 dark:text-green-400' : 'text-blue-600 dark:text-blue-400'}`}>
                      {currentProvider === 'kokoro' ? 'Kokoro (FREE)' : 'OpenAI'}
                    </div>
                  </div>
                  <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                    <div className="text-xs text-tsushin-muted mb-1">TTS Cost</div>
                    <div className={`font-medium text-sm ${currentProvider === 'kokoro' ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                      {currentProvider === 'kokoro' ? '$0 (FREE!)' : '~$15/1M chars'}
                    </div>
                  </div>
                </>
              )}
              {transcriptEnabled && (
                <>
                  <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                    <div className="text-xs text-tsushin-muted mb-1">STT Model</div>
                    <div className="font-medium text-sm text-white">
                      Whisper
                    </div>
                  </div>
                  <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                    <div className="text-xs text-tsushin-muted mb-1">STT Mode</div>
                    <div className="font-medium text-sm text-white">
                      {transcriptConfigData.response_mode === 'transcript_only' ? 'Transcript' : 'AI Chat'}
                    </div>
                  </div>
                </>
              )}
            </div>

            <div className="mt-3 flex gap-2">
              {ttsEnabled && (
                <button
                  onClick={() => toggleAudioSubSkill('audio_tts', false)}
                  className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
                >
                  Disable TTS
                </button>
              )}
              {transcriptEnabled && (
                <button
                  onClick={() => toggleAudioSubSkill('audio_transcript', false)}
                  className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
                >
                  Disable Transcript
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  // Shell Skill Functions
  const openShellConfig = async () => {
    setProviderLoading(true)
    setConfiguringShell(true)

    try {
      // Load current shell config
      const shellSkill = agentSkills.find(s => s.skill_type === 'shell')
      if (shellSkill?.config) {
        setShellConfig(shellSkill.config)
      } else {
        setShellConfig({ wait_for_result: false, default_timeout: 60 })
      }

      // Try to load connected beacons (if API available)
      try {
        const response = await fetch('/api/shell/beacons')
        if (response.ok) {
          const beacons = await response.json()
          setShellBeacons(beacons.filter((b: any) => b.is_online))
        }
      } catch {
        setShellBeacons([])
      }
    } catch (err) {
      console.error('Failed to load shell config:', err)
    } finally {
      setProviderLoading(false)
    }
  }

  const saveShellConfig = async () => {
    try {
      await api.updateAgentSkill(agentId, 'shell', {
        is_enabled: true,
        config: shellConfig,
      })
      setConfiguringShell(false)
      loadData()
    } catch (err) {
      console.error('Failed to save shell config:', err)
      alert('Failed to save shell configuration')
    }
  }

  // Render Shell Skill Card (consistent with other skill cards)
  const renderShellSkillCard = () => {
    const enabled = isSkillEnabled('shell')
    const config = getSkillConfig('shell')
    const onlineBeacons = shellBeacons.filter(b => b.is_online).length

    return (
      <div
        className={`border border-tsushin-border rounded-lg p-6 ${
          enabled
            ? 'bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20 border-teal-300 dark:border-teal-600'
            : 'bg-tsushin-ink'
        }`}
      >
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <TerminalIcon size={24} />
              <h3 className="text-lg font-semibold">Shell</h3>
              {enabled && (
                <span className="px-2 py-0.5 text-xs font-medium bg-green-100 dark:bg-green-800/30 text-green-700 dark:text-green-300 rounded-full">
                  Active
                </span>
              )}
              {enabled && <SecurityIndicator skillType="shell" />}
            </div>
            <p className="text-sm text-tsushin-slate">
              Execute remote shell commands on connected beacons. Supports programmatic (/shell) and agentic (natural language) modes.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={openShellConfig}
              className="px-4 py-2 bg-teal-600 text-white text-sm rounded-lg hover:bg-teal-700 transition-colors inline-flex items-center gap-1.5"
            >
              {enabled ? <><SettingsIcon size={14} /> Configure</> : <><PlugIcon size={14} /> Setup</>}
            </button>
          </div>
        </div>

        {enabled && (
          <div className="mt-4 pt-4 border-t border-teal-200 dark:border-teal-700">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                <div className="text-xs text-tsushin-muted mb-1">Agent Mode</div>
                <div className="font-medium text-teal-700 dark:text-teal-300">
                  <span className="inline-flex items-center gap-1">{config.execution_mode === 'agentic' ? <><BotIcon size={14} /> Agentic</> : <><WrenchIcon size={14} /> Programmatic</>}</span>
                </div>
              </div>
              <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                <div className="text-xs text-tsushin-muted mb-1">Result Mode</div>
                <div className="font-medium text-white">
                  <span className="inline-flex items-center gap-1">{config.wait_for_result ? <><ClockIcon size={14} /> Wait</> : <><RocketIcon size={14} /> Fire &amp; Forget</>}</span>
                </div>
              </div>
              <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                <div className="text-xs text-tsushin-muted mb-1">Timeout</div>
                <div className="font-medium text-white">
                  {config.default_timeout || 60}s
                </div>
              </div>
              <div className="bg-tsushin-surface rounded-lg p-3 border border-tsushin-border">
                <div className="text-xs text-tsushin-muted mb-1">Beacons Online</div>
                <div className={`font-medium ${onlineBeacons > 0 ? 'text-green-600 dark:text-green-400' : 'text-gray-500'}`}>
                  {onlineBeacons > 0 ? <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500 inline-block" />{onlineBeacons} connected</span> : <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-gray-400 inline-block" />None online</span>}
                </div>
              </div>
            </div>

            <div className="mt-3 flex gap-2">
              <a
                href="/hub/shell"
                className="px-3 py-1 text-sm text-teal-600 dark:text-teal-400 hover:bg-teal-100 dark:hover:bg-teal-900/30 rounded inline-flex items-center gap-1"
              >
                <RadioIcon size={14} /> Shell Command Center
              </a>
              <button
                onClick={() => removeSkill('shell', 'Shell')}
                className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
              >
                Remove
              </button>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Render standard skill card (audio, etc.)
  const renderStandardSkillCard = (skill: SkillDefinition) => {
    // Skip provider-based skills (they're rendered separately)
    if (SPECIAL_RENDERED_SKILLS.has(skill.skill_type) || skill.skill_type === 'asana') {
      return null
    }

    const config = getSkillConfig(skill.skill_type)
    const display = getSkillDisplay(skill.skill_type, skill.skill_name, skill.skill_description)
    const Icon = display.icon

    return (
      <div
        key={skill.skill_type}
        className="border border-teal-300 dark:border-teal-600 rounded-lg p-6 bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20"
      >
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-2">
              <Icon size={24} />
              <h3 className="text-lg font-semibold">{display.displayName}</h3>
              <span className="px-2 py-0.5 text-xs font-medium bg-green-100 dark:bg-green-800/30 text-green-700 dark:text-green-300 rounded-full">
                Active
              </span>
            </div>
            <p className="text-sm text-tsushin-slate">{display.description}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => openConfig(skill.skill_type)}
              className="px-4 py-2 bg-teal-600 text-white text-sm rounded-lg hover:bg-teal-700 transition-colors inline-flex items-center gap-1.5"
            >
              <SettingsIcon size={14} /> Configure
            </button>
          </div>
        </div>

        {Object.keys(config).length > 0 && (
          <div className="mt-4 pt-4 border-t border-teal-200 dark:border-teal-700">
            <div className="grid grid-cols-3 gap-4">
              {Object.entries(config)
                .filter(([key]) => {
                  if (key === 'ai_model' && config.intent_detection_model) return false
                  return true
                })
                .slice(0, 6)
                .map(([key, value]) => (
                  <div key={key} className="bg-tsushin-surface rounded p-2 border border-tsushin-border">
                    <div className="text-xs text-tsushin-slate">{key.replace(/_/g, ' ')}</div>
                    <div className="text-sm font-medium truncate">{Array.isArray(value) ? `${value.length} items` : String(value)}</div>
                  </div>
                ))
              }
            </div>
            <div className="mt-3">
              <button
                onClick={() => removeSkill(skill.skill_type, display.displayName)}
                className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
              >
                Remove
              </button>
            </div>
          </div>
        )}

        {Object.keys(config).length === 0 && (
          <div className="mt-3">
            <button
              onClick={() => removeSkill(skill.skill_type, display.displayName)}
              className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
            >
              Remove
            </button>
          </div>
        )}
      </div>
    )
  }

  // Compute enabled skill types for the Add Skill modal (must be before any early return)
  const enabledSkillTypes = useMemo(() => {
    return new Set(agentSkills.filter(s => s.is_enabled).map(s => s.skill_type))
  }, [agentSkills])

  const assignedCustomSkillIds = useMemo(() => {
    return new Set(customSkillAssignments.map((a: any) => a.custom_skill_id))
  }, [customSkillAssignments])

  // Filter which provider skills are enabled
  const enabledProviderSkills = useMemo(() => {
    const result: { providerKey: 'scheduler' | 'email' | 'web_search'; displayName: string; skillType: string; icon: React.FC<IconProps>; description: string }[] = []
    const providerEntries: { providerKey: 'scheduler' | 'email' | 'web_search'; displayName: string; skillType: string; icon: React.FC<IconProps>; description: string }[] = [
      { providerKey: 'scheduler', displayName: 'Scheduler', skillType: 'flows', icon: CalendarIcon, description: 'Create events, reminders, and schedule AI conversations. Choose between built-in Flows, Google Calendar, or Asana.' },
      { providerKey: 'email', displayName: 'Email', skillType: 'gmail', icon: MailIcon, description: 'Read and search emails. Connect your Gmail account to enable email access.' },
      { providerKey: 'web_search', displayName: 'Web Search', skillType: 'web_search', icon: SearchIcon, description: 'Search the web for information. Choose between Brave Search (privacy-focused) or Google Search (via SerpAPI).' },
    ]
    for (const entry of providerEntries) {
      if (enabledSkillTypes.has(entry.skillType)) {
        result.push(entry)
      }
    }
    return result
  }, [enabledSkillTypes])

  const isAudioEnabled = enabledSkillTypes.has('audio_tts') || enabledSkillTypes.has('audio_transcript')
  const isShellEnabled = enabledSkillTypes.has('shell')

  // Filter standard skills that are enabled (not provider/audio/shell)
  const enabledStandardSkills = useMemo(() => {
    return availableSkills.filter(skill => {
      if (HIDDEN_SKILLS.has(skill.skill_type)) return false
      if (SPECIAL_RENDERED_SKILLS.has(skill.skill_type)) return false
      return enabledSkillTypes.has(skill.skill_type)
    })
  }, [availableSkills, enabledSkillTypes])

  const totalEnabledCount = enabledProviderSkills.length + (isAudioEnabled ? 1 : 0) + (isShellEnabled ? 1 : 0) + enabledStandardSkills.length

  if (loading) {
    return <div className="p-8 text-center">Loading skills...</div>
  }

  const currentProviders =
    configuringProvider === 'scheduler' ? schedulerProviders :
    configuringProvider === 'email' ? emailProviders :
    configuringProvider === 'web_search' ? webSearchProviders :
    []
  const selectedProviderData = currentProviders.find(p => p.provider_type === selectedProvider)

  return (
    <div className="space-y-6">
      {/* Header with Add Skill button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2">
            <PlugIcon size={20} /> Skills
            <span className="text-sm font-normal text-tsushin-slate ml-1">
              {totalEnabledCount} active
            </span>
          </h2>
          <p className="text-sm text-tsushin-slate mt-1">
            Manage the capabilities enabled for this agent.
          </p>
        </div>
        <button
          onClick={() => setShowAddSkillModal(true)}
          className="px-4 py-2 bg-teal-600 text-white text-sm rounded-lg hover:bg-teal-700 transition-colors inline-flex items-center gap-1.5 font-medium"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Skill
        </button>
      </div>

      {/* Empty state */}
      {totalEnabledCount === 0 ? (
        <div className="text-center py-16 bg-tsushin-ink rounded-lg border border-white/5">
          <PlugIcon size={48} className="mx-auto text-tsushin-muted mb-4" />
          <h3 className="text-lg font-medium text-white mb-2">No skills configured</h3>
          <p className="text-sm text-tsushin-muted mb-6 max-w-md mx-auto">
            Add skills to give your agent capabilities like web search, scheduling, audio processing, and more.
          </p>
          <button
            onClick={() => setShowAddSkillModal(true)}
            className="px-6 py-2.5 bg-teal-600 text-white rounded-lg hover:bg-teal-700 transition-colors inline-flex items-center gap-2 font-medium"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Your First Skill
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Built-in Skills */}
          {(enabledProviderSkills.length > 0 || isAudioEnabled || isShellEnabled || enabledStandardSkills.length > 0) && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-tsushin-slate whitespace-nowrap">Built-in Skills</h3>
                <div className="flex-1 h-px bg-white/5" />
              </div>
              <div className="grid gap-6 md:grid-cols-2">
                {enabledProviderSkills.map((ps) => renderProviderSkillCard(ps.displayName, ps.providerKey, ps.icon, ps.description))}
                {isAudioEnabled && renderUnifiedAudioCard()}
                {isShellEnabled && renderShellSkillCard()}
                {enabledStandardSkills.map((skill) => renderStandardSkillCard(skill))}
              </div>
            </div>
          )}

        </div>
      )}

      {/* Add Skill Modal */}
      <AddSkillModal
        isOpen={showAddSkillModal}
        onClose={() => setShowAddSkillModal(false)}
        onAddBuiltinSkill={addBuiltinSkill}
        onAddCustomSkill={addCustomSkill}
        availableSkills={availableSkills}
        enabledSkillTypes={enabledSkillTypes}
        availableCustomSkills={availableCustomSkills}
        assignedCustomSkillIds={assignedCustomSkillIds}
      />

      {/* Provider Configuration Modal */}
      {configuringProvider && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-tsushin-surface rounded-xl max-w-lg w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
            <div className="bg-gradient-to-r from-teal-600 to-cyan-600 px-6 py-4 flex justify-between items-center">
              <h3 className="text-lg font-semibold text-white">
                Configure {PROVIDER_SKILLS[configuringProvider as 'scheduler' | 'email' | 'web_search'].displayName}
              </h3>
              <button
                onClick={() => setConfiguringProvider(null)}
                className="text-white/80 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-6 flex-1">
              {providerLoading ? (
                <div className="text-center py-8">Loading providers...</div>
              ) : (
                <>
                  {/* Provider Selection */}
                  <div>
                    <label className="block text-sm font-medium mb-3">
                      Select Provider
                    </label>
                    <div className="space-y-2">
                      {currentProviders.map((provider) => (
                        <div
                          key={provider.provider_type}
                          onClick={() => {
                            setSelectedProvider(provider.provider_type)
                            // Auto-select first integration if provider requires one
                            if (provider.requires_integration && provider.available_integrations.length > 0) {
                              setSelectedIntegration(provider.available_integrations[0].integration_id)
                            } else {
                              setSelectedIntegration(null)
                            }
                          }}
                          className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                            selectedProvider === provider.provider_type
                              ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20'
                              : 'border-tsushin-border hover:border-gray-300'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="font-medium">{provider.provider_name}</div>
                              <div className="text-sm text-tsushin-muted">{provider.description}</div>
                            </div>
                            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                              selectedProvider === provider.provider_type
                                ? 'border-teal-500 bg-teal-500'
                                : 'border-tsushin-border'
                            }`}>
                              {selectedProvider === provider.provider_type && (
                                <div className="w-2 h-2 rounded-full bg-white" />
                              )}
                            </div>
                          </div>

                          {/* Show warning if no integrations available */}
                          {provider.requires_integration && provider.available_integrations.length === 0 && (
                            <div className="mt-2 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded text-sm text-yellow-700 dark:text-yellow-300 flex items-center gap-1.5">
                              <AlertTriangleIcon size={14} /> No accounts connected. Visit the Hub to connect one.
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Integration Selection (if provider requires it) */}
                  {selectedProviderData?.requires_integration && selectedProviderData.available_integrations.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium mb-3">
                        Select Account
                      </label>
                      <div className="space-y-2">
                        {selectedProviderData.available_integrations.map((integration) => (
                          <div
                            key={integration.integration_id}
                            onClick={() => setSelectedIntegration(integration.integration_id)}
                            className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                              selectedIntegration === integration.integration_id
                                ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                                : 'border-tsushin-border hover:border-gray-300'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <div className="font-medium">{integration.name}</div>
                                <div className="text-sm text-tsushin-muted">
                                  {integration.email || integration.workspace || `ID: ${integration.integration_id}`}
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className={`px-2 py-0.5 text-xs rounded-full ${
                                  integration.health_status === 'connected'
                                    ? 'bg-green-100 text-green-700 dark:bg-green-800/30 dark:text-green-300'
                                    : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-800/30 dark:text-yellow-300'
                                }`}>
                                  {integration.health_status === 'connected' ? <span className="inline-flex items-center gap-1"><CheckIcon size={12} /> Connected</span> : integration.health_status}
                                </span>
                                <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                                  selectedIntegration === integration.integration_id
                                    ? 'border-green-500 bg-green-500'
                                    : 'border-tsushin-border'
                                }`}>
                                  {selectedIntegration === integration.integration_id && (
                                    <div className="w-2 h-2 rounded-full bg-white" />
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Info box for web_search provider pricing */}
                  {configuringProvider === 'web_search' && selectedProviderData && (
                    <div className="border-t pt-4 border-tsushin-border">
                      <div className={`p-3 rounded-lg ${
                        selectedProvider === 'brave'
                          ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700'
                          : 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700'
                      }`}>
                        <p className="text-sm font-medium inline-flex items-center gap-1.5">
                          <SearchIcon size={14} /> {selectedProvider === 'brave' ? 'Brave Search' : 'Google Search (SerpAPI)'}
                        </p>
                        <p className="text-xs mt-1">
                          {(selectedProviderData as any).pricing?.description || 'Web search provider'}
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Permission Configuration (Google Calendar only) */}
                  {configuringProvider === 'scheduler' && selectedProvider === 'google_calendar' && !providerLoading && (
                    <div className="border-t pt-6 border-tsushin-border">
                      <label className="block text-sm font-medium mb-3">
                        Permissions
                      </label>
                      <div className="space-y-3 bg-tsushin-ink p-4 rounded-lg">
                        <div className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            id="permission-read"
                            checked={providerPermissions.read}
                            onChange={(e) => setProviderPermissions(prev => ({ ...prev, read: e.target.checked }))}
                            className="mt-1 w-4 h-4 text-teal-600 border-gray-300 rounded focus:ring-teal-500"
                          />
                          <div className="flex-1">
                            <label htmlFor="permission-read" className="font-medium text-sm cursor-pointer">
                              Read Events
                            </label>
                            <p className="text-xs text-tsushin-muted mt-1">
                              View and list calendar events
                            </p>
                          </div>
                        </div>

                        <div className="flex items-start gap-3">
                          <input
                            type="checkbox"
                            id="permission-write"
                            checked={providerPermissions.write}
                            onChange={(e) => setProviderPermissions(prev => ({ ...prev, write: e.target.checked }))}
                            className="mt-1 w-4 h-4 text-teal-600 border-gray-300 rounded focus:ring-teal-500"
                          />
                          <div className="flex-1">
                            <label htmlFor="permission-write" className="font-medium text-sm cursor-pointer">
                              Write Events
                            </label>
                            <p className="text-xs text-tsushin-muted mt-1">
                              Create, update, and delete calendar events
                            </p>
                          </div>
                        </div>

                        {!providerPermissions.read && !providerPermissions.write && (
                          <div className="mt-2 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded text-xs text-yellow-700 dark:text-yellow-300 flex items-center gap-1.5">
                            <AlertTriangleIcon size={12} /> At least one permission must be enabled
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="bg-tsushin-ink px-6 py-4 border-t border-tsushin-border flex justify-between items-center">
              <button
                onClick={() => setConfiguringProvider(null)}
                className="px-4 py-2 text-tsushin-slate hover:bg-tsushin-surface rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={saveProviderConfig}
                disabled={
                  (selectedProviderData?.requires_integration && !selectedIntegration) ||
                  (!providerPermissions.read && !providerPermissions.write)
                }
                className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                  (selectedProviderData?.requires_integration && !selectedIntegration) ||
                  (!providerPermissions.read && !providerPermissions.write)
                    ? 'bg-tsushin-elevated text-tsushin-muted cursor-not-allowed'
                    : 'bg-teal-600 text-white hover:bg-teal-700'
                }`}
              >
                Save & Enable
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Unified Audio Configuration Modal (TTS + Transcript) */}
      {configuringAudio && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-xl max-w-lg w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
            <div className="bg-gradient-to-r from-teal-600 to-cyan-600 px-6 py-4 flex justify-between items-center">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <MicrophoneIcon size={20} /> Configure Audio Skills
              </h3>
              <button
                onClick={() => setConfiguringAudio(false)}
                className="text-white/80 hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Tab Navigation */}
            <div className="flex border-b border-tsushin-border">
              <button
                onClick={() => setAudioTab('tts')}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                  audioTab === 'tts'
                    ? 'text-teal-600 dark:text-teal-400 border-b-2 border-teal-600 dark:border-teal-400 bg-teal-50 dark:bg-teal-900/20'
                    : 'text-tsushin-muted hover:text-tsushin-fog'
                }`}
              >
                <span className="flex items-center justify-center gap-2">
                  <SpeakerIcon size={14} /> TTS Response
                  {isSkillEnabled('audio_tts') && <span className="w-2 h-2 rounded-full bg-green-500" />}
                </span>
              </button>
              <button
                onClick={() => setAudioTab('transcript')}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                  audioTab === 'transcript'
                    ? 'text-teal-600 dark:text-teal-400 border-b-2 border-teal-600 dark:border-teal-400 bg-teal-50 dark:bg-teal-900/20'
                    : 'text-tsushin-muted hover:text-tsushin-fog'
                }`}
              >
                <span className="flex items-center justify-center gap-2">
                  <MicrophoneIcon size={14} /> Transcript
                  {isSkillEnabled('audio_transcript') && <span className="w-2 h-2 rounded-full bg-green-500" />}
                </span>
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-6 flex-1">
              {providerLoading ? (
                <div className="text-center py-8">Loading configuration...</div>
              ) : audioTab === 'tts' ? (
                /* TTS Tab Content */
                <>
                  {/* Enable Toggle */}
                  <div className="flex items-center justify-between p-3 bg-tsushin-ink rounded-lg">
                    <span className="font-medium">Enable TTS Response</span>
                    <ToggleSwitch
                      checked={isSkillEnabled('audio_tts')}
                      onChange={(checked) => toggleAudioSubSkill('audio_tts', checked)}
                      size="md"
                      title={isSkillEnabled('audio_tts') ? 'Disable TTS' : 'Enable TTS'}
                    />
                  </div>

                  {/* Provider Selection */}
                  <div>
                    <label className="block text-sm font-medium mb-3">
                      Select TTS Provider
                    </label>
                    <div className="space-y-2">
                      {ttsProviders.map((provider) => (
                        <div
                          key={provider.id}
                          onClick={() => handleTTSProviderChange(provider.id)}
                          className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                            ttsConfig.provider === provider.id
                              ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20'
                              : 'border-tsushin-border hover:border-gray-300'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="font-medium flex items-center gap-2">
                                {provider.id === 'kokoro' ? <MicrophoneIcon size={14} /> : <span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block" />} {provider.name}
                                {provider.is_free && (
                                  <span className="px-2 py-0.5 text-xs bg-green-100 dark:bg-green-800/30 text-green-700 dark:text-green-300 rounded-full">
                                    FREE
                                  </span>
                                )}
                              </div>
                              <div className="text-sm text-tsushin-muted">
                                {provider.voice_count} voices • {provider.supported_languages.join(', ').toUpperCase()}
                              </div>
                              <div className="text-xs text-gray-400 mt-1">
                                {provider.is_free ? '$0 - completely free!' : `~$${(provider.pricing.cost_per_1k_chars || 0.015) * 1000}/1M chars`}
                              </div>
                            </div>
                            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                              ttsConfig.provider === provider.id
                                ? 'border-teal-500 bg-teal-500'
                                : 'border-tsushin-border'
                            }`}>
                              {ttsConfig.provider === provider.id && (
                                <div className="w-2 h-2 rounded-full bg-white" />
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Voice Selection */}
                  {ttsVoices.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium mb-2">Voice</label>
                      <select
                        value={ttsConfig.voice || ''}
                        onChange={(e) => setTTSConfig(prev => ({ ...prev, voice: e.target.value }))}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                      >
                        {ttsVoices.map((voice) => (
                          <option key={voice.voice_id} value={voice.voice_id}>
                            {voice.name} ({voice.language?.toUpperCase()}) - {voice.description || voice.gender || 'Voice'}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  {/* Language Selection (Kokoro only) */}
                  {ttsConfig.provider === 'kokoro' && (
                    <div>
                      <label className="block text-sm font-medium mb-2">Language</label>
                      <select
                        value={ttsConfig.language || 'pt'}
                        onChange={(e) => setTTSConfig(prev => ({ ...prev, language: e.target.value }))}
                        className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                      >
                        <option value="pt">Portuguese (PTBR)</option>
                        <option value="en">English</option>
                        <option value="es">Spanish</option>
                        <option value="fr">French</option>
                        <option value="de">German</option>
                        <option value="it">Italian</option>
                        <option value="ja">Japanese</option>
                        <option value="zh">Chinese</option>
                      </select>
                    </div>
                  )}

                  {/* Speed */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Speed: {ttsConfig.speed?.toFixed(1) || '1.0'}x
                    </label>
                    <input
                      type="range"
                      min="0.5"
                      max={ttsConfig.provider === 'openai' ? '4.0' : '2.0'}
                      step="0.1"
                      value={ttsConfig.speed || 1.0}
                      onChange={(e) => setTTSConfig(prev => ({ ...prev, speed: parseFloat(e.target.value) }))}
                      className="w-full accent-teal-600"
                    />
                    <div className="flex justify-between text-xs text-gray-400">
                      <span>Slower</span>
                      <span>Faster</span>
                    </div>
                  </div>

                  {/* Info Box */}
                  <div className={`p-3 rounded-lg ${
                    ttsConfig.provider === 'kokoro'
                      ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700'
                      : 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700'
                  }`}>
                    {ttsConfig.provider === 'kokoro' ? (
                      <>
                        <p className="text-sm font-medium text-green-700 dark:text-green-300 flex items-center gap-1.5"><MicrophoneIcon size={14} /> Kokoro TTS (FREE)</p>
                        <p className="text-xs text-green-600 dark:text-green-400 mt-1">
                          Open-source TTS with excellent Portuguese (PTBR) support. No API costs!
                        </p>
                      </>
                    ) : (
                      <>
                        <p className="text-sm font-medium text-blue-700 dark:text-blue-300 flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block" /> OpenAI TTS</p>
                        <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                          Premium quality TTS. Requires OpenAI API key. Cost: ~$15 per 1M characters.
                        </p>
                      </>
                    )}
                  </div>
                </>
              ) : (
                /* Transcript Tab Content */
                <>
                  {/* Enable Toggle */}
                  <div className="flex items-center justify-between p-3 bg-tsushin-ink rounded-lg">
                    <span className="font-medium">Enable Audio Transcript</span>
                    <ToggleSwitch
                      checked={isSkillEnabled('audio_transcript')}
                      onChange={(checked) => toggleAudioSubSkill('audio_transcript', checked)}
                      size="md"
                      title={isSkillEnabled('audio_transcript') ? 'Disable transcript' : 'Enable transcript'}
                    />
                  </div>

                  {/* Response Mode */}
                  <div>
                    <label className="block text-sm font-medium mb-3">Response Mode</label>
                    <div className="space-y-2">
                      <div
                        onClick={() => setTranscriptConfig(prev => ({ ...prev, response_mode: 'conversational' }))}
                        className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                          transcriptConfig.response_mode === 'conversational'
                            ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20'
                            : 'border-tsushin-border hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><MessageIcon size={14} /> Conversational</div>
                            <div className="text-sm text-tsushin-muted">
                              Transcribe audio → Pass to AI → Natural response
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            transcriptConfig.response_mode === 'conversational'
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-tsushin-border'
                          }`}>
                            {transcriptConfig.response_mode === 'conversational' && (
                              <div className="w-2 h-2 rounded-full bg-white" />
                            )}
                          </div>
                        </div>
                      </div>
                      <div
                        onClick={() => setTranscriptConfig(prev => ({ ...prev, response_mode: 'transcript_only' }))}
                        className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                          transcriptConfig.response_mode === 'transcript_only'
                            ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20'
                            : 'border-tsushin-border hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><FileTextIcon size={14} /> Transcript Only</div>
                            <div className="text-sm text-tsushin-muted">
                              Transcribe audio → Return raw transcript text (no AI)
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            transcriptConfig.response_mode === 'transcript_only'
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-tsushin-border'
                          }`}>
                            {transcriptConfig.response_mode === 'transcript_only' && (
                              <div className="w-2 h-2 rounded-full bg-white" />
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Language */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Language Detection</label>
                    <select
                      value={transcriptConfig.language || 'auto'}
                      onChange={(e) => setTranscriptConfig(prev => ({ ...prev, language: e.target.value }))}
                      className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                    >
                      <option value="auto">Auto-detect</option>
                      <option value="pt">🇧🇷 Portuguese</option>
                      <option value="en">🇺🇸 English</option>
                      <option value="es">🇪🇸 Spanish</option>
                      <option value="fr">🇫🇷 French</option>
                      <option value="de">🇩🇪 German</option>
                      <option value="it">🇮🇹 Italian</option>
                      <option value="ja">🇯🇵 Japanese</option>
                      <option value="ko">🇰🇷 Korean</option>
                      <option value="zh">🇨🇳 Chinese</option>
                    </select>
                  </div>

                  {/* Model */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Whisper Model</label>
                    <select
                      value={transcriptConfig.model || 'whisper-1'}
                      onChange={(e) => setTranscriptConfig(prev => ({ ...prev, model: e.target.value }))}
                      className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
                    >
                      <option value="whisper-1">whisper-1 (Standard)</option>
                    </select>
                  </div>

                  {/* Info Box */}
                  <div className="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700 rounded-lg">
                    <p className="text-sm font-medium text-yellow-800 dark:text-yellow-200 flex items-center gap-1.5"><AlertTriangleIcon size={14} /> OpenAI API Key Required</p>
                    <p className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
                      Uses OpenAI Whisper API. Cost: ~$0.006 per minute of audio.
                    </p>
                  </div>

                  {/* TTS Conflict Warning */}
                  {transcriptConfig.response_mode === 'transcript_only' && isSkillEnabled('audio_tts') && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg">
                      <p className="text-sm font-medium text-red-800 dark:text-red-200 flex items-center gap-1.5"><AlertTriangleIcon size={14} /> TTS Conflict</p>
                      <p className="text-xs text-red-700 dark:text-red-300 mt-1">
                        "Transcript Only" mode cannot be used with TTS Response enabled. The transcript bypasses AI processing, so there's no text to convert to speech.
                      </p>
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="bg-tsushin-ink px-6 py-4 border-t border-tsushin-border flex justify-between items-center">
              <button
                onClick={() => setConfiguringAudio(false)}
                className="px-4 py-2 text-tsushin-slate hover:bg-tsushin-surface rounded-lg"
              >
                Cancel
              </button>
              {/* Block save when transcript_only mode conflicts with TTS enabled */}
              {(() => {
                const hasConflict = transcriptConfig.response_mode === 'transcript_only' && isSkillEnabled('audio_tts')
                return (
                  <button
                    onClick={saveAudioConfig}
                    disabled={hasConflict}
                    className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                      hasConflict
                        ? 'bg-gray-400 text-gray-200 cursor-not-allowed'
                        : 'bg-teal-600 text-white hover:bg-teal-700'
                    }`}
                    title={hasConflict ? 'Disable TTS or change Transcript mode to save' : ''}
                  >
                    Save Configuration
                  </button>
                )
              })()}
            </div>
          </div>
        </div>
      )}

      {/* Shell Configuration Modal */}
      {configuringShell && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-xl max-w-lg w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
            <div className="bg-gradient-to-r from-teal-600 to-cyan-600 px-6 py-4 flex justify-between items-center">
              <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                <TerminalIcon size={20} /> Configure Shell Skill
              </h3>
              <button
                onClick={() => setConfiguringShell(false)}
                className="text-white/80 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-6 flex-1">
              {providerLoading ? (
                <div className="text-center py-8">Loading configuration...</div>
              ) : (
                <>
                  {/* Enable Toggle */}
                  <div className="flex items-center justify-between p-3 bg-tsushin-ink rounded-lg">
                    <span className="font-medium">Enable Shell Skill</span>
                    <ToggleSwitch
                      checked={isSkillEnabled('shell')}
                      onChange={(checked) => toggleSkill('shell', checked)}
                      size="md"
                      title={isSkillEnabled('shell') ? 'Disable shell' : 'Enable shell'}
                    />
                  </div>

                  {/* Agent Execution Mode */}
                  <div>
                    <label className="block text-sm font-medium mb-3">Agent Execution Mode</label>
                    <div className="space-y-2">
                      <div
                        onClick={() => setShellConfig(prev => ({ ...prev, execution_mode: 'programmatic' }))}
                        className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                          shellConfig.execution_mode !== 'agentic'
                            ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20'
                            : 'border-tsushin-border hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><WrenchIcon size={14} /> Programmatic Only</div>
                            <div className="text-sm text-tsushin-muted">
                              Only <code>/shell &lt;command&gt;</code> works. Natural language is ignored.
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            shellConfig.execution_mode !== 'agentic'
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-tsushin-border'
                          }`}>
                            {shellConfig.execution_mode !== 'agentic' && (
                              <div className="w-2 h-2 rounded-full bg-white" />
                            )}
                          </div>
                        </div>
                      </div>
                      <div
                        onClick={() => setShellConfig(prev => ({ ...prev, execution_mode: 'agentic' }))}
                        className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                          shellConfig.execution_mode === 'agentic'
                            ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20'
                            : 'border-tsushin-border hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><BotIcon size={14} /> Agentic (Natural Language)</div>
                            <div className="text-sm text-tsushin-muted">
                              Both <code>/shell</code> AND natural language like "list files in /tmp" work.
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            shellConfig.execution_mode === 'agentic'
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-tsushin-border'
                          }`}>
                            {shellConfig.execution_mode === 'agentic' && (
                              <div className="w-2 h-2 rounded-full bg-white" />
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Result Mode (for /shell command) */}
                  <div>
                    <label className="block text-sm font-medium mb-3">Result Mode (for /shell)</label>
                    <div className="space-y-2">
                      <div
                        onClick={() => setShellConfig(prev => ({ ...prev, wait_for_result: false }))}
                        className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                          !shellConfig.wait_for_result
                            ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20'
                            : 'border-tsushin-border hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><RocketIcon size={14} /> Fire &amp; Forget</div>
                            <div className="text-sm text-tsushin-muted">
                              Queue command and return immediately. Use <code>/inject</code> to retrieve output later.
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            !shellConfig.wait_for_result
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-tsushin-border'
                          }`}>
                            {!shellConfig.wait_for_result && (
                              <div className="w-2 h-2 rounded-full bg-white" />
                            )}
                          </div>
                        </div>
                      </div>
                      <div
                        onClick={() => setShellConfig(prev => ({ ...prev, wait_for_result: true }))}
                        className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                          shellConfig.wait_for_result
                            ? 'border-teal-500 bg-teal-50 dark:bg-teal-900/20'
                            : 'border-tsushin-border hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><ClockIcon size={14} /> Wait for Result</div>
                            <div className="text-sm text-tsushin-muted">
                              Wait for command to complete before returning response.
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            shellConfig.wait_for_result
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-tsushin-border'
                          }`}>
                            {shellConfig.wait_for_result && (
                              <div className="w-2 h-2 rounded-full bg-white" />
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Default Timeout */}
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Default Timeout: {shellConfig.default_timeout || 60}s
                    </label>
                    <input
                      type="range"
                      min="10"
                      max="300"
                      step="10"
                      value={shellConfig.default_timeout || 60}
                      onChange={(e) => setShellConfig(prev => ({ ...prev, default_timeout: parseInt(e.target.value) }))}
                      className="w-full accent-teal-600"
                    />
                    <div className="flex justify-between text-xs text-gray-400">
                      <span>10s</span>
                      <span>5min</span>
                    </div>
                  </div>

                  {/* Connected Beacons */}
                  <div>
                    <label className="block text-sm font-medium mb-2">Connected Beacons</label>
                    {shellBeacons.length > 0 ? (
                      <div className="space-y-2">
                        {shellBeacons.map((beacon: any, idx: number) => (
                          <div key={idx} className="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded-lg flex items-center justify-between">
                            <div>
                              <div className="font-medium text-green-700 dark:text-green-300 flex items-center gap-1.5">
                                <span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block" /> {beacon.hostname || beacon.name || `Beacon ${idx + 1}`}
                              </div>
                              <div className="text-xs text-gray-500">
                                Last seen: {beacon.last_checkin ? new Date(beacon.last_checkin).toLocaleString() : 'Unknown'}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="p-4 bg-tsushin-ink rounded-lg text-center">
                        <p className="text-tsushin-muted">No beacons online</p>
                        <a href="/hub/shell" className="text-orange-600 dark:text-orange-400 text-sm hover:underline">
                          → Go to Shell Command Center to enroll a beacon
                        </a>
                      </div>
                    )}
                  </div>

                  {/* Info Box */}
                  <div className="p-3 bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-700 rounded-lg">
                    <p className="text-sm font-medium text-orange-800 dark:text-orange-200 flex items-center gap-1.5"><TerminalIcon size={14} /> Shell Skill Usage</p>
                    <ul className="text-xs text-orange-700 dark:text-orange-300 mt-2 space-y-1">
                      <li>• <strong>Programmatic:</strong> Use <code>/shell &lt;command&gt;</code> for direct execution</li>
                      <li>• <strong>Agentic:</strong> Ask naturally: "List files in /tmp"</li>
                      <li>• <strong>Note:</strong> /shell always uses fire-and-forget to avoid UI freezing</li>
                    </ul>
                  </div>
                </>
              )}
            </div>

            <div className="bg-tsushin-ink px-6 py-4 border-t border-tsushin-border flex justify-between items-center">
              <button
                onClick={() => setConfiguringShell(false)}
                className="px-4 py-2 text-tsushin-slate hover:bg-tsushin-surface rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={saveShellConfig}
                className="px-6 py-2 rounded-lg font-medium transition-colors bg-teal-600 text-white hover:bg-teal-700"
              >
                Save Configuration
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Standard Configuration Modal */}
      {configuring && configuring !== 'sandboxed_tools' && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-lg max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="bg-tsushin-elevated px-6 py-4 border-b flex justify-between items-center">
              <h3 className="text-lg font-semibold">
                Configure: {availableSkills.find(s => s.skill_type === configuring)?.skill_name || configuring}
              </h3>
              <button
                onClick={() => setConfiguring(null)}
                className="text-tsushin-slate hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="overflow-y-auto p-6 space-y-4 flex-1">
              {availableSkills.find(s => s.skill_type === configuring)?.config_schema?.properties &&
                Object.entries(availableSkills.find(s => s.skill_type === configuring)!.config_schema.properties).map(([key, schema]) => (
                  <div key={key}>
                    <label className="block text-sm font-medium mb-2 capitalize">
                      {(schema as any).title || key.replace(/_/g, ' ')}
                    </label>
                    {renderConfigInput(key, schema, configData[key])}
                    {(schema as any).description && (
                      <p className="text-xs text-tsushin-muted mt-1">{(schema as any).description}</p>
                    )}
                  </div>
                ))}
            </div>

            <div className="bg-tsushin-elevated px-6 py-4 border-t flex justify-end gap-3">
              <button
                onClick={() => setConfiguring(null)}
                className="px-4 py-2 bg-gray-600 text-white rounded-md hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                onClick={saveConfig}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
              >
                Save Configuration
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Sandboxed Tools Configuration Modal */}
      {configuring === 'sandboxed_tools' && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-tsushin-surface rounded-xl max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col shadow-2xl">
            <div className="bg-gradient-to-r from-teal-600 to-cyan-600 px-6 py-4 flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold text-white flex items-center gap-2">
                  <WrenchIcon size={20} /> Sandboxed Tools
                </h3>
                <p className="text-sm text-white/70 mt-0.5">
                  {sandboxedTools.length} tool{sandboxedTools.length !== 1 ? 's' : ''} available &middot; {agentSandboxedTools.filter(at => at.is_enabled).length} enabled
                </p>
              </div>
              <button
                onClick={() => setConfiguring(null)}
                className="text-white/80 hover:text-white text-xl"
              >
                &#x2715;
              </button>
            </div>

            <div className="overflow-y-auto flex-1 p-6">
              {sandboxedToolsLoading ? (
                <div className="text-center py-12 text-tsushin-muted text-sm">Loading tools...</div>
              ) : sandboxedTools.length === 0 ? (
                <div className="text-center py-12">
                  <WrenchIcon size={40} className="mx-auto text-tsushin-muted mb-3" />
                  <p className="text-tsushin-muted text-sm">No sandboxed tools available.</p>
                  <p className="text-tsushin-muted/60 text-xs mt-1">Create tools in Hub &gt; Sandboxed Tools first.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {sandboxedTools.map((tool) => {
                    const enabled = isSandboxedToolEnabled(tool.id)
                    const isUpdating = sandboxedToolUpdating === tool.id
                    return (
                      <div
                        key={tool.id}
                        className={`border rounded-lg p-4 transition-colors ${
                          enabled
                            ? 'bg-teal-900/15 border-teal-600/30'
                            : 'bg-tsushin-ink border-white/5 hover:border-white/10'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                              enabled ? 'bg-teal-500/15 border border-teal-500/20' : 'bg-white/5 border border-white/10'
                            }`}>
                              <WrenchIcon size={16} className={enabled ? 'text-teal-400' : 'text-tsushin-muted'} />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <h4 className="text-sm font-semibold text-white">{tool.name}</h4>
                                <span className="px-1.5 py-0.5 text-[10px] font-medium bg-white/5 text-tsushin-slate rounded">
                                  {tool.tool_type}
                                </span>
                              </div>
                              <p className="text-xs text-tsushin-muted mt-0.5 line-clamp-1">
                                {tool.system_prompt.split('\n')[0]}
                              </p>
                            </div>
                          </div>
                          <div className="ml-3 shrink-0">
                            {isUpdating ? (
                              <span className="text-xs text-tsushin-muted">Saving...</span>
                            ) : (
                              <ToggleSwitch
                                checked={enabled}
                                onChange={(checked) => toggleSandboxedTool(tool, checked)}
                                title={enabled ? 'Disable tool' : 'Enable tool'}
                              />
                            )}
                          </div>
                        </div>
                        {/* Tool-specific warnings */}
                        {enabled && (tool.name === 'nmap' || tool.name === 'nuclei') && (
                          <div className="mt-3 p-2.5 bg-yellow-900/20 border border-yellow-700/30 rounded-lg flex items-start gap-2">
                            <AlertTriangleIcon size={14} className="text-yellow-400 mt-0.5 shrink-0" />
                            <p className="text-xs text-yellow-300/80">
                              {tool.name === 'nmap'
                                ? 'Network scanning should only be performed on networks you own or have permission to scan.'
                                : 'Only scan targets you own or have explicit permission to test.'}
                            </p>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            <div className="bg-tsushin-ink px-6 py-3 border-t border-tsushin-border flex items-center justify-between">
              <p className="text-xs text-tsushin-muted">
                Changes are saved automatically per toggle.
              </p>
              <button
                onClick={() => setConfiguring(null)}
                className="px-4 py-2 text-tsushin-slate hover:bg-tsushin-surface rounded-lg text-sm"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
