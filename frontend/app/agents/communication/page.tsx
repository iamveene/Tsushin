'use client'

/**
 * Studio - A2A Communications Page
 * Group-level configuration of inter-agent permission rules.
 * Observability (log, stats) lives in Watcher → A2A Comms.
 */

import StudioTabs from '@/components/studio/StudioTabs'
import A2APermissionsManager from '@/components/studio/A2APermissionsManager'

export default function A2ACommunicationsPage() {
  return (
    <div className="min-h-screen">
      <div className="w-full px-4 sm:px-6 lg:px-8 py-6">
        <div className="mb-5">
          <h1 className="text-2xl font-semibold text-white mb-1">A2A Communications</h1>
          <p className="text-sm text-tsushin-slate">Allow agents to message each other and delegate tasks. Configure who can reach whom.</p>
        </div>
      </div>

      <div className="w-full px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        <StudioTabs />
        <A2APermissionsManager />
      </div>
    </div>
  )
}
