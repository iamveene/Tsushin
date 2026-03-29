'use client'

/**
 * Reset Password Page
 * Handles password reset with token from email link
 */

import React, { useState, useEffect, Suspense } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { api } from '@/lib/client'
import { Input } from '@/components/ui/form-input'

function ResetPasswordForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const token = searchParams.get('token')

  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!token) {
      setError('Invalid or missing reset token')
    }
  }, [token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!token) {
      setError('Invalid or missing reset token')
      return
    }

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
      await api.confirmPasswordReset(token, password)
      setSuccess(true)
      setTimeout(() => {
        router.push('/auth/login')
      }, 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-tsushin-ink py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        {/* Header */}
        <div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-white">
            Create new password
          </h2>
          <p className="mt-2 text-center text-sm text-tsushin-slate">
            Enter your new password below
          </p>
        </div>

        {/* Form */}
        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="bg-tsushin-surface border border-tsushin-border rounded-2xl shadow-elevated p-8 space-y-6">
            {error && (
              <div className="bg-tsushin-vermilion/10 border border-tsushin-vermilion/30 rounded-md p-3">
                <p className="text-sm text-tsushin-vermilion">{error}</p>
              </div>
            )}

            {success && (
              <div className="bg-tsushin-success/10 border border-tsushin-success/30 rounded-md p-4">
                <h4 className="text-sm font-semibold text-tsushin-success mb-2">
                  Password reset successful!
                </h4>
                <p className="text-sm text-tsushin-success-glow">
                  Your password has been reset. Redirecting to login...
                </p>
              </div>
            )}

            {!success && (
              <>
                <Input
                  type="password"
                  label="New Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                  placeholder="••••••••"
                  helperText="Must be at least 8 characters"
                />

                <Input
                  type="password"
                  label="Confirm New Password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                  placeholder="••••••••"
                />

                <button
                  type="submit"
                  disabled={loading || !token}
                  className="btn-primary w-full flex justify-center py-2.5 px-4 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Resetting...' : 'Reset password'}
                </button>
              </>
            )}

            {!success && (
              <div className="text-center">
                <Link
                  href="/auth/login"
                  className="text-sm font-medium text-teal-400 hover:text-teal-300"
                >
                  ← Back to login
                </Link>
              </div>
            )}
          </div>
        </form>

        {/* Footer */}
        <p className="text-center text-xs text-tsushin-slate">
          &copy; 2026 Tsushin. All rights reserved.
        </p>
      </div>
    </div>
  )
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-tsushin-ink">
        <div className="text-tsushin-slate">Loading...</div>
      </div>
    }>
      <ResetPasswordForm />
    </Suspense>
  )
}
