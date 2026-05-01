'use client'

/**
 * Login Page
 * Supports email/password and Google SSO authentication
 */

import React, { useEffect, useRef, useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { Input } from '@/components/ui/form-input'
import { api } from '@/lib/client'
import { validateEmailAddress } from '@/lib/validation'

interface LoginClientProps {
  errorParam: string | null
  forceLogin: boolean
  initialGoogleSSOEnabled: boolean | null
  recoveryReason: string | null
}

// Google Icon SVG
const GoogleIcon = () => (
  <svg className="w-5 h-5" viewBox="0 0 24 24">
    <path
      fill="#4285F4"
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
    />
    <path
      fill="#34A853"
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
    />
    <path
      fill="#FBBC05"
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
    />
    <path
      fill="#EA4335"
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
    />
  </svg>
)

export default function LoginClient({
  errorParam,
  forceLogin,
  initialGoogleSSOEnabled,
  recoveryReason,
}: LoginClientProps) {
  const { login, loginWithGoogle } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [emailError, setEmailError] = useState('')
  const [loading, setLoading] = useState(false)
  const [googleSSOEnabled, setGoogleSSOEnabled] = useState(initialGoogleSSOEnabled ?? false)
  const [googleStatusResolved, setGoogleStatusResolved] = useState(initialGoogleSSOEnabled !== null)
  const [googleLoading, setGoogleLoading] = useState(false)
  const isSessionRecovery = recoveryReason === 'session-recovery'
  const showGoogleSection = googleSSOEnabled || !googleStatusResolved
  const recoveryCleanupRef = useRef<Promise<void> | null>(null)

  // Redirect to /setup if system needs initial setup
  useEffect(() => {
    api.getSetupStatus().then(({ needs_setup }) => {
      if (needs_setup) router.replace('/setup')
    })
  }, [router])

  // Refresh Google SSO status after hydration in case tenant configuration
  // changed between the server render and client boot.
  useEffect(() => {
    let cancelled = false

    const checkSSO = async () => {
      try {
        const status = await api.getGoogleSSOStatus()
        if (cancelled) {
          return
        }

        setGoogleSSOEnabled(status.enabled)
        setGoogleStatusResolved(true)
      } catch (err) {
        if (cancelled) {
          return
        }

        console.error('Failed to check SSO status:', err)
        setGoogleStatusResolved(true)
      }
    }

    checkSSO()

    return () => {
      cancelled = true
    }
  }, [])

  // Handle error from SSO callback
  useEffect(() => {
    if (errorParam) {
      setError(decodeURIComponent(errorParam))
    }
  }, [errorParam])

  useEffect(() => {
    if (!isSessionRecovery || !forceLogin) {
      return
    }

    recoveryCleanupRef.current = api.logout()
      .then(() => undefined)
      .catch(() => {
        // The backend may be the exact reason we landed here. Keep the login
        // page usable even when the cookie-clearing request fails.
      })
      .finally(() => {
        recoveryCleanupRef.current = null
      })
  }, [forceLogin, isSessionRecovery])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setEmailError('')

    const normalizedEmail = email.trim()
    const emailValidationError = validateEmailAddress(normalizedEmail)
    if (emailValidationError) {
      setEmailError(emailValidationError)
      return
    }

    setEmail(normalizedEmail)
    setLoading(true)

    try {
      await recoveryCleanupRef.current
      await login(normalizedEmail, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSignIn = async () => {
    setError('')
    setGoogleLoading(true)

    try {
      await loginWithGoogle({ platform: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google sign-in failed')
      setGoogleLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0d16] py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-lg w-full space-y-6">
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

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="bg-tsushin-surface border border-tsushin-border rounded-2xl shadow-elevated p-8 space-y-6">
            {isSessionRecovery && (
              <div className="bg-amber-500/10 border border-amber-400/30 rounded-md p-3">
                <p className="text-sm text-amber-200">
                  Your previous session could not be validated. Sign in again to continue.
                </p>
              </div>
            )}

            {error && (
              <div className="bg-tsushin-vermilion/10 border border-tsushin-vermilion/30 rounded-md p-3">
                <p className="text-sm text-tsushin-vermilion">{error}</p>
              </div>
            )}

            <Input
              type="text"
              label="Email address"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value)
                if (emailError) setEmailError('')
              }}
              required
              autoComplete="email"
              inputMode="email"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="you@example.com"
              error={emailError}
            />

            <Input
              type="password"
              label="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
            />

            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <input
                  id="remember-me"
                  name="remember-me"
                  type="checkbox"
                  className="h-4 w-4 text-teal-500 focus:ring-teal-500 border-tsushin-border rounded bg-tsushin-deep"
                />
                <label
                  htmlFor="remember-me"
                  className="ml-2 block text-sm text-tsushin-fog"
                >
                  Remember me
                </label>
              </div>

              <div className="text-sm">
                <Link
                  href="/auth/forgot-password"
                  className="font-medium text-teal-400 hover:text-teal-300"
                >
                  Forgot your password?
                </Link>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading || googleLoading}
              className="btn-primary w-full flex justify-center py-2.5 px-4 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>

            {showGoogleSection && (
              <>
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-tsushin-border" />
                  </div>
                  <div className="relative flex justify-center text-sm">
                    <span className="px-2 bg-tsushin-surface text-tsushin-slate">
                      {googleStatusResolved ? 'Or continue with' : 'Checking Google sign-in...'}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleGoogleSignIn}
                  disabled={loading || googleLoading || !googleStatusResolved}
                  className="btn-secondary w-full flex items-center justify-center gap-3 py-2.5 px-4 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {googleLoading || !googleStatusResolved ? (
                    <svg className="animate-spin h-5 w-5 text-tsushin-slate" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                  ) : (
                    <GoogleIcon />
                  )}
                  {!googleStatusResolved ? 'Checking Google sign-in...' : googleLoading ? 'Connecting...' : 'Sign in with Google'}
                </button>
              </>
            )}
          </div>
        </form>

        <p className="text-center text-xs text-tsushin-slate">
          &copy; 2026 Tsushin. Think, Secure, Build.
        </p>
      </div>
    </div>
  )
}
