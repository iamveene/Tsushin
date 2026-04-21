'use client'

import { useMemo, useState } from 'react'
import Modal from '@/components/ui/Modal'
import {
  BeakerIcon,
  BotIcon,
  BrainIcon,
  CloudIcon,
  GeminiIcon,
  GlobeIcon,
  LightningIcon,
  MicrophoneIcon,
  OpenAIIcon,
  PlaneIcon,
  SearchIcon,
  type IconProps,
} from '@/components/ui/icons'

interface ProviderSetupWizardProps {
  isOpen: boolean
  initialVendor?: string
  onClose: () => void
  onAdvanced: (vendor?: string) => void
  onOpenOllama: () => void
  onOpenKokoro: () => void
  onOpenApiKey: (service: string) => void
  onOpenToolWizard: (providerId?: string) => void
}

type CategoryId = 'cloud' | 'local' | 'audio' | 'tools'

interface SetupOption {
  id: string
  label: string
  description: string
  Icon: React.FC<IconProps>
  actionLabel: string
  action: () => void
}

const cloudVendors: SetupOption[] = [
  { id: 'openai', label: 'OpenAI', description: 'Hosted GPT and OpenAI-compatible models.', Icon: OpenAIIcon, actionLabel: 'Configure', action: () => {} },
  { id: 'anthropic', label: 'Anthropic', description: 'Claude reasoning and chat models.', Icon: BrainIcon, actionLabel: 'Configure', action: () => {} },
  { id: 'gemini', label: 'Google Gemini', description: 'Google multimodal and text models.', Icon: GeminiIcon, actionLabel: 'Configure', action: () => {} },
  { id: 'vertex_ai', label: 'Vertex AI', description: 'Google Cloud Model Garden providers.', Icon: CloudIcon, actionLabel: 'Configure', action: () => {} },
  { id: 'groq', label: 'Groq', description: 'Low-latency hosted inference.', Icon: LightningIcon, actionLabel: 'Configure', action: () => {} },
  { id: 'grok', label: 'Grok (xAI)', description: 'xAI Grok model endpoints.', Icon: BrainIcon, actionLabel: 'Configure', action: () => {} },
  { id: 'deepseek', label: 'DeepSeek', description: 'Reasoning and chat endpoints.', Icon: BrainIcon, actionLabel: 'Configure', action: () => {} },
  { id: 'openrouter', label: 'OpenRouter', description: 'Many hosted models behind one API.', Icon: GlobeIcon, actionLabel: 'Configure', action: () => {} },
  { id: 'custom', label: 'Custom', description: 'OpenAI-compatible or custom endpoint.', Icon: BeakerIcon, actionLabel: 'Configure', action: () => {} },
]

export default function ProviderSetupWizard({
  isOpen,
  initialVendor,
  onClose,
  onAdvanced,
  onOpenOllama,
  onOpenKokoro,
  onOpenApiKey,
  onOpenToolWizard,
}: ProviderSetupWizardProps) {
  const initialCategory: CategoryId = initialVendor ? 'cloud' : 'cloud'
  const [category, setCategory] = useState<CategoryId>(initialCategory)

  const categories = useMemo(() => [
    { id: 'cloud' as CategoryId, label: 'Cloud/API LLM', description: 'Hosted LLM providers and OpenAI-compatible endpoints.', Icon: CloudIcon },
    { id: 'local' as CategoryId, label: 'Local LLM', description: 'Self-hosted model runtimes managed per tenant.', Icon: BotIcon },
    { id: 'audio' as CategoryId, label: 'Audio/TTS', description: 'Text-to-speech and voice generation providers.', Icon: MicrophoneIcon },
    { id: 'tools' as CategoryId, label: 'Web Search/Tool API', description: 'Search, travel, and tool-capability APIs.', Icon: SearchIcon },
  ], [])

  const options = useMemo<SetupOption[]>(() => {
    if (category === 'cloud') {
      return cloudVendors.map(option => ({
        ...option,
        action: () => onAdvanced(option.id),
      }))
    }
    if (category === 'local') {
      return [
        {
          id: 'ollama',
          label: 'Ollama',
          description: 'Provision a tenant-scoped local model container or connect host Ollama.',
          Icon: BotIcon,
          actionLabel: 'Open Wizard',
          action: onOpenOllama,
        },
      ]
    }
    if (category === 'audio') {
      return [
        {
          id: 'kokoro',
          label: 'Kokoro',
          description: 'Provision a self-hosted TTS container and optionally attach it to agents.',
          Icon: MicrophoneIcon,
          actionLabel: 'Open Wizard',
          action: onOpenKokoro,
        },
        {
          id: 'elevenlabs',
          label: 'ElevenLabs',
          description: 'Store an API key for hosted voice generation.',
          Icon: MicrophoneIcon,
          actionLabel: 'Configure Key',
          action: () => onOpenApiKey('elevenlabs'),
        },
      ]
    }
    return [
      {
        id: 'searxng',
        label: 'SearXNG',
        description: 'Provision or connect a self-hosted metasearch instance.',
        Icon: GlobeIcon,
        actionLabel: 'Open Wizard',
        action: () => onOpenToolWizard('searxng'),
      },
      {
        id: 'brave_search',
        label: 'Brave Search',
        description: 'Store a Brave Search API key.',
        Icon: SearchIcon,
        actionLabel: 'Configure Key',
        action: () => onOpenApiKey('brave_search'),
      },
      {
        id: 'tavily',
        label: 'Tavily',
        description: 'Store a Tavily web search API key.',
        Icon: GlobeIcon,
        actionLabel: 'Configure Key',
        action: () => onOpenApiKey('tavily'),
      },
      {
        id: 'google_flights',
        label: 'SerpAPI / Google Services',
        description: 'Configure Google Search and Flights through the integration wizard.',
        Icon: PlaneIcon,
        actionLabel: 'Open Wizard',
        action: () => onOpenToolWizard('google_flights'),
      },
    ]
  }, [category, onAdvanced, onOpenApiKey, onOpenKokoro, onOpenOllama, onOpenToolWizard])

  const runAction = (action: () => void) => {
    onClose()
    action()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Add Provider"
      size="xl"
      footer={
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
          <button
            onClick={() => {
              onClose()
              onAdvanced(initialVendor)
            }}
            className="btn-secondary"
          >
            Advanced Form
          </button>
          <button onClick={onClose} className="btn-ghost px-4 py-2">
            Cancel
          </button>
        </div>
      }
    >
      <div className="grid gap-5 lg:grid-cols-[220px_1fr]">
        <div className="space-y-2">
          {categories.map(item => {
            const Icon = item.Icon
            const active = item.id === category
            return (
              <button
                key={item.id}
                onClick={() => setCategory(item.id)}
                className={`w-full rounded-lg border px-3 py-3 text-left transition-colors ${
                  active
                    ? 'border-tsushin-accent bg-tsushin-accent/10'
                    : 'border-tsushin-border bg-tsushin-ink/40 hover:border-tsushin-accent/50'
                }`}
              >
                <span className="flex items-center gap-2 text-sm font-semibold text-white">
                  <Icon size={16} className={active ? 'text-tsushin-accent' : 'text-tsushin-slate'} />
                  {item.label}
                </span>
                <span className="mt-1 block text-xs text-tsushin-slate">{item.description}</span>
              </button>
            )
          })}
        </div>

        <div className="space-y-3">
          <div>
            <h3 className="text-sm font-semibold text-white">Choose what to add</h3>
            <p className="text-xs text-tsushin-slate">Guided setup opens the right flow for the provider type.</p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {options.map(option => {
              const Icon = option.Icon
              return (
                <div key={option.id} className="rounded-lg border border-tsushin-border bg-tsushin-ink/40 p-4">
                  <div className="mb-3 flex items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-tsushin-accent/10 text-tsushin-accent">
                      <Icon size={18} />
                    </div>
                    <div className="min-w-0">
                      <h4 className="text-sm font-semibold text-white">{option.label}</h4>
                      <p className="mt-1 text-xs text-tsushin-slate">{option.description}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => runAction(option.action)}
                    className="w-full rounded-lg bg-tsushin-accent/15 px-3 py-2 text-xs font-medium text-tsushin-accent transition-colors hover:bg-tsushin-accent/25 hover:text-white"
                  >
                    {option.actionLabel}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </Modal>
  )
}
