'use client'

import { ReactNode } from 'react'
import Modal from '@/components/ui/Modal'

export interface WizardStep {
  id: string
  label: string
  description?: string
}

interface WizardStatus {
  tone?: 'info' | 'success' | 'error'
  title: string
  message?: string
}

interface WizardProps {
  isOpen: boolean
  onClose: () => void
  title: string
  children?: ReactNode
  steps: WizardStep[]
  currentStep: number
  footer?: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl'
  autoHeight?: boolean
  showCloseButton?: boolean
  closePrompt?: string | null
  status?: 'idle' | 'loading' | 'success' | 'error' | WizardStatus | null
  statusTitle?: string
  statusDescription?: string
  statusBody?: ReactNode
  stepTitle?: string
  stepDescription?: string
  showProgress?: boolean
  tone?: 'default' | 'gmail' | 'discord' | 'slack' | 'whatsapp' | 'mcp'
}

const STATUS_STYLES: Record<NonNullable<WizardStatus['tone']>, string> = {
  info: 'bg-tsushin-indigo/10 border-tsushin-indigo/30 text-tsushin-indigo-glow',
  success: 'bg-tsushin-success/10 border-tsushin-success/30 text-tsushin-success',
  error: 'bg-tsushin-vermilion/10 border-tsushin-vermilion/30 text-tsushin-vermilion',
}

type WizardTone = NonNullable<WizardProps['tone']>

const STEP_ACCENT: Record<WizardTone, { active: string; complete: string; progress: string }> = {
  default: {
    active: 'bg-tsushin-accent text-white border-tsushin-accent',
    complete: 'bg-tsushin-success/20 text-tsushin-success border-tsushin-success/40',
    progress: 'bg-tsushin-accent',
  },
  gmail: {
    active: 'bg-red-600 text-white border-red-500',
    complete: 'bg-red-500/15 text-red-300 border-red-500/30',
    progress: 'bg-red-500',
  },
  discord: {
    active: 'bg-indigo-600 text-white border-indigo-500',
    complete: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
    progress: 'bg-indigo-500',
  },
  slack: {
    active: 'bg-purple-600 text-white border-purple-500',
    complete: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
    progress: 'bg-purple-500',
  },
  whatsapp: {
    active: 'bg-teal-600 text-white border-teal-500',
    complete: 'bg-teal-500/15 text-teal-300 border-teal-500/30',
    progress: 'bg-teal-500',
  },
  mcp: {
    active: 'bg-emerald-600 text-white border-emerald-500',
    complete: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    progress: 'bg-emerald-500',
  },
}

function normalizeStatus(
  status: WizardProps['status'],
  statusTitle?: string,
  statusDescription?: string,
): WizardStatus | null {
  if (!status || status === 'idle') return null
  if (typeof status === 'object') return status

  if (status === 'success') {
    return {
      tone: 'success',
      title: statusTitle || 'Completed',
      message: statusDescription,
    }
  }
  if (status === 'error') {
    return {
      tone: 'error',
      title: statusTitle || 'Something went wrong',
      message: statusDescription,
    }
  }
  return {
    tone: 'info',
    title: statusTitle || 'Working…',
    message: statusDescription,
  }
}

export default function Wizard({
  isOpen,
  onClose,
  title,
  children,
  steps,
  currentStep,
  footer,
  size = 'lg',
  autoHeight = false,
  showCloseButton = true,
  closePrompt = null,
  status = null,
  statusTitle,
  statusDescription,
  statusBody,
  stepTitle,
  stepDescription,
  showProgress = false,
  tone = 'default',
}: WizardProps) {
  const accent = STEP_ACCENT[tone]
  const normalizedStatus = normalizeStatus(status, statusTitle, statusDescription)
  const currentStepLabel = steps[currentStep - 1]?.label
  const progressPercent = steps.length > 0
    ? Math.min(100, Math.max(0, Math.round((currentStep / steps.length) * 100)))
    : 0

  const handleClose = () => {
    if (closePrompt && typeof window !== 'undefined' && !window.confirm(closePrompt)) {
      return
    }
    onClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={title}
      footer={footer}
      size={size}
      autoHeight={autoHeight}
      showCloseButton={showCloseButton}
    >
      <div className="space-y-5">
        <div className="flex flex-wrap items-start gap-3">
          {steps.map((step, index) => {
            const stepNumber = index + 1
            const isActive = stepNumber === currentStep
            const isComplete = stepNumber < currentStep
            return (
              <div key={step.id} className="flex items-center gap-3 min-w-0">
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={`w-7 h-7 rounded-full border flex items-center justify-center text-xs font-semibold ${
                      isActive
                        ? accent.active
                        : isComplete
                        ? accent.complete
                        : 'bg-tsushin-slate/10 text-tsushin-slate border-tsushin-border'
                    }`}
                  >
                    {isComplete ? '✓' : stepNumber}
                  </div>
                  <div className="min-w-0">
                    <div className={`text-sm font-medium ${isActive ? 'text-white' : 'text-tsushin-fog'}`}>
                      {step.label}
                    </div>
                    {step.description && (
                      <div className="text-[11px] text-tsushin-slate truncate">
                        {step.description}
                      </div>
                    )}
                  </div>
                </div>
                {index < steps.length - 1 && (
                  <div className={`hidden sm:block w-8 h-px ${isComplete ? 'bg-tsushin-success/40' : 'bg-tsushin-border'}`} />
                )}
              </div>
            )
          })}
        </div>

        {showProgress && (
          <div>
            <div className="mb-2 flex items-center justify-between gap-4 text-xs text-tsushin-slate">
              <span>Step {currentStep} of {steps.length}</span>
              {currentStepLabel && <span className="truncate">{currentStepLabel}</span>}
            </div>
            <div className="h-1.5 w-full rounded-full bg-tsushin-deep">
              <div
                className={`h-1.5 rounded-full transition-all duration-300 ${accent.progress}`}
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        )}

        {(stepTitle || stepDescription) && (
          <div className="space-y-1">
            {stepTitle && <div className="text-lg font-semibold text-white">{stepTitle}</div>}
            {stepDescription && <div className="text-sm text-tsushin-slate">{stepDescription}</div>}
          </div>
        )}

        {normalizedStatus && (
          <div className={`rounded-xl border px-4 py-3 ${STATUS_STYLES[normalizedStatus.tone || 'info']}`}>
            <div className="text-sm font-semibold">{normalizedStatus.title}</div>
            {normalizedStatus.message && <div className="text-xs mt-1 opacity-90">{normalizedStatus.message}</div>}
            {statusBody && <div className="mt-3">{statusBody}</div>}
          </div>
        )}

        {children}
      </div>
    </Modal>
  )
}
