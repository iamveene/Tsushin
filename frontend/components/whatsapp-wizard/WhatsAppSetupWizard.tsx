'use client'

import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'
import Wizard, { type WizardStep } from '@/components/ui/Wizard'
import StepWelcome from './StepWelcome'
import StepCreateInstance from './StepCreateInstance'
import StepUserInfo from './StepUserInfo'
import StepDmConfig from './StepDmConfig'
import StepGroupConfig from './StepGroupConfig'
import StepContacts from './StepContacts'
import StepBindAgent from './StepBindAgent'
import StepConfirmation from './StepConfirmation'

const WIZARD_STEPS: WizardStep[] = [
  { id: 'welcome', label: 'Welcome', description: 'Overview' },
  { id: 'connect-phone', label: 'Connect Phone', description: 'MCP instance' },
  { id: 'user-info', label: 'About You', description: 'Profile' },
  { id: 'dm-config', label: 'DM Settings', description: 'Direct chat' },
  { id: 'group-config', label: 'Group Settings', description: 'Groups' },
  { id: 'contacts', label: 'Contacts', description: 'Allowlist' },
  { id: 'bind-agent', label: 'Bind Agent', description: 'Routing' },
  { id: 'done', label: 'All Done!', description: 'Finish' },
]

export default function WhatsAppSetupWizard() {
  const { state, closeWizard, previousStep, nextStep } = useWhatsAppWizard()
  const stepTitles = WIZARD_STEPS.map(step => step.label)

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
      case 3: return <StepUserInfo />
      case 4: return <StepDmConfig />
      case 5: return <StepGroupConfig />
      case 6: return <StepContacts />
      case 7: return <StepBindAgent />
      case 8: return <StepConfirmation />
      default: return null
    }
  }

  // Steps 3-8 require an instance to be created first
  const canAccessStep = (step: number) => {
    if (step <= 2) return true
    return !!state.createdInstanceId
  }

  return (
    <Wizard
      isOpen={state.isOpen}
      onClose={handleClose}
      title="WhatsApp Setup"
      steps={WIZARD_STEPS}
      currentStep={state.currentStep}
      size="xl"
      autoHeight
      showProgress
      tone="whatsapp"
      footer={
        state.currentStep === 1 ? (
          <button
            type="button"
            onClick={nextStep}
            className="w-full py-3 bg-gradient-to-r from-teal-500 to-cyan-500 text-white font-semibold rounded-lg hover:from-teal-600 hover:to-cyan-600 transition-all"
          >
            Let&apos;s Get Started
          </button>
        ) : state.currentStep > 1 && state.currentStep < state.totalSteps ? (
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={previousStep}
              className="px-4 py-2 text-tsushin-slate hover:text-white transition-colors rounded-lg"
            >
              &larr; Back
            </button>
            <div className="hidden sm:block text-xs text-tsushin-slate">
              {stepTitles[state.currentStep - 1]}
            </div>
            <button
              type="button"
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
      {renderStep()}
    </Wizard>
  )
}
