'use client'

/**
 * Forgot Password Page
 * Requests password reset email
 */

import React, { useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/contexts/AuthContext'
import { Input } from '@/components/ui/form-input'

export default function ForgotPasswordPage() {
  const { forgotPassword } = useAuth()
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess(false)
    setLoading(true)

    try {
      await forgotPassword(email)
      setSuccess(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send reset email')
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
            Reset your password
          </h2>
          <p className="mt-2 text-center text-sm text-tsushin-slate">
            Enter your email address and we'll send you a link to reset your password
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
                  Check your email
                </h4>
                <p className="text-sm text-tsushin-success-glow">
                  We've sent a password reset link to <strong>{email}</strong>. Please check your
                  inbox and follow the instructions.
                </p>
                <p className="text-xs text-tsushin-success/80 mt-2">
                  Didn't receive the email? Check your spam folder or{' '}
                  <button
                    type="button"
                    onClick={() => setSuccess(false)}
                    className="underline hover:no-underline"
                  >
                    try again
                  </button>
                  .
                </p>
              </div>
            )}

            {!success && (
              <>
                <Input
                  type="email"
                  label="Email address"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="you@example.com"
                />

                <button
                  type="submit"
                  disabled={loading}
                  className="btn-primary w-full flex justify-center py-2.5 px-4 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Sending...' : 'Send reset link'}
                </button>
              </>
            )}

            <div className="text-center">
              <Link
                href="/auth/login"
                className="text-sm font-medium text-teal-400 hover:text-teal-300"
              >
                ← Back to login
              </Link>
            </div>
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
