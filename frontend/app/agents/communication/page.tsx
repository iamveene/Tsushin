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
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Agent Studio</h1>
          <p className="text-tsushin-slate">Wire agents together for inter-agent messaging and task delegation</p>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        <StudioTabs />
        <A2APermissionsManager />
      </div>
    </div>
  )
}
