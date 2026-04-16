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
    <div className="min-h-screen flex items-center justify-center bg-tsushin-ink">
      <p className="text-tsushin-slate">Redirecting to login...</p>
    </div>
  )
}
