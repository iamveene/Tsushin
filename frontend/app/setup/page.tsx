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
  const [geminiApiKey, setGeminiApiKey] = useState('')
  const [openaiApiKey, setOpenaiApiKey] = useState('')
  const [anthropicApiKey, setAnthropicApiKey] = useState('')
  const [groqApiKey, setGroqApiKey] = useState('')
  const [grokApiKey, setGrokApiKey] = useState('')
  const [deepseekApiKey, setDeepseekApiKey] = useState('')
  const [openrouterApiKey, setOpenrouterApiKey] = useState('')
  const [providerKeysOpen, setProviderKeysOpen] = useState(true)
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
      const result = await api.setupWizard({
        tenant_name: orgName,
        admin_email: email,
        admin_password: password,
        admin_full_name: fullName,
        create_default_agents: createDefaultAgents,
        gemini_api_key: geminiApiKey || undefined,
        openai_api_key: openaiApiKey || undefined,
        anthropic_api_key: anthropicApiKey || undefined,
        groq_api_key: groqApiKey || undefined,
        grok_api_key: grokApiKey || undefined,
        deepseek_api_key: deepseekApiKey || undefined,
        openrouter_api_key: openrouterApiKey || undefined,
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
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
                  <div>
                    <label htmlFor="geminiApiKey" className="block text-sm font-medium text-gray-300 mb-1">
                      Google Gemini <span className="text-teal-500 text-xs">(recommended)</span>
                    </label>
                    <input
                      id="geminiApiKey"
                      type="password"
                      value={geminiApiKey}
                      onChange={(e) => setGeminiApiKey(e.target.value)}
                      placeholder="AIza..."
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent text-sm"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">ai.google.dev</p>
                  </div>

                  <div>
                    <label htmlFor="openaiApiKey" className="block text-sm font-medium text-gray-300 mb-1">
                      OpenAI
                    </label>
                    <input
                      id="openaiApiKey"
                      type="password"
                      value={openaiApiKey}
                      onChange={(e) => setOpenaiApiKey(e.target.value)}
                      placeholder="sk-..."
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent text-sm"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">platform.openai.com</p>
                  </div>

                  <div>
                    <label htmlFor="anthropicApiKey" className="block text-sm font-medium text-gray-300 mb-1">
                      Anthropic Claude
                    </label>
                    <input
                      id="anthropicApiKey"
                      type="password"
                      value={anthropicApiKey}
                      onChange={(e) => setAnthropicApiKey(e.target.value)}
                      placeholder="sk-ant-..."
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent text-sm"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">console.anthropic.com</p>
                  </div>

                  <div>
                    <label htmlFor="groqApiKey" className="block text-sm font-medium text-gray-300 mb-1">
                      Groq
                    </label>
                    <input
                      id="groqApiKey"
                      type="password"
                      value={groqApiKey}
                      onChange={(e) => setGroqApiKey(e.target.value)}
                      placeholder="gsk_..."
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent text-sm"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">console.groq.com</p>
                  </div>

                  <div>
                    <label htmlFor="grokApiKey" className="block text-sm font-medium text-gray-300 mb-1">
                      Grok (xAI)
                    </label>
                    <input
                      id="grokApiKey"
                      type="password"
                      value={grokApiKey}
                      onChange={(e) => setGrokApiKey(e.target.value)}
                      placeholder="xai-..."
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent text-sm"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">console.x.ai</p>
                  </div>

                  <div>
                    <label htmlFor="deepseekApiKey" className="block text-sm font-medium text-gray-300 mb-1">
                      DeepSeek
                    </label>
                    <input
                      id="deepseekApiKey"
                      type="password"
                      value={deepseekApiKey}
                      onChange={(e) => setDeepseekApiKey(e.target.value)}
                      placeholder="sk-..."
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent text-sm"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">platform.deepseek.com</p>
                  </div>

                  <div className="sm:col-span-2">
                    <label htmlFor="openrouterApiKey" className="block text-sm font-medium text-gray-300 mb-1">
                      OpenRouter
                    </label>
                    <input
                      id="openrouterApiKey"
                      type="password"
                      value={openrouterApiKey}
                      onChange={(e) => setOpenrouterApiKey(e.target.value)}
                      placeholder="sk-or-..."
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent text-sm"
                    />
                    <p className="mt-0.5 text-xs text-gray-600">openrouter.ai</p>
                  </div>
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
