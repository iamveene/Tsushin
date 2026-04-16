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
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-display font-bold text-white mb-2">Agent Studio</h1>
            <p className="text-tsushin-slate">Visual agent configuration builder</p>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        {/* Sub Navigation */}
        <StudioTabs />

        {/* Agent Studio Content */}
        <AgentStudioTab />
      </div>
    </div>
  )
}
