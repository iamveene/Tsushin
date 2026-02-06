'use client'

import { useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'

export default function AsanaCallbackPage() {
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing')
  const [message, setMessage] = useState('')

  // Helper function to get authentication headers
  const getAuthHeaders = () => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }

  useEffect(() => {
    handleCallback()
  }, [])

  const handleCallback = async () => {
    const code = searchParams.get('code')
    const state = searchParams.get('state')
    const error = searchParams.get('error')

    // Handle OAuth error
    if (error) {
      setStatus('error')
      setMessage(`OAuth authorization failed: ${error}`)
      return
    }

    if (!code || !state) {
      setStatus('error')
      setMessage('Missing OAuth parameters (code or state)')
      return
    }

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'
      const response = await fetch(`${apiUrl}/api/hub/asana/oauth/callback`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ code, state })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }))
        throw new Error(errorData.detail || 'Callback failed')
      }

      const data = await response.json()
      setStatus('success')
      setMessage(`Successfully connected to Asana workspace: ${data.workspace_name}`)

      // Redirect to Hub page after 2 seconds
      setTimeout(() => {
        window.location.href = data.redirect_url || '/hub'
      }, 2000)
    } catch (error) {
      console.error('OAuth callback error:', error)
      setStatus('error')
      setMessage(error instanceof Error ? error.message : 'Unknown error occurred')
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <div className="max-w-2xl mx-auto px-4 py-16">
        <div className="bg-gray-900/50 border border-gray-800 rounded-lg p-8">
          <div className="text-center">
            {status === 'processing' && (
              <>
                <div className="inline-block w-16 h-16 border-4 border-orange-500/30 border-t-orange-500 rounded-full animate-spin mb-4"></div>
                <h2 className="text-2xl font-bold mb-2">Connecting to Asana...</h2>
                <p className="text-tsushin-slate">Please wait while we complete the authorization.</p>
              </>
            )}

            {status === 'success' && (
              <>
                <div className="inline-block w-16 h-16 bg-green-500/10 rounded-full mb-4 flex items-center justify-center">
                  <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h2 className="text-2xl font-bold mb-2 text-green-400">Connected Successfully!</h2>
                <p className="text-tsushin-slate">{message}</p>
                <p className="text-sm text-gray-600 mt-4">Redirecting you back...</p>
              </>
            )}

            {status === 'error' && (
              <>
                <div className="inline-block w-16 h-16 bg-red-500/10 rounded-full mb-4 flex items-center justify-center">
                  <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </div>
                <h2 className="text-2xl font-bold mb-2 text-red-400">Connection Failed</h2>
                <p className="text-tsushin-slate mb-6">{message}</p>
                <button
                  onClick={() => window.location.href = '/hub'}
                  className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
                >
                  Back to Hub
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
