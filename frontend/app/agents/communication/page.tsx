'use client'

import StudioTabs from '@/components/studio/StudioTabs'
import AgentCommunicationManager from '@/components/AgentCommunicationManager'

export default function CommunicationPage() {
  return (
    <div className="min-h-screen animate-fade-in">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-display font-bold text-white mb-2">Agent Communication</h1>
          <p className="text-tsushin-slate">Manage inter-agent messaging permissions and monitor communication sessions</p>
        </div>
      </div>
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        <StudioTabs />
        <AgentCommunicationManager />
      </div>
    </div>
  )
}
