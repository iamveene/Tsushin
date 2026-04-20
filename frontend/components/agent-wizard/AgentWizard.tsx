'use client'

import { useState, useEffect } from 'react'
import Modal from '@/components/ui/Modal'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import type { StepKey } from '@/lib/agent-wizard/reducer'
import StepTypeSelect from './steps/StepTypeSelect'
import StepBasics from './steps/StepBasics'
import StepPersonality from './steps/StepPersonality'
import StepAudio from './steps/StepAudio'
import StepSkills from './steps/StepSkills'
import StepMemory from './steps/StepMemory'
import StepChannels from './steps/StepChannels'
import StepReview from './steps/StepReview'
import StepProgress from './steps/StepProgress'

const STEP_LABELS: Record<StepKey, string> = {
  type: 'Type',
  basics: 'Basics',
  personality: 'Personality',
  audio: 'Voice',
  skills: 'Skills',
  memory: 'Memory',
  channels: 'Channels',
  review: 'Review',
  progress: 'Progress',
}

export default function AgentWizard() {
  const wiz = useAgentWizard()
  const { state, stepOrder, totalSteps, stepIndex, closeWizard, nextStep, previousStep, setMode, clearPersistedDraft, openWizard } = wiz
  const [askClose, setAskClose] = useState(false)

  useEffect(() => {
    if (!state.isOpen) setAskClose(false)
  }, [state.isOpen])

  const requestClose = () => {
    // If nothing meaningful chosen, close silently.
    if (!state.draft.type && state.currentStep === 'type') {
      closeWizard()
      return
    }
    // On progress step after success, just close.
    if (state.currentStep === 'progress' && state.progressStatus === 'done') {
      closeWizard()
      return
    }
    setAskClose(true)
  }

  const confirmClose = () => {
    setAskClose(false)
    clearPersistedDraft()
    closeWizard()
  }

  const switchToAdvanced = () => {
    setMode('advanced')
    // closeWizard() persists the current draft so the legacy modal can read it on open.
    closeWizard()
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('tsushin:open-agent-advanced-modal'))
    }
  }

  const isProgress = state.currentStep === 'progress'
  const showCloseButton = !isProgress || state.progressStatus === 'done' || state.progressStatus === 'error'

  const stepIndicator = (
    <div className="flex items-center justify-center gap-1 mb-5 flex-wrap">
      {stepOrder.slice(0, totalSteps).map((key, n) => {
        const isCurrent = n === stepIndex
        const isComplete = state.stepsCompleted[key] && !isCurrent
        return (
          <div key={key} className="flex items-center gap-1">
            <div
              title={`Step ${n + 1}: ${STEP_LABELS[key]}`}
              aria-label={`Step ${n + 1}: ${STEP_LABELS[key]}, ${isCurrent ? 'current' : isComplete ? 'complete' : 'upcoming'}`}
              className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
                isCurrent ? 'bg-teal-500 text-white' :
                isComplete ? 'bg-teal-500/20 text-teal-400' :
                'bg-white/5 text-gray-500'
              }`}
            >
              {isComplete ? '✓' : n + 1}
            </div>
            {n < totalSteps - 1 && (
              <div className={`w-6 h-0.5 ${isComplete ? 'bg-teal-500/40' : 'bg-white/5'}`} />
            )}
          </div>
        )
      })}
    </div>
  )

  const canAdvance = state.stepsCompleted[state.currentStep]

  const renderStep = () => {
    switch (state.currentStep) {
      case 'type': return <StepTypeSelect />
      case 'basics': return <StepBasics />
      case 'personality': return <StepPersonality />
      case 'audio': return <StepAudio />
      case 'skills': return <StepSkills />
      case 'memory': return <StepMemory />
      case 'channels': return <StepChannels />
      case 'review': return <StepReview />
      case 'progress': return <StepProgress />
      default: return null
    }
  }

  const footer = isProgress ? (
    <div className="flex items-center justify-end w-full gap-2">
      {state.progressStatus === 'error' && (
        <>
          <button onClick={() => wiz.goToStep('review')} className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">← Back to Review</button>
          <button onClick={confirmClose} className="px-4 py-2 text-sm bg-red-500/20 hover:bg-red-500/30 text-red-200 rounded-lg transition-colors">Close</button>
        </>
      )}
      {state.progressStatus === 'done' && (
        <button onClick={confirmClose} className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors">Done</button>
      )}
    </div>
  ) : (
    <div className="flex items-center justify-between w-full">
      <div className="flex items-center gap-2">
        {stepIndex > 0 && (
          <button
            type="button"
            onClick={previousStep}
            className="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
          >
            ← Back
          </button>
        )}
      </div>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={switchToAdvanced}
          className="px-3 py-2 text-xs text-gray-400 hover:text-white transition-colors underline decoration-dotted"
        >
          Switch to Advanced
        </button>
        {state.currentStep === 'review' ? (
          <span className="text-xs text-gray-500">Press <span className="text-teal-400">Create</span> below</span>
        ) : (
          <button
            type="button"
            onClick={nextStep}
            disabled={!canAdvance}
            className="px-4 py-2 text-sm bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next →
          </button>
        )}
      </div>
    </div>
  )

  return (
    <>
      <Modal
        isOpen={state.isOpen}
        onClose={requestClose}
        title="Create New Agent"
        footer={footer}
        size="xl"
        showCloseButton={showCloseButton}
      >
        <div className="space-y-5">
          {stepIndicator}
          {renderStep()}
        </div>
      </Modal>

      {askClose && (
        <Modal
          isOpen={true}
          onClose={() => setAskClose(false)}
          title="Close the wizard?"
          size="sm"
          footer={
            <div className="flex items-center justify-end w-full gap-2">
              <button onClick={() => setAskClose(false)} className="px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors">Keep editing</button>
              <button onClick={confirmClose} className="px-3 py-1.5 text-sm bg-red-500/20 hover:bg-red-500/30 text-red-200 rounded-lg transition-colors">Discard</button>
            </div>
          }
        >
          <div className="text-sm text-gray-300">
            Your progress will be lost unless you've already created the agent.
          </div>
        </Modal>
      )}
    </>
  )
}
