'use client'

/**
 * Integration Hub - Consolidated Single Page
 *
 * Manages all integrations organized by category:
 * - AI Providers: Ollama, Gemini, OpenAI, Anthropic, Groq, Grok, DeepSeek, Vertex AI, ElevenLabs
 * - Communication: WhatsApp, Telegram, Discord, Slack, Email (coming soon)
 * - Productivity: Asana, Google Calendar, Notion (coming soon)
 * - Developer Tools: Shell, Sandboxed Tools, GitHub (coming soon)
 * - Tool APIs: Brave Search, Tavily, Amadeus
 */

import { useEffect, useState, useCallback } from 'react'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useToast } from '@/contexts/ToastContext'
import { api, authenticatedFetch, WhatsAppMCPInstance, MCPHealthStatus, QRCodeResponse, TelegramBotInstance, TelegramHealthStatus, SlackIntegration, SlackIntegrationCreate, DiscordIntegration, DiscordIntegrationCreate, WebhookIntegration, WebhookIntegrationCreate, Config, ProviderInstance, VectorStoreInstance, TesterMCPStatus } from '@/lib/client'
import Modal from '@/components/ui/Modal'
import TelegramBotModal from '@/components/TelegramBotModal'
// V060-CHN-002: SlackSetupModal/DiscordSetupModal replaced by guided wizards.
// The bare modals dumped users into a 5-field form with no idea where to get a
// bot token, what scopes were needed, or how to wire the webhook back. The
// wizards (mirrors WhatsAppSetupWizard) walk through every Discord/Slack
// portal click, show the exact manifest/perms list, and surface the webhook
// URL with a copy button after save.
import SlackSetupModal from '@/components/SlackSetupWizard'
import DiscordSetupModal from '@/components/DiscordSetupWizard'
import PublicBaseUrlCard from '@/components/PublicBaseUrlCard'
import WebhookSetupModal from '@/components/WebhookSetupModal'
import WhatsAppCreateModeSelector from '@/components/hub/WhatsAppCreateModeSelector'
import ProviderInstanceModal from '@/components/providers/ProviderInstanceModal'
import VectorStoreCard from '@/components/vector-stores/VectorStoreCard'
import VectorStoreConfigModal from '@/components/vector-stores/VectorStoreConfigModal'
import MCPServerWizard from '@/components/mcp/MCPServerWizard'
import TypeaheadChipInput, { TypeaheadSuggestion } from '@/components/hub/TypeaheadChipInput'
import InfoTooltip from '@/components/ui/InfoTooltip'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'
import IntegrationSummary from '@/components/hub/IntegrationSummary'
import {
  GeminiIcon,
  OpenAIIcon,
  AnthropicIcon,
  GlobeIcon,
  LightningIcon,
  MicrophoneIcon,
  MessageIcon as MessageIconSvg,
  MailIcon,
  PlaneIcon,
  GamepadIcon,
  BriefcaseIcon,
  CheckCircleIcon,
  CalendarIcon,
  DocumentIcon,
  TerminalIcon as TerminalIconSvg,
  GitHubIcon,
  SearchIcon,
  BotIcon as BotIconSvg,
  BrainIcon,
  BeakerIcon,
  LightbulbIcon,
  RocketIcon,
  BellIcon,
  LockIcon,
  SmartphoneIcon,
  EnvelopeIcon,
  PlusIcon as PlusIconSvg,
  RadioIcon,
  ClipboardIcon as ClipboardIconSvg,
  ShieldIcon,
  BoxIcon as BoxIconSvg,
  PackageIcon,
  CreditCardIcon,
  AlertTriangleIcon,
  SlackIcon,
  DiscordIcon,
  WebhookIcon,
  CopyIcon,
  CloudIcon,
  type IconProps
} from '@/components/ui/icons'
import ToggleSwitch from '@/components/ui/ToggleSwitch'

type TabType = 'ai-providers' | 'communication' | 'productivity' | 'developer' | 'tool-apis' | 'mcp-servers' | 'vector-stores'

// SVG Icons for Hub Tabs
const BotIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="11" width="18" height="10" rx="2" />
    <circle cx="12" cy="5" r="2" />
    <path d="M12 7v4" />
    <line x1="8" y1="16" x2="8" y2="16" />
    <line x1="16" y1="16" x2="16" y2="16" />
  </svg>
)

const MessageIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
)

const ClipboardIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
  </svg>
)

const TerminalIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="4 17 10 11 4 5" />
    <line x1="12" y1="19" x2="20" y2="19" />
  </svg>
)

const WrenchIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
)

const BoxIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
    <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
    <line x1="12" y1="22.08" x2="12" y2="12" />
  </svg>
)

const ServerIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
    <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
    <line x1="6" y1="6" x2="6.01" y2="6" />
    <line x1="6" y1="18" x2="6.01" y2="18" />
  </svg>
)

const VectorStoreIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <ellipse cx="12" cy="5" rx="9" ry="3" />
    <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
    <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    <circle cx="18" cy="12" r="1.5" fill="currentColor" />
    <circle cx="6" cy="18" r="1.5" fill="currentColor" />
  </svg>
)

interface APIKey {
  id: number
  service: string
  api_key_preview: string
  is_active: boolean
  created_at: string
  updated_at: string
}

interface OllamaHealth {
  status: string
  base_url: string
  available: boolean
  models_count?: number
  models?: Array<{ name: string; size: number; modified_at: string }>
  error?: string
}

interface KokoroHealth {
  provider: string
  status: string
  message: string
  available: boolean
  latency_ms?: number
  details?: {
    service_url?: string
    voices?: number
    languages?: string[]
    is_free?: boolean
    hint?: string
  }
}

interface HubIntegration {
  id: number
  type: string
  name: string
  is_active: boolean
  health_status: string
  health_status_reason?: string
  workspace_gid?: string
  workspace_name?: string
}

interface ModalData {
  service: string
  api_key: string
  is_active: boolean
}

interface ToolboxStatus {
  status: string
  health: string
  container_name: string
  container_id?: string
  image?: string
}

// Grok (xAI) icon — X-shaped to match xAI branding
const GrokIcon = ({ size, className }: IconProps) => (
  <svg className={className} width={size || 20} height={size || 20} viewBox="0 0 24 24" fill="currentColor">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
  </svg>
)

// ============================================
// Service Definitions by Category
// ============================================

const AI_PROVIDERS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'gemini', label: 'Google Gemini', Icon: GeminiIcon, description: 'Google\'s multimodal AI', status: 'available' },
  { value: 'openai', label: 'OpenAI (GPT)', Icon: OpenAIIcon, description: 'GPT-4, ChatGPT models', status: 'available' },
  { value: 'anthropic', label: 'Anthropic Claude', Icon: AnthropicIcon, description: 'Claude 3.5, reasoning models', status: 'available' },
  { value: 'openrouter', label: 'OpenRouter', Icon: GlobeIcon, description: '100+ models via single API', status: 'available' },
  { value: 'groq', label: 'Groq', Icon: LightningIcon, description: 'Ultra-fast inference', status: 'available' },
  { value: 'grok', label: 'Grok (xAI)', Icon: GrokIcon, description: 'xAI Grok models', status: 'available' },
  { value: 'deepseek', label: 'DeepSeek', Icon: BrainIcon, description: 'Affordable reasoning & chat', status: 'available' },
  { value: 'vertex_ai', label: 'Vertex AI (GCP)', Icon: CloudIcon, description: 'Google Cloud Model Garden', status: 'available' },
  { value: 'elevenlabs', label: 'ElevenLabs', Icon: MicrophoneIcon, description: 'Voice AI & TTS synthesis', status: 'available' },
]

const COMMUNICATION_CHANNELS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'whatsapp', label: 'WhatsApp', Icon: MessageIconSvg, description: 'WhatsApp Business via MCP', status: 'available' },
  { value: 'gmail', label: 'Gmail', Icon: MailIcon, description: 'Google Gmail for email actions', status: 'available' },
  { value: 'telegram', label: 'Telegram', Icon: PlaneIcon, description: 'Telegram Bot API', status: 'available' },  // Phase 10.1.1: Now available!
  { value: 'slack', label: 'Slack', Icon: SlackIcon, description: 'Slack workspace integration', status: 'available' },
  { value: 'discord', label: 'Discord', Icon: DiscordIcon, description: 'Discord bot integration', status: 'available' },
  { value: 'webhook', label: 'Webhook', Icon: WebhookIcon, description: 'HTTP webhook integration (bidirectional)', status: 'available' },
]

const PRODUCTIVITY_APPS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'asana', label: 'Asana', Icon: CheckCircleIcon, description: 'Task & project management', status: 'available' },
  { value: 'google_calendar', label: 'Google Calendar', Icon: CalendarIcon, description: 'Calendar & scheduling', status: 'available' },
  { value: 'notion', label: 'Notion', Icon: DocumentIcon, description: 'Knowledge base & docs', status: 'coming_soon' },
]

const DEVELOPER_TOOLS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'shell', label: 'Shell Command Center', Icon: TerminalIconSvg, description: 'Remote shell execution & beacon management', status: 'available' },
  { value: 'github', label: 'GitHub', Icon: GitHubIcon, description: 'Issues, PRs, repositories', status: 'coming_soon' },
]

const TOOL_APIS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'brave_search', label: 'Brave Search', Icon: SearchIcon, description: 'Privacy-focused web search API', status: 'available' },
  { value: 'tavily', label: 'Tavily', Icon: GlobeIcon, description: 'AI-focused web search API', status: 'available' },
  { value: 'google_flights', label: 'SerpAPI (Google Services)', Icon: GlobeIcon, description: 'Unified SerpAPI key for Google Search, Google Flights, and other Google services', status: 'available' },
  { value: 'amadeus', label: 'Amadeus', Icon: PlaneIcon, description: 'Flight search API', status: 'available' },
]

const NOTIFICATION_SERVICES: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = []

export default function HubPage() {
  const toast = useToast()
  const { isGlobalAdmin, hasPermission } = useAuth()
  // BUG-322: Use forceOpenWizard so the wizard always opens when explicitly triggered from Hub,
  // even if the user previously dismissed it.
  const { forceOpenWizard: openWhatsAppWizard } = useWhatsAppWizard()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState<TabType>(() => {
    if (typeof window === 'undefined') return 'ai-providers'
    const validTabs: TabType[] = ['ai-providers', 'communication', 'productivity', 'developer', 'tool-apis', 'mcp-servers', 'vector-stores']
    const requested = new URLSearchParams(window.location.search).get('tab') as TabType | null
    return requested && validTabs.includes(requested) ? requested : 'ai-providers'
  })

  // Sync activeTab with ?tab= query param when it changes (e.g., via soft nav back from sub-pages)
  useEffect(() => {
    const validTabs: TabType[] = ['ai-providers', 'communication', 'productivity', 'developer', 'tool-apis', 'mcp-servers', 'vector-stores']
    const requested = searchParams?.get('tab') as TabType | null
    if (requested && validTabs.includes(requested)) {
      setActiveTab(requested)
    }
  }, [searchParams])

  // API Keys state
  const [apiKeys, setApiKeys] = useState<APIKey[]>([])
  const [ollamaHealth, setOllamaHealth] = useState<OllamaHealth | null>(null)
  const [kokoroHealth, setKokoroHealth] = useState<KokoroHealth | null>(null)
  const [hubIntegrations, setHubIntegrations] = useState<HubIntegration[]>([])

  // MCP Instances state
  const [mcpInstances, setMcpInstances] = useState<WhatsAppMCPInstance[]>([])
  const [healthStatuses, setHealthStatuses] = useState<Record<number, MCPHealthStatus>>({})
  const [testerStatus, setTesterStatus] = useState<TesterMCPStatus | null>(null)

  // Phase 10.1.1: Telegram Bot Integration
  const [telegramInstances, setTelegramInstances] = useState<TelegramBotInstance[]>([])
  const [telegramHealthStatuses, setTelegramHealthStatuses] = useState<Record<number, TelegramHealthStatus>>({})
  const [showTelegramModal, setShowTelegramModal] = useState(false)

  // v0.6.0: Slack Integration
  const [slackIntegrations, setSlackIntegrations] = useState<SlackIntegration[]>([])
  const [showSlackSetupModal, setShowSlackSetupModal] = useState(false)
  const [slackTestLoading, setSlackTestLoading] = useState<number | null>(null)

  // v0.6.0: Discord Integration
  const [discordIntegrations, setDiscordIntegrations] = useState<DiscordIntegration[]>([])
  const [showDiscordSetupModal, setShowDiscordSetupModal] = useState(false)

  // v0.6.0: Webhook-as-a-Channel
  const [webhookIntegrations, setWebhookIntegrations] = useState<WebhookIntegration[]>([])
  const [showWebhookSetupModal, setShowWebhookSetupModal] = useState(false)
  const [webhookSaving, setWebhookSaving] = useState(false)
  const [discordTestLoading, setDiscordTestLoading] = useState<number | null>(null)

  // Vertex AI configuration state
  const [showVertexAiModal, setShowVertexAiModal] = useState(false)
  const [vertexProjectId, setVertexProjectId] = useState('')
  const [vertexRegion, setVertexRegion] = useState('us-east5')
  const [vertexSaEmail, setVertexSaEmail] = useState('')
  const [vertexPrivateKey, setVertexPrivateKey] = useState('')
  // BUG-513: Track unsaved form edits so Test Connection can be blocked until
  // the user saves the modal — the backend test endpoint only validates the
  // stored tenant config, so testing unsaved draft fields would always hit
  // the previously saved values and mislead the user.
  const [vertexDirty, setVertexDirty] = useState(false)
  const [vertexJsonPaste, setVertexJsonPaste] = useState('')
  const [vertexSaving, setVertexSaving] = useState(false)
  const [vertexTesting, setVertexTesting] = useState(false)
  const [vertexTestResult, setVertexTestResult] = useState<{success: boolean; message: string} | null>(null)

  // Toolbox Container state
  const [toolboxStatus, setToolboxStatus] = useState<ToolboxStatus | null>(null)

  // Provider Instances state (Phase 21)
  const [providerInstances, setProviderInstances] = useState<ProviderInstance[]>([])
  const [instanceModalOpen, setInstanceModalOpen] = useState(false)
  const [editingInstance, setEditingInstance] = useState<ProviderInstance | null>(null)
  const [selectedVendor, setSelectedVendor] = useState<string>('')
  const [instanceMenuOpen, setInstanceMenuOpen] = useState<number | null>(null)

  // Local Services state (Ollama & Kokoro management)
  const [kokoroContainerStatus, setKokoroContainerStatus] = useState<{ status: string; name?: string; image?: string; message?: string } | null>(null)
  const [kokoroActionLoading, setKokoroActionLoading] = useState(false)
  const [ollamaEnabled, setOllamaEnabled] = useState(false)
  const [ollamaToggleLoading, setOllamaToggleLoading] = useState(false)
  const [ollamaUrlEditing, setOllamaUrlEditing] = useState(false)
  const [ollamaUrlValue, setOllamaUrlValue] = useState('')
  const [ollamaUrlSaving, setOllamaUrlSaving] = useState(false)
  const [ollamaTestResult, setOllamaTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [ollamaTestLoading, setOllamaTestLoading] = useState(false)

  // MCP Servers state (Phase 26)
  const [mcpServers, setMcpServers] = useState<any[]>([])
  const [mcpServersLoading, setMcpServersLoading] = useState(false)
  const [showMcpServerModal, setShowMcpServerModal] = useState(false)
  const [mcpWizardServer, setMcpWizardServer] = useState<{ id: number; server_name: string } | null>(null)
  const [mcpServerForm, setMcpServerForm] = useState({
    server_name: '',
    description: '',
    transport_type: 'sse' as string,
    server_url: '',
    auth_type: 'none' as string,
    auth_token: '',
    auth_header_name: '',
    stdio_binary: '',
    stdio_args: [] as string[],
    trust_level: 'untrusted' as string,
    timeout_seconds: 30,
    idle_timeout_seconds: 300,
  })
  const [mcpServerActionLoading, setMcpServerActionLoading] = useState<number | null>(null)
  const [allowedBinaries, setAllowedBinaries] = useState<string[]>(['uvx'])

  // v0.6.0: Vector Store Instances
  const [vectorStoreInstances, setVectorStoreInstances] = useState<VectorStoreInstance[]>([])
  const [vectorStoresLoading, setVectorStoresLoading] = useState(false)
  const [showVectorStoreModal, setShowVectorStoreModal] = useState(false)
  const [editingVectorStore, setEditingVectorStore] = useState<VectorStoreInstance | null>(null)
  const [vectorStoreTestLoading, setVectorStoreTestLoading] = useState<number | null>(null)

  // UI state
  const [loading, setLoading] = useState(true)
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [apiKeyDeleteTarget, setApiKeyDeleteTarget] = useState<string | null>(null)
  const [deletingApiKeyService, setDeletingApiKeyService] = useState<string | null>(null)
  const [showMcpCreateModal, setShowMcpCreateModal] = useState(false)
  const [showCreateModeSelector, setShowCreateModeSelector] = useState(false)
  const [showQRModal, setShowQRModal] = useState(false)
  const [showFiltersModal, setShowFiltersModal] = useState(false)  // Phase 17: Instance filters modal
  const [editingKey, setEditingKey] = useState<APIKey | null>(null)
  const [selectedMcpInstance, setSelectedMcpInstance] = useState<WhatsAppMCPInstance | null>(null)
  const [selectedQrResource, setSelectedQrResource] = useState<'instance' | 'tester' | null>(null)
  const [qrCode, setQRCode] = useState<string | null>(null)
  // QR Modal polling state for auto-refresh and auto-close
  const [qrPollingActive, setQrPollingActive] = useState(false)
  const [qrLastRefresh, setQrLastRefresh] = useState<Date | null>(null)
  const [qrAuthSuccess, setQrAuthSuccess] = useState(false)
  const [qrStatus, setQrStatus] = useState<'loading' | 'ready' | 'degraded'>('loading')
  const [qrStatusMessage, setQrStatusMessage] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const [systemConfig, setSystemConfig] = useState<Config | null>(null)
  const [whatsappDelaySeconds, setWhatsappDelaySeconds] = useState<string>('5')
  const [savingWhatsappDelay, setSavingWhatsappDelay] = useState(false)
  const [whatsappDelayError, setWhatsappDelayError] = useState<string | null>(null)

  // Phase 17: Instance filters form state
  const [filterGroupFilters, setFilterGroupFilters] = useState<string[]>([])
  const [filterNumberFilters, setFilterNumberFilters] = useState<string[]>([])
  const [filterGroupKeywords, setFilterGroupKeywords] = useState<string[]>([])
  const [filterDmAutoMode, setFilterDmAutoMode] = useState(false)
  const [filterInputGroup, setFilterInputGroup] = useState('')
  const [filterInputNumber, setFilterInputNumber] = useState('')
  const [filterInputKeyword, setFilterInputKeyword] = useState('')

  // Form state
  const [modalData, setModalData] = useState<ModalData>({
    service: '',
    api_key: '',
    is_active: true
  })
  const [mcpPhoneNumber, setMcpPhoneNumber] = useState('')
  const [mcpInstanceType, setMcpInstanceType] = useState<'agent' | 'tester'>('agent')

  // Google OAuth credentials state (read-only, configured in Settings/Integrations)
  const [googleCredentials, setGoogleCredentials] = useState<{ client_id: string, client_secret: string } | null>(null)

  const canEditSettings = hasPermission('org.settings.write')
  const canReadSettings = hasPermission('org.settings.read')

  const loadMcpInstances = useCallback(async () => {
    try {
      const data = await api.getMCPInstances()
      setMcpInstances(data)

      // Load health status for each instance
      const healthPromises = data.map(async (instance) => {
        try {
          const health = await api.getMCPHealth(instance.id)
          return { instanceId: instance.id, health }
        } catch (err) {
          return { instanceId: instance.id, health: null }
        }
      })

      const healthResults = await Promise.all(healthPromises)
      setHealthStatuses(prev => {
        const updated = { ...prev }
        healthResults.forEach(({ instanceId, health }) => {
          if (health) {
            updated[instanceId] = health
          }
        })
        return updated
      })
    } catch (err) {
      console.error('Failed to load MCP instances:', err)
    }
  }, [])

  const loadTesterStatus = useCallback(async () => {
    try {
      const status = await api.getTesterStatus()
      setTesterStatus(status)
    } catch (err) {
      console.error('Failed to load tester status:', err)
    }
  }, [])

  useEffect(() => {
    loadAllData()
    const interval = setInterval(() => {
      loadHubIntegrations(true)
      fetchToolboxStatus()
      if (activeTab === 'communication') {
        loadMcpInstances()
        loadTesterStatus()
        loadTelegramInstances()  // Phase 10.1.1
        loadSlackIntegrations()  // v0.6.0
        loadDiscordIntegrations()  // v0.6.0
        loadWebhookIntegrations()  // v0.6.0: Webhook-as-Channel
      }
      if (activeTab === 'mcp-servers') {
        loadMcpServers()  // Phase 26
      }
      if (activeTab === 'vector-stores') {
        loadVectorStoreInstances()  // v0.6.0
      }
    }, 10000)
    return () => clearInterval(interval)
  }, [activeTab])

  useGlobalRefresh(() => loadAllData())

  // Close instance dropdown menu when clicking outside
  useEffect(() => {
    if (instanceMenuOpen === null) return
    const handleClickOutside = () => setInstanceMenuOpen(null)
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [instanceMenuOpen])

  // QR Code Modal polling - auto-refresh QR and auto-close on authentication
  useEffect(() => {
    if (!showQRModal || !selectedQrResource || (selectedQrResource === 'instance' && !selectedMcpInstance)) {
      setQrPollingActive(false)
      return
    }

    setQrPollingActive(true)
    let consecutiveFailures = 0
    let emptyQrPolls = 0
    let isCancelled = false

    const handleAuthSuccess = () => {
      if (isCancelled) return
      setQrAuthSuccess(true)

      // Brief delay to show success message, then close
      setTimeout(() => {
        if (isCancelled) return
        setShowQRModal(false)
        setQRCode(null)
        setSelectedMcpInstance(null)
        setSelectedQrResource(null)
        setQrAuthSuccess(false)
        setQrLastRefresh(null)
        setQrStatus('loading')
        setQrStatusMessage(null)

        // Refresh instances list to update status badges
        loadMcpInstances()
        loadTesterStatus()

        setSuccessMessage(selectedQrResource === 'tester' ? 'Tester WhatsApp connected successfully!' : 'WhatsApp connected successfully!')
        setTimeout(() => setSuccessMessage(null), 3000)
      }, 1500) // 1.5s to show success state
    }

    const checkAuthStatus = async () => {
      if (isCancelled) return

      try {
        const health = selectedQrResource === 'tester'
          ? await api.getTesterStatus()
          : await api.getMCPHealth(selectedMcpInstance!.id)

        // Only consider authenticated if ALL conditions are true:
        // 1. authenticated=true (device session exists in DB)
        // 2. connected=true (WebSocket is connected to WhatsApp)
        // 3. needs_reauth=false (session is valid, user didn't logout from phone)
        const isFullyAuthenticated = Boolean(health.authenticated) &&
                                      Boolean(health.connected) &&
                                      !health.needs_reauth
        if (isFullyAuthenticated) {
          handleAuthSuccess()
          return true
        }
        if (health.error) {
          setQrStatusMessage(health.error)
        }
      } catch (err) {
        consecutiveFailures += 1
        console.debug('QR auth check error (will retry):', err)
        if (consecutiveFailures >= 2) {
          setQrStatus('degraded')
          setQrStatusMessage(err instanceof Error ? err.message : 'Failed to check WhatsApp health')
        }
      }
      return false
    }

    const refreshQRCode = async () => {
      if (isCancelled) return

      try {
        // First check if authenticated
        const isAuth = await checkAuthStatus()
        if (isAuth) return // Already handled auth success

        // Refresh QR code
        const qrResponse = selectedQrResource === 'tester'
          ? await api.getTesterQRCode()
          : await api.getMCPQRCode(selectedMcpInstance!.id)

        if (isCancelled) return

        if (qrResponse.qr_code) {
          setQRCode(qrResponse.qr_code)
          setQrLastRefresh(new Date())
          setQrStatus('ready')
          setQrStatusMessage(qrResponse.message || 'Scan QR code with WhatsApp')
          consecutiveFailures = 0
          emptyQrPolls = 0
        } else {
          emptyQrPolls += 1
          if (emptyQrPolls >= 3) {
            setQrStatus('degraded')
            setQrStatusMessage(qrResponse.message || 'QR code is not becoming available. Restart or reset authentication.')
          } else {
            setQrStatus('loading')
            setQrStatusMessage(qrResponse.message || 'Waiting for QR code...')
          }
        }
      } catch (err) {
        console.warn('QR refresh error (will retry):', err)
        consecutiveFailures += 1
        if (consecutiveFailures >= 2) {
          setQrStatus('degraded')
          setQrStatusMessage(err instanceof Error ? err.message : 'Failed to refresh QR code')
        }
      }
    }

    // Initial auth check after short delay (give time for initial fetch)
    const initialTimeout = setTimeout(checkAuthStatus, 2000)

    // Set up intervals:
    // - Auth check every 3 seconds (fast, lightweight)
    // - QR refresh every 15 seconds (heavier, new image - WhatsApp expires ~20s)
    const authCheckInterval = setInterval(checkAuthStatus, 3000)
    const qrRefreshInterval = setInterval(refreshQRCode, 15000)

    // Cleanup function
    return () => {
      isCancelled = true
      setQrPollingActive(false)
      clearTimeout(initialTimeout)
      clearInterval(authCheckInterval)
      clearInterval(qrRefreshInterval)
    }
  }, [showQRModal, selectedMcpInstance, selectedQrResource, loadMcpInstances, loadTesterStatus])

  // Fetch allowed stdio binaries when MCP server modal opens
  useEffect(() => {
    if (showMcpServerModal) {
      loadAllowedBinaries()
    }
  }, [showMcpServerModal])

  const loadAllData = async () => {
    setLoading(true)
    try {
      await Promise.all([
        fetchAPIKeys(),
        fetchOllamaHealth(),
        fetchKokoroHealth(),
        fetchKokoroContainerStatus(),
        loadHubIntegrations(),
        loadMcpInstances(),
        loadTesterStatus(),
        loadTelegramInstances(),  // Phase 10.1.1
        loadSlackIntegrations(),  // v0.6.0
        loadDiscordIntegrations(),  // v0.6.0
        loadWebhookIntegrations(),  // v0.6.0: Webhook-as-Channel
        fetchToolboxStatus(),
        loadGoogleCredentials(),
        loadSystemConfig(),
        fetchProviderInstances(),  // Phase 21: Provider Instances
        loadMcpServers(),  // Phase 26: MCP Servers
        loadVectorStoreInstances(),  // v0.6.0: Vector Store Instances
      ])
    } finally {
      setLoading(false)
    }
  }

  const loadSystemConfig = async () => {
    if (!canReadSettings) {
      return
    }

    try {
      const config = await api.getConfig()
      setSystemConfig(config)
      const delayValue = config.whatsapp_conversation_delay_seconds ?? 5
      setWhatsappDelaySeconds(String(delayValue))
    } catch (error) {
      console.error('Failed to load system config:', error)
    }
  }

  const fetchAPIKeys = async () => {
    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/api-keys`)
      if (!response.ok) {
        const errorText = await response.text()
        console.error('Failed to fetch API keys:', response.status, errorText)
        setError(`Failed to load API keys: ${response.status}`)
        return
      }
      const data = await response.json()
      setApiKeys(data)
    } catch (error) {
      console.error('Failed to fetch API keys:', error)
      setError('Failed to load API keys')
    }
  }

  const fetchProviderInstances = async () => {
    try {
      const instances = await api.getProviderInstances()
      setProviderInstances(instances)
    } catch (error) {
      console.error('Failed to fetch provider instances:', error)
    }
  }

  // Phase 26: MCP Servers
  const loadMcpServers = async () => {
    try {
      setMcpServersLoading(true)
      const servers = await api.getMCPServers()
      setMcpServers(servers)
    } catch (error) {
      console.error('Failed to fetch MCP servers:', error)
    } finally {
      setMcpServersLoading(false)
    }
  }

  const loadVectorStoreInstances = async () => {
    try {
      setVectorStoresLoading(true)
      const instances = await api.getVectorStoreInstances()
      setVectorStoreInstances(instances)
    } catch (error) {
      console.error('Failed to fetch vector store instances:', error)
    } finally {
      setVectorStoresLoading(false)
    }
  }

  const loadAllowedBinaries = async () => {
    try {
      const result = await api.getAllowedBinaries()
      if (result.binaries && result.binaries.length > 0) {
        setAllowedBinaries(result.binaries)
      }
    } catch (error) {
      console.error('Failed to fetch allowed binaries:', error)
    }
  }

  const handleCreateMcpServer = async () => {
    if (!mcpServerForm.server_name.trim()) {
      toast.error('Server name is required')
      return
    }
    setSaving(true)
    try {
      const payload: any = {
        server_name: mcpServerForm.server_name,
        description: mcpServerForm.description || undefined,
        transport_type: mcpServerForm.transport_type,
        auth_type: mcpServerForm.auth_type,
        trust_level: mcpServerForm.trust_level,
        timeout_seconds: mcpServerForm.timeout_seconds,
        idle_timeout_seconds: mcpServerForm.idle_timeout_seconds,
      }
      if (mcpServerForm.transport_type === 'stdio') {
        payload.stdio_binary = mcpServerForm.stdio_binary
        payload.stdio_args = mcpServerForm.stdio_args.filter(a => a.trim())
      } else {
        payload.server_url = mcpServerForm.server_url
      }
      if (mcpServerForm.auth_type !== 'none' && mcpServerForm.auth_token) {
        payload.auth_token = mcpServerForm.auth_token
      }
      if (mcpServerForm.auth_header_name) {
        payload.auth_header_name = mcpServerForm.auth_header_name
      }

      const createdServer = await api.createMCPServer(payload)
      toast.success('MCP server created successfully')

      if (createdServer?.id) {
        try {
          await api.testMCPServer(createdServer.id)
        } catch { /* test is optional — tools may still be discoverable */ }
        setMcpWizardServer({ id: createdServer.id, server_name: createdServer.server_name || payload.server_name })
      }

      setShowMcpServerModal(false)
      setMcpServerForm({
        server_name: '', description: '', transport_type: 'sse', server_url: '',
        auth_type: 'none', auth_token: '', auth_header_name: '', stdio_binary: '',
        stdio_args: [], trust_level: 'untrusted', timeout_seconds: 30, idle_timeout_seconds: 300,
      })
      loadMcpServers()
    } catch (err: any) {
      toast.error(err.message || 'Failed to create MCP server')
    } finally {
      setSaving(false)
    }
  }

  const handleConnectMcpServer = async (serverId: number) => {
    setMcpServerActionLoading(serverId)
    try {
      await api.connectMCPServer(serverId)
      toast.success('MCP server connected')
      loadMcpServers()
    } catch (err: any) {
      toast.error(err.message || 'Failed to connect')
    } finally {
      setMcpServerActionLoading(null)
    }
  }

  const handleDisconnectMcpServer = async (serverId: number) => {
    setMcpServerActionLoading(serverId)
    try {
      await api.disconnectMCPServer(serverId)
      toast.success('MCP server disconnected')
      loadMcpServers()
    } catch (err: any) {
      toast.error(err.message || 'Failed to disconnect')
    } finally {
      setMcpServerActionLoading(null)
    }
  }

  const handleRefreshMcpTools = async (serverId: number) => {
    setMcpServerActionLoading(serverId)
    try {
      const result = await api.refreshMCPTools(serverId)
      toast.success(`Refreshed: ${result.total_tools} tools found (${result.new_tools} new)`)
      loadMcpServers()
    } catch (err: any) {
      toast.error(err.message || 'Failed to refresh tools')
    } finally {
      setMcpServerActionLoading(null)
    }
  }

  const handleDeleteMcpServer = async (serverId: number, serverName: string) => {
    if (!confirm(`Delete MCP server "${serverName}"? This will remove the server and all discovered tools.`)) return
    setMcpServerActionLoading(serverId)
    try {
      await api.deleteMCPServer(serverId)
      toast.success('MCP server deleted')
      loadMcpServers()
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete MCP server')
    } finally {
      setMcpServerActionLoading(null)
    }
  }

  const fetchOllamaHealth = async () => {
    try {
      const data = await api.getOllamaHealth()
      setOllamaHealth(data)
    } catch (error) {
      setOllamaHealth({
        status: 'offline',
        base_url: 'http://localhost:11434',
        available: false,
        error: 'Cannot reach backend'
      })
    }
  }

  const fetchKokoroHealth = async () => {
    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/tts-providers/kokoro/status`)
      if (response.ok) {
        const data = await response.json()
        setKokoroHealth(data)
      } else {
        setKokoroHealth({
          provider: 'kokoro',
          status: 'unavailable',
          message: 'Health check failed',
          available: false,
          details: { hint: 'Start with: docker compose --profile tts up -d' }
        })
      }
    } catch (error) {
      setKokoroHealth({
        provider: 'kokoro',
        status: 'unavailable',
        message: 'Cannot reach backend',
        available: false,
        details: { hint: 'Start with: docker compose --profile tts up -d' }
      })
    }
  }

  // ==================== Kokoro Container Management ====================

  const fetchKokoroContainerStatus = async () => {
    try {
      const data = await api.getKokoroStatus()
      setKokoroContainerStatus(data)
    } catch (error) {
      setKokoroContainerStatus({ status: 'error', message: 'Cannot reach backend' })
    }
  }

  const handleStartKokoro = async () => {
    setKokoroActionLoading(true)
    try {
      const result = await api.startKokoro()
      if (!result.success) {
        toast.error(result.message)
        setKokoroActionLoading(false)
        return
      }
      toast.success('Kokoro container started — waiting for service to initialize...')
      // Update container status immediately
      await fetchKokoroContainerStatus()
      // Poll health with retries (Kokoro needs time to load models)
      const maxRetries = 20
      const retryInterval = 3000 // 3 seconds
      for (let i = 0; i < maxRetries; i++) {
        await new Promise(r => setTimeout(r, retryInterval))
        const apiUrl = ''
        try {
          const resp = await authenticatedFetch(`${apiUrl}/api/tts-providers/kokoro/status`)
          if (resp.ok) {
            const data = await resp.json()
            if (data.available) {
              setKokoroHealth(data)
              toast.success('Kokoro TTS is ready!')
              setKokoroActionLoading(false)
              return
            }
          }
        } catch { /* keep retrying */ }
      }
      // Final fetch even if not healthy yet
      await fetchKokoroHealth()
      toast.error('Kokoro container is running but service is still initializing. Click "Refresh Status" to check again.')
    } catch (err: any) {
      toast.error(err.message || 'Failed to start Kokoro')
    } finally {
      setKokoroActionLoading(false)
    }
  }

  const handleStopKokoro = async () => {
    setKokoroActionLoading(true)
    try {
      const result = await api.stopKokoro()
      if (result.success) {
        toast.success(result.message)
      } else {
        toast.error(result.message)
      }
      await Promise.all([fetchKokoroContainerStatus(), fetchKokoroHealth()])
    } catch (err: any) {
      toast.error(err.message || 'Failed to stop Kokoro')
    } finally {
      setKokoroActionLoading(false)
    }
  }

  // Auto-poll Kokoro health when container is running but service not yet available
  useEffect(() => {
    if (
      kokoroContainerStatus?.status === 'running' &&
      !kokoroHealth?.available &&
      !kokoroActionLoading
    ) {
      const interval = setInterval(async () => {
        await fetchKokoroHealth()
      }, 5000) // poll every 5s
      return () => clearInterval(interval)
    }
  }, [kokoroContainerStatus?.status, kokoroHealth?.available, kokoroActionLoading])

  // ==================== Ollama Instance Management ====================

  // Derive Ollama enabled state from provider instances
  useEffect(() => {
    const ollamaInstance = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    setOllamaEnabled(!!ollamaInstance)
    if (ollamaInstance?.base_url) {
      setOllamaUrlValue(ollamaInstance.base_url)
    } else if (ollamaHealth?.base_url) {
      setOllamaUrlValue(ollamaHealth.base_url)
    }
  }, [providerInstances, ollamaHealth])

  const handleOllamaToggle = async () => {
    setOllamaToggleLoading(true)
    try {
      if (ollamaEnabled) {
        // Disable: soft-delete the Ollama instance
        const ollamaInstance = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
        if (ollamaInstance) {
          await api.deleteProviderInstance(ollamaInstance.id)
          toast.success('Ollama disabled')
        }
      } else {
        // Enable: ensure an Ollama instance exists
        await api.ensureOllamaInstance()
        toast.success('Ollama enabled')
      }
      await fetchProviderInstances()
      await fetchOllamaHealth()
    } catch (err: any) {
      toast.error(err.message || 'Failed to toggle Ollama')
    } finally {
      setOllamaToggleLoading(false)
    }
  }

  const handleOllamaUrlSave = async () => {
    const ollamaInstance = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!ollamaInstance) return

    setOllamaUrlSaving(true)
    try {
      await api.updateProviderInstance(ollamaInstance.id, { base_url: ollamaUrlValue })
      toast.success('Ollama URL updated')
      setOllamaUrlEditing(false)
      await Promise.all([fetchProviderInstances(), fetchOllamaHealth()])
    } catch (err: any) {
      toast.error(err.message || 'Failed to update URL')
    } finally {
      setOllamaUrlSaving(false)
    }
  }

  const handleOllamaTest = async () => {
    const ollamaInstance = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!ollamaInstance) {
      // If no instance, just refresh the health check
      await fetchOllamaHealth()
      return
    }

    setOllamaTestLoading(true)
    setOllamaTestResult(null)
    try {
      const result = await api.testProviderConnection(ollamaInstance.id)
      setOllamaTestResult(result)
      if (result.success) {
        toast.success(`Connected (${result.latency_ms}ms)`)
      } else {
        toast.error(result.message)
      }
      await fetchProviderInstances()
    } catch (err: any) {
      setOllamaTestResult({ success: false, message: err.message || 'Test failed' })
      toast.error(err.message || 'Test failed')
    } finally {
      setOllamaTestLoading(false)
    }
  }

  const fetchToolboxStatus = async () => {
    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/toolbox/status`)
      if (response.ok) {
        const data = await response.json()
        setToolboxStatus(data)
      }
    } catch (error) {
      console.error('Failed to fetch toolbox status:', error)
    }
  }

  const getToolboxBadge = () => {
    if (!toolboxStatus) {
      return <span className="badge badge-neutral">Unknown</span>
    }

    const status = toolboxStatus.status.toLowerCase()
    const health = toolboxStatus.health.toLowerCase()

    if (status === 'running' && health === 'healthy') {
      return <span className="badge badge-success">Running</span>
    } else if (status === 'running') {
      return <span className="badge badge-warning">Running (Unhealthy)</span>
    } else if (status === 'exited' || status === 'stopped') {
      return <span className="badge badge-error">Stopped</span>
    } else if (status === 'not_created' || health === 'not_created') {
      return <span className="badge badge-neutral">Not Started</span>
    } else {
      return <span className="badge badge-neutral">{status}</span>
    }
  }

  const loadHubIntegrations = async (refreshHealth: boolean = false) => {
    try {
      const apiUrl = ''
      const url = refreshHealth
        ? `${apiUrl}/api/hub/integrations?refresh_health=true`
        : `${apiUrl}/api/hub/integrations`
      const response = await authenticatedFetch(url)
      if (response.ok) {
        const data = await response.json()
        setHubIntegrations(data)
      }
    } catch (error) {
      console.error('Failed to fetch Hub integrations:', error)
    }
  }

  const handleSaveWhatsappDelay = async () => {
    if (!canEditSettings) {
      return
    }

    setSavingWhatsappDelay(true)
    setWhatsappDelayError(null)

    const parsed = Number(whatsappDelaySeconds)
    if (Number.isNaN(parsed) || parsed < 0) {
      setSavingWhatsappDelay(false)
      setWhatsappDelayError('Delay must be a non-negative number')
      return
    }

    try {
      const updated = await api.updateConfig({
        whatsapp_conversation_delay_seconds: parsed
      })
      setSystemConfig(updated)
      setWhatsappDelaySeconds(String(updated.whatsapp_conversation_delay_seconds ?? parsed))
      setSuccessMessage('WhatsApp conversation delay updated')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error) {
      console.error('Failed to update WhatsApp delay:', error)
      setWhatsappDelayError('Failed to update conversation delay')
    } finally {
      setSavingWhatsappDelay(false)
    }
  }

  // Phase 10.1.1: Load Telegram bot instances
  const loadTelegramInstances = useCallback(async () => {
    try {
      const data = await api.getTelegramInstances()
      setTelegramInstances(data)

      // Load health status for each instance
      const healthPromises = data.map(async (instance) => {
        try {
          const health = await api.getTelegramHealth(instance.id)
          return { instanceId: instance.id, health }
        } catch (err) {
          return { instanceId: instance.id, health: null }
        }
      })

      const healthResults = await Promise.all(healthPromises)
      setTelegramHealthStatuses(prev => {
        const updated = { ...prev }
        healthResults.forEach(({ instanceId, health }) => {
          if (health) {
            updated[instanceId] = health
          }
        })
        return updated
      })
    } catch (err) {
      console.error('Failed to load Telegram instances:', err)
    }
  }, [])

  // API Key handlers
  const openAddApiKeyModal = (service: string) => {
    setEditingKey(null)
    setModalData({ service, api_key: '', is_active: true })
    setShowApiKeyModal(true)
  }

  const openEditApiKeyModal = (key: APIKey) => {
    setEditingKey(key)
    setModalData({ service: key.service, api_key: '', is_active: key.is_active })
    setShowApiKeyModal(true)
  }

  // Vertex AI handlers
  const handleVertexJsonPaste = (jsonStr: string) => {
    setVertexJsonPaste(jsonStr)
    try {
      const parsed = JSON.parse(jsonStr)
      if (parsed.project_id) setVertexProjectId(parsed.project_id)
      if (parsed.client_email) setVertexSaEmail(parsed.client_email)
      if (parsed.private_key) setVertexPrivateKey(parsed.private_key)
      setVertexDirty(true)
    } catch {
      // Not valid JSON — user may be typing
    }
  }

  const handleSaveVertexAi = async () => {
    if (!vertexProjectId.trim() || !vertexSaEmail.trim() || !vertexPrivateKey.trim()) {
      toast.warning('Validation', 'Project ID, Service Account Email, and Private Key are required')
      return
    }
    setVertexSaving(true)
    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/api-keys`, {
        method: 'POST',
        body: JSON.stringify({
          service: 'vertex_ai',
          api_key: vertexPrivateKey.trim(),
          is_active: true
        })
      })
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Failed to save: ${errorText}`)
      }
      // Also save project_id, region, sa_email as structured metadata via separate keys
      // Save vertex_ai_project_id
      await authenticatedFetch(`${apiUrl}/api/api-keys`, {
        method: 'POST',
        body: JSON.stringify({ service: 'vertex_ai_project_id', api_key: vertexProjectId.trim(), is_active: true })
      })
      // Save vertex_ai_region
      await authenticatedFetch(`${apiUrl}/api/api-keys`, {
        method: 'POST',
        body: JSON.stringify({ service: 'vertex_ai_region', api_key: vertexRegion.trim(), is_active: true })
      })
      // Save vertex_ai_sa_email
      await authenticatedFetch(`${apiUrl}/api/api-keys`, {
        method: 'POST',
        body: JSON.stringify({ service: 'vertex_ai_sa_email', api_key: vertexSaEmail.trim(), is_active: true })
      })

      await fetchAPIKeys()
      setVertexDirty(false)
      setShowVertexAiModal(false)
      setSuccessMessage('Vertex AI credentials saved successfully')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save Vertex AI credentials')
    } finally {
      setVertexSaving(false)
    }
  }

  const handleTestVertexAi = async () => {
    setVertexTesting(true)
    setVertexTestResult(null)
    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/integrations/vertex_ai/test`, {
        method: 'POST',
        body: JSON.stringify({})
      })
      const result = await response.json()
      setVertexTestResult({ success: result.success, message: result.message })
    } catch (err: unknown) {
      setVertexTestResult({ success: false, message: err instanceof Error ? err.message : 'Test failed' })
    } finally {
      setVertexTesting(false)
    }
  }

  const saveAPIKey = async () => {
    if (!modalData.service || !modalData.api_key) {
      toast.warning('Validation', 'Please select a service and provide the API key')
      return
    }

    setSaving(true)
    setError(null)
    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/api-keys`, {
        method: 'POST',
        body: JSON.stringify(modalData)
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('Failed to save API key:', response.status, errorText)
        throw new Error(`Failed to save API key: ${response.status}`)
      }

      await fetchAPIKeys()
      setShowApiKeyModal(false)
      setSuccessMessage(editingKey ? 'API key updated' : 'API key added')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error: any) {
      console.error('Error saving API key:', error)
      setError(error.message || 'Failed to save API key')
    } finally {
      setSaving(false)
    }
  }

  const deleteAPIKey = async () => {
    if (!apiKeyDeleteTarget) return

    const service = apiKeyDeleteTarget
    setDeletingApiKeyService(service)
    setError(null)
    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/api-keys/${service}`, {
        method: 'DELETE'
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('Failed to delete API key:', response.status, errorText)
        throw new Error(`Failed to remove API key: ${response.status}`)
      }

      await fetchAPIKeys()
      setApiKeyDeleteTarget(null)
      setSuccessMessage('API key removed')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error: any) {
      console.error('Error deleting API key:', error)
      setError(error.message || 'Failed to remove API key')
    } finally {
      setDeletingApiKeyService(null)
    }
  }

  // MCP Instance handlers
  const handleCreateMcpInstance = async () => {
    if (!mcpPhoneNumber.trim()) {
      setError('Phone number is required')
      return
    }

    if (!mcpPhoneNumber.startsWith('+')) {
      setError('Phone number must start with country code (e.g., +55)')
      return
    }

    setSaving(true)
    setError(null)

    try {
      const newInstance = await api.createMCPInstance(mcpPhoneNumber.trim(), mcpInstanceType)
      setShowMcpCreateModal(false)
      setMcpPhoneNumber('')
      setMcpInstanceType('agent')
      setSuccessMessage(`Instance created on port ${newInstance.mcp_port}. Click QR Code to authenticate.`)
      setTimeout(() => setSuccessMessage(null), 8000)
      loadMcpInstances()
      loadTesterStatus()
    } catch (err: any) {
      setError(err.message || 'Failed to create instance')
    } finally {
      setSaving(false)
    }
  }

  const handleMcpAction = async (action: 'start' | 'stop' | 'restart' | 'delete', id: number) => {
    if (action === 'delete' && !confirm('Delete this instance?')) return

    try {
      if (action === 'start') await api.startMCPInstance(id)
      else if (action === 'stop') await api.stopMCPInstance(id)
      else if (action === 'restart') await api.restartMCPInstance(id)
      else if (action === 'delete') await api.deleteMCPInstance(id, false)

      setSuccessMessage(`Instance ${action}${action === 'delete' ? 'd' : 'ed'}`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadMcpInstances()
      loadTesterStatus()
    } catch (err: any) {
      setError(err.message || `Failed to ${action} instance`)
    }
  }

  const handleShowQR = async (instance: WhatsAppMCPInstance) => {
    setSelectedMcpInstance(instance)
    setSelectedQrResource('instance')
    setShowQRModal(true)
    setQRCode(null)
    setQrAuthSuccess(false)
    setQrLastRefresh(null)
    setQrStatus('loading')
    setQrStatusMessage('Checking WhatsApp session...')

    try {
      // First check health to see if we really need a QR code
      // This is more reliable than the QR endpoint's "authenticated" message
      const health = await api.getMCPHealth(instance.id)

      // If truly authenticated (not needs_reauth), show success
      // needs_reauth is set when user logs out from phone
      if (health.authenticated && health.connected && !health.needs_reauth) {
        setQrAuthSuccess(true)
        setTimeout(() => {
          setShowQRModal(false)
          setQRCode(null)
          setSelectedMcpInstance(null)
          setSelectedQrResource(null)
          setQrAuthSuccess(false)
          setQrLastRefresh(null)
          setQrStatus('loading')
          setQrStatusMessage(null)
          loadMcpInstances()
          setSuccessMessage('WhatsApp is already connected!')
          setTimeout(() => setSuccessMessage(null), 3000)
        }, 1500)
        return
      }

      // Not authenticated or needs reauth - fetch QR code
      const response: QRCodeResponse = await api.getMCPQRCode(instance.id)
      if (response.qr_code) {
        setQRCode(response.qr_code)
        setQrLastRefresh(new Date())
        setQrStatus('ready')
        setQrStatusMessage(response.message || 'Scan QR code with WhatsApp')
      } else {
        setQrStatus('loading')
        setQrStatusMessage(response.message || 'Waiting for QR code...')
      }
    } catch (err: any) {
      setQrStatus('degraded')
      setQrStatusMessage(err.message || 'Failed to fetch QR code')
    }
  }

  const handleShowTesterQR = async () => {
    setSelectedMcpInstance(null)
    setSelectedQrResource('tester')
    setShowQRModal(true)
    setQRCode(null)
    setQrAuthSuccess(false)
    setQrLastRefresh(null)
    setQrStatus('loading')
    setQrStatusMessage('Checking tester session...')

    try {
      const health = await api.getTesterStatus()
      if (health.authenticated && health.connected && !health.needs_reauth) {
        setQrAuthSuccess(true)
        setTimeout(() => {
          setShowQRModal(false)
          setQRCode(null)
          setSelectedQrResource(null)
          setQrAuthSuccess(false)
          setQrLastRefresh(null)
          setQrStatus('loading')
          setQrStatusMessage(null)
          loadTesterStatus()
          setSuccessMessage('Tester WhatsApp is already connected!')
          setTimeout(() => setSuccessMessage(null), 3000)
        }, 1500)
        return
      }

      const response = await api.getTesterQRCode()
      if (response.qr_code) {
        setQRCode(response.qr_code)
        setQrLastRefresh(new Date())
        setQrStatus('ready')
        setQrStatusMessage(response.message || 'Scan QR code with WhatsApp')
      } else {
        setQrStatus('loading')
        setQrStatusMessage(response.message || 'Waiting for tester QR code...')
      }
    } catch (err: any) {
      setQrStatus('degraded')
      setQrStatusMessage(err.message || 'Failed to fetch tester QR code')
    }
  }

  // Reset WhatsApp authentication (logout and regenerate QR)
  const handleResetAuth = async (instance: WhatsAppMCPInstance) => {
    if (!confirm(`Reset authentication for ${instance.phone_number}? This will:\n\n• Unlink the device from WhatsApp\n• Create a backup of session data\n• Generate a new QR code for re-authentication\n\nMessages will be preserved.`)) {
      return
    }

    try {
      setSuccessMessage('Resetting authentication...')
      const response = await api.logoutMCPInstance(instance.id, true)

      if (response.success) {
        setSuccessMessage(response.message || 'Authentication reset. Opening QR code...')
        setTimeout(() => setSuccessMessage(null), 3000)

        // Refresh instances list to update status
        await loadMcpInstances()

        // Open QR modal after a brief delay to allow container to generate new QR
        setTimeout(() => {
          handleShowQR(instance)
        }, 2000)
      } else {
        setError(response.message || 'Failed to reset authentication')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to reset authentication')
    }
  }

  const handleRestartTester = async () => {
    try {
      const result = await api.restartTester()
      setSuccessMessage(result.message || 'Tester restarting')
      setTimeout(() => setSuccessMessage(null), 3000)
      await loadTesterStatus()
    } catch (err: any) {
      setError(err.message || 'Failed to restart tester')
    }
  }

  const handleResetTesterAuth = async () => {
    if (!confirm('Reset authentication for the tester WhatsApp instance?')) {
      return
    }

    try {
      const response = await api.logoutTester()
      setSuccessMessage(response.message || 'Tester authentication reset. Opening QR code...')
      setTimeout(() => setSuccessMessage(null), 3000)
      await loadTesterStatus()
      setTimeout(() => {
        handleShowTesterQR()
      }, 1500)
    } catch (err: any) {
      setError(err.message || 'Failed to reset tester authentication')
    }
  }

  // Phase 17: Instance Filters handlers
  const handleConfigureFilters = (instance: WhatsAppMCPInstance) => {
    setSelectedMcpInstance(instance)
    setFilterGroupFilters(instance.group_filters || [])
    setFilterNumberFilters(instance.number_filters || [])
    setFilterGroupKeywords(instance.group_keywords || [])
    setFilterDmAutoMode(instance.dm_auto_mode || false)
    setFilterInputGroup('')
    setFilterInputNumber('')
    setFilterInputKeyword('')
    setShowFiltersModal(true)
  }

  const handleSaveFilters = async () => {
    if (!selectedMcpInstance) return

    setSaving(true)
    try {
      const updated = await api.updateMCPInstanceFilters(selectedMcpInstance.id, {
        group_filters: filterGroupFilters,
        number_filters: filterNumberFilters,
        group_keywords: filterGroupKeywords,
        dm_auto_mode: filterDmAutoMode,
      })

      // Update local state
      setMcpInstances(prev => prev.map(inst =>
        inst.id === selectedMcpInstance.id ? updated : inst
      ))

      setShowFiltersModal(false)
      setSuccessMessage('Message filters updated successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to update filters')
    } finally {
      setSaving(false)
    }
  }

  const addFilterItem = (type: 'group' | 'number' | 'keyword') => {
    if (type === 'group' && filterInputGroup.trim()) {
      if (!filterGroupFilters.includes(filterInputGroup.trim())) {
        setFilterGroupFilters([...filterGroupFilters, filterInputGroup.trim()])
      }
      setFilterInputGroup('')
    } else if (type === 'number' && filterInputNumber.trim()) {
      if (!filterNumberFilters.includes(filterInputNumber.trim())) {
        setFilterNumberFilters([...filterNumberFilters, filterInputNumber.trim()])
      }
      setFilterInputNumber('')
    } else if (type === 'keyword' && filterInputKeyword.trim()) {
      if (!filterGroupKeywords.includes(filterInputKeyword.trim())) {
        setFilterGroupKeywords([...filterGroupKeywords, filterInputKeyword.trim()])
      }
      setFilterInputKeyword('')
    }
  }

  const removeFilterItem = (type: 'group' | 'number' | 'keyword', item: string) => {
    if (type === 'group') {
      setFilterGroupFilters(filterGroupFilters.filter(f => f !== item))
    } else if (type === 'number') {
      setFilterNumberFilters(filterNumberFilters.filter(f => f !== item))
    } else if (type === 'keyword') {
      setFilterGroupKeywords(filterGroupKeywords.filter(f => f !== item))
    }
  }

  // Phase 10.1.1: Telegram Bot handlers
  const handleCreateTelegramBot = async (token: string) => {
    setSaving(true)
    try {
      await api.createTelegramInstance(token)
      setShowTelegramModal(false)
      setSuccessMessage('Telegram bot created successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadTelegramInstances()
    } catch (err: any) {
      setError(err.message || 'Failed to create Telegram bot')
    } finally {
      setSaving(false)
    }
  }

  const handleTelegramAction = async (action: 'start' | 'stop' | 'delete', id: number) => {
    if (action === 'delete' && !confirm('Delete this Telegram bot?')) return

    try {
      if (action === 'start') await api.startTelegramInstance(id)
      else if (action === 'stop') await api.stopTelegramInstance(id)
      else if (action === 'delete') await api.deleteTelegramInstance(id)

      setSuccessMessage(`Telegram bot ${action}${action === 'delete' ? 'd' : 'ed'}`)
      setTimeout(() => setSuccessMessage(null), 3000)
      loadTelegramInstances()
    } catch (err: any) {
      setError(err.message || `Failed to ${action} Telegram bot`)
    }
  }

  // v0.6.0: Slack Integration handlers
  const loadSlackIntegrations = useCallback(async () => {
    try {
      const data = await api.getSlackIntegrations()
      setSlackIntegrations(data)
    } catch (err) {
      console.error('Failed to load Slack integrations:', err)
    }
  }, [])

  const handleCreateSlackIntegration = async (data: SlackIntegrationCreate) => {
    setSaving(true)
    try {
      await api.createSlackIntegration(data)
      setShowSlackSetupModal(false)
      setSuccessMessage('Slack workspace connected successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadSlackIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to connect Slack workspace')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteSlackIntegration = async (id: number) => {
    if (!confirm('Disconnect this Slack workspace? The bot will stop responding to messages.')) return
    try {
      await api.deleteSlackIntegration(id)
      setSuccessMessage('Slack workspace disconnected')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadSlackIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to disconnect Slack workspace')
    }
  }

  const handleTestSlackConnection = async (id: number) => {
    setSlackTestLoading(id)
    try {
      const result = await api.testSlackConnection(id)
      if (result.success) {
        setSuccessMessage(result.message || 'Slack connection is healthy!')
      } else {
        setError(result.message || 'Slack connection test failed')
      }
      setTimeout(() => { setSuccessMessage(null); setError(null) }, 3000)
      loadSlackIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to test Slack connection')
    } finally {
      setSlackTestLoading(null)
    }
  }

  // v0.6.0: Discord Integration handlers
  const loadDiscordIntegrations = useCallback(async () => {
    try {
      const data = await api.getDiscordIntegrations()
      setDiscordIntegrations(data)
    } catch (err) {
      console.error('Failed to load Discord integrations:', err)
    }
  }, [])

  const handleCreateDiscordIntegration = async (data: DiscordIntegrationCreate) => {
    setSaving(true)
    try {
      await api.createDiscordIntegration(data)
      setShowDiscordSetupModal(false)
      setSuccessMessage('Discord bot connected successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadDiscordIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to connect Discord bot')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteDiscordIntegration = async (id: number) => {
    if (!confirm('Disconnect this Discord bot? The bot will stop responding to messages.')) return
    try {
      await api.deleteDiscordIntegration(id)
      setSuccessMessage('Discord bot disconnected')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadDiscordIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to disconnect Discord bot')
    }
  }

  const handleTestDiscordConnection = async (id: number) => {
    setDiscordTestLoading(id)
    try {
      const result = await api.testDiscordConnection(id)
      if (result.success) {
        setSuccessMessage(`Discord connection healthy! Bot: ${result.bot_user}, ${result.guilds} server(s)`)
      } else {
        setError(result.error || 'Discord connection test failed')
      }
      setTimeout(() => { setSuccessMessage(null); setError(null) }, 3000)
      loadDiscordIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to test Discord connection')
    } finally {
      setDiscordTestLoading(null)
    }
  }

  // v0.6.0: Webhook-as-a-Channel handlers
  const loadWebhookIntegrations = useCallback(async () => {
    try {
      const data = await api.listWebhookIntegrations()
      setWebhookIntegrations(data)
    } catch (err) {
      console.error('Failed to load webhook integrations:', err)
    }
  }, [])

  const handleCreateWebhookIntegration = async (data: WebhookIntegrationCreate) => {
    setWebhookSaving(true)
    try {
      const response = await api.createWebhookIntegration(data)
      setSuccessMessage('Webhook integration created successfully!')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadWebhookIntegrations()
      return { api_secret: response.api_secret, inbound_url: response.integration.inbound_url }
    } catch (err: any) {
      setError(err.message || 'Failed to create webhook integration')
      return null
    } finally {
      setWebhookSaving(false)
    }
  }

  const handleDeleteWebhookIntegration = async (id: number) => {
    if (!confirm('Delete this webhook integration? Any agent bound to it will be unbound.')) return
    try {
      await api.deleteWebhookIntegration(id)
      setSuccessMessage('Webhook integration deleted')
      setTimeout(() => setSuccessMessage(null), 3000)
      loadWebhookIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to delete webhook integration')
    }
  }

  const handleRotateWebhookSecret = async (id: number) => {
    if (!confirm('Rotate the HMAC secret? Your external system will need the new secret before the next request.')) return
    try {
      const result = await api.rotateWebhookSecret(id)
      await navigator.clipboard.writeText(result.api_secret).catch(() => {})
      setSuccessMessage(`New secret copied to clipboard: ${result.api_secret_preview}`)
      setTimeout(() => setSuccessMessage(null), 6000)
      loadWebhookIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to rotate webhook secret')
    }
  }

  // Asana handlers
  const handleAsanaConnect = async () => {
    const workspaceName = prompt('Enter your Asana workspace name:', 'My Workspace')
    if (!workspaceName?.trim()) return

    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/hub/asana/oauth/authorize`, {
        method: 'POST',
        body: JSON.stringify({ redirect_url: '/hub', workspace_name: workspaceName.trim() })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }

      const data = await response.json()
      window.location.href = data.authorization_url
    } catch (err: any) {
      if (err.message?.includes('ASANA_ENCRYPTION_KEY')) {
        toast.error('Asana Configuration', 'Asana OAuth not configured. Required: ASANA_ENCRYPTION_KEY in backend/.env')
      } else {
        toast.error('Connection Failed', `Failed to connect: ${err.message}`)
      }
    }
  }

  const handleAsanaDisconnect = async (integrationId: number) => {
    if (!confirm('Disconnect Asana integration?')) return

    try {
      const apiUrl = ''
      await authenticatedFetch(`${apiUrl}/api/hub/asana/oauth/disconnect/${integrationId}`, {
        method: 'POST'
      })
      loadHubIntegrations()
      setSuccessMessage('Asana disconnected')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error) {
      setError('Failed to disconnect Asana')
    }
  }

  // Google OAuth Credentials handlers
  const loadGoogleCredentials = async () => {
    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/credentials`)
      if (response.ok) {
        const data = await response.json()
        // BUG-343 fix: backend now returns 200 with configured=false instead of 404
        // when Google credentials are not set up on a fresh install.
        if (data && data.configured === false) {
          setGoogleCredentials(null)
        } else {
          setGoogleCredentials(data)
        }
      } else {
        setGoogleCredentials(null)
      }
    } catch (error) {
      // Silently set null — Google integration is optional
      setGoogleCredentials(null)
    }
  }

  // Google Calendar handlers
  const handleGoogleCalendarConnect = async () => {
    // Check if Google credentials are configured first
    if (!googleCredentials) {
      setError('Google OAuth credentials are not configured. Please configure them in Settings → Integrations first.')
      return
    }

    try {
      const apiUrl = ''
      const params = new URLSearchParams({ redirect_url: '/hub' })
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/calendar/oauth/authorize?${params}`, {
        method: 'POST'
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }

      const data = await response.json()
      window.location.href = data.authorization_url
    } catch (err: any) {
      if (err.message?.includes('credentials not configured')) {
        setError('Google OAuth credentials are not configured. Please configure them in Settings → Integrations first.')
      } else {
        setError(`Failed to connect: ${err.message}`)
      }
    }
  }

  const handleGoogleCalendarDisconnect = async (integrationId: number) => {
    if (!confirm('Disconnect Google Calendar integration?')) return

    try {
      const apiUrl = ''
      await authenticatedFetch(`${apiUrl}/api/hub/google/calendar/oauth/disconnect/${integrationId}`, {
        method: 'POST'
      })
      loadHubIntegrations()
      setSuccessMessage('Google Calendar disconnected')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error) {
      setError('Failed to disconnect Google Calendar')
    }
  }

  // Gmail handlers
  const handleGmailConnect = async () => {
    // Check if Google credentials are configured first
    if (!googleCredentials) {
      setError('Google OAuth credentials are not configured. Please configure them in Settings → Integrations first.')
      return
    }

    try {
      const apiUrl = ''
      const params = new URLSearchParams({ redirect_url: '/hub' })
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/gmail/oauth/authorize?${params}`, {
        method: 'POST'
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }

      const data = await response.json()
      window.location.href = data.authorization_url
    } catch (err: any) {
      if (err.message?.includes('credentials not configured')) {
        setError('Google OAuth credentials are not configured. Please configure them in Settings → Integrations first.')
      } else {
        setError(`Failed to connect: ${err.message}`)
      }
    }
  }

  const handleGmailDisconnect = async (integrationId: number) => {
    if (!confirm('Disconnect Gmail integration?')) return

    try {
      const apiUrl = ''
      await authenticatedFetch(`${apiUrl}/api/hub/google/gmail/oauth/disconnect/${integrationId}`, {
        method: 'POST'
      })
      loadHubIntegrations()
      setSuccessMessage('Gmail disconnected')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error) {
      setError('Failed to disconnect Gmail')
    }
  }

  // Re-authorize an expired/revoked integration
  const handleReauthorize = async (integrationId: number) => {
    try {
      const apiUrl = ''
      const params = new URLSearchParams({ redirect_url: '/hub' })
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/reauthorize/${integrationId}?${params}`, {
        method: 'POST'
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || `HTTP ${response.status}`)
      }

      const data = await response.json()
      window.location.href = data.authorization_url
    } catch (err: any) {
      setError(`Failed to re-authorize: ${err.message}`)
    }
  }

  // Helper functions
  const getApiKeyForService = (service: string) => apiKeys.find(k => k.service === service)

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      running: 'bg-green-500/20 text-green-400 border-green-500/50',
      starting: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/50',
      stopped: 'bg-gray-500/20 text-gray-400 border-gray-500/50',
      error: 'bg-red-500/20 text-red-400 border-red-500/50',
    }
    return `px-2 py-1 text-xs font-medium border rounded-full ${colors[status] || colors.stopped}`
  }

  const getAuthBadge = (health?: Pick<MCPHealthStatus, 'authenticated' | 'connected' | 'needs_reauth'>) => {
    if (health?.authenticated && health?.connected && !health?.needs_reauth) {
      return {
        className: 'bg-green-600/20 text-green-400 border border-green-600/50',
        label: 'Authenticated',
      }
    }
    if (health?.needs_reauth) {
      return {
        className: 'bg-orange-600/20 text-orange-300 border border-orange-600/50',
        label: 'Needs Reauth',
      }
    }
    return {
      className: 'bg-yellow-600/20 text-yellow-400 border border-yellow-600/50',
      label: 'Not Auth',
    }
  }

  const agentMcpInstances = mcpInstances.filter(instance => instance.instance_type === 'agent')
  const testerMcpInstances = mcpInstances.filter(instance => instance.instance_type === 'tester')
  const runtimeTesterInstances = testerMcpInstances.filter(instance => instance.status !== 'deleted')
  const communicationMcpInstances = mcpInstances
  const testerControlSource = testerStatus?.source ?? (runtimeTesterInstances.length > 0 ? 'runtime' : 'compose')
  const showDedicatedTesterCard = Boolean(testerStatus) || runtimeTesterInstances.length > 0
  const testerSourceLabel = testerControlSource === 'runtime' ? 'Runtime-managed tester' : 'Compose-managed tester'
  const testerContainerLabel = testerStatus?.name || runtimeTesterInstances[0]?.container_name || 'tester-mcp'
  const apiKeyDeleteLabel = apiKeyDeleteTarget
    ? [...AI_PROVIDERS, ...TOOL_APIS].find(item => item.value === apiKeyDeleteTarget)?.label ?? apiKeyDeleteTarget
    : null

  // Render integration card based on status
  const renderIntegrationCard = (
    item: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string },
    type: 'ai' | 'tool' | 'app'
  ) => {
    const apiKey = getApiKeyForService(item.value)
    const isComingSoon = item.status === 'coming_soon'
    const configuredInstance = type === 'ai'
      ? (
        providerInstances.find(i => i.vendor === item.value && i.is_active && i.api_key_configured && i.is_default)
        || providerInstances.find(i => i.vendor === item.value && i.is_active && i.api_key_configured)
      )
      : null
    const hasInstanceKey = Boolean(configuredInstance)
    const configuredViaInstance = !apiKey && hasInstanceKey
    const ItemIcon = item.Icon

    return (
      <div
        key={item.value}
        className={`card p-5 group ${isComingSoon ? 'opacity-60' : 'hover-glow'}`}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-transform ${isComingSoon ? 'bg-gray-700/50 text-gray-400' : 'bg-teal-500/10 text-teal-400 group-hover:scale-110'
              }`}>
              <ItemIcon size={20} />
            </div>
            <div>
              <h3 className="font-semibold text-white">{item.label}</h3>
              {hasInstanceKey && apiKey && (
                <span className="text-[10px] text-amber-400/80">Fallback — instance key takes priority</span>
              )}
              {configuredViaInstance && (
                <span className="text-[10px] text-teal-400/80">
                  Configured via instance: {configuredInstance?.instance_name}
                </span>
              )}
            </div>
          </div>
          {isComingSoon ? (
            <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-600/30 text-gray-400 border border-gray-600/50">
              Coming Soon
            </span>
          ) : (
            <span className={(apiKey?.is_active || configuredViaInstance) ? 'badge badge-success' : 'badge badge-neutral'}>
              {apiKey ? (apiKey.is_active ? 'Active' : 'Inactive') : (configuredViaInstance ? 'Instance configured' : 'Not configured')}
            </span>
          )}
        </div>
        <p className="text-xs text-tsushin-slate mb-4">{item.description}</p>
        {!isComingSoon && apiKey && (
          <div className="text-sm text-tsushin-slate mb-4">
            <p className="font-mono text-xs text-tsushin-accent">{apiKey.api_key_preview}</p>
          </div>
        )}
        {!isComingSoon && !apiKey && configuredInstance && (
          <div className="text-sm text-tsushin-slate mb-4">
            <p className="text-xs text-tsushin-slate">Using instance <span className="font-medium text-white">{configuredInstance.instance_name}</span></p>
            <p className="font-mono text-xs text-tsushin-accent">{configuredInstance.api_key_preview}</p>
          </div>
        )}
        {!isComingSoon && (
          <div className="flex gap-2">
            {apiKey ? (
              <>
                <button
                  onClick={() => item.value === 'vertex_ai' ? setShowVertexAiModal(true) : openEditApiKeyModal(apiKey)}
                  className="flex-1 btn-ghost py-2 text-sm"
                >
                  Edit
                </button>
                <button
                  onClick={() => setApiKeyDeleteTarget(apiKey.service)}
                  className="flex-1 py-2 text-sm rounded-lg font-medium bg-tsushin-vermilion/10 text-tsushin-vermilion border border-tsushin-vermilion/30 hover:bg-tsushin-vermilion/20 transition-all"
                >
                  Remove
                </button>
              </>
            ) : (
              <button
                onClick={() => item.value === 'vertex_ai' ? setShowVertexAiModal(true) : openAddApiKeyModal(item.value)}
                className="w-full btn-secondary py-2 text-sm"
              >
                {configuredViaInstance ? 'Configure Fallback' : 'Configure'}
              </button>
            )}
          </div>
        )}
        {isComingSoon && (
          <div className="text-center py-2">
            <span className="text-xs text-gray-500">Coming Soon</span>
          </div>
        )}
      </div>
    )
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading integrations...</p>
        </div>
      </div>
    )
  }

  const tabs = [
    { key: 'ai-providers', label: 'AI Providers', Icon: BotIcon, color: 'text-tsushin-indigo', iconBg: 'bg-tsushin-indigo/10' },
    { key: 'communication', label: 'Communication', Icon: MessageIcon, color: 'text-tsushin-accent', iconBg: 'bg-tsushin-accent/10' },
    { key: 'productivity', label: 'Productivity', Icon: ClipboardIcon, color: 'text-tsushin-warning', iconBg: 'bg-tsushin-warning/10' },
    { key: 'developer', label: 'Developer Tools', Icon: TerminalIcon, color: 'text-purple-400', iconBg: 'bg-purple-400/10' },
    { key: 'tool-apis', label: 'Tool APIs', Icon: WrenchIcon, color: 'text-tsushin-success', iconBg: 'bg-tsushin-success/10' },
    { key: 'mcp-servers', label: 'MCP Servers', Icon: ServerIcon, color: 'text-cyan-400', iconBg: 'bg-cyan-400/10' },
    { key: 'vector-stores', label: 'Vector Stores', Icon: VectorStoreIcon, color: 'text-emerald-400', iconBg: 'bg-emerald-400/10' },
  ]

  return (
    <div className="min-h-screen animate-fade-in">
      {/* Header */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-display font-bold text-white mb-2">Integration Hub</h1>
          <p className="text-tsushin-slate">Connect AI providers, communication channels, productivity apps, and developer tools</p>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 pb-8 space-y-6">
        {/* Alerts */}
        {successMessage && (
          <div className="p-4 bg-tsushin-success/10 border border-tsushin-success/30 rounded-xl text-tsushin-success flex justify-between items-center animate-fade-in-down">
            <span className="flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              {successMessage}
            </span>
            <button onClick={() => setSuccessMessage(null)} className="text-tsushin-success/80 hover:text-tsushin-success transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}
        {error && (
          <div className="p-4 bg-tsushin-vermilion/10 border border-tsushin-vermilion/30 rounded-xl text-tsushin-vermilion flex justify-between items-center animate-fade-in-down">
            <span className="flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              {error}
            </span>
            <button onClick={() => setError(null)} className="text-tsushin-vermilion/80 hover:text-tsushin-vermilion transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Integration Summary */}
        <IntegrationSummary
          providerCount={providerInstances.length}
          whatsappCount={mcpInstances.length}
          telegramCount={telegramInstances.length}
          slackCount={slackIntegrations.length}
          discordCount={discordIntegrations.length}
          webhookCount={webhookIntegrations.length}
          onTabSelect={(tab) => setActiveTab(tab as TabType)}
        />

        {/* Tabs */}
        <div className="glass-card rounded-xl overflow-clip">
          <div className="border-b border-tsushin-border/50 overflow-x-auto">
            <nav className="flex min-w-max">
              {tabs.map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key as TabType)}
                  className={`group relative px-5 py-4 font-medium text-sm transition-all duration-200 flex items-center gap-3 whitespace-nowrap ${activeTab === tab.key
                      ? 'text-white'
                      : 'text-tsushin-slate hover:text-white'
                    }`}
                >
                  <div className={`w-7 h-7 rounded-lg ${tab.iconBg} flex items-center justify-center ${activeTab === tab.key ? tab.color : 'text-tsushin-slate'} group-hover:scale-110 group-hover:${tab.color} transition-all`}>
                    <tab.Icon />
                  </div>
                  <span className="relative z-10">{tab.label}</span>
                  {activeTab === tab.key && (
                    <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-12 h-0.5 rounded-full bg-gradient-to-r from-teal-500 to-cyan-400" />
                  )}
                </button>
              ))}
            </nav>
          </div>

          <div className="p-6">
            {/* ==================== AI PROVIDERS TAB ==================== */}
            {activeTab === 'ai-providers' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">AI Model Providers</h2>
                    <p className="text-sm text-tsushin-slate">Manage provider instances and API keys for AI models</p>
                  </div>
                  <button
                    onClick={() => {
                      setEditingInstance(null)
                      setSelectedVendor('')
                      setInstanceModalOpen(true)
                    }}
                    className="btn-primary"
                  >
                    + New Instance
                  </button>
                </div>

                {/* Provider Instances grouped by vendor */}
                {(() => {
                  const vendorGroups: Record<string, ProviderInstance[]> = {}
                  providerInstances.forEach(inst => {
                    if (!vendorGroups[inst.vendor]) vendorGroups[inst.vendor] = []
                    vendorGroups[inst.vendor].push(inst)
                  })

                  const VENDOR_LABELS: Record<string, string> = {
                    openai: 'OpenAI',
                    anthropic: 'Anthropic',
                    gemini: 'Google Gemini',
                    groq: 'Groq',
                    grok: 'Grok (xAI)',
                    deepseek: 'DeepSeek',
                    openrouter: 'OpenRouter',
                    elevenlabs: 'ElevenLabs',
                    vertex_ai: 'Vertex AI (Google Cloud)',
                    ollama: 'Ollama',
                    custom: 'Custom',
                  }

                  const VENDOR_ICONS: Record<string, React.FC<{ size?: number; className?: string }>> = {
                    openai: OpenAIIcon,
                    anthropic: AnthropicIcon,
                    gemini: GeminiIcon,
                    groq: LightningIcon,
                    grok: GrokIcon,
                    deepseek: BrainIcon,
                    openrouter: GlobeIcon,
                    elevenlabs: MicrophoneIcon,
                    vertex_ai: CloudIcon,
                    ollama: BotIconSvg,
                    custom: BeakerIcon,
                  }

                  const VENDOR_COLORS: Record<string, string> = {
                    openai: 'text-green-400',
                    anthropic: 'text-orange-400',
                    gemini: 'text-blue-400',
                    groq: 'text-yellow-400',
                    grok: 'text-red-400',
                    deepseek: 'text-cyan-400',
                    openrouter: 'text-teal-400',
                    elevenlabs: 'text-pink-400',
                    vertex_ai: 'text-sky-400',
                    ollama: 'text-purple-400',
                    custom: 'text-rose-400',
                  }

                  const healthDotClass = (status: string) => {
                    switch (status) {
                      case 'healthy': return 'bg-tsushin-success animate-pulse'
                      case 'degraded': return 'bg-tsushin-warning'
                      case 'unavailable': return 'bg-tsushin-vermilion'
                      default: return 'bg-tsushin-slate'
                    }
                  }

                  // LLM provider instances grid — excludes:
                  // - 'ollama': has its own dedicated Local Services section above with health monitoring
                  // - 'elevenlabs': TTS-only provider configured via API Keys, not provider instances
                  const allVendors = Array.from(new Set([
                    ...Object.keys(vendorGroups),
                    'openai', 'anthropic', 'gemini', 'groq', 'grok', 'deepseek', 'openrouter', 'vertex_ai',
                  ])).filter(v => v !== 'ollama' && v !== 'elevenlabs').sort()

                  return (
                    <div className="space-y-6">
                      {allVendors.map(vendor => {
                        const instances = vendorGroups[vendor] || []
                        const VendorIcon = VENDOR_ICONS[vendor] || BeakerIcon
                        const vendorColor = VENDOR_COLORS[vendor] || 'text-tsushin-accent'

                        return (
                          <div key={vendor} className="space-y-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2.5">
                                <VendorIcon size={18} className={vendorColor} />
                                <h3 className="text-sm font-semibold text-white">{VENDOR_LABELS[vendor] || vendor}</h3>
                                <span className="text-xs text-tsushin-slate">
                                  {instances.length} instance{instances.length !== 1 ? 's' : ''}
                                </span>
                              </div>
                              <button
                                onClick={() => {
                                  setEditingInstance(null)
                                  setSelectedVendor(vendor)
                                  setInstanceModalOpen(true)
                                }}
                                className="flex items-center gap-1 text-xs text-tsushin-accent hover:text-white transition-colors"
                              >
                                <PlusIconSvg size={14} />
                                Add Instance
                              </button>
                            </div>

                            {instances.length === 0 ? (
                              <div className="border border-dashed border-tsushin-border rounded-xl p-4 text-center">
                                <p className="text-xs text-tsushin-slate">No instances configured</p>
                              </div>
                            ) : (
                              <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                                {instances.map(inst => (
                                  <div key={inst.id} className="card p-4 hover-glow group relative">
                                    <div className="flex items-start justify-between mb-3">
                                      <div className="flex items-center gap-2.5 min-w-0">
                                        <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${healthDotClass(inst.health_status)}`} title={inst.health_status} />
                                        <h4 className="text-sm font-semibold text-white truncate">{inst.instance_name}</h4>
                                        {inst.is_default && (
                                          <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-semibold rounded bg-tsushin-indigo/20 text-tsushin-indigo border border-tsushin-indigo/30">
                                            DEFAULT
                                          </span>
                                        )}
                                      </div>
                                      {/* Three-dot menu */}
                                      <div className="relative">
                                        <button
                                          onClick={(e) => {
                                            e.stopPropagation()
                                            setInstanceMenuOpen(instanceMenuOpen === inst.id ? null : inst.id)
                                          }}
                                          className="p-1 text-tsushin-slate hover:text-white transition-colors rounded"
                                        >
                                          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                                            <circle cx="12" cy="5" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="12" cy="19" r="2" />
                                          </svg>
                                        </button>
                                        {instanceMenuOpen === inst.id && (
                                          <div className="absolute right-0 top-8 z-20 w-44 bg-tsushin-elevated border border-tsushin-border rounded-lg shadow-elevated py-1 animate-fade-in">
                                            <button
                                              onClick={() => {
                                                setInstanceMenuOpen(null)
                                                setEditingInstance(inst)
                                                setInstanceModalOpen(true)
                                              }}
                                              className="w-full text-left px-3 py-2 text-sm text-tsushin-fog hover:text-white hover:bg-white/5 transition-colors"
                                            >
                                              Edit
                                            </button>
                                            <button
                                              onClick={async () => {
                                                setInstanceMenuOpen(null)
                                                try {
                                                  const result = await api.testProviderConnection(inst.id)
                                                  toast.success(result.success
                                                    ? `Connected (${result.latency_ms}ms)`
                                                    : `Failed: ${result.message}`
                                                  )
                                                  fetchProviderInstances()
                                                } catch (err: any) {
                                                  toast.error(err.message || 'Test failed')
                                                }
                                              }}
                                              className="w-full text-left px-3 py-2 text-sm text-tsushin-fog hover:text-white hover:bg-white/5 transition-colors"
                                            >
                                              Test Connection
                                            </button>
                                            <button
                                              onClick={async () => {
                                                setInstanceMenuOpen(null)
                                                try {
                                                  const models = await api.discoverProviderModels(inst.id)
                                                  toast.success(`Discovered ${models.length} model${models.length !== 1 ? 's' : ''}`)
                                                  fetchProviderInstances()
                                                } catch (err: any) {
                                                  toast.error(err.message || 'Discovery failed')
                                                }
                                              }}
                                              className="w-full text-left px-3 py-2 text-sm text-tsushin-fog hover:text-white hover:bg-white/5 transition-colors"
                                            >
                                              Discover Models
                                            </button>
                                            {!inst.is_default && (
                                              <button
                                                onClick={async () => {
                                                  setInstanceMenuOpen(null)
                                                  try {
                                                    await api.updateProviderInstance(inst.id, { is_default: true })
                                                    toast.success(`${inst.instance_name} set as default`)
                                                    fetchProviderInstances()
                                                  } catch (err: any) {
                                                    toast.error(err.message || 'Failed to set default')
                                                  }
                                                }}
                                                className="w-full text-left px-3 py-2 text-sm text-tsushin-fog hover:text-white hover:bg-white/5 transition-colors"
                                              >
                                                Set as Default
                                              </button>
                                            )}
                                            <div className="border-t border-tsushin-border my-1" />
                                            <button
                                              onClick={async () => {
                                                setInstanceMenuOpen(null)
                                                if (!confirm(`Delete instance "${inst.instance_name}"?`)) return
                                                try {
                                                  await api.deleteProviderInstance(inst.id)
                                                  toast.success(`Deleted ${inst.instance_name}`)
                                                  fetchProviderInstances()
                                                } catch (err: any) {
                                                  toast.error(err.message || 'Failed to delete')
                                                }
                                              }}
                                              className="w-full text-left px-3 py-2 text-sm text-tsushin-vermilion hover:bg-tsushin-vermilion/10 transition-colors"
                                            >
                                              Delete
                                            </button>
                                          </div>
                                        )}
                                      </div>
                                    </div>

                                    <div className="space-y-1.5 text-xs">
                                      <p className="text-tsushin-slate">
                                        {inst.base_url
                                          ? <span className="font-mono text-tsushin-accent truncate block">{inst.base_url}</span>
                                          : <span className="text-tsushin-slate italic">Default URL</span>
                                        }
                                      </p>
                                      {inst.api_key_configured && (
                                        <p className="text-tsushin-slate">
                                          Key: <span className="font-mono text-tsushin-fog">{inst.api_key_preview}</span>
                                        </p>
                                      )}
                                      <p className="text-tsushin-slate">
                                        {inst.available_models.length > 0
                                          ? `${inst.available_models.length} model${inst.available_models.length !== 1 ? 's' : ''}`
                                          : 'No models configured'
                                        }
                                      </p>
                                      {inst.health_status_reason && inst.health_status !== 'healthy' && (
                                        <p className="text-tsushin-vermilion text-[11px] truncate" title={inst.health_status_reason}>
                                          {inst.health_status_reason}
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )
                })()}

                {/* Local Services Section */}
                <div className="pt-2">
                  <h3 className="text-sm font-semibold text-tsushin-fog mb-3">Local Services</h3>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {/* Ollama Card (Enhanced - Local LLM) */}
                    <div className="card p-5 hover-glow group">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                            <BotIconSvg size={20} className="text-purple-400" />
                          </div>
                          <h3 className="font-semibold text-white">Ollama (Local)</h3>
                        </div>
                        <div className="flex items-center gap-3">
                          {/* Status indicator */}
                          <div className="flex items-center gap-1.5">
                            <div className={`w-2 h-2 rounded-full ${ollamaHealth?.available ? 'bg-tsushin-success animate-pulse' : 'bg-tsushin-slate'}`} />
                            <span className="text-[11px] text-tsushin-slate">{ollamaHealth?.available ? 'Healthy' : 'Offline'}</span>
                          </div>
                          {/* Enable/Disable Toggle */}
                          {canEditSettings && (
                            <ToggleSwitch
                              checked={ollamaEnabled}
                              onChange={() => handleOllamaToggle()}
                              disabled={ollamaToggleLoading}
                              title={ollamaEnabled ? 'Disable Ollama' : 'Enable Ollama'}
                              activeColor="bg-tsushin-success"
                            />
                          )}
                        </div>
                      </div>
                      <p className="text-xs text-tsushin-slate mb-3">Run LLMs locally - no API key needed</p>
                      <div className="text-sm text-tsushin-slate space-y-2">
                        {ollamaHealth?.available ? (
                          <>
                            <p className="text-xs">{ollamaHealth.models_count || 0} models available</p>
                            {/* Inline URL editor */}
                            {ollamaUrlEditing ? (
                              <div className="flex items-center gap-1.5">
                                <input
                                  type="text"
                                  value={ollamaUrlValue}
                                  onChange={(e) => setOllamaUrlValue(e.target.value)}
                                  className="bg-tsushin-ink border border-white/10 rounded-lg px-3 py-1.5 text-white text-sm font-mono flex-1 min-w-0"
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') handleOllamaUrlSave()
                                    if (e.key === 'Escape') setOllamaUrlEditing(false)
                                  }}
                                />
                                <button
                                  onClick={handleOllamaUrlSave}
                                  disabled={ollamaUrlSaving}
                                  className="bg-tsushin-success/20 text-tsushin-success hover:bg-tsushin-success/30 rounded-lg px-2.5 py-1.5 text-xs shrink-0"
                                >
                                  {ollamaUrlSaving ? '...' : 'Save'}
                                </button>
                                <button
                                  onClick={() => setOllamaUrlEditing(false)}
                                  className="text-tsushin-slate hover:text-white px-1.5 py-1.5 text-xs shrink-0"
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <p
                                className="text-xs font-mono text-tsushin-accent cursor-pointer hover:text-white transition-colors"
                                onClick={() => canEditSettings && setOllamaUrlEditing(true)}
                                title={canEditSettings ? 'Click to edit URL' : ''}
                              >
                                {ollamaHealth.base_url}
                                {canEditSettings && (
                                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="inline ml-1.5 opacity-50">
                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                                    <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                                  </svg>
                                )}
                              </p>
                            )}
                            {ollamaHealth.models?.slice(0, 3).map((m, i) => (
                              <p key={i} className="text-xs text-tsushin-muted">- {m.name}</p>
                            ))}
                            {(ollamaHealth.models_count || 0) > 3 && (
                              <p className="text-xs text-tsushin-slate">... and {(ollamaHealth.models_count || 0) - 3} more</p>
                            )}
                          </>
                        ) : (
                          <>
                            <p className="text-xs text-tsushin-vermilion">{ollamaHealth?.error || 'Not running'}</p>
                            <p className="text-xs">Start with: <code className="bg-tsushin-deep px-1.5 py-0.5 rounded font-mono text-tsushin-accent">ollama serve</code></p>
                          </>
                        )}
                        {/* BUG-331: Docker networking guidance — always visible */}
                        <div className="mt-3 p-2.5 bg-tsushin-deep/60 border border-white/10 rounded-lg space-y-1.5">
                          <p className="text-xs font-medium text-tsushin-accent">Docker Networking Note</p>
                          <p className="text-xs text-tsushin-slate">
                            Tsushin runs inside Docker. Use <code className="bg-tsushin-ink px-1 rounded font-mono text-tsushin-accent">http://172.18.0.1:11434</code> instead of <code className="bg-tsushin-ink px-1 rounded font-mono">localhost</code> so the backend container can reach Ollama on the host.
                          </p>
                          <p className="text-xs text-tsushin-slate">
                            Also ensure Ollama listens on all interfaces — add to its systemd override:
                          </p>
                          <code className="block text-xs bg-tsushin-ink px-2 py-1.5 rounded font-mono text-tsushin-success whitespace-nowrap overflow-x-auto">
                            Environment=&quot;OLLAMA_HOST=0.0.0.0:11434&quot;
                          </code>
                        </div>
                        {/* Test result display */}
                        {ollamaTestResult && (
                          <p className={`text-xs ${ollamaTestResult.success ? 'text-tsushin-success' : 'text-tsushin-vermilion'}`}>
                            {ollamaTestResult.success ? 'Connection successful' : ollamaTestResult.message}
                          </p>
                        )}
                      </div>
                      {/* Action buttons */}
                      <div className="flex gap-2 mt-4">
                        <button
                          onClick={handleOllamaTest}
                          disabled={ollamaTestLoading}
                          className="flex-1 bg-tsushin-success/20 text-tsushin-success hover:bg-tsushin-success/30 rounded-lg px-3 py-1.5 text-sm transition-colors disabled:opacity-50"
                        >
                          {ollamaTestLoading ? 'Testing...' : 'Test Connection'}
                        </button>
                        <button
                          onClick={async () => {
                            await fetchOllamaHealth()
                            const ollamaInst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
                            if (ollamaInst) {
                              try {
                                const models = await api.discoverProviderModels(ollamaInst.id)
                                toast.success(`Discovered ${models.length} model${models.length !== 1 ? 's' : ''}`)
                                await fetchProviderInstances()
                              } catch { /* ignore */ }
                            }
                          }}
                          className="flex-1 btn-secondary py-1.5 text-sm"
                        >
                          Refresh Models
                        </button>
                      </div>
                      {/* Manage instance link */}
                      {canEditSettings && (() => {
                        const ollamaInst = providerInstances.find(i => i.vendor === 'ollama')
                        return ollamaInst ? (
                          <button
                            onClick={() => { setEditingInstance(ollamaInst); setInstanceModalOpen(true) }}
                            className="w-full mt-2 text-xs text-tsushin-slate hover:text-white transition-colors text-center py-1"
                          >
                            Manage Instance
                          </button>
                        ) : null
                      })()}
                    </div>

                    {/* Kokoro TTS Card (Enhanced - Container Management) */}
                    <div className="card p-5 hover-glow group border-green-700/30">
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-green-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                            <MicrophoneIcon size={20} className="text-green-400" />
                          </div>
                          <h3 className="font-semibold text-white">Kokoro TTS (Free)</h3>
                        </div>
                        <div className="flex items-center gap-3">
                          {/* Status indicator with color-coded dot */}
                          <div className="flex items-center gap-1.5">
                            <div className={`w-2 h-2 rounded-full ${
                              kokoroContainerStatus?.status === 'running' && kokoroHealth?.available
                                ? 'bg-tsushin-success animate-pulse'
                                : kokoroContainerStatus?.status === 'running' && !kokoroHealth?.available
                                  ? 'bg-yellow-400 animate-pulse'
                                  : kokoroContainerStatus?.status === 'not_installed' || kokoroContainerStatus?.status === 'error'
                                    ? 'bg-tsushin-vermilion'
                                    : 'bg-tsushin-slate'
                            }`} />
                            <span className="text-[11px] text-tsushin-slate capitalize">
                              {kokoroContainerStatus?.status === 'running' && kokoroHealth?.available
                                ? 'Running'
                                : kokoroContainerStatus?.status === 'running' && !kokoroHealth?.available
                                  ? 'Initializing...'
                                  : kokoroContainerStatus?.status === 'exited'
                                    ? 'Stopped'
                                    : kokoroContainerStatus?.status === 'not_installed'
                                      ? 'Not Installed'
                                      : kokoroContainerStatus?.status === 'error'
                                        ? 'Error'
                                        : kokoroHealth?.available ? 'Online' : 'Offline'}
                            </span>
                          </div>
                          {/* Enable/Disable Toggle */}
                          {canEditSettings && kokoroContainerStatus?.status !== 'not_installed' && (
                            <ToggleSwitch
                              checked={kokoroContainerStatus?.status === 'running'}
                              onChange={async (checked) => {
                                if (checked) {
                                  await handleStartKokoro()
                                } else {
                                  await handleStopKokoro()
                                }
                              }}
                              disabled={kokoroActionLoading}
                              title={kokoroContainerStatus?.status === 'running' ? 'Stop Kokoro' : 'Start Kokoro'}
                            />
                          )}
                        </div>
                      </div>
                      <p className="text-xs text-tsushin-slate mb-3">Free text-to-speech with PTBR support</p>
                      <div className="text-sm text-tsushin-slate space-y-2">
                        {kokoroHealth?.available ? (
                          <>
                            <p className="text-xs">{kokoroHealth.details?.voices || 15} voices available</p>
                            <p className="text-xs font-mono text-tsushin-accent">{kokoroHealth.details?.service_url || 'http://localhost:8880'}</p>
                            {kokoroHealth.latency_ms && (
                              <p className="text-xs text-green-400">Latency: {kokoroHealth.latency_ms}ms</p>
                            )}
                            <p className="text-xs text-green-400 flex items-center gap-1"><CreditCardIcon size={12} className="text-green-400" /> 100% FREE - No API costs!</p>
                          </>
                        ) : kokoroContainerStatus?.status === 'running' ? (
                          <>
                            <p className="text-xs text-yellow-400">Container is running — loading TTS models, please wait...</p>
                            {kokoroContainerStatus?.name && (
                              <p className="text-xs font-mono text-tsushin-slate">Container: {kokoroContainerStatus.name}</p>
                            )}
                          </>
                        ) : (
                          <>
                            <p className="text-xs text-tsushin-vermilion">{kokoroHealth?.message || kokoroContainerStatus?.message || 'Service not running'}</p>
                            {kokoroContainerStatus?.status === 'not_installed' && (
                              <p className="text-xs">Install with: <code className="bg-tsushin-deep px-1.5 py-0.5 rounded font-mono text-tsushin-accent">docker compose --profile tts up -d</code></p>
                            )}
                            {kokoroContainerStatus?.name && (
                              <p className="text-xs font-mono text-tsushin-slate">Container: {kokoroContainerStatus.name}</p>
                            )}
                          </>
                        )}
                      </div>
                      {/* Container management */}
                      <div className="flex gap-2 mt-4">
                        <button
                          onClick={async () => {
                            await Promise.all([fetchKokoroContainerStatus(), fetchKokoroHealth()])
                          }}
                          className="flex-1 btn-secondary py-1.5 text-sm"
                        >
                          Refresh Status
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Service API Keys Section */}
                <div className="pt-2">
                  <h3 className="text-sm font-semibold text-tsushin-fog mb-1">Service API Keys</h3>
                  <p className="text-xs text-tsushin-slate mb-3">API keys for non-LLM integrations (e.g. ElevenLabs TTS) and LLM provider fallbacks</p>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {AI_PROVIDERS.map(provider => renderIntegrationCard(provider, 'ai'))}
                  </div>
                </div>

                {/* Info Box */}
                <div className="bg-purple-500/5 border border-purple-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-purple-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-purple-300" /> AI Providers
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    Provider instances let you configure multiple endpoints for the same vendor (e.g., different OpenAI-compatible servers).
                    Service API Keys below are used as fallbacks when instances don't have their own key configured.
                  </p>
                </div>
              </div>
            )}

            {/* ==================== COMMUNICATION TAB ==================== */}
            {activeTab === 'communication' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">Communication Channels</h2>
                    <p className="text-sm text-tsushin-slate">Connect messaging platforms for agent interactions</p>
                  </div>
                  <button
                    onClick={() => setShowCreateModeSelector(true)}
                    className="btn-primary"
                  >
                    + Create WhatsApp Instance
                  </button>
                </div>

                {/* v0.6.0 V060-CHN-002: Public Base URL setting (used by Slack HTTP + Discord) */}
                <PublicBaseUrlCard canEdit={canEditSettings} />

                {/* WhatsApp Instances */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <MessageIconSvg size={18} /> WhatsApp Instances
                    </h3>
                  </div>

                  {agentMcpInstances.length === 0 && testerMcpInstances.length > 0 && (
                    <div className="card p-4 border border-orange-500/20 bg-orange-500/5">
                      <p className="text-xs text-orange-200">
                        Tester instances are visible for QA workflows. Create an agent instance when you want live WhatsApp traffic routed to an AI agent.
                      </p>
                    </div>
                  )}

                  {canReadSettings && (
                    <div className="card p-4 border border-tsushin-border/60">
                      <div className="flex flex-col gap-3">
                        <div>
                          <h4 className="text-sm font-semibold text-white">Conversation Response Delay</h4>
                          <p className="text-xs text-tsushin-slate">
                            Buffers WhatsApp conversation messages for a short window so bursts are handled together.
                          </p>
                        </div>
                        <div className="flex flex-col gap-2">
                          <div className="flex flex-wrap items-center gap-3">
                            <input
                              type="number"
                              min="0"
                              step="0.5"
                              value={whatsappDelaySeconds}
                              onChange={(event) => setWhatsappDelaySeconds(event.target.value)}
                              className="input w-32 text-sm"
                              disabled={!canEditSettings || savingWhatsappDelay}
                            />
                            <span className="text-xs text-tsushin-slate">seconds</span>
                            <button
                              onClick={handleSaveWhatsappDelay}
                              className="px-4 py-2 bg-teal-600/20 text-teal-300 border border-teal-600/50 rounded text-xs"
                              disabled={!canEditSettings || savingWhatsappDelay}
                            >
                              {savingWhatsappDelay ? 'Saving...' : 'Save Delay'}
                            </button>
                          </div>
                          {whatsappDelayError && (
                            <p className="text-xs text-red-400">{whatsappDelayError}</p>
                          )}
                          {!canEditSettings && (
                            <p className="text-xs text-amber-300">
                              You need org.settings.write permission to edit this value.
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {communicationMcpInstances.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <SmartphoneIcon size={36} className="text-gray-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No WhatsApp Instances</h3>
                      <p className="text-tsushin-slate mb-4">Connect your WhatsApp number to start messaging with AI agents</p>
                      <button
                        onClick={() => setShowCreateModeSelector(true)}
                        className="btn-primary flex items-center gap-2"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                        </svg>
                        Create WhatsApp Instance
                      </button>
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {communicationMcpInstances.map(instance => {
                        const health = healthStatuses[instance.id]
                        const authBadge = getAuthBadge(health)
                        return (
                          <div key={instance.id} className="card p-4 hover-glow">
                            <div className="flex items-start justify-between mb-3">
                              <div>
                                <h3 className="font-semibold text-white">{instance.display_name || instance.phone_number}</h3>
                                {instance.display_name && <p className="text-xs text-tsushin-slate">{instance.phone_number}</p>}
                                <p className="text-xs text-tsushin-slate/60">Port: {instance.mcp_port}</p>
                              </div>
                              <div className="flex flex-col gap-1 items-end">
                                <span className={getStatusBadge(instance.status)}>{instance.status}</span>
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${instance.instance_type === 'agent'
                                    ? 'bg-green-600/20 text-green-400 border border-green-600/50'
                                    : 'bg-orange-600/20 text-orange-400 border border-orange-600/50'
                                  }`}>
                                  {instance.instance_type === 'agent' ? <span className="flex items-center gap-1"><BotIconSvg size={12} /> Agent</span> : <span className="flex items-center gap-1"><BeakerIcon size={12} /> Tester</span>}
                                </span>
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${authBadge.className}`}>
                                  {authBadge.label}
                                </span>
                              </div>
                            </div>

                            <div className="grid grid-cols-2 gap-2 mb-2">
                              {instance.status === 'running' ? (
                                <>
                                  <button
                                    onClick={() => handleMcpAction('stop', instance.id)}
                                    className="px-3 py-1.5 bg-yellow-600/20 text-yellow-400 border border-yellow-600/50 rounded text-xs"
                                  >
                                    Stop
                                  </button>
                                  <button
                                    onClick={() => handleMcpAction('restart', instance.id)}
                                    className="px-3 py-1.5 bg-blue-600/20 text-blue-400 border border-blue-600/50 rounded text-xs"
                                  >
                                    Restart
                                  </button>
                                </>
                              ) : (
                                <button
                                  onClick={() => handleMcpAction('start', instance.id)}
                                  className="col-span-2 px-3 py-1.5 bg-green-600/20 text-green-400 border border-green-600/50 rounded text-xs"
                                >
                                  Start
                                </button>
                              )}
                            </div>
                            <div className="grid grid-cols-4 gap-2">
                              <button
                                onClick={() => handleShowQR(instance)}
                                className="px-3 py-1.5 bg-purple-600/20 text-purple-400 border border-purple-600/50 rounded text-xs"
                              >
                                QR Code
                              </button>
                              <button
                                onClick={() => handleResetAuth(instance)}
                                className="px-3 py-1.5 bg-orange-600/20 text-orange-400 border border-orange-600/50 rounded text-xs"
                                title="Reset authentication and generate new QR code"
                              >
                                Reset Auth
                              </button>
                              <button
                                onClick={() => handleConfigureFilters(instance)}
                                className="px-3 py-1.5 bg-teal-600/20 text-teal-400 border border-teal-600/50 rounded text-xs"
                              >
                                Filters
                              </button>
                              <button
                                onClick={() => handleMcpAction('delete', instance.id)}
                                className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-600/50 rounded text-xs"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {showDedicatedTesterCard && (
                    <div className="card p-4 border border-tsushin-border/60">
                      <div className="flex items-start justify-between mb-3 gap-4">
                        <div>
                          <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                            <BeakerIcon size={16} className="text-orange-400" /> QA Tester
                          </h3>
                          <p className="text-xs text-tsushin-slate mt-1">
                            {testerSourceLabel} shortcuts for WhatsApp QA, QR validation, and watcher diagnostics.
                          </p>
                          <p className="text-xs text-tsushin-slate/70 mt-2">
                            Container: {testerContainerLabel}
                          </p>
                          {testerControlSource === 'compose' && runtimeTesterInstances.length > 0 && (
                            <p className="text-xs text-amber-300/90 mt-2">
                              Compose tester controls remain active. Runtime tester rows are still listed below for cleanup and visibility.
                            </p>
                          )}
                          {testerControlSource === 'runtime' && (
                            <p className="text-xs text-emerald-300/90 mt-2">
                              Tester shortcut endpoints are currently resolved to the runtime tester, so QR, health, and reset actions stay aligned with the active container.
                            </p>
                          )}
                        </div>
                        <div className="flex flex-col items-end gap-1">
                          <span className={`px-2 py-1 text-[11px] font-medium rounded-full border ${
                            testerControlSource === 'runtime'
                              ? 'bg-emerald-600/20 text-emerald-300 border-emerald-600/40'
                              : 'bg-sky-600/20 text-sky-300 border-sky-600/40'
                          }`}>
                            Source: {testerControlSource}
                          </span>
                          <span className={getStatusBadge(testerStatus?.container_state || 'stopped')}>
                            {testerStatus?.container_state || 'unknown'}
                          </span>
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            testerStatus?.authenticated && testerStatus?.connected && !testerStatus?.needs_reauth
                              ? 'bg-green-600/20 text-green-400 border border-green-600/50'
                              : testerStatus?.needs_reauth
                                ? 'bg-orange-600/20 text-orange-300 border border-orange-600/50'
                                : 'bg-yellow-600/20 text-yellow-400 border border-yellow-600/50'
                          }`}>
                            {testerStatus?.authenticated && testerStatus?.connected && !testerStatus?.needs_reauth
                              ? 'Authenticated'
                              : testerStatus?.needs_reauth
                                ? 'Needs Reauth'
                                : 'Not Auth'}
                          </span>
                        </div>
                      </div>

                      <div className="grid gap-2 md:grid-cols-2 mb-3 text-xs text-tsushin-slate">
                        <div>API: {testerStatus?.api_reachable ? 'reachable' : 'unreachable'}</div>
                        <div>QR: {testerStatus?.qr_available ? 'available' : testerStatus?.qr_message || 'not ready'}</div>
                        {testerStatus?.error && (
                          <div className="md:col-span-2 text-amber-300">{testerStatus.error}</div>
                        )}
                      </div>

                      <div className="grid grid-cols-4 gap-2">
                        <button
                          onClick={handleShowTesterQR}
                          className="px-3 py-1.5 bg-purple-600/20 text-purple-400 border border-purple-600/50 rounded text-xs"
                        >
                          Tester QR
                        </button>
                        <button
                          onClick={handleRestartTester}
                          className="px-3 py-1.5 bg-blue-600/20 text-blue-400 border border-blue-600/50 rounded text-xs"
                        >
                          Restart
                        </button>
                        <button
                          onClick={handleResetTesterAuth}
                          className="px-3 py-1.5 bg-orange-600/20 text-orange-400 border border-orange-600/50 rounded text-xs"
                        >
                          Reset Auth
                        </button>
                        <button
                          onClick={async () => {
                            const testerInstance = runtimeTesterInstances[0]
                            if (testerInstance) {
                              if (!confirm(`Delete tester instance "${testerInstance.instance_name}"? You can recreate it later.`)) return
                              try {
                                await api.deleteMCPInstance(testerInstance.id, true)
                                toast.success('Tester instance deleted')
                                loadMcpInstances()
                                loadTesterStatus()
                              } catch (err: any) {
                                toast.error(err.message || 'Failed to delete tester instance')
                              }
                            } else {
                              if (!confirm('Dismiss orphan tester card? The container is already gone.')) return
                              setTesterStatus(null)
                              toast.success('Tester card dismissed. Create a new tester instance when ready.')
                            }
                          }}
                          className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-600/50 rounded text-xs"
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {/* Phase 10.1.1: Telegram Bot Instances */}
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <PlaneIcon size={18} /> Telegram Bots
                    </h3>
                    <button
                      onClick={() => setShowTelegramModal(true)}
                      className="px-4 py-2 bg-blue-600/20 text-blue-400 border border-blue-600/50 rounded hover:bg-blue-600/30 text-sm"
                    >
                      + Create Bot
                    </button>
                  </div>

                  {telegramInstances.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <PlaneIcon size={36} className="text-blue-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Telegram Bots</h3>
                      <p className="text-tsushin-slate mb-4">Create a bot to connect Telegram</p>
                      <button
                        onClick={() => setShowTelegramModal(true)}
                        className="btn-primary"
                      >
                        Create Bot
                      </button>
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {telegramInstances.map(instance => {
                        const health = telegramHealthStatuses[instance.id]
                        return (
                          <div key={instance.id} className="card p-4 hover-glow">
                            <div className="flex items-start justify-between mb-3">
                              <div>
                                <h3 className="font-semibold text-white">@{instance.bot_username}</h3>
                                <p className="text-xs text-tsushin-slate">{instance.bot_name || 'Telegram Bot'}</p>
                              </div>
                              <div className="flex flex-col gap-1 items-end">
                                <span className={getStatusBadge(instance.status)}>{instance.status}</span>
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${health?.api_reachable
                                    ? 'bg-green-600/20 text-green-400 border border-green-600/50'
                                    : 'bg-yellow-600/20 text-yellow-400 border border-yellow-600/50'
                                  }`}>
                                  {health?.api_reachable ? 'Connected' : 'Disconnected'}
                                </span>
                              </div>
                            </div>

                            <div className="grid grid-cols-2 gap-2">
                              {instance.status === 'active' ? (
                                <button
                                  onClick={() => handleTelegramAction('stop', instance.id)}
                                  className="px-3 py-1.5 bg-yellow-600/20 text-yellow-400 border border-yellow-600/50 rounded text-xs"
                                >
                                  Stop
                                </button>
                              ) : (
                                <button
                                  onClick={() => handleTelegramAction('start', instance.id)}
                                  className="px-3 py-1.5 bg-green-600/20 text-green-400 border border-green-600/50 rounded text-xs"
                                >
                                  Start
                                </button>
                              )}
                              <button
                                onClick={() => handleTelegramAction('delete', instance.id)}
                                className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-600/50 rounded text-xs"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* v0.6.0: Slack Integration */}
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <SlackIcon size={18} className="text-purple-400" /> Slack
                    </h3>
                    <button
                      onClick={() => setShowSlackSetupModal(true)}
                      className="px-4 py-2 bg-purple-600/20 text-purple-400 border border-purple-600/50 rounded hover:bg-purple-600/30 text-sm"
                    >
                      + Connect Workspace
                    </button>
                  </div>

                  {slackIntegrations.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <SlackIcon size={36} className="text-purple-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Slack Workspaces</h3>
                      <p className="text-tsushin-slate mb-4">Connect a Slack workspace to enable bot messaging</p>
                      <button
                        onClick={() => setShowSlackSetupModal(true)}
                        className="btn-primary"
                      >
                        Connect Workspace
                      </button>
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {slackIntegrations.map(integration => (
                        <div key={integration.id} className="card p-5 hover-glow">
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center">
                                <SlackIcon size={20} className="text-purple-400" />
                              </div>
                              <div>
                                <h3 className="font-semibold text-white">{integration.workspace_name || 'Slack Workspace'}</h3>
                                <p className="text-xs text-tsushin-slate">{integration.mode === 'socket' ? 'Socket Mode' : 'HTTP Events'}</p>
                              </div>
                            </div>
                            <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                              integration.status === 'connected'
                                ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                                : integration.status === 'error'
                                ? 'bg-red-500/20 text-red-400 border border-red-500/50'
                                : 'bg-gray-500/20 text-gray-400 border border-gray-500/50'
                            }`}>
                              {integration.status === 'connected' ? 'Connected' : integration.status === 'error' ? 'Error' : 'Not configured'}
                            </span>
                          </div>

                          <div className="text-xs text-tsushin-slate mb-3 space-y-1">
                            <p>DM Policy: <span className="text-white capitalize">{integration.dm_policy ?? 'allowlist'}</span></p>
                            {(integration.allowed_channels?.length ?? 0) > 0 && (
                              <p>Channels: <span className="text-white">{integration.allowed_channels!.length} allowed</span></p>
                            )}
                          </div>

                          <div className="grid grid-cols-2 gap-2">
                            <button
                              onClick={() => handleTestSlackConnection(integration.id)}
                              disabled={slackTestLoading === integration.id}
                              className="px-3 py-1.5 bg-purple-600/20 text-purple-400 border border-purple-600/50 rounded text-xs hover:bg-purple-600/30 disabled:opacity-50"
                            >
                              {slackTestLoading === integration.id ? 'Testing...' : 'Test Connection'}
                            </button>
                            <button
                              onClick={() => handleDeleteSlackIntegration(integration.id)}
                              className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-600/50 rounded text-xs hover:bg-red-600/30"
                            >
                              Disconnect
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* v0.6.0: Discord Integration */}
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <DiscordIcon size={18} className="text-indigo-400" /> Discord
                    </h3>
                    <button
                      onClick={() => setShowDiscordSetupModal(true)}
                      className="px-4 py-2 bg-indigo-600/20 text-indigo-400 border border-indigo-600/50 rounded hover:bg-indigo-600/30 text-sm"
                    >
                      + Connect Bot
                    </button>
                  </div>

                  {discordIntegrations.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <DiscordIcon size={36} className="text-indigo-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Discord Bots</h3>
                      <p className="text-tsushin-slate mb-4">Connect a Discord bot to enable messaging in your servers</p>
                      <button
                        onClick={() => setShowDiscordSetupModal(true)}
                        className="btn-primary"
                      >
                        Connect Bot
                      </button>
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {discordIntegrations.map(integration => (
                        <div key={integration.id} className="card p-5 hover-glow">
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center">
                                <DiscordIcon size={20} className="text-indigo-400" />
                              </div>
                              <div>
                                <h3 className="font-semibold text-white">Discord Bot</h3>
                                <p className="text-xs text-tsushin-slate">App ID: {integration.application_id}</p>
                              </div>
                            </div>
                            <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                              integration.status === 'connected'
                                ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                                : integration.status === 'error'
                                ? 'bg-red-500/20 text-red-400 border border-red-500/50'
                                : 'bg-gray-500/20 text-gray-400 border border-gray-500/50'
                            }`}>
                              {integration.status === 'connected' ? 'Connected' : integration.status === 'error' ? 'Error' : 'Not configured'}
                            </span>
                          </div>

                          <div className="text-xs text-tsushin-slate mb-3 space-y-1">
                            <p>DM Policy: <span className="text-white capitalize">{integration.dm_policy ?? 'allowlist'}</span></p>
                            {(integration.allowed_guilds?.length ?? 0) > 0 && (
                              <p>Servers: <span className="text-white">{integration.allowed_guilds!.length} allowed</span></p>
                            )}
                          </div>

                          <div className="grid grid-cols-2 gap-2">
                            <button
                              onClick={() => handleTestDiscordConnection(integration.id)}
                              disabled={discordTestLoading === integration.id}
                              className="px-3 py-1.5 bg-indigo-600/20 text-indigo-400 border border-indigo-600/50 rounded text-xs hover:bg-indigo-600/30 disabled:opacity-50"
                            >
                              {discordTestLoading === integration.id ? 'Testing...' : 'Test Connection'}
                            </button>
                            <button
                              onClick={() => handleDeleteDiscordIntegration(integration.id)}
                              className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-600/50 rounded text-xs hover:bg-red-600/30"
                            >
                              Disconnect
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* v0.6.0: Webhook-as-a-Channel Integrations */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <WebhookIcon size={18} className="text-cyan-400" /> Webhook Integrations
                    </h3>
                    <button
                      onClick={() => setShowWebhookSetupModal(true)}
                      className="px-4 py-2 bg-cyan-600/20 text-cyan-400 border border-cyan-600/50 rounded hover:bg-cyan-600/30 text-sm"
                    >
                      + New Webhook
                    </button>
                  </div>

                  {webhookIntegrations.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <WebhookIcon size={36} className="text-cyan-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Webhook Integrations</h3>
                      <p className="text-tsushin-slate mb-4">
                        Connect external HTTP systems (CRMs, Zapier, custom apps) via HMAC-signed webhooks
                      </p>
                      <button
                        onClick={() => setShowWebhookSetupModal(true)}
                        className="btn-primary"
                      >
                        Create Webhook
                      </button>
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {webhookIntegrations.map(integration => (
                        <div key={integration.id} className="card p-5 hover-glow">
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-3 min-w-0">
                              <div className="w-10 h-10 rounded-xl bg-cyan-500/10 flex items-center justify-center shrink-0">
                                <WebhookIcon size={20} className="text-cyan-400" />
                              </div>
                              <div className="min-w-0">
                                <h3 className="font-semibold text-white truncate">{integration.integration_name}</h3>
                                <p className="text-xs text-tsushin-slate font-mono truncate">{integration.api_secret_preview}</p>
                              </div>
                            </div>
                            <span className={`px-2 py-1 text-xs font-medium rounded-full shrink-0 ${
                              !integration.is_active || integration.status === 'paused'
                                ? 'bg-gray-500/20 text-gray-400 border border-gray-500/50'
                                : integration.circuit_breaker_state === 'open'
                                ? 'bg-red-500/20 text-red-400 border border-red-500/50'
                                : integration.health_status === 'healthy'
                                ? 'bg-green-500/20 text-green-400 border border-green-500/50'
                                : 'bg-gray-500/20 text-gray-400 border border-gray-500/50'
                            }`}>
                              {!integration.is_active || integration.status === 'paused'
                                ? 'Paused'
                                : integration.circuit_breaker_state === 'open'
                                ? 'Circuit Open'
                                : integration.health_status === 'healthy'
                                ? 'Active'
                                : 'Unknown'}
                            </span>
                          </div>

                          <div className="text-xs text-tsushin-slate mb-3 space-y-1">
                            <div className="flex items-center gap-1">
                              <span>Inbound:</span>
                              <code className="text-cyan-300 text-xs bg-gray-900 px-1 rounded truncate">{integration.inbound_url}</code>
                              <button
                                type="button"
                                onClick={() => navigator.clipboard.writeText(window.location.origin + integration.inbound_url)}
                                title="Copy URL"
                                className="text-gray-500 hover:text-cyan-400 ml-auto shrink-0"
                              >
                                <CopyIcon size={12} />
                              </button>
                            </div>
                            <p>Callback: <span className="text-white">{integration.callback_enabled ? 'Enabled' : 'Disabled'}</span></p>
                            <p>Rate limit: <span className="text-white">{integration.rate_limit_rpm} req/min</span></p>
                          </div>

                          <div className="grid grid-cols-2 gap-2">
                            <button
                              onClick={() => handleRotateWebhookSecret(integration.id)}
                              className="px-3 py-1.5 bg-cyan-600/20 text-cyan-400 border border-cyan-600/50 rounded text-xs hover:bg-cyan-600/30"
                              title="Rotate HMAC secret"
                            >
                              Rotate Secret
                            </button>
                            <button
                              onClick={() => handleDeleteWebhookIntegration(integration.id)}
                              className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-600/50 rounded text-xs hover:bg-red-600/30"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Gmail Integration */}
                <div className="space-y-4">
                  <h3 className="text-md font-semibold text-white flex items-center gap-2">
                    <EnvelopeIcon size={18} /> Email Integration
                  </h3>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {/* Existing Gmail Integrations */}
                    {hubIntegrations.filter(i => i.type === 'gmail').map(integration => (
                      <div key={integration.id} className={`card p-5 hover-glow ${integration.health_status === 'unavailable' ? 'border-red-500/50' : 'border-red-700/30'}`}>
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center">
                              <EnvelopeIcon size={20} className="text-red-400" />
                            </div>
                            <h3 className="font-semibold text-white">Gmail</h3>
                          </div>
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                            integration.health_status === 'healthy'
                              ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                              : integration.health_status === 'unavailable'
                              ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                              : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                            }`}>
                            {integration.health_status === 'healthy' ? 'Connected' : integration.health_status === 'unavailable' ? 'Expired' : integration.health_status}
                          </span>
                        </div>
                        <p className="text-xs text-tsushin-slate mb-3">Email actions & reading</p>
                        <div className="text-sm text-tsushin-slate mb-3">
                          <p className="text-xs">Account: {integration.name?.replace('Gmail - ', '') || 'Unknown'}</p>
                        </div>
                        {integration.health_status === 'unavailable' && (
                          <div className="mb-3 p-2 bg-red-500/10 border border-red-500/20 rounded-lg">
                            <p className="text-xs text-red-400">
                              <AlertTriangleIcon size={14} className="inline-block align-text-bottom mr-1" />
                              Authorization expired. Re-authorize to restore access.
                            </p>
                          </div>
                        )}
                        <div className="flex gap-2">
                          {integration.health_status === 'unavailable' ? (
                            <button
                              onClick={() => handleReauthorize(integration.id)}
                              className="flex-1 py-2 text-sm rounded-lg font-medium bg-blue-500/10 text-blue-400 border border-blue-500/30 hover:bg-blue-500/20 transition-all"
                            >
                              Re-authorize
                            </button>
                          ) : (
                            <button
                              onClick={() => handleGmailDisconnect(integration.id)}
                              className="flex-1 py-2 text-sm rounded-lg font-medium bg-tsushin-vermilion/10 text-tsushin-vermilion border border-tsushin-vermilion/30 hover:bg-tsushin-vermilion/20 transition-all"
                            >
                              Disconnect
                            </button>
                          )}
                        </div>
                      </div>
                    ))}

                    {/* Add Another Account Card */}
                    <div className={`card p-5 hover-glow border-dashed border-red-700/30 ${!googleCredentials ? 'opacity-70' : ''}`}>
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center">
                            <PlusIconSvg size={20} className="text-red-400" />
                          </div>
                          <h3 className="font-semibold text-white">
                            {hubIntegrations.filter(i => i.type === 'gmail').length > 0 ? 'Add Another Gmail' : 'Gmail'}
                          </h3>
                        </div>
                        {hubIntegrations.filter(i => i.type === 'gmail').length === 0 && (
                          <span className="badge badge-neutral">Not Connected</span>
                        )}
                      </div>
                      <p className="text-xs text-tsushin-slate mb-3">
                        {hubIntegrations.filter(i => i.type === 'gmail').length > 0
                          ? 'Connect an additional Gmail account'
                          : 'Read and send emails via Gmail'}
                      </p>
                      {!googleCredentials && (
                        <div className="mb-3 p-2 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                          <p className="text-xs text-amber-400">
                            <AlertTriangleIcon size={14} className="inline-block align-text-bottom mr-1" /> Requires Google OAuth. <a href="/settings/integrations" className="underline hover:no-underline">Configure in Settings</a>
                          </p>
                        </div>
                      )}
                      <button
                        onClick={handleGmailConnect}
                        disabled={!googleCredentials}
                        className={`w-full btn-secondary py-2 text-sm ${!googleCredentials ? 'opacity-50 cursor-not-allowed' : ''}`}
                      >
                        {hubIntegrations.filter(i => i.type === 'gmail').length > 0 ? '+ Add Gmail Account' : 'Connect to Gmail'}
                      </button>
                    </div>
                  </div>
                </div>

                {/* More Channels and Push Notifications sections removed — all channels now have full integrations */}
              </div>
            )}

            {/* ==================== PRODUCTIVITY TAB ==================== */}
            {activeTab === 'productivity' && (
              <div className="space-y-6 animate-fade-in">
                <div>
                  <h2 className="text-lg font-display font-semibold text-white">Productivity & Scheduling</h2>
                  <p className="text-sm text-tsushin-slate">Connect task management and calendar apps</p>
                </div>

                {/* Google OAuth Credentials Status - Link to centralized settings */}
                <div className="card p-5 border-purple-700/30">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center">
                        <LockIcon size={20} className="text-purple-400" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-white">Google Integration</h3>
                        <p className="text-xs text-tsushin-slate">Gmail, Calendar & SSO</p>
                      </div>
                    </div>
                    {googleCredentials ? (
                      <span className="px-2 py-1 text-xs font-medium rounded-full bg-green-500/10 text-green-400 border border-green-500/20">
                        Configured
                      </span>
                    ) : (
                      <span className="px-2 py-1 text-xs font-medium rounded-full bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
                        Not Configured
                      </span>
                    )}
                  </div>
                  {googleCredentials ? (
                    <p className="text-xs text-tsushin-slate mb-3">
                      Google OAuth is configured. Connect Gmail or Calendar below.
                    </p>
                  ) : (
                    <p className="text-xs text-tsushin-slate mb-3">
                      Configure Google OAuth in Settings to enable Gmail, Calendar, and SSO.
                    </p>
                  )}
                  <a
                    href="/settings/integrations"
                    className="w-full btn-secondary py-2 text-sm inline-block text-center"
                  >
                    {googleCredentials ? 'Manage in Settings' : 'Configure in Settings'}
                  </a>
                </div>

                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {/* Asana Integration (Special - OAuth) */}
                  {hubIntegrations.filter(i => i.type === 'asana').length > 0 ? (
                    hubIntegrations.filter(i => i.type === 'asana').map(integration => (
                      <div key={integration.id} className="card p-5 hover-glow border-orange-700/30">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
                              <CheckCircleIcon size={20} className="text-orange-400" />
                            </div>
                            <h3 className="font-semibold text-white">Asana</h3>
                          </div>
                          <span className={`px-2 py-1 text-xs font-medium rounded-full ${integration.health_status === 'healthy'
                              ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                              : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                            }`}>
                            {integration.health_status === 'healthy' ? 'Connected' : integration.health_status}
                          </span>
                        </div>
                        <p className="text-xs text-tsushin-slate mb-3">Task & project management</p>
                        <div className="text-sm text-tsushin-slate mb-3">
                          <p className="text-xs">Workspace: {integration.workspace_name || 'Unknown'}</p>
                          <p className="text-xs font-mono text-orange-400">GID: {integration.workspace_gid || 'N/A'}</p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => window.location.href = `/hub/asana/${integration.id}`}
                            className="flex-1 btn-ghost py-2 text-sm"
                          >
                            Manage
                          </button>
                          <button
                            onClick={() => handleAsanaDisconnect(integration.id)}
                            className="flex-1 py-2 text-sm rounded-lg font-medium bg-tsushin-vermilion/10 text-tsushin-vermilion border border-tsushin-vermilion/30 hover:bg-tsushin-vermilion/20 transition-all"
                          >
                            Disconnect
                          </button>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="card p-5 hover-glow border-dashed border-orange-700/30">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
                            <CheckCircleIcon size={20} className="text-orange-400" />
                          </div>
                          <h3 className="font-semibold text-white">Asana</h3>
                        </div>
                        <span className="badge badge-neutral">Not Connected</span>
                      </div>
                      <p className="text-xs text-tsushin-slate mb-4">Task & project management</p>
                      <button
                        onClick={handleAsanaConnect}
                        className="w-full btn-secondary py-2 text-sm"
                      >
                        Connect to Asana
                      </button>
                    </div>
                  )}

                  {/* Google Calendar Integration */}
                  {/* Existing Calendar Integrations */}
                  {hubIntegrations.filter(i => i.type === 'calendar').map(integration => (
                    <div key={integration.id} className={`card p-5 hover-glow ${integration.health_status === 'unavailable' ? 'border-red-500/50' : 'border-blue-700/30'}`}>
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
                            <CalendarIcon size={20} className="text-blue-400" />
                          </div>
                          <h3 className="font-semibold text-white">Google Calendar</h3>
                        </div>
                        <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                          integration.health_status === 'healthy'
                            ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                            : integration.health_status === 'unavailable'
                            ? 'bg-red-500/10 text-red-400 border border-red-500/20'
                            : 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'
                          }`}>
                          {integration.health_status === 'healthy' ? 'Connected' : integration.health_status === 'unavailable' ? 'Expired' : integration.health_status}
                        </span>
                      </div>
                      <p className="text-xs text-tsushin-slate mb-3">Calendar & scheduling</p>
                      <div className="text-sm text-tsushin-slate mb-3">
                        <p className="text-xs">Account: {integration.name?.replace('Google Calendar - ', '') || 'Unknown'}</p>
                      </div>
                      {integration.health_status === 'unavailable' && (
                        <div className="mb-3 p-2 bg-red-500/10 border border-red-500/20 rounded-lg">
                          <p className="text-xs text-red-400">
                            <AlertTriangleIcon size={14} className="inline-block align-text-bottom mr-1" />
                            Authorization expired. Re-authorize to restore access.
                          </p>
                        </div>
                      )}
                      <div className="flex gap-2">
                        {integration.health_status === 'unavailable' ? (
                          <button
                            onClick={() => handleReauthorize(integration.id)}
                            className="flex-1 py-2 text-sm rounded-lg font-medium bg-blue-500/10 text-blue-400 border border-blue-500/30 hover:bg-blue-500/20 transition-all"
                          >
                            Re-authorize
                          </button>
                        ) : (
                          <button
                            onClick={() => handleGoogleCalendarDisconnect(integration.id)}
                            className="flex-1 py-2 text-sm rounded-lg font-medium bg-tsushin-vermilion/10 text-tsushin-vermilion border border-tsushin-vermilion/30 hover:bg-tsushin-vermilion/20 transition-all"
                          >
                            Disconnect
                          </button>
                        )}
                      </div>
                    </div>
                  ))}

                  {/* Add Another Account Card */}
                  <div className={`card p-5 hover-glow border-dashed border-blue-700/30 ${!googleCredentials ? 'opacity-70' : ''}`}>
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
                          {hubIntegrations.filter(i => i.type === 'calendar').length > 0 ? <PlusIconSvg size={20} className="text-blue-400" /> : <CalendarIcon size={20} className="text-blue-400" />}
                        </div>
                        <h3 className="font-semibold text-white">
                          {hubIntegrations.filter(i => i.type === 'calendar').length > 0 ? 'Add Another Calendar' : 'Google Calendar'}
                        </h3>
                      </div>
                      {hubIntegrations.filter(i => i.type === 'calendar').length === 0 && (
                        <span className="badge badge-neutral">Not Connected</span>
                      )}
                    </div>
                    <p className="text-xs text-tsushin-slate mb-3">
                      {hubIntegrations.filter(i => i.type === 'calendar').length > 0
                        ? 'Connect an additional Google Calendar'
                        : 'Calendar & scheduling'}
                    </p>
                    {!googleCredentials && (
                      <div className="mb-3 p-2 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                        <p className="text-xs text-amber-400">
                          <AlertTriangleIcon size={14} className="inline-block align-text-bottom mr-1" /> Requires Google OAuth. <a href="/settings/integrations" className="underline hover:no-underline">Configure in Settings</a>
                        </p>
                      </div>
                    )}
                    <button
                      onClick={handleGoogleCalendarConnect}
                      disabled={!googleCredentials}
                      className={`w-full btn-secondary py-2 text-sm ${!googleCredentials ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                      {hubIntegrations.filter(i => i.type === 'calendar').length > 0 ? '+ Add Calendar Account' : 'Connect to Google Calendar'}
                    </button>
                  </div>

                  {/* Coming Soon Productivity Apps */}
                  {PRODUCTIVITY_APPS.filter(app => app.value !== 'asana' && app.value !== 'google_calendar').map(app => {
                    const AppIcon = app.Icon
                    return (
                      <div key={app.value} className="card p-5 opacity-60">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gray-700/50 flex items-center justify-center text-gray-400">
                              <AppIcon size={20} />
                            </div>
                            <h3 className="font-semibold text-white">{app.label}</h3>
                        </div>
                        <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-600/30 text-gray-400 border border-gray-600/50">
                          Coming Soon
                        </span>
                        </div>
                        <p className="text-xs text-tsushin-slate mb-4">{app.description}</p>
                        <div className="text-center py-2">
                          <span className="text-xs text-gray-500">Coming Soon</span>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* Info Box */}
                <div className="bg-orange-500/5 border border-orange-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-orange-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-orange-300" /> Productivity Integrations
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    Connect your favorite productivity tools to let agents manage tasks, schedule meetings, and sync with your knowledge bases.
                    Google Calendar and Notion integrations are high priority for Q1 2026.
                  </p>
                </div>
              </div>
            )}

            {/* ==================== DEVELOPER TOOLS TAB ==================== */}
            {activeTab === 'developer' && (
              <div className="space-y-6 animate-fade-in">
                <div>
                  <h2 className="text-lg font-display font-semibold text-white">Developer Tools</h2>
                  <p className="text-sm text-tsushin-slate">Shell execution, sandboxed tools, and DevOps integrations</p>
                </div>

                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {/* Shell Command Center - Featured Card (full-width hero) */}
                  <div
                    className="card p-5 hover-glow group border-teal-700/30 col-span-full cursor-pointer"
                    onClick={() => window.location.href = '/hub/shell'}
                  >
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl bg-teal-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                          <TerminalIconSvg size={24} className="text-teal-400" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-white text-lg">Shell Command Center</h3>
                          <p className="text-sm text-tsushin-slate">Remote shell execution with security controls</p>
                        </div>
                      </div>
                      <span className="px-3 py-1 text-xs font-medium rounded-full bg-teal-500/20 text-teal-400 border border-teal-500/50">
                        Available
                      </span>
                    </div>
                    <div className="text-sm text-tsushin-slate mb-4">
                      <p className="mb-3">Execute shell commands remotely via beacon agents with secure approval workflows:</p>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-teal-400 flex items-center gap-1"><RadioIcon size={14} className="text-teal-400" /> Beacons</span>
                          <p className="text-xs text-gray-500">Remote agents</p>
                        </div>
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-orange-400 flex items-center gap-1"><LockIcon size={14} className="text-orange-400" /> Approvals</span>
                          <p className="text-xs text-gray-500">High-risk review</p>
                        </div>
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-purple-400 flex items-center gap-1"><ClipboardIconSvg size={14} className="text-purple-400" /> Audit Log</span>
                          <p className="text-xs text-gray-500">Full history</p>
                        </div>
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-red-400 flex items-center gap-1"><ShieldIcon size={14} className="text-red-400" /> Security</span>
                          <p className="text-xs text-gray-500">Rate limiting</p>
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={() => window.location.href = '/hub/shell'}
                      className="w-full btn-primary py-2.5 text-sm font-medium"
                    >
                      Open Shell Command Center →
                    </button>
                  </div>

                  {/* Toolbox Container - Sandboxed Tools */}
                  <div
                    className="card p-5 hover-glow group border-purple-700/30 col-span-full lg:col-span-2 cursor-pointer"
                    onClick={() => window.location.href = '/hub/sandboxed-tools'}
                  >
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                          <BoxIconSvg size={24} className="text-purple-400" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-white text-lg">Sandboxed Tools</h3>
                          <p className="text-sm text-tsushin-slate">Per-tenant isolated execution environment</p>
                        </div>
                      </div>
                      {getToolboxBadge()}
                    </div>
                    <div className="text-sm text-tsushin-slate mb-4">
                      <p className="mb-2">Create command-based tools that run in a secure, isolated container with pre-installed security scanners and utilities.</p>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-3">
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-tsushin-accent">nmap</span>
                          <p className="text-xs text-gray-500">Network scanner</p>
                        </div>
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-tsushin-accent">nuclei</span>
                          <p className="text-xs text-gray-500">Vuln scanner</p>
                        </div>
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-tsushin-accent">katana</span>
                          <p className="text-xs text-gray-500">Web crawler</p>
                        </div>
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-tsushin-accent">httpx</span>
                          <p className="text-xs text-gray-500">HTTP toolkit</p>
                        </div>
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-tsushin-accent">subfinder</span>
                          <p className="text-xs text-gray-500">Subdomain finder</p>
                        </div>
                        <div className="bg-tsushin-deep/50 px-3 py-2 rounded-lg">
                          <span className="text-xs text-tsushin-accent">Python 3.11</span>
                          <p className="text-xs text-gray-500">Scripting</p>
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); window.location.href = '/hub/sandboxed-tools' }}
                      className="w-full btn-primary py-2.5 text-sm font-medium"
                    >
                      Open Toolbox Manager →
                    </button>
                  </div>

                  {/* Sandboxed Tools Quick Actions */}
                  <div className="card p-5 hover-glow group">
                    <div className="flex items-center gap-3 mb-4">
                      <div className="w-10 h-10 rounded-xl bg-teal-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                        <LightningIcon size={20} className="text-teal-400" />
                      </div>
                      <h3 className="font-semibold text-white">Quick Actions</h3>
                    </div>
                    <div className="space-y-2">
                      <button
                        onClick={() => window.location.href = '/hub/sandboxed-tools?action=create'}
                        className="w-full btn-ghost py-2 text-sm text-left flex items-center gap-2"
                      >
                        <PlusIconSvg size={16} /> Create New Tool
                      </button>
                      <button
                        onClick={() => window.location.href = '/hub/sandboxed-tools?tab=packages'}
                        className="w-full btn-ghost py-2 text-sm text-left flex items-center gap-2"
                      >
                        <PackageIcon size={16} /> Install Package
                      </button>
                      <button
                        onClick={() => window.location.href = '/hub/sandboxed-tools?tab=executions'}
                        className="w-full btn-ghost py-2 text-sm text-left flex items-center gap-2"
                      >
                        <ClipboardIconSvg size={16} /> View Executions
                      </button>
                    </div>
                  </div>

                  {/* Coming Soon Developer Tools */}
                  {DEVELOPER_TOOLS.filter(tool => tool.status === 'coming_soon').map(tool => {
                    const ToolIcon = tool.Icon
                    return (
                      <div key={tool.value} className="card p-5 opacity-60">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-xl bg-gray-700/50 flex items-center justify-center text-gray-400">
                              <ToolIcon size={20} />
                            </div>
                            <h3 className="font-semibold text-white">{tool.label}</h3>
                          </div>
                          <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-600/30 text-gray-400 border border-gray-600/50">
                            Coming Soon
                          </span>
                        </div>
                        <p className="text-xs text-tsushin-slate mb-4">{tool.description}</p>
                        <div className="text-center py-2">
                          <span className="text-xs text-gray-500">Coming Soon</span>
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* Info Box */}
                <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-blue-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-blue-300" /> Developer Integrations
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    The Shell Command Center enables remote command execution with security approval workflows. Sandboxed Tools provide
                    per-tenant isolated containers for network scans, vulnerability assessments, and custom scripts. GitHub integration
                    is coming soon, enabling agents to create issues, summarize PRs, and respond to repository events.
                  </p>
                </div>
              </div>
            )}

            {/* ==================== TOOL APIS TAB ==================== */}
            {activeTab === 'tool-apis' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">Tool APIs</h2>
                    <p className="text-sm text-tsushin-slate">External APIs for agent capabilities</p>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 animate-stagger">
                  {TOOL_APIS.map(tool => renderIntegrationCard(tool, 'tool'))}
                </div>

                {/* Built-in Tools Info */}
                <div className="bg-teal-500/5 border border-teal-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-teal-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-teal-300" /> Built-in Tools
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    These tools are automatically available to agents when the corresponding API keys are configured.
                    Tools include: Web Search (Brave/Tavily/Google), Flight Search (Amadeus/Google), and Web Scraping.
                  </p>
                </div>
              </div>
            )}

            {/* ==================== MCP SERVERS TAB ==================== */}
            {activeTab === 'mcp-servers' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">MCP Servers</h2>
                    <p className="text-sm text-tsushin-slate">Connect external Model Context Protocol servers for tool discovery</p>
                  </div>
                  <button
                    onClick={() => setShowMcpServerModal(true)}
                    className="btn-primary"
                  >
                    + Add Server
                  </button>
                </div>

                {/* MCP Server Cards */}
                {mcpServersLoading ? (
                  <div className="text-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-tsushin-accent mx-auto mb-3" />
                    <p className="text-tsushin-slate text-sm">Loading MCP servers...</p>
                  </div>
                ) : mcpServers.length === 0 ? (
                  <div className="text-center py-16">
                    <div className="w-16 h-16 rounded-2xl bg-cyan-400/10 flex items-center justify-center mx-auto mb-4">
                      <ServerIcon />
                    </div>
                    <h3 className="text-white font-semibold mb-2">No MCP Servers</h3>
                    <p className="text-tsushin-slate text-sm mb-4">Add an MCP server to discover and use external tools</p>
                    <button
                      onClick={() => setShowMcpServerModal(true)}
                      className="btn-primary"
                    >
                      + Add Server
                    </button>
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {mcpServers.map(server => {
                      const isActionLoading = mcpServerActionLoading === server.id
                      const statusColor = server.connection_status === 'healthy' ? 'bg-green-400'
                        : server.connection_status === 'degraded' ? 'bg-yellow-400'
                        : server.connection_status === 'connecting' ? 'bg-yellow-400 animate-pulse'
                        : server.connection_status === 'disconnected' ? 'bg-red-400'
                        : 'bg-gray-400'
                      const transportLabel = server.transport_type === 'sse' ? 'SSE'
                        : server.transport_type === 'streamable_http' ? 'HTTP'
                        : server.transport_type === 'stdio' ? 'Stdio'
                        : server.transport_type

                      return (
                        <div key={server.id} className="bg-tsushin-surface border border-white/10 rounded-xl p-4 hover:border-white/20 transition-colors">
                          {/* Header */}
                          <div className="flex items-start justify-between mb-3">
                            <div className="flex items-center gap-2 min-w-0">
                              <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${statusColor}`} />
                              <h3 className="text-white font-semibold text-sm truncate">{server.server_name}</h3>
                            </div>
                            <span className="text-xs px-2 py-0.5 rounded-full bg-tsushin-indigo/20 text-tsushin-accent flex-shrink-0 ml-2">
                              {transportLabel}
                            </span>
                          </div>

                          {/* Description */}
                          {server.description && (
                            <p className="text-xs text-tsushin-slate mb-3 line-clamp-2">{server.description}</p>
                          )}

                          {/* Info row */}
                          <div className="flex items-center gap-3 text-xs text-tsushin-slate mb-3">
                            <span className="flex items-center gap-1">
                              <WrenchIcon />
                              {server.tool_count} tools
                            </span>
                            {server.last_connected_at && (
                              <span title={server.last_connected_at}>
                                Last: {new Date(server.last_connected_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>

                          {/* Error display */}
                          {server.last_error && (
                            <div className="text-xs text-tsushin-vermilion bg-tsushin-vermilion/10 rounded-lg px-2 py-1.5 mb-3 truncate" title={server.last_error}>
                              {server.last_error}
                            </div>
                          )}

                          {/* Actions */}
                          <div className="flex flex-wrap gap-1.5">
                            {server.connection_status === 'healthy' ? (
                              <button
                                onClick={() => handleDisconnectMcpServer(server.id)}
                                disabled={isActionLoading}
                                className="text-xs px-2.5 py-1.5 rounded-lg bg-white/5 text-tsushin-slate hover:bg-white/10 hover:text-white transition-colors disabled:opacity-50"
                              >
                                {isActionLoading ? 'Working...' : 'Disconnect'}
                              </button>
                            ) : (
                              <button
                                onClick={() => handleConnectMcpServer(server.id)}
                                disabled={isActionLoading}
                                className="text-xs px-2.5 py-1.5 rounded-lg bg-tsushin-accent/10 text-tsushin-accent hover:bg-tsushin-accent/20 transition-colors disabled:opacity-50"
                              >
                                {isActionLoading ? 'Working...' : 'Connect'}
                              </button>
                            )}
                            <button
                              onClick={() => handleRefreshMcpTools(server.id)}
                              disabled={isActionLoading}
                              className="text-xs px-2.5 py-1.5 rounded-lg bg-white/5 text-tsushin-slate hover:bg-white/10 hover:text-white transition-colors disabled:opacity-50"
                            >
                              Refresh Tools
                            </button>
                            <Link
                              href={`/agents/custom-skills?mcp_server_id=${server.id}`}
                              className="text-xs px-2.5 py-1.5 rounded-lg bg-tsushin-indigo/10 text-tsushin-indigo hover:bg-tsushin-indigo/20 transition-colors inline-flex items-center gap-1"
                            >
                              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                              </svg>
                              Create Skill
                            </Link>
                            <button
                              onClick={() => handleDeleteMcpServer(server.id, server.server_name)}
                              disabled={isActionLoading}
                              className="text-xs px-2.5 py-1.5 rounded-lg bg-white/5 text-tsushin-vermilion/80 hover:bg-tsushin-vermilion/10 hover:text-tsushin-vermilion transition-colors disabled:opacity-50"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}

                {/* Info Box */}
                <div className="bg-cyan-500/5 border border-cyan-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-cyan-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-cyan-300" /> MCP Server Integration
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    MCP (Model Context Protocol) servers expose tools that your agents can use. Connect via SSE, HTTP, or Stdio transport.
                    Stdio transport runs approved launchers inside your tenant toolbox container for maximum isolation. This stack ships with `uvx` available by default.
                    After connecting, use &ldquo;Refresh Tools&rdquo; to discover available tools from the server.
                  </p>
                </div>
              </div>
            )}

            {/* v0.6.0: Vector Stores Tab */}
            {activeTab === 'vector-stores' && (
              <div className="space-y-6 animate-fade-in">
                {/* Header */}
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">Vector Stores</h2>
                    <p className="text-sm text-tsushin-slate">Connect external vector databases for enhanced RAG and semantic search</p>
                  </div>
                  <button
                    onClick={() => { setEditingVectorStore(null); setShowVectorStoreModal(true) }}
                    className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white text-sm rounded-lg transition-colors"
                  >
                    + Add Vector Store
                  </button>
                </div>

                {/* Cards grid */}
                {vectorStoresLoading && vectorStoreInstances.length === 0 ? (
                  <div className="text-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-400 mx-auto mb-3" />
                    <p className="text-tsushin-slate text-sm">Loading vector stores...</p>
                  </div>
                ) : vectorStoreInstances.length === 0 ? (
                  <div className="text-center py-16">
                    <div className="w-16 h-16 rounded-2xl bg-emerald-400/10 flex items-center justify-center mx-auto mb-4 text-emerald-400">
                      <VectorStoreIcon />
                    </div>
                    <h3 className="text-white font-semibold mb-2">No Vector Stores Connected</h3>
                    <p className="text-tsushin-slate text-sm mb-4 max-w-md mx-auto">
                      Connect an external vector database (MongoDB Atlas, Pinecone, or Qdrant) to enable advanced RAG capabilities for your agents.
                    </p>
                    <button
                      onClick={() => { setEditingVectorStore(null); setShowVectorStoreModal(true) }}
                      className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white text-sm rounded-lg transition-colors"
                    >
                      + Add Vector Store
                    </button>
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {vectorStoreInstances.map(instance => (
                      <VectorStoreCard
                        key={instance.id}
                        instance={instance}
                        onEdit={(inst) => { setEditingVectorStore(inst); setShowVectorStoreModal(true) }}
                        onDelete={async (inst) => {
                          if (!confirm(`Delete vector store "${inst.instance_name}"? Agents using this store will fall back to ChromaDB.`)) return
                          try {
                            await api.deleteVectorStoreInstance(inst.id)
                            toast.success('Vector store deleted')
                            loadVectorStoreInstances()
                          } catch (err: any) {
                            toast.error(err.message || 'Failed to delete')
                          }
                        }}
                        onTest={async (inst) => {
                          setVectorStoreTestLoading(inst.id)
                          try {
                            const result = await api.testVectorStoreConnection(inst.id)
                            toast[result.success ? 'success' : 'error'](result.message)
                            loadVectorStoreInstances()
                          } catch (err: any) {
                            toast.error(err.message || 'Test failed')
                          } finally {
                            setVectorStoreTestLoading(null)
                          }
                        }}
                        testLoading={vectorStoreTestLoading === instance.id}
                        onContainerAction={async (inst, action) => {
                          try {
                            await api.vectorStoreContainerAction(inst.id, action)
                            toast.success(`Container ${action} successful`)
                            loadVectorStoreInstances()
                          } catch (err: any) {
                            toast.error(err.message || `Container ${action} failed`)
                          }
                        }}
                      />
                    ))}
                  </div>
                )}

                {/* Info Box */}
                <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-emerald-300 mb-2">External Vector Stores</h3>
                  <p className="text-xs text-tsushin-slate">
                    Connect external vector databases to replace or complement the built-in ChromaDB. Each agent can be configured to use a specific vector store in override, complement, or shadow mode. When an external store is unavailable, the system automatically falls back to ChromaDB.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* MCP Server Create Modal */}
      <Modal
        isOpen={showMcpServerModal}
        onClose={() => setShowMcpServerModal(false)}
        title="Add MCP Server"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowMcpServerModal(false)}
              className="px-4 py-2 bg-gray-700 text-white rounded"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              onClick={handleCreateMcpServer}
              disabled={saving}
              className="px-4 py-2 bg-teal-500 text-white rounded disabled:opacity-50"
            >
              {saving ? 'Creating...' : 'Create Server'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Server Name *</label>
            <input
              type="text"
              value={mcpServerForm.server_name}
              onChange={e => setMcpServerForm({ ...mcpServerForm, server_name: e.target.value })}
              placeholder="e.g. my-asana-mcp"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Description</label>
            <input
              type="text"
              value={mcpServerForm.description}
              onChange={e => setMcpServerForm({ ...mcpServerForm, description: e.target.value })}
              placeholder="Optional description"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Transport Type *</label>
            <select
              value={mcpServerForm.transport_type}
              onChange={e => setMcpServerForm({ ...mcpServerForm, transport_type: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
            >
              <option value="sse">SSE (Server-Sent Events)</option>
              <option value="streamable_http">Streamable HTTP</option>
              <option value="stdio">Stdio (Container Binary)</option>
            </select>
          </div>

          {/* Conditional fields based on transport type */}
          {mcpServerForm.transport_type !== 'stdio' ? (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Server URL *</label>
              <input
                type="url"
                value={mcpServerForm.server_url}
                onChange={e => setMcpServerForm({ ...mcpServerForm, server_url: e.target.value })}
                placeholder="https://mcp-server.example.com/sse"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
              />
            </div>
          ) : (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Binary *</label>
                <select
                  value={mcpServerForm.stdio_binary}
                  onChange={e => setMcpServerForm({ ...mcpServerForm, stdio_binary: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                >
                  <option value="">Select binary...</option>
                  {allowedBinaries.map(bin => (
                    <option key={bin} value={bin}>{bin}</option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {allowedBinaries.length} allowed {allowedBinaries.length === 1 ? 'binary' : 'binaries'} in toolbox containers
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Arguments (one per line)</label>
                <textarea
                  value={mcpServerForm.stdio_args.join('\n')}
                  onChange={e => setMcpServerForm({ ...mcpServerForm, stdio_args: e.target.value.split('\n') })}
                  placeholder={"e.g.\nmcp-server-package\n--port\n3000"}
                  rows={3}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white font-mono text-sm"
                />
              </div>
            </>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">Authentication</label>
            <select
              value={mcpServerForm.auth_type}
              onChange={e => setMcpServerForm({ ...mcpServerForm, auth_type: e.target.value })}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
            >
              <option value="none">None</option>
              <option value="bearer">Bearer Token</option>
              <option value="api_key">API Key</option>
              <option value="header">Custom Header</option>
            </select>
          </div>
          {mcpServerForm.auth_type !== 'none' && (
            <>
              {(mcpServerForm.auth_type === 'api_key' || mcpServerForm.auth_type === 'header') && (
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">Header Name</label>
                  <input
                    type="text"
                    value={mcpServerForm.auth_header_name}
                    onChange={e => setMcpServerForm({ ...mcpServerForm, auth_header_name: e.target.value })}
                    placeholder={mcpServerForm.auth_type === 'api_key' ? 'X-API-Key' : 'Authorization'}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Token / API Key</label>
                <input
                  type="password"
                  value={mcpServerForm.auth_token}
                  onChange={e => setMcpServerForm({ ...mcpServerForm, auth_token: e.target.value })}
                  placeholder="Enter token or key"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
                />
              </div>
            </>
          )}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Trust Level</label>
              <select
                value={mcpServerForm.trust_level}
                onChange={e => setMcpServerForm({ ...mcpServerForm, trust_level: e.target.value })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
              >
                <option value="untrusted">Untrusted</option>
                <option value="verified">Verified</option>
                <option value="system">System</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">Timeout (s)</label>
              <input
                type="number"
                min={5}
                max={300}
                value={mcpServerForm.timeout_seconds}
                onChange={e => setMcpServerForm({ ...mcpServerForm, timeout_seconds: parseInt(e.target.value) || 30 })}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
              />
            </div>
          </div>
        </div>
      </Modal>

      {/* API Key Modal */}
      {showApiKeyModal && (
        <Modal
          isOpen={showApiKeyModal}
          onClose={() => setShowApiKeyModal(false)}
          title={editingKey ? 'Edit API Key' : 'Add API Key'}
          footer={
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowApiKeyModal(false)}
                className="px-4 py-2 bg-gray-700 text-white rounded"
                disabled={saving}
              >
                Cancel
              </button>
              <button
                onClick={saveAPIKey}
                className="px-4 py-2 bg-teal-500 text-white rounded disabled:opacity-50"
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          }
        >
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Service</label>
              <select
                value={modalData.service}
                onChange={(e) => setModalData({ ...modalData, service: e.target.value })}
                disabled={!!editingKey}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white disabled:opacity-50"
              >
                <option value="">Select service...</option>
                <optgroup label="AI Providers">
                  {AI_PROVIDERS.filter(p => p.status === 'available').map(p => (
                    <option key={p.value} value={p.value}>{p.label}</option>
                  ))}
                </optgroup>
                <optgroup label="Tool APIs">
                  {TOOL_APIS.filter(t => t.status === 'available').map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </optgroup>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">API Key</label>
              <input
                type="password"
                value={modalData.api_key}
                onChange={(e) => setModalData({ ...modalData, api_key: e.target.value })}
                placeholder={editingKey ? 'Enter new key to update' : 'Enter API key'}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
              />
            </div>
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={modalData.is_active}
                onChange={(e) => setModalData({ ...modalData, is_active: e.target.checked })}
                className="mr-2"
              />
              <span className="text-sm text-gray-300">Enable this integration</span>
            </label>
          </div>
        </Modal>
      )}

      <Modal
        isOpen={Boolean(apiKeyDeleteTarget)}
        onClose={() => {
          if (!deletingApiKeyService) {
            setApiKeyDeleteTarget(null)
          }
        }}
        title="Remove Integration"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setApiKeyDeleteTarget(null)}
              className="px-4 py-2 bg-gray-700 text-white rounded disabled:opacity-50"
              disabled={Boolean(deletingApiKeyService)}
            >
              Cancel
            </button>
            <button
              onClick={deleteAPIKey}
              className="px-4 py-2 bg-red-600 text-white rounded disabled:opacity-50"
              disabled={Boolean(deletingApiKeyService)}
            >
              {deletingApiKeyService ? 'Removing...' : 'Remove'}
            </button>
          </div>
        }
      >
        <div className="space-y-3 text-sm text-tsushin-slate">
          <p>
            Remove the {apiKeyDeleteLabel || 'selected'} integration from this workspace?
          </p>
          <p className="text-xs text-tsushin-slate/80">
            Agents will stop using this credential until you add a new key.
          </p>
        </div>
      </Modal>

      {/* WhatsApp Create Mode Selector */}
      <WhatsAppCreateModeSelector
        isOpen={showCreateModeSelector}
        onClose={() => setShowCreateModeSelector(false)}
        onSelectWizard={() => {
          setShowCreateModeSelector(false)
          openWhatsAppWizard()
        }}
        onSelectAdvanced={() => {
          setShowCreateModeSelector(false)
          setShowMcpCreateModal(true)
        }}
      />

      {/* MCP Create Modal */}
      <Modal
        isOpen={showMcpCreateModal}
        onClose={() => {
          setShowMcpCreateModal(false)
          setMcpPhoneNumber('')
          setMcpInstanceType('agent')
        }}
        title="Create WhatsApp Instance"
        footer={
          <div className="flex justify-end gap-3">
            <button
              onClick={() => setShowMcpCreateModal(false)}
              className="px-4 py-2 bg-gray-700 text-white rounded"
              disabled={saving}
            >
              Cancel
            </button>
            <button
              onClick={handleCreateMcpInstance}
              className="px-4 py-2 bg-teal-500 text-white rounded disabled:opacity-50"
              disabled={saving}
            >
              {saving ? 'Creating...' : 'Create'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Instance Type</label>
            <div className="grid grid-cols-2 gap-4">
              <button
                type="button"
                onClick={() => setMcpInstanceType('agent')}
                className={`p-4 rounded-lg border-2 transition-all ${mcpInstanceType === 'agent'
                    ? 'border-green-500 bg-green-500/10'
                    : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                  }`}
              >
                <div className="mb-2"><BotIconSvg size={28} className="text-green-400" /></div>
                <div className="font-semibold text-white">Agent</div>
                <div className="text-xs text-gray-400">Bot responds to messages</div>
              </button>
              <button
                type="button"
                onClick={() => setMcpInstanceType('tester')}
                className={`p-4 rounded-lg border-2 transition-all ${mcpInstanceType === 'tester'
                    ? 'border-orange-500 bg-orange-500/10'
                    : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                  }`}
              >
                <div className="mb-2"><BeakerIcon size={28} className="text-orange-400" /></div>
                <div className="font-semibold text-white">Tester</div>
                <div className="text-xs text-gray-400">QA testing</div>
                <div className="text-[10px] text-orange-400/60 mt-1 italic">(For development testing purposes only)</div>
              </button>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">Phone Number</label>
            <input
              type="text"
              value={mcpPhoneNumber}
              onChange={(e) => setMcpPhoneNumber(e.target.value)}
              placeholder="+5500000000001"
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
            />
            <p className="mt-1 text-xs text-gray-500">Include country code (e.g., +55 for Brazil)</p>
          </div>
        </div>
      </Modal>

      {/* QR Code Modal */}
      <Modal
        isOpen={showQRModal}
        onClose={() => {
          setShowQRModal(false)
          setSelectedMcpInstance(null)
          setSelectedQrResource(null)
          setQRCode(null)
          setQrAuthSuccess(false)
          setQrLastRefresh(null)
          setQrStatus('loading')
          setQrStatusMessage(null)
        }}
        title={selectedQrResource === 'tester' ? 'QR Code - Tester MCP' : `QR Code - ${selectedMcpInstance?.phone_number}`}
        size="lg"
      >
        <div className="text-center">
          {qrAuthSuccess ? (
            // Success state - shown briefly before auto-close
            <div className="py-8">
              <div className="w-16 h-16 bg-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-green-400 font-medium">WhatsApp Connected!</p>
              <p className="text-gray-400 text-sm mt-2">Closing automatically...</p>
            </div>
          ) : qrCode ? (
            <div>
              <div className="relative inline-block">
                <img
                  src={`data:image/png;base64,${qrCode}`}
                  alt="WhatsApp QR Code"
                  className="mx-auto max-w-md border-4 border-gray-700 rounded-lg"
                />
                {/* Subtle refresh indicator */}
                {qrPollingActive && (
                  <div className="absolute top-2 right-2 flex items-center gap-1 bg-gray-800/80 px-2 py-1 rounded text-xs text-gray-400">
                    <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    <span>Live</span>
                  </div>
                )}
              </div>
              <p className="mt-4 text-gray-400">Scan with WhatsApp on your phone</p>
              {/* Last refresh notice */}
              {qrLastRefresh && (
                <p className="mt-1 text-xs text-gray-500">
                  QR refreshes automatically every 15s
                </p>
              )}
              <ol className="mt-4 text-left text-sm text-gray-400 space-y-2">
                <li>1. Open WhatsApp</li>
                <li>2. Tap Menu &rarr; Linked Devices</li>
                <li>3. Tap &quot;Link a Device&quot;</li>
                <li>4. Scan this QR code</li>
              </ol>
            </div>
          ) : qrStatus === 'degraded' ? (
            <div className="py-8 space-y-4">
              <div className="w-16 h-16 rounded-full bg-amber-500/20 border border-amber-500/40 flex items-center justify-center mx-auto">
                <AlertTriangleIcon size={28} className="text-amber-400" />
              </div>
              <div>
                <p className="text-amber-300 font-medium">QR generation is degraded</p>
                <p className="text-gray-400 text-sm mt-2">
                  {qrStatusMessage || 'The instance is not producing a QR code. Use the recovery actions below.'}
                </p>
              </div>
              <div className="flex items-center justify-center gap-3">
                {selectedQrResource === 'tester' ? (
                  <>
                    <button
                      onClick={handleRestartTester}
                      className="px-3 py-2 bg-blue-600/20 text-blue-300 border border-blue-600/40 rounded-lg text-sm"
                    >
                      Restart Tester
                    </button>
                    <button
                      onClick={handleResetTesterAuth}
                      className="px-3 py-2 bg-orange-600/20 text-orange-300 border border-orange-600/40 rounded-lg text-sm"
                    >
                      Reset Authentication
                    </button>
                  </>
                ) : selectedMcpInstance ? (
                  <>
                    <button
                      onClick={() => handleMcpAction('restart', selectedMcpInstance.id)}
                      className="px-3 py-2 bg-blue-600/20 text-blue-300 border border-blue-600/40 rounded-lg text-sm"
                    >
                      Restart Instance
                    </button>
                    <button
                      onClick={() => handleResetAuth(selectedMcpInstance)}
                      className="px-3 py-2 bg-orange-600/20 text-orange-300 border border-orange-600/40 rounded-lg text-sm"
                    >
                      Reset Authentication
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          ) : (
            <div className="py-8">
              <div className="w-16 h-16 border-4 border-tsushin-indigo border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
              <p className="text-gray-400">{qrStatusMessage || 'Loading QR code...'}</p>
            </div>
          )}
        </div>
      </Modal>

      {/* Phase 17: Instance Filters Modal */}
      <Modal
        isOpen={showFiltersModal}
        onClose={() => {
          setShowFiltersModal(false)
          setSelectedMcpInstance(null)
        }}
        title={`Message Filters - ${selectedMcpInstance?.phone_number}`}
        size="lg"
      >
        <div className="space-y-6">
          {/* Group Filters */}
          <div>
            <label className="block text-sm font-medium text-white mb-2 flex items-center gap-2">
              Group Filters
              <InfoTooltip title="Group Allowlist" text="List the WhatsApp group names your agent should monitor. If you leave this empty, the agent watches ALL groups it's a member of. Adding specific groups here acts as an allowlist." position="right" />
            </label>
            <p className="text-xs text-tsushin-slate mb-2">
              WhatsApp group names to monitor. Messages from other groups will be ignored.
            </p>
            <TypeaheadChipInput
              value={filterGroupFilters}
              onChange={setFilterGroupFilters}
              onSearch={async (query): Promise<TypeaheadSuggestion[]> => {
                if (!selectedMcpInstance) return []
                const res = await api.searchWhatsAppGroups(selectedMcpInstance.id, query, 20)
                return (res.groups || []).map((g) => ({ value: g.name, label: g.name, sublabel: g.jid }))
              }}
              placeholder="Type to search groups, or enter a name"
              emptyStateText="No groups configured. All groups will be monitored."
              chipClassName="bg-teal-500/20 border-teal-500/30 text-teal-300"
              chipRemoveClassName="text-teal-400 hover:text-red-400"
              addButtonClassName="bg-teal-600 hover:bg-teal-700"
            />
          </div>

          {/* Number Filters */}
          <div>
            <label className="block text-sm font-medium text-white mb-2 flex items-center gap-2">
              Number Filters (DM Allowlist)
              <InfoTooltip title="DM Allowlist" text="An allowlist of phone numbers. Only these numbers can DM your agent directly. Others are ignored unless DM Auto Mode is on. Leave empty to allow all." position="right" />
            </label>
            <p className="text-xs text-tsushin-slate mb-2">
              Phone numbers allowed to DM the agent. Include country code.
            </p>
            <TypeaheadChipInput
              value={filterNumberFilters}
              onChange={setFilterNumberFilters}
              onSearch={async (query): Promise<TypeaheadSuggestion[]> => {
                if (!selectedMcpInstance) return []
                const res = await api.searchWhatsAppContacts(selectedMcpInstance.id, query, 20)
                return (res.contacts || []).map((c) => {
                  const phoneStr = c.phone.startsWith('+') ? c.phone : `+${c.phone}`
                  return {
                    value: phoneStr,
                    label: c.name || phoneStr,
                    sublabel: c.name ? phoneStr : undefined,
                  }
                })
              }}
              placeholder="Type a name or phone (+5500000000001)"
              emptyStateText="No numbers configured."
              chipClassName="bg-purple-500/20 border-purple-500/30 text-purple-300"
              chipRemoveClassName="text-purple-400 hover:text-red-400"
              addButtonClassName="bg-purple-600 hover:bg-purple-700"
            />
          </div>

          {/* Group Keywords */}
          <div>
            <label className="block text-sm font-medium text-white mb-2 flex items-center gap-2">
              Group Keywords
              <InfoTooltip title="Trigger Keywords" text="Words that make your agent respond in a group chat, in addition to @mentions. For example, adding 'help' means any group message containing 'help' will trigger a response." position="right" />
            </label>
            <p className="text-xs text-tsushin-slate mb-2">
              Keywords that trigger agent responses in groups (besides @mentions).
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={filterInputKeyword}
                onChange={(e) => setFilterInputKeyword(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addFilterItem('keyword')}
                placeholder="Enter keyword"
                className="flex-1 bg-tsushin-deep border border-tsushin-slate/30 rounded px-3 py-2 text-white text-sm"
              />
              <button
                onClick={() => addFilterItem('keyword')}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded text-sm"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {filterGroupKeywords.length === 0 ? (
                <p className="text-xs text-tsushin-slate italic">No keywords configured. Only @mentions will trigger.</p>
              ) : (
                filterGroupKeywords.map((keyword) => (
                  <span
                    key={keyword}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-amber-500/20 border border-amber-500/30 rounded text-xs text-amber-300"
                  >
                    {keyword}
                    <button onClick={() => removeFilterItem('keyword', keyword)} className="text-amber-400 hover:text-red-400">×</button>
                  </span>
                ))
              )}
            </div>
          </div>

          {/* DM Auto Mode */}
          <div className="flex items-center gap-3 p-3 bg-tsushin-deep/50 rounded-lg">
            <input
              type="checkbox"
              id="dmAutoMode"
              checked={filterDmAutoMode}
              onChange={(e) => setFilterDmAutoMode(e.target.checked)}
              className="w-5 h-5 rounded border-tsushin-slate/30 bg-tsushin-deep text-teal-500"
            />
            <div>
              <label htmlFor="dmAutoMode" className="text-white font-medium flex items-center gap-2">
                DM Auto Mode
                <InfoTooltip title="Auto-Reply" text="When enabled, your AI agent automatically replies to every direct message it receives. When disabled, it only replies to messages from contacts you've marked as 'DM Trigger' in the Contacts page." position="right" />
              </label>
              <p className="text-xs text-tsushin-slate">
                Auto-reply to DMs from unknown senders (not in Contacts).
              </p>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-end gap-3 pt-4 border-t border-tsushin-slate/20">
            <button
              onClick={() => setShowFiltersModal(false)}
              className="px-4 py-2 bg-tsushin-deep border border-tsushin-slate/30 text-white rounded hover:bg-tsushin-slate/20"
            >
              Cancel
            </button>
            <button
              onClick={handleSaveFilters}
              disabled={saving}
              className="px-4 py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-medium rounded"
            >
              {saving ? 'Saving...' : 'Save Filters'}
            </button>
          </div>
        </div>
      </Modal>

      {/* Provider Instance Modal — rendered at root level to avoid z-index/overflow issues (BUG-109) */}
      <ProviderInstanceModal
        isOpen={instanceModalOpen}
        onClose={() => {
          setInstanceModalOpen(false)
          setEditingInstance(null)
          setSelectedVendor('')
          setInstanceMenuOpen(null)
        }}
        onSave={fetchProviderInstances}
        instance={editingInstance}
        defaultVendor={selectedVendor}
      />

      {/* Phase 10.1.1: Telegram Bot Creation Modal */}
      <TelegramBotModal
        isOpen={showTelegramModal}
        onClose={() => setShowTelegramModal(false)}
        onSubmit={handleCreateTelegramBot}
        saving={saving}
      />

      {/* v0.6.0: Slack Setup Modal */}
      <SlackSetupModal
        isOpen={showSlackSetupModal}
        onClose={() => setShowSlackSetupModal(false)}
        onSubmit={handleCreateSlackIntegration}
        saving={saving}
      />

      {/* v0.6.0: Discord Setup Modal */}
      <DiscordSetupModal
        isOpen={showDiscordSetupModal}
        onClose={() => setShowDiscordSetupModal(false)}
        onSubmit={handleCreateDiscordIntegration}
        saving={saving}
      />

      {/* v0.6.0: Webhook Setup Modal */}
      <WebhookSetupModal
        isOpen={showWebhookSetupModal}
        onClose={() => setShowWebhookSetupModal(false)}
        onSubmit={handleCreateWebhookIntegration}
        saving={webhookSaving}
        apiBase={typeof window !== 'undefined' ? window.location.origin : ''}
      />

      {/* v0.6.0: Vector Store Config Modal */}
      <VectorStoreConfigModal
        isOpen={showVectorStoreModal}
        onClose={() => { setShowVectorStoreModal(false); setEditingVectorStore(null) }}
        onSave={loadVectorStoreInstances}
        instance={editingVectorStore}
      />

      {/* MCP Server Creation Wizard */}
      <MCPServerWizard
        isOpen={mcpWizardServer !== null}
        onClose={() => setMcpWizardServer(null)}
        mcpServer={mcpWizardServer}
        onComplete={loadMcpServers}
      />

      {/* Vertex AI Configuration Modal */}
      {showVertexAiModal && (
        <Modal
          isOpen={showVertexAiModal}
          onClose={() => { setShowVertexAiModal(false); setVertexTestResult(null) }}
          title="Configure Vertex AI (Google Cloud)"
          size="lg"
        >
          <div className="space-y-5">
            {/* JSON Key Paste Option */}
            <div>
              <label className="block text-sm font-medium text-tsushin-fog mb-1.5">
                Paste Service Account JSON Key <span className="text-tsushin-slate">(auto-fills fields below)</span>
              </label>
              <textarea
                value={vertexJsonPaste}
                onChange={(e) => handleVertexJsonPaste(e.target.value)}
                className="input w-full h-24 font-mono text-xs"
                placeholder='{"type": "service_account", "project_id": "...", "client_email": "...", "private_key": "..."}'
              />
            </div>

            <div className="border-t border-tsushin-border/30 pt-4">
              <p className="text-xs text-tsushin-slate mb-4">Or fill in the fields manually:</p>
            </div>

            {/* Project ID */}
            <div>
              <label className="block text-sm font-medium text-tsushin-fog mb-1.5">GCP Project ID <span className="text-tsushin-vermilion">*</span></label>
              <input
                type="text"
                value={vertexProjectId}
                onChange={(e) => { setVertexProjectId(e.target.value); setVertexDirty(true) }}
                className="input w-full"
                placeholder="my-project-123"
              />
            </div>

            {/* Region */}
            <div>
              <label className="block text-sm font-medium text-tsushin-fog mb-1.5">Region <span className="text-tsushin-vermilion">*</span></label>
              <select
                value={vertexRegion}
                onChange={(e) => { setVertexRegion(e.target.value); setVertexDirty(true) }}
                className="input w-full"
              >
                <option value="us-east5">us-east5 (Columbus)</option>
                <option value="us-central1">us-central1 (Iowa)</option>
                <option value="us-east4">us-east4 (Virginia)</option>
                <option value="us-west1">us-west1 (Oregon)</option>
                <option value="europe-west1">europe-west1 (Belgium)</option>
                <option value="europe-west4">europe-west4 (Netherlands)</option>
                <option value="asia-northeast1">asia-northeast1 (Tokyo)</option>
                <option value="asia-southeast1">asia-southeast1 (Singapore)</option>
              </select>
              <p className="text-xs text-tsushin-slate mt-1">Claude models: us-east5, us-central1, europe-west1, europe-west4</p>
            </div>

            {/* Service Account Email */}
            <div>
              <label className="block text-sm font-medium text-tsushin-fog mb-1.5">Service Account Email <span className="text-tsushin-vermilion">*</span></label>
              <input
                type="text"
                value={vertexSaEmail}
                onChange={(e) => { setVertexSaEmail(e.target.value); setVertexDirty(true) }}
                className="input w-full"
                placeholder="my-sa@my-project.iam.gserviceaccount.com"
              />
            </div>

            {/* Private Key */}
            <div>
              <label className="block text-sm font-medium text-tsushin-fog mb-1.5">Private Key (PEM) <span className="text-tsushin-vermilion">*</span></label>
              <textarea
                value={vertexPrivateKey}
                onChange={(e) => { setVertexPrivateKey(e.target.value); setVertexDirty(true) }}
                className="input w-full h-32 font-mono text-xs"
                placeholder="Paste your PEM private key here"
              />
            </div>

            {/* Test Connection Result */}
            {vertexTestResult && (
              <div className={`p-3 rounded-lg border ${vertexTestResult.success ? 'bg-green-500/10 border-green-500/30 text-green-400' : 'bg-red-500/10 border-red-500/30 text-red-400'}`}>
                <p className="text-sm">{vertexTestResult.success ? '\u2713' : '\u2717'} {vertexTestResult.message}</p>
              </div>
            )}

            {/* BUG-513: The backend test endpoint only validates the saved
                tenant config. Block Test until the form is saved so users
                don't think the modal is honoring their unsaved edits. */}
            {vertexDirty && (
              <p className="text-xs text-tsushin-slate">
                Save configuration before testing — the Test Connection button
                validates the currently saved credentials, not the fields above.
              </p>
            )}

            {/* Actions */}
            <div className="flex gap-3 pt-2">
              <button
                onClick={handleTestVertexAi}
                disabled={vertexTesting || vertexSaving || vertexDirty || !vertexPrivateKey.trim()}
                className="btn-secondary flex-1"
              >
                {vertexTesting ? 'Testing...' : 'Test Connection'}
              </button>
              <button
                onClick={handleSaveVertexAi}
                disabled={vertexSaving || !vertexProjectId.trim() || !vertexSaEmail.trim() || !vertexPrivateKey.trim()}
                className="btn-primary flex-1"
              >
                {vertexSaving ? 'Saving...' : 'Save Configuration'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
