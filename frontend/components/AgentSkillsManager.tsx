'use client'

import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { api, AgentSkill, SkillDefinition, SkillIntegration, SkillProvider, TTSProviderInfo, TTSVoice, AgentTTSConfig, SentinelProfile, SentinelProfileAssignment, AgentSandboxedTool, SandboxedTool } from '@/lib/client'
import { ArrayConfigInput } from './ArrayConfigInput'
import {
  PlugIcon, SettingsIcon, MicrophoneIcon, SpeakerIcon, TerminalIcon, BotIcon,
  WrenchIcon, ClockIcon, RocketIcon, RadioIcon, CalendarIcon, MailIcon,
  SearchIcon, AlertTriangleIcon, CheckIcon, GitHubIcon,
  IconProps,
} from '@/components/ui/icons'
import AddSkillModal from './skills/AddSkillModal'
import ToggleSwitch from './ui/ToggleSwitch'
import { HIDDEN_SKILLS, SPECIAL_RENDERED_SKILLS, SKILL_DISPLAY_INFO, getSkillDisplay } from './skills/skill-constants'
import { AudioTranscriptFields } from '@/components/audio-wizard/AudioProviderFields'

interface Props {
  agentId: number
}

// Skills that have provider selection
const PROVIDER_SKILLS = {
  'scheduler': { displayName: 'Scheduler', skillType: 'flows', providerKey: 'scheduler' },
  'email': { displayName: 'Email', skillType: 'gmail', providerKey: 'email' },
  'web_search': { displayName: 'Web Search', skillType: 'web_search', providerKey: 'web_search' },
  'ticket_management': { displayName: 'Ticket Management', skillType: 'ticket_management', providerKey: 'ticket_management' },
  'code_repository': { displayName: 'Code Repository', skillType: 'code_repository', providerKey: 'code_repository' },
}

type ProviderKey = 'scheduler' | 'email' | 'web_search' | 'ticket_management' | 'code_repository'

// Ticket Management capability labels (mirrors backend default_config)
const TICKET_MANAGEMENT_CAPABILITY_LABELS: Record<string, { label: string; description: string; defaultEnabled: boolean }> = {
  search_tickets: { label: 'Search tickets', description: 'JQL search across tickets (read)', defaultEnabled: true },
  read_ticket: { label: 'Read ticket', description: "Fetch one ticket's fields (read)", defaultEnabled: true },
  read_comments: { label: 'Read comments', description: "Fetch a ticket's comments (read)", defaultEnabled: true },
  update_ticket: { label: 'Update ticket', description: 'Modify ticket fields (write — off by default)', defaultEnabled: false },
  add_comment: { label: 'Add comment', description: 'Post a comment on a ticket (write — off by default)', defaultEnabled: false },
  transition_ticket: { label: 'Transition ticket', description: 'Move a ticket through its workflow (write — off by default)', defaultEnabled: false },
}

// Email (Gmail) capability labels — mirrors backend GmailSkill default_config.
// Read default ON, write default OFF — same safety stance as Ticket Management.
const EMAIL_CAPABILITY_LABELS: Record<string, { label: string; description: string; defaultEnabled: boolean }> = {
  list_emails: { label: 'List emails', description: 'View recent messages in inbox (read)', defaultEnabled: true },
  search_emails: { label: 'Search emails', description: 'Search with Gmail query syntax (read)', defaultEnabled: true },
  read_email: { label: 'Read email', description: 'Get full email content (read)', defaultEnabled: true },
  send_email: { label: 'Send email', description: 'Send a new outbound email (write — off by default)', defaultEnabled: false },
  reply_email: { label: 'Reply to email', description: 'Reply within an existing email thread (write — off by default)', defaultEnabled: false },
  draft_email: { label: 'Create draft', description: 'Save an email draft without sending it (write — off by default)', defaultEnabled: false },
}

// Code Repository capability labels — mirrors backend CodeRepositorySkill
// default_config. Read defaults ON, write defaults OFF (same safety stance as
// Ticket Management / Email). Provider today: GitHub via REST.
const CODE_REPOSITORY_CAPABILITY_LABELS: Record<string, { label: string; description: string; defaultEnabled: boolean }> = {
  search_repos: { label: 'Search repositories', description: 'Search across the connected account’s repositories (read)', defaultEnabled: true },
  list_pull_requests: { label: 'List pull requests', description: 'List PRs on a repository, filterable by state (read)', defaultEnabled: true },
  read_pull_request: { label: 'Read pull request', description: 'Fetch one PR’s metadata, files, and reviews (read)', defaultEnabled: true },
  list_issues: { label: 'List issues', description: 'List issues on a repository (read)', defaultEnabled: true },
  read_issue: { label: 'Read issue', description: 'Fetch one issue’s metadata and comments (read)', defaultEnabled: true },
  create_issue: { label: 'Create issue', description: 'Open a new issue on a repository (write — off by default)', defaultEnabled: false },
  add_pr_comment: { label: 'Add PR comment', description: 'Post a comment on an existing pull request (write — off by default)', defaultEnabled: false },
  approve_pull_request: { label: 'Approve pull request', description: 'Submit an APPROVE review on a PR (write — off by default)', defaultEnabled: false },
  request_changes: { label: 'Request changes on PR', description: 'Submit a REQUEST_CHANGES review on a PR (write — off by default)', defaultEnabled: false },
  merge_pull_request: { label: 'Merge pull request', description: 'Merge a PR via merge/squash/rebase (write — off by default)', defaultEnabled: false },
  close_pull_request: { label: 'Close pull request', description: 'Close a PR without merging (write — off by default)', defaultEnabled: false },
  close_issue: { label: 'Close issue', description: 'Close an issue (write — off by default)', defaultEnabled: false },
}

// Audio sub-skill tabs
type AudioTab = 'tts' | 'transcript'
type TranscriptResponseMode = 'conversational' | 'transcript_only'
type TranscriptASRMode = 'openai' | 'instance'
type SkillConfig = Record<string, unknown>

interface ConfigSchemaProperty extends SkillConfig {
  type?: string
  default?: unknown
  title?: string
  description?: string
  options?: Array<string | number>
  enum?: Array<string | number>
  min?: number
  max?: number
  step?: number
}

interface CapabilityConfig extends SkillConfig {
  enabled?: boolean
  label?: string
  description?: string
}

interface CustomSkillAssignment {
  custom_skill_id: number
}

interface CustomSkillSummary {
  id: number
  is_enabled: boolean
  name?: string
  description?: string
}

interface ShellSkillConfig extends SkillConfig {
  execution_mode?: string
  wait_for_result?: boolean
  default_timeout?: number
}

interface ShellBeacon {
  is_online?: boolean
  hostname?: string
  name?: string
  last_seen?: string
}

interface WebSearchProviderWithPricing extends SkillProvider {
  pricing?: {
    description?: string
  }
}

interface SkillProviderWithDefault extends SkillProvider {
  is_default?: boolean
}

interface TranscriptSkillConfig extends Record<string, unknown> {
  language: string
  model: string
  response_mode: TranscriptResponseMode
  asr_mode: TranscriptASRMode
  asr_instance_id: number | null
}

interface SkillCardFact {
  label: string
  value: string
}

const HIDDEN_CARD_CONFIG_KEYS = new Set([
  'ai_model',
  'analysis_prompt',
  'edit_handoff_keywords',
  'edit_keywords',
  'enabled_channels',
  'execution_mode',
  'generate_keywords',
  'keywords',
  'processing_message',
  'use_ai_fallback',
])

const MODEL_LABELS: Record<string, string> = {
  'gemini-2.5-flash': 'Gemini 2.5 Flash',
  'gemini-2.5-flash-image': 'Gemini 2.5 Flash Image',
  'gemini-3.1-flash-image-preview': 'Gemini 3.1 Flash Image Preview',
  'gemini-3-pro-image-preview': 'Gemini 3 Pro Image Preview',
  'imagen-4.0-fast-generate-001': 'Imagen 4 Fast',
  'imagen-4.0-generate-001': 'Imagen 4 Standard',
  'imagen-4.0-ultra-generate-001': 'Imagen 4 Ultra',
  'gpt-image-2': 'OpenAI GPT Image 2',
}

const FLIGHT_PROVIDER_LABELS: Record<string, string> = {
  amadeus: 'Amadeus',
  google_flights: 'Google Flights (SerpAPI)',
  skyscanner: 'Skyscanner',
}

const BROWSER_PROVIDER_LABELS: Record<string, string> = {
  cdp: 'Chrome CDP',
  playwright: 'Playwright',
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function asBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value : fallback
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

function boolLabel(value: boolean): string {
  return value ? 'Enabled' : 'Disabled'
}

function percentLabel(value: unknown, fallback: number): string {
  return `${Math.round(asNumber(value, fallback) * 100)}%`
}

function formatModelName(value: unknown): string {
  const model = asString(value)
  if (!model) return 'Default'
  return MODEL_LABELS[model] || model
    .split(/[-_]/)
    .filter(Boolean)
    .map(part => (/^\d/.test(part) ? part : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ')
}

function formatConfigValue(value: unknown): string | null {
  if (Array.isArray(value)) {
    return value.length > 0 ? `${value.length} configured` : null
  }
  if (typeof value === 'boolean') {
    return boolLabel(value)
  }
  if (typeof value === 'number') {
    return String(value)
  }
  if (typeof value === 'string') {
    return value.trim() || null
  }
  if (typeof value === 'object' && value !== null) {
    return Object.keys(value).length > 0 ? 'Configured' : null
  }
  return null
}

function formatConfigLabel(key: string, schema?: ConfigSchemaProperty): string {
  if (schema?.title) return String(schema.title)
  return key.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function getFallbackSkillCardFacts(
  config: SkillConfig,
  schemaProperties: Record<string, ConfigSchemaProperty>,
): SkillCardFact[] {
  const keywords = asStringArray(config.keywords)
  const facts: SkillCardFact[] = []

  Object.entries(config).forEach(([key, value]) => {
    if (HIDDEN_CARD_CONFIG_KEYS.has(key)) return

    const formatted = formatConfigValue(value)
    if (!formatted) return

    facts.push({
      label: formatConfigLabel(key, schemaProperties[key]),
      value: formatted,
    })
  })

  if (keywords.length > 0) {
    facts.push({ label: 'Keywords', value: `${keywords.length} configured` })
  }

  return facts
}

function getSkillCardFacts(
  skillType: string,
  config: SkillConfig,
  schemaProperties: Record<string, ConfigSchemaProperty>,
): SkillCardFact[] {
  switch (skillType) {
    case 'agent_communication':
      return [
        { label: 'Runtime model', value: 'Target agent setting' },
        { label: 'Timeout', value: `${asNumber(config.default_timeout, 60)}s` },
        { label: 'Depth limit', value: 'A2A permission rule' },
      ]
    case 'agent_switcher': {
      const keywordCount = asStringArray(config.keywords).length
      return [
        { label: 'Triggering', value: 'Agent tool call' },
        { label: 'Keywords', value: keywordCount > 0 ? `${keywordCount} configured` : 'Not required' },
      ]
    }
    case 'browser_automation':
      return [
        { label: 'Browser engine', value: BROWSER_PROVIDER_LABELS[asString(config.provider_type, 'playwright')] || asString(config.provider_type, 'playwright') },
        { label: 'Action timeout', value: `${asNumber(config.timeout_seconds, 30)}s` },
        { label: 'Triggering', value: 'Agent tool call' },
      ]
    case 'flight_search': {
      const settings = asRecord(config.settings)
      const preferDirect = asBoolean(settings.prefer_direct_flights, false)
      return [
        { label: 'Provider', value: FLIGHT_PROVIDER_LABELS[asString(config.provider, 'google_flights')] || asString(config.provider, 'google_flights') },
        { label: 'Currency', value: asString(settings.default_currency, 'BRL') },
        { label: 'Results', value: `${asNumber(settings.max_results, 5)} max` },
        { label: 'Direct flights', value: preferDirect ? 'Preferred' : 'Flexible' },
      ]
    }
    case 'image': {
      const model = asString(config.model, 'imagen-4.0-generate-001')
      const channels = asStringArray(config.enabled_channels)
      return [
        { label: 'Model', value: formatModelName(model) },
        { label: 'Mode', value: model.startsWith('imagen-') ? 'Generation only' : 'Generate and edit' },
        { label: 'Channels', value: channels.length > 0 ? `${channels.length} active` : 'All configured channels' },
        { label: 'Edit context', value: `${asNumber(config.lookback_messages, 5)} messages` },
      ]
    }
    case 'image_analysis': {
      const channels = asStringArray(config.enabled_channels)
      return [
        { label: 'Vision model', value: formatModelName(config.model) },
        { label: 'Triggering', value: 'Inbound images' },
        { label: 'Channels', value: channels.length > 0 ? `${channels.length} active` : 'All configured channels' },
        { label: 'Edit requests', value: 'Hand off to Image Generation' },
      ]
    }
    case 'knowledge_sharing':
      return [
        { label: 'Fact extraction', value: boolLabel(asBoolean(config.auto_extract, true)) },
        { label: 'Auto share', value: boolLabel(asBoolean(config.auto_share, true)) },
        { label: 'Access', value: asString(config.access_level, 'public') },
        { label: 'Confidence', value: percentLabel(config.min_confidence, 0.7) },
        { label: 'Group context', value: asBoolean(config.share_group_context, true) ? `${asNumber(config.group_context_window, 20)} messages` : 'Disabled' },
      ]
    case 'adaptive_personality':
      return [
        { label: 'Learning threshold', value: `${asNumber(config.detection_threshold, 3)} repeats` },
        { label: 'Adaptation strength', value: percentLabel(config.adaptation_strength, 0.7) },
        { label: 'Formality matching', value: boolLabel(asBoolean(config.mirror_formality, true)) },
        { label: 'Inside jokes', value: boolLabel(asBoolean(config.learn_inside_jokes, true)) },
      ]
    case 'okg_term_memory':
      return [
        { label: 'Auto capture', value: boolLabel(asBoolean(config.auto_capture_enabled, false)) },
        { label: 'Auto recall', value: boolLabel(asBoolean(config.auto_recall_enabled, true)) },
        { label: 'Recall limit', value: `${asNumber(config.auto_recall_limit, 5)} memories` },
        { label: 'Capture confidence', value: percentLabel(config.capture_min_confidence, 0.75) },
      ]
    case 'automation':
      return [
        { label: 'Flow execution', value: boolLabel(asBoolean(config.is_enabled, true)) },
        { label: 'Confirmation', value: asBoolean(config.require_confirmation, true) ? 'Required' : 'Not required' },
        { label: 'Parallel limit', value: `${asNumber(config.max_parallel_flows, 5)} flows` },
      ]
    case 'sandboxed_tools':
      return [
        { label: 'Tool access', value: 'Configured per tool' },
        { label: 'Runtime', value: 'Isolated toolbox containers' },
      ]
    default:
      return getFallbackSkillCardFacts(config, schemaProperties)
  }
}

function normalizeTranscriptConfig(
  config: Record<string, unknown> | null | undefined,
): TranscriptSkillConfig {
  const raw = config || {}
  // ``tenant_default`` was retired (no tenant-level ASR default — instances
  // are assigned per-agent). Stale rows still carrying it collapse to
  // 'openai' so they fall back to the cloud Whisper API instead of silently
  // resolving to a phantom tenant default.
  const rawAsrMode = raw.asr_mode
  const asrMode: TranscriptASRMode =
    rawAsrMode === 'openai' || rawAsrMode === 'instance'
      ? rawAsrMode
      : raw.asr_instance_id
        ? 'instance'
        : 'openai'

  const normalized: TranscriptSkillConfig = {
    ...raw,
    language: typeof raw.language === 'string' ? raw.language : 'auto',
    model: typeof raw.model === 'string' ? raw.model : 'whisper-1',
    response_mode: raw.response_mode === 'transcript_only' ? 'transcript_only' : 'conversational',
    asr_mode: asrMode,
    asr_instance_id: typeof raw.asr_instance_id === 'number' ? raw.asr_instance_id : null,
  }
  if (normalized.asr_mode !== 'instance') {
    normalized.asr_instance_id = null
  }
  return normalized
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export default function AgentSkillsManager({ agentId }: Props) {
  const [availableSkills, setAvailableSkills] = useState<SkillDefinition[]>([])
  const [agentSkills, setAgentSkills] = useState<AgentSkill[]>([])
  const [skillIntegrations, setSkillIntegrations] = useState<SkillIntegration[]>([])
  const [loading, setLoading] = useState(true)
  const [configuring, setConfiguring] = useState<string | null>(null)
  const [configuringProvider, setConfiguringProvider] = useState<string | null>(null)
  const [configData, setConfigData] = useState<SkillConfig>({})

  // Provider configuration state
  const [schedulerProviders, setSchedulerProviders] = useState<SkillProvider[]>([])
  const [emailProviders, setEmailProviders] = useState<SkillProvider[]>([])
  const [webSearchProviders, setWebSearchProviders] = useState<SkillProvider[]>([])
  const [ticketManagementProviders, setTicketManagementProviders] = useState<SkillProvider[]>([])
  const [codeRepositoryProviders, setCodeRepositoryProviders] = useState<SkillProvider[]>([])
  const [selectedProvider, setSelectedProvider] = useState<string>('')
  const [selectedIntegration, setSelectedIntegration] = useState<number | null>(null)
  const [providerLoading, setProviderLoading] = useState(false)

  // Permission configuration state (for Google Calendar)
  const [providerPermissions, setProviderPermissions] = useState<{ read: boolean; write: boolean }>({
    read: true,
    write: false
  })

  // Ticket Management capability toggles (per-agent, six booleans)
  const [ticketCapabilities, setTicketCapabilities] = useState<Record<string, boolean>>(
    Object.fromEntries(
      Object.entries(TICKET_MANAGEMENT_CAPABILITY_LABELS).map(([k, v]) => [k, v.defaultEnabled])
    )
  )

  // Email (Gmail) capability toggles — same shape, read on / write off by default.
  const [emailCapabilities, setEmailCapabilities] = useState<Record<string, boolean>>(
    Object.fromEntries(
      Object.entries(EMAIL_CAPABILITY_LABELS).map(([k, v]) => [k, v.defaultEnabled])
    )
  )

  // Code Repository (GitHub) capability toggles — read defaults ON, write OFF.
  const [codeRepositoryCapabilities, setCodeRepositoryCapabilities] = useState<Record<string, boolean>>(
    Object.fromEntries(
      Object.entries(CODE_REPOSITORY_CAPABILITY_LABELS).map(([k, v]) => [k, v.defaultEnabled])
    )
  )

  // Unified Audio skill state
  const [configuringAudio, setConfiguringAudio] = useState(false)
  const [audioTab, setAudioTab] = useState<AudioTab>('tts')

  // TTS Provider state
  const [ttsProviders, setTTSProviders] = useState<TTSProviderInfo[]>([])
  const [ttsVoices, setTTSVoices] = useState<TTSVoice[]>([])
  const [ttsConfig, setTTSConfig] = useState<AgentTTSConfig>({ provider: 'kokoro', voice: 'pf_dora', language: 'pt', speed: 1.0 })

  // Transcript config state
  const [transcriptConfig, setTranscriptConfig] = useState<TranscriptSkillConfig>(normalizeTranscriptConfig(undefined))

  // Shell skill state
  const [configuringShell, setConfiguringShell] = useState(false)
  const [shellConfig, setShellConfig] = useState<ShellSkillConfig>({ wait_for_result: false, default_timeout: 60 })
  const [shellBeacons, setShellBeacons] = useState<ShellBeacon[]>([])

  // Skill-level security profile state (v1.6.0 Phase E)
  const [securityProfiles, setSecurityProfiles] = useState<SentinelProfile[]>([])
  const [skillSecurityAssignments, setSkillSecurityAssignments] = useState<Map<string, SentinelProfileAssignment | null>>(new Map())
  const [skillSecurityPopover, setSkillSecurityPopover] = useState<string | null>(null)
  const securityPopoverRef = useRef<HTMLDivElement>(null)

  // Phase 24: Custom Skills state
  const [customSkillAssignments, setCustomSkillAssignments] = useState<CustomSkillAssignment[]>([])
  const [availableCustomSkills, setAvailableCustomSkills] = useState<CustomSkillSummary[]>([])

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

  const buildDefaultSkillConfig = (skillDef?: SkillDefinition | null): SkillConfig => {
    if (!skillDef) return {}

    const schemaDefaults: SkillConfig = {}
    const schemaProperties = (skillDef.config_schema?.properties || {}) as Record<string, ConfigSchemaProperty>

    Object.entries(schemaProperties).forEach(([key, schema]) => {
      if (schema.default !== undefined) {
        schemaDefaults[key] = schema.default
      }
    })

    return {
      ...schemaDefaults,
      ...(skillDef.default_config || {}),
    }
  }

  const getSkillConfig = (skillType: string): SkillConfig => {
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
      alert(errorMessage(err, 'Failed to toggle skill'))
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
        openProviderConfig(info.providerKey as ProviderKey)
      } else if (info?.configType === 'audio') {
        openAudioConfig(skillType === 'audio_transcript' ? 'transcript' : 'tts')
      } else if (info?.configType === 'shell') {
        openShellConfig()
      } else {
        openConfig(skillType)
      }
    } catch (err) {
      console.error('Failed to add skill:', err)
      alert(errorMessage(err, 'Failed to add skill'))
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

  const openProviderConfig = async (providerKey: ProviderKey) => {
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
      } else if (providerKey === 'ticket_management') {
        setTicketManagementProviders(providers)
      } else if (providerKey === 'code_repository') {
        setCodeRepositoryProviders(providers)
      }

      // Load current integration for this skill
      const skillType = PROVIDER_SKILLS[providerKey].skillType
      const integration = getSkillIntegration(skillType)
      const providersWithDefaults = providers as SkillProviderWithDefault[]
      const defaultProvider =
        (providersWithDefaults.find(p => p.is_default)?.provider_type)
        || providers[0]?.provider_type
        || (providerKey === 'scheduler' ? 'flows'
          : providerKey === 'email' ? 'gmail'
          : providerKey === 'ticket_management' ? 'jira'
          : providerKey === 'code_repository' ? 'github'
          : 'brave')

      if (integration) {
        setSelectedProvider(
          providerKey === 'web_search'
            ? (getSkillConfig(skillType).provider || defaultProvider)
            : (integration.scheduler_provider || defaultProvider)
        )
        setSelectedIntegration(integration.integration_id)

        // Load permissions from config if available
        const permissions = integration.config?.permissions || { read: true, write: true }
        setProviderPermissions(permissions)
      } else {
        // Set default provider
        setSelectedProvider(defaultProvider)
        setSelectedIntegration(null)
        // For ticket_management, auto-select the only integration when there's exactly one
        if (providerKey === 'ticket_management') {
          const defaultProviderEntry = providers.find(p => p.provider_type === defaultProvider)
          if (defaultProviderEntry?.available_integrations?.length === 1) {
            setSelectedIntegration(defaultProviderEntry.available_integrations[0].integration_id)
          }
        }
        // Same auto-select-only-integration UX for code_repository (GitHub).
        if (providerKey === 'code_repository') {
          const defaultProviderEntry = providers.find(p => p.provider_type === defaultProvider)
          if (defaultProviderEntry?.available_integrations?.length === 1) {
            setSelectedIntegration(defaultProviderEntry.available_integrations[0].integration_id)
          }
        }
        // Default permissions: read-only for safety
        setProviderPermissions({ read: true, write: false })
      }

      // Load ticket capability toggles for ticket_management
      if (providerKey === 'ticket_management') {
        const skillCfg = getSkillConfig(skillType)
        const cfgCaps = (skillCfg?.capabilities as Record<string, { enabled?: boolean } | undefined>) || {}
        const next: Record<string, boolean> = {}
        for (const [capKey, meta] of Object.entries(TICKET_MANAGEMENT_CAPABILITY_LABELS)) {
          const stored = cfgCaps[capKey]
          next[capKey] = typeof stored?.enabled === 'boolean' ? stored.enabled : meta.defaultEnabled
        }
        setTicketCapabilities(next)
      }

      // Load email capability toggles for the email/gmail provider
      if (providerKey === 'email') {
        const skillCfg = getSkillConfig(skillType)
        const cfgCaps = (skillCfg?.capabilities as Record<string, { enabled?: boolean } | undefined>) || {}
        const next: Record<string, boolean> = {}
        for (const [capKey, meta] of Object.entries(EMAIL_CAPABILITY_LABELS)) {
          const stored = cfgCaps[capKey]
          next[capKey] = typeof stored?.enabled === 'boolean' ? stored.enabled : meta.defaultEnabled
        }
        setEmailCapabilities(next)
      }

      // Load code_repository capability toggles (GitHub provider).
      if (providerKey === 'code_repository') {
        const skillCfg = getSkillConfig(skillType)
        const cfgCaps = (skillCfg?.capabilities as Record<string, { enabled?: boolean } | undefined>) || {}
        const next: Record<string, boolean> = {}
        for (const [capKey, meta] of Object.entries(CODE_REPOSITORY_CAPABILITY_LABELS)) {
          const stored = cfgCaps[capKey]
          next[capKey] = typeof stored?.enabled === 'boolean' ? stored.enabled : meta.defaultEnabled
        }
        setCodeRepositoryCapabilities(next)
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
      const skillType = PROVIDER_SKILLS[configuringProvider as ProviderKey].skillType

      // Build config with permissions (for Google Calendar)
      const config: SkillConfig = {}
      if (configuringProvider === 'scheduler' && selectedProvider === 'google_calendar') {
        config.permissions = providerPermissions
      }

      // For web_search, we need to update the skill config with the provider
      if (configuringProvider === 'web_search') {
        const currentConfig = getSkillConfig(skillType)
        // Merge existing config first, then overwrite the provider selected
        // in the modal so stale defaults like "brave" do not win.
        Object.assign(config, currentConfig, {
          provider: selectedProvider
        })

        // Update the skill config directly
        await api.updateAgentSkill(agentId, skillType, {
          is_enabled: true,
          config: config
        })
      } else if (configuringProvider === 'ticket_management') {
        // Persist the integration link AND the capability toggles in parallel.
        // Both PUTs are idempotent on retry; running them concurrently avoids a
        // half-updated DB state when a transient error fails the second call
        // after the first has already committed.
        const currentConfig = getSkillConfig(skillType)
        const capabilities: Record<string, { enabled: boolean; label?: string; description?: string }> = {}
        for (const [capKey, meta] of Object.entries(TICKET_MANAGEMENT_CAPABILITY_LABELS)) {
          capabilities[capKey] = {
            enabled: ticketCapabilities[capKey] ?? meta.defaultEnabled,
            label: meta.label,
            description: meta.description,
          }
        }
        const mergedConfig: SkillConfig = {
          ...currentConfig,
          execution_mode: 'tool',
          integration_id: selectedIntegration,
          capabilities,
        }
        await Promise.all([
          api.updateAgentSkill(agentId, skillType, {
            is_enabled: true,
            config: mergedConfig,
          }),
          api.updateSkillIntegration(agentId, skillType, {
            scheduler_provider: null,
            integration_id: selectedIntegration,
            config: undefined,
          }),
        ])
      } else if (configuringProvider === 'email') {
        // Email/Gmail: persist integration link AND capability toggles in
        // parallel — same Promise.all pattern used by ticket_management so a
        // transient API error doesn't leave a half-updated state.
        const currentConfig = getSkillConfig(skillType)
        const capabilities: Record<string, { enabled: boolean; label?: string; description?: string }> = {}
        for (const [capKey, meta] of Object.entries(EMAIL_CAPABILITY_LABELS)) {
          capabilities[capKey] = {
            enabled: emailCapabilities[capKey] ?? meta.defaultEnabled,
            label: meta.label,
            description: meta.description,
          }
        }
        const mergedConfig: SkillConfig = {
          ...currentConfig,
          execution_mode: 'tool',
          integration_id: selectedIntegration,
          capabilities,
        }
        await Promise.all([
          api.updateAgentSkill(agentId, skillType, {
            is_enabled: true,
            config: mergedConfig,
          }),
          api.updateSkillIntegration(agentId, skillType, {
            scheduler_provider: null,
            integration_id: selectedIntegration,
            config: undefined,
          }),
        ])
      } else if (configuringProvider === 'code_repository') {
        // Code Repository (GitHub today): same atomic Promise.all pattern as
        // ticket_management/email — keep AgentSkill.config and the
        // AgentSkillIntegration link in sync so the LLM tool spec and the
        // integration link can never disagree about which connection or
        // which capabilities are active.
        const currentConfig = getSkillConfig(skillType)
        const capabilities: Record<string, { enabled: boolean; label?: string; description?: string }> = {}
        for (const [capKey, meta] of Object.entries(CODE_REPOSITORY_CAPABILITY_LABELS)) {
          capabilities[capKey] = {
            enabled: codeRepositoryCapabilities[capKey] ?? meta.defaultEnabled,
            label: meta.label,
            description: meta.description,
          }
        }
        const mergedConfig: SkillConfig = {
          ...currentConfig,
          execution_mode: 'tool',
          integration_id: selectedIntegration,
          capabilities,
        }
        await Promise.all([
          api.updateAgentSkill(agentId, skillType, {
            is_enabled: true,
            config: mergedConfig,
          }),
          api.updateSkillIntegration(agentId, skillType, {
            scheduler_provider: null,
            integration_id: selectedIntegration,
            config: undefined,
          }),
        ])
      } else {
        // Save skill integration for scheduler
        await api.updateSkillIntegration(agentId, skillType, {
          scheduler_provider: configuringProvider === 'scheduler' ? selectedProvider : null,
          integration_id: selectedIntegration,
          config: Object.keys(config).length > 0 ? config : undefined,
        })

        // Make sure the skill is enabled
        if (!isSkillEnabled(skillType)) {
          const skillDef = availableSkills.find(s => s.skill_type === skillType)
          const defaultConfig: SkillConfig = {}
          if (skillDef) {
            Object.entries((skillDef.config_schema || {}) as Record<string, ConfigSchemaProperty>).forEach(([key, schema]) => {
              defaultConfig[key] = schema.default
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
        setTranscriptConfig(normalizeTranscriptConfig(transcriptSkill.config))
      } else {
        setTranscriptConfig(normalizeTranscriptConfig(undefined))
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

  const renderCapabilitiesConfig = (capabilities: Record<string, unknown>) => {
    return (
      <div className="space-y-3">
        {Object.entries(capabilities).map(([capKey, capValue]) => {
          const capConfig = (
            typeof capValue === 'object' && capValue !== null ? capValue : {}
          ) as CapabilityConfig
          const capEnabled = capConfig.enabled ?? true
          const capLabel = capConfig.label || capKey.replace(/_/g, ' ')
          const capDesc = capConfig.description || ''

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
                  const capabilityMap = newConfig.capabilities as Record<string, CapabilityConfig>
                  if (!capabilityMap[capKey]) {
                    capabilityMap[capKey] = { ...capConfig }
                  }
                  capabilityMap[capKey].enabled = e.target.checked
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

  const renderConfigInput = (key: string, schema: ConfigSchemaProperty, value: unknown) => {
    const inputClasses = "w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"

    if (key === 'capabilities' && schema.type === 'object' && value) {
      return renderCapabilitiesConfig(value as Record<string, unknown>)
    }

    if (schema.type === 'boolean') {
      return (
        <label className="flex items-center cursor-pointer">
          <input
            type="checkbox"
            checked={Boolean(value !== undefined ? value : schema.default)}
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
      const arrayValue = Array.isArray(value)
        ? value.map(String)
        : Array.isArray(schema.default)
          ? schema.default.map(String)
          : []
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
          value={String(value || schema.default || '')}
          onChange={(e) => setConfigData({ ...configData, [key]: e.target.value })}
          className={inputClasses}
        >
          {options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      )
    }

    if (schema.type === 'number') {
      return (
        <input
          type="number"
          value={String(value !== undefined ? value : (schema.default || 0))}
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
        value={String(value || schema.default || '')}
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
    } catch (err) {
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

  // Render provider-based skill card (Scheduler, Email, Web Search, Ticket Management)
  const renderProviderSkillCard = (
    displayName: string,
    providerKey: ProviderKey,
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
      providerDisplay =
        provider === 'brave' ? 'Brave Search'
        : provider === 'google' ? 'Google Search (SerpAPI)'
        : provider === 'searxng' ? 'SearXNG'
        : provider
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
      } else if (providerKey === 'ticket_management') {
        providerDisplay = 'Atlassian Jira'
        integrationDisplay = integration.integration_name || ''
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
                {transcriptConfigData.asr_mode === 'instance'
                  ? 'Pinned local ASR'
                  : 'OpenAI Whisper'} • {transcriptConfigData.response_mode === 'transcript_only' ? 'Transcript only' : 'Conversational'}
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
                      {transcriptConfigData.asr_mode === 'instance'
                        ? 'Pinned local'
                        : 'OpenAI Whisper'}
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
          const beacons = (await response.json()) as ShellBeacon[]
          setShellBeacons(beacons.filter(b => b.is_online))
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
    const schemaProperties = (skill.config_schema?.properties || {}) as Record<string, ConfigSchemaProperty>
    const cardFacts = getSkillCardFacts(skill.skill_type, config, schemaProperties).slice(0, 6)

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

        {cardFacts.length > 0 && (
          <div className="mt-4 pt-4 border-t border-teal-200 dark:border-teal-700">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {cardFacts.map((fact) => (
                <div key={`${fact.label}:${fact.value}`} className="bg-tsushin-surface rounded p-2 border border-tsushin-border">
                  <div className="text-xs text-tsushin-slate">{fact.label}</div>
                  <div className="text-sm font-medium truncate" title={fact.value}>{fact.value}</div>
                </div>
              ))}
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

        {cardFacts.length === 0 && (
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
    return new Set(customSkillAssignments.map(a => a.custom_skill_id))
  }, [customSkillAssignments])

  // Filter which provider skills are enabled
  const enabledProviderSkills = useMemo(() => {
    const result: { providerKey: ProviderKey; displayName: string; skillType: string; icon: React.FC<IconProps>; description: string }[] = []
    const providerEntries: { providerKey: ProviderKey; displayName: string; skillType: string; icon: React.FC<IconProps>; description: string }[] = [
      { providerKey: 'scheduler', displayName: 'Scheduler', skillType: 'flows', icon: CalendarIcon, description: 'Create events, reminders, and schedule AI conversations. Choose between built-in Flows, Google Calendar, or Asana.' },
      { providerKey: 'email', displayName: 'Email', skillType: 'gmail', icon: MailIcon, description: 'Read, search, send, reply to, and draft emails. Connect your Gmail account to enable email access.' },
      { providerKey: 'web_search', displayName: 'Web Search', skillType: 'web_search', icon: SearchIcon, description: 'Search the web for information. Choose between Brave Search, SearXNG, or Google Search (via SerpAPI).' },
      { providerKey: 'ticket_management', displayName: 'Ticket Management', skillType: 'ticket_management', icon: WrenchIcon, description: 'Search, read, and (when enabled) act on tickets in a connected ticketing system. Today: Atlassian Jira via REST API.' },
      { providerKey: 'code_repository', displayName: 'Code Repository', skillType: 'code_repository', icon: GitHubIcon, description: 'Search repos, list pull requests and issues, read PR details, and (when enabled) open issues or comment on PRs. Today: GitHub via REST API.' },
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
    configuringProvider === 'ticket_management' ? ticketManagementProviders :
    configuringProvider === 'code_repository' ? codeRepositoryProviders :
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
                Configure {PROVIDER_SKILLS[configuringProvider as ProviderKey].displayName}
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
                          : selectedProvider === 'searxng'
                          ? 'bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700'
                          : 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-700'
                      }`}>
                        <p className="text-sm font-medium inline-flex items-center gap-1.5">
                          <SearchIcon size={14} /> {
                            selectedProvider === 'brave'
                              ? 'Brave Search'
                              : selectedProvider === 'searxng'
                              ? 'SearXNG'
                              : 'Google Search (SerpAPI)'
                          }
                        </p>
                        <p className="text-xs mt-1">
                          {(selectedProviderData as WebSearchProviderWithPricing).pricing?.description || 'Web search provider'}
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

                  {/* Capability toggles — Email (Gmail) */}
                  {configuringProvider === 'email' && !providerLoading && (
                    <div className="border-t pt-6 border-tsushin-border">
                      <label className="block text-sm font-medium mb-3">
                        Capabilities
                      </label>
                      <p className="text-xs text-tsushin-muted mb-3">
                        Disabled actions are removed from the agent&apos;s tool spec — the LLM never even sees them.
                        Read actions are on by default; write actions are off by default for safety.
                      </p>
                      <div className="space-y-3 bg-tsushin-ink p-4 rounded-lg">
                        {Object.entries(EMAIL_CAPABILITY_LABELS).map(([capKey, meta]) => (
                          <div key={capKey} className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              id={`email-cap-${capKey}`}
                              checked={!!emailCapabilities[capKey]}
                              onChange={(e) =>
                                setEmailCapabilities(prev => ({ ...prev, [capKey]: e.target.checked }))
                              }
                              className="mt-1 w-4 h-4 text-teal-600 border-gray-300 rounded focus:ring-teal-500"
                            />
                            <div className="flex-1">
                              <label htmlFor={`email-cap-${capKey}`} className="font-medium text-sm cursor-pointer">
                                {meta.label}
                                {!meta.defaultEnabled && (
                                  <span className="ml-2 rounded-full border border-yellow-500/30 bg-yellow-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-yellow-300">write</span>
                                )}
                              </label>
                              <p className="text-xs text-tsushin-muted mt-1">{meta.description}</p>
                            </div>
                          </div>
                        ))}
                        {!Object.values(emailCapabilities).some(Boolean) && (
                          <div className="mt-2 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded text-xs text-yellow-700 dark:text-yellow-300 flex items-center gap-1.5">
                            <AlertTriangleIcon size={12} /> At least one capability must be enabled
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Capability toggles — Ticket Management (Jira) */}
                  {configuringProvider === 'ticket_management' && !providerLoading && (
                    <div className="border-t pt-6 border-tsushin-border">
                      <label className="block text-sm font-medium mb-3">
                        Capabilities
                      </label>
                      <p className="text-xs text-tsushin-muted mb-3">
                        Disabled actions are removed from the agent&apos;s tool spec — the LLM never even sees them.
                        Read actions are on by default; write actions are off by default for safety.
                      </p>
                      <div className="space-y-3 bg-tsushin-ink p-4 rounded-lg">
                        {Object.entries(TICKET_MANAGEMENT_CAPABILITY_LABELS).map(([capKey, meta]) => (
                          <div key={capKey} className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              id={`ticket-cap-${capKey}`}
                              checked={!!ticketCapabilities[capKey]}
                              onChange={(e) =>
                                setTicketCapabilities(prev => ({ ...prev, [capKey]: e.target.checked }))
                              }
                              className="mt-1 w-4 h-4 text-teal-600 border-gray-300 rounded focus:ring-teal-500"
                            />
                            <div className="flex-1">
                              <label htmlFor={`ticket-cap-${capKey}`} className="font-medium text-sm cursor-pointer">
                                {meta.label}
                                {!meta.defaultEnabled && (
                                  <span className="ml-2 rounded-full border border-yellow-500/30 bg-yellow-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-yellow-300">write</span>
                                )}
                              </label>
                              <p className="text-xs text-tsushin-muted mt-1">{meta.description}</p>
                            </div>
                          </div>
                        ))}
                        {!Object.values(ticketCapabilities).some(Boolean) && (
                          <div className="mt-2 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded text-xs text-yellow-700 dark:text-yellow-300 flex items-center gap-1.5">
                            <AlertTriangleIcon size={12} /> At least one capability must be enabled
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Capability toggles — Code Repository (GitHub) */}
                  {configuringProvider === 'code_repository' && !providerLoading && (
                    <div className="border-t pt-6 border-tsushin-border">
                      <label className="block text-sm font-medium mb-3">
                        Capabilities
                      </label>
                      <p className="text-xs text-tsushin-muted mb-3">
                        Disabled actions are removed from the agent&apos;s tool spec — the LLM never even sees them.
                        Read actions are on by default; write actions are off by default for safety.
                      </p>
                      <div className="space-y-3 bg-tsushin-ink p-4 rounded-lg">
                        {Object.entries(CODE_REPOSITORY_CAPABILITY_LABELS).map(([capKey, meta]) => (
                          <div key={capKey} className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              id={`coderepo-cap-${capKey}`}
                              checked={!!codeRepositoryCapabilities[capKey]}
                              onChange={(e) =>
                                setCodeRepositoryCapabilities(prev => ({ ...prev, [capKey]: e.target.checked }))
                              }
                              className="mt-1 w-4 h-4 text-teal-600 border-gray-300 rounded focus:ring-teal-500"
                            />
                            <div className="flex-1">
                              <label htmlFor={`coderepo-cap-${capKey}`} className="font-medium text-sm cursor-pointer">
                                {meta.label}
                                {!meta.defaultEnabled && (
                                  <span className="ml-2 rounded-full border border-yellow-500/30 bg-yellow-500/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-yellow-300">write</span>
                                )}
                              </label>
                              <p className="text-xs text-tsushin-muted mt-1">{meta.description}</p>
                            </div>
                          </div>
                        ))}
                        {!Object.values(codeRepositoryCapabilities).some(Boolean) && (
                          <div className="mt-2 p-2 bg-yellow-50 dark:bg-yellow-900/20 rounded text-xs text-yellow-700 dark:text-yellow-300 flex items-center gap-1.5">
                            <AlertTriangleIcon size={12} /> At least one capability must be enabled
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
                disabled={(() => {
                  if (selectedProviderData?.requires_integration && !selectedIntegration) return true
                  if (configuringProvider === 'scheduler' && selectedProvider === 'google_calendar' && !providerPermissions.read && !providerPermissions.write) return true
                  if (configuringProvider === 'ticket_management' && !Object.values(ticketCapabilities).some(Boolean)) return true
                  if (configuringProvider === 'email' && !Object.values(emailCapabilities).some(Boolean)) return true
                  if (configuringProvider === 'code_repository' && !Object.values(codeRepositoryCapabilities).some(Boolean)) return true
                  return false
                })()}
                className={`px-6 py-2 rounded-lg font-medium transition-colors ${
                  ((selectedProviderData?.requires_integration && !selectedIntegration) ||
                    (configuringProvider === 'scheduler' && selectedProvider === 'google_calendar' && !providerPermissions.read && !providerPermissions.write) ||
                    (configuringProvider === 'ticket_management' && !Object.values(ticketCapabilities).some(Boolean)) ||
                    (configuringProvider === 'email' && !Object.values(emailCapabilities).some(Boolean)) ||
                    (configuringProvider === 'code_repository' && !Object.values(codeRepositoryCapabilities).some(Boolean)))
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

                  <AudioTranscriptFields
                    value={{
                      responseMode: transcriptConfig.response_mode || 'conversational',
                      language: transcriptConfig.language || 'auto',
                      model: transcriptConfig.model || 'whisper-1',
                      asrMode: transcriptConfig.asr_mode || 'openai',
                      asrInstanceId: transcriptConfig.asr_instance_id ?? null,
                    }}
                    onChange={(patch) => setTranscriptConfig(prev => normalizeTranscriptConfig({
                      ...prev,
                      response_mode: patch.responseMode !== undefined ? patch.responseMode : prev.response_mode,
                      language: patch.language !== undefined ? patch.language : prev.language,
                      model: patch.model !== undefined ? patch.model : prev.model,
                      asr_mode: patch.asrMode !== undefined ? patch.asrMode : prev.asr_mode,
                      asr_instance_id: patch.asrInstanceId !== undefined ? patch.asrInstanceId : prev.asr_instance_id,
                    }))}
                  />

                  {/* TTS Conflict Warning */}
                  {transcriptConfig.response_mode === 'transcript_only' && isSkillEnabled('audio_tts') && (
                    <div className="p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg">
                      <p className="text-sm font-medium text-red-800 dark:text-red-200 flex items-center gap-1.5"><AlertTriangleIcon size={14} /> TTS Conflict</p>
                      <p className="text-xs text-red-700 dark:text-red-300 mt-1">
                        &quot;Transcript Only&quot; mode cannot be used with TTS Response enabled. The transcript bypasses AI processing, so there&apos;s no text to convert to speech.
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
                              Both <code>/shell</code> AND natural language like &quot;list files in /tmp&quot; work.
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
                        {shellBeacons.map((beacon, idx) => (
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
                      <li>• <strong>Agentic:</strong> Ask naturally: &quot;List files in /tmp&quot;</li>
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
                Object.entries((availableSkills.find(s => s.skill_type === configuring)!.config_schema.properties || {}) as Record<string, ConfigSchemaProperty>).map(([key, schema]) => (
                  <div key={key}>
                    <label className="block text-sm font-medium mb-2 capitalize">
                      {schema.title || key.replace(/_/g, ' ')}
                    </label>
                    {renderConfigInput(key, schema, configData[key])}
                    {schema.description && (
                      <p className="text-xs text-tsushin-muted mt-1">{schema.description}</p>
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
