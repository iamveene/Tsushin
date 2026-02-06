'use client'

/**
 * SSO Callback Page
 * Handles the redirect from Google OAuth
 *
 * MED-009 Security Fix: Now receives a one-time code instead of JWT in URL.
 * The code is exchanged for JWT via /api/auth/sso-exchange endpoint.
 * This prevents JWT exposure in browser history, server logs, and referrer headers.
 */

import { Suspense, useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

function SSOCallbackContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { setAuthFromToken } = useAuth()
  const [error, setError] = useState<string | null>(null)
  const [processing, setProcessing] = useState(true)

  useEffect(() => {
    const processCallback = async () => {
      // MED-009: Now receives 'code' instead of 'token'
      const code = searchParams.get('code')
      const errorMsg = searchParams.get('error')

      // Legacy support: still accept 'token' for backwards compatibility during rollout
      const legacyToken = searchParams.get('token')

      if (errorMsg) {
        setError(decodeURIComponent(errorMsg))
        setProcessing(false)
        return
      }

      // Handle legacy token flow (backwards compatibility)
      if (legacyToken && !code) {
        try {
          await setAuthFromToken(legacyToken)
          const redirect = searchParams.get('redirect') || '/'
          router.replace(redirect)
          return
        } catch (err: any) {
          console.error('SSO callback error (legacy):', err)
          setError(err.message || 'Failed to complete authentication')
          setProcessing(false)
          return
        }
      }

      if (!code) {
        setError('No authentication code received')
        setProcessing(false)
        return
      }

      try {
        // MED-009: Exchange the one-time code for JWT token
        const response = await fetch(`${API_URL}/api/auth/sso-exchange`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ code }),
        })

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}))
          throw new Error(errorData.detail || 'Failed to exchange authentication code')
        }

        const data = await response.json()
        const { access_token, redirect_after } = data

        // Store the token and fetch user info
        await setAuthFromToken(access_token)

        // Redirect to the intended destination
        const redirect = redirect_after || '/'
        router.replace(redirect)
      } catch (err: any) {
        console.error('SSO callback error:', err)
        setError(err.message || 'Failed to complete authentication')
        setProcessing(false)
      }
    }

    processCallback()
  }, [searchParams, router, setAuthFromToken])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="w-full max-w-md">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8 text-center">
          {processing ? (
            <>
              <div className="w-16 h-16 mx-auto mb-4">
                <svg
                  className="animate-spin w-full h-full text-blue-600"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Completing sign in...
              </h2>
              <p className="text-gray-600 dark:text-gray-400">
                Please wait while we verify your credentials.
              </p>
            </>
          ) : error ? (
            <>
              <div className="w-16 h-16 mx-auto mb-4 text-red-500">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                  className="w-full h-full"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Authentication Failed
              </h2>
              <p className="text-red-600 dark:text-red-400 mb-4">
                {error}
              </p>
              <button
                onClick={() => router.push('/auth/login')}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors"
              >
                Back to Login
              </button>
            </>
          ) : (
            <>
              <div className="w-16 h-16 mx-auto mb-4 text-green-500">
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth={2}
                  stroke="currentColor"
                  className="w-full h-full"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                Authentication Successful
              </h2>
              <p className="text-gray-600 dark:text-gray-400">
                Redirecting...
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function LoadingFallback() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <div className="w-full max-w-md">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-8 text-center">
          <div className="w-16 h-16 mx-auto mb-4">
            <svg
              className="animate-spin w-full h-full text-blue-600"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Loading...
          </h2>
        </div>
      </div>
    </div>
  )
}

export default function SSOCallbackPage() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <SSOCallbackContent />
    </Suspense>
  )
}
