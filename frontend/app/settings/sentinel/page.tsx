'use client'

/**
 * Sentinel Security Settings Page - Phase 20
 *
 * Configure the AI-powered Sentinel Security Agent:
 * - Toggle security analysis components
 * - Configure detection types and aggressiveness
 * - Configure LLM settings for analysis
 * - View and customize analysis prompts
 */

import { useState, useEffect, useCallback } from 'react'
import { useRequireAuth } from '@/contexts/AuthContext'
import { api, SentinelConfig, SentinelConfigUpdate, SentinelPrompt, SentinelLLMProvider, SentinelStats, SentinelException, SentinelExceptionCreate, SentinelExceptionUpdate, Contact } from '@/lib/client'
import Link from 'next/link'
import {
  SettingsIcon,
  DocumentIcon,
  BotIcon,
  ChartBarIcon,
  CheckCircleIcon,
  MessageIcon,
  LinkIcon,
  PhoneIcon,
  PlayIcon,
  PauseIcon,
  EditIcon,
  TrashIcon,
} from '@/components/ui/icons'

type TabType = 'general' | 'prompts' | 'llm' | 'stats' | 'exceptions'

export default function SentinelSettingsPage() {
  const { user, loading: authLoading, hasPermission } = useRequireAuth()
  const canEdit = hasPermission('org.settings.write')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabType>('general')

  // Config state
  const [config, setConfig] = useState<SentinelConfig | null>(null)
  const [prompts, setPrompts] = useState<SentinelPrompt[]>([])
  const [providers, setProviders] = useState<SentinelLLMProvider[]>([])
  const [stats, setStats] = useState<SentinelStats | null>(null)
  const [exceptions, setExceptions] = useState<SentinelException[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])

  // Channel toggles (WhatsApp is currently the only supported channel)
  const [whatsappEnabled, setWhatsappEnabled] = useState(true)

  // Form state
  const [formState, setFormState] = useState<SentinelConfigUpdate>({})

  // Exception modal state
  const [showExceptionModal, setShowExceptionModal] = useState(false)
  const [editingException, setEditingException] = useState<SentinelException | null>(null)
  const [exceptionForm, setExceptionForm] = useState<SentinelExceptionCreate>({
    name: '',
    exception_type: 'network_target',
    pattern: '',
    match_mode: 'exact',
    detection_types: '*',
    action: 'skip_llm',
    priority: 100,
  })
  const [savingException, setSavingException] = useState(false)
  const [testingException, setTestingException] = useState<number | null>(null)
  const [exceptionTestContent, setExceptionTestContent] = useState('')
  const [exceptionTestResult, setExceptionTestResult] = useState<any>(null)

  // Prompt editing state
  const [editingPrompt, setEditingPrompt] = useState<string | null>(null)
  const [promptText, setPromptText] = useState('')

  // LLM test state
  const [testingLLM, setTestingLLM] = useState(false)
  const [llmTestResult, setLLMTestResult] = useState<string | null>(null)

  // Analysis test state
  const [testInput, setTestInput] = useState('')
  const [testDetectionType, setTestDetectionType] = useState('prompt_injection')
  const [testingAnalysis, setTestingAnalysis] = useState(false)
  const [testResult, setTestResult] = useState<any>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [configData, providersData, statsData, contactsData] = await Promise.all([
        api.getSentinelConfig(),
        api.getSentinelLLMProviders(),
        api.getSentinelStats(7),
        api.getContacts(),
      ])

      setConfig(configData)
      setProviders(providersData)
      setStats(statsData)
      setContacts(contactsData)

      // Initialize WhatsApp toggle based on whether a recipient is set
      setWhatsappEnabled(!!configData.notification_recipient)

      // Initialize form state from config
      setFormState({
        is_enabled: configData.is_enabled,
        enable_prompt_analysis: configData.enable_prompt_analysis,
        enable_tool_analysis: configData.enable_tool_analysis,
        enable_shell_analysis: configData.enable_shell_analysis,
        detect_prompt_injection: configData.detect_prompt_injection,
        detect_agent_takeover: configData.detect_agent_takeover,
        detect_poisoning: configData.detect_poisoning,
        detect_shell_malicious_intent: configData.detect_shell_malicious_intent,
        aggressiveness_level: configData.aggressiveness_level,
        llm_provider: configData.llm_provider,
        llm_model: configData.llm_model,
        llm_max_tokens: configData.llm_max_tokens,
        llm_temperature: configData.llm_temperature,
        cache_ttl_seconds: configData.cache_ttl_seconds,
        timeout_seconds: configData.timeout_seconds,
        block_on_detection: configData.block_on_detection,
        log_all_analyses: configData.log_all_analyses,
        // Phase 20 Enhancement
        detection_mode: configData.detection_mode,
        enable_slash_command_analysis: configData.enable_slash_command_analysis,
        // Notification settings
        enable_notifications: configData.enable_notifications,
        notification_on_block: configData.notification_on_block,
        notification_on_detect: configData.notification_on_detect,
        notification_recipient: configData.notification_recipient,
        notification_message_template: configData.notification_message_template,
      })
    } catch (err: any) {
      console.error('Failed to fetch Sentinel config:', err)
      setError(err.message || 'Failed to load Sentinel settings')
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchPrompts = useCallback(async () => {
    try {
      const promptsData = await api.getSentinelPrompts()
      setPrompts(promptsData)
    } catch (err: any) {
      console.error('Failed to fetch prompts:', err)
    }
  }, [])

  const fetchExceptions = useCallback(async () => {
    try {
      const exceptionsData = await api.getSentinelExceptions()
      setExceptions(exceptionsData)
    } catch (err: any) {
      console.error('Failed to fetch exceptions:', err)
    }
  }, [])

  useEffect(() => {
    if (!authLoading && user) {
      fetchData()
    }
  }, [fetchData, authLoading, user])

  useEffect(() => {
    if (activeTab === 'prompts') {
      fetchPrompts()
    }
    if (activeTab === 'exceptions') {
      fetchExceptions()
    }
  }, [activeTab, fetchPrompts, fetchExceptions])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const updated = await api.updateSentinelConfig(formState)
      setConfig(updated)
      setSuccess('Sentinel settings saved successfully')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  const handleTestLLM = async () => {
    setTestingLLM(true)
    setLLMTestResult(null)
    try {
      const result = await api.testSentinelLLMConnection(
        formState.llm_provider || config?.llm_provider || 'gemini',
        formState.llm_model || config?.llm_model || 'gemini-2.0-flash-lite'
      )
      setLLMTestResult(result.success ? `Success (${result.response_time_ms}ms): ${result.message}` : `Failed: ${result.message}`)
    } catch (err: any) {
      setLLMTestResult(`Error: ${err.message}`)
    } finally {
      setTestingLLM(false)
    }
  }

  const handleTestAnalysis = async () => {
    if (!testInput.trim()) return
    setTestingAnalysis(true)
    setTestResult(null)
    try {
      const result = await api.testSentinelAnalysis(testInput, testDetectionType)
      setTestResult(result)
    } catch (err: any) {
      setTestResult({ error: err.message })
    } finally {
      setTestingAnalysis(false)
    }
  }

  const handleSavePrompt = async (detectionType: string) => {
    setSaving(true)
    try {
      await api.updateSentinelPrompt(detectionType, promptText || null)
      setEditingPrompt(null)
      setPromptText('')
      await fetchPrompts()
      setSuccess('Prompt updated successfully')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err: any) {
      setError(err.message || 'Failed to save prompt')
    } finally {
      setSaving(false)
    }
  }

  const aggressivenessLabels = ['Off', 'Moderate', 'Aggressive', 'Extra Aggressive']

  if (authLoading || loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-center py-12">
          <div className="text-center">
            <div className="relative w-12 h-12 mx-auto mb-4">
              <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
              <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
            </div>
            <p className="text-tsushin-slate font-medium">Loading Sentinel settings...</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Sentinel Security Agent
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            AI-powered security layer that detects prompt injection, agent takeover, and malicious shell intent
          </p>
        </div>

        {/* Back to Settings */}
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Settings
        </Link>

        {/* Messages */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <p className="text-red-800 dark:text-red-200">{error}</p>
          </div>
        )}
        {success && (
          <div className="mb-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
            <p className="text-green-800 dark:text-green-200">{success}</p>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="flex space-x-1 glass-card rounded-xl p-1 mb-6">
          {[
            { id: 'general', label: 'General', Icon: SettingsIcon },
            { id: 'prompts', label: 'Analysis Prompts', Icon: DocumentIcon },
            { id: 'llm', label: 'LLM Configuration', Icon: BotIcon },
            { id: 'stats', label: 'Statistics', Icon: ChartBarIcon },
            { id: 'exceptions', label: 'Exceptions', Icon: CheckCircleIcon },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as TabType)}
              className={`flex-1 py-3 px-4 rounded-lg font-medium transition-all flex items-center justify-center gap-2 ${
                activeTab === tab.id
                  ? 'bg-teal-500/20 text-teal-400 border border-teal-500/50'
                  : 'text-tsushin-slate hover:text-white hover:bg-tsushin-dark/30'
              }`}
            >
              <tab.Icon size={16} /> {tab.label}
            </button>
          ))}
        </div>

        {/* General Tab */}
        {activeTab === 'general' && (
          <div className="space-y-6">
            {/* Master Toggle */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                      Sentinel Protection
                    </h3>
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      Enable AI-powered security analysis
                    </p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formState.is_enabled ?? false}
                      onChange={(e) => setFormState({ ...formState, is_enabled: e.target.checked })}
                      disabled={!canEdit}
                      className="sr-only peer"
                    />
                    <div className="w-14 h-7 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-teal-300 dark:peer-focus:ring-teal-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[4px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all dark:border-gray-600 peer-checked:bg-teal-600"></div>
                  </label>
                </div>
              </div>

              {/* Component Toggles */}
              <div className="p-6 space-y-4">
                <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-4">Analysis Components</h4>

                {[
                  { key: 'enable_prompt_analysis', label: 'Prompt Analysis', desc: 'Analyze user messages for injection attempts' },
                  { key: 'enable_tool_analysis', label: 'Tool Analysis', desc: 'Analyze tool arguments for malicious patterns' },
                  { key: 'enable_shell_analysis', label: 'Shell Analysis', desc: 'Analyze shell commands for malicious intent' },
                  { key: 'enable_slash_command_analysis', label: 'Slash Command Analysis', desc: 'Analyze slash commands (/invoke, /shell) for threats (disable to bypass Sentinel for trusted commands)' },
                ].map((toggle) => (
                  <div key={toggle.key} className="flex items-center justify-between py-2">
                    <div>
                      <p className="font-medium text-gray-900 dark:text-gray-100">{toggle.label}</p>
                      <p className="text-sm text-gray-500 dark:text-gray-400">{toggle.desc}</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={(formState as any)[toggle.key] ?? false}
                        onChange={(e) => setFormState({ ...formState, [toggle.key]: e.target.checked })}
                        disabled={!canEdit}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-teal-600"></div>
                    </label>
                  </div>
                ))}
              </div>
            </div>

            {/* Detection Mode - Phase 20 Enhancement */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Detection Mode
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Control how Sentinel responds to detected threats
                </p>
              </div>
              <div className="p-6">
                <div className="space-y-3">
                  {[
                    { value: 'block', label: 'Block', desc: 'Analyze and block detected threats (recommended)', color: 'red' },
                    { value: 'warn_only', label: 'Warn Only', desc: 'Analyze and flag threats without blocking', color: 'orange' },
                    { value: 'detect_only', label: 'Detect Only', desc: 'Analyze and log threats silently (audit mode)', color: 'yellow' },
                    { value: 'off', label: 'Off', desc: 'Disable Sentinel analysis entirely', color: 'gray' },
                  ].map((mode) => (
                    <label
                      key={mode.value}
                      className={`flex items-start gap-4 p-4 rounded-lg border-2 cursor-pointer transition-all ${
                        formState.detection_mode === mode.value
                          ? mode.color === 'red' ? 'border-red-500 bg-red-50 dark:bg-red-900/10' :
                            mode.color === 'orange' ? 'border-orange-500 bg-orange-50 dark:bg-orange-900/10' :
                            mode.color === 'yellow' ? 'border-yellow-500 bg-yellow-50 dark:bg-yellow-900/10' :
                            'border-gray-500 bg-gray-50 dark:bg-gray-900/10'
                          : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                      }`}
                    >
                      <input
                        type="radio"
                        name="detection_mode"
                        value={mode.value}
                        checked={formState.detection_mode === mode.value}
                        onChange={(e) => setFormState({ ...formState, detection_mode: e.target.value as any })}
                        disabled={!canEdit}
                        className="mt-1"
                      />
                      <div>
                        <p className="font-medium text-gray-900 dark:text-gray-100">{mode.label}</p>
                        <p className="text-sm text-gray-500 dark:text-gray-400">{mode.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>
                {formState.detection_mode === 'off' && (
                  <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                    <p className="text-sm text-red-800 dark:text-red-200">
                      Warning: Sentinel analysis is disabled. Your agents are not protected from prompt injection and other threats.
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Detection Types */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Detection Types
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Choose which threat types to detect
                </p>
              </div>
              <div className="p-6 space-y-4">
                {[
                  { key: 'detect_prompt_injection', label: 'Prompt Injection', desc: 'Attempts to override AI instructions', severity: 'high' },
                  { key: 'detect_agent_takeover', label: 'Agent Takeover', desc: 'Attempts to hijack agent identity', severity: 'high' },
                  { key: 'detect_poisoning', label: 'Poisoning Attacks', desc: 'Gradual manipulation patterns', severity: 'medium' },
                  { key: 'detect_shell_malicious_intent', label: 'Shell Malicious Intent', desc: 'Malicious shell command patterns', severity: 'critical' },
                ].map((detection) => (
                  <div key={detection.key} className="flex items-center justify-between py-2">
                    <div className="flex items-center gap-3">
                      <span className={`px-2 py-1 text-xs rounded-full ${
                        detection.severity === 'critical' ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400' :
                        detection.severity === 'high' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400' :
                        'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400'
                      }`}>
                        {detection.severity}
                      </span>
                      <div>
                        <p className="font-medium text-gray-900 dark:text-gray-100">{detection.label}</p>
                        <p className="text-sm text-gray-500 dark:text-gray-400">{detection.desc}</p>
                      </div>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={(formState as any)[detection.key] ?? false}
                        onChange={(e) => setFormState({ ...formState, [detection.key]: e.target.checked })}
                        disabled={!canEdit}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-gray-200 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-teal-600"></div>
                    </label>
                  </div>
                ))}
              </div>
            </div>

            {/* Aggressiveness Slider */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Aggressiveness Level
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Higher levels detect more threats but may have more false positives
                </p>
              </div>
              <div className="p-6">
                <div className="flex items-center justify-between mb-4">
                  {aggressivenessLabels.map((label, index) => (
                    <span
                      key={label}
                      className={`text-sm ${
                        formState.aggressiveness_level === index
                          ? 'text-teal-400 font-medium'
                          : 'text-gray-400'
                      }`}
                    >
                      {label}
                    </span>
                  ))}
                </div>
                <input
                  type="range"
                  min="0"
                  max="3"
                  value={formState.aggressiveness_level ?? 1}
                  onChange={(e) => setFormState({ ...formState, aggressiveness_level: parseInt(e.target.value) })}
                  disabled={!canEdit}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
                />
              </div>
            </div>

            {/* Action Settings */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Action Settings
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div className="flex items-center justify-between py-2">
                  <div>
                    <p className="font-medium text-gray-900 dark:text-gray-100">Log All Analyses</p>
                    <p className="text-sm text-gray-500 dark:text-gray-400">Log all analyses including allowed messages (increases storage)</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formState.log_all_analyses ?? false}
                      onChange={(e) => setFormState({ ...formState, log_all_analyses: e.target.checked })}
                      disabled={!canEdit}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-gray-200 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-teal-600"></div>
                  </label>
                </div>
              </div>
            </div>

            {/* Notification Settings */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  User Notifications
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Customize notifications sent to users when threats are detected
                </p>
              </div>
              <div className="p-6 space-y-6">
                {/* Enable Notifications Toggle */}
                <div className="flex items-center justify-between">
                  <div>
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Enable Notifications
                    </label>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Send notifications to users when security events occur
                    </p>
                  </div>
                  <button
                    onClick={() => setFormState({ ...formState, enable_notifications: !formState.enable_notifications })}
                    disabled={!canEdit}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      formState.enable_notifications ? 'bg-teal-600' : 'bg-gray-300 dark:bg-gray-600'
                    } ${!canEdit ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        formState.enable_notifications ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>

                {/* Conditional notification options */}
                {formState.enable_notifications && (
                  <>
                    {/* Notify on Block Toggle */}
                    <div className="flex items-center justify-between pl-4 border-l-2 border-teal-500">
                      <div>
                        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                          Notify on Block
                        </label>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          Send notification when a message is blocked
                        </p>
                      </div>
                      <button
                        onClick={() => setFormState({ ...formState, notification_on_block: !formState.notification_on_block })}
                        disabled={!canEdit}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          formState.notification_on_block ? 'bg-teal-600' : 'bg-gray-300 dark:bg-gray-600'
                        } ${!canEdit ? 'opacity-50 cursor-not-allowed' : ''}`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            formState.notification_on_block ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>

                    {/* Notify on Detect Toggle */}
                    <div className="flex items-center justify-between pl-4 border-l-2 border-teal-500">
                      <div>
                        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                          Notify on Detect
                        </label>
                        <p className="text-xs text-gray-500 dark:text-gray-400">
                          Send notification when a threat is detected (even if not blocked)
                        </p>
                      </div>
                      <button
                        onClick={() => setFormState({ ...formState, notification_on_detect: !formState.notification_on_detect })}
                        disabled={!canEdit}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          formState.notification_on_detect ? 'bg-teal-600' : 'bg-gray-300 dark:bg-gray-600'
                        } ${!canEdit ? 'opacity-50 cursor-not-allowed' : ''}`}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                            formState.notification_on_detect ? 'translate-x-6' : 'translate-x-1'
                          }`}
                        />
                      </button>
                    </div>

                    {/* Notification Recipient */}
                    <div className="pl-4 border-l-2 border-teal-500">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Notification Recipient (Optional)
                      </label>
                      <select
                        value={formState.notification_recipient || ''}
                        onChange={(e) => setFormState({ ...formState, notification_recipient: e.target.value || null })}
                        disabled={!canEdit}
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 text-sm focus:ring-teal-500 focus:border-teal-500"
                      >
                        <option value="">Notify sender (default)</option>
                        {contacts
                          .filter(c => c.whatsapp_id) // Only show contacts with WhatsApp
                          .map(contact => (
                            <option key={contact.id} value={contact.whatsapp_id}>
                              {contact.friendly_name} {contact.phone_number ? `(${contact.phone_number})` : ''}
                            </option>
                          ))
                        }
                      </select>
                      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        Leave empty to notify the sender. Select a contact to send alerts to a specific recipient.
                      </p>
                    </div>

                    {/* Notification Channels */}
                    <div className="pl-4 border-l-2 border-teal-500">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                        Notification Channels
                      </label>

                      {/* WhatsApp Channel Toggle */}
                      <div className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                        <div className="flex items-center gap-3">
                          <MessageIcon size={20} className="text-green-500" />
                          <div>
                            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                              WhatsApp
                            </label>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              Send notifications via WhatsApp
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => setWhatsappEnabled(!whatsappEnabled)}
                          disabled={!canEdit}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                            whatsappEnabled ? 'bg-green-600' : 'bg-gray-300 dark:bg-gray-600'
                          } ${!canEdit ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                              whatsappEnabled ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </div>

                      {/* Future channels placeholder */}
                      <div className="mt-2 flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg opacity-50">
                        <div className="flex items-center gap-3">
                          <LinkIcon size={20} className="text-blue-500" />
                          <div>
                            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                              Webhook
                            </label>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              Coming soon
                            </p>
                          </div>
                        </div>
                        <span className="text-xs text-gray-400 dark:text-gray-500 px-2 py-1 bg-gray-200 dark:bg-gray-600 rounded">
                          Soon
                        </span>
                      </div>

                      <div className="mt-2 flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg opacity-50">
                        <div className="flex items-center gap-3">
                          <PhoneIcon size={20} className="text-sky-500" />
                          <div>
                            <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                              Telegram
                            </label>
                            <p className="text-xs text-gray-500 dark:text-gray-400">
                              Coming soon
                            </p>
                          </div>
                        </div>
                        <span className="text-xs text-gray-400 dark:text-gray-500 px-2 py-1 bg-gray-200 dark:bg-gray-600 rounded">
                          Soon
                        </span>
                      </div>
                    </div>

                    {/* Custom Message Template */}
                    <div className="pl-4 border-l-2 border-teal-500">
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Custom Message Template (Optional)
                      </label>
                      <textarea
                        value={formState.notification_message_template || ''}
                        onChange={(e) => setFormState({ ...formState, notification_message_template: e.target.value || null })}
                        disabled={!canEdit}
                        rows={4}
                        placeholder="🛡️ Security Notice

Your message was flagged by our security system.
Action: {action}
Reason: {reason}

If you believe this is an error, please contact support."
                        className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 font-mono text-sm focus:ring-teal-500 focus:border-teal-500"
                      />
                      <p className="mt-1 text-xs text-gray-500">
                        Variables: {'{detection_type}'}, {'{action}'}, {'{reason}'}, {'{score}'}, {'{sender_key}'}
                      </p>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Save Button */}
            {canEdit && (
              <div className="flex justify-end">
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-6 py-2 bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-lg disabled:opacity-50 transition-colors"
                >
                  {saving ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            )}

            {/* Test Analysis */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Test Analysis
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Test Sentinel analysis on sample input
                </p>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Detection Type
                  </label>
                  <select
                    value={testDetectionType}
                    onChange={(e) => setTestDetectionType(e.target.value)}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  >
                    <option value="prompt_injection">Prompt Injection</option>
                    <option value="agent_takeover">Agent Takeover</option>
                    <option value="poisoning">Poisoning</option>
                    <option value="shell_malicious">Shell Malicious Intent</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Test Input
                  </label>
                  <textarea
                    value={testInput}
                    onChange={(e) => setTestInput(e.target.value)}
                    rows={3}
                    placeholder="Enter text to analyze..."
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                </div>
                <button
                  onClick={handleTestAnalysis}
                  disabled={testingAnalysis || !testInput.trim()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md disabled:opacity-50 transition-colors"
                >
                  {testingAnalysis ? 'Analyzing...' : 'Test Analysis'}
                </button>

                {testResult && (
                  <div className={`mt-4 p-4 rounded-lg ${
                    testResult.error ? 'bg-red-50 dark:bg-red-900/20' :
                    testResult.is_threat_detected ? 'bg-orange-50 dark:bg-orange-900/20' :
                    'bg-green-50 dark:bg-green-900/20'
                  }`}>
                    {testResult.error ? (
                      <p className="text-red-800 dark:text-red-200">Error: {testResult.error}</p>
                    ) : (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-1 text-sm rounded-full ${
                            testResult.is_threat_detected ? 'bg-red-200 text-red-800' : 'bg-green-200 text-green-800'
                          }`}>
                            {testResult.is_threat_detected ? 'THREAT DETECTED' : 'SAFE'}
                          </span>
                          <span className="text-sm text-gray-500">
                            Score: {(testResult.threat_score * 100).toFixed(0)}%
                          </span>
                          <span className="text-sm text-gray-500">
                            ({testResult.response_time_ms}ms)
                          </span>
                        </div>
                        {testResult.threat_reason && (
                          <p className="text-sm text-gray-700 dark:text-gray-300">
                            Reason: {testResult.threat_reason}
                          </p>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Prompts Tab */}
        {activeTab === 'prompts' && (
          <div className="space-y-6">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Analysis Prompts
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Customize the prompts used for each detection type. Set to empty to use defaults.
                </p>
              </div>
              <div className="divide-y divide-gray-200 dark:divide-gray-700">
                {prompts.map((prompt) => (
                  <div key={prompt.detection_type} className="p-6">
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h4 className="font-medium text-gray-900 dark:text-gray-100 capitalize">
                          {prompt.detection_type.replace('_', ' ')}
                        </h4>
                        <p className="text-sm text-gray-500">
                          {prompt.has_custom_prompt ? 'Using custom prompt' : 'Using default prompt'}
                        </p>
                      </div>
                      {canEdit && (
                        <button
                          onClick={() => {
                            setEditingPrompt(prompt.detection_type)
                            setPromptText(prompt.custom_prompt || '')
                          }}
                          className="px-3 py-1 text-sm text-teal-400 hover:text-teal-300 border border-teal-400 rounded"
                        >
                          {editingPrompt === prompt.detection_type ? 'Cancel' : 'Edit'}
                        </button>
                      )}
                    </div>

                    {editingPrompt === prompt.detection_type ? (
                      <div className="space-y-4">
                        <textarea
                          value={promptText}
                          onChange={(e) => setPromptText(e.target.value)}
                          rows={8}
                          placeholder="Enter custom prompt or leave empty for default..."
                          className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 font-mono text-sm"
                        />
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleSavePrompt(prompt.detection_type)}
                            disabled={saving}
                            className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-md disabled:opacity-50"
                          >
                            {saving ? 'Saving...' : 'Save Prompt'}
                          </button>
                          <button
                            onClick={() => {
                              setEditingPrompt(null)
                              setPromptText('')
                            }}
                            className="px-4 py-2 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 font-medium rounded-md"
                          >
                            Cancel
                          </button>
                        </div>
                        <div className="mt-4">
                          <p className="text-sm text-gray-500 mb-2">Default prompt (for reference):</p>
                          <pre className="p-3 bg-gray-100 dark:bg-gray-900 rounded text-xs overflow-x-auto">
                            {prompt.default_prompt}
                          </pre>
                        </div>
                      </div>
                    ) : (
                      <pre className="p-3 bg-gray-100 dark:bg-gray-900 rounded text-xs overflow-x-auto max-h-32">
                        {prompt.custom_prompt || prompt.default_prompt}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* LLM Tab */}
        {activeTab === 'llm' && (
          <div className="space-y-6">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  LLM Configuration
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Configure the AI model used for security analysis
                </p>
              </div>
              <div className="p-6 space-y-6">
                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Provider
                    </label>
                    <select
                      value={formState.llm_provider || config?.llm_provider || 'gemini'}
                      onChange={(e) => setFormState({ ...formState, llm_provider: e.target.value, llm_model: undefined })}
                      disabled={!canEdit}
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    >
                      {providers.map((p) => (
                        <option key={p.name} value={p.name}>{p.display_name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Model
                    </label>
                    <select
                      value={formState.llm_model || config?.llm_model || ''}
                      onChange={(e) => setFormState({ ...formState, llm_model: e.target.value })}
                      disabled={!canEdit}
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    >
                      {providers.find(p => p.name === (formState.llm_provider || config?.llm_provider))?.models.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Max Tokens
                    </label>
                    <input
                      type="number"
                      value={formState.llm_max_tokens ?? config?.llm_max_tokens ?? 256}
                      onChange={(e) => setFormState({ ...formState, llm_max_tokens: parseInt(e.target.value) })}
                      disabled={!canEdit}
                      min={64}
                      max={1024}
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Temperature
                    </label>
                    <input
                      type="number"
                      value={formState.llm_temperature ?? config?.llm_temperature ?? 0.1}
                      onChange={(e) => setFormState({ ...formState, llm_temperature: parseFloat(e.target.value) })}
                      disabled={!canEdit}
                      min={0}
                      max={1}
                      step={0.1}
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Timeout (seconds)
                    </label>
                    <input
                      type="number"
                      value={formState.timeout_seconds ?? config?.timeout_seconds ?? 5}
                      onChange={(e) => setFormState({ ...formState, timeout_seconds: parseFloat(e.target.value) })}
                      disabled={!canEdit}
                      min={1}
                      max={30}
                      step={0.5}
                      className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Cache TTL (seconds)
                  </label>
                  <input
                    type="number"
                    value={formState.cache_ttl_seconds ?? config?.cache_ttl_seconds ?? 300}
                    onChange={(e) => setFormState({ ...formState, cache_ttl_seconds: parseInt(e.target.value) })}
                    disabled={!canEdit}
                    min={0}
                    max={3600}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    How long to cache analysis results (0 to disable caching)
                  </p>
                </div>

                <div className="flex items-center gap-4">
                  <button
                    onClick={handleTestLLM}
                    disabled={testingLLM}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md disabled:opacity-50 transition-colors"
                  >
                    {testingLLM ? 'Testing...' : 'Test Connection'}
                  </button>
                  {llmTestResult && (
                    <span className={`text-sm ${llmTestResult.startsWith('Success') ? 'text-green-600' : 'text-red-600'}`}>
                      {llmTestResult}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Save Button */}
            {canEdit && (
              <div className="flex justify-end">
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="px-6 py-2 bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-lg disabled:opacity-50 transition-colors"
                >
                  {saving ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Stats Tab */}
        {activeTab === 'stats' && stats && (
          <div className="space-y-6">
            {/* Summary Cards */}
            <div className="grid grid-cols-4 gap-4">
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <p className="text-sm text-gray-500 dark:text-gray-400">Total Analyses</p>
                <p className="text-3xl font-bold text-gray-900 dark:text-gray-100">{stats.total_analyses}</p>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <p className="text-sm text-gray-500 dark:text-gray-400">Threats Detected</p>
                <p className="text-3xl font-bold text-orange-600">{stats.threats_detected}</p>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <p className="text-sm text-gray-500 dark:text-gray-400">Threats Blocked</p>
                <p className="text-3xl font-bold text-red-600">{stats.threats_blocked}</p>
              </div>
              <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
                <p className="text-sm text-gray-500 dark:text-gray-400">Detection Rate</p>
                <p className="text-3xl font-bold text-teal-600">{stats.detection_rate}%</p>
              </div>
            </div>

            {/* By Detection Type */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Threats by Detection Type
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Last {stats.period_days} days
                </p>
              </div>
              <div className="p-6">
                {Object.entries(stats.by_detection_type).length > 0 ? (
                  <div className="space-y-4">
                    {Object.entries(stats.by_detection_type).map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between">
                        <span className="text-gray-700 dark:text-gray-300 capitalize">
                          {type.replace('_', ' ')}
                        </span>
                        <span className="font-medium text-gray-900 dark:text-gray-100">
                          {count}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                    No threats detected in this period
                  </p>
                )}
              </div>
            </div>

            {/* Link to Watcher */}
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
              <p className="text-blue-800 dark:text-blue-200">
                View detailed security events in the{' '}
                <Link href="/watcher" className="underline font-medium">
                  Watcher Security Tab
                </Link>
              </p>
            </div>
          </div>
        )}

        {/* Exceptions Tab - Phase 20 Enhancement */}
        {activeTab === 'exceptions' && (
          <div className="space-y-6">
            {/* Header with Add Button */}
            <div className="flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Exception Rules
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Allow specific patterns, domains, or tools to bypass Sentinel analysis
                </p>
              </div>
              {canEdit && (
                <button
                  onClick={() => {
                    setEditingException(null)
                    setExceptionForm({
                      name: '',
                      exception_type: 'network_target',
                      pattern: '',
                      match_mode: 'exact',
                      detection_types: '*',
                      action: 'skip_llm',
                      priority: 100,
                    })
                    setShowExceptionModal(true)
                  }}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-lg transition-colors"
                >
                  Add Exception
                </button>
              )}
            </div>

            {/* Exceptions Table */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 dark:bg-gray-700">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Name</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Type</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Pattern</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Mode</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Scope</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Status</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                    {exceptions.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-8 text-center text-gray-500 dark:text-gray-400">
                          No exception rules configured
                        </td>
                      </tr>
                    ) : (
                      exceptions.map((exc) => (
                        <tr key={exc.id} className={!exc.is_active ? 'opacity-50' : ''}>
                          <td className="px-4 py-3">
                            <div>
                              <p className="font-medium text-gray-900 dark:text-gray-100">{exc.name}</p>
                              {exc.description && (
                                <p className="text-xs text-gray-500 dark:text-gray-400 truncate max-w-xs">{exc.description}</p>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 text-xs rounded-full ${
                              exc.exception_type === 'network_target' ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400' :
                              exc.exception_type === 'domain' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' :
                              exc.exception_type === 'tool' ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400' :
                              'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400'
                            }`}>
                              {exc.exception_type.replace('_', ' ')}
                            </span>
                          </td>
                          <td className="px-4 py-3">
                            <code className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded font-mono truncate max-w-[200px] block">
                              {exc.pattern}
                            </code>
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                            {exc.match_mode}
                          </td>
                          <td className="px-4 py-3 text-sm">
                            {exc.tenant_id === null ? (
                              <span className="px-2 py-1 text-xs rounded-full bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400">
                                System
                              </span>
                            ) : (
                              <span className="text-gray-500 dark:text-gray-400">Tenant</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 text-xs rounded-full ${
                              exc.is_active
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400'
                            }`}>
                              {exc.is_active ? 'Active' : 'Inactive'}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right">
                            <div className="flex justify-end gap-2">
                              <button
                                onClick={async () => {
                                  try {
                                    await api.toggleSentinelException(exc.id)
                                    fetchExceptions()
                                  } catch (err: any) {
                                    setError(err.message)
                                  }
                                }}
                                disabled={!canEdit}
                                className="p-1 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 disabled:opacity-50"
                                title={exc.is_active ? 'Deactivate' : 'Activate'}
                              >
                                {exc.is_active ? <PauseIcon size={16} /> : <PlayIcon size={16} />}
                              </button>
                              {exc.tenant_id !== null && canEdit && (
                                <>
                                  <button
                                    onClick={() => {
                                      setEditingException(exc)
                                      setExceptionForm({
                                        name: exc.name,
                                        description: exc.description || '',
                                        exception_type: exc.exception_type,
                                        pattern: exc.pattern,
                                        match_mode: exc.match_mode,
                                        detection_types: exc.detection_types,
                                        action: exc.action,
                                        priority: exc.priority,
                                      })
                                      setShowExceptionModal(true)
                                    }}
                                    className="p-1 text-blue-500 hover:text-blue-700"
                                    title="Edit"
                                  >
                                    <EditIcon size={16} />
                                  </button>
                                  <button
                                    onClick={async () => {
                                      if (confirm('Delete this exception?')) {
                                        try {
                                          await api.deleteSentinelException(exc.id)
                                          fetchExceptions()
                                          setSuccess('Exception deleted')
                                        } catch (err: any) {
                                          setError(err.message)
                                        }
                                      }
                                    }}
                                    className="p-1 text-red-500 hover:text-red-700"
                                    title="Delete"
                                  >
                                    <TrashIcon size={16} />
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Test Exception Panel */}
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md overflow-hidden">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Test Exception
                </h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Test if content would match an exception rule
                </p>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Select Exception
                  </label>
                  <select
                    value={testingException ?? ''}
                    onChange={(e) => {
                      setTestingException(e.target.value ? parseInt(e.target.value) : null)
                      setExceptionTestResult(null)
                    }}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  >
                    <option value="">Select an exception...</option>
                    {exceptions.map((exc) => (
                      <option key={exc.id} value={exc.id}>{exc.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Test Content
                  </label>
                  <textarea
                    value={exceptionTestContent}
                    onChange={(e) => setExceptionTestContent(e.target.value)}
                    rows={3}
                    placeholder="Enter content to test (e.g., 'nmap scanme.nmap.org' or 'curl https://httpbin.org/get')"
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                </div>
                <button
                  onClick={async () => {
                    if (!testingException || !exceptionTestContent.trim()) return
                    try {
                      const result = await api.testSentinelException(testingException, {
                        test_content: exceptionTestContent,
                      })
                      setExceptionTestResult(result)
                    } catch (err: any) {
                      setError(err.message)
                    }
                  }}
                  disabled={!testingException || !exceptionTestContent.trim()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md disabled:opacity-50 transition-colors"
                >
                  Test
                </button>

                {exceptionTestResult && (
                  <div className={`mt-4 p-4 rounded-lg ${
                    exceptionTestResult.matches
                      ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                      : 'bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800'
                  }`}>
                    <p className={`font-medium ${
                      exceptionTestResult.matches ? 'text-green-800 dark:text-green-200' : 'text-yellow-800 dark:text-yellow-200'
                    }`}>
                      {exceptionTestResult.matches ? '✓ Exception matches' : '✗ Exception does not match'}
                    </p>
                    <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                      {exceptionTestResult.matches
                        ? 'This content would bypass Sentinel analysis'
                        : 'This content would still be analyzed by Sentinel'}
                    </p>
                    {exceptionTestResult.extracted_targets && exceptionTestResult.extracted_targets.length > 0 && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                        Extracted targets: {exceptionTestResult.extracted_targets.join(', ')}
                      </p>
                    )}
                    {exceptionTestResult.extracted_domains && exceptionTestResult.extracted_domains.length > 0 && (
                      <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                        Extracted domains: {exceptionTestResult.extracted_domains.join(', ')}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Info Box */}
            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
              <h4 className="font-medium text-blue-800 dark:text-blue-200 mb-2">About Exceptions</h4>
              <ul className="text-sm text-blue-700 dark:text-blue-300 space-y-1 list-disc list-inside">
                <li><strong>System exceptions</strong> (shown with orange badge) are pre-configured and cannot be modified</li>
                <li><strong>Network Target</strong> exceptions match hostnames, IPs, and domains extracted from content</li>
                <li><strong>Domain</strong> exceptions match domains from URLs</li>
                <li><strong>Pattern</strong> exceptions match against the entire input content</li>
                <li><strong>Tool</strong> exceptions match against the tool name being called</li>
              </ul>
            </div>
          </div>
        )}

        {/* Exception Modal */}
        {showExceptionModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto">
              <div className="p-6 border-b border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  {editingException ? 'Edit Exception' : 'Add Exception'}
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Name *</label>
                  <input
                    type="text"
                    value={exceptionForm.name}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, name: e.target.value })}
                    placeholder="e.g., Allow httpbin.org"
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Description</label>
                  <textarea
                    value={exceptionForm.description || ''}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, description: e.target.value })}
                    rows={2}
                    placeholder="Optional description"
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Exception Type *</label>
                  <select
                    value={exceptionForm.exception_type}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, exception_type: e.target.value as any })}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  >
                    <option value="network_target">Network Target (hosts/IPs/domains in content)</option>
                    <option value="domain">Domain (from URLs)</option>
                    <option value="pattern">Pattern (match content)</option>
                    <option value="tool">Tool (match tool name)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Pattern *</label>
                  <input
                    type="text"
                    value={exceptionForm.pattern}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, pattern: e.target.value })}
                    placeholder={exceptionForm.match_mode === 'regex' ? '.*example\\.com$' : 'scanme.nmap.org'}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Match Mode</label>
                  <select
                    value={exceptionForm.match_mode}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, match_mode: e.target.value as any })}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  >
                    <option value="exact">Exact (case-insensitive)</option>
                    <option value="glob">Glob (wildcard patterns like *.example.com)</option>
                    <option value="regex">Regex (regular expression)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Detection Types</label>
                  <input
                    type="text"
                    value={exceptionForm.detection_types}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, detection_types: e.target.value })}
                    placeholder="* for all, or comma-separated: shell_malicious,prompt_injection"
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                  <p className="text-xs text-gray-500 mt-1">Use * for all detection types, or specify: shell_malicious, prompt_injection, agent_takeover, poisoning</p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Priority</label>
                  <input
                    type="number"
                    value={exceptionForm.priority}
                    onChange={(e) => setExceptionForm({ ...exceptionForm, priority: parseInt(e.target.value) })}
                    min={1}
                    max={1000}
                    className="w-full px-3 py-2 border dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  />
                  <p className="text-xs text-gray-500 mt-1">Higher priority exceptions are evaluated first</p>
                </div>
              </div>
              <div className="p-6 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
                <button
                  onClick={() => {
                    setShowExceptionModal(false)
                    setEditingException(null)
                  }}
                  className="px-4 py-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    if (!exceptionForm.name || !exceptionForm.pattern) {
                      setError('Name and pattern are required')
                      return
                    }
                    setSavingException(true)
                    try {
                      if (editingException) {
                        await api.updateSentinelException(editingException.id, exceptionForm as SentinelExceptionUpdate)
                        setSuccess('Exception updated')
                      } else {
                        await api.createSentinelException(exceptionForm)
                        setSuccess('Exception created')
                      }
                      setShowExceptionModal(false)
                      setEditingException(null)
                      fetchExceptions()
                    } catch (err: any) {
                      setError(err.message)
                    } finally {
                      setSavingException(false)
                    }
                  }}
                  disabled={savingException || !exceptionForm.name || !exceptionForm.pattern}
                  className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white font-medium rounded-md disabled:opacity-50 transition-colors"
                >
                  {savingException ? 'Saving...' : editingException ? 'Update' : 'Create'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
