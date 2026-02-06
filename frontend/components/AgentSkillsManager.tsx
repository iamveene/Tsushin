'use client'

import React, { useEffect, useState, useCallback } from 'react'
import { api, AgentSkill, SkillDefinition, SkillIntegration, SkillProvider, TTSProviderInfo, TTSVoice, AgentTTSConfig } from '@/lib/client'
import { ArrayConfigInput } from './ArrayConfigInput'
import {
  PlugIcon, SettingsIcon, MicrophoneIcon, SpeakerIcon, TerminalIcon, BotIcon,
  WrenchIcon, ClockIcon, RocketIcon, RadioIcon, CalendarIcon, MailIcon,
  SearchIcon, AlertTriangleIcon, CheckIcon, MessageIcon, FileTextIcon,
  IconProps,
} from '@/components/ui/icons'

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

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [available, agent, integrations] = await Promise.all([
        api.getAvailableSkills(),
        api.getAgentSkills(agentId),
        api.getAgentSkillIntegrations(agentId),
      ])
      setAvailableSkills(available)
      setAgentSkills(agent)
      setSkillIntegrations(integrations)
    } catch (err) {
      console.error('Failed to load skills:', err)
    } finally {
      setLoading(false)
    }
  }, [agentId])

  useEffect(() => {
    loadData()
  }, [loadData])

  const isSkillEnabled = (skillType: string): boolean => {
    return agentSkills.some(s => s.skill_type === skillType && s.is_enabled)
  }

  const getSkillConfig = (skillType: string): Record<string, any> => {
    const skill = agentSkills.find(s => s.skill_type === skillType)
    return skill?.config || {}
  }

  const getSkillIntegration = (skillType: string): SkillIntegration | undefined => {
    return skillIntegrations.find(si => si.skill_type === skillType)
  }

  const toggleSkill = async (skillType: string, enabled: boolean) => {
    try {
      if (enabled) {
        const skillDef = availableSkills.find(s => s.skill_type === skillType)
        const defaultConfig: Record<string, any> = {}
        if (skillDef) {
          Object.entries(skillDef.config_schema || {}).forEach(([key, schema]) => {
            defaultConfig[key] = (schema as any).default
          })
        }
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

  const openConfig = (skillType: string) => {
    setConfiguring(skillType)
    setConfigData(getSkillConfig(skillType))
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
              className="flex items-start space-x-3 p-3 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800"
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
                <label className="font-medium text-gray-900 dark:text-gray-100 cursor-pointer">
                  {capLabel}
                </label>
                {capDesc && (
                  <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
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
    const inputClasses = "w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"

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
        className={`border dark:border-gray-700 rounded-lg p-6 ${
          enabled
            ? 'bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20 border-teal-300 dark:border-teal-600'
            : 'bg-gray-50 dark:bg-gray-900'
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
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">{description}</p>
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
              <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Provider</div>
                <div className="font-medium text-teal-700 dark:text-teal-300">{providerDisplay}</div>
              </div>
              {integrationDisplay && (
                <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                  <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Account</div>
                  <div className="font-medium text-gray-900 dark:text-gray-100 truncate">{integrationDisplay}</div>
                </div>
              )}
              {integration?.integration_health && (
                <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                  <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Status</div>
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
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Trigger Keywords</div>
                <div className="flex flex-wrap gap-1">
                  {config.keywords.slice(0, 8).map((kw: string, i: number) => (
                    <span key={i} className="px-2 py-0.5 text-xs bg-teal-100 dark:bg-teal-800/30 text-teal-700 dark:text-teal-300 rounded">
                      {kw}
                    </span>
                  ))}
                  {config.keywords.length > 8 && (
                    <span className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">
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
                onClick={() => toggleSkill(skillType, false)}
                className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
              >
                Disable
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
        className={`border dark:border-gray-700 rounded-lg p-6 ${
          anyEnabled
            ? 'bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20 border-teal-300 dark:border-teal-600'
            : 'bg-gray-50 dark:bg-gray-900'
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
            <p className="text-sm text-gray-600 dark:text-gray-400">
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
                : 'bg-gray-100 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
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
              <div className="text-xs text-gray-500 dark:text-gray-400">
                <span className="inline-flex items-center gap-1">{currentProvider === 'kokoro' ? <><MicrophoneIcon size={10} /> Kokoro (FREE)</> : <>OpenAI</>}</span> • {ttsConfigData.voice || 'pf_dora'}
              </div>
            )}
          </div>

          {/* Transcript Sub-skill */}
          <div
            className={`p-3 rounded-lg border cursor-pointer transition-all ${
              transcriptEnabled
                ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-600'
                : 'bg-gray-100 dark:bg-gray-800 border-gray-200 dark:border-gray-700'
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
              <div className="text-xs text-gray-500 dark:text-gray-400">
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
                  <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">TTS Provider</div>
                    <div className={`font-medium text-sm ${currentProvider === 'kokoro' ? 'text-green-600 dark:text-green-400' : 'text-blue-600 dark:text-blue-400'}`}>
                      {currentProvider === 'kokoro' ? 'Kokoro (FREE)' : 'OpenAI'}
                    </div>
                  </div>
                  <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">TTS Cost</div>
                    <div className={`font-medium text-sm ${currentProvider === 'kokoro' ? 'text-green-600 dark:text-green-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                      {currentProvider === 'kokoro' ? '$0 (FREE!)' : '~$15/1M chars'}
                    </div>
                  </div>
                </>
              )}
              {transcriptEnabled && (
                <>
                  <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">STT Model</div>
                    <div className="font-medium text-sm text-gray-900 dark:text-gray-100">
                      Whisper
                    </div>
                  </div>
                  <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                    <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">STT Mode</div>
                    <div className="font-medium text-sm text-gray-900 dark:text-gray-100">
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
        className={`border dark:border-gray-700 rounded-lg p-6 ${
          enabled
            ? 'bg-gradient-to-br from-teal-50 to-cyan-50 dark:from-teal-900/20 dark:to-cyan-900/20 border-teal-300 dark:border-teal-600'
            : 'bg-gray-50 dark:bg-gray-900'
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
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">
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
              <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Agent Mode</div>
                <div className="font-medium text-teal-700 dark:text-teal-300">
                  <span className="inline-flex items-center gap-1">{config.execution_mode === 'agentic' ? <><BotIcon size={14} /> Agentic</> : <><WrenchIcon size={14} /> Programmatic</>}</span>
                </div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Result Mode</div>
                <div className="font-medium text-gray-900 dark:text-gray-100">
                  <span className="inline-flex items-center gap-1">{config.wait_for_result ? <><ClockIcon size={14} /> Wait</> : <><RocketIcon size={14} /> Fire &amp; Forget</>}</span>
                </div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Timeout</div>
                <div className="font-medium text-gray-900 dark:text-gray-100">
                  {config.default_timeout || 60}s
                </div>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg p-3 border dark:border-gray-700">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">Beacons Online</div>
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
                onClick={() => toggleSkill('shell', false)}
                className="px-3 py-1 text-sm text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded"
              >
                Disable
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
    // - flows: Part of Scheduler skill
    // - gmail: Part of Email skill
    // - asana: Provider for Scheduler skill
    // - audio_tts: Part of unified Audio skill
    // - audio_transcript: Part of unified Audio skill
    // - shell: Has its own dedicated card
    if (skill.skill_type === 'flows' || skill.skill_type === 'gmail' || skill.skill_type === 'asana' || skill.skill_type === 'audio_tts' || skill.skill_type === 'audio_transcript' || skill.skill_type === 'shell') {
      return null
    }

    const enabled = isSkillEnabled(skill.skill_type)
    const config = getSkillConfig(skill.skill_type)

    return (
      <div
        key={skill.skill_type}
        className={`border dark:border-gray-700 rounded-lg p-6 ${
          enabled
            ? 'bg-green-50 dark:bg-green-900/20 border-green-300 dark:border-green-600'
            : 'bg-gray-50 dark:bg-gray-900'
        }`}
      >
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <h3 className="text-lg font-semibold mb-2">{skill.skill_name}</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">{skill.skill_description}</p>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => toggleSkill(skill.skill_type, e.target.checked)}
                className="mr-2 w-5 h-5"
              />
              <span className="text-sm font-medium">
                {enabled ? 'Enabled' : 'Disabled'}
              </span>
            </label>
            {enabled && (
              <button
                onClick={() => openConfig(skill.skill_type)}
                className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
              >
                Configure
              </button>
            )}
          </div>
        </div>

        {enabled && Object.keys(config).length > 0 && (
          <div className="mt-4 pt-4 border-t border-green-300 dark:border-green-600">
            <h4 className="text-sm font-medium mb-2 text-green-700 dark:text-green-300">Current Configuration:</h4>
            <div className="grid grid-cols-3 gap-4">
              {Object.entries(config)
                .filter(([key]) => {
                  if (key === 'ai_model' && config.intent_detection_model) return false
                  return true
                })
                .map(([key, value]) => (
                  <div key={key} className="bg-white dark:bg-gray-800 rounded p-2 border dark:border-gray-700">
                    <div className="text-xs text-gray-600 dark:text-gray-400">{key}</div>
                    <div className="text-sm font-medium truncate">{String(value)}</div>
                  </div>
                ))
              }
            </div>
          </div>
        )}


      </div>
    )
  }

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
    <div className="space-y-8">
      {/* Provider-Based Skills Section */}
      <div>
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
          <PlugIcon size={20} /> Integration Skills
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          These skills connect to external services. Configure the provider and account to use.
        </p>

        <div className="grid gap-6 md:grid-cols-2">
          {renderProviderSkillCard(
            'Scheduler',
            'scheduler',
            CalendarIcon,
            'Create events, reminders, and schedule AI conversations. Choose between built-in Flows, Google Calendar, or Asana.'
          )}

          {renderProviderSkillCard(
            'Email',
            'email',
            MailIcon,
            'Read and search emails. Connect your Gmail account to enable email access.'
          )}

          {renderProviderSkillCard(
            'Web Search',
            'web_search',
            SearchIcon,
            'Search the web for information. Choose between Brave Search (privacy-focused) or Google Search (via SerpAPI).'
          )}

          {/* Unified Audio Skill Card (TTS + Transcript) */}
          {renderUnifiedAudioCard()}

          {/* Shell Skill Card */}
          {renderShellSkillCard()}
        </div>
      </div>

      {/* Standard Skills Section */}
      <div>
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
          <WrenchIcon size={20} /> Other Skills
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
          Additional capabilities for your agent.
        </p>

        <div className="grid gap-6">
          {availableSkills.map((skill) => renderStandardSkillCard(skill))}
        </div>
      </div>

      {/* Provider Configuration Modal */}
      {configuringProvider && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white dark:bg-gray-800 rounded-xl max-w-lg w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
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
                              : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="font-medium">{provider.provider_name}</div>
                              <div className="text-sm text-gray-500 dark:text-gray-400">{provider.description}</div>
                            </div>
                            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                              selectedProvider === provider.provider_type
                                ? 'border-teal-500 bg-teal-500'
                                : 'border-gray-300 dark:border-gray-600'
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
                                : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <div className="font-medium">{integration.name}</div>
                                <div className="text-sm text-gray-500 dark:text-gray-400">
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
                                    : 'border-gray-300 dark:border-gray-600'
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
                    <div className="border-t pt-4 dark:border-gray-700">
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
                    <div className="border-t pt-6 dark:border-gray-700">
                      <label className="block text-sm font-medium mb-3">
                        Permissions
                      </label>
                      <div className="space-y-3 bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
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
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
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
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
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

            <div className="bg-gray-50 dark:bg-gray-900 px-6 py-4 border-t dark:border-gray-700 flex justify-between items-center">
              <button
                onClick={() => setConfiguringProvider(null)}
                className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg"
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
                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
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
          <div className="bg-white dark:bg-gray-800 rounded-xl max-w-lg w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
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
            <div className="flex border-b dark:border-gray-700">
              <button
                onClick={() => setAudioTab('tts')}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                  audioTab === 'tts'
                    ? 'text-teal-600 dark:text-teal-400 border-b-2 border-teal-600 dark:border-teal-400 bg-teal-50 dark:bg-teal-900/20'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
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
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
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
                  <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                    <span className="font-medium">Enable TTS Response</span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isSkillEnabled('audio_tts')}
                        onChange={(e) => toggleAudioSubSkill('audio_tts', e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-teal-300 dark:peer-focus:ring-teal-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-teal-600"></div>
                    </label>
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
                              : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
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
                              <div className="text-sm text-gray-500 dark:text-gray-400">
                                {provider.voice_count} voices • {provider.supported_languages.join(', ').toUpperCase()}
                              </div>
                              <div className="text-xs text-gray-400 mt-1">
                                {provider.is_free ? '$0 - completely free!' : `~$${(provider.pricing.cost_per_1k_chars || 0.015) * 1000}/1M chars`}
                              </div>
                            </div>
                            <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                              ttsConfig.provider === provider.id
                                ? 'border-teal-500 bg-teal-500'
                                : 'border-gray-300 dark:border-gray-600'
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
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
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
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
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
                  <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                    <span className="font-medium">Enable Audio Transcript</span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isSkillEnabled('audio_transcript')}
                        onChange={(e) => toggleAudioSubSkill('audio_transcript', e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-teal-300 dark:peer-focus:ring-teal-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-teal-600"></div>
                    </label>
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
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><MessageIcon size={14} /> Conversational</div>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              Transcribe audio → Pass to AI → Natural response
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            transcriptConfig.response_mode === 'conversational'
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-gray-300 dark:border-gray-600'
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
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><FileTextIcon size={14} /> Transcript Only</div>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              Transcribe audio → Return raw transcript text (no AI)
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            transcriptConfig.response_mode === 'transcript_only'
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-gray-300 dark:border-gray-600'
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
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
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
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
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

            <div className="bg-gray-50 dark:bg-gray-900 px-6 py-4 border-t dark:border-gray-700 flex justify-between items-center">
              <button
                onClick={() => setConfiguringAudio(false)}
                className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg"
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
          <div className="bg-white dark:bg-gray-800 rounded-xl max-w-lg w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
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
                  <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                    <span className="font-medium">Enable Shell Skill</span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={isSkillEnabled('shell')}
                        onChange={(e) => toggleSkill('shell', e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-teal-300 dark:peer-focus:ring-teal-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-teal-600"></div>
                    </label>
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
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><WrenchIcon size={14} /> Programmatic Only</div>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              Only <code>/shell &lt;command&gt;</code> works. Natural language is ignored.
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            shellConfig.execution_mode !== 'agentic'
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-gray-300 dark:border-gray-600'
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
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><BotIcon size={14} /> Agentic (Natural Language)</div>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              Both <code>/shell</code> AND natural language like "list files in /tmp" work.
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            shellConfig.execution_mode === 'agentic'
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-gray-300 dark:border-gray-600'
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
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><RocketIcon size={14} /> Fire &amp; Forget</div>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              Queue command and return immediately. Use <code>/inject</code> to retrieve output later.
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            !shellConfig.wait_for_result
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-gray-300 dark:border-gray-600'
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
                            : 'border-gray-200 dark:border-gray-700 hover:border-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div>
                            <div className="font-medium flex items-center gap-1.5"><ClockIcon size={14} /> Wait for Result</div>
                            <div className="text-sm text-gray-500 dark:text-gray-400">
                              Wait for command to complete before returning response.
                            </div>
                          </div>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                            shellConfig.wait_for_result
                              ? 'border-teal-500 bg-teal-500'
                              : 'border-gray-300 dark:border-gray-600'
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
                      <div className="p-4 bg-gray-50 dark:bg-gray-900 rounded-lg text-center">
                        <p className="text-gray-500 dark:text-gray-400">No beacons online</p>
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

            <div className="bg-gray-50 dark:bg-gray-900 px-6 py-4 border-t dark:border-gray-700 flex justify-between items-center">
              <button
                onClick={() => setConfiguringShell(false)}
                className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg"
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
      {configuring && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col">
            <div className="bg-gray-100 dark:bg-gray-800 px-6 py-4 border-b flex justify-between items-center">
              <h3 className="text-lg font-semibold">
                Configure: {availableSkills.find(s => s.skill_type === configuring)?.skill_name || configuring}
              </h3>
              <button
                onClick={() => setConfiguring(null)}
                className="text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
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
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{(schema as any).description}</p>
                    )}
                  </div>
                ))}
            </div>

            <div className="bg-gray-100 dark:bg-gray-800 px-6 py-4 border-t flex justify-end gap-3">
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
    </div>
  )
}
