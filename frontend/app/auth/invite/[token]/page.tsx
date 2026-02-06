'use client'

/**
 * Invitation Accept Page
 * Allows users to accept an invitation and create their account
 * Supports both local registration and Google SSO
 * Phase 7.9: RBAC & Multi-tenancy
 */

import { useState, useEffect } from 'react'
import { useParams, useRouter } from 'next/navigation'
import Link from 'next/link'
import { api, InvitationInfo, GoogleSSOStatus } from '@/lib/client'
import { useAuth } from '@/contexts/AuthContext'

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

export default function AcceptInvitationPage() {
  const params = useParams()
  const router = useRouter()
  const { loginWithGoogle } = useAuth()
  const token = params.token as string

  const [invitationInfo, setInvitationInfo] = useState<InvitationInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)
  const [googleSSOEnabled, setGoogleSSOEnabled] = useState(false)
  const [formData, setFormData] = useState({
    full_name: '',
    password: '',
    confirmPassword: '',
  })
  const [formErrors, setFormErrors] = useState<string[]>([])

  // Fetch invitation info and SSO status on mount
  useEffect(() => {
    const fetchData = async () => {
      try {
        const info = await api.getInvitationInfo(token)
        setInvitationInfo(info)

        if (!info.is_valid) {
          setError('This invitation has expired. Please contact the person who invited you.')
        } else {
          // Check if Google SSO is available (platform-wide)
          try {
            const ssoStatus = await api.getGoogleSSOStatus()
            setGoogleSSOEnabled(ssoStatus.enabled)
          } catch (err) {
            console.error('Failed to check SSO status:', err)
          }
        }
      } catch (err: any) {
        setError(err.message || 'Invalid invitation')
      } finally {
        setLoading(false)
      }
    }

    if (token) {
      fetchData()
    }
  }, [token])

  // Handle Google SSO sign up
  const handleGoogleSignUp = async () => {
    setGoogleLoading(true)
    try {
      await loginWithGoogle({
        invitationToken: token,
        redirectAfter: '/',
      })
    } catch (err: any) {
      setFormErrors([err.message || 'Google sign up failed'])
      setGoogleLoading(false)
    }
  }

  const validateForm = (): boolean => {
    const errors: string[] = []

    if (!formData.full_name.trim()) {
      errors.push('Full name is required')
    }

    if (formData.password.length < 8) {
      errors.push('Password must be at least 8 characters')
    }

    if (formData.password !== formData.confirmPassword) {
      errors.push('Passwords do not match')
    }

    setFormErrors(errors)
    return errors.length === 0
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!validateForm()) return

    setSubmitting(true)
    setFormErrors([])

    try {
      const response = await api.acceptInvitation(token, {
        password: formData.password,
        full_name: formData.full_name,
      })

      // Store the token and redirect to home
      localStorage.setItem('tsushin_auth_token', response.access_token)

      // Show success briefly then redirect
      router.push('/')
    } catch (err: any) {
      setFormErrors([err.message || 'Failed to accept invitation'])
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-gray-600 dark:text-gray-400">Loading invitation...</div>
      </div>
    )
  }

  if (error || !invitationInfo) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-md p-8 text-center">
          <div className="mb-4"><svg className="w-10 h-10 mx-auto text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><line x1="15" y1="9" x2="9" y2="15" /><line x1="9" y1="9" x2="15" y2="15" /></svg></div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Invalid Invitation
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            {error || 'This invitation link is invalid or has expired.'}
          </p>
          <Link
            href="/auth/login"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            Go to Login
          </Link>
        </div>
      </div>
    )
  }

  if (!invitationInfo.is_valid) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-md p-8 text-center">
          <div className="mb-4"><svg className="w-10 h-10 mx-auto text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg></div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Invitation Expired
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            This invitation has expired. Please contact{' '}
            <strong>{invitationInfo.inviter_name}</strong> to send a new invitation.
          </p>
          <Link
            href="/auth/login"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            Go to Login
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-4">
      <div className="max-w-md w-full">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-2">
            Join {invitationInfo.tenant_name}
          </h1>
          <p className="text-gray-600 dark:text-gray-400">
            {invitationInfo.inviter_name} invited you to join as{' '}
            <strong>{invitationInfo.role_display_name}</strong>
          </p>
        </div>

        {/* Invitation Details Card */}
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-6">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-blue-700 dark:text-blue-300 font-medium">Organization</div>
              <div className="text-blue-900 dark:text-blue-100">{invitationInfo.tenant_name}</div>
            </div>
            <div>
              <div className="text-blue-700 dark:text-blue-300 font-medium">Role</div>
              <div className="text-blue-900 dark:text-blue-100">
                {invitationInfo.role_display_name}
              </div>
            </div>
            <div>
              <div className="text-blue-700 dark:text-blue-300 font-medium">Email</div>
              <div className="text-blue-900 dark:text-blue-100">{invitationInfo.email}</div>
            </div>
            <div>
              <div className="text-blue-700 dark:text-blue-300 font-medium">Invited by</div>
              <div className="text-blue-900 dark:text-blue-100">{invitationInfo.inviter_name}</div>
            </div>
          </div>
        </div>

        {/* Registration Form */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
            Create Your Account
          </h2>

          {formErrors.length > 0 && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded">
              <ul className="text-sm text-red-800 dark:text-red-200 list-disc list-inside">
                {formErrors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Google SSO Option */}
          {googleSSOEnabled && (
            <>
              <button
                type="button"
                onClick={handleGoogleSignUp}
                disabled={submitting || googleLoading}
                className="w-full flex items-center justify-center gap-3 py-2 px-4 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {googleLoading ? (
                  <svg className="animate-spin h-5 w-5 text-gray-500" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                ) : (
                  <GoogleIcon />
                )}
                {googleLoading ? 'Connecting...' : 'Continue with Google'}
              </button>

              <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 text-center">
                Use {invitationInfo.email} to sign in with Google
              </p>

              <div className="relative my-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300 dark:border-gray-600" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                    Or create a password
                  </span>
                </div>
              </div>
            </>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email (readonly) */}
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                Email
              </label>
              <input
                type="email"
                value={invitationInfo.email}
                disabled
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-900 cursor-not-allowed"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                This email is linked to your invitation
              </p>
            </div>

            {/* Full Name */}
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                Full Name
              </label>
              <input
                type="text"
                value={formData.full_name}
                onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                placeholder="John Doe"
                required
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Password */}
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                Password
              </label>
              <input
                type="password"
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                placeholder="Min 8 characters"
                required
                minLength={8}
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Confirm Password */}
            <div>
              <label className="block text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                Confirm Password
              </label>
              <input
                type="password"
                value={formData.confirmPassword}
                onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                placeholder="Re-enter password"
                required
                className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={submitting || googleLoading}
              className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? 'Creating Account...' : 'Accept Invitation & Join'}
            </button>
          </form>

          {/* Already have account */}
          <div className="mt-4 text-center text-sm text-gray-600 dark:text-gray-400">
            Already have an account?{' '}
            <Link href="/auth/login" className="text-blue-600 dark:text-blue-400 hover:underline">
              Sign in
            </Link>
          </div>
        </div>

        {/* Terms */}
        <p className="mt-4 text-center text-xs text-gray-500 dark:text-gray-400">
          By accepting this invitation, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  )
}
