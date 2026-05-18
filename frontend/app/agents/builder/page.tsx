'use client'

/**
 * Studio - Agent Builder Page
 * Visual node-based agent configuration builder
 */

import StudioTabs from '@/components/studio/StudioTabs'
import AgentStudioTab from '@/components/watcher/studio/AgentStudioTab'

export default function BuilderPage() {
  return (
    <div className="min-h-screen animate-fade-in">
      <div className="w-full px-4 sm:px-6 lg:px-8 py-6">
        <div className="mb-5 flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-display font-semibold text-white mb-1">Builder</h1>
            <p className="text-sm text-tsushin-slate">Visual canvas for wiring agents, skills, and triggers together.</p>
          </div>
        </div>
      </div>

      <div className="w-full px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        {/* Sub Navigation */}
        <StudioTabs />

        {/* Agent Studio Content */}
        <AgentStudioTab />
      </div>
    </div>
  )
}
