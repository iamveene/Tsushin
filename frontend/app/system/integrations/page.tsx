'use client'

/**
 * /system/integrations is retained as a redirect stub.
 *
 * The old global-admin hub lived here (card grid + Google SSO config). Those
 * have moved:
 *   - Admin cards (Tenants, Users, Plans, Remote Access, SSO) → /settings (System group).
 *   - Google SSO config → /system/sso
 *
 * This stub exists so old bookmarks, email links, and tour anchors don't 404.
 * Safe to remove in a future release.
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function SystemIntegrationsRedirect() {
  const router = useRouter()
  useEffect(() => {
    router.replace('/settings')
  }, [router])
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-tsushin-slate">Redirecting to System settings…</div>
    </div>
  )
}
