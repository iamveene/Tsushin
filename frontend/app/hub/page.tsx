'use client'

/**
 * Integration Hub - Consolidated Single Page
 *
 * Manages all integrations organized by category:
 * - AI Providers: Ollama, Gemini, OpenAI, Anthropic, Groq (coming soon)
 * - Communication: WhatsApp, Telegram, Discord, Slack, Email (coming soon)
 * - Productivity: Asana, Google Calendar, Notion (coming soon)
 * - Developer Tools: Shell, GitHub (coming soon)
 * - Tool APIs: Brave Search, OpenWeather, Amadeus
 * - Sandboxed Tools: Per-tenant toolbox containers
 */

import { useEffect, useState, useCallback } from 'react'
import { useAuth } from '@/contexts/AuthContext'
import { api, WhatsAppMCPInstance, MCPHealthStatus, QRCodeResponse, TelegramBotInstance, TelegramHealthStatus, Config } from '@/lib/client'
import Modal from '@/components/ui/Modal'
import TelegramBotModal from '@/components/TelegramBotModal'
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
  CloudSunIcon,
  BotIcon as BotIconSvg,
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
  type IconProps
} from '@/components/ui/icons'

type TabType = 'ai-providers' | 'communication' | 'productivity' | 'developer' | 'tool-apis' | 'sandboxed-tools'

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

// ============================================
// Service Definitions by Category
// ============================================

const AI_PROVIDERS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'gemini', label: 'Google Gemini', Icon: GeminiIcon, description: 'Google\'s multimodal AI', status: 'available' },
  { value: 'openai', label: 'OpenAI (GPT)', Icon: OpenAIIcon, description: 'GPT-4, ChatGPT models', status: 'available' },
  { value: 'anthropic', label: 'Anthropic Claude', Icon: AnthropicIcon, description: 'Claude 3.5, reasoning models', status: 'available' },
  { value: 'openrouter', label: 'OpenRouter', Icon: GlobeIcon, description: '100+ models via single API', status: 'available' },
  { value: 'groq', label: 'Groq', Icon: LightningIcon, description: 'Ultra-fast inference', status: 'coming_soon' },
  { value: 'elevenlabs', label: 'ElevenLabs', Icon: MicrophoneIcon, description: 'Voice AI & TTS synthesis', status: 'coming_soon' },
]

const COMMUNICATION_CHANNELS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'whatsapp', label: 'WhatsApp', Icon: MessageIconSvg, description: 'WhatsApp Business via MCP', status: 'available' },
  { value: 'gmail', label: 'Gmail', Icon: MailIcon, description: 'Google Gmail for email actions', status: 'available' },
  { value: 'telegram', label: 'Telegram', Icon: PlaneIcon, description: 'Telegram Bot API', status: 'available' },  // Phase 10.1.1: Now available!
  { value: 'discord', label: 'Discord', Icon: GamepadIcon, description: 'Discord bot integration', status: 'coming_soon' },
  { value: 'slack', label: 'Slack', Icon: BriefcaseIcon, description: 'Slack workspace integration', status: 'coming_soon' },
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
  { value: 'google_flights', label: 'SerpAPI (Google Services)', Icon: GlobeIcon, description: 'Unified SerpAPI key for Google Search, Google Flights, and other Google services', status: 'available' },
  { value: 'openweather', label: 'OpenWeather', Icon: CloudSunIcon, description: 'Weather data API', status: 'available' },
  { value: 'amadeus', label: 'Amadeus', Icon: PlaneIcon, description: 'Flight search API', status: 'available' },
]

const NOTIFICATION_SERVICES: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = []

export default function HubPage() {
  const { isGlobalAdmin, hasPermission } = useAuth()
  const [activeTab, setActiveTab] = useState<TabType>('ai-providers')

  // API Keys state
  const [apiKeys, setApiKeys] = useState<APIKey[]>([])
  const [ollamaHealth, setOllamaHealth] = useState<OllamaHealth | null>(null)
  const [kokoroHealth, setKokoroHealth] = useState<KokoroHealth | null>(null)
  const [hubIntegrations, setHubIntegrations] = useState<HubIntegration[]>([])

  // MCP Instances state
  const [mcpInstances, setMcpInstances] = useState<WhatsAppMCPInstance[]>([])
  const [healthStatuses, setHealthStatuses] = useState<Record<number, MCPHealthStatus>>({})

  // Phase 10.1.1: Telegram Bot Integration
  const [telegramInstances, setTelegramInstances] = useState<TelegramBotInstance[]>([])
  const [telegramHealthStatuses, setTelegramHealthStatuses] = useState<Record<number, TelegramHealthStatus>>({})
  const [showTelegramModal, setShowTelegramModal] = useState(false)

  // Toolbox Container state
  const [toolboxStatus, setToolboxStatus] = useState<ToolboxStatus | null>(null)

  // UI state
  const [loading, setLoading] = useState(true)
  const [showApiKeyModal, setShowApiKeyModal] = useState(false)
  const [showMcpCreateModal, setShowMcpCreateModal] = useState(false)
  const [showQRModal, setShowQRModal] = useState(false)
  const [showFiltersModal, setShowFiltersModal] = useState(false)  // Phase 17: Instance filters modal
  const [editingKey, setEditingKey] = useState<APIKey | null>(null)
  const [selectedMcpInstance, setSelectedMcpInstance] = useState<WhatsAppMCPInstance | null>(null)
  const [qrCode, setQRCode] = useState<string | null>(null)
  // QR Modal polling state for auto-refresh and auto-close
  const [qrPollingActive, setQrPollingActive] = useState(false)
  const [qrLastRefresh, setQrLastRefresh] = useState<Date | null>(null)
  const [qrAuthSuccess, setQrAuthSuccess] = useState(false)
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

  // Helper function to get authentication headers
  const getAuthHeaders = () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }

  useEffect(() => {
    loadAllData()
    const interval = setInterval(() => {
      loadHubIntegrations(true)
      fetchToolboxStatus()
      if (activeTab === 'communication') {
        loadMcpInstances()
        loadTelegramInstances()  // Phase 10.1.1
      }
    }, 10000)
    return () => clearInterval(interval)
  }, [activeTab])

  useEffect(() => {
    const handleRefresh = () => {
      loadAllData()
    }
    window.addEventListener('tsushin:refresh', handleRefresh)
    return () => window.removeEventListener('tsushin:refresh', handleRefresh)
  }, [])

  // QR Code Modal polling - auto-refresh QR and auto-close on authentication
  useEffect(() => {
    // Only poll when QR modal is open and we have a selected instance
    if (!showQRModal || !selectedMcpInstance) {
      setQrPollingActive(false)
      return
    }

    setQrPollingActive(true)
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
        setQrAuthSuccess(false)
        setQrLastRefresh(null)

        // Refresh instances list to update status badges
        loadMcpInstances()

        setSuccessMessage('WhatsApp connected successfully!')
        setTimeout(() => setSuccessMessage(null), 3000)
      }, 1500) // 1.5s to show success state
    }

    const checkAuthStatus = async () => {
      if (isCancelled || !selectedMcpInstance) return

      try {
        const health = await api.getMCPHealth(selectedMcpInstance.id)
        // Only consider authenticated if ALL conditions are true:
        // 1. authenticated=true (device session exists in DB)
        // 2. connected=true (WebSocket is connected to WhatsApp)
        // 3. needs_reauth=false (session is valid, user didn't logout from phone)
        const isFullyAuthenticated = health.authenticated &&
                                      health.connected &&
                                      !health.needs_reauth
        if (isFullyAuthenticated) {
          handleAuthSuccess()
          return true
        }
      } catch (err) {
        // Ignore auth check errors - transient failures during container startup
        console.debug('QR auth check error (will retry):', err)
      }
      return false
    }

    const refreshQRCode = async () => {
      if (isCancelled || !selectedMcpInstance) return

      try {
        // First check if authenticated
        const isAuth = await checkAuthStatus()
        if (isAuth) return // Already handled auth success

        // Refresh QR code
        const qrResponse = await api.getMCPQRCode(selectedMcpInstance.id)

        if (isCancelled) return

        if (qrResponse.qr_code) {
          setQRCode(qrResponse.qr_code)
          setQrLastRefresh(new Date())
        }
        // REMOVED: Don't trigger auth success based on QR endpoint message
        // The health check polling (checkAuthStatus) is the authoritative source
        // This prevents false positives when QR endpoint says "authenticated"
        // but needs_reauth is actually true
      } catch (err) {
        // Log but don't show error - transient failures are expected during container startup
        console.warn('QR refresh error (will retry):', err)
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
  }, [showQRModal, selectedMcpInstance])

  const loadAllData = async () => {
    setLoading(true)
    try {
      await Promise.all([
        fetchAPIKeys(),
        fetchOllamaHealth(),
        fetchKokoroHealth(),
        loadHubIntegrations(),
        loadMcpInstances(),
        loadTelegramInstances(),  // Phase 10.1.1
        fetchToolboxStatus(),
        loadGoogleCredentials(),
        loadSystemConfig()
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/api-keys`, {
        headers: getAuthHeaders()
      })
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

  const fetchOllamaHealth = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/ollama/health`)
      if (response.ok) {
        const data = await response.json()
        setOllamaHealth(data)
      } else {
        setOllamaHealth({
          status: 'offline',
          base_url: 'http://localhost:11434',
          available: false,
          error: 'Health check failed'
        })
      }
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/tts-providers/kokoro/status`, {
        headers: getAuthHeaders()
      })
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

  const fetchToolboxStatus = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/toolbox/status`, {
        headers: getAuthHeaders()
      })
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const url = refreshHealth
        ? `${apiUrl}/api/hub/integrations?refresh_health=true`
        : `${apiUrl}/api/hub/integrations`
      const response = await fetch(url, {
        headers: getAuthHeaders()
      })
      if (response.ok) {
        const data = await response.json()
        setHubIntegrations(data)
      }
    } catch (error) {
      console.error('Failed to fetch Hub integrations:', error)
    }
  }

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

  const saveAPIKey = async () => {
    if (!modalData.service || !modalData.api_key) {
      alert('Please select a service and provide the API key')
      return
    }

    setSaving(true)
    setError(null)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/api-keys`, {
        method: 'POST',
        headers: getAuthHeaders(),
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

  const deleteAPIKey = async (service: string) => {
    if (!confirm(`Remove the ${service} integration?`)) return

    setError(null)
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/api-keys/${service}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('Failed to delete API key:', response.status, errorText)
        throw new Error(`Failed to remove API key: ${response.status}`)
      }

      await fetchAPIKeys()
      setSuccessMessage('API key removed')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error: any) {
      console.error('Error deleting API key:', error)
      setError(error.message || 'Failed to remove API key')
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
    } catch (err: any) {
      setError(err.message || `Failed to ${action} instance`)
    }
  }

  const handleShowQR = async (instance: WhatsAppMCPInstance) => {
    setSelectedMcpInstance(instance)
    setShowQRModal(true)
    setQRCode(null)
    setQrAuthSuccess(false)
    setQrLastRefresh(null)

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
          setQrAuthSuccess(false)
          setQrLastRefresh(null)
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
      }
      // Don't show error if QR not available - polling will pick it up
      // The loading state is shown by default when qrCode is null
    } catch (err: any) {
      setError(err.message || 'Failed to fetch QR code')
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

  // Asana handlers
  const handleAsanaConnect = async () => {
    const workspaceName = prompt('Enter your Asana workspace name:', 'My Workspace')
    if (!workspaceName?.trim()) return

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/hub/asana/oauth/authorize`, {
        method: 'POST',
        headers: getAuthHeaders(),
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
        alert('Asana OAuth not configured. Required: ASANA_ENCRYPTION_KEY in backend/.env')
      } else {
        alert(`Failed to connect: ${err.message}`)
      }
    }
  }

  const handleAsanaDisconnect = async (integrationId: number) => {
    if (!confirm('Disconnect Asana integration?')) return

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      await fetch(`${apiUrl}/api/hub/asana/oauth/disconnect/${integrationId}`, {
        method: 'POST',
        headers: getAuthHeaders()
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/hub/google/credentials`, {
        headers: getAuthHeaders()
      })
      if (response.ok) {
        const data = await response.json()
        setGoogleCredentials(data)
      } else {
        setGoogleCredentials(null)
      }
    } catch (error) {
      console.error('Failed to load Google credentials:', error)
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const params = new URLSearchParams({ redirect_url: '/hub' })
      const response = await fetch(`${apiUrl}/api/hub/google/calendar/oauth/authorize?${params}`, {
        method: 'POST',
        headers: getAuthHeaders()
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      await fetch(`${apiUrl}/api/hub/google/calendar/oauth/disconnect/${integrationId}`, {
        method: 'POST',
        headers: getAuthHeaders()
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const params = new URLSearchParams({ redirect_url: '/hub' })
      const response = await fetch(`${apiUrl}/api/hub/google/gmail/oauth/authorize?${params}`, {
        method: 'POST',
        headers: getAuthHeaders()
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      await fetch(`${apiUrl}/api/hub/google/gmail/oauth/disconnect/${integrationId}`, {
        method: 'POST',
        headers: getAuthHeaders()
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
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const params = new URLSearchParams({ redirect_url: '/hub' })
      const response = await fetch(`${apiUrl}/api/hub/google/reauthorize/${integrationId}?${params}`, {
        method: 'POST',
        headers: getAuthHeaders()
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

  // Render integration card based on status
  const renderIntegrationCard = (
    item: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string },
    type: 'ai' | 'tool' | 'app'
  ) => {
    const apiKey = getApiKeyForService(item.value)
    const isComingSoon = item.status === 'coming_soon'
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
            <h3 className="font-semibold text-white">{item.label}</h3>
          </div>
          {isComingSoon ? (
            <span className="px-2 py-1 text-xs font-medium rounded-full bg-gray-600/30 text-gray-400 border border-gray-600/50">
              Coming Soon
            </span>
          ) : (
            <span className={apiKey?.is_active ? 'badge badge-success' : 'badge badge-neutral'}>
              {apiKey ? (apiKey.is_active ? 'Active' : 'Inactive') : 'Not configured'}
            </span>
          )}
        </div>
        <p className="text-xs text-tsushin-slate mb-4">{item.description}</p>
        {!isComingSoon && apiKey && (
          <div className="text-sm text-tsushin-slate mb-4">
            <p className="font-mono text-xs text-tsushin-accent">{apiKey.api_key_preview}</p>
          </div>
        )}
        {!isComingSoon && (
          <div className="flex gap-2">
            {apiKey ? (
              <>
                <button
                  onClick={() => openEditApiKeyModal(apiKey)}
                  className="flex-1 btn-ghost py-2 text-sm"
                >
                  Edit
                </button>
                <button
                  onClick={() => deleteAPIKey(apiKey.service)}
                  className="flex-1 py-2 text-sm rounded-lg font-medium bg-tsushin-vermilion/10 text-tsushin-vermilion border border-tsushin-vermilion/30 hover:bg-tsushin-vermilion/20 transition-all"
                >
                  Remove
                </button>
              </>
            ) : (
              <button
                onClick={() => openAddApiKeyModal(item.value)}
                className="w-full btn-secondary py-2 text-sm"
              >
                Configure
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
    { key: 'sandboxed-tools', label: 'Sandboxed Tools', Icon: BoxIcon, color: 'text-pink-400', iconBg: 'bg-pink-400/10' },
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

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
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

        {/* Tabs */}
        <div className="glass-card rounded-xl overflow-hidden">
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
                    <p className="text-sm text-tsushin-slate">Configure API keys for AI models (LLMs)</p>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 animate-stagger">
                  {/* Ollama Card (Special - Local) */}
                  <div className="card p-5 hover-glow group">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                          <BotIconSvg size={20} className="text-purple-400" />
                        </div>
                        <h3 className="font-semibold text-white">Ollama (Local)</h3>
                      </div>
                      <span className={ollamaHealth?.available ? 'badge badge-success' : 'badge badge-neutral'}>
                        {ollamaHealth?.available ? 'Online' : 'Offline'}
                      </span>
                    </div>
                    <p className="text-xs text-tsushin-slate mb-3">Run LLMs locally - no API key needed</p>
                    <div className="text-sm text-tsushin-slate">
                      {ollamaHealth?.available ? (
                        <>
                          <p className="text-xs mb-2">{ollamaHealth.models_count || 0} models available</p>
                          <p className="text-xs font-mono text-tsushin-accent mb-2">{ollamaHealth.base_url}</p>
                          {ollamaHealth.models?.slice(0, 3).map((m, i) => (
                            <p key={i} className="text-xs text-tsushin-muted">• {m.name}</p>
                          ))}
                        </>
                      ) : (
                        <>
                          <p className="text-xs text-tsushin-vermilion mb-2">{ollamaHealth?.error || 'Not running'}</p>
                          <p className="text-xs">Start with: <code className="bg-tsushin-deep px-1.5 py-0.5 rounded font-mono text-tsushin-accent">ollama serve</code></p>
                        </>
                      )}
                    </div>
                    <button
                      onClick={fetchOllamaHealth}
                      className="w-full mt-4 btn-secondary py-2 text-sm"
                    >
                      Refresh Status
                    </button>
                  </div>

                  {/* Kokoro TTS Card (Special - Free Local TTS) */}
                  <div className="card p-5 hover-glow group border-green-700/30">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-green-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                          <MicrophoneIcon size={20} className="text-green-400" />
                        </div>
                        <h3 className="font-semibold text-white">Kokoro TTS (Free)</h3>
                      </div>
                      <span className={kokoroHealth?.available ? 'badge badge-success' : 'badge badge-neutral'}>
                        {kokoroHealth?.available ? 'Online' : 'Offline'}
                      </span>
                    </div>
                    <p className="text-xs text-tsushin-slate mb-3">Free text-to-speech with PTBR support</p>
                    <div className="text-sm text-tsushin-slate">
                      {kokoroHealth?.available ? (
                        <>
                          <p className="text-xs mb-2">{kokoroHealth.details?.voices || 15} voices available</p>
                          <p className="text-xs font-mono text-tsushin-accent mb-2">{kokoroHealth.details?.service_url || 'http://localhost:8880'}</p>
                          {kokoroHealth.latency_ms && (
                            <p className="text-xs text-green-400">Latency: {kokoroHealth.latency_ms}ms</p>
                          )}
                          <p className="text-xs text-green-400 mt-1 flex items-center gap-1"><CreditCardIcon size={12} className="text-green-400" /> 100% FREE - No API costs!</p>
                        </>
                      ) : (
                        <>
                          <p className="text-xs text-tsushin-vermilion mb-2">{kokoroHealth?.message || 'Service not running'}</p>
                          <p className="text-xs">Start with: <code className="bg-tsushin-deep px-1.5 py-0.5 rounded font-mono text-tsushin-accent">docker compose --profile tts up -d</code></p>
                        </>
                      )}
                    </div>
                    <button
                      onClick={fetchKokoroHealth}
                      className="w-full mt-4 btn-secondary py-2 text-sm"
                    >
                      Refresh Status
                    </button>
                  </div>

                  {/* Other AI Providers */}
                  {AI_PROVIDERS.map(provider => renderIntegrationCard(provider, 'ai'))}
                </div>

                {/* Info Box */}
                <div className="bg-purple-500/5 border border-purple-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-purple-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-purple-300" /> AI Providers
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    Configure API keys for cloud AI providers, use Ollama for free local LLM inference, or Kokoro for free text-to-speech.
                    Groq offers ultra-fast inference, and ElevenLabs provides premium voice AI synthesis - both coming soon!
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
                    onClick={() => setShowMcpCreateModal(true)}
                    className="btn-primary"
                  >
                    + Create WhatsApp Instance
                  </button>
                </div>

                {/* WhatsApp Instances */}
                <div className="space-y-4">
                  <h3 className="text-md font-semibold text-white flex items-center gap-2">
                    <MessageIconSvg size={18} /> WhatsApp Instances
                  </h3>

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

                  {mcpInstances.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <SmartphoneIcon size={36} className="text-gray-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No WhatsApp Instances</h3>
                      <p className="text-tsushin-slate mb-4">Create an instance to connect WhatsApp</p>
                      <button
                        onClick={() => setShowMcpCreateModal(true)}
                        className="btn-primary"
                      >
                        Create Instance
                      </button>
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {mcpInstances.map(instance => {
                        const health = healthStatuses[instance.id]
                        return (
                          <div key={instance.id} className="card p-4 hover-glow">
                            <div className="flex items-start justify-between mb-3">
                              <div>
                                <h3 className="font-semibold text-white">{instance.phone_number}</h3>
                                <p className="text-xs text-tsushin-slate">Port: {instance.mcp_port}</p>
                              </div>
                              <div className="flex flex-col gap-1 items-end">
                                <span className={getStatusBadge(instance.status)}>{instance.status}</span>
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${instance.instance_type === 'agent'
                                    ? 'bg-green-600/20 text-green-400 border border-green-600/50'
                                    : 'bg-orange-600/20 text-orange-400 border border-orange-600/50'
                                  }`}>
                                  {instance.instance_type === 'agent' ? <span className="flex items-center gap-1"><BotIconSvg size={12} /> Agent</span> : <span className="flex items-center gap-1"><BeakerIcon size={12} /> Tester</span>}
                                </span>
                                <span className={`px-2 py-1 text-xs font-medium rounded-full ${health?.authenticated
                                    ? 'bg-green-600/20 text-green-400 border border-green-600/50'
                                    : 'bg-yellow-600/20 text-yellow-400 border border-yellow-600/50'
                                  }`}>
                                  {health?.authenticated ? 'Authenticated' : 'Not Auth'}
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

                {/* Coming Soon Channels */}
                <div className="space-y-4">
                  <h3 className="text-md font-semibold text-white flex items-center gap-2">
                    <RocketIcon size={18} /> More Channels
                  </h3>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    {COMMUNICATION_CHANNELS.filter(c => c.value !== 'whatsapp' && c.value !== 'gmail' && c.value !== 'telegram').map(channel => {
                      const ChannelIcon = channel.Icon
                      return (
                        <div key={channel.value} className="card p-4 opacity-60">
                          <div className="flex items-center gap-3 mb-2">
                            <div className="w-10 h-10 rounded-xl bg-gray-700/50 flex items-center justify-center text-gray-400">
                              <ChannelIcon size={20} />
                            </div>
                          <div>
                            <h4 className="font-semibold text-white">{channel.label}</h4>
                            <span className="text-xs text-gray-500">Coming Soon</span>
                          </div>
                        </div>
                        <p className="text-xs text-tsushin-slate">{channel.description}</p>
                      </div>
                      )
                    })}
                  </div>
                </div>

                {/* Notifications */}
                <div className="space-y-4">
                  <h3 className="text-md font-semibold text-white flex items-center gap-2">
                    <BellIcon size={18} /> Push Notifications
                  </h3>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    {NOTIFICATION_SERVICES.map(service => {
                      const ServiceIcon = service.Icon
                      return (
                        <div key={service.value} className="card p-4 opacity-60">
                          <div className="flex items-center gap-3 mb-2">
                            <div className="w-10 h-10 rounded-xl bg-gray-700/50 flex items-center justify-center text-gray-400">
                              <ServiceIcon size={20} />
                            </div>
                          <div>
                            <h4 className="font-semibold text-white">{service.label}</h4>
                            <span className="text-xs text-gray-500">Coming Soon</span>
                          </div>
                        </div>
                        <p className="text-xs text-tsushin-slate">{service.description}</p>
                      </div>
                      )
                    })}
                  </div>
                </div>
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
                  <p className="text-sm text-tsushin-slate">Connect development and DevOps platforms</p>
                </div>

                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {/* Shell Command Center - Featured Card */}
                  <div
                    className="card p-5 hover-glow group border-teal-700/30 col-span-full lg:col-span-2 cursor-pointer"
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
                    The Shell Command Center is now available for remote command execution with security approval workflows.
                    GitHub integration is coming soon, enabling agents to create issues, summarize PRs, and respond to repository events.
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
                    Tools include: Web Search (Brave/Google), Weather (OpenWeather), Flight Search (Amadeus/Google), and Web Scraping.
                  </p>
                </div>
              </div>
            )}

            {/* ==================== CUSTOM TOOLS TAB ==================== */}
            {activeTab === 'sandboxed-tools' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">Sandboxed Tools</h2>
                    <p className="text-sm text-tsushin-slate">Manage and create command-based tools for agents</p>
                  </div>
                  <button
                    onClick={() => window.location.href = '/hub/sandboxed-tools'}
                    className="btn-primary"
                  >
                    Manage Tools →
                  </button>
                </div>

                {/* Toolbox Status Card */}
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  <div className="card p-5 hover-glow group col-span-full lg:col-span-2">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-3">
                        <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                          <BoxIconSvg size={24} className="text-purple-400" />
                        </div>
                        <div>
                          <h3 className="font-semibold text-white text-lg">Toolbox Container</h3>
                          <p className="text-sm text-tsushin-slate">Per-tenant isolated execution environment</p>
                        </div>
                      </div>
                      {getToolboxBadge()}
                    </div>
                    <div className="text-sm text-tsushin-slate mb-4">
                      <p className="mb-2">The toolbox container provides a secure, isolated environment for running sandboxed tools with pre-installed security scanners and utilities.</p>
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
                      onClick={() => window.location.href = '/hub/sandboxed-tools'}
                      className="w-full btn-secondary py-2 text-sm"
                    >
                      Open Toolbox Manager
                    </button>
                  </div>

                  {/* Quick Stats Card */}
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
                </div>

                {/* Info Box */}
                <div className="bg-purple-500/5 border border-purple-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-purple-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-purple-300" /> Sandboxed Tools Feature
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    Sandboxed Tools allow you to create command-based tools that agents can execute in a secure container environment.
                    Tools can run network scans, vulnerability assessments, web crawling, and custom scripts.
                    Each tenant gets an isolated container with the ability to install additional packages.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

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
          setQRCode(null)
          setQrAuthSuccess(false)
          setQrLastRefresh(null)
        }}
        title={`QR Code - ${selectedMcpInstance?.phone_number}`}
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
          ) : (
            <div className="py-8">
              <div className="w-16 h-16 border-4 border-tsushin-indigo border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
              <p className="text-gray-400">Loading QR code...</p>
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
            <label className="block text-sm font-medium text-white mb-2">
              Group Filters
            </label>
            <p className="text-xs text-tsushin-slate mb-2">
              WhatsApp group names to monitor. Messages from other groups will be ignored.
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={filterInputGroup}
                onChange={(e) => setFilterInputGroup(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addFilterItem('group')}
                placeholder="Enter group name"
                className="flex-1 bg-tsushin-deep border border-tsushin-slate/30 rounded px-3 py-2 text-white text-sm"
              />
              <button
                onClick={() => addFilterItem('group')}
                className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded text-sm"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {filterGroupFilters.length === 0 ? (
                <p className="text-xs text-tsushin-slate italic">No groups configured. All groups will be monitored.</p>
              ) : (
                filterGroupFilters.map((filter) => (
                  <span
                    key={filter}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-teal-500/20 border border-teal-500/30 rounded text-xs text-teal-300"
                  >
                    {filter}
                    <button onClick={() => removeFilterItem('group', filter)} className="text-teal-400 hover:text-red-400">×</button>
                  </span>
                ))
              )}
            </div>
          </div>

          {/* Number Filters */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Number Filters (DM Allowlist)
            </label>
            <p className="text-xs text-tsushin-slate mb-2">
              Phone numbers allowed to DM the agent. Include country code.
            </p>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={filterInputNumber}
                onChange={(e) => setFilterInputNumber(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addFilterItem('number')}
                placeholder="+5500000000001"
                className="flex-1 bg-tsushin-deep border border-tsushin-slate/30 rounded px-3 py-2 text-white text-sm"
              />
              <button
                onClick={() => addFilterItem('number')}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded text-sm"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {filterNumberFilters.length === 0 ? (
                <p className="text-xs text-tsushin-slate italic">No numbers configured.</p>
              ) : (
                filterNumberFilters.map((filter) => (
                  <span
                    key={filter}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-purple-500/20 border border-purple-500/30 rounded text-xs text-purple-300"
                  >
                    {filter}
                    <button onClick={() => removeFilterItem('number', filter)} className="text-purple-400 hover:text-red-400">×</button>
                  </span>
                ))
              )}
            </div>
          </div>

          {/* Group Keywords */}
          <div>
            <label className="block text-sm font-medium text-white mb-2">
              Group Keywords
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
              <label htmlFor="dmAutoMode" className="text-white font-medium">
                DM Auto Mode
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

      {/* Phase 10.1.1: Telegram Bot Creation Modal */}
      <TelegramBotModal
        isOpen={showTelegramModal}
        onClose={() => setShowTelegramModal(false)}
        onSubmit={handleCreateTelegramBot}
        saving={saving}
      />
    </div>
  )
}
