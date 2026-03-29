'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { api, ProviderInstance, ProviderInstanceCreate } from '@/lib/client'
import Modal from '@/components/ui/Modal'
import {
  CheckCircleIcon,
  AlertTriangleIcon,
  SearchIcon,
  LightningIcon,
} from '@/components/ui/icons'

interface Props {
  isOpen: boolean
  onClose: () => void
  onSave: () => void
  instance?: ProviderInstance | null
  defaultVendor?: string
}

const VENDORS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'groq', label: 'Groq' },
  { value: 'grok', label: 'Grok (xAI)' },
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'elevenlabs', label: 'ElevenLabs' },
  { value: 'ollama', label: 'Ollama' },
  { value: 'custom', label: 'Custom' },
]

const VENDOR_DEFAULT_URLS: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  anthropic: 'https://api.anthropic.com',
  gemini: 'https://generativelanguage.googleapis.com',
  groq: 'https://api.groq.com/openai/v1',
  grok: 'https://api.x.ai/v1',
  openrouter: 'https://openrouter.ai/api/v1',
  deepseek: 'https://api.deepseek.com',
  elevenlabs: 'https://api.elevenlabs.io/v1',
  ollama: 'http://localhost:11434',
  custom: '',
}

export default function ProviderInstanceModal({ isOpen, onClose, onSave, instance, defaultVendor }: Props) {
  const isEditing = !!instance

  const [vendor, setVendor] = useState('openai')
  const [instanceName, setInstanceName] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [models, setModels] = useState<string[]>([])
  const [modelInput, setModelInput] = useState('')
  const [isDefault, setIsDefault] = useState(false)

  // Validation states
  const [urlValidation, setUrlValidation] = useState<{ valid: boolean; error?: string } | null>(null)
  const [urlValidating, setUrlValidating] = useState(false)
  const urlDebounceRef = useRef<NodeJS.Timeout | null>(null)

  // Connection test states
  const [testResult, setTestResult] = useState<{ success: boolean; message: string; latency_ms?: number } | null>(null)
  const [testing, setTesting] = useState(false)

  // Model discovery
  const [discovering, setDiscovering] = useState(false)

  // Saving state
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Initialize form when instance changes or modal opens
  useEffect(() => {
    if (!isOpen) return

    if (instance) {
      setVendor(instance.vendor)
      setInstanceName(instance.instance_name)
      setBaseUrl(instance.base_url || '')
      setApiKey('')
      setShowApiKey(false)
      setModels(instance.available_models || [])
      setIsDefault(instance.is_default)
    } else {
      setVendor(defaultVendor || 'openai')
      setInstanceName('')
      setBaseUrl('')
      setApiKey('')
      setShowApiKey(false)
      setModels([])
      setModelInput('')
      setIsDefault(false)
    }

    setUrlValidation(null)
    setTestResult(null)
    setError(null)
  }, [isOpen, instance])

  // Debounced URL validation
  const validateUrl = useCallback((url: string) => {
    if (urlDebounceRef.current) {
      clearTimeout(urlDebounceRef.current)
    }

    if (!url.trim()) {
      setUrlValidation(null)
      setUrlValidating(false)
      return
    }

    setUrlValidating(true)
    urlDebounceRef.current = setTimeout(async () => {
      try {
        const result = await api.validateProviderUrl(url)
        setUrlValidation(result)
      } catch {
        setUrlValidation({ valid: false, error: 'Failed to validate URL' })
      } finally {
        setUrlValidating(false)
      }
    }, 600)
  }, [])

  const handleBaseUrlChange = (value: string) => {
    setBaseUrl(value)
    validateUrl(value)
  }

  const addModel = () => {
    const model = modelInput.trim()
    if (model && !models.includes(model)) {
      setModels([...models, model])
      setModelInput('')
    }
  }

  const removeModel = (model: string) => {
    setModels(models.filter(m => m !== model))
  }

  const handleDiscoverModels = async () => {
    if (!instance) return
    setDiscovering(true)
    try {
      const discovered = await api.discoverProviderModels(instance.id)
      setModels(discovered)
    } catch (err: any) {
      setError(err.message || 'Failed to discover models')
    } finally {
      setDiscovering(false)
    }
  }

  const handleTestConnection = async () => {
    if (!instance) return
    setTesting(true)
    setTestResult(null)
    try {
      const result = await api.testProviderConnection(instance.id)
      setTestResult(result)
    } catch (err: any) {
      setTestResult({ success: false, message: err.message || 'Test failed' })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (!instanceName.trim()) {
      setError('Instance name is required')
      return
    }

    setSaving(true)
    setError(null)
    try {
      if (isEditing && instance) {
        const updateData: Partial<ProviderInstanceCreate> = {
          instance_name: instanceName,
          base_url: baseUrl || undefined,
          available_models: models,
          is_default: isDefault,
        }
        if (apiKey) {
          updateData.api_key = apiKey
        }
        await api.updateProviderInstance(instance.id, updateData)
      } else {
        const createData: ProviderInstanceCreate = {
          vendor,
          instance_name: instanceName,
          base_url: baseUrl || undefined,
          api_key: apiKey || undefined,
          available_models: models,
          is_default: isDefault,
        }
        await api.createProviderInstance(createData)
      }
      onSave()
      onClose()
    } catch (err: any) {
      setError(err.message || 'Failed to save provider instance')
    } finally {
      setSaving(false)
    }
  }

  const footer = (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        {isEditing && instance && (
          <button
            onClick={handleTestConnection}
            disabled={testing}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-tsushin-accent/30 text-tsushin-accent bg-tsushin-accent/5 hover:bg-tsushin-accent/10 transition-colors disabled:opacity-50"
          >
            <LightningIcon size={14} />
            {testing ? 'Testing...' : 'Test Connection'}
          </button>
        )}
        {testResult && (
          <span className={`text-xs flex items-center gap-1.5 ${testResult.success ? 'text-tsushin-success' : 'text-tsushin-vermilion'}`}>
            {testResult.success ? <CheckCircleIcon size={14} /> : <AlertTriangleIcon size={14} />}
            {testResult.message}
            {testResult.latency_ms !== undefined && testResult.success && (
              <span className="text-tsushin-slate ml-1">({testResult.latency_ms}ms)</span>
            )}
          </span>
        )}
      </div>
      <div className="flex gap-3">
        <button
          onClick={onClose}
          className="px-4 py-2 text-sm font-medium rounded-lg border border-tsushin-border text-tsushin-slate hover:text-white hover:border-white/20 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={saving || !instanceName.trim()}
          className="btn-primary px-5 py-2 text-sm font-medium rounded-lg disabled:opacity-50"
        >
          {saving ? 'Saving...' : (isEditing ? 'Update Instance' : 'Create Instance')}
        </button>
      </div>
    </div>
  )

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={isEditing ? 'Edit Provider Instance' : 'New Provider Instance'}
      size="lg"
      footer={footer}
    >
      <div className="space-y-5">
        {error && (
          <div className="bg-tsushin-vermilion/10 border border-tsushin-vermilion/30 rounded-lg p-3 flex items-center gap-2">
            <AlertTriangleIcon size={16} className="text-tsushin-vermilion shrink-0" />
            <p className="text-sm text-tsushin-vermilion">{error}</p>
          </div>
        )}

        {/* Vendor */}
        <div>
          <label className="block text-sm font-medium text-tsushin-fog mb-1.5">Vendor</label>
          <select
            value={vendor}
            onChange={(e) => {
              setVendor(e.target.value)
              setBaseUrl('')
              setUrlValidation(null)
            }}
            disabled={isEditing}
            className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {VENDORS.map(v => (
              <option key={v.value} value={v.value}>{v.label}</option>
            ))}
          </select>
          {isEditing && (
            <p className="text-xs text-tsushin-slate mt-1">Vendor cannot be changed after creation</p>
          )}
        </div>

        {/* Instance Name */}
        <div>
          <label className="block text-sm font-medium text-tsushin-fog mb-1.5">Instance Name <span className="text-tsushin-vermilion">*</span></label>
          <input
            type="text"
            value={instanceName}
            onChange={(e) => setInstanceName(e.target.value)}
            placeholder={`e.g., ${vendor}-production, ${vendor}-dev`}
            className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50"
          />
        </div>

        {/* Base URL */}
        <div>
          <label className="block text-sm font-medium text-tsushin-fog mb-1.5">Base URL <span className="text-tsushin-slate text-xs font-normal">(Optional)</span></label>
          <div className="relative">
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => handleBaseUrlChange(e.target.value)}
              placeholder={VENDOR_DEFAULT_URLS[vendor] || 'https://...'}
              className={`w-full px-3 py-2 border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50 pr-10 ${
                urlValidation
                  ? urlValidation.valid
                    ? 'border-tsushin-success/50'
                    : 'border-tsushin-vermilion/50'
                  : 'border-tsushin-border'
              }`}
            />
            {urlValidating && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                <div className="w-4 h-4 rounded-full border-2 border-tsushin-accent/30 border-t-tsushin-accent animate-spin" />
              </div>
            )}
            {!urlValidating && urlValidation && (
              <div className="absolute right-3 top-1/2 -translate-y-1/2">
                {urlValidation.valid
                  ? <CheckCircleIcon size={16} className="text-tsushin-success" />
                  : <AlertTriangleIcon size={16} className="text-tsushin-vermilion" />
                }
              </div>
            )}
          </div>
          {urlValidation && !urlValidation.valid && urlValidation.error && (
            <p className="text-xs text-tsushin-vermilion mt-1">{urlValidation.error}</p>
          )}
          {!baseUrl && (
            <p className="text-xs text-tsushin-slate mt-1">Leave empty to use vendor default: {VENDOR_DEFAULT_URLS[vendor] || 'N/A'}</p>
          )}
        </div>

        {/* API Key */}
        <div>
          <label className="block text-sm font-medium text-tsushin-fog mb-1.5">API Key</label>
          {isEditing && instance?.api_key_configured && !apiKey && (
            <p className="text-xs text-tsushin-slate mb-1.5">
              Current key: <span className="font-mono text-tsushin-accent">{instance.api_key_preview}</span> -- Enter a new key below to replace it
            </p>
          )}
          <div className="relative">
            <input
              type={showApiKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={isEditing ? 'Enter new key to replace...' : 'sk-...'}
              className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50 pr-10 font-mono text-sm"
            />
            <button
              type="button"
              onClick={() => setShowApiKey(!showApiKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-tsushin-slate hover:text-white transition-colors"
              title={showApiKey ? 'Hide' : 'Reveal'}
            >
              {showApiKey ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                  <line x1="1" y1="1" x2="23" y2="23" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Models */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-sm font-medium text-tsushin-fog">Models</label>
            {isEditing && instance && (
              <button
                onClick={handleDiscoverModels}
                disabled={discovering}
                className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md border border-tsushin-accent/30 text-tsushin-accent bg-tsushin-accent/5 hover:bg-tsushin-accent/10 transition-colors disabled:opacity-50"
              >
                <SearchIcon size={12} />
                {discovering ? 'Discovering...' : 'Auto-detect'}
              </button>
            )}
          </div>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={modelInput}
              onChange={(e) => setModelInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addModel()
                }
              }}
              placeholder="Add model name..."
              className="flex-1 px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50 text-sm"
            />
            <button
              onClick={addModel}
              disabled={!modelInput.trim()}
              className="px-3 py-2 text-sm font-medium rounded-lg border border-tsushin-border text-tsushin-fog hover:text-white hover:border-white/20 transition-colors disabled:opacity-30"
            >
              Add
            </button>
          </div>
          {models.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {models.map(model => (
                <span
                  key={model}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-tsushin-indigo/10 text-tsushin-indigo border border-tsushin-indigo/20 rounded-md text-xs font-mono"
                >
                  {model}
                  <button
                    onClick={() => removeModel(model)}
                    className="text-tsushin-indigo/60 hover:text-tsushin-indigo transition-colors"
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <p className="text-xs text-tsushin-slate">
              {isEditing ? 'No models configured. Use Auto-detect to discover available models.' : 'Add models manually or use Auto-detect after creation.'}
            </p>
          )}
        </div>

        {/* Default Instance */}
        <label className="flex items-center gap-3 cursor-pointer p-3 bg-tsushin-ink rounded-lg border border-tsushin-border hover:border-white/15 transition-colors">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
            className="w-4 h-4 rounded accent-tsushin-indigo"
          />
          <div>
            <div className="text-sm font-medium text-white">Default instance</div>
            <div className="text-xs text-tsushin-slate">
              Set as the default instance for {VENDORS.find(v => v.value === vendor)?.label || vendor}. Only one instance per vendor can be the default.
            </div>
          </div>
        </label>
      </div>
    </Modal>
  )
}
