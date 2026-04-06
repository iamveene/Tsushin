'use client'

import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'
import Modal from '@/components/ui/Modal'
import StepWelcome from './StepWelcome'
import StepCreateInstance from './StepCreateInstance'
import StepDmConfig from './StepDmConfig'
import StepGroupConfig from './StepGroupConfig'
import StepContacts from './StepContacts'
import StepBindAgent from './StepBindAgent'
import StepConfirmation from './StepConfirmation'

const stepTitles = [
  'Welcome',
  'Connect Phone',
  'DM Settings',
  'Group Settings',
  'Contacts',
  'Bind Agent',
  'All Done!',
]

export default function WhatsAppSetupWizard() {
  const { state, closeWizard, previousStep, nextStep, goToStep } = useWhatsAppWizard()

  if (!state.isOpen) return null

  const handleClose = () => {
    if (state.currentStep > 1 && state.currentStep < state.totalSteps) {
      if (window.confirm('Close the wizard? Your progress so far is saved — you can restart from the Hub page.')) {
        closeWizard()
      }
    } else {
      closeWizard()
    }
  }

  const renderStep = () => {
    switch (state.currentStep) {
      case 1: return <StepWelcome />
      case 2: return <StepCreateInstance />
      case 3: return <StepDmConfig />
      case 4: return <StepGroupConfig />
      case 5: return <StepContacts />
      case 6: return <StepBindAgent />
      case 7: return <StepConfirmation />
      default: return null
    }
  }

  // Steps 3-6 require an instance to be created first
  const canAccessStep = (step: number) => {
    if (step <= 2) return true
    return !!state.createdInstanceId
  }

  return (
    <Modal
      isOpen={state.isOpen}
      onClose={handleClose}
      title={`WhatsApp Setup — ${stepTitles[state.currentStep - 1]}`}
      size="xl"
      footer={
        state.currentStep > 1 && state.currentStep < state.totalSteps ? (
          <div className="flex items-center justify-between">
            <button
              onClick={previousStep}
              className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors rounded-lg"
            >
              &larr; Back
            </button>
            <div className="flex items-center gap-2">
              {/* Step indicator pills */}
              {stepTitles.map((_, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    if (canAccessStep(idx + 1) && state.currentStep !== idx + 1) {
                      goToStep(idx + 1)
                    }
                  }}
                  className={`w-2 h-2 rounded-full transition-colors ${
                    idx + 1 === state.currentStep
                      ? 'bg-teal-500'
                      : state.stepsCompleted[idx + 1]
                      ? 'bg-green-500'
                      : idx + 1 < state.currentStep
                      ? 'bg-tsushin-slate/60'
                      : 'bg-tsushin-slate/20'
                  }`}
                />
              ))}
            </div>
            <button
              onClick={nextStep}
              disabled={!canAccessStep(state.currentStep + 1)}
              className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors rounded-lg disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Skip &rarr;
            </button>
          </div>
        ) : undefined
      }
    >
      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-tsushin-slate">
            Step {state.currentStep} of {state.totalSteps}
          </span>
          {state.currentStep > 1 && state.currentStep < state.totalSteps && (
            <span className="text-xs text-tsushin-slate/60">
              {stepTitles[state.currentStep - 1]}
            </span>
          )}
        </div>
        <div className="w-full bg-tsushin-deep rounded-full h-1.5">
          <div
            className="bg-gradient-to-r from-teal-500 to-cyan-500 h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${(state.currentStep / state.totalSteps) * 100}%` }}
          />
        </div>
      </div>

      {renderStep()}
    </Modal>
  )
}
