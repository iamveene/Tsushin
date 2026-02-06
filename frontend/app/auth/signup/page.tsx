'use client'

/**
 * Signup Page - Disabled
 * Self-registration is not available. Redirects to login.
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function SignupPage() {
  const router = useRouter()

  useEffect(() => {
    router.replace('/auth/login')
  }, [router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <p className="text-gray-600 dark:text-gray-400">Redirecting to login...</p>
    </div>
  )
}
