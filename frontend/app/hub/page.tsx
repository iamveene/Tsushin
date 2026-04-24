'use client'

/**
 * Integration Hub - Consolidated Single Page
 *
 * Manages all integrations organized by category:
 * - AI Providers: Ollama, Gemini, OpenAI, Anthropic, Groq, Grok, DeepSeek, Vertex AI, ElevenLabs
 * - Communication: WhatsApp, Telegram, Discord, Slack, Email Triggers, Webhooks
 * - Productivity: Asana, Google Calendar
 * - Developer Tools: Shell, Sandboxed Tools
 * - Tool APIs: Brave Search, Tavily, Amadeus
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import dynamic from 'next/dynamic'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

const AddIntegrationWizard = dynamic(
  () => import('@/components/integrations/AddIntegrationWizard'),
  { ssr: false },
)
// Guided wizards that replace the Hub's fixed-card / scattered-CTA pattern
// with a single "+ Add ..." launcher per tab. Both are thin dispatchers —
// once the user picks a service/channel, they hand off to the existing
// per-service sub-wizard (SlackSetupWizard, GmailSetupWizard, etc.). See
// frontend/components/integrations/ProductivityWizard.tsx + ChannelsWizard.tsx.
const ProductivityWizard = dynamic(
  () => import('@/components/integrations/ProductivityWizard'),
  { ssr: false },
)
const ChannelsWizard = dynamic(
  () => import('@/components/integrations/ChannelsWizard'),
  { ssr: false },
)
const TriggerWizard = dynamic(
  () => import('@/components/triggers/TriggerWizard'),
  { ssr: false },
)
const EmailTriggerWizard = dynamic(
  () => import('@/components/triggers/EmailTriggerWizard'),
  { ssr: false },
)
const TriggerSetupModal = dynamic(
  () => import('@/components/triggers/TriggerSetupModal'),
  { ssr: false },
)
import type { ChannelId } from '@/components/integrations/ChannelsWizard'
import type { TriggerId } from '@/components/triggers/TriggerWizard'
import { useToast } from '@/contexts/ToastContext'
import { api, authenticatedFetch, WhatsAppMCPInstance, MCPHealthStatus, QRCodeResponse, TelegramBotInstance, TelegramHealthStatus, SlackIntegration, SlackIntegrationCreate, DiscordIntegration, DiscordIntegrationCreate, WebhookIntegration, WebhookIntegrationCreate, Config, ProviderInstance, VectorStoreInstance, TesterMCPStatus, PublicIngressInfo, TTSInstance, SearxngInstance, EmailTrigger, JiraTrigger, ScheduleTrigger, GitHubTrigger } from '@/lib/client'
import { OLLAMA_CURATED_MODEL_IDS } from '@/lib/ollama-curated-models'
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
import WebhookSecretRevealModal from '@/components/WebhookSecretRevealModal'
import WebhookEditModal from '@/components/WebhookEditModal'
import TriggerBreadthCards from '@/components/triggers/TriggerBreadthCards'
import WhatsAppCreateModeSelector from '@/components/hub/WhatsAppCreateModeSelector'
import ChannelRoutingRulesPanel from '@/components/hub/ChannelRoutingRulesPanel'
import ProviderInstanceModal from '@/components/providers/ProviderInstanceModal'
import ManagedContainerPanel from '@/components/hub/ManagedContainerPanel'
import VectorStoreCard from '@/components/vector-stores/VectorStoreCard'
import VectorStoreConfigModal from '@/components/vector-stores/VectorStoreConfigModal'
import MCPServerWizard from '@/components/mcp/MCPServerWizard'
import OllamaSetupWizard from '@/components/ollama/OllamaSetupWizard'
import KokoroSetupWizard from '@/components/tts/KokoroSetupWizard'
import TypeaheadChipInput, { TypeaheadSuggestion } from '@/components/hub/TypeaheadChipInput'
import InfoTooltip from '@/components/ui/InfoTooltip'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'
import { useGoogleWizard, useGoogleWizardComplete } from '@/contexts/GoogleWizardContext'
import { useProviderWizard, useProviderWizardComplete } from '@/contexts/ProviderWizardContext'
import IntegrationSummary from '@/components/hub/IntegrationSummary'
import {
  GeminiIcon,
  OpenAIIcon,
  AnthropicIcon,
  GlobeIcon,
  LightningIcon,
  MicrophoneIcon,
  MessageIcon as MessageIconSvg,
  PlaneIcon,
  GamepadIcon,
  BriefcaseIcon,
  CheckCircleIcon,
  CalendarIcon,
  TerminalIcon as TerminalIconSvg,
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
  ChevronRightIcon,
  type IconProps
} from '@/components/ui/icons'
// ToggleSwitch — formerly used for the Ollama panel-level Enable toggle;
// now encapsulated inside ManagedContainerPanel.

type BreadthTriggerId = Extract<TriggerId, 'jira' | 'schedule' | 'github'>
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
  { value: 'telegram', label: 'Telegram', Icon: PlaneIcon, description: 'Telegram Bot API', status: 'available' },  // Phase 10.1.1: Now available!
  { value: 'slack', label: 'Slack', Icon: SlackIcon, description: 'Slack workspace integration', status: 'available' },
  { value: 'discord', label: 'Discord', Icon: DiscordIcon, description: 'Discord bot integration', status: 'available' },
  { value: 'webhook', label: 'Webhook', Icon: WebhookIcon, description: 'HTTP webhook integration (bidirectional)', status: 'available' },
]

const PRODUCTIVITY_APPS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'asana', label: 'Asana', Icon: CheckCircleIcon, description: 'Task & project management', status: 'available' },
  { value: 'google_calendar', label: 'Google Calendar', Icon: CalendarIcon, description: 'Calendar & scheduling', status: 'available' },
]

const DEVELOPER_TOOLS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'shell', label: 'Shell Command Center', Icon: TerminalIconSvg, description: 'Remote shell execution & beacon management', status: 'available' },
]

const TOOL_APIS: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = [
  { value: 'brave_search', label: 'Brave Search', Icon: SearchIcon, description: 'Privacy-focused web search API', status: 'available' },
  { value: 'searxng', label: 'SearXNG', Icon: GlobeIcon, description: 'Self-hosted open-source metasearch', status: 'available' },
  { value: 'tavily', label: 'Tavily', Icon: GlobeIcon, description: 'AI-focused web search API', status: 'available' },
  { value: 'google_flights', label: 'SerpAPI (Google Services)', Icon: GlobeIcon, description: 'Unified SerpAPI key for Google Search, Google Flights, and other Google services', status: 'available' },
  { value: 'amadeus', label: 'Amadeus', Icon: PlaneIcon, description: 'Flight search API', status: 'available' },
]

const NOTIFICATION_SERVICES: { value: string; label: string; Icon: React.FC<IconProps>; description: string; status: string }[] = []

// v0.6.x: Curated list of Ollama models for per-tenant auto-provisioning.
// The curated IDs live in lib/ollama-curated-models (shared with
// OllamaSetupWizard); 'custom' is appended here because this panel supports
// pulling arbitrary tags, whereas the wizard offers it via a separate flow.
const CURATED_OLLAMA_MODELS = [...OLLAMA_CURATED_MODEL_IDS, 'custom']

export default function HubPage() {
  const toast = useToast()
  const { isGlobalAdmin, hasPermission } = useAuth()
  const [oauthPopupHandoff, setOauthPopupHandoff] = useState(false)
  // BUG-610 FIX: Gate every Hub mutation control (connect, disconnect,
  // delete, edit, add) on ``hub.write``. Tenants with only ``hub.read``
  // should see the catalog of configured integrations but must not be
  // offered action buttons that the backend would 403 on anyway.
  const canWriteHub = hasPermission('hub.write')
  // BUG-322: Use forceOpenWizard so the wizard always opens when explicitly triggered from Hub,
  // even if the user previously dismissed it.
  const { forceOpenWizard: openWhatsAppWizard } = useWhatsAppWizard()
  const { openWizard: openGoogleWizard } = useGoogleWizard()
  const { openWizard: openProviderWizard } = useProviderWizard()
  // loadHubIntegrations is defined later in the component; keep a ref so we can
  // invoke the latest version from the wizard-complete callback without
  // dancing around declaration order.
  const loadHubIntegrationsRef = useRef<((refreshHealth?: boolean) => Promise<void>) | null>(null)
  const onGoogleWizardComplete = useCallback(() => {
    loadHubIntegrationsRef.current?.()
  }, [])
  useGoogleWizardComplete('gmail', onGoogleWizardComplete)
  useGoogleWizardComplete('calendar', onGoogleWizardComplete)
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState<TabType>(() => {
    if (typeof window === 'undefined') return 'ai-providers'
    const validTabs: TabType[] = ['ai-providers', 'communication', 'productivity', 'developer', 'tool-apis', 'mcp-servers', 'vector-stores']
    const requested = new URLSearchParams(window.location.search).get('tab') as TabType | null
    return requested && validTabs.includes(requested) ? requested : 'ai-providers'
  })
  const [showSearchWizard, setShowSearchWizard] = useState(false)
  const [addIntegrationInitialProvider, setAddIntegrationInitialProvider] = useState<string | undefined>(undefined)

  // OAuth popup handoff. The Google OAuth callback redirects the popup window to
  // /hub?integration=<gmail|calendar>&status=success&id=<n>. Keep this in an
  // effect so the component's hook order remains stable.
  useEffect(() => {
    if (typeof window === 'undefined' || !window.opener || window.opener === window) {
      return
    }

    try {
      const params = new URLSearchParams(window.location.search)
      const status = params.get('status')
      const integration = params.get('integration') || params.get('type')
      if (status !== 'success' || (integration !== 'gmail' && integration !== 'calendar')) {
        return
      }

      const id = params.get('id')
      setOauthPopupHandoff(true)
      try {
        window.opener.postMessage({
          source: 'tsushin-google-oauth',
          integration,
          integration_id: id ? Number(id) : null,
          status,
        }, window.location.origin)
      } catch {}
      window.close()
    } catch {
      // Fall through to normal Hub render on any unexpected error.
    }
  }, [])

  // Sync activeTab with ?tab= query param when it changes (e.g., via soft nav back from sub-pages)
  useEffect(() => {
    const validTabs: TabType[] = ['ai-providers', 'communication', 'productivity', 'developer', 'tool-apis', 'mcp-servers', 'vector-stores']
    const requested = searchParams?.get('tab') as TabType | null
    if (requested && validTabs.includes(requested)) {
      setActiveTab(requested)
    }
  }, [searchParams])

  // Advanced-mode fallback from ProviderWizard → opens legacy ProviderInstanceModal
  // with the vendor pre-selected.
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<{ vendor?: string }>).detail
      setEditingInstance(null)
      setSelectedVendor(detail?.vendor || '')
      setInstanceModalOpen(true)
    }
    window.addEventListener('tsushin:open-provider-advanced-modal', handler)
    return () => window.removeEventListener('tsushin:open-provider-advanced-modal', handler)
  }, [])

  // Refetch provider instances / TTS instances when the new ProviderWizard completes.
  useProviderWizardComplete(() => {
    fetchProviderInstances()
    refreshKokoroInstances().catch(() => {})
    fetchAPIKeys()
  })

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
  const [emailTriggers, setEmailTriggers] = useState<EmailTrigger[]>([])
  const [jiraTriggers, setJiraTriggers] = useState<JiraTrigger[]>([])
  const [scheduleTriggers, setScheduleTriggers] = useState<ScheduleTrigger[]>([])
  const [githubTriggers, setGithubTriggers] = useState<GitHubTrigger[]>([])
  const [showWebhookSetupModal, setShowWebhookSetupModal] = useState(false)

  // v0.7.0: Guided wizards for the Productivity + Communication tabs. These
  // dispatchers replace the "+ Configure" / per-placeholder-card CTAs with a
  // single "+ Add ..." launcher per tab. See the wizard components for the
  // picker UX; they delegate to the existing per-service/per-channel setup
  // modals (SlackSetupWizard, GmailSetupWizard, Asana OAuth handler, etc.)
  // once the user has picked a target on step 1.
  const [showProductivityWizard, setShowProductivityWizard] = useState(false)
  const [showChannelsWizard, setShowChannelsWizard] = useState(false)
  const [channelsWizardSession, setChannelsWizardSession] = useState(0)
  const [showTriggerWizard, setShowTriggerWizard] = useState(false)
  const [triggerWizardSession, setTriggerWizardSession] = useState(0)
  const [showEmailTriggerWizard, setShowEmailTriggerWizard] = useState(false)
  const [triggerSetupTarget, setTriggerSetupTarget] = useState<BreadthTriggerId | null>(null)
  const [editingEmailTrigger, setEditingEmailTrigger] = useState<EmailTrigger | null>(null)
  const [webhookRotateModal, setWebhookRotateModal] = useState<
    { open: boolean; secret: string; inboundUrl: string } | null
  >(null)
  const [webhookEditTarget, setWebhookEditTarget] = useState<WebhookIntegration | null>(null)
  const [webhookSaving, setWebhookSaving] = useState(false)

  // v0.6.1: resolved public ingress info — authoritative source for inbound
  // webhook URL display (replaces window.location.origin fallback).
  const [publicIngress, setPublicIngress] = useState<PublicIngressInfo | null>(null)
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
  // (v0.7.x) Old flat provider picker was replaced by the multi-step
  // ProviderWizard — state for the old picker has been removed. The Advanced
  // fallback listens for `tsushin:open-provider-advanced-modal` and opens
  // the existing ProviderInstanceModal below.
  const [editingInstance, setEditingInstance] = useState<ProviderInstance | null>(null)
  const [selectedVendor, setSelectedVendor] = useState<string>('')
  const [instanceMenuOpen, setInstanceMenuOpen] = useState<number | null>(null)

  // Local Services state (Ollama & Kokoro management)
  // v0.7.0: Per-tenant Kokoro auto-provisioning (Hub-consolidated, replaces /settings/tts)
  const [kokoroInstances, setKokoroInstances] = useState<TTSInstance[]>([])
  const [kokoroDefault, setKokoroDefault] = useState<{ default_tts_instance_id: number | null; instance: TTSInstance | null } | null>(null)
  const [kokoroWizardOpen, setKokoroWizardOpen] = useState(false)
  const [kokoroInstanceActionLoading, setKokoroInstanceActionLoading] = useState<number | null>(null)
  const [kokoroLegacyExpanded, setKokoroLegacyExpanded] = useState(false)
  const [kokoroLogsOpenFor, setKokoroLogsOpenFor] = useState<number | null>(null)
  const [kokoroLogsContent, setKokoroLogsContent] = useState<string>('')
  const [kokoroLogsLoading, setKokoroLogsLoading] = useState(false)
  const [kokoroConfirmDelete, setKokoroConfirmDelete] = useState<{ id: number; removeVolume: boolean } | null>(null)
  // v0.6.0-patch.7: Per-tenant SearXNG auto-provisioning (Hub Tool APIs panel)
  const [searxngInstances, setSearxngInstances] = useState<SearxngInstance[]>([])
  const [searxngLoading, setSearxngLoading] = useState(false)
  const [searxngActionLoading, setSearxngActionLoading] = useState<number | null>(null)
  const [searxngConfirmDelete, setSearxngConfirmDelete] = useState<{ id: number; instance_name: string } | null>(null)
  const [searxngLogsOpenFor, setSearxngLogsOpenFor] = useState<number | null>(null)
  const [searxngLogsContent, setSearxngLogsContent] = useState<string>('')
  const [searxngLogsLoading, setSearxngLogsLoading] = useState(false)
  const [ollamaEnabled, setOllamaEnabled] = useState(false)
  const [ollamaToggleLoading, setOllamaToggleLoading] = useState(false)
  const [ollamaUrlEditing, setOllamaUrlEditing] = useState(false)
  const [ollamaUrlValue, setOllamaUrlValue] = useState('')
  const [ollamaUrlSaving, setOllamaUrlSaving] = useState(false)
  const [ollamaTestResult, setOllamaTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [ollamaTestLoading, setOllamaTestLoading] = useState(false)
  // v0.6.x: Ollama per-tenant auto-provisioning
  const [ollamaMode, setOllamaMode] = useState<'host' | 'auto'>('host')
  const [ollamaProvisionLoading, setOllamaProvisionLoading] = useState(false)
  const [ollamaContainerActionLoading, setOllamaContainerActionLoading] = useState(false)
  const [showOllamaSetupWizard, setShowOllamaSetupWizard] = useState(false)
  const [ollamaContainerStatus, setOllamaContainerStatus] = useState<any | null>(null)
  const [ollamaGpuEnabled, setOllamaGpuEnabled] = useState(false)
  const [ollamaMemLimit, setOllamaMemLimit] = useState('4g')
  const [ollamaSelectedModel, setOllamaSelectedModel] = useState('llama3.2:1b')
  const [ollamaCustomModel, setOllamaCustomModel] = useState('')
  const [ollamaPullLoading, setOllamaPullLoading] = useState(false)
  const [ollamaPullJobId, setOllamaPullJobId] = useState<string | null>(null)
  const [ollamaPullProgress, setOllamaPullProgress] = useState<any | null>(null)
  const [ollamaPulledModels, setOllamaPulledModels] = useState<string[]>([])
  const [ollamaLogsOpen, setOllamaLogsOpen] = useState(false)
  const [ollamaLogsContent, setOllamaLogsContent] = useState<string>('')
  const [ollamaLogsLoading, setOllamaLogsLoading] = useState(false)
  const [ollamaConfirmDelete, setOllamaConfirmDelete] = useState<{ id: number; removeVolume: boolean } | null>(null)

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

  async function loadJiraTriggers() {
    try {
      const data = await api.listJiraTriggers()
      setJiraTriggers(data)
    } catch (err) {
      console.error('Failed to load Jira triggers:', err)
    }
  }

  async function loadScheduleTriggers() {
    try {
      const data = await api.listScheduleTriggers()
      setScheduleTriggers(data)
    } catch (err) {
      console.error('Failed to load schedule triggers:', err)
    }
  }

  async function loadGitHubTriggers() {
    try {
      const data = await api.listGitHubTriggers()
      setGithubTriggers(data)
    } catch (err) {
      console.error('Failed to load GitHub triggers:', err)
    }
  }

  async function loadBreadthTriggers() {
    await Promise.all([
      loadJiraTriggers(),
      loadScheduleTriggers(),
      loadGitHubTriggers(),
    ])
  }

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
        loadEmailTriggers()
        loadWebhookIntegrations()  // v0.6.0: Webhook-as-Channel
        loadBreadthTriggers()  // v0.7.0: Jira, Schedule, GitHub triggers
        loadPublicIngress()  // v0.6.1: resolver-backed inbound URL
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
        refreshKokoroInstances(),  // v0.7.0: per-tenant Kokoro (Hub-consolidated)
        refreshSearxngInstances(),  // v0.6.0-patch.7: per-tenant SearXNG (Hub-consolidated)
        loadHubIntegrations(),
        loadMcpInstances(),
        loadTesterStatus(),
        loadTelegramInstances(),  // Phase 10.1.1
        loadSlackIntegrations(),  // v0.6.0
        loadDiscordIntegrations(),  // v0.6.0
        loadEmailTriggers(),
        loadWebhookIntegrations(),  // v0.6.0: Webhook-as-Channel
        loadBreadthTriggers(),  // v0.7.0: Jira, Schedule, GitHub triggers
        loadPublicIngress(),  // v0.6.1: resolver-backed inbound URL
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
          details: { hint: 'Create a per-tenant Kokoro instance at /hub (Kokoro card → Setup with Wizard).' }
        })
      }
    } catch (error) {
      setKokoroHealth({
        provider: 'kokoro',
        status: 'unavailable',
        message: 'Cannot reach backend',
        available: false,
        details: { hint: 'Create a per-tenant Kokoro instance at /hub (Kokoro card → Setup with Wizard).' }
      })
    }
  }

  // ==================== Kokoro Container Management ====================

  // Auto-poll Kokoro health periodically while the service is not yet available.
  // Per-tenant Kokoro instances (v0.7.0) are managed via the dedicated wizard;
  // this legacy-panel poll is purely for visibility into any out-of-band compose
  // install that the tenant may still be running.
  useEffect(() => {
    if (!kokoroHealth?.available) {
      const interval = setInterval(async () => {
        await fetchKokoroHealth()
      }, 5000) // poll every 5s
      return () => clearInterval(interval)
    }
  }, [kokoroHealth?.available])

  // ==================== Per-tenant Kokoro Instance Management (v0.7.0) ====================

  const refreshKokoroInstances = async () => {
    try {
      const [list, def] = await Promise.all([
        api.getTTSInstances().catch(() => [] as TTSInstance[]),
        api.getDefaultTTSInstance().catch(() => null),
      ])
      setKokoroInstances((list || []).filter((i: TTSInstance) => i.vendor === 'kokoro'))
      setKokoroDefault(def)
    } catch {
      // Non-fatal — tenant may not have permissions
    }
  }

  const handleKokoroWizardClose = (refresh?: boolean) => {
    setKokoroWizardOpen(false)
    if (refresh) {
      refreshKokoroInstances()
    }
  }

  const handleKokoroInstanceStart = async (id: number) => {
    setKokoroInstanceActionLoading(id)
    try {
      await api.ttsContainerAction(id, 'start')
      toast.success('Starting Kokoro container...')
      setTimeout(() => refreshKokoroInstances(), 1200)
    } catch (e: any) {
      toast.error(e?.message || 'Failed to start container')
    } finally {
      setKokoroInstanceActionLoading(null)
    }
  }

  const handleKokoroInstanceStop = async (id: number) => {
    setKokoroInstanceActionLoading(id)
    try {
      await api.ttsContainerAction(id, 'stop')
      toast.success('Stopping Kokoro container...')
      setTimeout(() => refreshKokoroInstances(), 1200)
    } catch (e: any) {
      toast.error(e?.message || 'Failed to stop container')
    } finally {
      setKokoroInstanceActionLoading(null)
    }
  }

  const handleKokoroInstanceRestart = async (id: number) => {
    setKokoroInstanceActionLoading(id)
    try {
      await api.ttsContainerAction(id, 'restart')
      toast.success('Restarting Kokoro container...')
      setTimeout(() => refreshKokoroInstances(), 1500)
    } catch (e: any) {
      toast.error(e?.message || 'Failed to restart container')
    } finally {
      setKokoroInstanceActionLoading(null)
    }
  }

  const handleSetKokoroDefault = async (id: number | null) => {
    try {
      await api.setDefaultTTSInstance(id)
      toast.success(id ? 'Default Kokoro instance updated' : 'Default Kokoro cleared')
      await refreshKokoroInstances()
    } catch (e: any) {
      toast.error(e?.message || 'Failed to set default')
    }
  }

  const handleKokoroInstanceDelete = async () => {
    if (!kokoroConfirmDelete) return
    const { id, removeVolume } = kokoroConfirmDelete
    try {
      await api.deleteTTSInstance(id, removeVolume)
      toast.success('Kokoro instance deleted')
      setKokoroConfirmDelete(null)
      await refreshKokoroInstances()
    } catch (e: any) {
      toast.error(e?.message || 'Failed to delete instance')
      setKokoroConfirmDelete(null)
    }
  }

  const handleKokoroViewLogs = async (id: number) => {
    if (kokoroLogsOpenFor === id) {
      setKokoroLogsOpenFor(null)
      setKokoroLogsContent('')
      return
    }
    setKokoroLogsOpenFor(id)
    setKokoroLogsLoading(true)
    try {
      const { logs } = await api.getTTSContainerLogs(id, 100)
      setKokoroLogsContent(logs || '(no logs)')
    } catch (e: any) {
      setKokoroLogsContent(`Error loading logs: ${e?.message || 'unknown'}`)
    } finally {
      setKokoroLogsLoading(false)
    }
  }

  // ==================== SearXNG Instance Management (v0.6.0-patch.7) ====================

  const refreshSearxngInstances = async () => {
    setSearxngLoading(true)
    try {
      const list = await api.listSearxngInstances().catch(() => [] as SearxngInstance[])
      setSearxngInstances(list || [])
    } finally {
      setSearxngLoading(false)
    }
  }

  const handleSearxngAction = async (id: number, action: 'start' | 'stop' | 'restart') => {
    setSearxngActionLoading(id)
    try {
      await api.searxngContainerAction(id, action)
      toast.success(`${action === 'start' ? 'Starting' : action === 'stop' ? 'Stopping' : 'Restarting'} SearXNG container…`)
      setTimeout(() => refreshSearxngInstances(), 1200)
    } catch (e: any) {
      toast.error(e?.message || `Failed to ${action} SearXNG container`)
    } finally {
      setSearxngActionLoading(null)
    }
  }

  const handleSearxngDelete = async () => {
    if (!searxngConfirmDelete) return
    const { id } = searxngConfirmDelete
    setSearxngActionLoading(id)
    try {
      await api.deleteSearxngInstance(id)
      toast.success('SearXNG instance deleted')
      setSearxngConfirmDelete(null)
      await refreshSearxngInstances()
    } catch (e: any) {
      toast.error(e?.message || 'Failed to delete instance')
      setSearxngConfirmDelete(null)
    } finally {
      setSearxngActionLoading(null)
    }
  }

  const handleSearxngViewLogs = async (id: number) => {
    if (searxngLogsOpenFor === id) {
      setSearxngLogsOpenFor(null)
      setSearxngLogsContent('')
      return
    }
    setSearxngLogsOpenFor(id)
    setSearxngLogsLoading(true)
    try {
      const { logs } = await api.getSearxngContainerLogs(id, 100)
      setSearxngLogsContent(logs || '(no logs)')
    } catch (e: any) {
      setSearxngLogsContent(`Error loading logs: ${e?.message || 'unknown'}`)
    } finally {
      setSearxngLogsLoading(false)
    }
  }

  // Poll container status for SearXNG instances still provisioning
  useEffect(() => {
    const pending = searxngInstances.filter(i => {
      const s = (i.container_status || '').toLowerCase()
      return s === 'creating' || s === 'provisioning'
    })
    if (pending.length === 0) return
    const interval = setInterval(async () => {
      try {
        const updates = await Promise.all(
          pending.map(i => api.getSearxngContainerStatus(i.id).catch(() => null))
        )
        const anyTerminal = updates.some(u => {
          const s = (u?.status || '').toLowerCase()
          return s === 'running' || s === 'error' || s === 'stopped'
        })
        if (anyTerminal) refreshSearxngInstances()
      } catch { /* transient */ }
    }, 3000)
    return () => clearInterval(interval)
  }, [searxngInstances])

  // Poll container status for Kokoro instances that are creating/provisioning
  useEffect(() => {
    const pending = kokoroInstances.filter(i => {
      const s = (i.container_status || '').toLowerCase()
      return s === 'creating' || s === 'provisioning'
    })
    if (pending.length === 0) return
    const interval = setInterval(async () => {
      try {
        const updates = await Promise.all(
          pending.map(i => api.getTTSContainerStatus(i.id).catch(() => null))
        )
        let changed = false
        const next = kokoroInstances.map((inst) => {
          const match = pending.find(p => p.id === inst.id)
          if (!match) return inst
          const idx = pending.indexOf(match)
          const statusResp = updates[idx]
          if (statusResp && statusResp.status && statusResp.status !== inst.container_status) {
            changed = true
            return { ...inst, container_status: statusResp.status }
          }
          return inst
        })
        if (changed) {
          setKokoroInstances(next)
          // If any transitioned to running/error/stopped, refresh the full list
          const anyTerminal = updates.some(u => {
            const s = (u?.status || '').toLowerCase()
            return s === 'running' || s === 'error' || s === 'stopped'
          })
          if (anyTerminal) {
            refreshKokoroInstances()
          }
        }
      } catch { /* transient */ }
    }, 3000)
    return () => clearInterval(interval)
  }, [kokoroInstances])

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
        const ollamaInstance = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
        if (ollamaInstance) {
          if (ollamaInstance.is_auto_provisioned) {
            await api.controlOllamaContainer(ollamaInstance.id, 'stop')
            toast.success('Stopping Ollama container...')
            setTimeout(() => { refreshOllamaContainerStatus() }, 1200)
          } else {
            await api.deleteProviderInstance(ollamaInstance.id)
            toast.success('Ollama disabled')
          }
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

  // v0.6.x: Ollama auto-provisioning handlers
  const refreshOllamaContainerStatus = async () => {
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst) return null
    try {
      const status = await api.getOllamaContainerStatus(inst.id)
      setOllamaContainerStatus(status)
      return status
    } catch {
      return null
    }
  }

  const refreshOllamaPulledModels = async () => {
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst) return
    try {
      const { models } = await api.listOllamaModels(inst.id)
      setOllamaPulledModels(models || [])
    } catch {
      /* ignore */
    }
  }

  // Detect auto-provisioned Ollama and load its state
  useEffect(() => {
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (inst?.is_auto_provisioned) {
      setOllamaMode('auto')
      // Load initial status + pulled models
      ;(async () => {
        try {
          const status = await api.getOllamaContainerStatus(inst.id)
          setOllamaContainerStatus(status)
          if ((status?.status || '').toLowerCase() === 'running') {
            try {
              const { models } = await api.listOllamaModels(inst.id)
              setOllamaPulledModels(models || [])
            } catch { /* ignore */ }
          }
        } catch { /* ignore */ }
      })()
    } else if (inst) {
      setOllamaMode('host')
    }
  }, [providerInstances])

  // Poll container status while provisioning (peer review A-11: cleanup on unmount)
  useEffect(() => {
    if (ollamaMode !== 'auto') return
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst?.is_auto_provisioned) return
    const state = (ollamaContainerStatus?.status || '').toLowerCase()
    if (state !== 'creating' && state !== 'provisioning') return

    let cancelled = false
    let ticks = 0
    const timer = setInterval(async () => {
      if (cancelled) return
      ticks++
      try {
        const status = await api.getOllamaContainerStatus(inst.id)
        if (cancelled) return
        setOllamaContainerStatus(status)
        const s = (status?.status || '').toLowerCase()
        if (s === 'running') {
          try {
            const { models } = await api.listOllamaModels(inst.id)
            if (!cancelled) setOllamaPulledModels(models || [])
          } catch { /* ignore */ }
          clearInterval(timer)
        } else if (s === 'error') {
          clearInterval(timer)
        }
      } catch { /* keep polling on transient errors */ }
      if (ticks > 180) clearInterval(timer)  // ~9 min cap
    }, 3000)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [ollamaMode, ollamaContainerStatus?.status, providerInstances])

  const handleOllamaProvision = async () => {
    // Ensure an Ollama provider instance exists first
    setOllamaProvisionLoading(true)
    try {
      let inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
      if (!inst) {
        inst = await api.ensureOllamaInstance()
        await fetchProviderInstances()
      }
      await api.provisionOllamaContainer(inst.id, ollamaGpuEnabled, ollamaMemLimit)
      toast.success('Provisioning Ollama container — this may take 1-2 minutes')
      // Set initial status so the status-poll useEffect kicks in
      setOllamaContainerStatus({ status: 'provisioning' })
      await fetchProviderInstances()
    } catch (err: any) {
      toast.error(err.message || 'Failed to provision Ollama container')
    } finally {
      setOllamaProvisionLoading(false)
    }
  }

  const handleOllamaDeprovision = async (removeVolume: boolean) => {
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst) return
    if (!confirm(`Deprovision Ollama container${removeVolume ? ' and remove model volume (permanent data loss)' : ''}?`)) return
    try {
      await api.deprovisionOllamaContainer(inst.id, removeVolume)
      toast.success('Ollama container deprovisioned')
      setOllamaContainerStatus(null)
      setOllamaPulledModels([])
      await fetchProviderInstances()
    } catch (err: any) {
      toast.error(err.message || 'Failed to deprovision Ollama container')
    }
  }

  // Unified Ollama instance delete — mirrors handleKokoroInstanceDelete so
  // the ManagedContainerPanel `onDelete` action behaves identically across
  // Ollama and Kokoro (soft-delete the provider instance; backend tears down
  // the container for auto-provisioned rows, see routes_provider_instances).
  const handleOllamaInstanceDelete = async () => {
    if (!ollamaConfirmDelete) return
    const { id, removeVolume } = ollamaConfirmDelete
    try {
      const inst = providerInstances.find(i => i.id === id)
      if (inst?.is_auto_provisioned) {
        try {
          await api.deprovisionOllamaContainer(id, removeVolume)
        } catch {
          // Deprovision is best-effort; the delete below is the source of truth.
        }
      }
      await api.deleteProviderInstance(id)
      toast.success('Ollama instance deleted')
      setOllamaConfirmDelete(null)
      setOllamaContainerStatus(null)
      setOllamaPulledModels([])
      await fetchProviderInstances()
    } catch (e: any) {
      toast.error(e?.message || 'Failed to delete instance')
      setOllamaConfirmDelete(null)
    }
  }

  const handleOllamaContainerAction = async (action: 'start' | 'stop' | 'restart') => {
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst) return
    setOllamaContainerActionLoading(true)
    try {
      await api.controlOllamaContainer(inst.id, action)
      toast.success(`${action === 'start' ? 'Starting' : action === 'stop' ? 'Stopping' : 'Restarting'} Ollama container...`)
      setTimeout(() => { refreshOllamaContainerStatus() }, 1200)
    } catch (err: any) {
      toast.error(err.message || `Failed to ${action} container`)
    } finally {
      setOllamaContainerActionLoading(false)
    }
  }

  const handleOllamaViewLogs = async () => {
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst) return
    if (ollamaLogsOpen) {
      setOllamaLogsOpen(false)
      setOllamaLogsContent('')
      return
    }
    setOllamaLogsOpen(true)
    setOllamaLogsLoading(true)
    try {
      const { logs } = await api.getOllamaContainerLogs(inst.id, 100)
      setOllamaLogsContent(logs || '(no logs)')
    } catch (e: any) {
      setOllamaLogsContent(`Error loading logs: ${e?.message || 'unknown'}`)
    } finally {
      setOllamaLogsLoading(false)
    }
  }

  const handleOllamaPullModel = async () => {
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst) return
    const modelName = ollamaSelectedModel === 'custom'
      ? ollamaCustomModel.trim()
      : ollamaSelectedModel
    if (!modelName) {
      toast.error('Please enter a model name')
      return
    }
    setOllamaPullLoading(true)
    setOllamaPullProgress(null)
    try {
      const job = await api.pullOllamaModel(inst.id, modelName)
      setOllamaPullJobId(job.job_id)
      setOllamaPullProgress(job)
    } catch (err: any) {
      toast.error(err.message || 'Failed to start model pull')
      setOllamaPullLoading(false)
    }
  }

  // Poll pull job (peer review A-11: cleanup on unmount)
  useEffect(() => {
    if (!ollamaPullJobId || !ollamaPullLoading) return
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst) return

    let cancelled = false
    const timer = setInterval(async () => {
      if (cancelled) return
      try {
        const status = await api.getPullJobStatus(inst.id, ollamaPullJobId)
        if (cancelled) return
        setOllamaPullProgress(status)
        if (status.status === 'done') {
          toast.success(`Pulled ${status.model || 'model'}`)
          setOllamaPullLoading(false)
          setOllamaPullJobId(null)
          await refreshOllamaPulledModels()
          clearInterval(timer)
        } else if (status.status === 'error') {
          toast.error(status.error || 'Pull failed')
          setOllamaPullLoading(false)
          setOllamaPullJobId(null)
          clearInterval(timer)
        }
      } catch { /* keep polling on transient */ }
    }, 2000)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ollamaPullJobId, ollamaPullLoading])

  const handleOllamaDeleteModel = async (modelName: string) => {
    const inst = providerInstances.find(i => i.vendor === 'ollama' && i.is_active)
    if (!inst) return
    if (!confirm(`Delete model "${modelName}"?`)) return
    try {
      await api.deleteOllamaModel(inst.id, modelName)
      toast.success(`Deleted ${modelName}`)
      await refreshOllamaPulledModels()
    } catch (err: any) {
      toast.error(err.message || 'Failed to delete model')
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
  // Keep the ref used by the Google wizard complete handler in sync.
  loadHubIntegrationsRef.current = loadHubIntegrations

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

  // Bridge function: maintained for the existing call sites inside this
  // file. Routes everything to the new multi-step ProviderWizard. A vendor
  // preset lands the user directly on the credentials/container step (the
  // reducer skips any earlier steps whose answers are already implied).
  const openProviderSetupWizard = (vendor?: string) => {
    setEditingInstance(null)
    setSelectedVendor('')
    if (vendor) {
      // TTS Kokoro lands on the container branch; everything else is LLM cloud.
      const isTTSKokoro = vendor === 'kokoro'
      const isTTSEleven = vendor === 'elevenlabs'
      const isOllamaLocal = vendor === 'ollama'
      const modality = isTTSKokoro || isTTSEleven ? 'tts' as const : 'llm' as const
      const hosting = isTTSKokoro || isOllamaLocal ? 'local' as const : 'cloud' as const
      openProviderWizard({ vendor, modality, hosting })
    } else {
      openProviderWizard()
    }
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
      toast.warning(
        'Validation',
        modalData.service === 'searxng'
          ? 'Please provide the SearXNG base URL'
          : 'Please select a service and provide the API key'
      )
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
  const loadEmailTriggers = useCallback(async () => {
    try {
      const data = await api.listEmailTriggers()
      setEmailTriggers(data)
    } catch (err) {
      console.error('Failed to load email triggers:', err)
    }
  }, [])

  const loadWebhookIntegrations = useCallback(async () => {
    try {
      const data = await api.listWebhookIntegrations()
      setWebhookIntegrations(data)
    } catch (err) {
      console.error('Failed to load webhook integrations:', err)
    }
  }, [])

  // v0.6.1: fetch the resolver-computed public ingress URL so all inbound-URL
  // displays (webhook cards, setup modal) share the same authoritative value.
  const loadPublicIngress = useCallback(async () => {
    try {
      const info = await api.getMyPublicIngress()
      setPublicIngress(info)
    } catch (err) {
      console.error('Failed to resolve public ingress:', err)
      setPublicIngress(null)
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

  const handleToggleWebhookActive = async (integration: WebhookIntegration) => {
    const next = !integration.is_active
    try {
      await api.updateWebhookIntegration(integration.id, { is_active: next })
      setSuccessMessage(next ? `"${integration.integration_name}" is now active` : `"${integration.integration_name}" paused — slug remains reserved`)
      setTimeout(() => setSuccessMessage(null), 4000)
      loadWebhookIntegrations()
    } catch (err: any) {
      setError(err.message || 'Failed to toggle webhook')
    }
  }

  const handleRotateWebhookSecret = async (id: number, inboundUrl: string) => {
    if (!confirm('Rotate the HMAC secret? Your external system will need the new secret before the next request.')) return
    try {
      const result = await api.rotateWebhookSecret(id)
      setWebhookRotateModal({ open: true, secret: result.api_secret, inboundUrl })
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
      const response = await authenticatedFetch(`${apiUrl}/api/hub/asana/oauth/disconnect/${integrationId}`, {
        method: 'POST'
      })
      if (!response.ok) {
        const body = await response.text().catch(() => '')
        throw new Error(body || `Disconnect failed (${response.status})`)
      }
      setHubIntegrations(prev => prev.filter(i => i.id !== integrationId))
      await loadHubIntegrations()
      setSuccessMessage('Asana disconnected')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error: any) {
      setError(error?.message || 'Failed to disconnect Asana')
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

  // Google Calendar handlers — route through the shared wizard so OAuth, account
  // selection and agent-linking all happen in one flow.
  const handleGoogleCalendarConnect = () => {
    if (!googleCredentials) {
      setError('Google OAuth credentials are not configured. Please configure them in Settings → Integrations first.')
      return
    }
    openGoogleWizard('calendar')
  }

  const handleGoogleCalendarDisconnect = async (integrationId: number) => {
    if (!confirm('Disconnect Google Calendar integration?')) return

    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/calendar/oauth/disconnect/${integrationId}`, {
        method: 'POST'
      })
      if (!response.ok) {
        const body = await response.text().catch(() => '')
        throw new Error(body || `Disconnect failed (${response.status})`)
      }
      setHubIntegrations(prev => prev.filter(i => i.id !== integrationId))
      await loadHubIntegrations()
      setSuccessMessage('Google Calendar disconnected')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error: any) {
      setError(error?.message || 'Failed to disconnect Google Calendar')
    }
  }

  // Gmail handlers — route through the shared wizard so OAuth and agent-linking
  // run together (matches the Settings → Integrations flow).
  const handleGmailConnect = () => {
    if (!googleCredentials) {
      setError('Google OAuth credentials are not configured. Please configure them in Settings → Integrations first.')
      return
    }
    openGoogleWizard('gmail')
  }

  const handleGmailDisconnect = async (integrationId: number) => {
    if (!confirm('Disconnect Gmail integration?')) return

    try {
      const apiUrl = ''
      const response = await authenticatedFetch(`${apiUrl}/api/hub/google/gmail/oauth/disconnect/${integrationId}`, {
        method: 'POST'
      })
      if (!response.ok) {
        const body = await response.text().catch(() => '')
        throw new Error(body || `Disconnect failed (${response.status})`)
      }
      setHubIntegrations(prev => prev.filter(i => i.id !== integrationId))
      await loadHubIntegrations()
      setSuccessMessage('Gmail disconnected')
      setTimeout(() => setSuccessMessage(null), 3000)
    } catch (error: any) {
      setError(error?.message || 'Failed to disconnect Gmail')
    }
  }

  // v0.7.0 — wizard dispatchers. Both wizards close themselves before
  // invoking these callbacks, so we only need to flip the right sub-wizard's
  // visibility (or call the existing connect handler for browser-redirect
  // flows like Asana).
  const handleProductivityDispatch = (serviceId: string) => {
    if (serviceId === 'gmail') {
      handleGmailConnect()
    } else if (serviceId === 'google_calendar') {
      handleGoogleCalendarConnect()
    } else if (serviceId === 'asana') {
      handleAsanaConnect()
    } else {
      toast.error('Not yet supported', `No connect handler for '${serviceId}' yet`)
    }
  }

  const openChannelsWizard = () => {
    setChannelsWizardSession((current) => current + 1)
    setShowChannelsWizard(true)
  }

  const openTriggerWizard = () => {
    setTriggerWizardSession((current) => current + 1)
    setShowTriggerWizard(true)
  }

  const handleChannelsDispatch = (channelId: ChannelId) => {
    switch (channelId) {
      case 'whatsapp':
        setShowCreateModeSelector(true)
        break
      case 'telegram':
        setShowTelegramModal(true)
        break
      case 'slack':
        setShowSlackSetupModal(true)
        break
      case 'discord':
        setShowDiscordSetupModal(true)
        break
      default:
        toast.error('Not yet supported', `No connect handler for '${channelId}' yet`)
    }
  }

  const handleTriggerDispatch = (triggerId: TriggerId) => {
    switch (triggerId) {
      case 'email':
        setEditingEmailTrigger(null)
        setShowEmailTriggerWizard(true)
        break
      case 'webhook':
        setShowWebhookSetupModal(true)
        break
      case 'jira':
      case 'schedule':
      case 'github':
        setTriggerSetupTarget(triggerId)
        break
      default:
        toast.error('Not yet supported', `No connect handler for '${triggerId}' yet`)
    }
  }

  const handleEmailTriggerComplete = async (trigger: EmailTrigger) => {
    const wasEditing = editingEmailTrigger !== null
    await loadEmailTriggers()
    await loadHubIntegrations()
    setShowEmailTriggerWizard(false)
    setEditingEmailTrigger(null)
    setSuccessMessage(wasEditing ? `Email trigger updated: ${trigger.integration_name}` : `Email trigger created: ${trigger.integration_name}`)
    setTimeout(() => setSuccessMessage(null), 3000)
  }

  const handleBreadthTriggerComplete = async (trigger: JiraTrigger | ScheduleTrigger | GitHubTrigger) => {
    await loadBreadthTriggers()
    await loadHubIntegrations()
    setTriggerSetupTarget(null)
    setSuccessMessage(`Trigger created: ${trigger.integration_name}`)
    setTimeout(() => setSuccessMessage(null), 3000)
  }

  // Re-authorize an expired/revoked integration
  const handleReauthorize = async (integrationId: number, integrationType?: string) => {
    try {
      const apiUrl = ''
      const params = new URLSearchParams({ redirect_url: '/hub' })
      if (integrationType === 'gmail') {
        params.set('include_send_scope', 'true')
      }
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
  const hasComposeTesterContainer = Boolean(
    testerStatus &&
    testerStatus.source === 'compose' &&
    testerStatus.container_state &&
    testerStatus.container_state !== 'not_found'
  )
  const showDedicatedTesterCard = hasComposeTesterContainer
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
    // Tool APIs — SearXNG has no API key; its configured state is driven by
    // SearxngInstance rows, not the `api_keys` table.
    const hasSearxngInstance = type === 'tool' && item.value === 'searxng' && searxngInstances.some(i => i.is_active)
    const hasInstanceKey = Boolean(configuredInstance)
    const configuredViaInstance = !apiKey && (hasInstanceKey || hasSearxngInstance)
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
              {/* (v0.7.x) The inline "Fallback — instance key takes priority"
                  amber label was removed; the Service API Keys surface is now
                  collapsed by default and only lists vendors that have NO
                  matching ProviderInstance, so duplicate display is impossible
                  by construction. */}
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
              {apiKey
                ? (apiKey.is_active ? 'Active' : 'Inactive')
                : hasSearxngInstance
                  ? 'Active'
                  : (configuredViaInstance ? 'Instance configured' : 'Not configured')}
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
        {!isComingSoon && canWriteHub && (
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
                onClick={() => {
                  if (item.value === 'vertex_ai') {
                    setShowVertexAiModal(true)
                    return
                  }
                  // Tool APIs that own a richer flow (auto-provisioning, OAuth-style credentials)
                  // route through the generic Add Integration wizard so we share one codepath.
                  const wizardProviders = new Set(['searxng', 'amadeus', 'google_flights'])
                  if (type === 'tool' && wizardProviders.has(item.value)) {
                    setAddIntegrationInitialProvider(item.value)
                    setShowSearchWizard(true)
                    return
                  }
                  openAddApiKeyModal(item.value)
                }}
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

  // (v0.7.x) The inline `renderManagedContainerControls` helper was extracted
  // into `@/components/hub/ManagedContainerPanel` so Ollama / Kokoro / SearXNG
  // all render identical lifecycle affordances. See that file for the body.

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
  // (v0.7.x) Service API Keys — surface ONLY vendors that have a fallback
  // api_key configured AND zero `ProviderInstance` rows. This eliminates the
  // duplicate-Gemini display by construction: if you have a Gemini instance,
  // Gemini never appears in the fallback disclosure below.
  const vendorsWithInstances = new Set(providerInstances.map(i => i.vendor))
  const visibleAiFallbackProviders = AI_PROVIDERS.filter(provider =>
    Boolean(getApiKeyForService(provider.value)) && !vendorsWithInstances.has(provider.value)
  )
  const visibleToolApis = TOOL_APIS.filter(tool => {
    if (tool.value === 'searxng') return searxngInstances.some(i => i.is_active)
    return Boolean(getApiKeyForService(tool.value))
  })
  // v0.7.x: align Ollama visibility with Kokoro — show panel only when an
  // active provider_instance exists. `ollamaEnabled` (tenant setting) remains
  // the gate for background health polling, but the Hub card itself is driven
  // by the instance list so unused providers never take visual space.
  const ollamaInstance = providerInstances.find(i => i.vendor === 'ollama' && i.is_active) ?? null
  const showLocalServices = !!ollamaInstance || kokoroInstances.length > 0

  if (oauthPopupHandoff) {
    return null
  }

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
        {/* BUG-610 read-only banner: surfaces why Connect/Add/Disconnect
            buttons are missing for non-admins. Without this the page
            looks broken ("why are there no actions?") — with it the
            user knows to ask an admin for hub.write. */}
        {!canWriteHub && (
          <div
            className="p-4 bg-tsushin-warning/10 border border-tsushin-warning/30 rounded-xl text-tsushin-warning flex items-center gap-3"
            data-testid="hub-readonly-banner"
          >
            <svg className="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 100 20 10 10 0 000-20z" />
            </svg>
            <div className="text-sm">
              <span className="font-medium">Read-only view.</span>{' '}
              Your role does not have <code className="font-mono">hub.write</code>{' '}
              — you can browse configured integrations but cannot add, edit, or disconnect them. Ask an owner/admin for access.
            </div>
          </div>
        )}
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
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">AI Model Providers</h2>
                    <p className="text-sm text-tsushin-slate">Manage provider instances and API keys for AI models</p>
                  </div>
                  {canWriteHub && (
                    <button
                      onClick={() => openProviderSetupWizard()}
                      className="btn-primary w-full sm:w-auto justify-center"
                    >
                      + New Instance
                    </button>
                  )}
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
                  const allVendors = Object.keys(vendorGroups)
                    .filter(v => v !== 'ollama' && v !== 'elevenlabs')
                    .sort()

                  return (
                    <div className="space-y-6">
                      {allVendors.length === 0 && (
                        <div className="border border-dashed border-tsushin-border rounded-xl p-5 text-center">
                          <p className="text-sm text-tsushin-slate">No LLM provider instances configured yet.</p>
                          {canEditSettings && (
                            <button
                              onClick={() => openProviderSetupWizard()}
                              className="mt-3 btn-secondary px-4 py-2 text-sm"
                            >
                              Add Provider
                            </button>
                          )}
                        </div>
                      )}
                      {allVendors.map(vendor => {
                        const instances = vendorGroups[vendor] || []
                        const VendorIcon = VENDOR_ICONS[vendor] || BeakerIcon
                        const vendorColor = VENDOR_COLORS[vendor] || 'text-tsushin-accent'

                        return (
                          <div key={vendor} className="space-y-3">
                            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                              <div className="flex items-center gap-2.5 min-w-0">
                                <VendorIcon size={18} className={vendorColor} />
                                <h3 className="text-sm font-semibold text-white">{VENDOR_LABELS[vendor] || vendor}</h3>
                                <span className="text-xs text-tsushin-slate">
                                  {instances.length} instance{instances.length !== 1 ? 's' : ''}
                                </span>
                              </div>
                              {canWriteHub && (
                                <button
                                  onClick={() => openProviderSetupWizard(vendor)}
                                  className="inline-flex w-fit items-center gap-1 rounded-md border border-tsushin-accent/25 bg-tsushin-accent/10 px-2.5 py-1 text-xs text-tsushin-accent hover:text-white hover:bg-tsushin-accent/15 transition-colors"
                                >
                                  <PlusIconSvg size={14} />
                                  Add Instance
                                </button>
                              )}
                            </div>

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
                          </div>
                        )
                      })}
                    </div>
                  )
                })()}

                {/* Local Services Section */}
                {showLocalServices && (
                <div className="pt-2">
                  <h3 className="text-sm font-semibold text-tsushin-fog mb-3">Local Services</h3>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {/* Ollama Card (Local LLM) — aligned with Kokoro pattern:
                        renders only when an Ollama provider_instance exists,
                        mode (host vs. auto) is derived from the instance, and
                        lifecycle controls go through the shared
                        `ManagedContainerPanel` so Ollama ↔ Kokoro ↔ SearXNG
                        expose the same affordances (toggle, restart, logs,
                        test, delete). The legacy Mode radio + separate
                        Deprovision/Test/Refresh/Manage buttons were removed. */}
                    {ollamaInstance && (() => {
                      const isAuto = !!ollamaInstance.is_auto_provisioned
                      const raw = (ollamaContainerStatus?.status || 'none').toLowerCase()
                      // Docker reports 'exited' for a cleanly-stopped container that still exists.
                      const state = raw === 'exited' ? 'stopped' : raw
                      const isProvisioning = state === 'creating' || state === 'provisioning'
                      const isRunning = isAuto ? state === 'running' : !!ollamaHealth?.available
                      const isNoneOrError = state === 'none' || state === 'error' || !state
                      return (
                        <div className="card p-5 hover-glow group border-purple-700/30">
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-3">
                              <div className="w-10 h-10 rounded-xl bg-purple-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                                <BotIconSvg size={20} className="text-purple-400" />
                              </div>
                              <div>
                                <h3 className="font-semibold text-white">Ollama (Local)</h3>
                                <p className="text-[11px] text-tsushin-slate">Run LLMs locally — host URL or auto-provisioned container</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-1.5">
                              <div className={`w-2 h-2 rounded-full ${
                                isRunning
                                  ? 'bg-tsushin-success animate-pulse'
                                  : isProvisioning ? 'bg-yellow-400' : 'bg-tsushin-slate'
                              }`} />
                              <span className="text-[11px] text-tsushin-slate">1 instance</span>
                            </div>
                          </div>

                          {/* Per-instance row — mirrors Kokoro's per-instance card */}
                          <div className="p-3 bg-tsushin-ink/40 border border-white/5 rounded-lg space-y-3">
                            <div className="flex items-start justify-between gap-2 flex-wrap">
                              <div className="flex items-start gap-2 min-w-0">
                                <div className="min-w-0">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <span className="text-sm text-white font-medium truncate">{ollamaInstance.instance_name}</span>
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">ollama</span>
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">{isAuto ? 'Auto' : 'Host'}</span>
                                    {ollamaInstance.is_default && (
                                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-tsushin-success/20 text-tsushin-success">Default</span>
                                    )}
                                  </div>
                                </div>
                              </div>
                              <span className={`text-[11px] px-2 py-0.5 rounded shrink-0 ${
                                isRunning ? 'bg-tsushin-success/20 text-tsushin-success' :
                                isProvisioning ? 'bg-yellow-500/20 text-yellow-400' :
                                state === 'error' ? 'bg-tsushin-vermilion/20 text-tsushin-vermilion' :
                                'bg-gray-500/20 text-gray-400'
                              }`}>
                                {isProvisioning
                                  ? 'Provisioning…'
                                  : isAuto
                                    ? (state || 'n/a')
                                    : (ollamaHealth?.available ? 'running' : 'offline')}
                              </span>
                            </div>

                            {/* Host mode: URL editor + Docker networking note + health summary */}
                            {!isAuto && (
                              <div className="space-y-2">
                                <div className="flex items-center gap-1.5">
                                  <span className="text-[11px] text-tsushin-muted shrink-0">URL:</span>
                                  {ollamaUrlEditing ? (
                                    <>
                                      <input
                                        type="text"
                                        value={ollamaUrlValue}
                                        onChange={(e) => setOllamaUrlValue(e.target.value)}
                                        className="bg-tsushin-ink border border-white/10 rounded-lg px-2.5 py-1 text-white text-xs font-mono flex-1 min-w-0"
                                        onKeyDown={(e) => {
                                          if (e.key === 'Enter') handleOllamaUrlSave()
                                          if (e.key === 'Escape') setOllamaUrlEditing(false)
                                        }}
                                      />
                                      <button
                                        onClick={handleOllamaUrlSave}
                                        disabled={ollamaUrlSaving}
                                        className="text-[11px] bg-tsushin-success/20 text-tsushin-success hover:bg-tsushin-success/30 rounded px-2 py-1 shrink-0"
                                      >
                                        {ollamaUrlSaving ? '…' : 'Save'}
                                      </button>
                                      <button
                                        onClick={() => setOllamaUrlEditing(false)}
                                        className="text-[11px] text-tsushin-slate hover:text-white px-1.5 py-1 shrink-0"
                                      >
                                        Cancel
                                      </button>
                                    </>
                                  ) : (
                                    <p
                                      className="text-[11px] font-mono text-tsushin-accent cursor-pointer hover:text-white transition-colors flex-1 truncate"
                                      onClick={() => canEditSettings && setOllamaUrlEditing(true)}
                                      title={canEditSettings ? 'Click to edit URL' : ''}
                                    >
                                      {ollamaHealth?.base_url || ollamaInstance.base_url || '(not set)'}
                                    </p>
                                  )}
                                </div>

                                {ollamaHealth?.available ? (
                                  <p className="text-[11px] text-tsushin-slate">
                                    {ollamaHealth.models_count || 0} model{(ollamaHealth.models_count || 0) !== 1 ? 's' : ''} available
                                  </p>
                                ) : (
                                  <>
                                    <p className="text-[11px] text-tsushin-vermilion">{ollamaHealth?.error || 'Not running'}</p>
                                    <p className="text-[11px] text-tsushin-slate">
                                      Start with: <code className="bg-tsushin-deep px-1 py-0.5 rounded font-mono text-tsushin-accent">ollama serve</code>
                                    </p>
                                  </>
                                )}

                                {/* BUG-331: Docker networking guidance (host mode only) */}
                                <div className="p-2 bg-tsushin-deep/60 border border-white/10 rounded-lg space-y-1">
                                  <p className="text-[11px] font-medium text-tsushin-accent">Docker Networking Note</p>
                                  <p className="text-[11px] text-tsushin-slate">
                                    Tsushin runs inside Docker. Use <code className="bg-tsushin-ink px-1 rounded font-mono text-tsushin-accent">http://172.18.0.1:11434</code> instead of <code className="bg-tsushin-ink px-1 rounded font-mono">localhost</code> so the backend container can reach Ollama on the host.
                                  </p>
                                  <code className="block text-[11px] bg-tsushin-ink px-2 py-1 rounded font-mono text-tsushin-success overflow-x-auto">
                                    Environment=&quot;OLLAMA_HOST=0.0.0.0:11434&quot;
                                  </code>
                                </div>

                                {ollamaTestResult && (
                                  <p className={`text-[11px] ${ollamaTestResult.success ? 'text-tsushin-success' : 'text-tsushin-vermilion'}`}>
                                    {ollamaTestResult.success ? 'Connection successful' : ollamaTestResult.message}
                                  </p>
                                )}
                              </div>
                            )}

                            {/* Auto mode — provision config when no container */}
                            {isAuto && isNoneOrError && canEditSettings && (
                              <div className="space-y-2">
                                <label className="flex items-center gap-2 text-xs text-tsushin-slate">
                                  <input
                                    type="checkbox"
                                    checked={ollamaGpuEnabled}
                                    onChange={e => setOllamaGpuEnabled(e.target.checked)}
                                    className="accent-tsushin-success"
                                  />
                                  GPU enabled (requires NVIDIA runtime on host)
                                </label>
                                <div>
                                  <label className="block text-[11px] text-tsushin-muted mb-1">Memory limit</label>
                                  <select
                                    value={ollamaMemLimit}
                                    onChange={e => setOllamaMemLimit(e.target.value)}
                                    className="w-full bg-tsushin-ink border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white"
                                  >
                                    <option value="2g">2g</option>
                                    <option value="4g">4g</option>
                                    <option value="8g">8g</option>
                                    <option value="16g">16g</option>
                                  </select>
                                </div>
                                <button
                                  onClick={handleOllamaProvision}
                                  disabled={ollamaProvisionLoading}
                                  className="w-full bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 rounded-lg px-3 py-1.5 text-xs transition-colors disabled:opacity-50"
                                >
                                  {ollamaProvisionLoading ? 'Starting…' : 'Provision Container'}
                                </button>
                              </div>
                            )}

                            {/* Auto mode — provisioning spinner */}
                            {isAuto && isProvisioning && (
                              <div className="flex items-center gap-2 text-xs text-yellow-400">
                                <span className="animate-spin rounded-full h-3 w-3 border-t-2 border-b-2 border-yellow-400" />
                                Setting up Ollama container (may take 1–2 minutes)…
                                <button
                                  onClick={refreshOllamaContainerStatus}
                                  className="ml-auto text-[11px] text-tsushin-accent hover:text-white"
                                >
                                  Refresh
                                </button>
                              </div>
                            )}

                            {/* Auto mode — pulled models + pull a new model (when running) */}
                            {isAuto && isRunning && (
                              <div className="space-y-3">
                                <div>
                                  <p className="text-[11px] text-tsushin-muted mb-1.5">Pulled models</p>
                                  {ollamaPulledModels.length === 0 ? (
                                    <p className="text-[11px] text-tsushin-slate italic">None yet — pull one below.</p>
                                  ) : (
                                    <div className="flex flex-wrap gap-1.5">
                                      {ollamaPulledModels.map(m => (
                                        <span key={m} className="inline-flex items-center gap-1.5 text-[11px] bg-tsushin-ink border border-white/10 rounded-lg px-2 py-1 text-white font-mono">
                                          {m}
                                          {canEditSettings && (
                                            <button
                                              onClick={() => handleOllamaDeleteModel(m)}
                                              className="text-tsushin-vermilion hover:text-red-300 text-xs"
                                              title="Delete model"
                                            >
                                              &times;
                                            </button>
                                          )}
                                        </span>
                                      ))}
                                    </div>
                                  )}
                                </div>
                                {canEditSettings && (
                                  <div className="space-y-2 pt-2 border-t border-white/5">
                                    <p className="text-[11px] text-tsushin-muted">Pull a new model</p>
                                    <div className="flex gap-1.5">
                                      <select
                                        value={ollamaSelectedModel}
                                        onChange={e => setOllamaSelectedModel(e.target.value)}
                                        disabled={ollamaPullLoading}
                                        className="flex-1 bg-tsushin-ink border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white font-mono disabled:opacity-50"
                                      >
                                        {CURATED_OLLAMA_MODELS.map(m => (
                                          <option key={m} value={m}>{m}</option>
                                        ))}
                                      </select>
                                      <button
                                        onClick={handleOllamaPullModel}
                                        disabled={ollamaPullLoading || (ollamaSelectedModel === 'custom' && !ollamaCustomModel.trim())}
                                        className="bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 rounded-lg px-3 py-1.5 text-xs transition-colors disabled:opacity-50"
                                      >
                                        {ollamaPullLoading ? 'Pulling…' : 'Pull'}
                                      </button>
                                    </div>
                                    {ollamaSelectedModel === 'custom' && (
                                      <input
                                        type="text"
                                        value={ollamaCustomModel}
                                        onChange={e => setOllamaCustomModel(e.target.value)}
                                        placeholder="e.g. llama3.2:8b-instruct-q4_K_M"
                                        disabled={ollamaPullLoading}
                                        className="w-full bg-tsushin-ink border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-white font-mono disabled:opacity-50"
                                      />
                                    )}
                                    {ollamaPullLoading && ollamaPullProgress && (
                                      <div className="space-y-1">
                                        <div className="flex items-center justify-between text-[11px] text-tsushin-slate">
                                          <span>Pulling {ollamaPullProgress.model || ollamaSelectedModel}</span>
                                          <span>{ollamaPullProgress.percent != null ? `${Math.round(ollamaPullProgress.percent)}%` : '…'}</span>
                                        </div>
                                        <div className="h-1.5 w-full bg-tsushin-ink rounded-full overflow-hidden">
                                          <div
                                            className="h-full bg-purple-400 transition-all"
                                            style={{ width: `${ollamaPullProgress.percent ?? 0}%` }}
                                          />
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Unified lifecycle controls — ManagedContainerPanel for
                                auto-provisioned instances (matches Kokoro), a compact
                                Test+Refresh+Delete strip for host-mode where there's
                                no container to toggle. */}
                            {canEditSettings && isAuto && (
                              <ManagedContainerPanel
                                status={state}
                                isBusy={ollamaContainerActionLoading || ollamaTestLoading}
                                onToggle={() => handleOllamaContainerAction(isRunning ? 'stop' : 'start')}
                                onRestart={() => handleOllamaContainerAction('restart')}
                                onLogs={handleOllamaViewLogs}
                                logsOpen={ollamaLogsOpen}
                                onTest={handleOllamaTest}
                                testLabel={ollamaTestLoading ? 'Testing…' : 'Test'}
                                onDelete={() => setOllamaConfirmDelete({ id: ollamaInstance.id, removeVolume: true })}
                              />
                            )}

                            {canEditSettings && !isAuto && (
                              <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5">
                                <button
                                  onClick={handleOllamaTest}
                                  disabled={ollamaTestLoading}
                                  className="text-[11px] bg-white/5 border border-white/10 text-tsushin-slate hover:bg-white/10 rounded px-2 py-1 disabled:opacity-50"
                                >
                                  {ollamaTestLoading ? 'Testing…' : 'Test'}
                                </button>
                                <button
                                  onClick={async () => {
                                    await fetchOllamaHealth()
                                    try {
                                      const models = await api.discoverProviderModels(ollamaInstance.id)
                                      toast.success(`Discovered ${models.length} model${models.length !== 1 ? 's' : ''}`)
                                      await fetchProviderInstances()
                                    } catch { /* ignore */ }
                                  }}
                                  className="text-[11px] bg-white/5 border border-white/10 text-tsushin-slate hover:bg-white/10 rounded px-2 py-1"
                                >
                                  Refresh Models
                                </button>
                                <button
                                  onClick={() => setOllamaConfirmDelete({ id: ollamaInstance.id, removeVolume: true })}
                                  className="ml-auto text-[11px] bg-tsushin-vermilion/10 border border-tsushin-vermilion/20 text-tsushin-vermilion hover:bg-tsushin-vermilion/20 rounded px-2 py-1"
                                >
                                  Delete
                                </button>
                              </div>
                            )}

                            {/* Logs drawer — auto mode only (host mode has no container logs) */}
                            {isAuto && ollamaLogsOpen && (
                              <div className="p-2 bg-black/50 border border-white/5 rounded">
                                <div className="flex items-center justify-between mb-1">
                                  <span className="text-[10px] text-tsushin-muted uppercase tracking-wider">Last 100 log lines</span>
                                  <button
                                    onClick={async () => {
                                      setOllamaLogsLoading(true)
                                      try {
                                        const { logs } = await api.getOllamaContainerLogs(ollamaInstance.id, 100)
                                        setOllamaLogsContent(logs || '(no logs)')
                                      } catch (e: any) {
                                        setOllamaLogsContent(`Error: ${e?.message || 'unknown'}`)
                                      } finally {
                                        setOllamaLogsLoading(false)
                                      }
                                    }}
                                    disabled={ollamaLogsLoading}
                                    className="text-[10px] text-tsushin-accent hover:text-white disabled:opacity-50"
                                  >
                                    {ollamaLogsLoading ? 'Loading…' : 'Refresh'}
                                  </button>
                                </div>
                                <pre className="text-[10px] font-mono text-tsushin-slate whitespace-pre-wrap max-h-48 overflow-auto">
                                  {ollamaLogsContent || (ollamaLogsLoading ? 'Loading logs…' : '(no logs loaded)')}
                                </pre>
                              </div>
                            )}
                          </div>
                        </div>
                      )
                    })()}

                    {/* Kokoro TTS Card (v0.7.0 consolidated — per-tenant instances + removed legacy controls) */}
                    {kokoroInstances.length > 0 && (
                    <div className="card p-5 hover-glow group border-green-700/30">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-green-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                            <MicrophoneIcon size={20} className="text-green-400" />
                          </div>
                          <div>
                            <h3 className="font-semibold text-white">Kokoro TTS (Free)</h3>
                            <p className="text-[11px] text-tsushin-slate">Self-hosted, multilingual text-to-speech</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <div className={`w-2 h-2 rounded-full ${
                            kokoroInstances.some(i => (i.container_status || '').toLowerCase() === 'running')
                              ? 'bg-tsushin-success animate-pulse'
                              : kokoroInstances.length > 0 ? 'bg-yellow-400' : 'bg-tsushin-slate'
                          }`} />
                          <span className="text-[11px] text-tsushin-slate">
                            {kokoroInstances.length} instance{kokoroInstances.length !== 1 ? 's' : ''}
                          </span>
                        </div>
                      </div>

                      {/* Per-Tenant Instances (primary UX) */}
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-medium text-tsushin-accent uppercase tracking-wider">Per-Tenant Instances</p>
                          {canEditSettings && (
                            <button
                              onClick={() => setKokoroWizardOpen(true)}
                              className="text-[11px] bg-green-500/20 text-green-400 hover:bg-green-500/30 rounded-lg px-2.5 py-1 transition-colors"
                            >
                              + Setup with Wizard
                            </button>
                          )}
                        </div>

                        {kokoroInstances.length === 0 ? (
                          <div className="p-4 bg-tsushin-ink/40 border border-white/5 rounded-lg text-center">
                            <p className="text-xs text-tsushin-slate">
                              {canEditSettings
                                ? 'No Kokoro instances yet — use the wizard above to set one up.'
                                : 'No Kokoro instances yet.'}
                            </p>
                          </div>
                        ) : (
                          <div className="space-y-2">
                            {kokoroInstances.map(inst => {
                              const raw = (inst.container_status || 'none').toLowerCase()
                              const status = raw === 'exited' ? 'stopped' : raw
                              const isProvisioning = status === 'creating' || status === 'provisioning'
                              const isRunning = status === 'running'
                              const isStopped = status === 'stopped'
                              const isBusy = kokoroInstanceActionLoading === inst.id
                              const isDefault = kokoroDefault?.default_tts_instance_id === inst.id
                              return (
                                <div key={inst.id} className="p-3 bg-tsushin-ink/40 border border-white/5 rounded-lg">
                                  <div className="flex items-start justify-between gap-2 flex-wrap">
                                    <div className="flex items-start gap-2 min-w-0">
                                      <input
                                        type="radio"
                                        checked={isDefault}
                                        onChange={() => canEditSettings && handleSetKokoroDefault(isDefault ? null : inst.id)}
                                        disabled={!canEditSettings}
                                        aria-label={`Set ${inst.instance_name} as default Kokoro instance`}
                                        className="mt-1 accent-green-400"
                                      />
                                      <div className="min-w-0">
                                        <div className="flex items-center gap-1.5 flex-wrap">
                                          <span className="text-sm text-white font-medium truncate">{inst.instance_name}</span>
                                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/10 text-green-400">{inst.vendor}</span>
                                          {inst.is_auto_provisioned && (
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">Auto</span>
                                          )}
                                          {isDefault && (
                                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-tsushin-success/20 text-tsushin-success">Default</span>
                                          )}
                                        </div>
                                        {inst.base_url && (
                                          <p className="text-[11px] font-mono text-tsushin-muted mt-1 truncate">{inst.base_url}</p>
                                        )}
                                      </div>
                                    </div>
                                    <span className={`text-[11px] px-2 py-0.5 rounded shrink-0 ${
                                      isRunning ? 'bg-tsushin-success/20 text-tsushin-success' :
                                      isProvisioning ? 'bg-yellow-500/20 text-yellow-400' :
                                      isStopped ? 'bg-gray-500/20 text-gray-400' :
                                      status === 'error' ? 'bg-tsushin-vermilion/20 text-tsushin-vermilion' :
                                      'bg-gray-500/20 text-gray-400'
                                    }`}>
                                      {isProvisioning ? 'Provisioning...' : status || 'n/a'}
                                    </span>
                                  </div>

                                  {/* Actions */}
                                  {canEditSettings && inst.is_auto_provisioned && (
                                    <ManagedContainerPanel
                                      status={status}
                                      isBusy={isBusy}
                                      onToggle={() => isRunning ? handleKokoroInstanceStop(inst.id) : handleKokoroInstanceStart(inst.id)}
                                      onRestart={() => handleKokoroInstanceRestart(inst.id)}
                                      onLogs={() => handleKokoroViewLogs(inst.id)}
                                      logsOpen={kokoroLogsOpenFor === inst.id}
                                      onDelete={() => setKokoroConfirmDelete({ id: inst.id, removeVolume: true })}
                                    />
                                  )}

                                  {/* Logs drawer (inline) */}
                                  {kokoroLogsOpenFor === inst.id && (
                                    <div className="mt-2 p-2 bg-black/50 border border-white/5 rounded">
                                      <div className="flex items-center justify-between mb-1">
                                        <span className="text-[10px] text-tsushin-muted uppercase tracking-wider">Last 100 log lines</span>
                                        <button
                                          onClick={async () => {
                                            setKokoroLogsLoading(true)
                                            try {
                                              const { logs } = await api.getTTSContainerLogs(inst.id, 100)
                                              setKokoroLogsContent(logs || '(no logs)')
                                            } catch (e: any) {
                                              setKokoroLogsContent(`Error: ${e?.message || 'unknown'}`)
                                            } finally {
                                              setKokoroLogsLoading(false)
                                            }
                                          }}
                                          disabled={kokoroLogsLoading}
                                          className="text-[10px] text-tsushin-accent hover:text-white disabled:opacity-50"
                                        >
                                          {kokoroLogsLoading ? 'Loading...' : 'Refresh'}
                                        </button>
                                      </div>
                                      <pre className="text-[10px] font-mono text-tsushin-slate whitespace-pre-wrap max-h-48 overflow-auto">
                                        {kokoroLogsContent || (kokoroLogsLoading ? 'Loading logs...' : '(no logs loaded)')}
                                      </pre>
                                    </div>
                                  )}
                                </div>
                              )
                            })}
                          </div>
                        )}
                      </div>

                      {/* Removed global Kokoro controls (demoted, collapsed by default) */}
                      <div className="mt-4 pt-3 border-t border-white/5">
                        <button
                          onClick={() => setKokoroLegacyExpanded(v => !v)}
                          className="flex items-center gap-1.5 text-[11px] text-tsushin-slate hover:text-white transition-colors"
                          aria-expanded={kokoroLegacyExpanded}
                        >
                          <svg className={`w-3 h-3 transition-transform ${kokoroLegacyExpanded ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                          </svg>
                          Removed global Kokoro controls
                        </button>
                        {kokoroLegacyExpanded && (
                          <div className="mt-3 p-3 bg-tsushin-ink/30 border border-white/5 rounded-lg space-y-2">
                            <p className="text-[11px] text-tsushin-muted">
                              The old shared Kokoro service controls were removed in v0.7.0. Older <code className="text-tsushin-accent font-mono">/api/services/kokoro/*</code> clients receive HTTP 410 with a successor link to <code className="text-tsushin-accent font-mono">/api/tts-instances</code>. Use the per-tenant instances above for all Kokoro setup and lifecycle actions.
                            </p>
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-1.5">
                                <div className={`w-2 h-2 rounded-full ${
                                  kokoroHealth?.available
                                    ? 'bg-tsushin-success animate-pulse'
                                    : 'bg-tsushin-slate'
                                }`} />
                                <span className="text-[11px] text-tsushin-slate capitalize">
                                  {kokoroHealth?.available ? 'Online' : 'Offline'}
                                </span>
                              </div>
                            </div>
                            {kokoroHealth?.available && (
                              <p className="text-[11px] font-mono text-tsushin-accent">{kokoroHealth.details?.service_url || 'http://localhost:8880'}</p>
                            )}
                            {!kokoroHealth?.available && (
                              <p className="text-[11px] text-tsushin-slate">No active Kokoro provider endpoint. Click <span className="font-semibold text-tsushin-accent">Setup with Wizard</span> above to auto-provision a per-tenant instance.</p>
                            )}
                            <button
                              onClick={async () => {
                                await fetchKokoroHealth()
                              }}
                              className="text-[11px] text-tsushin-accent hover:text-white"
                            >
                              Refresh status
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                    )}
                  </div>
                </div>
                )}

                {/* (v0.7.x) Service API Keys — collapsed disclosure.
                    Only renders vendors that have a fallback api_key AND no
                    matching ProviderInstance, so vendors already covered by
                    an instance never duplicate here. Collapsed by default to
                    keep the Hub clean for users who only use instances. */}
                {visibleAiFallbackProviders.length > 0 && (
                  <details className="pt-2 group">
                    <summary className="cursor-pointer list-none flex items-center gap-2 select-none">
                      <ChevronRightIcon size={14} className="text-tsushin-slate transition-transform group-open:rotate-90" />
                      <div>
                        <h3 className="text-sm font-semibold text-tsushin-fog">Service API Keys — fallback keys</h3>
                        <p className="text-xs text-tsushin-slate">{visibleAiFallbackProviders.length} vendor{visibleAiFallbackProviders.length !== 1 ? 's' : ''} using a fallback key (no provider instance)</p>
                      </div>
                    </summary>
                    <div className="mt-3 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {visibleAiFallbackProviders.map(provider => renderIntegrationCard(provider, 'ai'))}
                    </div>
                  </details>
                )}
              </div>
            )}

            {/* ==================== COMMUNICATION TAB ==================== */}
            {/* v0.7.0 rework — single "+ Add Channel" launcher opens
                ChannelsWizard, which dispatches to the existing per-channel
                setup modal (WhatsApp / Telegram / Slack / Discord). Email now
                lives in the trigger path below, alongside webhook triggers.
                Per-channel sections are hidden when they
                contain zero instances so empty shells don't dominate the tab.
                The per-section "+ Create X" button inside each section (shown
                only when at least one instance already exists) lets users add
                another instance without going back through the wizard. */}
            {activeTab === 'communication' && (() => {
              const channelConfiguredCount =
                mcpInstances.length +
                telegramInstances.length +
                slackIntegrations.length +
                discordIntegrations.length
              return (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">Communication</h2>
                    <p className="text-sm text-tsushin-slate">Connect real-time channels and trigger-driven entry points for agent interactions.</p>
                  </div>
                  {canWriteHub && (
                    <button
                      onClick={openChannelsWizard}
                      className="btn-primary"
                    >
                      + Add Channel
                    </button>
                  )}
                </div>

                {channelConfiguredCount === 0 && (
                  <div className="card p-8 text-center border-dashed border-tsushin-border/60">
                    <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-tsushin-accent/10 flex items-center justify-center">
                      <MessageIconSvg size={24} className="text-tsushin-accent" />
                    </div>
                    <h3 className="text-white font-semibold mb-1">No channels configured yet</h3>
                    <p className="text-xs text-tsushin-slate mb-4 max-w-md mx-auto">
                      Connect WhatsApp, Telegram, Slack, or Discord so users can reach your agents on the platforms they already use.
                    </p>
                    {canWriteHub && (
                      <button
                        onClick={openChannelsWizard}
                        className="btn-primary px-4 py-2 text-sm"
                      >
                        + Add Channel
                      </button>
                    )}
                  </div>
                )}

                {/* WhatsApp Instances — v0.7.0: hidden when zero instances
                    exist. Settings like the Conversation Response Delay are
                    only relevant once at least one WhatsApp instance is
                    provisioned; the "+ Add Channel" launcher at the top of
                    the tab covers first-time provisioning. */}
                {mcpInstances.length > 0 && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <MessageIconSvg size={18} /> WhatsApp Instances
                    </h3>
                    {canWriteHub && (
                      <button
                        onClick={() => setShowCreateModeSelector(true)}
                        className="px-4 py-2 bg-green-600/20 text-green-400 border border-green-600/50 rounded hover:bg-green-600/30 text-sm"
                      >
                        + Create Instance
                      </button>
                    )}
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
                            {instance.instance_type === 'agent' && (
                              <ChannelRoutingRulesPanel
                                channelType="whatsapp"
                                instanceId={instance.id}
                                canWrite={canWriteHub}
                              />
                            )}
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
                )}

                {/* Phase 10.1.1: Telegram Bot Instances — v0.7.0: section
                    rendered only when the tenant already has at least one
                    bot. The "+ Add Channel" launcher covers the 0-instance
                    case; per-section "+ Create Bot" stays for adding a 2nd. */}
                {telegramInstances.length > 0 && (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <PlaneIcon size={18} /> Telegram Bots
                    </h3>
                    {canWriteHub && (
                      <button
                        onClick={() => setShowTelegramModal(true)}
                        className="px-4 py-2 bg-blue-600/20 text-blue-400 border border-blue-600/50 rounded hover:bg-blue-600/30 text-sm"
                      >
                        + Create Bot
                      </button>
                    )}
                  </div>

                  {telegramInstances.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <PlaneIcon size={36} className="text-blue-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Telegram Bots</h3>
                      <p className="text-tsushin-slate mb-4">Create a bot to connect Telegram</p>
                      {canWriteHub && (
                        <button
                          onClick={() => setShowTelegramModal(true)}
                          className="btn-primary"
                        >
                          Create Bot
                        </button>
                      )}
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
                            <ChannelRoutingRulesPanel
                              channelType="telegram"
                              instanceId={instance.id}
                              canWrite={canWriteHub}
                            />
                          </div>
                        )
                      })}
                    </div>
                  )}
                </div>
                )}

                {/* v0.6.0: Slack Integration — v0.7.0: hidden when empty. */}
                {slackIntegrations.length > 0 && (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <SlackIcon size={18} className="text-purple-400" /> Slack
                    </h3>
                    {canWriteHub && (
                      <button
                        onClick={() => setShowSlackSetupModal(true)}
                        className="px-4 py-2 bg-purple-600/20 text-purple-400 border border-purple-600/50 rounded hover:bg-purple-600/30 text-sm"
                      >
                        + Connect Workspace
                      </button>
                    )}
                  </div>

                  {slackIntegrations.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <SlackIcon size={36} className="text-purple-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Slack Workspaces</h3>
                      <p className="text-tsushin-slate mb-4">Connect a Slack workspace to enable bot messaging</p>
                      {canWriteHub && (
                        <button
                          onClick={() => setShowSlackSetupModal(true)}
                          className="btn-primary"
                        >
                          Connect Workspace
                        </button>
                      )}
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
                          <ChannelRoutingRulesPanel
                            channelType="slack"
                            instanceId={integration.id}
                            canWrite={canWriteHub}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                )}

                {/* v0.6.0: Discord Integration — v0.7.0: hidden when empty. */}
                {discordIntegrations.length > 0 && (
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <DiscordIcon size={18} className="text-indigo-400" /> Discord
                    </h3>
                    {canWriteHub && (
                      <button
                        onClick={() => setShowDiscordSetupModal(true)}
                        className="px-4 py-2 bg-indigo-600/20 text-indigo-400 border border-indigo-600/50 rounded hover:bg-indigo-600/30 text-sm"
                      >
                        + Connect Bot
                      </button>
                    )}
                  </div>

                  {discordIntegrations.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <DiscordIcon size={36} className="text-indigo-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Discord Bots</h3>
                      <p className="text-tsushin-slate mb-4">Connect a Discord bot to enable messaging in your servers</p>
                      {canWriteHub && (
                        <button
                          onClick={() => setShowDiscordSetupModal(true)}
                          className="btn-primary"
                        >
                          Connect Bot
                        </button>
                      )}
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
                          <ChannelRoutingRulesPanel
                            channelType="discord"
                            instanceId={integration.id}
                            canWrite={canWriteHub}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                )}

                {/* v0.6.0 V060-CHN-002: Public Base URL setting (used by Slack HTTP + Discord + Webhooks) */}
                {(slackIntegrations.length > 0 || discordIntegrations.length > 0 || webhookIntegrations.length > 0) && (
                  <PublicBaseUrlCard canEdit={canEditSettings} />
                )}

                <div className="space-y-4 pt-2" data-testid="hub-triggers-section">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-md font-semibold text-white flex items-center gap-2">
                        <WebhookIcon size={18} className="text-cyan-400" /> Triggers
                      </h3>
                      <p className="text-xs text-tsushin-slate mt-1">
                        Event-driven entry points that wake agents from inbox activity or signed external events.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      <Link
                        href="/hub/wake-events"
                        className="px-3 py-2 bg-gray-800/70 text-gray-200 border border-gray-700 rounded hover:bg-gray-700 text-sm"
                      >
                        Wake Events
                      </Link>
                      <Link
                        href="/continuous-agents"
                        className="px-3 py-2 bg-gray-800/70 text-gray-200 border border-gray-700 rounded hover:bg-gray-700 text-sm"
                      >
                        Continuous Agents
                      </Link>
                      {canWriteHub && (
                        <button
                          onClick={openTriggerWizard}
                          className="px-4 py-2 bg-cyan-600/20 text-cyan-400 border border-cyan-600/50 rounded hover:bg-cyan-600/30 text-sm"
                        >
                          + Add Trigger
                        </button>
                      )}
                    </div>
                  </div>

                  {emailTriggers.length === 0 && webhookIntegrations.length === 0 && jiraTriggers.length === 0 && scheduleTriggers.length === 0 && githubTriggers.length === 0 && (
                    <div className="card p-6 border-dashed border-tsushin-border/60">
                      <h4 className="text-white font-semibold mb-1">No triggers configured yet</h4>
                      <p className="text-sm text-tsushin-slate mb-4">
                        Create an Email, Webhook, Jira, Schedule, or GitHub trigger to wake agents from external events.
                      </p>
                      {canWriteHub && (
                        <button onClick={openTriggerWizard} className="btn-primary px-4 py-2 text-sm">
                          + Add Trigger
                        </button>
                      )}
                    </div>
                  )}
                </div>

                <div className="space-y-4">
                  <div>
                    <h3 className="text-md font-semibold text-white flex items-center gap-2">
                      <EnvelopeIcon size={18} className="text-red-400" /> Email Triggers
                    </h3>
                    <p className="text-xs text-tsushin-slate mt-1">
                      Gmail-backed trigger rows that watch inbox activity, apply an optional search filter, and wake agents from matching messages.
                    </p>
                  </div>

                  {emailTriggers.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-tsushin-border p-6">
                      <div className="text-sm font-medium text-white mb-2">No email triggers yet</div>
                      <p className="text-sm text-tsushin-slate mb-3">
                        Email triggers reuse your connected Gmail accounts and a persisted default agent. Create one from the trigger launcher when you&apos;re ready.
                      </p>
                      <div className="text-xs text-tsushin-slate bg-tsushin-slate/5 border border-tsushin-border/70 rounded-lg px-3 py-2">
                        Need a new inbox? The email trigger wizard can connect a Gmail account inline before you save the trigger.
                      </div>
                    </div>
                  ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {emailTriggers.map((emailTrigger) => (
                        <div key={emailTrigger.id} className="card p-5 hover-glow border-red-700/30">
                          <div className="flex items-start justify-between mb-3 gap-3">
                            <div>
                              <h3 className="font-semibold text-white">{emailTrigger.integration_name}</h3>
                              <p className="text-xs text-tsushin-slate">
                                {emailTrigger.gmail_account_email || emailTrigger.gmail_integration_name || 'Gmail inbox'}
                              </p>
                            </div>
                            <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                              emailTrigger.is_active
                                ? 'bg-green-500/10 text-green-400 border border-green-500/20'
                                : 'bg-gray-500/20 text-gray-400 border border-gray-500/50'
                            }`}>
                              {emailTrigger.is_active ? 'Active' : 'Paused'}
                            </span>
                          </div>

                          <div className="text-xs text-tsushin-slate space-y-1 mb-4">
                            <p>Default agent: <span className="text-white">{emailTrigger.default_agent_name || 'None'}</span></p>
                            <p>Search: <span className="text-white">{emailTrigger.search_query || 'Inbox default'}</span></p>
                            <p>Poll every: <span className="text-white">{emailTrigger.poll_interval_seconds}s</span></p>
                            <p>Health: <span className="text-white">{emailTrigger.health_status}</span></p>
                          </div>

                          <div className="grid grid-cols-3 gap-2">
                            <Link
                              href={`/hub/triggers/email/${emailTrigger.id}`}
                              className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-600/50 rounded text-xs hover:bg-red-600/30 text-center"
                            >
                              Details
                            </Link>
                            <button
                              onClick={() => {
                                setEditingEmailTrigger(emailTrigger)
                                setShowEmailTriggerWizard(true)
                              }}
                              className="px-3 py-1.5 bg-red-600/20 text-red-400 border border-red-600/50 rounded text-xs hover:bg-red-600/30"
                            >
                              Edit
                            </button>
                            <button
                              onClick={async () => {
                                try {
                                  await api.updateEmailTrigger(emailTrigger.id, { is_active: !emailTrigger.is_active })
                                  await loadEmailTriggers()
                                  setSuccessMessage(!emailTrigger.is_active ? 'Email trigger resumed' : 'Email trigger paused')
                                  setTimeout(() => setSuccessMessage(null), 3000)
                                } catch (err: any) {
                                  setError(err.message || 'Failed to update email trigger')
                                }
                              }}
                              className="px-3 py-1.5 bg-gray-700 text-gray-200 border border-gray-600 rounded text-xs hover:bg-gray-600"
                            >
                              {emailTrigger.is_active ? 'Pause' : 'Resume'}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Webhook trigger section remains visible so the trigger path
                    is still reachable after webhook leaves the channel wizard. */}
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-md font-semibold text-white flex items-center gap-2">
                        <WebhookIcon size={18} className="text-cyan-400" /> Webhook Triggers
                      </h3>
                      <p className="text-xs text-tsushin-slate mt-1">
                        Signed external events that can wake agents or continuous flows.
                      </p>
                    </div>
                  </div>

                  {webhookIntegrations.length === 0 ? (
                    <div className="empty-state py-12 border border-dashed border-tsushin-border rounded-xl">
                      <div className="empty-state-icon">
                        <WebhookIcon size={36} className="text-cyan-400" />
                      </div>
                      <h3 className="text-lg font-semibold text-white mb-2">No Webhook Triggers</h3>
                      <p className="text-tsushin-slate mb-4">
                        Connect external HTTP systems (CRMs, Zapier, custom apps) via HMAC-signed webhook triggers
                      </p>
                      {canWriteHub && (
                        <button
                          onClick={() => setShowWebhookSetupModal(true)}
                          className="btn-primary"
                        >
                          Create Webhook Trigger
                        </button>
                      )}
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
                                onClick={() => navigator.clipboard.writeText((publicIngress?.url || window.location.origin) + integration.inbound_url)}
                                title="Copy URL"
                                className="text-gray-500 hover:text-cyan-400 ml-auto shrink-0"
                              >
                                <CopyIcon size={12} />
                              </button>
                            </div>
                            <p>Callback: <span className="text-white">{integration.callback_enabled ? 'Enabled' : 'Disabled'}</span></p>
                            <p>Rate limit: <span className="text-white">{integration.rate_limit_rpm} req/min</span></p>
                          </div>

                          <label className="flex items-center justify-between gap-3 mb-3 p-2 rounded bg-gray-900/40 border border-gray-800 cursor-pointer">
                            <div className="text-xs">
                              <div className="text-gray-300 font-medium">
                                {integration.is_active ? 'Enabled' : 'Paused'}
                              </div>
                              <div className="text-gray-500">
                                {integration.is_active
                                  ? 'Accepts inbound signed events.'
                                  : 'Slug stays reserved — only deletion frees it for reuse.'}
                              </div>
                            </div>
                            <button
                              type="button"
                              role="switch"
                              aria-checked={integration.is_active}
                              onClick={() => handleToggleWebhookActive(integration)}
                              className={`relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors ${
                                integration.is_active ? 'bg-cyan-500' : 'bg-gray-600'
                              }`}
                              title={integration.is_active ? 'Pause webhook' : 'Enable webhook'}
                            >
                              <span
                                className={`inline-block h-4 w-4 transform rounded-full bg-white transition ${
                                  integration.is_active ? 'translate-x-4' : 'translate-x-0.5'
                                }`}
                              />
                            </button>
                          </label>

                          <div className="grid grid-cols-4 gap-2">
                            <Link
                              href={`/hub/triggers/webhook/${integration.id}`}
                              className="px-3 py-1.5 bg-gray-700 text-gray-200 border border-gray-600 rounded text-xs hover:bg-gray-600 text-center"
                              title="View webhook details"
                            >
                              Details
                            </Link>
                            <button
                              onClick={() => setWebhookEditTarget(integration)}
                              className="px-3 py-1.5 bg-gray-700 text-gray-200 border border-gray-600 rounded text-xs hover:bg-gray-600"
                              title="Edit webhook"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleRotateWebhookSecret(integration.id, integration.inbound_url)}
                              className="px-3 py-1.5 bg-cyan-600/20 text-cyan-400 border border-cyan-600/50 rounded text-xs hover:bg-cyan-600/30"
                              title="Rotate HMAC secret"
                            >
                              Rotate
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

                <TriggerBreadthCards
                  jiraTriggers={jiraTriggers}
                  scheduleTriggers={scheduleTriggers}
                  githubTriggers={githubTriggers}
                  canWrite={canWriteHub}
                  onCreate={(kind) => setTriggerSetupTarget(kind)}
                  onChanged={loadBreadthTriggers}
                  onSuccess={(message) => {
                    setSuccessMessage(message)
                    setTimeout(() => setSuccessMessage(null), 3000)
                  }}
                  onError={(message) => setError(message)}
                />

                {/* More Channels and Push Notifications sections removed — all channels now have full integrations */}
              </div>
              )
            })()}

            {/* ==================== PRODUCTIVITY TAB ==================== */}
            {/* v0.7.0 rework — single "+ Add Productivity Integration" launcher
                opens ProductivityWizard (Category -> Service). Configured
                integration cards render only when present; unconfigured
                services live inside the wizard picker, so the tab no longer
                shows "Asana — Not Connected" / "Google Calendar — Not
                Connected" placeholder cards. Gmail stays in the productivity
                area as a reusable Google account integration that also powers
                email triggers. Google OAuth credentials are still configured
                in Settings → Integrations and surfaced as a small badge so the
                user knows whether Google-backed connects will proceed without
                a pre-setup step. */}
            {activeTab === 'productivity' && (() => {
              const gmailIntegrations = hubIntegrations.filter(i => i.type === 'gmail')
              const asanaIntegrations = hubIntegrations.filter(i => i.type === 'asana')
              const calendarIntegrations = hubIntegrations.filter(i => i.type === 'calendar')
              const anyConfigured = gmailIntegrations.length + asanaIntegrations.length + calendarIntegrations.length > 0
              return (
              <div className="space-y-6 animate-fade-in">
                <div className="flex justify-between items-center">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">Productivity & Scheduling</h2>
                    <p className="text-sm text-tsushin-slate">Connect calendar, email, and task-management services to agents.</p>
                  </div>
                  {canWriteHub && (
                    <button
                      onClick={() => setShowProductivityWizard(true)}
                      className="btn-primary"
                    >
                      + Add Productivity Integration
                    </button>
                  )}
                </div>

                {/* Google OAuth badge — compact, not a full card, so it stops
                    dominating the tab when the user hasn't added anything yet.
                    The wizard handles the "missing credentials" case inline. */}
                <div className="flex items-center gap-3 text-xs text-tsushin-slate px-4 py-2 rounded-lg border border-tsushin-border/60 bg-tsushin-slate/5">
                  <LockIcon size={14} className="text-purple-400" />
                  <span>Google OAuth:</span>
                  {googleCredentials ? (
                    <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-green-500/10 text-green-400 border border-green-500/20">
                      Configured
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
                      Not configured
                    </span>
                  )}
                  {!googleCredentials && (
                    <span className="text-amber-400/80">— required for Gmail/Calendar</span>
                  )}
                  <a href="/settings/integrations" className="ml-auto underline hover:no-underline">
                    {googleCredentials ? 'Manage' : 'Configure'}
                  </a>
                </div>

                {gmailIntegrations.length > 0 && (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-md font-semibold text-white flex items-center gap-2">
                        <EnvelopeIcon size={18} /> Gmail Accounts
                      </h3>
                      {canWriteHub && (
                        <button
                          onClick={handleGmailConnect}
                          disabled={!googleCredentials}
                          className={`px-4 py-2 bg-red-600/20 text-red-400 border border-red-600/50 rounded hover:bg-red-600/30 text-sm ${!googleCredentials ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          + Add Gmail Account
                        </button>
                      )}
                    </div>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      {gmailIntegrations.map(integration => (
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
                          <p className="text-xs text-tsushin-slate mb-3">Email actions and trigger inbox selection</p>
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
                                onClick={() => handleReauthorize(integration.id, integration.type)}
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
                    </div>
                  </div>
                )}

                {!anyConfigured ? (
                  <div className="card p-8 text-center border-dashed border-tsushin-border/60">
                    <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-orange-500/10 flex items-center justify-center">
                      <LightbulbIcon size={24} className="text-orange-300" />
                    </div>
                    <h3 className="text-white font-semibold mb-1">No productivity integrations yet</h3>
                    <p className="text-xs text-tsushin-slate mb-4 max-w-md mx-auto">
                      Connect Google Calendar, Gmail, or Asana so agents can schedule meetings, read mail, or create tasks on your behalf.
                    </p>
                    {canWriteHub && (
                      <button
                        onClick={() => setShowProductivityWizard(true)}
                        className="btn-primary px-4 py-2 text-sm"
                      >
                        + Add Productivity Integration
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {asanaIntegrations.map(integration => (
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
                    ))}

                    {calendarIntegrations.map(integration => (
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
                              onClick={() => handleReauthorize(integration.id, integration.type)}
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

                  </div>
                )}
              </div>
              )
            })()}

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

                </div>

                {/* Info Box */}
                <div className="bg-blue-500/5 border border-blue-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-blue-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-blue-300" /> Developer Integrations
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    The Shell Command Center enables remote command execution with security approval workflows. Sandboxed Tools provide
                    per-tenant isolated containers for network scans, vulnerability assessments, and custom scripts.
                  </p>
                </div>
              </div>
            )}

            {/* ==================== TOOL APIS TAB ==================== */}
            {activeTab === 'tool-apis' && (
              <div className="space-y-6 animate-fade-in">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-lg font-display font-semibold text-white">Tool APIs</h2>
                    <p className="text-sm text-tsushin-slate">External APIs for agent capabilities</p>
                  </div>
                  <button
                    onClick={() => { setAddIntegrationInitialProvider(undefined); setShowSearchWizard(true) }}
                    className="w-full sm:w-auto px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-medium transition-colors"
                  >
                    + Add Integration
                  </button>
                </div>

                {visibleToolApis.length > 0 && (
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3 animate-stagger">
                    {visibleToolApis.map(tool => renderIntegrationCard(tool, 'tool'))}
                  </div>
                )}

                {/* SearXNG Per-Tenant Instances (v0.6.0-patch.7) — structure mirrors Kokoro panel */}
                {searxngInstances.length > 0 && (
                <div className="card p-5 hover-glow group border-teal-700/30">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-teal-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                        <GlobeIcon size={20} className="text-teal-400" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-white">SearXNG (Self-hosted)</h3>
                        <p className="text-[11px] text-tsushin-slate">Per-tenant metasearch containers</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className={`w-2 h-2 rounded-full ${
                        searxngInstances.some(i => (i.container_status || '').toLowerCase() === 'running')
                          ? 'bg-tsushin-success animate-pulse'
                          : searxngInstances.length > 0 ? 'bg-yellow-400' : 'bg-tsushin-slate'
                      }`} />
                      <span className="text-[11px] text-tsushin-slate">
                        {searxngInstances.length} instance{searxngInstances.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-tsushin-accent uppercase tracking-wider">Per-Tenant Instances</p>
                      {canEditSettings && (
                        <button
                          onClick={() => { setAddIntegrationInitialProvider('searxng'); setShowSearchWizard(true) }}
                          className="text-[11px] bg-teal-500/20 text-teal-400 hover:bg-teal-500/30 rounded-lg px-2.5 py-1 transition-colors"
                        >
                          + Setup with Wizard
                        </button>
                      )}
                    </div>

                    {searxngLoading ? (
                      <div className="p-4 bg-tsushin-ink/40 border border-white/5 rounded-lg text-center text-xs text-tsushin-slate">Loading…</div>
                    ) : searxngInstances.length === 0 ? (
                      <div className="p-4 bg-tsushin-ink/40 border border-white/5 rounded-lg text-center">
                        <p className="text-xs text-tsushin-slate">
                          {canEditSettings
                            ? 'No SearXNG instances yet — use the wizard above to set one up.'
                            : 'No SearXNG instances yet.'}
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {searxngInstances.map(inst => {
                          const raw = (inst.container_status || 'none').toLowerCase()
                          const status = raw === 'exited' ? 'stopped' : raw
                          const isProvisioning = status === 'creating' || status === 'provisioning'
                          const isRunning = status === 'running'
                          const isStopped = status === 'stopped'
                          const isBusy = searxngActionLoading === inst.id
                          return (
                            <div key={inst.id} className="p-3 bg-tsushin-ink/40 border border-white/5 rounded-lg">
                              <div className="flex items-start justify-between gap-2 flex-wrap">
                                <div className="min-w-0">
                                  <div className="flex items-center gap-1.5 flex-wrap">
                                    <span className="text-sm text-white font-medium truncate">{inst.instance_name}</span>
                                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-400">searxng</span>
                                    {inst.is_auto_provisioned && (
                                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400">Auto</span>
                                    )}
                                  </div>
                                  {inst.base_url && (
                                    <p className="text-[11px] font-mono text-tsushin-muted mt-1 truncate">{inst.base_url}</p>
                                  )}
                                </div>
                                <span className={`text-[11px] px-2 py-0.5 rounded shrink-0 ${
                                  isRunning ? 'bg-tsushin-success/20 text-tsushin-success' :
                                  isProvisioning ? 'bg-yellow-500/20 text-yellow-400' :
                                  isStopped ? 'bg-gray-500/20 text-gray-400' :
                                  status === 'error' ? 'bg-tsushin-vermilion/20 text-tsushin-vermilion' :
                                  'bg-gray-500/20 text-gray-400'
                                }`}>
                                  {isProvisioning ? 'Provisioning...' : status || 'n/a'}
                                </span>
                              </div>
                              {canEditSettings && inst.is_auto_provisioned && (
                                <ManagedContainerPanel
                                  status={status}
                                  isBusy={isBusy}
                                  onToggle={() => isRunning ? handleSearxngAction(inst.id, 'stop') : handleSearxngAction(inst.id, 'start')}
                                  onRestart={() => handleSearxngAction(inst.id, 'restart')}
                                  onLogs={() => handleSearxngViewLogs(inst.id)}
                                  logsOpen={searxngLogsOpenFor === inst.id}
                                  onDelete={() => setSearxngConfirmDelete({ id: inst.id, instance_name: inst.instance_name })}
                                />
                              )}
                              {searxngLogsOpenFor === inst.id && (
                                <div className="mt-2 p-2 bg-black/50 border border-white/5 rounded">
                                  <div className="flex items-center justify-between mb-1">
                                    <span className="text-[10px] text-tsushin-muted uppercase tracking-wider">Last 100 log lines</span>
                                    <button
                                      onClick={async () => {
                                        setSearxngLogsLoading(true)
                                        try {
                                          const { logs } = await api.getSearxngContainerLogs(inst.id, 100)
                                          setSearxngLogsContent(logs || '(no logs)')
                                        } catch (e: any) {
                                          setSearxngLogsContent(`Error: ${e?.message || 'unknown'}`)
                                        } finally {
                                          setSearxngLogsLoading(false)
                                        }
                                      }}
                                      disabled={searxngLogsLoading}
                                      className="text-[10px] text-tsushin-accent hover:text-white disabled:opacity-50"
                                    >
                                      {searxngLogsLoading ? 'Loading...' : 'Refresh'}
                                    </button>
                                  </div>
                                  <pre className="text-[10px] font-mono text-tsushin-slate whitespace-pre-wrap max-h-48 overflow-auto">
                                    {searxngLogsContent || (searxngLogsLoading ? 'Loading logs...' : '(no logs loaded)')}
                                  </pre>
                                </div>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </div>
                )}

                {/* Built-in Tools Info */}
                <div className="bg-teal-500/5 border border-teal-500/20 rounded-xl p-5">
                  <h3 className="text-sm font-semibold text-teal-300 mb-2 flex items-center gap-2">
                    <LightbulbIcon size={16} className="text-teal-300" /> Built-in Tools
                  </h3>
                  <p className="text-xs text-tsushin-slate">
                    These tools are automatically available to agents when the corresponding API keys are configured.
                    Tools include: Web Search (Brave/SearXNG/Tavily/Google), Flight Search (Amadeus/Google), and Web Scraping.
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
                  {canWriteHub && (
                    <button
                      onClick={() => setShowMcpServerModal(true)}
                      className="btn-primary"
                    >
                      + Add Server
                    </button>
                  )}
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
                    {canWriteHub && (
                      <button
                        onClick={() => setShowMcpServerModal(true)}
                        className="btn-primary"
                      >
                        + Add Server
                      </button>
                    )}
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
          title={
            modalData.service === 'searxng'
              ? (editingKey ? 'Edit SearXNG URL' : 'Add SearXNG URL')
              : (editingKey ? 'Edit API Key' : 'Add API Key')
          }
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
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {modalData.service === 'searxng' ? 'Base URL' : 'API Key'}
              </label>
              <input
                type={modalData.service === 'searxng' ? 'text' : 'password'}
                value={modalData.api_key}
                onChange={(e) => setModalData({ ...modalData, api_key: e.target.value })}
                placeholder={
                  modalData.service === 'searxng'
                    ? 'https://your-searxng-instance.example.com'
                    : (editingKey ? 'Enter new key to update' : 'Enter API key')
                }
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded text-white"
              />
              {modalData.service === 'searxng' && (
                <p className="text-xs text-tsushin-slate mt-2">
                  Enter the base URL of your SearXNG instance. Tsushin will call `/search?format=json` on that host.
                </p>
              )}
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

      {/* (v0.7.x) The legacy flat `ProviderSetupWizard` picker has been
          replaced by the guided multi-step ProviderWizard mounted from
          `ProviderWizardProvider` at the app root (see layout.tsx). The
          ProviderInstanceModal below remains in place as the Advanced-mode
          fallback — it listens for the `tsushin:open-provider-advanced-modal`
          event dispatched by the new wizard footer. */}

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
        apiBase={publicIngress?.url || (typeof window !== 'undefined' ? window.location.origin : '')}
      />

      {/* v0.7.1: Webhook Rotate Secret Reveal Modal */}
      {webhookRotateModal && (
        <WebhookSecretRevealModal
          isOpen={webhookRotateModal.open}
          onClose={() => setWebhookRotateModal(null)}
          secret={webhookRotateModal.secret}
          inboundUrl={webhookRotateModal.inboundUrl}
          apiBase={publicIngress?.url || (typeof window !== 'undefined' ? window.location.origin : '')}
          rotatedNotice
        />
      )}

      {/* v0.7.1: Webhook Edit Modal */}
      <WebhookEditModal
        isOpen={webhookEditTarget !== null}
        onClose={() => setWebhookEditTarget(null)}
        onSaved={loadWebhookIntegrations}
        integration={webhookEditTarget}
        apiBase={publicIngress?.url || (typeof window !== 'undefined' ? window.location.origin : '')}
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

      {/* Ollama Setup Wizard — guided provision + model pull + agent assignment */}
      <OllamaSetupWizard
        isOpen={showOllamaSetupWizard}
        onClose={() => setShowOllamaSetupWizard(false)}
        onComplete={() => {
          setShowOllamaSetupWizard(false)
          toast.success('Ollama is ready — model pulled and agents wired')
          // Refresh provider instances and container status so the card reflects new state
          fetchOllamaHealth()
          refreshOllamaContainerStatus()
        }}
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

      {/* Kokoro Setup Wizard (v0.7.0 Hub-consolidated) */}
      {kokoroWizardOpen && (
        <KokoroSetupWizard
          isOpen={kokoroWizardOpen}
          onClose={() => handleKokoroWizardClose(false)}
          onComplete={() => handleKokoroWizardClose(true)}
        />
      )}

      {/* SearXNG delete confirmation */}
      {searxngConfirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
          <div className="bg-[#12121a] border border-white/10 rounded-xl w-full max-w-md">
            <div className="p-6">
              <h3 className="text-lg font-semibold text-white mb-2">Delete SearXNG instance?</h3>
              <p className="text-sm text-tsushin-slate mb-4">
                This will soft-delete the instance <span className="font-mono text-white">{searxngConfirmDelete.instance_name}</span> and (if auto-provisioned) stop the container.
              </p>
              <div className="mt-5 flex items-center justify-end gap-2">
                <button
                  onClick={() => setSearxngConfirmDelete(null)}
                  className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-tsushin-slate text-sm hover:bg-white/10"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSearxngDelete}
                  className="px-4 py-2 rounded-lg bg-tsushin-vermilion text-white text-sm font-medium hover:bg-red-400"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Kokoro delete confirmation */}
      {kokoroConfirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
          <div className="bg-[#12121a] border border-white/10 rounded-xl w-full max-w-md">
            <div className="p-6">
              <h3 className="text-lg font-semibold text-white mb-2">Delete Kokoro instance?</h3>
              <p className="text-sm text-tsushin-slate mb-4">
                This will soft-delete the instance and (if auto-provisioned) stop the container.
              </p>
              <label className="flex items-start gap-2 p-3 rounded-lg bg-tsushin-vermilion/5 border border-tsushin-vermilion/20 cursor-pointer">
                <input
                  type="checkbox"
                  checked={kokoroConfirmDelete.removeVolume}
                  onChange={e => setKokoroConfirmDelete({ ...kokoroConfirmDelete, removeVolume: e.target.checked })}
                  className="mt-0.5 accent-tsushin-vermilion"
                />
                <div>
                  <div className="text-sm text-white">Also remove container volume</div>
                  <div className="text-xs text-tsushin-vermilion mt-0.5">Permanent data loss — cached models and any voice files will be deleted.</div>
                </div>
              </label>
              <div className="mt-5 flex items-center justify-end gap-2">
                <button
                  onClick={() => setKokoroConfirmDelete(null)}
                  className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-tsushin-slate text-sm hover:bg-white/10"
                >
                  Cancel
                </button>
                <button
                  onClick={handleKokoroInstanceDelete}
                  className="px-4 py-2 rounded-lg bg-tsushin-vermilion text-white text-sm font-medium hover:bg-red-400"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Ollama delete confirmation — mirrors the Kokoro modal so the Delete
          action offered by <ManagedContainerPanel /> (and the host-mode
          action strip) feels identical across both services. */}
      {ollamaConfirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70">
          <div className="bg-[#12121a] border border-white/10 rounded-xl w-full max-w-md">
            <div className="p-6">
              <h3 className="text-lg font-semibold text-white mb-2">Delete Ollama instance?</h3>
              <p className="text-sm text-tsushin-slate mb-4">
                This will soft-delete the instance and (if auto-provisioned) stop the container.
              </p>
              <label className="flex items-start gap-2 p-3 rounded-lg bg-tsushin-vermilion/5 border border-tsushin-vermilion/20 cursor-pointer">
                <input
                  type="checkbox"
                  checked={ollamaConfirmDelete.removeVolume}
                  onChange={e => setOllamaConfirmDelete({ ...ollamaConfirmDelete, removeVolume: e.target.checked })}
                  className="mt-0.5 accent-tsushin-vermilion"
                />
                <div>
                  <div className="text-sm text-white">Also remove container volume</div>
                  <div className="text-xs text-tsushin-vermilion mt-0.5">Permanent data loss — pulled models will be deleted and must be re-downloaded.</div>
                </div>
              </label>
              <div className="mt-5 flex items-center justify-end gap-2">
                <button
                  onClick={() => setOllamaConfirmDelete(null)}
                  className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-tsushin-slate text-sm hover:bg-white/10"
                >
                  Cancel
                </button>
                <button
                  onClick={handleOllamaInstanceDelete}
                  className="px-4 py-2 rounded-lg bg-tsushin-vermilion text-white text-sm font-medium hover:bg-red-400"
                >
                  Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <AddIntegrationWizard
        isOpen={showSearchWizard}
        onClose={() => { setShowSearchWizard(false); setAddIntegrationInitialProvider(undefined) }}
        onComplete={() => { refreshSearxngInstances(); loadHubIntegrations() }}
        initialProviderId={addIntegrationInitialProvider as any}
      />

      {/* v0.7.0: guided wizards for Productivity + Communication tabs. Both
          are thin dispatchers — they pick a service/channel and hand off to
          the existing per-service sub-wizard / OAuth handler. */}
      <ProductivityWizard
        isOpen={showProductivityWizard}
        onClose={() => setShowProductivityWizard(false)}
        onServiceSelected={handleProductivityDispatch}
      />
      <ChannelsWizard
        key={channelsWizardSession}
        isOpen={showChannelsWizard}
        onClose={() => setShowChannelsWizard(false)}
        onChannelSelected={handleChannelsDispatch}
      />
      <TriggerWizard
        key={triggerWizardSession}
        isOpen={showTriggerWizard}
        onClose={() => setShowTriggerWizard(false)}
        onTriggerSelected={handleTriggerDispatch}
      />
      <EmailTriggerWizard
        isOpen={showEmailTriggerWizard}
        onClose={() => {
          setShowEmailTriggerWizard(false)
          setEditingEmailTrigger(null)
        }}
        onComplete={handleEmailTriggerComplete}
        triggerId={editingEmailTrigger?.id ?? null}
      />
      {triggerSetupTarget && (
        <TriggerSetupModal
          isOpen={triggerSetupTarget !== null}
          triggerType={triggerSetupTarget}
          onClose={() => setTriggerSetupTarget(null)}
          onSaved={handleBreadthTriggerComplete}
        />
      )}
    </div>
  )
}
