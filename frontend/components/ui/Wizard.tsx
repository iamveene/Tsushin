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
  showCloseButton?: boolean
  closePrompt?: string | null
  status?: 'idle' | 'loading' | 'success' | 'error' | WizardStatus | null
  statusTitle?: string
  statusDescription?: string
  statusBody?: ReactNode
  stepTitle?: string
  stepDescription?: string
  tone?: 'default' | 'gmail'
}

const STATUS_STYLES: Record<NonNullable<WizardStatus['tone']>, string> = {
  info: 'bg-tsushin-indigo/10 border-tsushin-indigo/30 text-tsushin-indigo-glow',
  success: 'bg-tsushin-success/10 border-tsushin-success/30 text-tsushin-success',
  error: 'bg-tsushin-vermilion/10 border-tsushin-vermilion/30 text-tsushin-vermilion',
}

const STEP_ACCENT: Record<'default' | 'gmail', { active: string; complete: string }> = {
  default: {
    active: 'bg-tsushin-accent text-white border-tsushin-accent',
    complete: 'bg-tsushin-success/20 text-tsushin-success border-tsushin-success/40',
  },
  gmail: {
    active: 'bg-red-600 text-white border-red-500',
    complete: 'bg-red-500/15 text-red-300 border-red-500/30',
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
  showCloseButton = true,
  closePrompt = null,
  status = null,
  statusTitle,
  statusDescription,
  statusBody,
  stepTitle,
  stepDescription,
  tone = 'default',
}: WizardProps) {
  const accent = STEP_ACCENT[tone]
  const normalizedStatus = normalizeStatus(status, statusTitle, statusDescription)

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
