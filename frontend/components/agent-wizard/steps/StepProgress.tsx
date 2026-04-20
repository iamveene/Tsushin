'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAgentWizard } from '@/contexts/AgentWizardContext'

export default function StepProgress() {
  const wiz = useAgentWizard()
  const router = useRouter()
  const { state, closeWizard } = wiz
  const { progressStatus, progressMessage, createdAgentId, failedStep } = state

  useEffect(() => {
    // Auto-dismiss timer isn't desired — user may want to read the state.
    // Navigation only fires when user explicitly clicks "Chat with agent now".
  }, [progressStatus])

  const openPlayground = () => {
    if (createdAgentId) {
      router.push(`/playground?agent=${createdAgentId}`)
    }
    closeWizard()
  }

  const goToAgentsList = () => {
    closeWizard()
  }

  return (
    <div className="space-y-5 py-4">
      <div className="flex items-start gap-4">
        {progressStatus === 'running' && (
          <svg className="animate-spin h-10 w-10 text-teal-400 flex-shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
          </svg>
        )}
        {progressStatus === 'done' && (
          <div className="w-10 h-10 rounded-full bg-emerald-500/20 border border-emerald-500/50 flex items-center justify-center text-emerald-300 text-xl flex-shrink-0">✓</div>
        )}
        {progressStatus === 'error' && (
          <div className="w-10 h-10 rounded-full bg-red-500/20 border border-red-500/50 flex items-center justify-center text-red-300 text-xl flex-shrink-0">×</div>
        )}
        <div className="flex-1">
          <div className="text-white font-medium">
            {progressStatus === 'running' && 'Setting up your agent…'}
            {progressStatus === 'done' && 'Your agent is ready'}
            {progressStatus === 'error' && 'Something went wrong'}
          </div>
          <div className="text-xs text-gray-400 mt-1">{progressMessage || '—'}</div>
          {failedStep && (
            <div className="text-xs text-amber-300 mt-1">Failed at stage: <span className="font-mono">{failedStep}</span></div>
          )}
        </div>
      </div>

      {progressStatus === 'done' && createdAgentId && (
        <div className="p-4 rounded-xl bg-white/[0.02] border border-white/10 space-y-3">
          <div className="text-sm text-white">Your new agent has been created.</div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={openPlayground}
              className="px-3 py-1.5 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors"
            >
              Chat with agent now →
            </button>
            <button
              type="button"
              onClick={goToAgentsList}
              className="px-3 py-1.5 text-sm text-gray-300 hover:text-white transition-colors"
            >
              Back to agents
            </button>
          </div>
        </div>
      )}

      {progressStatus === 'error' && createdAgentId && (
        <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 space-y-2">
          <div className="text-sm text-amber-200">
            The agent was created (id: <span className="font-mono">{createdAgentId}</span>) but the <span className="font-mono">{failedStep}</span> step failed.
          </div>
          <div className="flex items-center gap-2">
            <a
              href={`/agents/${createdAgentId}`}
              className="px-3 py-1.5 text-xs bg-white/5 hover:bg-white/10 text-white rounded-lg transition-colors"
            >
              Open agent in Studio
            </a>
          </div>
        </div>
      )}
    </div>
  )
}
