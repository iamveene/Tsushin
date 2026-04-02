'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import { api } from '@/lib/client'

export default function SetupPage() {
  const router = useRouter()
  const [checking, setChecking] = useState(true)
  const [orgName, setOrgName] = useState('')
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [providerKeys, setProviderKeys] = useState<Array<{provider: string, key: string, model: string}>>([])
  const [selectedProvider, setSelectedProvider] = useState('gemini')
  const [currentKey, setCurrentKey] = useState('')
  const [currentModel, setCurrentModel] = useState('')
  const [providerKeysOpen, setProviderKeysOpen] = useState(true)

  const PROVIDERS: Record<string, { label: string; field: string; placeholder: string; models: string[]; defaultModel: string }> = {
    gemini:     { label: 'Google Gemini',    field: 'gemini_api_key',     placeholder: 'AIza...',    models: ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash'], defaultModel: 'gemini-2.5-flash' },
    openai:     { label: 'OpenAI',           field: 'openai_api_key',     placeholder: 'sk-...',     models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4.1-mini', 'gpt-4.1', 'o4-mini'], defaultModel: 'gpt-4o-mini' },
    anthropic:  { label: 'Anthropic Claude', field: 'anthropic_api_key',  placeholder: 'sk-ant-...', models: ['claude-haiku-4-5', 'claude-sonnet-4-6', 'claude-opus-4-6'], defaultModel: 'claude-haiku-4-5' },
    groq:       { label: 'Groq',             field: 'groq_api_key',       placeholder: 'gsk_...',    models: ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'], defaultModel: 'llama-3.3-70b-versatile' },
    grok:       { label: 'Grok (xAI)',       field: 'grok_api_key',       placeholder: 'xai-...',    models: ['grok-3-mini', 'grok-3'], defaultModel: 'grok-3-mini' },
    deepseek:   { label: 'DeepSeek',         field: 'deepseek_api_key',   placeholder: 'sk-...',     models: ['deepseek-chat', 'deepseek-reasoner'], defaultModel: 'deepseek-chat' },
    openrouter: { label: 'OpenRouter',       field: 'openrouter_api_key', placeholder: 'sk-or-...',  models: ['google/gemini-2.5-flash', 'anthropic/claude-sonnet-4', 'openai/gpt-4o-mini'], defaultModel: 'google/gemini-2.5-flash' },
  }

  const maskKey = (key: string) => {
    if (key.length <= 6) return key.replace(/./g, '*')
    return key.slice(0, key.indexOf('-') + 1 || 4) + '...' + key.slice(-3)
  }

  const handleAddProvider = () => {
    if (!currentKey.trim()) return
    if (providerKeys.some(p => p.provider === selectedProvider)) return
    const model = currentModel || PROVIDERS[selectedProvider]?.defaultModel || ''
    setProviderKeys([...providerKeys, { provider: selectedProvider, key: currentKey.trim(), model }])
    setCurrentKey('')
    setCurrentModel('')
    // Auto-select next available provider
    const usedProviders = new Set([...providerKeys.map(p => p.provider), selectedProvider])
    const nextAvailable = Object.keys(PROVIDERS).find(p => !usedProviders.has(p))
    if (nextAvailable) setSelectedProvider(nextAvailable)
  }

  const handleRemoveProvider = (provider: string) => {
    setProviderKeys(providerKeys.filter(p => p.provider !== provider))
  }
  const [createDefaultAgents, setCreateDefaultAgents] = useState(true)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.getSetupStatus().then(({ needs_setup }) => {
      if (!needs_setup) {
        router.replace('/auth/login')
      } else {
        setChecking(false)
      }
    })
  }, [router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters')
      return
    }

    setLoading(true)
    try {
      const keyFields: Record<string, string | undefined> = {}
      for (const { provider, key } of providerKeys) {
        const field = PROVIDERS[provider]?.field
        if (field && key) keyFields[field] = key
      }

      // Send the primary provider's model as default_model
      const primaryModel = providerKeys.length > 0 ? providerKeys[0].model : undefined

      const result = await api.setupWizard({
        tenant_name: orgName,
        admin_email: email,
        admin_password: password,
        admin_full_name: fullName,
        create_default_agents: createDefaultAgents,
        default_model: primaryModel,
        ...keyFields,
      })

      if (result.success) {
        // Redirect to login — the account is ready, user just needs to sign in.
        // Trying to auto-login causes AuthContext race conditions on full page reload.
        router.replace('/auth/login')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Setup failed')
    } finally {
      setLoading(false)
    }
  }

  if (checking) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-20 h-20 mx-auto mb-6">
            <div className="absolute inset-0 rounded-full border-4 border-gray-800"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-indigo-500 animate-spin"></div>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-2xl">通</span>
            </div>
          </div>
          <p className="text-gray-400 font-medium">Checking system status...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-lg w-full space-y-6">
        {/* Banner */}
        <div className="relative w-full overflow-hidden">
          <Image
            src="/images/tsushin-banner.png"
            alt="Tsushin - Think. Secure. Build."
            width={1280}
            height={640}
            priority
            className="w-full h-auto"
          />
        </div>

        {/* Title */}
        <div className="text-center">
          <h1 className="text-2xl font-bold text-white">Initial Setup</h1>
          <p className="mt-1 text-sm text-gray-400">
            Create your organization and administrator account
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl shadow-xl p-8 space-y-5">
            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-md p-3">
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            <div>
              <label htmlFor="orgName" className="block text-sm font-medium text-gray-300 mb-1">
                Organization Name
              </label>
              <input
                id="orgName"
                type="text"
                required
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="My Organization"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
              />
            </div>

            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-1">
                Admin Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@example.com"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
              />
            </div>

            <div>
              <label htmlFor="fullName" className="block text-sm font-medium text-gray-300 mb-1">
                Full Name
              </label>
              <input
                id="fullName"
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="John Doe"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-1">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min 8 characters"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
              />
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-300 mb-1">
                Confirm Password
              </label>
              <input
                id="confirmPassword"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Repeat password"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent"
              />
            </div>

            {/* AI Provider Keys */}
            <div className="border-t border-gray-800 pt-4">
              <button
                type="button"
                onClick={() => setProviderKeysOpen(!providerKeysOpen)}
                className="w-full flex items-center justify-between text-left"
              >
                <div>
                  <h3 className="text-sm font-medium text-gray-300">AI Provider API Keys</h3>
                  <p className="text-xs text-gray-500 mt-0.5">Configure at least one provider. More can be added later in Hub.</p>
                </div>
                <svg
                  className={`w-4 h-4 text-gray-500 transition-transform ${providerKeysOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {providerKeysOpen && (
                <div className="mt-4 space-y-3">
                  {/* Added provider chips */}
                  {providerKeys.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {providerKeys.map((entry, idx) => (
                        <div
                          key={entry.provider}
                          className="bg-gray-800/50 border border-gray-700 rounded-lg px-3 py-2 flex items-center gap-2 text-sm"
                        >
                          <span className="text-gray-300">
                            {PROVIDERS[entry.provider]?.label}
                          </span>
                          <span className="text-gray-500 font-mono text-xs">
                            {entry.model}
                          </span>
                          <span className="text-gray-600 font-mono text-xs">
                            {maskKey(entry.key)}
                          </span>
                          {idx === 0 && (
                            <span className="text-teal-400 text-xs font-medium">Primary</span>
                          )}
                          <button
                            type="button"
                            onClick={() => handleRemoveProvider(entry.provider)}
                            className="ml-1 text-gray-500 hover:text-red-400 transition-colors"
                            aria-label={`Remove ${PROVIDERS[entry.provider]?.label}`}
                          >
                            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Provider + model + key input */}
                  {providerKeys.length < Object.keys(PROVIDERS).length && (
                    <div className="space-y-2">
                      <div className="flex gap-2">
                        <select
                          value={selectedProvider}
                          onChange={(e) => { setSelectedProvider(e.target.value); setCurrentModel('') }}
                          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent min-w-[160px]"
                        >
                          {Object.entries(PROVIDERS)
                            .filter(([key]) => !providerKeys.some(p => p.provider === key))
                            .map(([key, { label }]) => (
                              <option key={key} value={key}>{label}</option>
                            ))}
                        </select>
                        <select
                          value={currentModel || PROVIDERS[selectedProvider]?.defaultModel || ''}
                          onChange={(e) => setCurrentModel(e.target.value)}
                          className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent min-w-[180px]"
                        >
                          {PROVIDERS[selectedProvider]?.models.map((m) => (
                            <option key={m} value={m}>{m}</option>
                          ))}
                        </select>
                      </div>
                      <div className="flex gap-2">
                        <input
                          type="password"
                          value={currentKey}
                          onChange={(e) => setCurrentKey(e.target.value)}
                          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddProvider() } }}
                          placeholder={PROVIDERS[selectedProvider]?.placeholder || 'API key'}
                          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent text-sm"
                        />
                        <button
                          type="button"
                          onClick={handleAddProvider}
                          disabled={!currentKey.trim()}
                          className="px-4 py-2 bg-teal-600 hover:bg-teal-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors whitespace-nowrap"
                        >
                          Add
                        </button>
                      </div>
                    </div>
                  )}

                  <p className="text-xs text-gray-500">
                    Configure at least one provider. The first added will be the default.
                  </p>
                </div>
              )}
            </div>

            <div className="flex items-center">
              <input
                id="createAgents"
                type="checkbox"
                checked={createDefaultAgents}
                onChange={(e) => setCreateDefaultAgents(e.target.checked)}
                className="h-4 w-4 text-teal-500 focus:ring-teal-500 border-gray-700 rounded bg-gray-800"
              />
              <label htmlFor="createAgents" className="ml-2 text-sm text-gray-300">
                Create default agents
              </label>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center py-2.5 px-4 text-sm font-medium rounded-lg text-white bg-teal-600 hover:bg-teal-500 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Setting up...' : 'Complete Setup'}
            </button>
          </div>
        </form>

        {/* Footer */}
        <p className="text-center text-xs text-gray-500">
          &copy; 2026 Tsushin. Think, Secure, Build.
        </p>
      </div>
    </div>
  )
}
