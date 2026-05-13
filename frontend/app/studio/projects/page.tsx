'use client'

/**
 * /studio/projects → /agents/projects redirect.
 *
 * v0.7.x IA cleanup — pre-fix /studio/projects rendered a near-duplicate
 * of /agents/projects with a stripped-down 4-tab strip pointing back at
 * /agents/* routes. The two surfaces were the same conceptual page in
 * two routes; operators bookmarking one or the other landed in two
 * different chromes for the same data.
 *
 * /agents/projects is the canonical Studio surface (uses the full
 * StudioTabs strip with all 9 entries). This route forwards to it so
 * stored bookmarks / inbound deep-links keep working.
 *
 * /studio/projects/[id] (the project DETAIL page) is left in place for
 * now — the detail surface has its own layout that doesn't suffer from
 * the duplicate-tab-strip problem and tearing it out requires a router
 * sweep.
 */

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function StudioProjectsRedirect() {
  const router = useRouter()
  useEffect(() => {
    router.replace('/agents/projects')
  }, [router])
  return null
}
